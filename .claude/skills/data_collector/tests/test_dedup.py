"""Tests for dedup module. Run from project root."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from skills.data_collector.scripts.dedup import dedup_papers

def test_dedup_cross_version():
    papers = [
        {"arxiv_id": "2301.00001", "arxiv_id_versioned": "2301.00001v2", "title": "v2"},
        {"arxiv_id": "2301.00001", "arxiv_id_versioned": "2301.00001v1", "title": "v1"},
    ]
    result, stats = dedup_papers(papers)
    assert stats["output_count"] == 1
    assert "v2" in result[0]["arxiv_id_versioned"]

if __name__ == "__main__":
    test_dedup_cross_version()
    print("All dedup tests passed.")
