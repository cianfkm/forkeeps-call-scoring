# Weekly call scorecards

HubSpot calls -> qualify -> Dialpad transcripts -> Claude (claude-sonnet-5-5) scores each call -> one PDF per rep -> Slack.
Replaces Rory's Cowork task. Report content, structure, tone and colours: `docs/v6-spec.md`. Build brief: `docs/brief.md`.

- **Schedule:** Monday ~7am Melbourne, previous Mon to Fri week (`.github/workflows/score.yml`).
- **On demand:** `/call-scoring`, `/call-scoring leanne`, `/call-scoring all 2026-08-28` in #pipeline-briefings
  (anyone in that private channel). Handler lives in the `pipeline-briefings` repo, `slack-command/api/call-scoring.js`, Vercel project `pipeline-briefings-slack`.
  Or: Actions tab > Call scorecards > Run workflow.
- **Config (no code changes needed):**
  - `config/reps.yaml` roster, HubSpot owner IDs, start dates (Baseline panel). Niamh is never scored.
  - `config/playbook.yaml` live Dialpad "For Keeps Sales Call" wording, quoted verbatim as the Script column.
  - `config/settings.yaml` qualification thresholds (`NEW_CONTACT_WINDOW_DAYS`, `REPEAT_RULE`) and model.
- **Secrets:** `HUBSPOT_TOKEN`, `DIALPAD_API_KEY` (recordings_export scope), `ANTHROPIC_API_KEY`, `SLACK_BOT_TOKEN`, `SLACK_CHANNEL_ID` (C0C43USSFTK).
- **Dry run:** Run workflow with "Dry run" ticked; PDFs, HTML and JSON land in the run's `scorecards` artifact.
- **Every dropped call and its reason** is printed in the Action log (search `DROP`), for threshold tuning.
- **Acceptance check against Rory's reference:** dry-run Leanne w/e 2026-08-28, download the artifact, then
  `python -m tools.compare_reference "out/Call Scorecard Leanne Cooper, w-e 28 Aug 2026.json"`.
- **Layout check offline:** `python -m tools.render_sample` -> `out/sample.pdf`.
