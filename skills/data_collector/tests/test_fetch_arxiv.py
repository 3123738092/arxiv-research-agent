"""Tests for fetch_arxiv module. Run from project root."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from skills.data_collector.scripts.fetch_arxiv import build_query, filter_by_negative_keywords

def test_build_query_single_category():
    q = build_query(["cs.CL"], ["agent", "skill"])
    assert "cat:cs.CL" in q and 'all:"agent"' in q and "AND" in q and "OR" in q

def test_build_query_multi_category():
    q = build_query(["cs.CL", "cs.LG"], ["diffusion"])
    assert "(cat:cs.CL OR cat:cs.LG)" in q

def test_filter_negative_keywords():
    papers = [
        {"title": "Deep Learning for MRI", "abstract": "Medical imaging."},
        {"title": "Deep Learning for NLP", "abstract": "Natural language processing."},
    ]
    result = filter_by_negative_keywords(papers, ["medical imaging", "MRI"])
    assert len(result) == 1 and result[0]["title"] == "Deep Learning for NLP"

if __name__ == "__main__":
    test_build_query_single_category(); test_build_query_multi_category()
    test_filter_negative_keywords()
    print("All fetch_arxiv tests passed.")
