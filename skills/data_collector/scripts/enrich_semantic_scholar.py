"""Stage 4: Enrich papers with Semantic Scholar API data.

Fetches references, citation counts, and author IDs for each paper.
Free tier: 1 req/s without key, 100 req/s with API key.
"""

import os
import requests
import time
from tenacity import retry, stop_after_attempt, wait_exponential

S2_API = "https://api.semanticscholar.org/graph/v1"
S2_BATCH_URL = f"{S2_API}/paper/batch"
S2_PAPER_URL = f"{S2_API}/paper"

FIELDS = (
    "title,authors,year,externalIds,citationCount,referenceCount,"
    "references.paperId,references.title,references.externalIds,"
    "publicationVenue,openAccessPdf"
)


def _s2_headers():
    key = os.environ.get("SEMANTIC_SCHOLAR_API_KEY", "")
    h = {"Accept": "application/json"}
    if key:
        h["x-api-key"] = key
    return h


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=30))
def _s2_post(url, json_data):
    resp = requests.post(url, json=json_data, headers=_s2_headers(), timeout=30)
    resp.raise_for_status()
    return resp.json()


def _s2_get(url, params=None):
    resp = requests.get(url, params=params, headers=_s2_headers(), timeout=30)
    resp.raise_for_status()
    return resp.json()


def find_papers_by_arxiv_ids(arxiv_ids, batch_size=500, delay=1.0):
    """Batch-lookup papers on Semantic Scholar.

    Args:
        arxiv_ids: list of arxiv IDs (without version suffix)
        batch_size: max 500 per request
        delay: seconds between batches (1s for free tier)

    Returns:
        dict: {arxiv_id: paper_data} for found papers
    """
    result = {}
    for i in range(0, len(arxiv_ids), batch_size):
        batch = arxiv_ids[i : i + batch_size]
        ids_payload = [f"ArXiv:{aid}" for aid in batch]
        try:
            data = _s2_post(S2_BATCH_URL, {"ids": ids_payload, "fields": FIELDS})
        except Exception as e:
            print(f"  [S2 batch error] offset={i}: {e}")
            continue

        for item in (data or []):
            if item is None:
                continue
            parsed = _parse_s2_paper(item)
            if parsed:
                aid = parsed.get("arxiv_id")
                if aid:
                    result[aid] = parsed
        if i + batch_size < len(arxiv_ids):
            time.sleep(delay)
    return result


def _parse_s2_paper(item):
    """Parse a Semantic Scholar paper object into our standard format."""
    if not item:
        return None
    external_ids = item.get("externalIds") or {}
    arxiv_id = external_ids.get("ArXiv")
    if not arxiv_id:
        return None

    authors = []
    for a in item.get("authors") or []:
        authors.append({
            "name": a.get("name", ""),
            "s2_author_id": a.get("authorId"),
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
    """Merge S2 enrichment data with arXiv papers.

    Returns:
        enriched_papers: papers list with s2 fields added
        citations_edges: list of {from, to} for citation graph
        authors_dim: dict of {author_key: author_data}
    """
    enriched = []
    citations_edges = []
    authors_dim = {}

    for p in papers:
        aid = p.get("arxiv_id", "")
        s2 = s2_results.get(aid, {})

        author_ids_for_paper = []
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
                    "paper_ids": [],
                }
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
            "embedding_row": None,
        })
        enriched.append(ep)

    return enriched, citations_edges, list(authors_dim.values())


def enrich_papers(papers):
    """Main entry point: enrich a list of arXiv papers with S2 data.

    Returns:
        (enriched_papers, citations_edges, authors_list, warnings)
    """
    arxiv_ids = [p["arxiv_id"] for p in papers]
    warnings = []

    if not arxiv_ids:
        return papers, [], [], warnings

    try:
        s2_results = find_papers_by_arxiv_ids(arxiv_ids)
        found = len(s2_results)
        if found < len(arxiv_ids):
            warnings.append(f"S2 found {found}/{len(arxiv_ids)} papers")
    except Exception as e:
        warnings.append(f"Semantic Scholar API unavailable: {e}")
        return papers, [], [], warnings

    enriched, edges, authors = build_enrichment_map(s2_results, papers)
    return enriched, edges, authors, warnings
