"""Tests for Skill 2 — Paper Ranker."""

from pathlib import Path

import pytest

from skills.paper_ranker.rank import (
    rank_papers,
    compute_pagerank,
    compute_interest_scores,
    compute_novelty_scores,
    combine_scores,
    save_rankings,
    save_ranked_papers,
    _generate_ranking_reason,
)
from skills.paper_ranker._io import load_papers, load_citation_graph, load_embeddings, load_raw_papers

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_load_fixtures():
    papers = load_papers(data_dir=FIXTURES)
    assert len(papers) == 3
    assert "2301.00001" in papers


def test_load_citation_graph():
    g = load_citation_graph(data_dir=FIXTURES)
    assert g.number_of_nodes() > 0
    assert g.has_edge("2301.00001", "2301.00003")


def test_load_embeddings():
    vecs, index = load_embeddings(data_dir=FIXTURES)
    assert vecs.shape == (3, 384)
    assert len(index) == 3


def test_pagerank():
    papers = load_papers(data_dir=FIXTURES)
    g = load_citation_graph(data_dir=FIXTURES)
    scores = compute_pagerank(g, papers)
    assert len(scores) == 3
    # 2301.00003 is cited by 2 papers → should have highest PageRank
    assert scores["2301.00003"] >= scores["2301.00001"]
    assert scores["2301.00003"] >= scores["2301.00002"]


def test_novelty():
    papers = load_papers(data_dir=FIXTURES)
    g = load_citation_graph(data_dir=FIXTURES)
    scores = compute_novelty_scores(papers, g)
    assert len(scores) == 3
    # Lower citation_count → higher novelty
    assert scores["2301.00003"] > scores["2301.00001"]


def test_combine_scores():
    papers = load_papers(data_dir=FIXTURES)
    pr = {"2301.00001": 0.1, "2301.00002": 0.2, "2301.00003": 0.7}
    interest = {"2301.00001": 8.0, "2301.00002": 5.0, "2301.00003": 3.0}
    novelty = {"2301.00001": 3.0, "2301.00002": 5.0, "2301.00003": 8.0}
    rankings = combine_scores(papers, pr, interest, novelty, alpha=0.4, beta=0.6)
    assert len(rankings) == 3
    assert rankings[0]["rank"] == 1
    assert all("arxiv_id" in r for r in rankings)
    assert all("score" in r for r in rankings)


def test_full_pipeline():
    rankings = rank_papers(
        user_interest="graph neural networks social network",
        data_dir=FIXTURES,
    )
    assert len(rankings) == 3
    assert rankings[0]["rank"] == 1
    # Paper 2301.00002 is about GNN + social networks — should rank high
    # Paper 2301.00003 has highest PageRank but low interest match
    # Exactly which paper is #1 depends on embedding similarity, but all 3 ranked

    for r in rankings:
        assert "pagerank_score" in r
        assert "interest_score" in r
        assert "novelty_score" in r
        assert "relevance_score" in r
        assert "score" in r
        assert "rank" in r
        assert 1 <= r["rank"] <= 3


def test_empty_interest():
    rankings = rank_papers(user_interest="", data_dir=FIXTURES)
    assert len(rankings) == 3
    assert all(r["interest_score"] == 0.0 for r in rankings)


def test_generate_ranking_reason():
    item = {"pagerank_score": 0.5, "interest_score": 8.5, "novelty_score": 6.5}
    reason = _generate_ranking_reason(item, max_pr=0.5)
    assert isinstance(reason, str)
    assert len(reason) > 10
    assert "Above-average" in reason or "Top" in reason
    assert "strong interest" in reason


def test_generate_ranking_reason_low_scores():
    item = {"pagerank_score": 0.01, "interest_score": 0.0, "novelty_score": 0.5}
    reason = _generate_ranking_reason(item, max_pr=0.5)
    assert "Low" in reason
    assert "no interest" in reason


def test_save_ranked_papers():
    rankings = rank_papers(
        user_interest="graph neural networks", data_dir=FIXTURES,
    )
    out_dir = FIXTURES
    path = save_ranked_papers(rankings, data_dir=out_dir)

    import json
    with open(path) as f:
        data = json.load(f)

    assert len(data) == 3
    for entry in data:
        assert "relevance_score" in entry
        assert "novelty_score" in entry
        assert "ranking_reason" in entry
        assert isinstance(entry["ranking_reason"], str)

    # When raw_papers.json exists, extra fields should be added to existing fields
    assert "title" in data[0]
    assert "arxiv_id" in data[0]


def test_save_both_outputs():
    rankings = rank_papers(
        user_interest="graph neural networks", data_dir=FIXTURES,
    )
    p1 = save_rankings(rankings, data_dir=FIXTURES)
    p2 = save_ranked_papers(rankings, data_dir=FIXTURES)

    assert p1.exists()
    assert p2.exists()
    assert p1.name == "rankings.json"
    assert p2.name == "ranked_papers.json"
