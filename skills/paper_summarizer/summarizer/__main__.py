"""CLI entry: ``python -m summarizer [--input PATH] [--top-n N] [--mode ...]``.

Input resolution order when --input is not given:
  1. ``<shared_data_dir>/ranked_papers.json`` (produced by the ranker Skill).
  2. ``<shared_data_dir>/papers.json`` via ``shared.loader.load_papers_list``
     when running inside the arxiv-research-agent project (ranker not yet
     wired up). Falls back silently if ``shared`` is not importable.
  3. Error with the usual "Run the ranker first" message.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys

from .config import SummarizerConfig
from .core import summarize


def _default_input(cfg: SummarizerConfig) -> str:
    return os.path.join(cfg.shared_data_dir, "ranked_papers.json")


def _load_papers_from_default(cfg: SummarizerConfig):
    """Return (papers_list, source_label) or (None, None) if no input resolvable."""
    ranked = _default_input(cfg)
    if os.path.isfile(ranked):
        with open(ranked, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("papers", []), ranked

    # Fallback: data_collector's papers.json via the shared loader.
    try:
        from pathlib import Path

        from shared.loader import SkillInputMissingError, load_papers_list
    except ImportError:
        return None, None

    try:
        papers = load_papers_list(data_dir=Path(cfg.shared_data_dir))
    except SkillInputMissingError:
        return None, None
    return papers, os.path.join(cfg.shared_data_dir, "papers.json")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="summarizer", description="Summarize ranked arXiv papers."
    )
    parser.add_argument("--input", help="Path to ranked_papers.json")
    parser.add_argument("--top-n", type=int, help="Number of top papers to summarize")
    parser.add_argument(
        "--mode", choices=["abstract", "pdf"], help="Summarization mode"
    )
    parser.add_argument("--language", choices=["en", "zh"], help="Output language")
    parser.add_argument("--model", help="Override Anthropic model")
    parser.add_argument("--no-cache", action="store_true", help="Disable local cache")
    parser.add_argument(
        "--no-prompt-cache",
        action="store_true",
        help="Disable Anthropic prompt caching",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    cfg = SummarizerConfig()
    if args.top_n is not None:
        cfg.top_n = args.top_n
    if args.mode:
        cfg.mode = args.mode
    if args.language:
        cfg.language = args.language
    if args.model:
        cfg.model = args.model
    if args.no_cache:
        cfg.enable_local_cache = False
    if args.no_prompt_cache:
        cfg.enable_prompt_cache = False

    if args.input:
        if not os.path.isfile(args.input):
            print(f"Input not found: {args.input}", file=sys.stderr)
            return 2
        with open(args.input, encoding="utf-8") as f:
            data = json.load(f)
        papers = data.get("papers", data if isinstance(data, list) else [])
        in_path = args.input
    else:
        papers, in_path = _load_papers_from_default(cfg)
        if papers is None:
            print(
                f"No input found under {cfg.shared_data_dir} "
                "(looked for ranked_papers.json, then papers.json).",
                file=sys.stderr,
            )
            print("Run the ranker or data-collector first, or pass --input.", file=sys.stderr)
            return 2

    if not papers:
        print(f"No papers in input ({in_path}).", file=sys.stderr)
        return 1

    logging.getLogger(__name__).info("Loaded %d papers from %s", len(papers), in_path)

    result = summarize(papers, cfg=cfg)

    summarized = [p for p in result if p.get("one_line_summary")]
    print(f"\n== Summarized {len(summarized)} / {len(result)} papers ==")
    for i, p in enumerate(summarized[:5], 1):
        print(f"\n[{i}] {p['title']}")
        print(f"    {p['one_line_summary']}")
        if p.get("methods"):
            print(f"    methods: {', '.join(p['methods'][:5])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
