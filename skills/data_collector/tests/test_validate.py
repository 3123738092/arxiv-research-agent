"""Tests for validate module. Run from project root."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from skills.data_collector.scripts.validate import (
    validate_papers, validate_authors, validate_citation_edges, validate_coauthorship_edges,
)

def test_validate_valid_paper():
    papers = [{"arxiv_id": "2301.00001", "title": "Test Paper", "source": "arxiv"}]
    valid, errors = validate_papers(papers)
    assert len(valid) == 1 and len(errors) == 0

def test_validate_empty_title():
    papers = [{"arxiv_id": "2301.00001", "title": "", "source": "arxiv"}]
    valid, errors = validate_papers(papers)
    assert len(errors) > 0

def test_validate_author():
    authors = [{"author_id": "a1", "name": "Alice Smith"}]
    valid, errors = validate_authors(authors)
    assert len(valid) == 1

def test_validate_citation_edge():
    edges = [{"from": "2301.00001", "to": "2301.00002"}]
    valid, errors = validate_citation_edges(edges)
    assert len(valid) == 1

def test_validate_coauthorship_edge():
    edges = [{"author_a": "a1", "author_b": "a2", "weight": 3}]
    valid, errors = validate_coauthorship_edges(edges)
    assert len(valid) == 1

if __name__ == "__main__":
    test_validate_valid_paper(); test_validate_empty_title(); test_validate_author()
    test_validate_citation_edge(); test_validate_coauthorship_edge()
    print("All validate tests passed.")
