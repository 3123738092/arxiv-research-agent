"""Shared data loader — the neutral contract layer between all Skills.

Lives in shared/ (code) and reads from shared_data/ (runtime artifacts).
All downstream Skills (Skill 2-5) import from here. This file does no business
logic — only file I/O, schema validation, and type conversion.

Supports data_dir parameter for fixture-based testing so each skill can be
developed and tested independently.

Usage:
    from shared.loader import load_papers, load_embeddings
    papers = load_papers()  # reads shared_data/papers.json
    papers = load_papers(data_dir=Path("tests/fixtures"))  # for testing
"""

import json
from pathlib import Path
from typing import Dict, List, Tuple, Optional

import numpy as np

DATA_DIR = Path(__file__).resolve().parent.parent / "shared_data"


class SkillInputMissingError(FileNotFoundError):
    """Raised when a required data file is missing (e.g., Skill 1 hasn't run yet)."""


class SchemaValidationError(ValueError):
    """Raised when a data file fails JSON Schema validation."""


# --------------------------------------------------------------------------
# Low-level helpers
# --------------------------------------------------------------------------

def _resolve(path: str, data_dir: Optional[Path] = None) -> Path:
    base = data_dir or DATA_DIR
    return base / path


def _load_json(path: str, data_dir: Optional[Path] = None) -> dict | list:
    full = _resolve(path, data_dir)
    if not full.exists():
        raise SkillInputMissingError(
            f"{full.name} not found — has Skill 1 (data-collector) run? "
            f"Expected at {full}"
        )
    with open(full, encoding="utf-8") as f:
        return json.load(f)


def _load_json_optional(path: str, data_dir: Optional[Path] = None):
    """Load a JSON file, return None if it doesn't exist."""
    full = _resolve(path, data_dir)
    if not full.exists():
        return None
    with open(full, encoding="utf-8") as f:
        return json.load(f)


# --------------------------------------------------------------------------
# Manifest
# --------------------------------------------------------------------------

def load_manifest(data_dir: Optional[Path] = None) -> dict:
    """Return the latest pipeline run manifest."""
    return _load_json("manifest.json", data_dir)


# --------------------------------------------------------------------------
# Papers (fact table)
# --------------------------------------------------------------------------

def load_papers(data_dir: Optional[Path] = None) -> Dict[str, dict]:
    """Return papers indexed by arxiv_id: {arxiv_id: paper_dict}.

    This is the primary accessor for papers — keyed lookup by ID.
    """
    papers_list = _load_json("papers.json", data_dir)
    if isinstance(papers_list, list):
        return {p["arxiv_id"]: p for p in papers_list if "arxiv_id" in p}
    return {}


def load_papers_list(data_dir: Optional[Path] = None) -> list:
    """Return papers as a plain list of dicts (the raw JSON array)."""
    return _load_json("papers.json", data_dir)


# --------------------------------------------------------------------------
# Authors (dimension table)
# --------------------------------------------------------------------------

def load_authors(data_dir: Optional[Path] = None) -> list:
    """Return the authors dimension table as a list of dicts."""
    return _load_json("authors.json", data_dir)


def load_authors_index(data_dir: Optional[Path] = None) -> Dict[str, dict]:
    """Return authors indexed by author_id: {author_id: author_dict}."""
    authors_list = _load_json("authors.json", data_dir)
    if isinstance(authors_list, list):
        return {a["author_id"]: a for a in authors_list if "author_id" in a}
    return {}


# --------------------------------------------------------------------------
# Affiliations (dimension table)
# --------------------------------------------------------------------------

def load_affiliations(data_dir: Optional[Path] = None) -> list:
    """Return the affiliations dimension table."""
    return _load_json("affiliations.json", data_dir)


# --------------------------------------------------------------------------
# Edge tables
# --------------------------------------------------------------------------

def load_citation_edges(data_dir: Optional[Path] = None) -> list:
    """Return citation edges: [{from, to}, ...]."""
    return _load_json("edges/citations.json", data_dir)


def load_coauthorship_edges(data_dir: Optional[Path] = None) -> list:
    """Return coauthorship edges: [{author_a, author_b, weight}, ...]."""
    return _load_json("edges/coauthorship.json", data_dir)


def load_author_paper_edges(data_dir: Optional[Path] = None) -> list:
    """Return author-paper bipartite edges: [{author_id, paper_id}, ...]."""
    return _load_json("edges/author_paper.json", data_dir)


def load_citation_edges_external(data_dir: Optional[Path] = None) -> list:
    """Return external citation edges if available, else empty list."""
    return _load_json_optional("edges/citations_external.json", data_dir) or []


# --------------------------------------------------------------------------
# NetworkX graph builders (loaded lazily)
# --------------------------------------------------------------------------

def load_citation_graph(data_dir: Optional[Path] = None) -> "nx.DiGraph":
    """Return a directed NetworkX citation graph (paper -> paper)."""
    import networkx as nx
    g = nx.DiGraph()
    for edge in load_citation_edges(data_dir):
        g.add_edge(edge["from"], edge["to"])
    return g


def load_coauthor_graph(data_dir: Optional[Path] = None) -> "nx.Graph":
    """Return a weighted co-authorship graph."""
    import networkx as nx
    g = nx.Graph()
    for edge in load_coauthorship_edges(data_dir):
        g.add_edge(edge["author_a"], edge["author_b"], weight=edge.get("weight", 1))
    return g


def load_author_paper_graph(data_dir: Optional[Path] = None) -> "nx.Graph":
    """Return a bipartite author-paper graph."""
    import networkx as nx
    g = nx.Graph()
    for edge in load_author_paper_edges(data_dir):
        g.add_edge(edge["author_id"], edge["paper_id"])
    return g


# --------------------------------------------------------------------------
# Embeddings
# --------------------------------------------------------------------------

def load_embeddings(data_dir: Optional[Path] = None) -> Tuple[np.ndarray, dict]:
    """Return (vectors_ndarray, index_dict).

    vectors: float32 ndarray of shape (N, 384)
    index:   {arxiv_id: row_number}
    """
    vecs_path = _resolve("embeddings/paper_vecs.npy", data_dir)
    index_path = _resolve("embeddings/index.json", data_dir)

    if not vecs_path.exists():
        raise SkillInputMissingError(
            f"paper_vecs.npy not found in {vecs_path.parent} — "
            "has the embedding stage run?"
        )
    if not index_path.exists():
        raise SkillInputMissingError(
            f"index.json not found in {index_path.parent}"
        )

    vecs = np.load(vecs_path)
    with open(index_path, encoding="utf-8") as f:
        index = json.load(f)
    return vecs, index


# --------------------------------------------------------------------------
# Raw papers (legacy)
# --------------------------------------------------------------------------

def load_raw_papers(data_dir: Optional[Path] = None) -> list:
    """Return the legacy raw_papers.json list."""
    return _load_json("raw_papers.json", data_dir)


# --------------------------------------------------------------------------
# State file
# --------------------------------------------------------------------------

def load_rankings(data_dir: Optional[Path] = None) -> Optional[list]:
    """Return Skill 2 rankings if present: [{arxiv_id, pagerank_score, interest_score, rank}, ...]."""
    return _load_json_optional("rankings.json", data_dir)


def load_communities(data_dir: Optional[Path] = None) -> Optional[list]:
    """Return Skill 3 communities if present: [{community_id, members, label, size}, ...]."""
    return _load_json_optional("communities.json", data_dir)


def load_last_fetch(data_dir: Optional[Path] = None) -> dict:
    """Return the last_fetch state: {seen_ids, last_fetch_time, params}."""
    result = _load_json_optional("last_fetch.json", data_dir)
    if result is None:
        return {"seen_ids": [], "last_fetch_time": None, "params": {}}
    return result


# --------------------------------------------------------------------------
# Convenience: load everything at once
# --------------------------------------------------------------------------

def load_all(data_dir: Optional[Path] = None) -> dict:
    """Return a dict with all data center contents.

    Keys: manifest, papers, authors, affiliations, edges, embeddings, raw_papers, last_fetch.
    """
    result = {}
    result["manifest"] = _load_json_optional("manifest.json", data_dir)

    papers = _load_json_optional("papers.json", data_dir) or []
    result["papers"] = papers
    result["papers_index"] = {p["arxiv_id"]: p for p in papers if "arxiv_id" in p}

    result["authors"] = _load_json_optional("authors.json", data_dir) or []
    result["affiliations"] = _load_json_optional("affiliations.json", data_dir) or []
    result["raw_papers"] = _load_json_optional("raw_papers.json", data_dir) or []
    result["last_fetch"] = _load_json_optional("last_fetch.json", data_dir)

    result["edges"] = {
        "citations": _load_json_optional("edges/citations.json", data_dir) or [],
        "coauthorship": _load_json_optional("edges/coauthorship.json", data_dir) or [],
        "author_paper": _load_json_optional("edges/author_paper.json", data_dir) or [],
    }

    try:
        result["embeddings"] = load_embeddings(data_dir)
    except SkillInputMissingError:
        result["embeddings"] = (np.array([]), {})

    return result


# --------------------------------------------------------------------------
# Cross-reference helpers
# --------------------------------------------------------------------------

def get_author_papers(author_id: str, data_dir: Optional[Path] = None) -> List[str]:
    """Return all paper IDs authored by a given author."""
    edges = load_author_paper_edges(data_dir)
    return [e["paper_id"] for e in edges if e["author_id"] == author_id]


def get_paper_authors(paper_id: str, data_dir: Optional[Path] = None) -> List[str]:
    """Return all author IDs for a given paper."""
    edges = load_author_paper_edges(data_dir)
    return [e["author_id"] for e in edges if e["paper_id"] == paper_id]


def get_cited_by(paper_id: str, data_dir: Optional[Path] = None) -> List[str]:
    """Return papers that cite the given paper (inbound citations)."""
    edges = load_citation_edges(data_dir)
    return [e["from"] for e in edges if e["to"] == paper_id]


def get_cites(paper_id: str, data_dir: Optional[Path] = None) -> List[str]:
    """Return papers cited by the given paper (outbound citations)."""
    edges = load_citation_edges(data_dir)
    return [e["to"] for e in edges if e["from"] == paper_id]
