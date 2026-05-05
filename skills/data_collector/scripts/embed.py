"""Stage 6: Pre-compute text embeddings for all papers.

Uses sentence-transformers (all-MiniLM-L6-v2, 384-dim) running locally.
Outputs binary .npy for fast loading by downstream Skills.
"""

import numpy as np
from pathlib import Path
from .utils import SHARED_DATA

EMBED_DIR = SHARED_DATA / "embeddings"
VECS_FILE = EMBED_DIR / "paper_vecs.npy"
INDEX_FILE = EMBED_DIR / "index.json"

MODEL_NAME = "all-MiniLM-L6-v2"


def load_model():
    """Lazy-load the sentence-transformers model."""
    try:
        from sentence_transformers import SentenceTransformer
        return SentenceTransformer(MODEL_NAME)
    except ImportError:
        raise ImportError(
            "sentence-transformers not installed. Run: pip install sentence-transformers"
        )


def compute_embeddings(papers, model=None):
    """Compute embeddings for a list of paper dicts.

    Returns:
        (vecs_np, index_dict) where vecs_np shape (N, 384), index_dict maps arxiv_id -> row
    """
    if not papers:
        return np.empty((0, 384), dtype=np.float32), {}

    if model is None:
        model = load_model()

    texts = [f"{p.get('title', '')} {p.get('abstract', '')}" for p in papers]
    embeddings = model.encode(texts, show_progress_bar=False, convert_to_numpy=True)

    index = {}
    for i, p in enumerate(papers):
        aid = p.get("arxiv_id", "")
        index[aid] = i
        p["embedding_row"] = i

    return embeddings.astype(np.float32), index


def save_embeddings(vecs, index):
    """Save embeddings and index to disk."""
    EMBED_DIR.mkdir(parents=True, exist_ok=True)
    np.save(VECS_FILE, vecs)
    from .utils import save_json
    save_json(INDEX_FILE, index)


def embed_papers(papers):
    """Main entry point: compute and save embeddings for papers.

    Returns:
        (vecs, index, warnings)
    """
    warnings = []
    try:
        model = load_model()
        vecs, index = compute_embeddings(papers, model)
        save_embeddings(vecs, index)
        return vecs, index, warnings
    except ImportError as e:
        warnings.append(f"Embedding skipped: {e}")
        return np.empty((0, 384), dtype=np.float32), {}, warnings
    except Exception as e:
        warnings.append(f"Embedding error: {e}")
        return np.empty((0, 384), dtype=np.float32), {}, warnings
