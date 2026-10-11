from bse import BSE
import json
from datetime import datetime, timedelta
from collections import defaultdict
import sys

def main():
    with BSE(download_folder='./') as bse:
        target_date = datetime.now() - timedelta(days=1)

        all_rows = []
        page_no = 1
        max_pages = 40

        while page_no <= max_pages:
            try:
                data = bse.announcements(
                    page_no=page_no,
                    from_date=target_date,
                    to_date=target_date
                )
                rows = data.get('Table', [])
                if not rows:
                    break
                all_rows.extend(rows)
                total = data.get('Table1', [{}])[0].get('ROWCNT', 0)
                if len(all_rows) >= total:
                    break
                page_no += 1
            except Exception as e:
                print(f"Error: {e}")
                break

        print(f"Total announcements: {len(all_rows)}")

        by_cat_subcat = defaultdict(lambda: defaultdict(list))
        for r in all_rows:
            cat = r.get('CATEGORYNAME', 'UNKNOWN')
            subcat = r.get('SUBCATNAME', 'NONE')
            by_cat_subcat[cat][subcat].append(r.get('NEWSSUB', '')[:90])

        for cat in sorted(by_cat_subcat.keys(), key=lambda c: -sum(len(v) for v in by_cat_subcat[c].values())):
            subcats = by_cat_subcat[cat]
            cat_total = sum(len(v) for v in subcats.values())
            print(f"\n\n########## {cat}: {cat_total} total ##########")
            for subcat, items in sorted(subcats.items(), key=lambda x: -len(x[1])):
                print(f"\n  [{subcat}]: {len(items)}")
                for sample in items[:2]:
                    print(f"    - {sample}")

        with open('debug-all-announcements-output.json', 'w') as f:
            json.dump(all_rows, f, indent=2)

    print("\nDone.")

try:
    main()
except Exception as e:
    print(f"\nCaught error after main logic: {e}")

sys.exit(0)
