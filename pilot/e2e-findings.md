# E2E pilot findings (18 Oct 2026) - dry run, nothing posted

## Pipeline lessons
- Numbers must be exchange-agnostic: `scripts/fin_data.py` merges NSE integrated filings (2025+), NSE legacy results (pre-2025) and BSE tables. EBITDA = PBT + finance cost + depreciation - other income (ties to BSE and presentation).
- NSE legacy results API stops at Dec-24 for E2E; newer results sit in `api/integrated-filing-results` (xbrl, consolidated/standalone, qe_Date).
- Gemini AUDIO transcript hallucinated numbers (said Rs 473.8 Mn, +117%, Q2 FY25; filed: Rs 2,238 Mn, +411%). Never use it for numbers. Use official transcript PDFs (NSE announcements desc "Analysts/Institutional Investor Meet/Con. Call Updates", text contains "Transcript") or Whisper as rough fallback. Cross-check every figure against filed numbers.
- 12 official E2E transcripts found on NSE (Nov-23 to Jul-26). Promise extraction: `scripts/pilot_wtt.py`, all quotes verified.

## E2E quarterly (Rs Cr; Mar-25..May-26 standalone, Jun-26+ consolidated)
Sep-24 rev 47.6 / EBITDA 66.1% / PAT 12.2 | Mar-25 33.5 / 39.8% / 13.6 | Jun-25 36.1 / 29.1% / -2.8 | Sep-25 43.8 / 41.1% / -13.5 | Dec-25 70.0 / 56.6% / -5.7 | Mar-26 95.6 / 60.7% / 6.4 | Jun-26 156.8 / 75.2% / 43.9 | Sep-26 223.8 / 76.6% / 72.7

## Walk-the-talk ledger (hand-checked from verified quotes vs filed numbers)
Delivered: equity raise within "couple of quarters" (May-24 -> preferential/L&T Dec-24); FY26 revenue 1.5-1.7x FY25 (actual 1.50x); EBITDA back to ~60% (Mar-26 60.7%); 40-50% growth medium term (FY25 +74%, FY26 +50%); Rs 450 Cr debt facility (Jul-26 call: loan ~Rs 450 Cr).
Delayed: Chennai DC "couple of weeks" (May-25) -> end Jul/Aug-25; 2,048 H200 live in Q1 FY26 -> slipped; EBITDA 65-75% by Mar-26 -> 60.7% (reached 75.2% a quarter later); Blackwell live before Q4 FY26 end -> mid-May 2026.
CORRECTION (auto-judge, 18 Oct): MRR Rs 35-40 Cr by Mar-26 appears DELIVERED - a later call quotes 'March MRR of INR 37.4 crores' (spoken by an analyst on the call; quarterly average was Rs 31.9 Cr/month). Treat exit-MRR figures as 'per call', not filed.
Pattern: financial promises kept; physical GPU deployment promises slip 1-3 months. Indicative credibility ~7/10.
Promoter holding 51.6% (Sep-24) -> 39.45% (Jun-26) coincides with fresh issuance (L&T SAST acquisitions Dec-24, May-25); split between dilution and selling NOT yet verified.

## Auto-judge run (Flash-class model, 18 Oct): 16 delivered, 5 delayed, 2 missed (1 false: Rs 800 Cr capex was an 'ideal world' remark, not a promise), 8 unverifiable.
Lessons: quote-exists check does not prove the quote supports the verdict; strong judging model matters; exclude hypothetical remarks from promises.
## Gemini free-tier facts (measured 18 Oct)
Limits are per model per day (error code GenerateRequestsPerDayPerProjectPerModel-FreeTier). gemini-flash-latest (3.8) exhausted by repeated test runs; gemini-3.5-flash allowed ~9 calls/day; flash-lite models still available. Use a model ladder, cache extractions, compute numeric promises in code, avoid repeated full-test reruns.

## Data store (18 Oct)
Everything per company is saved under `companydata/<SYMBOL>/` in the repo (website-ready JSON): profile, quarters, filings (all NSE announcements), holding, sast, transcripts (+ gz raw text cache), promises (with verdicts, evidence, model, date), score (to come). Built by `scripts/pilot_build.py` (workflow pilot-collect; JUDGE=1 runs the quota-costly judge). Extraction cached per transcript (extractor version v3). Note: the repo is public, so stored company data/analysis is public; revisit if the analysis should be private.

## Trust Gate + quantitative score (code only, 18 Oct) - `scripts/score_quant.py`, output `companydata/E2E/score.json`
Facts read from filings (trust_docs.json): ICRA A- (Stable) Nov-25; three Reg-32 statements say no deviation in use of preferential-issue proceeds; Apr-26 NSE clarification was an XBRL form-selection error (annual results tagged half-yearly); 19-May-26 order from Delhi Collector of Stamps on stamp duty for dematerialised share issuance - company says it paid duty correctly, writ pending in Delhi High Court (not a SEBI order).
Governance watch items: 5 director exits + 1 senior-management exit in 24 months (reasons not read); promoter holding 59.7% (Jun-24) -> 39.45% (Jun-26) in two steps coinciding with preferential allotments (promoter family also bought on 21-Sep-24 per SAST).
Gate: AMBER-WATCH (no red). Pledge and insider (PIT) feeds returned nothing: marked not verified, not clean.
Scored so far (v0 rules): profitability 15/15, growth 10/10 (low-base flag: prior-year revenue only Rs 43.8 Cr), promoter holding/pledge 3/6, insider/large-holder 2/3, governance 2/4, use of funds 2/2 = 34/40; walk-the-talk provisional 9.4/10 from code-checked promises only. Pending: balance sheet 13, visibility 8, capex 8, mix 8, moat 8, sector 5, risk penalty. No grade yet.
Caveat: extreme-high scores on margin/growth show the v0 thresholds are generous at the top; recalibrate after a second company (not before the E2E process is finished).

## Balance sheet pillar (code only, 18 Oct) - `companydata/E2E/balance.json`
NSE half-yearly integrated filings (Mar/Sep) carry full balance sheet + cash flow (XBRL). E2E Sep-26 (consolidated): debt Rs 450 Cr (Rs 160 Cr a year earlier), cash+bank Rs 734 Cr => net cash Rs 284 Cr; D/E 0.25; receivable days ~14; other income 14% of PBT; H1 operating cash flow Rs 396 Cr = 1.37x EBITDA; H1 capex Rs 420 Cr, free cash flow about -Rs 23 Cr; interest cover 14x. Score 12/13. Scored so far 46/53 (+ walk-the-talk provisional 9.4/10). Pending: visibility, capex/capacity, mix, moat, sector, risk penalty (all need presentation/call extraction = Gemini quota).
Caveat: Sep-26 is consolidated, earlier periods standalone (company added subsidiaries) - comparisons across bases are flagged.

## Governance facts read from filings (18 Oct)
- Dec-24: promoter-holding drop confirmed as dilution: 04-Dec-2024 preferential allotment of 29,79,579 shares to Larsen & Toubro (non-promoter) for Rs 1,079 Cr; Sep-24 preferential (Rs 405.66 Cr) with promoter-family acquisitions (SAST 21-Sep-24). Not promoter selling.
- Independent-director resignations in 24m: Dec-24, Mar-25, Aug-25, Jan-26 (4). Reasons: Dec-24/Mar-25/Aug-25 only in attached letters; Jan-26 "personal and professional commitments" (director had been appointed 28-Aug-25). CRO (senior management) resigned Jun-26, personal commitments. Oct-26 exit = L&T nominee replaced by another L&T nominee (routine, ignored).
- Gate stays AMBER-WATCH on board turnover + the stamp-duty order; no red.

## Quota workaround: cheap-model judge (18 Oct) - `scripts/judge_v2.py`
Problem: strong Gemini model has ~9-20 calls/day free. Fix: retrieval (top sentences per later call) + two Flash-Lite-family models (separate per-model daily quotas, ~500/day each) must agree + verbatim quote must exist in the retrieved text + analyst-question quotes rejected + second-look wider retrieval for unresolved. Cost per full E2E history: ~35 calls per model, no strong-model calls. Conservative by design (unverifiable when unsure).
E2E result: 8 delivered, 2 delayed, 1 missed, 12 unverifiable (+ 2 disagree). Checked against known facts: Chennai delay (Jan-25 promise) correct, Blackwell slip correct, equity raise correct; misses: Jul-25 Chennai promise left unverifiable; Cluster-1 mid-May now unverifiable. Questionable: Nov-23 "no equity raise in short term" marked missed (equity raised Sep-24).
Walk-the-talk now scored 8.6/10 from 18 verifiable promises (14 delivered, 3 delayed, 1 missed; 14 unverifiable not scored). Scored so far 54.6/63.

## 18 Oct 2026 (evening): strong-model plan under the free tier
- Hard fact: free tier = 20 requests/day PER MODEL (error text: "generate_content_free_tier_requests, limit: 20, model: gemini-3.8-flash / gemini-3.6-flash"). Reset ~06:00 IST. Flash-Lite models are separate quotas and were still available. Pro models: not available free.
- Budget per company per day with two strong models (3.8 Flash = gemini-flash-latest, 3.6 Flash = gemini-3.5-flash): judge ~10 big calls (one per earnings call, full text of up to 8 later calls inside), audit 1-2 calls, pillar extraction 1 call, pillar audit 1-2 calls = ~15 total. Never run test runs against the strong models; probe with Flash-Lite instead.
- New scripts: judge_v3.py (strong judge + evidence audit by a different model; resumable; keeps old verdict as v2_label; keeps previous verdict if audit is unavailable), pillars_extract.py (visibility, capex/capacity, mix, moat, sector, risks: one extraction call over latest 3 calls + 2 presentations, quotes verified in code, audit by second model), score_pillars.py (v0 code rules), strong_report.py, workflow pilot-strong.yml (separate steps so annotations are not capped), probe_quota.py.
- First strong run was cut off by the per-day cap after 1-2 calls; two sample observations: the strong model also quoted ANALYST statements as evidence (so the audit stage is needed), and its first-pass quotes for the Nov-23 capex promise were weak.
- Scheduled: full strong run on 19 Oct ~06:45 IST.

## 19 Oct 2026 - strong run attempt (06:46 IST)
- Workflow pilot-strong dispatched right after the scheduled time; no test runs first.
- Result: BOTH strong models returned per-day 429 ("limit: 20, model: gemini-3.8-flash / gemini-3.6-flash") after only 1 successful call each. Retry hint "22h41m" from 01:17 UTC = about 05:28 IST on 20 Oct.
- So the daily quota was already used up before the run started, although nothing of ours ran between the 18 Oct evening runs and this one. Cause unknown (to check: AI Studio usage page ai.dev/rate-limit; whether the same Google project/key is used by another bot; whether failed or retried calls count).
- What the run did get: 4 promises re-judged (16-Nov-2023 x2 kept previous verdict, audit unavailable; 30-May-2024 fundraise promise: strong judge said unverifiable, was "delivered" by cheap judge). Pillars extraction: no answer (quota). Pillars facts unchanged (2 confirmed of 3).
- Scores now (partial, NOT a grade): walk-the-talk 8.5/10 (17 verifiable: 13 delivered, 3 delayed, 1 missed; 15 unverifiable). Code-scored pillars with the old sparse facts: visibility 1.5/8, capex 4/8, product mix 0/8, moat 2/8, sector 0/5, risk -2. Provisional 60.0 of 100 is meaningless until pillar facts are extracted by a strong model.
- Lesson: free tier = 20 requests/day/model and a failed day cannot be recovered; do not schedule more than one strong attempt per day, and check usage on the AI Studio page first.
