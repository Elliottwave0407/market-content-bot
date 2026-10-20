# Quarterly Verdict v1.0 (frozen 20-Oct-2026)

The six-tier rating on every result card: **Blockbuster, Excellent, Strong, Steady, Weak, Poor**. Code: `scripts/quarter_rating.py` (`rate6`, `RATING_VERSION`). Badge name: QUARTERLY VERDICT.

## Inputs
Current quarter, previous quarter (QoQ base), year-ago quarter (YoY base), and optionally the quarter before the year-ago one (seasonality). All on the SAME basis (consolidated preferred). Revenue, EBITDA (operating profit), PAT. No operating-profit row (banks, NBFCs, insurers) = no badge; a separate finance model is planned.

## Score 0-100 (piecewise-linear between anchors, no cliffs)
Reading order: revenue first, then profit, then EBITDA, then margins. Weights out of 96, scaled to 100: revenue YoY 22, revenue QoQ 8, PAT YoY 22, PAT QoQ 6, EBITDA YoY 16, EBITDA QoQ 6, margin YoY 10, margin QoQ 6.
- Seasonality: half of last year's same-quarter QoQ move is removed (clipped: revenue +-30, EBITDA +-40, margin +-6 pts) when available.
- Margin level: when the margin is 20%+, a small dip counts as neutral (tolerance 1.0 to 2.5 pts, growing with the margin). Margin gains are scaled to the room left (never reduced, capped 3x).

## Gates (a tier can be pulled DOWN, never up)
- Net loss, PAT down 30%+ YoY, or revenue and PAT both down QoQ with PAT up under 10% YoY: Weak at best.
- PAT down 5%+ YoY: Steady at best. PAT down 0-5%: Strong at best.
- Revenue YoY under 15%: Steady at best, unless PAT is up 30%+ YoY (Strong at best) or 50%+ (no cap), and only when revenue is not falling QoQ.
- Revenue down more than 5% QoQ (seasonally adjusted): Steady at best.
- Margin fell QoQ (raw): Strong at best.
- Small base (year-ago revenue under Rs 25 Cr or EBITDA under Rs 2 Cr) or turnaround from a zero/negative EBITDA base: Excellent at best.

## Tier cut-offs (score)
Excellent 70+, Strong 48-69, Steady 36-47, Weak 20-35, Poor below 20.

## Blockbuster (rule based)
Route A: EBITDA YoY 40%+, revenue YoY 20%+, margin YoY at least 0, at least 2 of {EBITDA QoQ 20%+, margin QoQ +2 pts, margin YoY +4 pts}, and score 80+.
Route B (explosive growth): revenue, EBITDA and PAT all up 50%+ YoY, revenue not falling QoQ; margin not required.

## Evidence
- Fitted to the owner's own ratings of 13 borderline results (12 of 13 reproduced; HFCL Sep-25 is the known exception, owner: Strong with a caution, model: Steady).
- Backtest on 1,029 like-for-like company-quarters (95 companies, Jun-23 to Sep-26, finance excluded): Blockbuster 6%, Excellent 11%, Strong 16%, Steady 31%, Weak 21%, Poor 15%.
- Owner's target mix: 5-10 / 10-15 / 15-20 / 25-30 / 15-20 / 10-15 percent.

## Known limits / not yet done
- Finance companies (lenders, insurers, capital-market firms): separate model, no badge until then.
- Possible merger/consolidation distortions (e.g. Schaeffler Jun-26, revenue +127%) are not detected.
- No price-action or expected-vs-actual input (planned separate engine feature).
- Recalibrate only as a numbered release; the owner may revisit after more labelled results.

---

# v1.1 (live on cards from 20-Oct-2026) - size-aware and noise-aware additions
Everything in v1.0 above still applies. v1.1 adds:
- **Abnormal quarter-ago base:** if the previous quarter had zero/negative EBITDA, a margin below -20%, or a big loss, the QoQ pillars (EBITDA, margin, PAT) score neutral. QoQ means nothing after an exceptional quarter.
- **Tiny profit base:** if year-ago PAT is under Rs 1 Cr or under 1.5% of revenue, PAT YoY scores neutral and cannot unlock the "revenue growth under 15%" exemptions.
- **Sharp sequential fall:** EBITDA or PAT down 30%+ QoQ (normal base): Steady at best.
- **Two-year seasonality:** when last year's and the year before's same-quarter QoQ moves point the same way, 80% of their average is removed (instead of 50% of one year). Needs the two-year-old quarters; the live card does not fetch them yet, so this part is inactive on live cards.
- Tiny-base Blockbuster stays capped at Excellent (year-ago revenue under Rs 25 Cr or EBITDA under Rs 2 Cr), as in v1.0.
- Backtest mix (v1.1): large/mid 1,881 quarters: 6/10/14/33/21/16 percent; small 1,026 quarters: 5/11/9/26/24/25; micro 765: 2/9/10/24/28/26. Owner's 13 calls: still 12 of 13.

# Half-yearly mode (SME companies) - dry run only, not live
SMEs file half-yearly (about Nov and May) as PDFs on BSE; NSE and BSE results tables do not carry them. `scripts/sme_half.py` reads the PDF, columns = current half | preceding half | same half last year, labels Mar/Sep only. A filing is accepted only if the column dates are exactly 6 and 12 months apart and end in Mar/Sep (quarterly filers such as Asarfi Hospital are rejected and belong to the normal route). SME arithmetic check: total income minus expenses must equal PBT; PAT must be sane versus PBT (tax lines often exclude deferred tax). `rate6(half=True)`: the HoH changes are halved to a per-quarter equivalent and no seasonality is applied. Cards show an "HoH" column.
Open: Route B Blockbuster allows a large margin fall (CWD Mar-26: revenue +286%, margin -13 pts, still Blockbuster); the live poller does not pick up SME filings yet.

# Finance model (draft v0, not live)
Lenders (HDBFS, HUDCO, IREDA, LICHSGFIN, M&MFIN, MANAPPURAM, PNBHOUSING, POONAWALLA, SBICARD): NII (revenue minus finance costs) replaces EBITDA, so "margin" is the spread kept. Capital-market firms (360ONE, ABSLAMC, ANANDRATHI, ANGELONE, NUVAMA) use the normal model. Banks and insurers: not covered (different XBRL). Mix on 95 lender quarters: 6/14/31/25/19/5 percent; 51 capital-market quarters: 4/24/33/20/18/2.
