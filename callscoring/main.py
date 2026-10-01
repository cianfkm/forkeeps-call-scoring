"""Weekly call scorecards: HubSpot -> qualify -> Dialpad transcripts -> Claude -> PDF -> Slack.

python -m callscoring.main [--rep all|Leanne] [--week-ending 2026-08-28] [--no-post] [--out out]
"""
import argparse
import json
import os
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from . import dialpad, hubspot, render, scoring, slack
from .qualify import qualify
from .config import REPS, SETTINGS, STEPS, TZ, find_rep, week_window


def log_drop(d):
    dt = datetime.fromtimestamp(d["ts_ms"] / 1000, TZ)
    print(f"    DROP {dt:%a %d %b %H:%M} {render.mmss(d['duration_ms']):>6}  call {d['hs_id']}  "
          f"{d['title'][:40]!r}  -> {d['reason']}")


def run_rep(rep, friday, start, end, out):
    print(f"\n=== {rep['full']} ({rep['owner_id']}) w/e {friday} ===")
    hubspot.check_owner(rep)
    calls_made = hubspot.count_calls(rep["owner_id"], start, end)
    long_calls = hubspot.search_calls(rep["owner_id"], start, end, min_ms=SETTINGS["MIN_CALL_MS"])
    kept, dropped = qualify(long_calls, int(start.timestamp() * 1000))
    print(f"  {calls_made} calls made, {len(long_calls)} over 2 min, {len(kept)} in scope, {len(dropped)} dropped")
    for d in dropped:
        log_drop(d)
    for k in kept:
        print(f"    KEEP {k['customer']} (call {k['hs_id']})" + (f"  note: {k['note']}" if k.get("note") else ""))

    # Transcripts: a call without one stays in "calls made", is excluded from scoring and listed
    not_scored, to_score = [], []
    for c in kept:
        dt = datetime.fromtimestamp(c["ts_ms"] / 1000, TZ)
        c.update(day_long=f"{dt:%A} {dt.day} {dt:%B}", length=render.mmss(c["duration_ms"]))
        text = dialpad.transcript(c["dialpad_id"]) if c["dialpad_id"] else None
        if not text:
            why = "no Dialpad link in HubSpot" if not c["dialpad_id"] else "no transcript"
            print(f"    NOT SCORED {c['customer']} (call {c['hs_id']}): {why}")
            not_scored.append(c["customer"])
            continue
        to_score.append((c, text))

    def _score(pair):
        c, text = pair
        c["score"] = scoring.score_call(c, text)
        c["totals"] = scoring.call_totals(c["score"])
        print(f"    scored {c['customer']}: {c['totals']['overall']:.1f}/9 ({c['totals']['pct']}%), "
              f"Must-Ask {c['totals']['must']:.1f} [{''.join(s['rating'] for s in c['score']['steps'])}]")
        return c

    with ThreadPoolExecutor(max_workers=5) as pool:
        scored = sorted(pool.map(_score, to_score), key=lambda c: c["ts_ms"])

    week, summary = None, None
    if scored:
        week = scoring.week_totals(scored)
        rep_week = {
            "calls_scored": week["n"], "calls_made": calls_made,
            "week_overall": f"{week['overall_avg']:.1f}/9 ({week['pct']}%)", "week_must_ask": f"{week['must_avg']:.1f}/4",
            "step_totals": {f"{s['n']}. {s['name']}": f"{week['step_tot'][s['n']]:.1f}/{week['n']}" for s in STEPS},
            "calls": [{"customer": c["customer"], "company": c["company"], "day": c["day_long"], "length": c["length"],
                       "deals": c["deals"], "overall": f"{c['totals']['overall']:.1f}/9 ({c['totals']['pct']}%)",
                       "must_ask": f"{c['totals']['must']:.1f}/4", "context": c["score"]["context"],
                       "steps": [{"step": s["step"], "rating": s["rating"], "evidence": s["evidence"],
                                  "what_happened": s["what_happened"]} for s in c["score"]["steps"]],
                       "panel": c["score"]["panel"]} for c in scored],
        }
        summary = scoring.summarise(rep_week)

    html_text = render.build_html(rep, friday, calls_made, len(kept), not_scored, scored, week, summary)
    title = render.title_for(rep["full"], friday)
    base = os.path.join(out, title.replace(":", "").replace("/", "-"))
    with open(base + ".html", "w", encoding="utf-8") as f:
        f.write(html_text)
    with open(base + ".json", "w", encoding="utf-8") as f:
        json.dump({"rep": rep["full"], "week_ending": str(friday), "calls_made": calls_made,
                   "dropped": dropped, "not_scored": not_scored, "summary": summary,
                   "week": week, "calls": [{k: v for k, v in c.items() if k != "body"} for c in scored]},
                  f, indent=1, default=str, ensure_ascii=False)
    render.to_pdf(html_text, base + ".pdf")
    print(f"  wrote {base}.pdf")
    return {"rep": rep, "title": title, "pdf": base + ".pdf", "n": len(scored),
            "pct": week["pct"] if week else None}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rep", default="all")
    ap.add_argument("--week-ending", default="")
    ap.add_argument("--no-post", action="store_true", help="write PDFs to --out only (Action artifacts)")
    ap.add_argument("--out", default="out")
    a = ap.parse_args()

    friday, start, end = week_window(a.week_ending or None)
    reps = REPS if a.rep.strip().lower() in ("", "all") else [find_rep(x) for x in a.rep.split(",")]
    os.makedirs(a.out, exist_ok=True)
    print(f"Week ending {friday:%a %d %b %Y}: {start.isoformat()} to {end.isoformat()} "
          f"(Melbourne UTC{start.strftime("%z")}) -> {len(reps)} rep(s), model {SETTINGS['MODEL']}")

    results, failures = [], []
    for rep in reps:
        try:
            results.append(run_rep(rep, friday, start, end, a.out))
        except Exception as e:
            traceback.print_exc()
            failures.append(f"{rep['full']}: {e}")

    total = sum(r["n"] for r in results)
    head = f"Call scorecards, w/e {render.d_title(friday)}: {len(results)} reps, {total} calls scored"
    lines = [head] + [f"• {r['rep']['name']}: {r['n']} scored" + (f", {r['pct']}%" if r["pct"] is not None else "")
                      for r in results]
    if failures:
        lines += ["", ":warning: *Failed, not posted:*"] + [f"• {f[:300]}" for f in failures]
    message = "\n".join(lines)
    print("\n" + message)

    if not a.no_post:
        ts = slack.post(message)
        for r in results:
            n = slack.delete_previous(r["title"])
            if n:
                print(f"  deleted {n} previous copy of {r['title']}")
            slack.upload(r["pdf"], r["title"], ts)
    if failures:
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        err = traceback.format_exc()
        print(err)
        if slack.TOKEN and slack.CHANNEL and "--no-post" not in sys.argv:
            try:
                slack.post(f":x: Call scorecards failed:\n```{err[-2500:]}```")
            except Exception:
                pass
        sys.exit(1)
