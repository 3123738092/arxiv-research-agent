"""Stage 3: Deduplicate papers across versions, categories, and dates."""

from .utils import normalize_arxiv_id, load_last_fetch


def dedup_papers(papers, last_fetch_seen=None):
    """Deduplicate paper list.

    1. Cross-version dedup: keep latest version per arxiv_id
    2. Cross-category dedup: same arxiv_id appears in multiple categories
    3. Cross-date dedup: remove papers already seen in last_fetch

    Args:
        papers: list of paper dicts with 'arxiv_id' key
        last_fetch_seen: set of arxiv_ids from previous runs

    Returns:
        (deduped_papers, dedup_stats)
    """
    seen_ids = set(last_fetch_seen or [])
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

    stats = {
        "input_count": len(papers),
        "after_version_dedup": len(groups),
        "cross_date_dedup_removed": 0,
        "output_count": 0,
    }

    result = []
    for aid, p in groups.items():
        if aid in seen_ids:
            stats["cross_date_dedup_removed"] += 1
            continue
        result.append(p)

    stats["output_count"] = len(result)
    return result, stats


def _version_number(versioned_id):
    """Extract version number from arxiv ID like '2301.00001v2' -> 2."""
    if "v" in versioned_id:
        try:
            return int(versioned_id.split("v")[-1])
        except ValueError:
            return 1
    return 1


def update_seen_ids(last_fetch, new_papers):
    """Return the updated set of all seen arxiv_ids."""
    seen = set(last_fetch.get("seen_ids", []))
    for p in new_papers:
        seen.add(normalize_arxiv_id(p.get("arxiv_id", "")))
    return list(seen)


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
