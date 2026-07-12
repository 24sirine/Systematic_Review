import argparse
import csv
import re
import unicodedata
from pathlib import Path
from typing import Dict, List, Tuple, Optional

OUT_HEADER = [
    "uid",
    "doi",
    "title",
    "authors",
    "venue",
    "year",
    "citations",
    "abstract",
    "url",
    "pdf_url",
    "source",
    "id_s2",
    "id_openalex",
    "id_dblp",
]

def norm_doi(x: str) -> str:
    x = (x or "").strip()
    x = re.sub(r"^https?://(dx\.)?doi\.org/", "", x, flags=re.I)
    return x.lower().strip()

def norm_title(x: str) -> str:
    x = (x or "").lower().strip()
    x = unicodedata.normalize("NFKD", x)
    x = re.sub(r"[^\w\s]", " ", x)  
    x = re.sub(r"\s+", " ", x)
    return x.strip()

def pick_longer(a: str, b: str) -> str:
    a, b = (a or "").strip(), (b or "").strip()
    return b if len(b) > len(a) else a

def pick_nonempty(a: str, b: str) -> str:
    a, b = (a or "").strip(), (b or "").strip()
    return a if a else b

def parse_int(x: str) -> Optional[int]:
    x = (x or "").strip()
    if not x:
        return None
    try:
        return int(float(x))
    except Exception:
        return None

def merge_citations(a: str, b: str) -> str:
    ia, ib = parse_int(a), parse_int(b)
    if ia is None and ib is None:
        return ""
    if ia is None:
        return str(ib)
    if ib is None:
        return str(ia)
    return str(max(ia, ib))

def add_source(existing: str, src: str) -> str:
    parts = [p for p in (existing or "").split("|") if p]
    if src not in parts:
        parts.append(src)
    return "|".join(parts)

def load_csv(path: Path) -> List[Dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        return [dict((k, (v or "").strip()) for k, v in row.items()) for row in r]

def key_for(row: Dict[str, str]) -> Tuple[str, str, str]:
    doi = norm_doi(row.get("doi", ""))
    title = norm_title(row.get("title", ""))
    year = (row.get("year", "") or "").strip()
    return doi, title, year

def upsert(
    merged: Dict[str, Dict[str, str]],
    row_in: Dict[str, str],
    src: str,
    uid_counter_ref: List[int],
) -> None:

    doi, title, year = key_for(row_in)

    found_key = None
    max_year = parse_int(year)

    for k, v in merged.items():
        v_doi = v.get("doi", "").lower()
        v_title = norm_title(v.get("title", ""))
        v_year = parse_int(v.get("year", ""))

        # 1) même DOI
        if doi and doi == v_doi:
            found_key = k
            break

        # 2) même title + même year
        if title == v_title and v_year == max_year:
            found_key = k
            break

        # 3) même title, year diff → fusion et garder la plus grande année
        if title == v_title:
            found_key = k
            if max_year and (not v_year or max_year > v_year):
                v["year"] = str(max_year)
            break

    if found_key is None:
        uid = f"P{uid_counter_ref[0]:06d}"
        uid_counter_ref[0] += 1

        out = {h: "" for h in OUT_HEADER}
        out["uid"] = uid
        out["doi"] = doi
        out["title"] = row_in.get("title", "")
        out["authors"] = row_in.get("authors", "")
        out["venue"] = row_in.get("venue", "")
        out["year"] = year
        out["citations"] = row_in.get("citations", "")
        out["abstract"] = row_in.get("abstract", "")
        out["url"] = row_in.get("url", "") or row_in.get("pub", "")
        out["pdf_url"] = row_in.get("pdf_url", "") or row_in.get("doc", "")
        out["source"] = src
        if src == "S2":
            out["id_s2"] = row_in.get("paperId", "")
        elif src == "OA":
            out["id_openalex"] = row_in.get("paperId", "")
        elif src == "DBLP":
            out["id_dblp"] = row_in.get("pub", "")

        merged[uid] = out
    else:
        out = merged[found_key]
        out["source"] = add_source(out["source"], src)
        if not out["doi"]:
            out["doi"] = doi
        out["title"] = pick_longer(out["title"], row_in.get("title", ""))
        out["authors"] = pick_longer(out["authors"], row_in.get("authors", ""))
        out["venue"] = pick_nonempty(out["venue"], row_in.get("venue", ""))
        out["citations"] = merge_citations(out["citations"], row_in.get("citations", ""))
        out["abstract"] = pick_longer(out["abstract"], row_in.get("abstract", ""))
        out["url"] = pick_nonempty(out["url"], row_in.get("url", "") or row_in.get("pub", ""))
        out["pdf_url"] = pick_nonempty(out["pdf_url"], row_in.get("pdf_url", "") or row_in.get("doc", ""))
        if src == "S2" and not out["id_s2"]:
            out["id_s2"] = row_in.get("paperId", "")
        if src == "OA" and not out["id_openalex"]:
            out["id_openalex"] = row_in.get("paperId", "")
        if src == "DBLP" and not out["id_dblp"]:
            out["id_dblp"] = row_in.get("pub", "")

def main():
    parser = argparse.ArgumentParser(description="Merge ABAC papers from S2, OpenAlex, and DBLP")
    parser.add_argument("--basename", required=True, help="Base name of files, e.g., 'abac'")
    args = parser.parse_args()

    basename = args.basename
    s2_file = Path(f"{basename}_s2.csv")
    oa_file = Path(f"{basename}_openalex.csv")
    dblp_file = Path(f"{basename}_dblp.csv") if Path(f"{basename}_dblp.csv").exists() else Path(f"{basename}.csv")

    for f in [s2_file, oa_file, dblp_file]:
        if not f.exists():
            raise FileNotFoundError(f"Missing file: {f}")

    merged: Dict[str, Dict[str, str]] = {}
    uid_counter_ref = [1]

    for row in load_csv(dblp_file):
        upsert(merged, row, "DBLP", uid_counter_ref)

    for row in load_csv(oa_file):
        upsert(merged, row, "OA", uid_counter_ref)

    for row in load_csv(s2_file):
        upsert(merged, row, "S2", uid_counter_ref)

    out_file = Path(f"{basename}_merged.csv")
    with out_file.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUT_HEADER, delimiter=';', quoting=csv.QUOTE_ALL, lineterminator='\n')
        writer.writeheader()
        for row in merged.values():
            for k in row:
                row[k] = row[k].replace('\n', ' ').replace('\r', ' ')
            writer.writerow(row)

    print(f"Merge done: {out_file} ({len(merged)} merged rows)")

if __name__ == "__main__":
    main()

