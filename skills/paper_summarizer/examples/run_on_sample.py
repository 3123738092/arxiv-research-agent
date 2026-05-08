"""Minimal example: summarize the 3 fixture papers with real Claude.

Requires ANTHROPIC_API_KEY in env.

    python examples/run_on_sample.py
"""

from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, ROOT)

from summarizer import summarize, SummarizerConfig  # noqa: E402


def main() -> int:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Set ANTHROPIC_API_KEY first.", file=sys.stderr)
        return 2
    with open(os.path.join(ROOT, "data", "fixtures", "ranked_papers_sample.json")) as f:
        data = json.load(f)

    cfg = SummarizerConfig(top_n=3, batch_size=3)
    cfg.shared_data_dir = os.path.join(ROOT, "data")
    cfg.output_filename = "summarized_papers_sample.json"

    result = summarize(data["papers"], cfg=cfg)
    for p in result:
        print(f"\n{p['title']}\n  -> {p['one_line_summary']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
