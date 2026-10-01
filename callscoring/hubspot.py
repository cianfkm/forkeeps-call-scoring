"""HubSpot: owners check, call search (paginated), associated contacts and deals."""
import os
import time
from datetime import datetime

import requests

HS = "https://api.hubapi.com"
TOKEN = os.environ.get("HUBSPOT_TOKEN", "")
CALL_PROPS = ["hs_call_title", "hs_call_body", "hs_call_duration", "hs_timestamp",
              "hs_call_to_number", "hs_call_direction"]
CONTACT_PROPS = ["firstname", "lastname", "company", "createdate", "lifecyclestage",
                 "num_associated_deals", "hs_analytics_source"]


def hs(method, path, **kw):
    for attempt in range(5):
        r = requests.request(method, HS + path, headers={"Authorization": f"Bearer {TOKEN}"}, timeout=60, **kw)
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(2 ** attempt)
            continue
        if r.status_code == 403:
            # HubSpot names the missing scope in the body; surface it verbatim
            raise RuntimeError(f"HubSpot 403 on {path}: token is missing a scope. {r.text[:500]}")
        r.raise_for_status()
        return r.json()
    raise RuntimeError(f"HubSpot {path} kept failing (rate limit or server error)")


def check_owner(rep):
    r = requests.get(f"{HS}/crm/v3/owners/{rep['owner_id']}", headers={"Authorization": f"Bearer {TOKEN}"}, timeout=60)
    if r.status_code != 200:
        raise RuntimeError(f"{rep['full']}: owner ID {rep['owner_id']} not found in HubSpot ({r.status_code}). Left or deactivated?")
    o = r.json()
    name = f"{o.get('firstName', '')} {o.get('lastName', '')}".strip()
    if name.lower() != rep["full"].lower():
        raise RuntimeError(f"{rep['full']}: owner ID {rep['owner_id']} belongs to '{name}' in HubSpot")


def _ms(dt):
    return str(int(dt.timestamp() * 1000))


def search_calls(owner_id, start, end, min_ms=None):
    """All calls for the owner in [start, end). Paginates until done and checks the total."""
    filters = [{"propertyName": "hubspot_owner_id", "operator": "EQ", "value": owner_id},
               {"propertyName": "hs_timestamp", "operator": "BETWEEN", "value": _ms(start), "highValue": _ms(end)}]
    if min_ms is not None:
        filters.append({"propertyName": "hs_call_duration", "operator": "GT", "value": str(min_ms)})
    out, after, total = [], None, 0
    while True:
        body = {"filterGroups": [{"filters": filters}], "properties": CALL_PROPS, "limit": 100,
                "sorts": [{"propertyName": "hs_timestamp", "direction": "ASCENDING"}]}
        if after:
            body["after"] = after
        data = hs("POST", "/crm/v3/objects/calls/search", json=body)
        out += data["results"]
        total = data.get("total", len(out))
        after = data.get("paging", {}).get("next", {}).get("after")
        if not after:
            break
        time.sleep(0.25)  # search API is rate limited per portal
    if len(out) != total:
        raise RuntimeError(f"Truncated call pull for owner {owner_id}: got {len(out)} of {total}")
    # BETWEEN is inclusive of the high value; drop anything stamped exactly at Sat 00:00
    end_ms = int(_ms(end))
    return [c for c in out if int(parse_ms(c["properties"].get("hs_timestamp"))) < end_ms]


def count_calls(owner_id, start, end):
    return len(search_calls(owner_id, start, end))


def parse_ms(v):
    """HubSpot datetime (epoch ms string or ISO) -> epoch ms."""
    if v is None:
        return 0
    s = str(v)
    if s.isdigit():
        return int(s)
    return int(datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp() * 1000)



def associations(from_type, to_type, ids):
    """{from_id: [to_id, ...]} via the v4 batch associations API."""
    out = {}
    ids = list(dict.fromkeys(str(i) for i in ids))
    for i in range(0, len(ids), 100):
        data = hs("POST", f"/crm/v4/associations/{from_type}/{to_type}/batch/read",
                  json={"inputs": [{"id": x} for x in ids[i:i + 100]]})
        for row in data.get("results", []):
            out[str(row["from"]["id"])] = [str(t["toObjectId"]) for t in row.get("to", [])]
    return out


def batch_read(obj, ids, props):
    out = {}
    ids = list(dict.fromkeys(str(i) for i in ids))
    for i in range(0, len(ids), 100):
        data = hs("POST", f"/crm/v3/objects/{obj}/batch/read",
                  json={"inputs": [{"id": x} for x in ids[i:i + 100]], "properties": props})
        for row in data.get("results", []):
            out[str(row["id"])] = row["properties"]
    return out
