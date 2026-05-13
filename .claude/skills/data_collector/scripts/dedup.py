"""Stage 3: Deduplicate papers across versions and categories."""

from .utils import normalize_arxiv_id


def dedup_papers(papers):
    """Deduplicate paper list.

    1. Cross-version dedup: keep latest version per arxiv_id
    2. Cross-category dedup: same arxiv_id appears in multiple categories

    Args:
        papers: list of paper dicts with 'arxiv_id' key

    Returns:
        (deduped_papers, dedup_stats)
    """
    groups = {}
    for p in papers:
        aid = normalize_arxiv_id(p.get("arxiv_id", ""))
        if not aid:
            continue
        if aid not in groups:
            groups[aid] = p
        else:
            existing_ver = _version_number(groups[aid].get("arxiv_id_versioned", ""))
            current_ver = _version_number(p.get("arxiv_id_versioned", ""))
            if current_ver > existing_ver:
                groups[aid] = p

    result = list(groups.values())
    stats = {
        "input_count": len(papers),
        "after_version_dedup": len(groups),
        "output_count": len(result),
    }

    return result, stats


def _version_number(versioned_id):
    """Extract version number from arxiv ID like '2301.00001v2' -> 2."""
    if "v" in versioned_id:
        try:
            return int(versioned_id.split("v")[-1])
        except ValueError:
            return 1
    return 1


# Standalone test
if __name__ == "__main__":
    sample = [
        {"arxiv_id": "2301.00001v2", "title": "Paper A v2"},
        {"arxiv_id": "2301.00001v1", "title": "Paper A v1"},
        {"arxiv_id": "2301.00002v1", "title": "Paper B"},
    ]
    result, stats = dedup_papers(sample)
    print(f"Dedup stats: {stats}")
    print(f"Result: {[p['title'] for p in result]}")
