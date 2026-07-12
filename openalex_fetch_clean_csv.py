
import argparse
import csv
import os
import re
import time
from typing import Any, Dict, Iterable, List, Optional, Tuple
import requests

OPENALEX_WORKS_URL = "https://api.openalex.org/works"

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

def normalize_text(s: Optional[str]) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip().lower()

def decode_abstract(aii: Optional[Dict[str, List[int]]]) -> str:
    if not isinstance(aii, dict) or not aii:
        return ""
    max_pos = -1
    for positions in aii.values():
        if positions:
            mp = max(positions)
            if mp > max_pos:
                max_pos = mp
    if max_pos < 0:
        return ""
    tokens = [""] * (max_pos + 1)
    for word, positions in aii.items():
        for p in positions:
            if 0 <= p < len(tokens) and not tokens[p]:
                tokens[p] = word
    return " ".join(t for t in tokens if t)

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
    pattern_matches = [bool(p.search(combined_text)) for p in patterns]
    if not pattern_matches:
        return False
    return all(pattern_matches) if mode == "all" else any(pattern_matches)

def get_with_backoff(
    session: requests.Session, 
    params: Dict[str, Any], 
    min_interval: float = 1.0,
     max_retries: int = 8
     ) -> Dict[str, Any]:
    backoff = 1.0
    last_call = getattr(get_with_backoff, "_last_call", 0.0)

    for _ in range(max_retries):
        elapsed = time.time() - last_call
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        try:
            response = session.get(OPENALEX_WORKS_URL, params=params, timeout=30)
            get_with_backoff._last_call = time.time()

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

    raise RuntimeError("OpenAlex request failed after retries")

def build_filter(from_year: int, to_year: int, cs_only: bool) -> str:
    if from_year > to_year:
        raise ValueError(f"from_year ({from_year}) cannot be greater than to_year ({to_year})")
    f = [
        f"from_publication_date:{from_year}-01-01",
        f"to_publication_date:{to_year}-12-31"
    ]
    if cs_only:
        f.append("concepts.id:C41008148")
    return ",".join(f)

def iter_openalex_works(search: str, from_year: int, to_year: int, cs_only: bool, per_page: int, mailto: Optional[str], min_interval: float) -> Iterable[Dict[str, Any]]:
    cursor = "*"
    page = 0
    select = ",".join([
        "id",
        "display_name",
        "publication_year",
        "doi",
        "abstract_inverted_index",
        "primary_location",
        "best_oa_location",
        "authorships",
        "cited_by_count",
    ])
    filt = build_filter(from_year, to_year, cs_only)

    with requests.Session() as session:
        while True:
            params: Dict[str, Any] = {
                "search": search,
                "filter": filt,
                "select": select,
                "per_page": per_page,
                "cursor": cursor,
            }
            if mailto:
                params["mailto"] = mailto

            data = get_with_backoff(session, params, min_interval=min_interval)
            results = data.get("results") or []
            meta = data.get("meta") or {}
            next_cursor = meta.get("next_cursor")

            print(f"[OA page {page}] fetched {len(results)} | next cursor = {'yes' if next_cursor else 'no'}")

            for w in results:
                yield w

            page += 1
            if not next_cursor:
                break
            cursor = next_cursor

def safe_get(d: Any, path: List[str]) -> Any:
    cur = d
    for k in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur

def authors_to_str(w: Dict[str, Any]) -> str:
    authorships = w.get("authorships") or []
    if not isinstance(authorships, list):
        return ""
    names: List[str] = []
    for au in authorships:
        if not isinstance(au, dict):
            continue
        a = au.get("author") or {}
        if isinstance(a, dict):
            n = (a.get("display_name") or "").strip()
            if n:
                names.append(n)
    seen = set()
    out = []
    for n in names:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return "; ".join(out)

def extract_row(w: Dict[str, Any]) -> Dict[str, str]:
    work_id = (w.get("id") or "").strip()
    paper_id = work_id.rsplit("/", 1)[-1] if "/" in work_id else work_id

    title = (w.get("display_name") or "").strip()
    year = str(w.get("publication_year") or "")

    doi = (w.get("doi") or "").strip()
    if doi.lower().startswith("https://doi.org/"):
        doi = doi[len("https://doi.org/"):]

    abstract = decode_abstract(w.get("abstract_inverted_index"))
    primary_location = w.get("primary_location") or {}
    best_oa_location = w.get("best_oa_location") or {}

    venue = (safe_get(primary_location, ["source", "display_name"]) or "").strip()

    pdf_url = (safe_get(best_oa_location, ["pdf_url"]) or "").strip()

    if not pdf_url:
        pdf_url = (safe_get(primary_location, ["pdf_url"]) or "").strip()

    cit = w.get("cited_by_count")
    cit_s = str(cit) if cit is not None else ""

    return {
        "doi": doi,
        "title": title,
        "abstract": abstract.replace("\n", " ").strip(),
        "authors": authors_to_str(w),
        "venue": venue,
        "year": year,
        "citations": cit_s,
        "url": work_id,
        "pdf_url": pdf_url,
        "paperId": paper_id,
    }

def main() -> None:
    ap = argparse.ArgumentParser(description="Fetch OpenAlex works to CSV (CS-filtered, title/abstract filtering; no DOI resolve).")
    ap.add_argument("--search", required=True)
    ap.add_argument("--terms", required=True, help='Comma-separated terms enforced in TITLE or ABSTRACT.')
    ap.add_argument("--mode", choices=["any", "all"], default="all", help="all: all terms must match in title/abstract. any: at least one.")
    ap.add_argument("--out", required=True,  help="Output CSV path")

    ap.add_argument("--from-year", type=int, default=1995)
    ap.add_argument("--to-year", type=int, default=2026)
    ap.add_argument("--cs-only", action="store_true")
    ap.add_argument("--no-cs-only", dest="cs_only", action="store_false")
    ap.set_defaults(cs_only=True)

    ap.add_argument("--per-page", type=int, default=200)
    ap.add_argument("--require-abstract", action="store_true")

    ap.add_argument("--mailto", default=os.getenv("OPENALEX_MAILTO"))
    ap.add_argument("--rps", type=float, default=1.0)

    args = ap.parse_args()

    terms = [t.strip() for t in args.terms.split(",") if t.strip()]
    patterns = compile_term_patterns(terms)
    min_interval = 1.0 / args.rps if args.rps > 0 else 1.0

    seen = matched = written = filtered = 0
    missing_abstract = 0

    with open(args.out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADER)
        writer.writeheader()

        for w in iter_openalex_works(
            search=args.search,
            from_year=args.from_year,
            to_year=args.to_year,
            cs_only=args.cs_only,
            per_page=args.per_page,
            mailto=args.mailto,
            min_interval=min_interval,
        ):
            seen += 1
            title = (w.get("display_name") or "")
            abstract = decode_abstract(w.get("abstract_inverted_index"))

            if not match_in_title_or_abstract(title, abstract, patterns, args.mode):
                filtered += 1
                continue

            matched += 1

            if not abstract.strip():
                missing_abstract += 1
                if args.require_abstract:
                    continue

            writer.writerow(extract_row(w))
            written += 1

    print("\nDONE")
    print(f"Seen: {seen}")
    print(f"Matched (title/abstract filter): {matched}")
    print(f"Written: {written}")
    print(f"Filtered out (no match in title/abstract): {filtered}")
    print(f"Abstract missing among matched: {missing_abstract}")

if __name__ == "__main__":
    main()
