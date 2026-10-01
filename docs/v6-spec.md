# Call Scoring Report: Build Instructions (v6, final)

> Converted to text from Rory's "Call Reporting CoWork Task Weekly" Word doc on 1 Oct 2026. Source of truth for report content, structure, tone and colours. `docs/brief.md` changes only how data is gathered and delivered (no browser step: transcripts come from the Dialpad API and Claude scores them).

This is the complete instruction set for producing a weekly sales call scorecard at For Keeps Merch. Follow it end to end. No other document is needed to run the report.
Reference output: "Call Scorecard: Leanne Cooper, w/e 28 Aug 2026" (Google Doc). Background: claude/dialpad-playbook-setup.md, claude/dialpad-playbook-scoring-calibration.md.
1. Inputs
Ask for, or confirm, these three before starting:
[TABLE]
Input | Example | Notes
Rep name | Leanne Cooper | Must map to a HubSpot owner id
Week ending | Fri 28 Aug 2026 | Monday to Friday of that week
HubSpot owner id | 93213822 | Look up with search_owners if unknown
[/TABLE]
Known owner ids: Leanne Cooper 93213822.
2. Pull the calls (HubSpot, one query)
Do not scrape Dialpad's call list. HubSpot holds it.
search_crm_objects, objectType CALL:
hubspot_owner_id EQ <owner id>
hs_timestamp BETWEEN <week start> <week end> UTC. Melbourne is UTC+10, so Monday 00:00 local is the Sunday 14:00Z. A Mon to Fri week ending 28 Aug = 2026-08-23T14:00:00Z to 2026-08-28T14:00:00Z.
hs_call_duration GT 120000 (milliseconds, so 2 minutes)
sort hs_timestamp ASCENDING, limit 50
properties: hs_call_title, hs_call_body, hs_call_duration, hs_timestamp, hs_call_to_number, hs_call_direction
hs_call_body contains, as plain text:
Call Summary Link: https://dialpad.com/callhistory/callreview/<callId>?tab=transcript
Call recording url, AI recap, AI CSAT, call purpose, outcome, action items
Ai Playbook Adherence percentage
Keep the Call Summary Link. It is the ▶ Listen link in the report and the page you open in step 4.
Trap: the recording id in Dialpad's coaching Recordings tab is NOT the call id. Only the id inside hs_call_body opens a call review page.
3. Qualify the calls (HubSpot, one query)
Pull the contacts associated with those calls. Properties: firstname, lastname, company, createdate, lifecyclestage, num_associated_deals, hs_analytics_source.
Keep a call only if all four are true:
Over 2 minutes (already filtered)
Contact createdate is within days of the call, so genuinely new
lifecyclestage = opportunity
At least one associated deal
Drop: existing customers, contacts on file for months, repeat calls to the same number in the period, and numbers with no contact record.
Record how many calls the rep made in total that week, for the scope line. Expect a large drop: 64 calls produced 9 in scope for Leanne's first week.
4. Get the step evidence (Dialpad, one page per call)
The only browser step. For each qualifying call:
Open https://dialpad.com/callhistory/callreview/<callId>
Click the AI Playbooks panel in the right sidebar
Read the per topic evidence
The panel gives, per step: the step name, the prompt, and a Summary naming the specific words that earned the credit. The evidence is what you score, not the tick.
Extraction that works:
const b=[...document.querySelectorAll('button')].find(x=>(x.innerText||'').trim()==='AI Playbooks');
if(b) b.click();
await new Promise(r=>setTimeout(r,6000));
const t=document.body.innerText, i=t.indexOf('AI Playbooks'), s=t.slice(i);
const score=(s.match(/For Keeps Sales Call - ([\d.]+)%/)||[])[1];
const parts=s.split(/\n(?=\d\.\s)/).slice(1);
({score, topics: parts.map(p=>{
  const name=(p.split('\n')[0]||'').trim();
  const m=p.match(/Summary:\s*([\s\S]*?)(?=\n\d\.\s|$)/);
  return {t:name, hit:!!m, ev: m? m[1].replace(/\s+/g,' ').trim().slice(0,230):''};
})})

5. Score
Nine steps, matching the live Dialpad playbook. Must-Ask = steps 5, 6, 7, 8.
[TABLE]
# | Step | Must-Ask
1 | Check now is a good time to talk | 
2 | Merch purpose and alternatives | 
3 | Branding requirements | 
4 | Delivery deadline | 
5 | Budget or price range | ⭐
6 | Competing quotes or existing supplier | ⭐
7 | Approval and decision process | ⭐
8 | Other products to quote | ⭐
9 | Next steps and quote delivery | 
[/TABLE]
Three tier rule, applied to the evidence text:
Yes = 1.0 — the rep asked and got a usable answer.
Partial = 0.5 — the customer volunteered it; or the rep raised it and accepted a non answer; or the credit is a false positive (Dialpad crediting "competing quotes" because the rep mentioned our own supplier, for example).
Missed = 0.0 — no evidence.
Dialpad's adherence percentage runs roughly double the real score (76.6% vs 38% on Leanne's first week) because it credits a step when either party mentions the subject. Never show it in the report. It is working data only.
Two scores per call: Overall out of 9, also as a percentage. Must-Ask out of 4. Percentages matter because the scale changed from 10 steps to 9 on 1 Sep 2026.
Verify before writing: step totals and call totals must sum to the same number.
6. Write the report
Register: software output, not a person
The report is generated by a system. It has no voice, no name, and no relationship with the rep. Niamh translates it into a coaching conversation. The document does not attempt that conversation itself.
No second person. Not "you closed almost every call properly". Instead: "Quote commitment plus timeframe on 8 of 9 calls."
No addressing the rep by name, no opener, no sign-off, no "Rory".
No reassurance, no encouragement, no verdicts on character or effort.
Refer to the rep as "rep". Refer to customers by name.
Strengths are observations with evidence, not praise. Gaps are observations with evidence, not criticism.
Tone test: could this sentence appear in a system-generated report the rep reads without a manager present, without landing as either a telling-off or a pep talk? If not, cut it.
Two word budgets
Tight in the summary layer (snapshot, tables, grid, strengths, gaps, priority actions, follow ups): table cells 10 words maximum, bullets one line each, no restating a number already in a table. Scannable in two minutes.
Generous in the per-call "What happened" notes and the biggest-miss panels: one to three sentences per step. Structure each as what happened → what was left unestablished → why it matters commercially. Quote the customer or rep verbatim where it makes the point. "Not asked." alone is fine only where there is genuinely nothing more to say.
Never drop a section, a call, or a piece of evidence to save words.
Colour
[TABLE]
Band | Hex | Meaning
Green | #d9ead3 | 67%+, or Yes
Amber | #fff2cc | 40 to 66%, or Partial
Red | #f4cccc | Under 40%, or Missed
Table headers | #1c4587 background, white text | 
Callout panels | #e8eaf6 | 
Section headings | #1c4587 text | 
[/TABLE]
Structure, in order
Title block — rep name, week ending, calls scored, generated date, and a scope line in an #e8eaf6 panel stating calls made vs calls in scope.
Snapshot — 5 coloured tiles: Overall %, Must-Ask, best step, weakest step, average length.
Baseline panel — only where the playbook was not on screen for the period, or the rep is in their first 3 to 4 weeks. Name the first comparable week.
Call scores table — day, customer, company, length, Overall, Must-Ask, ▶ Listen. Colour coded, with a week average row and a colour key beneath.
Step scores table — all 9 steps, score out of the call count, one short pattern note each, total row.
Headline pattern — one #e8eaf6 panel, one or two sentences.
Step grid — one row per call, Y/P/M per step, colour coded, with a key.
Strengths — 3 to 4 bullets, each with a named example.
Gaps — 3 to 4 bullets, each with a number.
Priority actions — 4 column table: priority and step score, evidence bullets, script (verbatim playbook wording), numeric target. Three rows, plus an "Also monitor" line for the fourth gap.
Flagged for follow up — deals needing action this week: deal, why, action.
Call by call — one full scorecard per call in scope. Heading, date, length, Overall, Must-Ask, ▶ Listen link, one line of context, then a 9 row table with a full "What happened" note against every step, then a coloured panel: amber or red "Biggest miss", green "Best moment" where a call was exceptional, #e8eaf6 "Context" line where circumstances explain a low score (a price match, an inbound callback).
No method footer. No limitations footer. No Dialpad warning panel. Removed deliberately, 1 Sep 2026.
Sections 7 and 12 are not alternatives. The grid shows the pattern; the scorecards carry the evidence.
Priority actions: how to choose
Rank the three weakest steps by score, then adjust for leverage:
The opening line comes first where it is weak, because it unblocks the questions after it.
Prefer a step where the evidence shows repeated missed customer signals.
Always quote the playbook wording verbatim as the script. Never invent a better line; the rep has the playbook on screen and a mismatch costs trust in both.
Give every action a numeric target for next week.
7. Deliver
Google Doc in Rory's Drive, titled Call Scorecard: [Rep name], w/e [date]. Build it as HTML and upload with contentMimeType: text/html.
Send Rory the link. Niamh reviews, then decides what to pass on and how.
If a previous version of the same week's report exists, trash it. Two scorecards for one rep and week is a real confusion risk.
8. Conventions
Australian English. Ex GST. No em or en dashes. Percentages to whole numbers, scores to one decimal. Do not sign the document.