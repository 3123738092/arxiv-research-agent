"""Self-contained I/O for paper_ranker — reads shared_data/ artifacts.

No cross-skill imports. Each skill owns its data loading.
"""
import json
from pathlib import Path
from typing import Dict, Tuple

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SHARED_DATA = PROJECT_ROOT / "shared_data"


class SkillInputMissingError(FileNotFoundError):
    """Required data file not found — has the upstream stage run?"""


def _resolve(path: str, data_dir=None) -> Path:
    base = Path(data_dir) if data_dir else SHARED_DATA
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
    import networkx as nx
    edges = _load_json("edges/citations.json", data_dir)
    g = nx.DiGraph()
    for edge in edges:
        g.add_edge(edge["from"], edge["to"])
    return g


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
