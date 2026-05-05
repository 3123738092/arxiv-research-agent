"""Tests for dedup module. Run from project root."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from skills.data_collector.scripts.dedup import dedup_papers, update_seen_ids

def test_dedup_cross_version():
    papers = [
        {"arxiv_id": "2301.00001", "arxiv_id_versioned": "2301.00001v2", "title": "v2"},
        {"arxiv_id": "2301.00001", "arxiv_id_versioned": "2301.00001v1", "title": "v1"},
    ]
    result, stats = dedup_papers(papers)
    assert stats["output_count"] == 1
    assert "v2" in result[0]["arxiv_id_versioned"]

def test_dedup_cross_date():
    papers = [
        {"arxiv_id": "2301.00001", "title": "Paper A"},
        {"arxiv_id": "2301.00002", "title": "Paper B"},
    ]
    result, stats = dedup_papers(papers, last_fetch_seen={"2301.00001"})
    assert stats["output_count"] == 1

def test_update_seen_ids():
    last_fetch = {"seen_ids": ["2301.00001"]}
    new = [{"arxiv_id": "2301.00002"}]
    updated = update_seen_ids(last_fetch, new)
    assert "2301.00001" in updated
    assert "2301.00002" in updated

if __name__ == "__main__":
    test_dedup_cross_version(); test_dedup_cross_date(); test_update_seen_ids()
    print("All dedup tests passed.")
