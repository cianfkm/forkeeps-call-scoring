"""Keep only first calls to genuinely new enquiries (v6 section 3 / brief 4.3). Log every drop."""
import html
import re

from . import hubspot
from .config import SETTINGS

DAY_MS = 86_400_000
LINK_RE = re.compile(r"https?://dialpad\.com/callhistory/callreview/(\d+)[^\s\"'<>]*")
DEAL_PROPS = ["dealname", "amount", "dealstage", SETTINGS["DEAL_TYPE_PROPERTY"]]


def dialpad_link(body):
    """(call_id, full Call Summary Link) from hs_call_body. The coaching-tab recording ID is NOT this ID."""
    m = LINK_RE.search(html.unescape(body or ""))
    return (m.group(1), m.group(0)) if m else (None, None)


def stage_at(history, ms):
    """Lifecycle stage in force at `ms` (history is newest first), or None if none was set yet."""
    return next((h["value"] for h in history if h["ms"] <= ms), None)


def _lifecycle_reason(c, call_ms):
    """Judged as at the call, not today: a contact who has since bought is still in scope.
    Qualifies if not already past opportunity when called, and reached opportunity by call + grace days."""
    want = SETTINGS["LIFECYCLE_STAGE"]
    hist = (c.get("_history") or {}).get("lifecyclestage") or []
    if not hist:  # no history returned: fall back to today's value
        now = (c.get("lifecyclestage") or "").lower()
        return None if now == want else f"lifecycle stage is '{now or 'blank'}', not opportunity"
    then = (stage_at(hist, call_ms) or "").lower()
    if then and then not in ("lead", "subscriber", "marketingqualifiedlead", "salesqualifiedlead", want):
        return f"lifecycle stage was '{then}' at the time of the call, not opportunity"
    cutoff = call_ms + SETTINGS["OPPORTUNITY_GRACE_DAYS"] * DAY_MS
    if not any((h["value"] or "").lower() == want and h["ms"] <= cutoff for h in hist):
        return f"never reached opportunity within {SETTINGS['OPPORTUNITY_GRACE_DAYS']} days of the call (stage then '{then or 'blank'}')"
    return None


def _contact_reason(c, call_ms, deals):
    """(reason, note): reason is None if the contact qualifies; note flags a lenient pass for the log."""
    why = _lifecycle_reason(c, call_ms)
    if why:
        return why, None
    created = hubspot.parse_ms(c.get("createdate"))
    age_days = (call_ms - created) / DAY_MS
    if age_days > SETTINGS["NEW_CONTACT_WINDOW_DAYS"]:
        return f"contact created {age_days:.0f} days before the call (window {SETTINGS['NEW_CONTACT_WINDOW_DAYS']})", None
    if not deals:
        return "no associated deal", None
    prop, want = SETTINGS["DEAL_TYPE_PROPERTY"], SETTINGS["DEAL_TYPE_VALUE"].lower()
    types = [(d.get(prop) or "").lower() for d in deals]
    if want in types:
        return None, None
    if SETTINGS["ALLOW_BLANK_DEAL_TYPE"] and "" in types:
        return None, "deal type (system) blank, allowed"
    return f"no New Business deal (deal types: {', '.join(sorted({t or 'blank' for t in types}))})", None


def qualify(calls):
    """calls: HubSpot call records (already >2 min). Returns (kept, dropped)."""
    call_contacts = hubspot.associations("calls", "contacts", [c["id"] for c in calls])
    contact_ids = {x for ids in call_contacts.values() for x in ids}
    contacts = hubspot.batch_read("contacts", contact_ids, hubspot.CONTACT_PROPS, history=["lifecyclestage"])
    contact_deals = hubspot.associations("contacts", "deals", contact_ids)
    deals = hubspot.batch_read("deals", {x for ids in contact_deals.values() for x in ids}, DEAL_PROPS)

    kept, dropped = [], []
    for c in calls:
        p = c["properties"]
        call_ms = hubspot.parse_ms(p.get("hs_timestamp"))
        base = {"hs_id": c["id"], "ts_ms": call_ms, "duration_ms": int(float(p.get("hs_call_duration") or 0)),
                "title": p.get("hs_call_title") or "", "to_number": p.get("hs_call_to_number") or ""}
        cids = [x for x in call_contacts.get(c["id"], []) if x in contacts]
        if not cids:
            dropped.append({**base, "reason": "no contact record"})
            continue
        chosen, reasons, note = None, [], None
        for cid in cids:
            cdeals = [deals[d] for d in contact_deals.get(cid, []) if d in deals]
            why, note = _contact_reason(contacts[cid], call_ms, cdeals)
            if why is None:
                chosen = (cid, cdeals)
                break
            reasons.append(why)
        if not chosen:
            dropped.append({**base, "reason": "; ".join(dict.fromkeys(reasons))})
            continue
        cid, cdeals = chosen
        ct = contacts[cid]
        dp_id, link = dialpad_link(p.get("hs_call_body"))
        kept.append({**base, "contact_id": cid,
                     "customer": " ".join(x for x in [ct.get("firstname"), ct.get("lastname")] if x).strip() or "(no name)",
                     "company": (ct.get("company") or "").strip(),
                     "deals": [d.get("dealname") for d in cdeals if d.get("dealname")],
                     "dialpad_id": dp_id, "listen_url": link, "body": p.get("hs_call_body") or "", "note": note})

    # Repeat calls to the same contact in the week: keep one (REPEAT_RULE, default longest)
    by_contact = {}
    for k in kept:
        by_contact.setdefault(k["contact_id"], []).append(k)
    final = []
    for group in by_contact.values():
        if SETTINGS["REPEAT_RULE"] == "longest":
            best = max(group, key=lambda x: x["duration_ms"])
        else:
            best = min(group, key=lambda x: x["ts_ms"])
        final.append(best)
        for g in group:
            if g is not best:
                dropped.append({**{k: g[k] for k in ("hs_id", "ts_ms", "duration_ms", "title", "to_number")},
                                "reason": f"repeat call to {g['customer']} (kept call {best['hs_id']}, rule {SETTINGS['REPEAT_RULE']})"})
    final.sort(key=lambda x: x["ts_ms"])
    dropped.sort(key=lambda x: x["ts_ms"])
    return final, dropped
