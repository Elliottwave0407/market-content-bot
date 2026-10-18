"""Per-company data store (JSON in the repo, versioned by git; a website can read it as-is).
companydata/<SYMBOL>/profile.json quarters.json filings.json holding.json sast.json transcripts.json promises.json score.json raw/<key>.txt.gz"""
import os, json, gzip
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "companydata")

def _p(sym, name):
    d = os.path.join(ROOT, sym.upper()); os.makedirs(d, exist_ok=True)
    return os.path.join(d, name)

def load(sym, name, default=None):
    try:
        return json.load(open(_p(sym, name), encoding="utf-8"))
    except Exception:
        return default

def save(sym, name, obj):
    """write only when content changed (keeps git history clean)"""
    new = json.dumps(obj, indent=1, sort_keys=True, ensure_ascii=False) + "\n"
    f = _p(sym, name)
    try:
        if open(f, encoding="utf-8").read() == new:
            return False
    except Exception:
        pass
    open(f, "w", encoding="utf-8").write(new)
    return True

def save_raw(sym, key, text):
    d = os.path.join(os.path.dirname(_p(sym, "x")), "raw"); os.makedirs(d, exist_ok=True)
    f = os.path.join(d, key + ".txt.gz")
    if not os.path.exists(f):
        with open(f, "wb") as fh, gzip.GzipFile(fileobj=fh, mode="wb", mtime=0) as g:
            g.write(text.encode("utf-8"))

def load_raw(sym, key):
    f = os.path.join(os.path.dirname(_p(sym, "x")), "raw", key + ".txt.gz")
    try:
        return gzip.open(f, "rt", encoding="utf-8").read()
    except Exception:
        return None
