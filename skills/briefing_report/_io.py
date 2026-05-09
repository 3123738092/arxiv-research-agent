"""Self-contained I/O for briefing_report — reads shared_data/ artifacts.

No cross-skill imports. Each skill owns its data loading.
"""
import json
from pathlib import Path
from typing import Optional, Tuple

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


def _load_json_optional(path: str, data_dir=None):
    full = _resolve(path, data_dir)
    if not full.exists():
        return None
    with open(full, encoding="utf-8") as f:
        return json.load(f)


def load_manifest(data_dir=None) -> dict:
    return _load_json("manifest.json", data_dir)


def load_papers_list(data_dir=None) -> list:
    return _load_json("papers.json", data_dir)


def load_citation_edges(data_dir=None) -> list:
    return _load_json("edges/citations.json", data_dir)


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


def load_rankings(data_dir=None) -> Optional[list]:
    return _load_json_optional("rankings.json", data_dir)


def load_communities(data_dir=None) -> Optional[list]:
    return _load_json_optional("communities.json", data_dir)
