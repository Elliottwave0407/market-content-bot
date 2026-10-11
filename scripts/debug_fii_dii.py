import requests
from bs4 import BeautifulSoup
import re
import json
import sys

def main():
    URL = "https://www.5paisa.com/share-market-today/fii-dii-data"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    response = requests.get(URL, headers=headers, timeout=20)
    print(f"Status code: {response.status_code}")

    soup = BeautifulSoup(response.text, "html.parser")
    page_text = soup.get_text(separator="\n")

    match = re.search(
        r"FII DII Activity\s*:\s*([A-Za-z]+ \d{1,2}, \d{4}).*?"
        r"FII were net (buyers|sellers) of ₹([\-0-9,\.]+) Cr in the cash segment.*?"
        r"DII were net (buyers|sellers) of ₹([\-0-9,\.]+) Cr in the cash segment",
        page_text,
        re.DOTALL
    )

    if match:
        result = {
            "date": match.group(1),
            "fii_direction": match.group(2),
            "fii_amount_cr": match.group(3),
            "dii_direction": match.group(4),
            "dii_amount_cr": match.group(5),
        }
        print("\n=== PARSED FII/DII SUMMARY ===")
        print(json.dumps(result, indent=2))

        with open("debug-fii-dii-output.json", "w") as f:
            json.dump(result, f, indent=2)
    else:
        print("\nNo match found. Printing first 2000 chars of page text for inspection:")
        print(page_text[:2000])

    print("\nDone.")

try:
    main()
except Exception as e:
    print(f"\nCaught error: {e}")

sys.exit(0)
