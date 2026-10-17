import sys, os, re, collections
sys.path.insert(0, os.path.dirname(__file__))
from ci_out import p, publish
from datetime import datetime
import recap_post as rp
days = [datetime(2026, 10, d) for d in (6, 7, 8, 9, 12, 13, 14, 15)]
tr, rec, avs = [], [], 0
sub = collections.Counter()
for d in days:
    try:
        rows = rp._fetch_day(d)
    except Exception as e:
        p("err", d.date(), repr(e)[:60]); continue
    n_tr = n_rec = 0
    for x in rows:
        txt = " ".join(str(x.get(k) or "") for k in ("NEWSSUB", "HEADLINE", "MORE")).lower()
        if "transcript" in txt:
            n_tr += 1; tr.append(x)
        if x.get("AUDIO_VIDEO_FILE"):
            avs += 1
        if "recording" in txt or "audio" in txt:
            n_rec += 1; rec.append(x)
    p(d.date(), "rows", len(rows), "transcript", n_tr, "recording/audio", n_rec)
p("transcript total", len(tr), "recording total", len(rec), "rows with AUDIO_VIDEO_FILE", avs)
for x in tr[:12]:
    p("TR |", x.get("SUBCATNAME"), "|", (x.get("SLONGNAME") or "")[:28], "|", (x.get("NEWSSUB") or "")[:70], "|", (x.get("HEADLINE") or "")[:60].replace("\n", " "), "| pdf:", bool(x.get("ATTACHMENTNAME")))
for x in rec[:12]:
    p("REC|", x.get("SUBCATNAME"), "|", (x.get("SLONGNAME") or "")[:28], "|", (x.get("HEADLINE") or "")[:80].replace("\n", " "), "| AV:", bool(x.get("AUDIO_VIDEO_FILE")))
publish()
