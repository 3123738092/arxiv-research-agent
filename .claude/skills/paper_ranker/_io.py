"""Self-contained I/O for paper_ranker — reads shared_data/ artifacts.

No cross-skill imports. Each skill owns its data loading.
"""
import json
import os
from pathlib import Path
from typing import Dict, Tuple

import numpy as np

_FILE = Path(__file__).resolve()


def _find_shared_data():
    """Walk up from this file to find the nearest shared_data/ directory.

    Priority order:
      1. WORKBUDDY_SHARED_DATA env var
      2. Walk up from this file until shared_data/ is found
      3. Fallback to <repo-root>/shared_data/
    """
    env = os.environ.get("WORKBUDDY_SHARED_DATA")
    if env:
        return Path(env)

    # Walk up from the file's location
    current = _FILE.parent
    for _ in range(10):
        candidate = current / "shared_data"
        if candidate.is_dir():
            return candidate
        if current.parent == current:
            break
        current = current.parent

    # Last resort
    return _FILE.parents[3] / "shared_data"


SHARED_DATA = _find_shared_data()


class SkillInputMissingError(FileNotFoundError):
    """Required data file not found — has the upstream stage run?"""


def _resolve(path: str, data_dir=None) -> Path:
    base = Path(data_dir) if data_dir else SHARED_DATA
    # If data_dir is a workspace root (contains shared_data/ subdir), use that instead
    if data_dir:
        candidate = Path(data_dir)
        if candidate.name != "shared_data" and (candidate / "shared_data").is_dir():
            base = candidate / "shared_data"
    return base / path


def _load_json(path: str, data_dir=None):
    full = _resolve(path, data_dir)
    if not full.exists():
        raise SkillInputMissingError(
            f"{full.name} not found — expected at {full}"
        )
    with open(full, encoding="utf-8") as f:
        return json.load(f)


def load_papers(data_dir=None) -> Dict[str, dict]:
    papers_list = _load_json("papers.json", data_dir)
    return {p["arxiv_id"]: p for p in papers_list if "arxiv_id" in p}


def load_citation_graph(data_dir=None):
    """Load the semantic similarity graph from shared_data/edges/similarity.json.

    Each edge {from, to, weight} represents a top-K cosine neighbor pair from
    MiniLM embeddings (threshold=0.2). Returns an empty DiGraph if the file
    is missing or empty.
    """
    import networkx as nx

    sim_path = _resolve("edges/similarity.json", data_dir)
    if sim_path.exists():
        edges = _load_json("edges/similarity.json", data_dir)
        if edges:
            g = nx.DiGraph()
            for edge in edges:
                g.add_edge(edge["from"], edge["to"], weight=edge.get("weight", 1.0))
            return g

    return nx.DiGraph()


def load_embeddings(data_dir=None) -> Tuple[np.ndarray, dict]:
    vecs_path = _resolve("embeddings/paper_vecs.npy", data_dir)
    index_path = _resolve("embeddings/index.json", data_dir)
    if not vecs_path.exists():
        raise SkillInputMissingError(
            "paper_vecs.npy not found — embedding stage run?"
        )
    with open(index_path, encoding="utf-8") as f:
        index = json.load(f)
    return np.load(vecs_path), index


def load_raw_papers(data_dir=None) -> list:
    return _load_json("raw_papers.json", data_dir)
