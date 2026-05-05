"""Stage 5: Build graph edge tables from paper and author data."""

import hashlib
from collections import Counter


def derive_authors_from_raw(papers):
    """Build author list and populate author_ids from arXiv authors_raw.

    Used as fallback when Semantic Scholar enrichment returns no data.
    Generates stable author IDs from MD5 hash of author name.

    Returns:
        (authors_list, updated_papers)
    """
    author_map = {}   # name -> author_id
    authors_list = []
    updated_papers = []

    for p in papers:
        author_ids = []
        for name in p.get("authors_raw", []):
            if not name:
                continue
            if name not in author_map:
                aid = "a_" + hashlib.md5(name.encode()).hexdigest()[:8]
                author_map[name] = aid
                authors_list.append({
                    "author_id": aid,
                    "name": name,
                    "s2_author_id": None,
                    "affiliation_ids": [],
                    "paper_ids": [],
                })
            author_ids.append(author_map[name])

        new_p = dict(p)
        new_p["author_ids"] = author_ids
        updated_papers.append(new_p)

    for a in authors_list:
        a["paper_ids"] = [
            p["arxiv_id"] for p in updated_papers
            if a["author_id"] in p.get("author_ids", [])
        ]

    return authors_list, updated_papers


def build_author_edges(papers):
    """Build co-authorship and author-paper edges from papers' author_ids."""
    coauthor_pairs = Counter()
    author_paper_edges = []

    for p in papers:
        author_ids = p.get("author_ids", [])
        aid = p.get("arxiv_id", "")

        for author_id in author_ids:
            author_paper_edges.append({"author_id": author_id, "paper_id": aid})

        for i in range(len(author_ids)):
            for j in range(i + 1, len(author_ids)):
                pair = tuple(sorted([author_ids[i], author_ids[j]]))
                coauthor_pairs[pair] += 1

    coauthorship_edges = [
        {"author_a": pair[0], "author_b": pair[1], "weight": count}
        for pair, count in coauthor_pairs.items()
    ]
    return coauthorship_edges, author_paper_edges


def deduplicate_citation_edges(edges):
    """Remove duplicate citation edges."""
    seen = set()
    unique = []
    for e in edges:
        key = (e["from"], e["to"])
        if key not in seen:
            seen.add(key)
            unique.append(e)
    return unique


def filter_internal_citations(edges, arxiv_id_set):
    """Keep only citation edges where BOTH ends are in our paper set."""
    return [e for e in edges if e["from"] in arxiv_id_set and e["to"] in arxiv_id_set]


def build_all_edges(papers, authors_list, citations_edges):
    """Build all edge tables for the data center.

    If authors_list is empty (S2 unavailable), derives authors from
    papers' authors_raw field as fallback.

    Returns:
        dict with keys: citations, citations_external, coauthorship,
                        author_paper, authors_list, papers
    """
    # Fallback: derive authors from arXiv authors_raw when S2 has no data
    if not authors_list:
        authors_list, papers = derive_authors_from_raw(papers)

    aid_set = {p["arxiv_id"] for p in papers}
    citations = deduplicate_citation_edges(citations_edges)
    citations_internal = filter_internal_citations(citations, aid_set)
    coauthorship, author_paper = build_author_edges(papers)

    return {
        "citations": citations_internal,
        "citations_external": citations,
        "coauthorship": coauthorship,
        "author_paper": author_paper,
        "authors_list": authors_list,
        "papers": papers,
    }
