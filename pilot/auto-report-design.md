# Automated report card + note: design (19 Oct 2026)

Goal: after E2E, a company report (card + note + tweet draft) is produced with no hand-work. Owner's only action: tap a button in FinGod_Research_Desk.

## Rules from the owner
- No "grade pending" or "audit incomplete" wording on any card. The machine decides itself: publish only when checks pass; otherwise retry the weak step later and send nothing. (Optionally a short internal "held: reason" line to the group, never on a card.)
- Company selection is decided separately, from data (readiness screen), not by gut.
- Same template as E2E: card, six-section note, tweet draft, buttons Post to X / Posted / Skip / Needs fix (all group members).

## Pipeline per symbol (one workflow, symbol in -> message out)
1. Identify: NSE symbol -> BSE code + name (state/symbols.json).
2. Collect (no AI): quarters, balance sheet, holding, SAST/pledge, filings, transcripts (pilot_build.py).
3. Judge promises (strong model, few calls) -> judge_v3.py; pillars extract + audit -> pillars_extract.py, pillars_audit_missing.py; score -> strong_report.py.
4. Draft wording (NEW, auto_copy.py): card_copy.json narrative made by code + one strong-model call, each line validated.
5. Gate (NEW, auto_gate.py): automatic checks decide publish / hold / retry.
6. Render + send (analysis_send.py) with buttons.

## Wording that was hand-written for E2E and how it becomes automatic
- Ledger rows (5): code picks the most informative checked promises (mix of met / late / missed, newest first); model writes <=46-char labels; validator keeps the verdict, call month and outcome from data.
- Trust bullets: from trust_gate signals (promoter change + cause, director exits, regulatory order, rating).
- Beyond-the-numbers panels: from audited pillar facts (visibility / moat / capacity).
- Not disclosed: from pillar facts marked absent in the latest call + deck.
- Pattern line: from the by-type counts.
- Every quote must match the transcript (4-gram check); every number must match filed data; every card line must fit on one line.

## Gate (replaces the owner's manual review)
Publish only if ALL hold; otherwise retry next quota window, never show a partial card:
- >= 14 pillars scored; audit-confirmed pillar facts >= 80% (re-audit missing facts automatically);
- profit bridge ties to filed PBT within 1%;
- all quotes verified; all card lines single-line; >= 3 checkable promises;
- latest quarter filed and call transcript (or deck) for that quarter available.

## Quota (free tier)
- ~15 strong calls for a first full pass; ~3-5 per later quarter. One new company per day; a backlog of 10 takes ~2 weeks.

## Company selection (separate decision)
Readiness screen (scripts/readiness_screen.py, no AI calls) ranks candidates by: transcripts filed in 3 years, quarterly filings, freshness of last call, shareholding history. Owner picks the batch from the ranked list. Calibration population target: ~50 companies, then grade bands by percentile.
