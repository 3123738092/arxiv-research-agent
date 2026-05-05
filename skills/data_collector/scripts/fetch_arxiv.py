"""Stage 2: Fetch papers from arXiv API with auto-backtrack and weekend detection."""

import time
import arxiv
from datetime import datetime, timedelta
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from .utils import normalize_arxiv_id, is_weekend, weekend_window


@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=3, min=10, max=120),
    retry=retry_if_exception_type(arxiv.HTTPError),
)
def _search_arxiv(query, max_results=100):
    """Execute a single arXiv search with retry logic."""
    client = arxiv.Client(page_size=min(max_results, 30), delay_seconds=10)
    search = arxiv.Search(
        query=query,
        max_results=max_results,
        sort_by=arxiv.SortCriterion.SubmittedDate,
        sort_order=arxiv.SortOrder.Descending,
    )
    return list(client.results(search))


def build_query(categories, keywords):
    """Build arXiv API query string.

    Example: cat:cs.CL AND (all:agent OR all:skill OR all:tool use)
    """
    cat_part = " OR ".join(f"cat:{c}" for c in categories)
    kw_part = " OR ".join(f'all:"{kw}"' for kw in keywords)
    if len(categories) > 1:
        cat_part = f"({cat_part})"
    return f"{cat_part} AND ({kw_part})"


def fetch_arxiv_papers(categories, keywords, date_start, date_end, max_results=200, backtrack_days=3):
    """Fetch papers from arXiv with date range filtering and auto-backtrack.

    Args:
        categories: list of arXiv categories e.g. ["cs.CL", "cs.LG"]
        keywords: list of search keywords
        date_start: ISO date string "YYYY-MM-DD"
        date_end: ISO date string "YYYY-MM-DD"
        max_results: max papers per query
        backtrack_days: days to look back if no results found

    Returns:
        (papers_list, actual_date_used, warnings_list)
    """
    # Weekend handling: if target is Sat/Sun, adjust to Friday
    start_dt = datetime.fromisoformat(date_start)
    if is_weekend(start_dt):
        effective_date = weekend_window(start_dt)
        warnings = [f"Target date {date_start} is weekend, adjusted to {effective_date}"]
    else:
        effective_date = date_start
        warnings = []

    query = build_query(categories, keywords)
    papers = []
    search_date = effective_date

    for attempt in range(backtrack_days + 1):
        attempt_date = (
            datetime.fromisoformat(effective_date) - timedelta(days=attempt)
        ).strftime("%Y-%m-%d")
        search_query = query  # date filtering done client-side after fetch

        try:
            results = _search_arxiv(search_query, max_results)
        except Exception as e:
            # On rate limit, pause before next backtrack attempt
            if hasattr(e, 'status') and e.status == 429:
                time.sleep(30)
            warnings.append(f"arXiv API error on {attempt_date}: {e}")
            continue

        if results:
            # Client-side date filter: use attempt_date as lower bound so
            # backtracked days aren't blocked by the original date_start.
            filter_start_dt = datetime.fromisoformat(attempt_date)
            filter_end_dt = datetime.fromisoformat(date_end)
            filtered = []
            for r in results:
                pub_date = r.published.date() if r.published else None
                if pub_date and filter_start_dt.date() <= pub_date <= filter_end_dt.date():
                    filtered.append(r)
            if filtered:
                papers = filtered
                search_date = attempt_date
                if attempt > 0:
                    warnings.append(
                        f"No results for {effective_date}, backtracked to {attempt_date} "
                        f"(found {len(filtered)} papers)"
                    )
                break
            else:
                warnings.append(
                    f"No results in date range for {attempt_date}: "
                    f"API returned {len(results)}, 0 in [{attempt_date}, {date_end}]"
                )
        else:
            warnings.append(f"No results for {attempt_date} (attempt {attempt + 1}/{backtrack_days + 1})")

    structured = [_paper_to_dict(p) for p in papers]
    return structured, search_date, warnings


def _paper_to_dict(result):
    """Convert arxiv.Result to our standard dict format."""
    authors = [a.name for a in result.authors]
    return {
        "arxiv_id": normalize_arxiv_id(result.entry_id.split("/")[-1]),
        "arxiv_id_versioned": result.entry_id.split("/")[-1],
        "title": result.title.strip(),
        "abstract": result.summary.strip(),
        "authors_raw": authors,
        "published": result.published.isoformat() if result.published else None,
        "updated": result.updated.isoformat() if result.updated else None,
        "arxiv_url": result.entry_id,
        "pdf_url": result.pdf_url,
        "categories": result.categories,
        "primary_category": result.primary_category,
        "comment": result.comment,
        "journal_ref": result.journal_ref,
        "doi": result.doi,
        "source": "arxiv",
    }


def filter_by_negative_keywords(papers, negative_keywords):
    """Remove papers whose title+abstract contain any negative keyword (case-insensitive)."""
    if not negative_keywords:
        return papers
    lowered_neg = [k.lower() for k in negative_keywords]
    kept = []
    for p in papers:
        text = (p["title"] + " " + p["abstract"]).lower()
        if not any(k in text for k in lowered_neg):
            kept.append(p)
    return kept


# Standalone test
if __name__ == "__main__":
    papers, used_date, warnings = fetch_arxiv_papers(
        categories=["cs.CL"],
        keywords=["agent"],
        date_start="2026-05-04",
        date_end="2026-05-04",
        max_results=10,
        backtrack_days=3,
    )
    print(f"Fetched {len(papers)} papers from {used_date}")
    for w in warnings:
        print(f"  [WARN] {w}")
    if papers:
        print(f"  Sample: {papers[0]['title'][:80]}...")
