"""Stage 6: Pre-compute text embeddings for all papers.

Uses sentence-transformers (all-MiniLM-L6-v2, 384-dim) running locally.
Outputs binary .npy for fast loading by downstream Skills.
"""

import sys
import numpy as np
from pathlib import Path
from . import utils  # 引用式导入，运行时解析 SHARED_DATA

# Windows: torch._dynamo imports the Unix-only 'pwd' module.
# Inject a minimal stub so sentence-transformers can load on Windows.
if sys.platform == "win32" and "pwd" not in sys.modules:
    import types as _types
    _pwd = _types.ModuleType("pwd")

    class _Passwd:
        def __init__(self):
            self.pw_name = "unknown"
            self.pw_passwd = "*"
            self.pw_uid = 0
            self.pw_gid = 0
            self.pw_gecos = ""
            self.pw_dir = "/"
            self.pw_shell = ""

    def _getpwuid(uid=0):
        return _Passwd()

    def _getpwnam(name=""):
        return _Passwd()

    def _getpwall():
        return []

    _pwd.getpwuid = _getpwuid
    _pwd.getpwnam = _getpwnam
    _pwd.getpwall = _getpwall
    _pwd.struct_passwd = _Passwd
    sys.modules["pwd"] = _pwd

EMBED_DIR = utils.SHARED_DATA / "embeddings"
VECS_FILE = EMBED_DIR / "paper_vecs.npy"
INDEX_FILE = EMBED_DIR / "index.json"

MODEL_NAME = "all-MiniLM-L6-v2"

_EMBEDDING_AVAILABLE = None


def _check_embedding():
    """Lazy-check whether sentence-transformers can be imported."""
    global _EMBEDDING_AVAILABLE
    if _EMBEDDING_AVAILABLE is not None:
        return _EMBEDDING_AVAILABLE
    try:
        from sentence_transformers import SentenceTransformer  # noqa: F401
        _EMBEDDING_AVAILABLE = True
    except Exception as _e:
        print(f"[embed] sentence-transformers unavailable: {_e}", file=sys.stderr)
        _EMBEDDING_AVAILABLE = False
    return _EMBEDDING_AVAILABLE


def load_model():
    """Lazy-load the sentence-transformers model."""
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(MODEL_NAME)


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
    if not papers:
        warnings.append("Embedding skipped: no papers")
        return np.empty((0, 384), dtype=np.float32), {}, warnings

    if not _check_embedding():
        warnings.append("Embedding skipped: sentence-transformers unavailable")
        return np.empty((0, 384), dtype=np.float32), {}, warnings

    try:
        model = load_model()
        vecs, index = compute_embeddings(papers, model)
        save_embeddings(vecs, index)
        return vecs, index, warnings
    except Exception as e:
        name = type(e).__name__
        warnings.append(f"Embedding skipped [{name}]: {e}")
        return np.empty((0, 384), dtype=np.float32), {}, warnings
