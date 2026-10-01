"""Dialpad transcripts via the API. Never scrape the Dialpad UI."""
import os
import time

import requests

KEY = os.environ.get("DIALPAD_API_KEY", "")


def transcript(call_id):
    """Speaker-labelled transcript text, or None if Dialpad has none for this call.
    GET /api/v2/transcripts/{call_id} -> {"call_id", "lines": [{content, name, time, type, user_id, contact_id}]}"""
    for attempt in range(4):
        r = requests.get(f"https://dialpad.com/api/v2/transcripts/{call_id}",
                         headers={"Authorization": f"Bearer {KEY}"}, timeout=60)
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(2 ** attempt)
            continue
        if r.status_code in (401, 403):
            raise RuntimeError(f"Dialpad {r.status_code}: API key invalid or missing the recordings_export scope. {r.text[:300]}")
        if r.status_code == 404:
            return None
        r.raise_for_status()
        lines = [ln for ln in r.json().get("lines") or [] if ln.get("type", "transcript") == "transcript" and ln.get("content")]
        if not lines:
            return None
        out = []
        for ln in lines:
            # user_id = a Dialpad user (the rep); contact_id = the customer
            who = "REP" if ln.get("user_id") else "CUSTOMER"
            out.append(f"{who} ({ln.get('name') or 'unknown'}): {ln['content'].strip()}")
        return "\n".join(out)
    raise RuntimeError(f"Dialpad transcript {call_id} kept failing (rate limit or server error)")
