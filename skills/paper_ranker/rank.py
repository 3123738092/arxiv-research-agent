"""Skill 2: Paper Ranker — PageRank + interest-based scoring.

Produces rankings.json from shared_data/ with pagerank_score, interest_score,
novelty_score, relevance_score, and overall rank for each paper.

Usage:
    python -m skills.paper_ranker.rank --interest "large language model agents"
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

from ._io import (
    load_papers, load_citation_graph, load_embeddings, load_raw_papers,
    SkillInputMissingError, SHARED_DATA,
)

DEFAULT_ALPHA = 0.4  # weight for PageRank
DEFAULT_BETA = 0.6   # weight for interest (novelty = 1 - alpha - beta)
MODEL_NAME = "all-MiniLM-L6-v2"


def _get_data_dir(data_dir=None):
    if data_dir:
        return Path(data_dir)
    return SHARED_DATA


# ---------------------------------------------------------------------------
# PageRank with embedding similarity fallback for fresh papers
# ---------------------------------------------------------------------------

def _build_similarity_graph(papers_index, embeddings, top_k=5, threshold=0.2):
    """Build a topic-proximity graph from paper embeddings.

    Used as fallback when citation graph is empty (same-day fresh papers).
    Each paper connects to its top-k most semantically similar peers.

    Returns:
        networkx.Graph or None if embeddings are unavailable.
    """
    import networkx as nx

    vecs, emb_index = embeddings
    if vecs.size == 0 or len(emb_index) < 2:
        return None

    idx_to_aid = {v: k for k, v in emb_index.items()}

    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    norms[norms == 0] = 1
    normalized = vecs / norms

    sim_matrix = np.dot(normalized, normalized.T)
    np.fill_diagonal(sim_matrix, 0)

    n = len(emb_index)
    g = nx.Graph()
    for aid in papers_index:
        g.add_node(aid)

    added = 0
    for i in range(n):
        aid = idx_to_aid.get(i)
        if aid not in papers_index:
            continue
        neighbors = np.argsort(sim_matrix[i])[::-1][:top_k]
        for j in neighbors:
            if sim_matrix[i, j] <= threshold:
                continue
            other = idx_to_aid.get(j)
            if other and other in papers_index and other != aid:
                g.add_edge(aid, other, weight=round(float(sim_matrix[i, j]), 4))
                added += 1

    if added == 0:
        return None
    return g


def compute_pagerank(citation_graph, papers_index, embeddings=None):
    """Run PageRank on the citation graph.

    When the citation graph has no edges (same-day fresh papers not yet
    indexed by Semantic Scholar), falls back to an embedding similarity
    graph — a valid SNA proxy that identifies topically central papers.

    Edges point from citing paper → cited paper (real citations) so highly
    cited papers receive high PageRank.

    Returns:
        {arxiv_id: pagerank_score} raw PageRank values.
    """
    import networkx as nx

    has_edges = citation_graph.number_of_edges() > 0

    if not has_edges:
        sim_graph = _build_similarity_graph(papers_index, embeddings)
        if sim_graph is not None:
            citation_graph = sim_graph

    if citation_graph.number_of_nodes() == 0:
        return {aid: 0.0 for aid in papers_index}

    try:
        pr = nx.pagerank(citation_graph, alpha=0.85, max_iter=100, tol=1e-6)
    except nx.PowerIterationFailedConvergence:
        pr = nx.pagerank(citation_graph, alpha=0.85, max_iter=200, tol=1e-5)

    return {aid: pr.get(aid, 0.0) for aid in papers_index}


# ---------------------------------------------------------------------------
# Embedding model (lazy, with Windows pwd stub)
# ---------------------------------------------------------------------------

_embed_model = None


def _load_embed_model():
    global _embed_model
    if _embed_model is not None:
        return _embed_model

    if sys.platform == "win32" and "pwd" not in sys.modules:
        import types
        _pwd = types.ModuleType("pwd")

        class _Passwd:
            def __init__(self):
                self.pw_name = "unknown"
                self.pw_passwd = "*"
                self.pw_uid = 0
                self.pw_gid = 0
                self.pw_gecos = ""
                self.pw_dir = "/"
                self.pw_shell = ""

        _pwd.getpwuid = lambda uid=0: _Passwd()
        _pwd.getpwnam = lambda name="": _Passwd()
        _pwd.getpwall = lambda: []
        _pwd.struct_passwd = _Passwd
        sys.modules["pwd"] = _pwd

    try:
        from sentence_transformers import SentenceTransformer
        _embed_model = SentenceTransformer(MODEL_NAME)
    except Exception as _e:
        print(f"[paper_ranker] sentence-transformers unavailable: {_e}", file=sys.stderr)
        _embed_model = None
    return _embed_model


def embed_text(text):
    model = _load_embed_model()
    if model is None:
        return None
    return model.encode(
        [text], show_progress_bar=False, convert_to_numpy=True
    )[0].astype(np.float32)


# ---------------------------------------------------------------------------
# Interest scoring
# ---------------------------------------------------------------------------

def compute_interest_scores(papers_index, embeddings, user_interest_text):
    """Cosine similarity between user interest embedding and each paper.

    Returns:
        {arxiv_id: interest_score} 0–10 range.
        Empty dict if embeddings or interest text are unavailable.
    """
    vecs, emb_index = embeddings

    if vecs.size == 0 or not user_interest_text:
        return {}

    user_vec = embed_text(user_interest_text)
    if user_vec is None:
        return {}

    dot = np.dot(vecs, user_vec)
    norm_vecs = np.linalg.norm(vecs, axis=1)
    norm_user = np.linalg.norm(user_vec)
    denom = norm_vecs * norm_user
    denom[denom == 0] = 1e-8
    similarities = np.clip(dot / denom, 0, 1)

    result = {}
    for aid, row_idx in emb_index.items():
        if aid in papers_index and row_idx < len(similarities):
            result[aid] = round(float(similarities[row_idx] * 10), 2)
    return result


# ---------------------------------------------------------------------------
# Novelty scoring (with embedding-diversity fallback)
# ---------------------------------------------------------------------------

def _embedding_centroid_distances(embeddings):
    """Compute 1 - cosine_similarity between each paper embedding and centroid.

    Papers far from the embedding centroid are considered more novel
    (outlier / divergent research directions).

    Returns:
        {arxiv_id: distance_0to1} or empty dict.
    """
    vecs, emb_index = embeddings
    if vecs.size == 0:
        return {}

    centroid = np.mean(vecs, axis=0)
    c_norm = np.linalg.norm(centroid)
    if c_norm == 0:
        return {}

    norms = np.linalg.norm(vecs, axis=1)
    norms[norms == 0] = 1
    sims = np.dot(vecs, centroid) / (norms * c_norm + 1e-8)
    sims = np.clip(sims, 0, 1)

    return {
        aid: round(float(1.0 - sims[row]), 4)
        for aid, row in emb_index.items()
        if row < len(sims)
    }


def compute_novelty_scores(papers_index, citation_graph, embeddings=None):
    """Inverse citation impact — less-cited papers are more novel.

    When citation_count is null (S2 hasn't indexed fresh papers), falls
    back to embedding distance from centroid — papers with unusual topics
    score higher for novelty.

    Returns:
        {arxiv_id: novelty_score} 0–10.
    """
    centroid_dists = _embedding_centroid_distances(embeddings) if embeddings else {}

    result = {}
    for aid, paper in papers_index.items():
        cc = paper.get("citation_count")
        if cc is None:
            if aid in centroid_dists:
                novelty = centroid_dists[aid] * 10
            else:
                novelty = 5.0
        else:
            out_deg = citation_graph.out_degree(aid) if citation_graph.has_node(aid) else 0
            novelty = (10.0 / (1 + cc * 0.1)) + min(out_deg * 0.5, 3)
        result[aid] = round(min(novelty, 10.0), 2)
    return result


# ---------------------------------------------------------------------------
# Score combination
# ---------------------------------------------------------------------------

def combine_scores(papers_index, pagerank_scores, interest_scores,
                   novelty_scores, alpha=DEFAULT_ALPHA, beta=DEFAULT_BETA):
    """Combine PageRank, interest, and novelty into final ranking list.

    relevance_score = alpha * pagerank_norm + beta * interest
    final_score = relevance_score + gamma * novelty   (gamma = 1-alpha-beta)
    """
    gamma = 1.0 - alpha - beta  # weight for novelty

    max_pr = max(pagerank_scores.values()) if pagerank_scores else 0.0
    if max_pr == 0:
        max_pr = 1.0

    rankings = []
    for aid, paper in papers_index.items():
        pr_norm = (pagerank_scores.get(aid, 0.0) / max_pr * 10) if max_pr > 0 else 0.0
        interest = interest_scores.get(aid, 0.0)
        novelty = novelty_scores.get(aid, 0.0)
        relevance = alpha * pr_norm + beta * interest
        final = relevance + gamma * novelty

        rankings.append({
            "arxiv_id": aid,
            "title": paper.get("title", ""),
            "pagerank_score": pagerank_scores.get(aid, 0.0),
            "interest_score": interest,
            "novelty_score": novelty,
            "relevance_score": round(relevance, 2),
            "score": round(final, 2),
        })

    rankings.sort(key=lambda r: r["score"], reverse=True)
    for i, r in enumerate(rankings):
        r["rank"] = i + 1

    return rankings


def _generate_ranking_reason(item, max_pr):
    """Generate a human-readable ranking explanation for a paper.

    Args:
        item: a single ranking dict from combine_scores output.
        max_pr: maximum pagerank_score across all papers (for normalization).

    Returns:
        str like "Top network centrality; strong interest match; moderate novelty."
    """
    parts = []
    pr = item["pagerank_score"]
    interest = item["interest_score"]
    novelty = item["novelty_score"]

    if max_pr > 0:
        pr_ratio = pr / max_pr
        if pr_ratio > 0.8:
            parts.append("Top network centrality in today's batch")
        elif pr_ratio > 0.5:
            parts.append("Above-average network centrality")
        elif pr_ratio > 0.2:
            parts.append("Moderate network centrality")
        else:
            parts.append("Low network centrality")

    if interest >= 7:
        parts.append("strong interest match")
    elif interest >= 4:
        parts.append("moderate interest match")
    elif interest > 0:
        parts.append("weak interest match")
    else:
        parts.append("no interest data")

    if novelty >= 7:
        parts.append("high novelty (divergent topic)")
    elif novelty >= 4:
        parts.append("moderate novelty")
    else:
        parts.append("low novelty (mainstream topic)")

    return "; ".join(parts) + "."


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def rank_papers(user_interest="", data_dir=None, alpha=None, beta=None):
    """Compute all scores and return ranked list.

    Args:
        user_interest: user research interest text.
        data_dir: override shared_data path (for fixture testing).
        alpha: PageRank weight (default 0.4).
        beta: interest weight (default 0.6).
    """
    data_dir = _get_data_dir(data_dir)
    alpha = alpha if alpha is not None else DEFAULT_ALPHA
    beta = beta if beta is not None else DEFAULT_BETA

    papers_index = load_papers(data_dir=data_dir)
    citation_graph = load_citation_graph(data_dir=data_dir)

    try:
        embeddings = load_embeddings(data_dir=data_dir)
    except SkillInputMissingError:
        embeddings = (np.empty((0, 384), dtype=np.float32), {})

    pagerank_scores = compute_pagerank(citation_graph, papers_index, embeddings)
    interest_scores = compute_interest_scores(
        papers_index, embeddings, user_interest
    )
    novelty_scores = compute_novelty_scores(papers_index, citation_graph, embeddings)

    rankings = combine_scores(
        papers_index, pagerank_scores, interest_scores, novelty_scores,
        alpha=alpha, beta=beta,
    )
    return rankings


def save_rankings(rankings, data_dir=None):
    """Write rankings to shared_data/rankings.json."""
    data_dir = _get_data_dir(data_dir)
    output_path = data_dir / "rankings.json"

    clean = []
    for r in rankings:
        item = dict(r)
        item["pagerank_score"] = round(item["pagerank_score"], 6)
        clean.append(item)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(clean, f, ensure_ascii=False, indent=2)
    return output_path


def save_ranked_papers(rankings, data_dir=None):
    """Write ranked_papers.json — full paper list augmented with scores.

    Extends raw_papers.json per data contract with:
      relevance_score, novelty_score, ranking_reason

    Falls back to building from papers.json if raw_papers.json is absent.
    """
    data_dir = _get_data_dir(data_dir)

    ranking_index = {r["arxiv_id"]: r for r in rankings}
    max_pr = max(r["pagerank_score"] for r in rankings) if rankings else 0.0

    try:
        raw = load_raw_papers(data_dir=data_dir)
    except SkillInputMissingError:
        raw = []

    if raw:
        augmented = []
        for paper in raw:
            aid = paper.get("arxiv_id", "")
            item = ranking_index.get(aid)
            if item:
                paper["relevance_score"] = item["relevance_score"]
                paper["novelty_score"] = item["novelty_score"]
                paper["ranking_reason"] = _generate_ranking_reason(item, max_pr)
            augmented.append(paper)
        output_list = augmented
    else:
        output_list = []
        for r in rankings:
            entry = dict(r)
            entry["ranking_reason"] = _generate_ranking_reason(r, max_pr)
            output_list.append(entry)

    output_path = data_dir / "ranked_papers.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output_list, f, ensure_ascii=False, indent=2)
    return output_path


def run(user_interest="", data_dir=None, alpha=None, beta=None):
    """Full pipeline: rank → save → print summary."""
    rankings = rank_papers(
        user_interest=user_interest, data_dir=data_dir,
        alpha=alpha, beta=beta,
    )
    path1 = save_rankings(rankings, data_dir=data_dir)
    path2 = save_ranked_papers(rankings, data_dir=data_dir)

    print(f"[Skill 2] Ranked {len(rankings)} papers")
    print(f"  summary   → {path1}")
    print(f"  augmented → {path2}")
    print("\nTop papers:")
    for r in rankings[:5]:
        title = r.get("title", "")[:80]
        print(
            f"  #{r['rank']:2d} | PR={r['pagerank_score']:.6f} "
            f"interest={r['interest_score']:.1f} "
            f"novelty={r['novelty_score']:.1f} "
            f"→ {r['score']:.1f} | {title}"
        )

    return rankings


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Paper Ranker Skill (Skill 2)")
    parser.add_argument(
        "--interest", type=str, default="",
        help="User research interest text for embedding similarity"
    )
    parser.add_argument(
        "--data-dir", type=str, default=None,
        help="Override shared_data directory (for fixture testing)"
    )
    parser.add_argument(
        "--alpha", type=float, default=None,
        help="Weight for PageRank component (default 0.4)"
    )
    parser.add_argument(
        "--beta", type=float, default=None,
        help="Weight for interest component (default 0.6)"
    )
    args = parser.parse_args()

    try:
        rankings = run(
            user_interest=args.interest,
            data_dir=args.data_dir,
            alpha=args.alpha,
            beta=args.beta,
        )
    except SkillInputMissingError as e:
        print(f"[Skill 2] ERROR: {e}")
        return 1

    return 0 if rankings else 1


if __name__ == "__main__":
    sys.exit(main())
