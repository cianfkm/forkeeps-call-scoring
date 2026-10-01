import os
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import yaml

TZ = ZoneInfo("Australia/Melbourne")  # never hardcode UTC+10: AEDT starts 4 Oct 2026
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(name):
    with open(os.path.join(ROOT, "config", name), encoding="utf-8") as f:
        return yaml.safe_load(f)


SETTINGS = _load("settings.yaml")
STEPS = _load("playbook.yaml")["steps"]
REPS = _load("reps.yaml")["reps"]
MUST_ASK = [s["n"] for s in STEPS if s["must_ask"]]
assert [s["n"] for s in STEPS] == list(range(1, 10)), "playbook.yaml must define steps 1 to 9 in order"
assert MUST_ASK == [5, 6, 7, 8], "Must-Ask steps are 5 to 8 (v6 section 5)"


def week_window(week_ending=None, now=None):
    """Mon 00:00 to Sat 00:00 Melbourne for the Mon to Fri week ending on `week_ending` (a Friday).
    Default: the most recent completed week. Returns (friday, start_utc, end_utc)."""
    if week_ending:
        friday = date.fromisoformat(week_ending) if isinstance(week_ending, str) else week_ending
        if friday.weekday() != 4:
            raise ValueError(f"week_ending must be a Friday, got {friday:%a %d %b %Y}")
    else:
        today = (now or datetime.now(TZ)).astimezone(TZ).date()
        # Most recent Friday whose week (ending Sat 00:00) has finished
        w = today.weekday()
        friday = today - timedelta(days=w - 4 if w >= 5 else w + 3)
    monday = friday - timedelta(days=4)
    start = datetime(monday.year, monday.month, monday.day, tzinfo=TZ)
    end = datetime(friday.year, friday.month, friday.day, tzinfo=TZ) + timedelta(days=1)
    return friday, start, end


def find_rep(name):
    n = name.strip().lower()
    for r in REPS:
        if n in (r["name"].lower(), r["full"].lower()):
            return r
    raise SystemExit(f"Unknown rep '{name}'. Valid: {', '.join(r['name'] for r in REPS)}")
