"""HTML per v6 section 6, then PDF via Playwright (Chromium)."""
import os
from datetime import date, datetime, timedelta

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .config import SETTINGS, STEPS, TZ

_env = Environment(loader=FileSystemLoader(os.path.join(os.path.dirname(__file__), "templates")),
                   autoescape=select_autoescape(["html"]))


def band(fraction):
    """v6 colour bands: green 67%+, amber 40 to 66%, red under 40% (on the whole-number percentage)."""
    p = round(100 * fraction)
    return "green" if p >= 67 else "amber" if p >= 40 else "red"


def mmss(ms):
    s = round(ms / 1000)
    return f"{s // 60}:{s % 60:02d}"


def d_short(dt):   # "Mon 24"
    return f"{dt:%a} {dt.day}"


def d_med(dt):     # "Mon 24 Aug"
    return f"{dt:%a} {dt.day} {dt:%b}"


def d_long(d):     # "Fri 28 Aug 2026"
    return f"{d:%a} {d.day} {d:%b %Y}"


def d_title(d):    # "28 Aug 2026"
    return f"{d.day} {d:%b %Y}"


def title_for(rep_full, friday):
    return f"Call Scorecard: {rep_full}, w/e {d_title(friday)}"


def baseline_text(rep, friday):
    sd = rep.get("start_date")
    if not sd:
        return None
    start = sd if isinstance(sd, date) else date.fromisoformat(str(sd))
    weeks_in = (friday - start).days // 7 + 1
    if weeks_in > SETTINGS["BASELINE_WEEKS"]:
        return None
    first_comparable = start + timedelta(days=(4 - start.weekday()) % 7) + timedelta(weeks=SETTINGS["BASELINE_WEEKS"])
    return (f"Rep started {d_title(start)} and is in week {max(weeks_in, 1)}. "
            f"First comparable week is w/e {d_title(first_comparable)}.")


def build_html(rep, friday, calls_made, in_scope, not_scored, scored, week, summary):
    steps_by_n = {s["n"]: s for s in STEPS}
    n = len(scored)
    ctx = {
        "title": title_for(rep["full"], friday), "rep": rep["full"], "week_long": d_long(friday),
        "generated": d_title(datetime.now(TZ).date()), "calls_made": calls_made, "n_in_scope": in_scope,
        "n_scored": n, "not_scored": not_scored, "baseline": baseline_text(rep, friday),
    }
    if n:
        lens = [c["duration_ms"] for c in scored]
        tot = week["step_tot"]
        best = max(STEPS, key=lambda s: tot[s["n"]])
        weak = min(STEPS, key=lambda s: tot[s["n"]])
        ctx["snap"] = {
            "overall": f"{week['overall_avg']:.1f}", "overall_pct": week["pct"], "overall_band": band(week["grand"] / week["grand_max"]),
            "must": f"{week['must_avg']:.1f}", "must_band": band(week["must_avg"] / 4),
            "best_score": f"{tot[best['n']]:.1f}", "best_name": best["short"], "best_band": band(tot[best["n"]] / n),
            "weak_score": f"{tot[weak['n']]:.1f}", "weak_name": weak["short"], "weak_band": band(tot[weak["n"]] / n),
            "avg_len": mmss(sum(lens) / n), "len_range": f"{mmss(min(lens))} to {mmss(max(lens))}",
        }
        ctx["grand"], ctx["grand_max"] = f"{week['grand']:.1f}", week["grand_max"]
        ctx["steps"] = [{"n": s["n"], "name": s["name"], "must_ask": s["must_ask"], "score": f"{tot[s['n']]:.1f}",
                         "band": band(tot[s["n"]] / n), "pattern": summary["step_patterns"][s["n"] - 1]} for s in STEPS]
        ctx["calls"] = []
        for c in scored:
            dt = datetime.fromtimestamp(c["ts_ms"] / 1000, TZ)
            t = c["totals"]
            ptype = c["score"]["panel"]["type"]
            ctx["calls"].append({
                "customer": c["customer"], "company": c["company"], "day_short": d_short(dt), "day_med": d_med(dt),
                "length": mmss(c["duration_ms"]), "overall": f"{t['overall']:.1f}", "pct": t["pct"],
                "band": band(t["overall"] / 9), "must": f"{t['must']:.1f}", "must_band": band(t["must"] / 4),
                "listen_url": c["listen_url"], "context": c["score"]["context"],
                "ratings": [s["rating"] for s in c["score"]["steps"]],
                "steps": [{**steps_by_n[s["step"]], "rating": s["rating"], "what_happened": s["what_happened"]}
                          for s in c["score"]["steps"]],
                "panel_label": {"biggest_miss": "Biggest miss", "best_moment": "Best moment", "context": "Context"}[ptype],
                "panel_class": {"best_moment": "green", "context": ""}.get(ptype, "red" if t["pct"] < 40 else "amber"),
                "panel_text": c["score"]["panel"]["text"],
            })
        ctx["summary"] = summary
        # Script column is the verbatim playbook wording, inserted by code, never written by Claude
        ctx["actions"] = [{**a, "script": steps_by_n[a["step"]]["script"], "score": f"{tot[a['step']]:.1f}",
                           "band": band(tot[a["step"]] / n)} for a in summary["priority_actions"]]
    return _env.get_template("scorecard.html").render(**ctx)


def to_pdf(html_text, path):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.set_content(html_text, wait_until="load")
        page.pdf(path=path, format="A4", print_background=True,
                 margin={"top": "14mm", "bottom": "14mm", "left": "14mm", "right": "14mm"})
        browser.close()
