"""Core summarize() function — ties prompts/client/schema/cache together.

Design goals:
- **Drop-in replacement** for the original `skills/paper_summarizer.py`:
  same ``summarize(papers, top_n=...)`` entry point, same output JSON shape.
- Resilient: JSON parse failures on one batch do not crash the whole run.
- Cheap on re-runs: per-paper disk cache keyed by arxiv_url.
- Cheap on first run: Anthropic prompt caching for the (large) system prompt.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Optional

from .cache import SummaryCache
from .client import SummarizerClient, extract_json_array
from .config import SummarizerConfig
from .prompts import build_user_prompt
from .schema import empty_summary, merge_into_paper, normalize_summary

log = logging.getLogger(__name__)


def _chunk(items: list, size: int):
    for i in range(0, len(items), size):
        yield i, items[i : i + size]


def _summarize_batch(
    client: SummarizerClient,
    batch: list[dict],
    cfg: SummarizerConfig,
) -> list[dict]:
    """Return a list parallel to `batch` containing normalized summary dicts."""
    prompt = build_user_prompt(batch, mode=cfg.mode)
    try:
        raw = client.complete(prompt)
    except Exception as e:
        log.error("Batch failed: %s — falling back to empty summaries.", e)
        return [empty_summary() for _ in batch]

    parsed = extract_json_array(raw)
    by_index = {}
    for obj in parsed:
        idx = obj.get("index")
        if isinstance(idx, int) and 0 <= idx < len(batch):
            by_index[idx] = normalize_summary(obj)

    return [by_index.get(i, empty_summary()) for i in range(len(batch))]


def summarize(
    papers: list[dict],
    top_n: Optional[int] = None,
    cfg: Optional[SummarizerConfig] = None,
    *,
    persist: bool = True,
) -> list[dict]:
    """Summarize the top-N ranked papers and persist the result.

    Args:
        papers: Ranked papers (output of Skill 2). Must contain at least
            ``title`` and ``abstract``; ideally ``arxiv_url``/``pdf_url``.
        top_n: Override cfg.top_n for this call.
        cfg: Runtime configuration. A sensible default is used if None.
        persist: Write ``shared_data/summarized_papers.json`` when True.

    Returns:
        The full list of papers (top-N first, then the rest). Top-N papers
        are augmented with ``one_line_summary``, ``key_contributions``,
        ``methods``, ``keywords``.
    """
    cfg = cfg or SummarizerConfig()
    if top_n is not None:
        cfg.top_n = top_n

    to_summarize = papers[: cfg.top_n]
    rest = papers[cfg.top_n :]

    # PDF mode: fetch full text before calling the LLM
    if cfg.mode == "pdf":
        from .pdf_loader import augment_with_full_text

        log.info("PDF mode: fetching full text for %d papers...", len(to_summarize))
        augment_with_full_text(
            to_summarize,
            max_chars=cfg.pdf_max_chars,
            timeout=cfg.pdf_timeout_sec,
        )

    cache = SummaryCache(cfg.cache_dir, enabled=cfg.enable_local_cache)

    # 1. Serve from local cache where possible
    cached_by_idx: dict[int, dict] = {}
    uncached: list[tuple[int, dict]] = []
    for i, p in enumerate(to_summarize):
        hit = cache.get(p, mode=cfg.mode, model=cfg.model, language=cfg.language)
        if hit is not None:
            cached_by_idx[i] = hit
        else:
            uncached.append((i, p))

    if cached_by_idx:
        log.info(
            "Cache: %d/%d papers served from disk.",
            len(cached_by_idx),
            len(to_summarize),
        )

    # 2. Call Claude on the rest, batched
    if uncached:
        client = SummarizerClient(cfg)
        for batch_start, chunk in _chunk([p for _, p in uncached], cfg.batch_size):
            indices = [uncached[batch_start + j][0] for j in range(len(chunk))]
            summaries = _summarize_batch(client, chunk, cfg)
            for local_i, global_i in enumerate(indices):
                s = summaries[local_i]
                cached_by_idx[global_i] = s
                cache.put(
                    to_summarize[global_i],
                    mode=cfg.mode,
                    model=cfg.model,
                    language=cfg.language,
                    summary=s,
                )

    # 3. Merge back onto paper dicts
    for i, paper in enumerate(to_summarize):
        merge_into_paper(paper, cached_by_idx.get(i, empty_summary()))

    result = to_summarize + rest

    if persist:
        os.makedirs(cfg.shared_data_dir, exist_ok=True)
        out_path = os.path.join(cfg.shared_data_dir, cfg.output_filename)
        payload = {
            "count": len(result),
            "summarized_count": len(to_summarize),
            "model": cfg.model,
            "mode": cfg.mode,
            "language": cfg.language,
            "papers": result,
        }
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        log.info(
            "Wrote %s (%d papers, %d summarized)",
            out_path,
            len(result),
            len(to_summarize),
        )

    return result
