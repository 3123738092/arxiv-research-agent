"""Stage 4: Enrich papers with Semantic Scholar API data.

Fetches references, citation counts, and author IDs for each paper.
Free tier: 1 req/s without key, 100 req/s with API key.
Gracefully handles papers not yet indexed in S2.
"""

import os
import requests
import time
from tenacity import retry, stop_after_attempt, wait_exponential

S2_API = "https://api.semanticscholar.org/graph/v1"
S2_BATCH_URL = f"{S2_API}/paper/batch"
S2_PAPER_URL = f"{S2_API}/paper"

FIELDS = (
    "title,authors.affiliations,authors.name,year,externalIds,citationCount,"
    "referenceCount,references.paperId,references.title,references.externalIds,"
    "publicationVenue,openAccessPdf"
)

_NO_KEY_DELAY = 3.5   # free tier: 1 req/s, be extra safe
_HAS_KEY_DELAY = 0.05  # with key: 100 req/s


def _s2_headers():
    key = os.environ.get("SEMANTIC_SCHOLAR_API_KEY", "")
    h = {"Accept": "application/json"}
    if key:
        h["x-api-key"] = key
    return h


def _has_api_key():
    return bool(os.environ.get("SEMANTIC_SCHOLAR_API_KEY", ""))


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=5, max=60))
def _s2_post(url, json_data, params=None):
    resp = requests.post(url, json=json_data, params=params, headers=_s2_headers(), timeout=30)
    if resp.status_code == 429:
        retry_after = int(resp.headers.get("Retry-After", 60))
        time.sleep(retry_after)
        resp = requests.post(url, json=json_data, params=params, headers=_s2_headers(), timeout=30)
    resp.raise_for_status()
    return resp.json()


def find_papers_by_arxiv_ids(arxiv_ids, batch_size=500, delay=None):
    """Batch-lookup papers on Semantic Scholar.

    Args:
        arxiv_ids: list of arxiv IDs (without version suffix)
        batch_size: max 500 per request
        delay: seconds between batches (auto-detected from API key presence)

    Returns:
        dict: {arxiv_id: paper_data} for found papers
    """
    if delay is None:
        delay = _HAS_KEY_DELAY if _has_api_key() else _NO_KEY_DELAY

    result = {}
    not_found = []
    api_errors = []
    total = len(arxiv_ids)

    for i in range(0, total, batch_size):
        batch = arxiv_ids[i : i + batch_size]
        # S2 expects "ArXiv:" prefix
        ids_payload = [f"ArXiv:{aid}" for aid in batch]

        try:
            data = _s2_post(S2_BATCH_URL, {"ids": ids_payload}, params={"fields": FIELDS})
        except requests.HTTPError as e:
            code = e.response.status_code if hasattr(e, 'response') else 0
            if code == 400:
                # "No valid paper ids given" — papers not indexed yet
                not_found.extend(batch)
            else:
                api_errors.append(f"HTTP {code}: {e}")
            continue
        except Exception as e:
            api_errors.append(str(e))
            continue

        for idx, item in enumerate(data or []):
            aid = batch[idx] if idx < len(batch) else None
            if item is None:
                if aid:
                    not_found.append(aid)
                continue
            parsed = _parse_s2_paper(item, aid)
            if parsed and parsed.get("arxiv_id"):
                result[parsed["arxiv_id"]] = parsed

        if i + batch_size < len(arxiv_ids):
            time.sleep(delay)

    if not_found:
        n = len(not_found)
        print(f"  [S2] {n}/{total} papers not yet indexed (too recent)")

    return result


def _parse_s2_paper(item, fallback_arxiv_id=None):
    """Parse a Semantic Scholar paper object into our standard format."""
    if not item:
        return None

    external_ids = item.get("externalIds") or {}
    arxiv_id = external_ids.get("ArXiv")
    if not arxiv_id:
        arxiv_id = fallback_arxiv_id
    if not arxiv_id:
        return None

    authors = []
    for a in item.get("authors") or []:
        affiliations = a.get("affiliations") or []
        authors.append({
            "name": a.get("name", ""),
            "s2_author_id": a.get("authorId"),
            "affiliations": affiliations,
        })

    references = []
    for ref in item.get("references") or []:
        ref_ext = (ref.get("externalIds") or {})
        ref_aid = ref_ext.get("ArXiv")
        references.append({
            "paper_id": ref.get("paperId"),
            "title": ref.get("title"),
            "arxiv_id": ref_aid,
        })

    return {
        "arxiv_id": arxiv_id,
        "s2_paper_id": item.get("paperId"),
        "title": item.get("title", ""),
        "year": item.get("year"),
        "authors": authors,
        "citation_count": item.get("citationCount"),
        "reference_count": item.get("referenceCount"),
        "references": references,
        "venue": item.get("publicationVenue"),
        "open_access_pdf": (item.get("openAccessPdf") or {}).get("url"),
    }


def build_enrichment_map(s2_results, papers):
    """Merge S2 enrichment data with arXiv papers."""
    import hashlib

    enriched = []
    citations_edges = []
    authors_dim = {}
    affiliations_dim = {}

    for p in papers:
        aid = p.get("arxiv_id", "")
        s2 = s2_results.get(aid, {})

        author_ids_for_paper = []
        affiliation_ids_for_paper = []
        for a in s2.get("authors", []):
            a_name = a.get("name", "")
            if not a_name:
                continue
            author_key = a.get("s2_author_id") or a_name.lower().replace(" ", "_")
            if author_key not in authors_dim:
                authors_dim[author_key] = {
                    "author_id": author_key,
                    "name": a_name,
                    "s2_author_id": a.get("s2_author_id"),
                    "affiliation_ids": [],
                    "paper_ids": [],
                }

            # Collect affiliations for this author
            for aff_name in a.get("affiliations") or []:
                if not aff_name:
                    continue
                aff_id = "aff_" + hashlib.md5(aff_name.encode()).hexdigest()[:8]
                if aff_id not in affiliations_dim:
                    affiliations_dim[aff_id] = {
                        "affiliation_id": aff_id,
                        "name": aff_name,
                        "country": None,
                    }
                if aff_id not in authors_dim[author_key]["affiliation_ids"]:
                    authors_dim[author_key]["affiliation_ids"].append(aff_id)
                if aff_id not in affiliation_ids_for_paper:
                    affiliation_ids_for_paper.append(aff_id)

            authors_dim[author_key]["paper_ids"].append(aid)
            author_ids_for_paper.append(author_key)

        for ref in s2.get("references", []):
            ref_aid = ref.get("arxiv_id")
            if ref_aid:
                citations_edges.append({"from": aid, "to": ref_aid})

        ep = dict(p)
        ep.update({
            "s2_paper_id": s2.get("s2_paper_id"),
            "citation_count": s2.get("citation_count"),
            "reference_count": s2.get("reference_count"),
            "year": s2.get("year"),
            "venue": s2.get("venue"),
            "open_access_pdf": s2.get("open_access_pdf"),
            "author_ids": author_ids_for_paper,
            "affiliation_ids": affiliation_ids_for_paper,
            "embedding_row": None,
        })
        enriched.append(ep)

    return enriched, citations_edges, list(authors_dim.values()), list(affiliations_dim.values())


def enrich_papers(papers):
    """Main entry point: enrich a list of arXiv papers with S2 data.

    Returns:
        (enriched_papers, citations_edges, authors_list, affiliations_list, warnings)
    """
    arxiv_ids = [p["arxiv_id"] for p in papers]
    warnings = []

    if not arxiv_ids:
        return papers, [], [], [], warnings

    try:
        s2_results = find_papers_by_arxiv_ids(arxiv_ids)
        found = len(s2_results)
        if found < len(arxiv_ids):
            warnings.append(f"S2 found {found}/{len(arxiv_ids)} papers")
    except Exception as e:
        warnings.append(f"Semantic Scholar API unavailable: {e}")
        return papers, [], [], [], warnings

    enriched, edges, authors, affiliations = build_enrichment_map(s2_results, papers)
    return enriched, edges, authors, affiliations, warnings
