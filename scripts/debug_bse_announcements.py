from bse import BSE
import json
from datetime import datetime, timedelta

TEST_SCRIPCODES = {
    'Reliance Industries': '500325',
    'Tata Consultancy Services': '532540',
    'Infosys': '500209',
    'HDFC Bank': '500180',
    'ICICI Bank': '532174'
}

results = {}

with BSE(download_folder='./') as bse:
    to_date = datetime.now()
    from_date = to_date - timedelta(days=30)

    for name, scripcode in TEST_SCRIPCODES.items():
        print(f"\n=== {name} ===")
        try:
            data = bse.announcements(
                from_date=from_date,
                to_date=to_date,
                scripcode=scripcode
            )
            results[name] = data
            print(json.dumps(data)[:400])
        except Exception as e:
            results[name] = {"error": str(e)}
            print(f"Error: {e}")

with open('debug-bse-announcements-output.json', 'w') as f:
    json.dump(results, f, indent=2)

print("\nDone. Full output in debug-bse-announcements-output.json")
