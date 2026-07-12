import argparse
import csv
import os
import re
import time
from typing import Any, Dict, Iterable, List, Optional
import requests

S2_BULK_URL = "https://api.semanticscholar.org/graph/v1/paper/search/bulk"

FIELDS = ",".join([
    "paperId",
    "title",
    "abstract",
    "url",
    "venue",
    "openAccessPdf",
    "year",
    "externalIds",
    "authors",
    "citationCount",
])

CSV_HEADER = [
    "doi",
    "title",
    "abstract",
    "authors",
    "venue",
    "year",
    "citations",
    "url",
    "pdf_url",
    "paperId",
]

def build_headers(api_key: Optional[str]) -> Dict[str, str]:
    h = {"User-Agent": "s2-fetch-csv/1.0"}
    if api_key:
        h["x-api-key"] = api_key
    return h

def normalize_text(s: Optional[str]) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip().lower()

def compile_term_patterns(terms: List[str]) -> List[re.Pattern]:
    patterns: List[re.Pattern] = []
    for t in terms:
        t_norm = normalize_text(t)
        if not t_norm:
            continue

        if re.fullmatch(r"[a-z]+", t_norm):
            patterns.append(re.compile(rf"\b{re.escape(t_norm)}\b", re.IGNORECASE))
        else:
            words = t_norm.split(" ")
            sep = r"(?:\s+|-)+"
            phrase_pat = sep.join(re.escape(w) for w in words if w)
            patterns.append(re.compile(phrase_pat, re.IGNORECASE))
    return patterns

def match_in_title_or_abstract(title: str, abstract: str, patterns: List[re.Pattern], mode: str) -> bool:
    combined_text = f"{title or ''}\n{abstract or ''}"
    if not combined_text.strip():
        return False
    pattern_matches  = [bool(p.search(combined_text)) for p in patterns]
    if not pattern_matches :
        return False
    return all(pattern_matches ) if mode == "all" else any(pattern_matches)

def request_with_backoff_s2(
    session: requests.Session,
    params: Dict[str, Any],
    hdrs: Dict[str, str],
    min_interval: float = 1.0,
    max_retries: int = 8,
) -> Dict[str, Any]:
    backoff = 1.0
    last_call = getattr(request_with_backoff_s2, "_last_call", 0.0)

    for _ in range(max_retries):
        elapsed = time.time() - last_call
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)

        try:
            response = session.get(S2_BULK_URL, params=params, headers=hdrs, timeout=30)
            request_with_backoff_s2._last_call = time.time()

            if response.status_code == 200:
                return response.json()

            if response.status_code == 429 or 500 <= response.status_code < 600:
                ra = response.headers.get("Retry-After")
                if ra:
                    try:
                        time.sleep(float(ra))
                    except ValueError:
                        time.sleep(backoff)
                else:
                    time.sleep(backoff)
                backoff = min(backoff * 2, 60)
                continue

            response.raise_for_status()

        except (requests.Timeout, requests.ConnectionError):
            time.sleep(backoff)
            backoff = min(backoff * 2, 60)

    raise RuntimeError("Semantic Scholar request failed after retries")

def iter_bulk_search(query: str, year: str, limit: int, api_key: Optional[str]) -> Iterable[Dict[str, Any]]:
    hdrs = build_headers(api_key)
    params: Dict[str, Any] = {
        "query": query,
        "fields": FIELDS,
        "year": year,
        "limit": limit,
    }

    next_page_token = None
    page_index = 0

    with requests.Session() as session:
        while True:
            if next_page_token:
                params["token"] = next_page_token
            else:
                params.pop("token", None)

            data = request_with_backoff_s2(session, params, hdrs)
            papers = data.get("data", [])
            next_page_token = data.get("token")

            print(f"[S2 page {page_index}] fetched {len(papers)} | next token = {'yes' if next_page_token else 'no'}")

            for p in papers:
                yield p

            page_index += 1
            if not next_page_token:
                break

def get_doi(paper: Dict[str, Any]) -> str:
    ext = paper.get("externalIds") or {}
    if isinstance(ext, dict):
        return (ext.get("DOI") or ext.get("doi") or "").strip()
    return ""

def get_pdf_url(paper: Dict[str, Any]) -> str:
    oa = paper.get("openAccessPdf") or {}
    if isinstance(oa, dict):
        return (oa.get("url") or "").strip()
    return ""

def get_authors_str(paper: Dict[str, Any]) -> str:
    authors = paper.get("authors") or []
    if not isinstance(authors, list):
        return ""
    names: List[str] = []
    for a in authors:
        if isinstance(a, dict):
            n = (a.get("name") or "").strip()
            if n:
                names.append(n)
    # de-duplicate while preserving order
    seen = set()
    out = []
    for n in names:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return "; ".join(out)

def extract_row(paper: Dict[str, Any]) -> Dict[str, str]:
    cit = paper.get("citationCount")
    cit_s = str(cit) if cit is not None else ""

    return {
        "doi": get_doi(paper),
        "title": (paper.get("title") or "").strip(),
        "abstract": (paper.get("abstract") or "").replace("\n", " ").strip(),
        "authors": get_authors_str(paper),
        "venue": (paper.get("venue") or "").strip(),
        "year": str(paper.get("year") or ""),
        "citations": cit_s,
        "url": (paper.get("url") or "").strip(),
        "pdf_url": get_pdf_url(paper),
        "paperId": (paper.get("paperId") or "").strip(),
       
    }

def main() -> None:
    ap = argparse.ArgumentParser(description="Fetch Semantic Scholar bulk search results to CSV (no DOI resolving).")
    ap.add_argument("--query", required=True, help="Broad API query for /paper/search/bulk")
    ap.add_argument("--terms", required=True,
                    help='Comma-separated terms enforced in TITLE or ABSTRACT. Example: "attribute based access control,access control"')
    ap.add_argument("--mode", choices=["any", "all"], default="all",
                    help="all: all terms must match in title/abstract. any: at least one.")
    ap.add_argument("--out", required=True, help="Output CSV path")
    ap.add_argument("--year", default="1995-", help='Year range, e.g. "1995-" or "1995-2026"')
    ap.add_argument("--limit", type=int, default=1000, help="Bulk page size (max 1000)")
    ap.add_argument("--api-key", default=os.getenv("S2_API_KEY"), help="Semantic Scholar API key (optional)")
    ap.add_argument("--require-abstract", action="store_true",
                    help="Only export rows that have a non-empty abstract")

    args = ap.parse_args()

    terms = [t.strip() for t in args.terms.split(",") if t.strip()]
    patterns = compile_term_patterns(terms)

    seen = matched = written = filtered = 0
    missing_abstract = 0

    with open(args.out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADER)
        writer.writeheader()

        for paper in iter_bulk_search(args.query, args.year, args.limit, args.api_key):
            seen += 1
            title = paper.get("title") or ""
            abstract = paper.get("abstract") or ""

            if not match_in_title_or_abstract(title, abstract, patterns, args.mode):
                filtered += 1
                continue

            matched += 1

            if not (abstract or "").strip():
                missing_abstract += 1
                if args.require_abstract:
                    continue

            writer.writerow(extract_row(paper))
            written += 1

    print("\nDONE")
    print(f"Seen: {seen}")
    print(f"Matched (title/abstract filter): {matched}")
    print(f"Written: {written}")
    print(f"Filtered out (no match in title/abstract): {filtered}")
    print(f"Abstract missing among matched: {missing_abstract}")

if __name__ == "__main__":
    main()
