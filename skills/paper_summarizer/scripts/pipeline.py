"""Agent-facing pipeline wrapper for the paper-summarizer Skill.

Mirrors the style of ``skills/data_collector/scripts/pipeline.py``: a thin
``run_pipeline(config)`` that the main agent can call without knowing the
internals of the summarizer package.

Reads input in priority order:
  1. ``shared_data/ranked_papers.json`` (ranker output).
  2. ``shared_data/papers.json`` (data_collector output) via ``shared.loader``.

Writes ``shared_data/summarized_papers.json`` (schema unchanged from the
standalone skill).
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional

from ..summarizer.config import SummarizerConfig
from ..summarizer.core import summarize

log = logging.getLogger(__name__)


def _shared_dir(cfg: SummarizerConfig) -> Path:
    return Path(cfg.shared_data_dir)


def resolve_input_papers(cfg: Optional[SummarizerConfig] = None) -> list[dict]:
    """Return the list of papers to summarize, using the documented fallback.

    Raises FileNotFoundError if neither ranked_papers.json nor papers.json
    can be located — callers should treat that as 'nothing to do'.
    """
    cfg = cfg or SummarizerConfig()
    shared = _shared_dir(cfg)

    ranked = shared / "ranked_papers.json"
    if ranked.is_file():
        with ranked.open(encoding="utf-8") as f:
            data = json.load(f)
        papers = data.get("papers", data if isinstance(data, list) else [])
        log.info("Using ranker output: %s (%d papers)", ranked, len(papers))
        return papers

    try:
        from shared.loader import SkillInputMissingError, load_papers_list
    except ImportError as e:
        raise FileNotFoundError(
            f"No ranked_papers.json at {ranked} and shared.loader is not "
            "importable — run inside arxiv-research-agent or pass --input."
        ) from e

    try:
        papers = load_papers_list(data_dir=shared)
    except SkillInputMissingError as e:
        raise FileNotFoundError(str(e)) from e

    log.info("Using data_collector output: %s/papers.json (%d papers)", shared, len(papers))
    return papers


def run_pipeline(
    config: Optional[dict] = None,
    cfg: Optional[SummarizerConfig] = None,
) -> dict:
    """Entry point for the main agent. Returns a small manifest dict.

    Args:
        config: optional dict with keys mapping to ``SummarizerConfig`` fields
            (``top_n``, ``mode``, ``language``, ``model``, ``enable_local_cache``,
            ``enable_prompt_cache``). Used only when ``cfg`` is None.
        cfg: fully-constructed SummarizerConfig. Takes precedence over ``config``.

    Returns:
        ``{"count", "summarized_count", "model", "mode", "language", "output_path"}``.
    """
    if cfg is None:
        cfg = SummarizerConfig()
        for k, v in (config or {}).items():
            if hasattr(cfg, k) and v is not None:
                setattr(cfg, k, v)

    papers = resolve_input_papers(cfg)
    result = summarize(papers, cfg=cfg)
    out_path = os.path.join(cfg.shared_data_dir, cfg.output_filename)
    summarized = sum(1 for p in result[: cfg.top_n] if p.get("one_line_summary"))

    manifest = {
        "count": len(result),
        "summarized_count": summarized,
        "model": cfg.model,
        "mode": cfg.mode,
        "language": cfg.language,
        "output_path": out_path,
    }
    log.info("Summarizer pipeline done: %s", manifest)
    return manifest


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    print(json.dumps(run_pipeline(), indent=2))
