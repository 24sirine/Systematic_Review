import sys
import time
import csv
import requests
from pathlib import Path
from typing import Dict, List

ENDPOINT = "https://sparql.dblp.org/sparql"
PAGE_SIZE = 100
MAX_RETRIES = 5


def sparql_post(query: str) -> Dict:
    headers = {
        "Accept": "application/sparql-results+json",
        "Content-Type": "application/sparql-query",
    }

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = requests.post(ENDPOINT, headers=headers, data=query, timeout=30)
            if r.status_code == 200:
                return r.json()

            if r.status_code in (429, 503, 504):
                time.sleep(2 ** attempt)
                continue

            raise RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")
        except Exception as e:
            if attempt == MAX_RETRIES:
                raise
            time.sleep(2 ** attempt)

    raise RuntimeError("SPARQL failed")

def load_template(path: Path) -> str:
    if not path.exists():
        sys.exit(f"Missing file: {path}")
    return path.read_text(encoding="utf-8")

def main():
    if len(sys.argv) < 2:
        sys.exit("Usage: py dblp_fetch_clean.py <title>  (ex: abac → abac.csv)")

    title = sys.argv[1]
    out_csv = Path(f"{title}.csv")

    ids_template = load_template(Path("queries/ids.rq"))
    details_template = load_template(Path("queries/details_by_values.rq"))

    rows = {}
    offset = 0
    page = 1

    while True:
        print(f"Page {page} (OFFSET={offset})")

        ids_query = (
            ids_template
            .replace("__LIMIT__", str(PAGE_SIZE))
            .replace("__OFFSET__", str(offset))
        )

        ids_json = sparql_post(ids_query)
        bindings = ids_json.get("results", {}).get("bindings", [])

        if not bindings:
            print("Fin de pagination.")
            break

        pub_ids = [b["pub"]["value"] for b in bindings]
        values_block = " ".join(f"<{pid}>" for pid in pub_ids)

        details_query = details_template.replace("__VALUES__", values_block)
        details_json = sparql_post(details_query)

        for b in details_json["results"]["bindings"]:
            pub = b["pub"]["value"]
            rows[pub] = {
                "doi": b.get("doi_s", {}).get("value", ""),
                "title": b.get("title_s", {}).get("value", ""),
                "authors": b.get("authors", {}).get("value", ""),
                "venues": b.get("venues", {}).get("value", ""),
                "year": b.get("year_s", {}).get("value", ""),
                "pub": pub,
                "doc": b.get("doc_s", {}).get("value", ""),
            }

        offset += PAGE_SIZE
        page += 1

    with out_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "doi","title","authors", "venues", "year",  "pub", "doc"
        ])

        for r in rows.values():
            writer.writerow([
                r["doi"],
                r["title"],
                r["authors"],
                r["venues"],
                r["year"],
                r["pub"],
                r["doc"],
            ])

    print(f"CSV final : {out_csv}")
    print(f"Publications : {len(rows)}")

if __name__ == "__main__":
    main()