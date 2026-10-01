# Build brief: Weekly Call Scoring Report (`/call-scoring`)

Hand this to Claude Code. It replaces Rory's Cowork task ("Call Scoring Report: Build Instructions v6"). Put this file and Rory's v6 spec in the repo as `docs/brief.md` and `docs/v6-spec.md`. The v6 spec remains the source of truth for report content, structure, tone and colours. This brief changes only how the data is gathered and delivered.

## 1. Goal

Every Monday morning, produce one PDF scorecard per rep for the previous Mon to Fri week and post them to Slack channel #pipeline-briefings (ID `C0C43USSFTK`). Niamh can also run it on demand with `/call-scoring`.

## 2. Architecture

| Part | Choice |
|---|---|
| Repo | New GitHub repo `forkeeps-call-scoring`, Python 3.12 |
| Engine | GitHub Actions workflow `score.yml` |
| Schedule | Cron `0 20 * * 0` (Sunday 20:00 UTC = Monday 7am AEDT, 6am AEST) |
| Manual run | `workflow_dispatch` with inputs `rep` (name or `all`) and `week_ending` (YYYY-MM-DD, optional) |
| Slash command | Vercel serverless function receives `/call-scoring`, triggers `workflow_dispatch` |
| Slack bot | Existing "Dialpad Daily Calls" app (same one used for pipeline briefings) |
| Scoring | Claude API, model `claude-sonnet-5-5` |
| PDF | Render HTML, convert with Playwright (Chromium) inside the Action |

## 3. Reps in scope

Score these seven. Do NOT score Niamh Hamilton.

| Rep | HubSpot owner ID |
|---|---|
| Aoife Cripps | 1217171174 |
| Leilani Goodall | 82237377 |
| Jamie Hunt | 87580621 |
| Leanne Cooper | 93213822 |
| Emma Naughton | look up via owners API |
| Zoe Dragoi | look up via owners API |
| Jack Colleran | look up via owners API |

Zoe and Jack are new starters: the v6 Baseline panel applies for their first 3 to 4 weeks. Store each rep's start date in config so the panel switches off automatically.

Keep the roster in `config/reps.yaml`. On each run, confirm each ID still resolves via the HubSpot owners API and fail loudly if not.

## 4. Pipeline

### 4.1 Week window
- Use `zoneinfo("Australia/Melbourne")`. Never hardcode UTC+10 (Melbourne moves to UTC+11 on 4 Oct 2026).
- Default week: the most recent completed Mon 00:00 to Sat 00:00 local, converted to UTC.
- `week_ending` input = the Friday of the target week.

### 4.2 Pull calls (HubSpot)
- `POST /crm/v3/objects/calls/search`
- Filters: `hubspot_owner_id EQ <id>`, `hs_timestamp BETWEEN <start> <end>`, `hs_call_duration GT 120000`
- Sort `hs_timestamp` ascending. **Paginate until done.** Do not cap at 50.
- Properties: `hs_call_title, hs_call_body, hs_call_duration, hs_timestamp, hs_call_to_number, hs_call_direction`
- Also run a count with no duration filter for the scope line ("calls made").

### 4.3 Qualify
Fetch associated contacts (`firstname, lastname, company, createdate, lifecyclestage, num_associated_deals, hs_analytics_source`) and their associated deals (include the Deal type (system) property).

Keep a call only if all are true:
1. Duration over 2 minutes (already filtered)
2. Contact `createdate` within `NEW_CONTACT_WINDOW_DAYS` before the call (default 14, in config)
3. `lifecyclestage` = opportunity
4. At least one associated deal, and at least one with Deal type (system) = `New business` (exact value)

Drop: no contact record, existing customers, and repeat calls to the same contact in the week. **For repeats, keep the longest call** (config flag `REPEAT_RULE`, default `longest`).

Log every dropped call with its reason to the Action log. This makes threshold tuning easy.

### 4.4 Transcripts (Dialpad API)
- Extract the call ID from `hs_call_body` with regex `dialpad\.com/callhistory/callreview/(\d+)`. Keep the full Call Summary Link as the ▶ Listen URL.
- The recording ID from Dialpad's coaching tab is NOT the call ID. Use only the ID in `hs_call_body`.
- Fetch the transcript via the Dialpad API (`GET https://dialpad.com/api/v2/transcripts/{call_id}`; verify the endpoint and response shape against current Dialpad docs). Bearer auth, key needs `recordings_export` scope.
- If no transcript is available, keep the call in the "calls made" count, exclude it from scoring, and list it in a short "Not scored: no transcript" line in the title block.
- Do NOT scrape the Dialpad UI. The AI Playbook Adherence % in `hs_call_body` may be logged for comparison but must never appear in the report.

### 4.5 Score (Claude, one request per call)
Send the transcript, the rubric (section 5) and the three-tier rule. Require JSON only:

```json
{
  "context": "one line",
  "steps": [
    {"step": 1, "rating": "Y|P|M", "evidence": "verbatim quote or empty", "what_happened": "1 to 3 sentences"}
  ],
  "panel": {"type": "biggest_miss|best_moment|context", "text": "..."}
}
```

- Validate: exactly 9 steps, ratings only Y/P/M. Retry once on invalid JSON, then fail that call loudly.
- Do ALL maths in code: Y=1.0, P=0.5, M=0.0. Overall /9 and %, Must-Ask /4 (steps 5 to 8).
- Assert step totals and call totals sum to the same number before rendering.

### 4.6 Summarise (Claude, one request per rep)
Send the scored data (not transcripts). Ask for: headline pattern, 3 to 4 strengths, 3 to 4 gaps, 3 priority actions plus "Also monitor", and flagged follow ups. Follow the v6 priority-action rules. The script column must quote the playbook wording in section 5 verbatim.

### 4.7 Render
Build HTML exactly per v6 section 6 (structure 1 to 12, colours, word budgets, register). Convert to PDF with Playwright. Title: `Call Scorecard: [Rep name], w/e [D Mon YYYY]`.

Prompt rules to pass to Claude in both requests: no second person, never address the rep by name, refer to them as "rep", no praise or reassurance, Australian English, no em or en dashes, percentages to whole numbers, scores to one decimal. Add a post-processing check that replaces any em or en dash with a comma or "to" and fails if "you" appears in summary-layer text.

### 4.8 Deliver (Slack)
- Upload each PDF to `C0C43USSFTK` using `files.getUploadURLExternal` + `files.completeUploadExternal`.
- One parent message per run: "Call scorecards, w/e [date]: N reps, X calls scored", with the PDFs as thread replies.
- Duplicate rule (v6 section 7): before posting, find any file the bot previously posted with the same title and delete it (`files.delete`). Never leave two scorecards for one rep and week.
- Bot scopes needed: `chat:write`, `files:write`, `files:read`, `commands`.

## 5. Rubric and playbook wording

> **PLACEHOLDER:** the live Dialpad "For Keeps Sales Call" playbook wording differs from the 2026 Sales Training doc (confirmed by Rory's Leanne reference report). Cian will paste the live wording. Lines marked LIVE below are confirmed from the reference report; the rest are training-doc wording until replaced. Keep it in `config/playbook.yaml` so it can be swapped without code changes.

| # | Step | Must-Ask | Playbook wording (verbatim script) |
|---|---|---|---|
| 1 | Check now is a good time to talk | | LIVE: "Is now a good time? I want to check a few details around your needs, timeline and budget. Is that okay?" |
| 2 | Merch purpose and alternatives | | "What made you pick [Product] when you sent through the quote request?" / "Can you let me know what the merch is for?" |
| 3 | Branding requirements | | "In terms of branding, is there anything I should know?" / "Do you need a quote on multiple quantities?" |
| 4 | Delivery deadline | | "And when would you ideally need everything delivered by?" |
| 5 | Budget or price range | ⭐ | LIVE: "Do you have a budget in mind for this order?" Probe: "Are we talking closer to $5 a unit or $25 a unit?" |
| 6 | Competing quotes or existing supplier | ⭐ | "Are you getting multiple quotes, or do you have an existing supplier you're working with?" |
| 7 | Approval and decision process | ⭐ | LIVE: "What do you need to get this approved, and who signs off?" |
| 8 | Other products to quote | ⭐ | "Are there any other products I can quote for you that you might need in the future?" |
| 9 | Next steps and quote delivery | | "I'll send you a quote by [X time] based on our chat. Once you get it, just let me know if I've missed anything, or if you'd like to go ahead." |

Three-tier rule (from v6): **Yes** = rep asked and got a usable answer. **Partial** = customer volunteered it, or rep raised it and accepted a non-answer, or the credit is a false positive (e.g. rep mentioning our own supplier is not "competing quotes"). **Missed** = no evidence. Equal weighting; ignore the point values in the training doc.

## 6. Slash command (Vercel)

- Endpoint `/api/slack/call-scoring`. Verify the Slack signing secret.
- Usage: `/call-scoring` (all reps, last week), `/call-scoring leanne`, `/call-scoring all 2026-08-28`.
- Respond within 3 seconds with an ephemeral "Running, PDFs will post here in a few minutes", then call GitHub `workflow_dispatch`.
- Only accept the command from channel `C0C43USSFTK` and from allowed Slack user IDs in `config/slack.yaml` (Niamh and Cian; Cian will supply the member IDs).
- Reply with an ephemeral error for unknown rep names, listing valid ones.

## 7. Secrets

`HUBSPOT_TOKEN`, `DIALPAD_API_KEY`, `ANTHROPIC_API_KEY`, `SLACK_BOT_TOKEN`, `SLACK_SIGNING_SECRET` (Vercel only), `GITHUB_DISPATCH_TOKEN` (Vercel only, fine-grained, Actions write on this repo). Check whether the existing HubSpot token has calls read scope; if not, list exactly which scope to add.

## 8. Acceptance test

1. Run for Leanne Cooper, w/e 28 Aug 2026.
2. Expect roughly 64 calls made and about 9 in scope. Print the dropped-call log.
3. Compare per-call and per-step ratings with Rory's reference report `docs/reference-leanne-2026-08-28.docx` (expected: week 3.4/9, 38%, Must-Ask 1.2, step total 31.0/81). Report any step where ratings differ, with the transcript evidence for each.
   - The reference was generated 1 Sep, before v6 removed the Dialpad warning panel. Do NOT reproduce that panel. Everything else in it is the target layout.
4. Post to a test DM first, then switch to `C0C43USSFTK` once Cian approves.
5. Dry-run flag `--no-post` writes PDFs to the Action artifacts only.
