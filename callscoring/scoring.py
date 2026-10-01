"""Claude scoring: one request per call (4.5), one summary request per rep (4.6).
Claude returns ratings and words only. ALL maths happens in code."""
import json
import re

import anthropic

from .config import MUST_ASK, SETTINGS, STEPS

MODEL = SETTINGS["MODEL"]
POINTS = {"Y": 1.0, "P": 0.5, "M": 0.0}
_client = None


def client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic(max_retries=4)
    return _client


REGISTER = """Register and conventions (these are hard rules):
- The report is system output, not a person. No voice, no name, no relationship with the rep.
- No second person anywhere. Never write "you" or "your" in your own words. Never address the rep by name. Refer to the rep only as "rep". Refer to customers by name.
- No praise, no reassurance, no encouragement, no verdicts on character or effort. Strengths are observations with evidence; gaps are observations with evidence.
- Tone test: the sentence must read as neutral system output a rep could read without a manager present, landing as neither a telling-off nor a pep talk.
- Australian English. Ex GST. Never use em dashes or en dashes; use a comma, a full stop, or "to".
- Percentages as whole numbers, scores to one decimal."""

THREE_TIER = """Three-tier rule, applied to what the REP did (equal weighting, ignore any point values in training material):
- Y (Yes) = the rep asked and got a usable answer.
- P (Partial) = the customer volunteered it without being asked; or the rep raised it but accepted a non-answer; or the apparent credit is a false positive (for example the rep mentioning our own supplier is NOT a competing-quotes conversation).
- M (Missed) = no evidence in the call.
Score the rep's actual questions, not whether the subject came up. A subject the customer raised is at most P."""


def _rubric():
    rows = []
    for s in STEPS:
        star = " (Must-Ask)" if s["must_ask"] else ""
        rows.append(f"{s['n']}. {s['name']}{star}. Requirement: {s['definition']} Playbook prompt: {s['script']}")
    return "\n".join(rows)


CALL_SYSTEM = f"""You score one recorded sales call for For Keeps Merch, an Australian custom merchandise supplier, against its nine-step "For Keeps Sales Call" playbook. The output feeds a weekly scorecard that the sales manager reviews before coaching.

The nine steps:
{_rubric()}

{THREE_TIER}

For each of the nine steps return:
- rating: Y, P or M.
- evidence: a short verbatim quote from the transcript that supports the rating (rep or customer words, exactly as transcribed), or an empty string when there is genuinely nothing to quote.
- what_happened: one to three sentences. Structure: what happened, then what was left unestablished, then why it matters commercially. Quote the customer or rep verbatim where it makes the point. "Not asked." alone is acceptable only where there is genuinely nothing more to say.

Also return:
- context: one line describing the enquiry (products, quantity, occasion, timing), written as short fragments. Example: "Bottle holders and pens. Client gift box. Queensland delivery."
- panel: one closing panel for the call.
  - type "biggest_miss" by default: the single most commercially costly gap, with the customer signal that was missed.
  - type "best_moment" only where the call was exceptional on some step.
  - type "context" only where circumstances explain a low score (a price match on an existing arrangement, an inbound callback, a non-discovery call). The text may then also name the biggest miss after the context.

Calibration examples from a verified reference report (style and strictness to match):
- Opening line, M: "No permission bridge. The call opened with the reason for ringing and moved directly into confirming quantities and the due date."
- Merch purpose, P: "Customer volunteered that the items were for a client gift box. The question was not asked, so the occasion, the audience and the spend per box were never explored."
- Budget, P: "Offered rather than asked: \\"if you do have a figure at any point you are looking to work towards, I'm happy to help with that as well.\\" The customer did not respond with a number and it was not revisited."
- Competing quotes, M: "Not asked. Dialpad credited this step because the rep mentioned our own supplier making a mockup, which is a false positive."
- Deadline, Y: "Customer gave 12 September. Rep worked backwards against the ten business day lead time and proposed a 9 September due date. Handled properly."
- Biggest miss panel: "the customer said she had put in a second enquiry after spotting other items. That is a direct signal of more to quote, and it was not picked up. Shortest call of the week at 2:43, which is consistent with the discovery not happening."

Transcript lines are labelled REP or CUSTOMER by the phone system; labels can occasionally be wrong, so use the content to judge who is speaking when it matters.

{REGISTER}"""

CALL_SCHEMA = {
    "type": "object",
    "properties": {
        "context": {"type": "string"},
        "steps": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "step": {"type": "integer"},
                "rating": {"type": "string", "enum": ["Y", "P", "M"]},
                "evidence": {"type": "string"},
                "what_happened": {"type": "string"},
            },
            "required": ["step", "rating", "evidence", "what_happened"],
            "additionalProperties": False,
        }},
        "panel": {"type": "object", "properties": {
            "type": {"type": "string", "enum": ["biggest_miss", "best_moment", "context"]},
            "text": {"type": "string"},
        }, "required": ["type", "text"], "additionalProperties": False},
    },
    "required": ["context", "steps", "panel"],
    "additionalProperties": False,
}


def _ask(system, user, schema, effort="high"):
    resp = client().beta.messages.create(
        model=MODEL,
        max_tokens=16000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",  # a safety-classifier decline re-runs on Anthropic's recommended fallback model
        cache_control={"type": "ephemeral"},
        system=system,
        messages=[{"role": "user", "content": user}],
        output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
    )
    if resp.stop_reason == "refusal":
        raise RuntimeError(f"Claude declined the request ({getattr(resp.stop_details, 'category', None)})")
    if resp.stop_reason == "max_tokens":
        raise ValueError("response hit max_tokens")
    text = next(b.text for b in resp.content if b.type == "text")
    return json.loads(text)


def _validate_call(d):
    steps = d.get("steps") or []
    if sorted(s.get("step") for s in steps) != list(range(1, 10)):
        raise ValueError(f"expected exactly steps 1 to 9, got {[s.get('step') for s in steps]}")
    if any(s.get("rating") not in POINTS for s in steps):
        raise ValueError("ratings must be Y, P or M")
    d["steps"] = sorted(steps, key=lambda s: s["step"])
    return d


def score_call(call, transcript_text):
    """One Claude request per call. Retry once on invalid output, then fail loudly."""
    user = (f"Call metadata: {call['day_long']}, customer {call['customer']}"
            f"{', ' + call['company'] if call['company'] else ''}, length {call['length']}.\n\n"
            f"Transcript:\n{transcript_text}")
    last = None
    for attempt in range(2):
        try:
            d = _validate_call(_ask(CALL_SYSTEM, user, CALL_SCHEMA))
            for s in d["steps"]:
                s["what_happened"] = clean(s["what_happened"])
                s["evidence"] = clean(s["evidence"])
            d["context"] = clean(d["context"])
            d["panel"]["text"] = clean(d["panel"]["text"])
            return d
        except (ValueError, json.JSONDecodeError, StopIteration) as e:
            last = e
            print(f"  ! invalid scoring output for {call['customer']} (attempt {attempt + 1}): {e}")
    raise RuntimeError(f"Scoring failed twice for call {call['hs_id']} ({call['customer']}): {last}")


# ---------- maths (code only) ----------
def call_totals(d):
    pts = {s["step"]: POINTS[s["rating"]] for s in d["steps"]}
    overall = sum(pts.values())
    must = sum(pts[n] for n in MUST_ASK)
    return {"points": pts, "overall": overall, "pct": round(100 * overall / 9), "must": must}


def week_totals(scored):
    n = len(scored)
    step_tot = {s["n"]: sum(c["totals"]["points"][s["n"]] for c in scored) for s in STEPS}
    call_sum = sum(c["totals"]["overall"] for c in scored)
    grand = sum(step_tot.values())
    assert abs(call_sum - grand) < 1e-9, f"step totals {grand} != call totals {call_sum}"
    return {
        "n": n, "step_tot": step_tot, "grand": grand, "grand_max": 9 * n,
        "overall_avg": call_sum / n, "pct": round(100 * grand / (9 * n)),
        "must_avg": sum(c["totals"]["must"] for c in scored) / n,
    }


# ---------- summary (4.6) ----------
SUMMARY_SYSTEM = f"""You write the summary layer of a weekly sales call scorecard for one rep at For Keeps Merch, from per-call scores that have already been made. You never re-score calls. Every number you mention must come from the data provided.

The nine steps:
{_rubric()}

{THREE_TIER}

Word budget for everything you write here is TIGHT: table cells 10 words maximum; bullets one line each; do not restate a number already shown in a table. Scannable in two minutes.

Return:
- headline: one or two sentences naming the week's dominant pattern.
- step_patterns: exactly nine short pattern notes (one per step, in step order, 10 words max each). Example: "Raised on all 9 calls. Asked on none."
- strengths: 3 to 4 bullets, each an observation with a named example (customer name, quote or number). Format "Label. Observation." Example: "Next steps, 8.5/9. Quote commitment plus timeframe on 8 of 9 calls. Craig: \\"over to you in the next hour\\"."
- gaps: 3 to 4 bullets, each containing a number. Example: "Decision maker unknown on all 9. Two customers signalled internal approval. Neither followed up."
- priority_actions: exactly three, choosing steps by these rules: rank the three weakest steps by score, then adjust for leverage. The opening line (step 1) comes first where it is weak, because it unblocks the questions after it. Prefer a step where the evidence shows repeated missed customer signals. Each has: step (number), title (short imperative, e.g. "Ask for budget first"), evidence (2 to 5 short bullets with customer names and verbatim quotes, the last bullet may state the commercial result), target (numeric target for next week, e.g. "6/9" or "8/9, full marks"). Do NOT write the script; the system inserts the verbatim playbook wording.
- also_monitor: one line for the fourth weakest step: step name, score, the evidence, and the position to use.
- follow_ups: deals needing action this week (only where the calls show an open, recoverable gap on a live opportunity). Each: deal (customer and company), why (10 words max where possible), action.

{REGISTER}
Quoted customer or rep words inside quotation marks may contain "you"; your own words may not."""

SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {"type": "string"},
        "step_patterns": {"type": "array", "items": {"type": "string"}},
        "strengths": {"type": "array", "items": {"type": "string"}},
        "gaps": {"type": "array", "items": {"type": "string"}},
        "priority_actions": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "step": {"type": "integer"},
                "title": {"type": "string"},
                "evidence": {"type": "array", "items": {"type": "string"}},
                "target": {"type": "string"},
            },
            "required": ["step", "title", "evidence", "target"],
            "additionalProperties": False,
        }},
        "also_monitor": {"type": "string"},
        "follow_ups": {"type": "array", "items": {
            "type": "object",
            "properties": {"deal": {"type": "string"}, "why": {"type": "string"}, "action": {"type": "string"}},
            "required": ["deal", "why", "action"], "additionalProperties": False,
        }},
    },
    "required": ["headline", "step_patterns", "strengths", "gaps", "priority_actions", "also_monitor", "follow_ups"],
    "additionalProperties": False,
}


def _summary_text_fields(s):
    yield s["headline"]
    yield s["also_monitor"]
    yield from s["step_patterns"]
    yield from s["strengths"]
    yield from s["gaps"]
    for a in s["priority_actions"]:
        yield a["title"]
        yield a["target"]
        yield from a["evidence"]
    for f in s["follow_ups"]:
        yield from (f["deal"], f["why"], f["action"])


def _validate_summary(s):
    if len(s["step_patterns"]) != 9:
        raise ValueError(f"expected 9 step patterns, got {len(s['step_patterns'])}")
    if len(s["priority_actions"]) != 3:
        raise ValueError(f"expected 3 priority actions, got {len(s['priority_actions'])}")
    if any(a["step"] not in range(1, 10) for a in s["priority_actions"]):
        raise ValueError("priority action step out of range")
    for field in _summary_text_fields(s):
        if has_second_person(field):
            raise ValueError(f'second person in summary text: "{field[:120]}"')
    return s


def summarise(rep_week):
    """rep_week: scored data only (no transcripts)."""
    user = json.dumps(rep_week, ensure_ascii=False, indent=1)
    feedback, last = "", None
    for attempt in range(2):
        try:
            s = _ask(SUMMARY_SYSTEM, user + feedback, SUMMARY_SCHEMA)
            # Clean dashes first, then validate (a dash is fixable, "you" is not)
            s["headline"], s["also_monitor"] = clean(s["headline"]), clean(s["also_monitor"])
            for k in ("step_patterns", "strengths", "gaps"):
                s[k] = [clean(x) for x in s[k]]
            for a in s["priority_actions"]:
                a["title"], a["target"] = clean(a["title"]), clean(a["target"])
                a["evidence"] = [clean(x) for x in a["evidence"]]
            for f in s["follow_ups"]:
                for k in ("deal", "why", "action"):
                    f[k] = clean(f[k])
            return _validate_summary(s)
        except (ValueError, json.JSONDecodeError, StopIteration) as e:
            last = e
            print(f"  ! invalid summary output (attempt {attempt + 1}): {e}")
            feedback = f"\n\nYour previous answer was rejected: {e}. Fix that and answer again."
    raise RuntimeError(f"Summary failed twice: {last}")


# ---------- post-processing ----------
_QUOTED = re.compile(r'"[^"]*"|“[^”]*”')
_YOU = re.compile(r"\byou(r|rs|rself|'re|'ve|'ll|'d)?\b", re.I)


def has_second_person(text):
    """'you' outside quotation marks (verbatim customer/rep quotes are allowed to contain it)."""
    return bool(_YOU.search(_QUOTED.sub("", text or "")))


def clean(text):
    """No em or en dashes (v6 section 8): ranges become 'to', everything else a comma."""
    t = text or ""
    t = re.sub(r"(\d)\s*[–—]\s*(\d)", r"\1 to \2", t)
    t = re.sub(r"\s*[–—]\s*", ", ", t)
    return t.strip()
