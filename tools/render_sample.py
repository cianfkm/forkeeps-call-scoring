"""Offline layout check: renders a sample scorecard from fixed data (no HubSpot, Dialpad or Claude).
python -m tools.render_sample  ->  out/sample.pdf"""
import os
from datetime import datetime

from callscoring import render, scoring
from callscoring.config import STEPS, TZ, week_window

friday, start, _ = week_window("2026-08-28")


def call(customer, company, day, mins, ratings, panel_type="biggest_miss"):
    ts = int(datetime(2026, 8, day, 10, 0, tzinfo=TZ).timestamp() * 1000)
    score = {"context": "Bottle holders and pens. Client gift box. Queensland delivery.",
             "steps": [{"step": i + 1, "rating": r, "evidence": "",
                        "what_happened": "Customer volunteered that the items were for a client gift box. "
                                         "The question was not asked, so the occasion and audience were never explored."}
                       for i, r in enumerate(ratings)],
             "panel": {"type": panel_type, "text": "the customer said she had put in a second enquiry after spotting other items."}}
    c = {"customer": customer, "company": company, "ts_ms": ts, "duration_ms": int(mins * 60000),
         "listen_url": "https://dialpad.com/callhistory/callreview/123?tab=transcript", "score": score}
    c["totals"] = scoring.call_totals(score)
    return c


scored = [call("Michelle Brown", "MHI Roofing", 24, 2.72, "MPPPPMMPY"),
          call("Jess Collins", "Australi", 24, 5.73, "MPPYPPMPY"),
          call("Carolyn", "Ready Steady Go Kids", 28, 5.48, "MMMMPPPMP", "context")]
week = scoring.week_totals(scored)
summary = {"headline": "The information arrived on every call, but the customer supplied it.",
           "step_patterns": [f"Pattern note for step {s['n']}." for s in STEPS],
           "strengths": ["Next steps, 2.5/3. Quote commitment plus timeframe on 2 of 3 calls."] * 3,
           "gaps": ["Budget never asked. A figure surfaced on all 3 calls."] * 3,
           "priority_actions": [{"step": 1, "title": "Use the opening line", "evidence": ["Calls open with the reason for calling."], "target": "3/3"},
                                {"step": 5, "title": "Ask for budget first", "evidence": ['Michelle: "if you do have a figure at any point I\'m happy to help".'], "target": "2/3"},
                                {"step": 7, "title": "Establish who signs off", "evidence": ["Carolyn: checking with Danny. Not explored."], "target": "2/3"}],
           "also_monitor": "Step 6, competing quotes, 1.0/3.",
           "follow_ups": [{"deal": "Jess Collins / Australi", "why": "Another quote in play.", "action": "Call back this week."}]}
rep = {"full": "Sample Rep", "start_date": "2026-08-10"}
html_text = render.build_html(rep, friday, 64, 3, ["Kylie Geoghegan"], scored, week, summary)
os.makedirs("out", exist_ok=True)
render.to_pdf(html_text, "out/sample.pdf")
print("wrote out/sample.pdf", week["grand"], "/", week["grand_max"], week["pct"], "%")
