"""Re-render a scorecard PDF from a run's saved JSON (no HubSpot, Dialpad or Claude calls).
Use after template changes: python -m tools.rerender "<run>.json" [out.pdf]"""
import json
import sys
from datetime import date

from callscoring import render
from callscoring.config import find_rep

d = json.load(open(sys.argv[1], encoding="utf-8"))
# JSON turns integer dict keys into strings; restore them
d["week"]["step_tot"] = {int(k): v for k, v in d["week"]["step_tot"].items()}
for c in d["calls"]:
    c["totals"]["points"] = {int(k): v for k, v in c["totals"]["points"].items()}
rep = find_rep(d["rep"])
friday = date.fromisoformat(d["week_ending"])
html_text = render.build_html(rep, friday, d["calls_made"], len(d["calls"]) + len(d["not_scored"]),
                              d["not_scored"], d["calls"], d["week"], d["summary"])
out = sys.argv[2] if len(sys.argv) > 2 else sys.argv[1].rsplit(".", 1)[0] + ".rerender.pdf"
render.to_pdf(html_text, out)
print("wrote", out)
