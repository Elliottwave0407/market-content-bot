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
Not confirmed: MRR Rs 35-40 Cr by Mar-26 (Q4 FY26 average ~Rs 31.9 Cr/month; exit rate not verified).
Pattern: financial promises kept; physical GPU deployment promises slip 1-3 months. Indicative credibility ~7/10.
Promoter holding 51.6% (Sep-24) -> 39.45% (Jun-26) coincides with fresh issuance (L&T SAST acquisitions Dec-24, May-25); split between dilution and selling NOT yet verified.
