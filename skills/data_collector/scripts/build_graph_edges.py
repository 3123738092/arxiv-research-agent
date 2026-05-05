"""Stage 5: Build graph edge tables from paper and author data."""

from collections import Counter


def build_author_edges(papers, authors_list):
    """Build co-authorship and author-paper edges.

    Returns:
        (coauthorship_edges, author_paper_edges)
    """
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

    Returns:
        dict with keys: citations, citations_external, coauthorship, author_paper
    """
    aid_set = {p["arxiv_id"] for p in papers}
    citations = deduplicate_citation_edges(citations_edges)
    citations_internal = filter_internal_citations(citations, aid_set)
    coauthorship, author_paper = build_author_edges(papers, authors_list)

    return {
        "citations": citations_internal,
        "citations_external": citations,
        "coauthorship": coauthorship,
        "author_paper": author_paper,
    }
