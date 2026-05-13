"""Build semantic similarity edges from pre-computed paper embeddings.

Replaces the citation graph stage. Instead of "paper A cites B", builds:
    "paper A is semantically similar to B"

Output: edges/similarity.json
    [{"source": "arxiv_id", "target": "arxiv_id", "weight": 0.78}, ...]

Each paper connects to its top-K most similar peers (cosine similarity on
title+abstract embeddings from embed.py).

Usage:
    python -m skills.data_collector.scripts.build_similarity_graph --shared-data /path/to/shared_data
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np


def build_similarity_graph(papers_index, embeddings, top_k=5, threshold=0.2):
    """Build edges/similarity.json from paper embeddings.

    Args:
        papers_index: {arxiv_id: paper_dict}
        embeddings: (vecs_ndarray, index_dict) from load_embeddings
        top_k: max neighbours per paper
        threshold: minimum cosine similarity to include edge

    Returns:
        list of {"source": str, "target": str, "weight": float}
    """
    vecs, emb_index = embeddings
    if vecs.size == 0 or len(emb_index) < 2:
        return []

    idx_to_aid = {v: k for k, v in emb_index.items()}

    # L2-normalize for cosine similarity
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    norms[norms == 0] = 1
    normalized = vecs / norms

    sim_matrix = np.dot(normalized, normalized.T)
    np.fill_diagonal(sim_matrix, 0)

    n = len(emb_index)
    edges = []
    seen = set()

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
                # Deduplicate (A→B and B→A)
                key = tuple(sorted([aid, other]))
                if key in seen:
                    continue
                seen.add(key)
                edges.append({
                    "from": aid,       # compatible with load_citation_graph / validate_citation_edges
                    "to": other,
                    "weight": round(float(sim_matrix[i, j]), 4),
                })

    return edges


# ---------------------------------------------------------------------------
# I/O helpers (duplicated from _io.py to keep this script self-contained)
# ---------------------------------------------------------------------------

def _find_shared_data(shared_data_arg=None):
    if shared_data_arg:
        p = Path(shared_data_arg)
        if p.name != "shared_data" and (p / "shared_data").is_dir():
            p = p / "shared_data"
        return p
    import os
    env = os.environ.get("WORKBUDDY_SHARED_DATA")
    if env:
        return Path(env)
    # Walk up from this file
    current = Path(__file__).resolve()
    # ~/.workbuddy/skills/data_collector/scripts/build_similarity_graph.py
    # → ~/.workbuddy/
    root = current.parents[3]
    return root / "shared_data"


def _resolve(path, data_dir=None):
    base = data_dir or _find_shared_data()
    return base / path


def load_embeddings(data_dir=None):
    vecs_path = _resolve("embeddings/paper_vecs.npy", data_dir)
    index_path = _resolve("embeddings/index.json", data_dir)
    with open(index_path, encoding="utf-8") as f:
        index = json.load(f)
    return np.load(vecs_path), index


def load_papers(data_dir=None):
    with open(_resolve("papers.json", data_dir), encoding="utf-8") as f:
        return {p["arxiv_id"]: p for p in json.load(f) if "arxiv_id" in p}


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Build semantic similarity edges from embeddings")
    parser.add_argument(
        "--shared-data",
        default=None,
        dest="shared_data",
        help="shared_data/ directory (or workspace root containing it)",
    )
    parser.add_argument(
        "--top-k", type=int, default=5,
        help="Max similar neighbours per paper (default 5)",
    )
    parser.add_argument(
        "--threshold", type=float, default=0.2,
        help="Minimum cosine similarity to include edge (default 0.2)",
    )
    args = parser.parse_args()

    data_dir = _find_shared_data(args.shared_data)
    print(f"[build_similarity_graph] data_dir: {data_dir}")

    papers_index = load_papers(data_dir)
    embeddings = load_embeddings(data_dir)
    print(f"[build_similarity_graph] {len(papers_index)} papers, vecs shape: {embeddings[0].shape}")

    edges = build_similarity_graph(papers_index, embeddings, top_k=args.top_k, threshold=args.threshold)
    print(f"[build_similarity_graph] {len(edges)} similarity edges built")

    out_path = _resolve("edges/similarity.json", data_dir)
    save_json(out_path, edges)
    print(f"[build_similarity_graph] Saved: {out_path}")


if __name__ == "__main__":
    sys.exit(main())
