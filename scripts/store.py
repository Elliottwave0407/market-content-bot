"""Append-only data store (free, lives in the repo under store/). One JSON-lines file per kind per month: store/<kind>/<YYYY-MM>.jsonl
Kinds: results (every result card posted: all numbers, verdict, caption, telegram message id), fii_dii (one row per trading day), posts (every other Telegram post).
put() upserts by key, so a corrected re-post replaces its own row. Never raises: storing must never stop a post."""
import os, json, time
from datetime import datetime, timezone, timedelta
ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "store")
IST = timezone(timedelta(hours=5, minutes=30))

def _now():
    return datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")

def put(kind, key, rec, month=None):
    try:
        month = month or datetime.now(IST).strftime("%Y-%m")
        d = os.path.join(ROOT, kind); os.makedirs(d, exist_ok=True)
        f = os.path.join(d, f"{month}.jsonl")
        rows = []
        if os.path.exists(f):
            for ln in open(f, encoding="utf-8"):
                ln = ln.strip()
                if ln:
                    try: rows.append(json.loads(ln))
                    except Exception: pass
        row = {"key": key, "ts": _now(), **rec}
        rows = [r for r in rows if r.get("key") != key] + [row]
        tmp = f + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            for r in rows: fh.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
        os.replace(tmp, f)
        return True
    except Exception:
        return False

def _mid(resp):
    try:
        r = (resp or {}).get("result") or {}
        return {"msg_id": r.get("message_id"), "chat_id": (r.get("chat") or {}).get("id")}
    except Exception:
        return {}

def _cr(m):
    if not m: return None
    return {k: (v if k in ("eps", "kind", "bank") else (None if v is None else round(v / 10.0, 2))) for k, v in m.items() if k in ("revenue", "ebitda", "pbt", "pat", "eps", "kind", "nii", "prov")}

def _mins(filed):
    try:
        if isinstance(filed, str):
            filed = datetime.fromisoformat(filed[:19])
        if filed.tzinfo is None: filed = filed.replace(tzinfo=IST)
        return round((datetime.now(IST) - filed).total_seconds() / 60.0, 1)
    except Exception:
        return None

def log_result(route, caption, resp, card_last=None, filed=None):
    """After a result card was accepted by Telegram. card_last = card.LAST (set by card.render)."""
    try:
        L = card_last or {}
        qs = L.get("quarters") or []
        key = f"{L.get('ticker', '?')}|{qs[0]['q'] if qs else '?'}|{L.get('basis', '?')}"
        rt = L.get("rating") or {}
        put("results", key, {"route": route, "name": L.get("name"), "ticker": L.get("ticker"), "basis": L.get("basis"), "half_yearly": bool(L.get("half")),
                             "unit": "INR_crore (eps in INR)", "quarters": [{"q": q["q"], **(_cr(q.get("m")) or {})} for q in qs],
                             "yprev": _cr(L.get("yprev")), "verdict": rt.get("tier"), "score": rt.get("score"), "rating_version": L.get("rating_version"),
                             "rating_detail": {k: v for k, v in rt.items() if k not in ("tier",)}, "caption": caption, "filed_at": (str(filed)[:19] if filed else None), "latency_min": (_mins(filed) if filed else None), **_mid(resp)})
    except Exception:
        pass

def log_post(route, caption, resp, extra=None):
    try:
        mid = _mid(resp)
        put("posts", f"{route}|{mid.get('msg_id') or int(time.time())}", {"route": route, "caption": caption, **mid, **(extra or {})})
    except Exception:
        pass

def log_fii_dii(iso, row):
    put("fii_dii", iso, dict(row), month=iso[:7])

def put_text(kind, name, text):
    """Large raw text (e.g. a concall transcript), gzipped: store/<kind>/<name>.txt.gz. Returns the relative path or None."""
    try:
        import gzip, re
        name = re.sub(r"[^A-Za-z0-9_.-]+", "_", name)
        d = os.path.join(ROOT, kind); os.makedirs(d, exist_ok=True)
        f = os.path.join(d, name + ".txt.gz")
        with gzip.open(f, "wt", encoding="utf-8") as fh: fh.write(text)
        return os.path.relpath(f, os.path.dirname(ROOT))
    except Exception:
        return None
