import os, requests
from ci_out import p, publish
r = requests.get("https://integrate.api.nvidia.com/v1/models", headers={"Authorization": "Bearer " + os.environ.get("NVIDIA_API_KEY", "")}, timeout=60)
p("status", r.status_code)
ids = sorted(m["id"] for m in r.json().get("data", [])) if r.status_code == 200 else []
p(len(ids), "models")
p(" | ".join(ids))
publish()
