"""Skill 3 — validate & normalize summaries written by the host LLM.

After the host LLM writes ``shared_data/summarized_papers.json`` per the
prepared request, run this script to:
  - Accept either a bare list or the canonical envelope shape.
  - Normalize every per-paper summary block via summarizer.schema.
  - Re-emit the canonical envelope so downstream Skills (visualizer, report)
    have a stable contract.
  - Report which papers are missing summaries.

CLI:
    python -m skills.paper_summarizer.scripts.finalize
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Optional

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def resolve_shared_data(override=None):
    """Resolve shared_data path.

    Priority: CLI arg > WORKBUDDY_SHARED_DATA env > PROJECT_ROOT/shared_data (fallback).
    """
    if override:
        return Path(override)
    env = os.environ.get("WORKBUDDY_SHARED_DATA")
    if env:
        return Path(env)
    return PROJECT_ROOT / "shared_data"


def _get_shared_data(shared_data):
    """Runtime path resolution: use CLI arg if given, otherwise check env, else fallback."""
    if shared_data is not None:
        return Path(shared_data)
    return resolve_shared_data()

from skills.paper_summarizer.summarizer.schema import (
    SUMMARY_FIELDS,
    merge_into_paper,
    normalize_summary,
)

log = logging.getLogger(__name__)

OUTPUT_FILE = "summarized_papers.json"


def _read_summary_file(path: Path) -> tuple[list[dict], dict]:
    """Return (papers_list, envelope_meta) tolerating both shapes."""
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return data, {}
    if isinstance(data, dict):
        papers = data.get("papers", [])
        meta = {k: v for k, v in data.items() if k != "papers"}
        return papers, meta
    raise ValueError(f"Unsupported JSON shape in {path}: {type(data).__name__}")


def _read_ranked(shared_data: Path) -> list[dict]:
    p = shared_data / "ranked_papers.json"
    if not p.is_file():
        return []
    with p.open(encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else data.get("papers", [])


def _index_by_arxiv(papers: list[dict]) -> dict:
    return {p.get("arxiv_id", ""): p for p in papers if p.get("arxiv_id")}


def normalize_papers(
    written: list[dict],
    upstream: list[dict],
) -> tuple[list[dict], int, list[str]]:
    """Merge LLM output with upstream paper records; normalize summary fields.

    Returns (normalized_papers, summarized_count, missing_arxiv_ids).
    """
    upstream_by_id = _index_by_arxiv(upstream)
    normalized: list[dict] = []
    summarized = 0
    missing: list[str] = []

    for p in written:
        aid = p.get("arxiv_id", "")
        base = dict(upstream_by_id.get(aid, {}))
        base.update(p)

        summary_input = {k: p.get(k) for k in SUMMARY_FIELDS}
        norm = normalize_summary(summary_input)
        merge_into_paper(base, norm)

        if norm["one_line_summary"]:
            summarized += 1
        else:
            missing.append(aid or base.get("title", "<unknown>")[:60])

        normalized.append(base)
    return normalized, summarized, missing


def run(
    shared_data: Optional[Path] = None,
    output_filename: str = OUTPUT_FILE,
) -> dict:
    shared_data = _get_shared_data(shared_data)
    target = shared_data / output_filename

    if not target.is_file():
        return {
            "ok": False,
            "reason": (
                f"{target} not found. The host LLM should write its summary "
                "output there before running finalize."
            ),
            "path": str(target),
        }

    written, meta = _read_summary_file(target)
    upstream = _read_ranked(shared_data)
    normalized, summarized, missing = normalize_papers(written, upstream)

    envelope = {
        "count": len(normalized),
        "summarized_count": summarized,
        "model": meta.get("model", "host-llm"),
        "mode": meta.get("mode", "abstract"),
        "language": meta.get("language", "en"),
        "papers": normalized,
    }

    with target.open("w", encoding="utf-8") as f:
        json.dump(envelope, f, ensure_ascii=False, indent=2)

    return {
        "ok": True,
        "path": str(target),
        "count": envelope["count"],
        "summarized_count": summarized,
        "missing": missing,
        "model": envelope["model"],
        "language": envelope["language"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Skill 3 — finalize host-LLM summaries (validate + normalize)"
    )
    parser.add_argument("--shared-data", type=Path, default=None)
    parser.add_argument("--output-filename", default=OUTPUT_FILE)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    result = run(shared_data=args.shared_data, output_filename=args.output_filename)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
