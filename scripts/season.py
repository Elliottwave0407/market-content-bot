"""Results-season calendar (IST). Indian quarterly results peak from the 15th of the first month after a quarter ends to the 15th of the next month
(Q2: 15 Oct - 15 Nov, Q3: 15 Jan - 15 Feb, Q4: 15 Apr - 15 May, Q1: 15 Jul - 15 Aug); a few days of margin are added. Outside it, results are rare.
Used to share the free Gemini quota: during the peak the result-card lane keeps its keys; outside it the other jobs (presentation vision, audits) may use all keys."""
import time

def is_peak(now=None):
    t = time.gmtime((now or time.time()) + 19800)
    m, d = t.tm_mon, t.tm_mday
    first = m in (1, 4, 7, 10)      # first month after quarter end: from the 13th
    second = m in (2, 5, 8, 11)     # second month: until the 20th (late filers, SME half-yearly)
    return (first and d >= 13) or (second and d <= 20)

def phase(now=None):
    return "peak" if is_peak(now) else "quiet"

if __name__ == "__main__":
    print(phase())
