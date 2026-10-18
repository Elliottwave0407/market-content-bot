"""Quota-free preview of the pillar extraction using the Flash-Lite models (separate daily quotas from the strong models).
Writes pillars.json (provisional) and keeps a copy as pillars_cheap.json so the strong-model run can be compared against it later."""
import os, sys, runpy
sys.path.insert(0, os.path.dirname(__file__))
os.environ["MODELS"] = "gemini-flash-lite-latest,gemini-3.1-flash-lite,gemini-3.5-flash-lite"
runpy.run_path(os.path.join(os.path.dirname(__file__), "pillars_extract.py"), run_name="__main__")
import store
SYM = os.environ.get("SYMBOL", "E2E").strip().upper()
d = store.load(SYM, "pillars.json")
if d: store.save(SYM, "pillars_cheap.json", d)
