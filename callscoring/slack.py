"""Slack delivery: one parent message per run, PDFs as thread replies, previous copies deleted (v6 section 7)."""
import json
import os
import time

import requests

TOKEN = os.environ.get("SLACK_BOT_TOKEN", "")
CHANNEL = os.environ.get("SLACK_CHANNEL_ID", "")


def api(method, **data):
    r = requests.post(f"https://slack.com/api/{method}", headers={"Authorization": f"Bearer {TOKEN}"},
                      data=data, timeout=60).json()
    if not r.get("ok"):
        raise RuntimeError(f"Slack {method} failed: {r.get('error')} {r.get('needed', '')}".strip())
    return r


def post(text, thread_ts=None):
    return api("chat.postMessage", channel=CHANNEL, text=text, **({"thread_ts": thread_ts} if thread_ts else {}))["ts"]


def delete_previous(title):
    """Delete any file this bot already posted in the channel with the same title. Never leave two scorecards."""
    me = api("auth.test")["user_id"]
    page, removed = 1, 0
    while True:
        r = api("files.list", channel=CHANNEL, user=me, count=200, page=page,
                ts_from=str(int(time.time()) - 120 * 86400))
        for f in r.get("files", []):
            if f.get("title") == title:
                api("files.delete", file=f["id"])
                removed += 1
        if page >= r.get("paging", {}).get("pages", 1):
            return removed
        page += 1


def upload(path, title, thread_ts):
    name = os.path.basename(path)
    r = api("files.getUploadURLExternal", filename=name, length=os.path.getsize(path))
    with open(path, "rb") as f:
        requests.post(r["upload_url"], data=f.read(), timeout=120).raise_for_status()
    api("files.completeUploadExternal", files=json.dumps([{"id": r["file_id"], "title": title}]),
        channel_id=CHANNEL, thread_ts=thread_ts)
