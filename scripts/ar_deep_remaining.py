import json, os
R = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "store") + "/"
p = R + "annual_report_deep/_priority.json"
L = json.load(open(p)) if os.path.exists(p) else []
print(sum(1 for i in L if not os.path.exists(R + "annual_report_deep/%s_2026.json" % i)))
