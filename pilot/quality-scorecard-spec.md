# FinGod Quality Scorecard + Trust Gate (design spec, 18 Oct 2026; v0 thresholds CONFIRMED by Mayank 19 Oct 2026)

Purpose: differentiate the Market Content Bot with a "Beyond the numbers" card built from concall transcript + investor presentation + filed numbers, with a transparent score. Scores the BUSINESS STORY, not the stock. No price targets / upside / buy-sell calls (SEBI Research Analyst registration risk). Name: "FinGod Quality Grade" (avoid "investment grade" = credit-rating term).

## Weights (100)
- Promoter & credibility 25: walk the talk 10 (past 3-4 calls' guidance vs reported), promoter holding & pledge 6, insider/large-holder activity 3, governance events 4, use of funds 2
- Profitability & margin 15 (5-quarter EBITDA margin trend, expansion vs last year, margin outlook)
- Balance sheet & cash quality 13 (debt, working-capital days, other income share, cash flow)
- Growth 10 (revenue/PAT growth and trend, from filed numbers)
- Visibility 8 (order book vs revenue, specific guidance, repeat business)
- Capex & capacity 8 (size vs scale, funding, timeline, capacity added)
- Product mix & value-add 8
- Moat & future roadmap 8 (verified barriers; long-term numeric targets)
- Sector & positioning 5
- Risk penalty up to -15 (concentration, regulatory, execution)
Grades: A >=75, B 60-74, C 45-59, D <45.

## Trust gate
Red (cap grade at C): auditor resignation mid-term or qualified/adverse/disclaimer opinion; regulatory/SEBI order vs company/promoter/KMP in last 24 months; promoter pledge >50% of holding or +10 pts in 2 quarters; insolvency/going-concern doubt.
Amber (cap at B): promoter holding down >=5 pts in 4 quarters with no stated reason; CFO/CEO/MD exit without explanation; guidance missed by >25% in 2 of last 3 quarters; monitoring-agency deviation in IPO proceeds; late results filing.
Data gate: fewer than 3 of 5 credibility signals available -> "not enough data", no grade.

## Rules
- Hard numbers (growth, margins) come from filed results, not from what management says.
- Every concall/presentation fact needs a verbatim quote verified against the source text; two extraction passes, keep only facts present in both; A/B needs >=80% facts verified.
- Facts only, with source and date; never "untrustworthy"/fraud language. Missing signal = "not disclosed", zero points.
- Management guidance is stored per company so next quarter's walk-the-talk check is free.

## Decisions 19 Oct 2026 (Mayank)
- Delay tolerance: a promise delivered up to 3 months late counts as on time (full credit); the lag is kept and shown in the ledger. Delays over 3 months = half credit; missed = 0. Implemented as TOL=3 in score_quant.
- Pilot sign-off: Mayank hand-checked 12 promise verdicts under that rule (judged right) and accepted the v0 thresholds. For the pilot, the grade is shown on owner sign-off (card_copy.json owner_review) even though pillar facts were 13/19 (68%) audit-confirmed; the evidence gate stays computed and recorded. Owner sign-off never substitutes for missing pillars.
- E2E Networks: grade B (70/100), trust gate Amber-watch (caps at B). Walk-the-talk 8.2/10 on 14 verifiable promises (11 on time, 1 late, 2 missed, 17 unverifiable).
- Scoring is code-only from verified facts; similar promises recorded twice (original + revised transcript) are de-duplicated.

## Data sources (checked 18 Oct 2026, via GitHub Actions)
- NSE `corporate-share-holdings-master` (symbol): ~22 quarters promoter/public % (works).
- NSE `corporate-sast-reg29`: large acquirer/seller disclosures (works).
- NSE `corporate-pledgedata`, `corporates-pit` (insider): endpoints respond but returned empty for E2E; must test on a company that has pledges/trades.
- BSE announcements (auditor, KMP, rating, regulatory, monitoring-agency reports) - already accessible.
- Transcripts: BSE SUBCATNAME "Earnings Call Transcript" (~3/day early season) plus recording links via AUDIO_VIDEO_FILE / "Link of Recording" PDFs; E2E recording mp3 transcribed OK via Gemini Flash and Whisper small (Flash-Lite loops on long audio - avoid).

## Current scan prototype
`scripts/concall_scan.py` + `.github/workflows/concall-scan.yml` (dry run, posts nothing): finds BSE transcript filings, size filter (default mcap <= Rs 25,000 Cr), Gemini extraction with verified quotes, code-computed score. First ranking (7 cos): Ganesh Benzoplast 39, Kanohar 38, Glass Wall 34, Waterways 32, Purple Style 13, Canara Robeco AMC 12, ARCIL 9. Known issues: run-to-run variance, margin-comparison parsing (guard added), 4 of 11 transcripts scanned images.

## Next steps
1. Card generator (scripts/make_card.py, data-driven, tall 1080 wide, 2x PNG) done for E2E; written research note generator next (6 sections: thesis, results & margin bridge, cash & balance sheet, walk-the-talk, beyond the numbers, not disclosed).
2. Free-tier Gemini plan: 20 requests/day/model, resets midnight Pacific; one strong pass per company per day; incremental per quarter.
3. Telegram analysis group, then second company only after the E2E process is finished.

## Calibration decision (19 Oct 2026)
- Amber cap (max B) and Red cap (max C) are kept as is.
- v0 score thresholds are provisional. After ~50 company report cards, grade bands move to percentiles of our own population.
- Under consideration: grade words next to the letter; separate business-quality and disclosure/governance sub-scores.
