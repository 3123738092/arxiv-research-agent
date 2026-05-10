"""Skill 3 — prepare summarization request for the host LLM.

This script does NOT call any external LLM API. It assembles the inputs
(ranked papers + system prompt + output schema) so the host LLM running
the Agent (e.g. Claude in WorkBuddy) can perform the summarization
in-context using its own conversation API, then write back to
``shared_data/summarized_papers.json``.

CLI:
    python -m skills.paper_summarizer.scripts.prepare --top-n 10 --language en
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

from skills.paper_summarizer.summarizer.prompts import build_user_prompt, get_system_prompt
from skills.paper_summarizer.summarizer.schema import SUMMARY_FIELDS

log = logging.getLogger(__name__)

DEFAULT_REQUEST_FILE = "summarize_request.json"
DEFAULT_OUTPUT_FILE = "summarized_papers.json"


def _rank_score(p: dict) -> float:
    return float(p.get("relevance_score", 0.0) or 0.0) + float(p.get("novelty_score", 0.0) or 0.0)


def _load_papers(shared_data: Path) -> list[dict]:
    """Return papers ordered by (relevance + novelty) when available.

    ranked_papers.json preserves the upstream arxiv listing order, so we sort
    here. papers.json is taken in arxiv order as a fallback.
    """
    ranked = shared_data / "ranked_papers.json"
    if ranked.is_file():
        with ranked.open(encoding="utf-8") as f:
            data = json.load(f)
        items = data if isinstance(data, list) else data.get("papers", [])
        return sorted(items, key=_rank_score, reverse=True)

    papers = shared_data / "papers.json"
    if papers.is_file():
        with papers.open(encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return list(data.values())
    return []


def _trim_paper(p: dict, index: int) -> dict:
    """Compact view of one paper for the LLM context."""
    return {
        "index": index,
        "arxiv_id": p.get("arxiv_id", ""),
        "title": (p.get("title") or "").strip(),
        "abstract": (p.get("abstract") or "").strip(),
        "arxiv_url": p.get("arxiv_url") or p.get("pdf_url") or "",
    }


def build_request(
    papers: list[dict],
    top_n: int = 10,
    language: str = "en",
    mode: str = "abstract",
    output_path: str = DEFAULT_OUTPUT_FILE,
) -> dict:
    """Build the structured request payload the host LLM will execute."""
    selected = papers[:top_n]
    trimmed = [_trim_paper(p, i) for i, p in enumerate(selected)]

    instructions = (
        "You are running Skill 3 (paper_summarizer) of the arXiv Research "
        "Briefing Agent. Read the papers in `papers` below, summarize each "
        "according to the schema, and write the result to "
        f"`shared_data/{output_path}`. Do not call any external API for "
        "this task — generate the summaries yourself in the current "
        "conversation. After writing the file, run "
        "`python -m skills.paper_summarizer.scripts.finalize` to validate."
    )

    output_schema = {
        "envelope": {
            "count": "int — total papers in `papers`",
            "summarized_count": "int — number of papers you actually filled in",
            "model": "str — name of the model performing the summarization",
            "mode": mode,
            "language": language,
            "papers": "list — original paper objects augmented with the four summary fields",
        },
        "per_paper_fields": {k: "see system prompt for type and limits" for k in SUMMARY_FIELDS},
    }

    return {
        "instructions": instructions,
        "system_prompt": get_system_prompt(language),
        "user_prompt": build_user_prompt(trimmed, mode=mode),
        "output_path": f"shared_data/{output_path}",
        "output_schema": output_schema,
        "language": language,
        "mode": mode,
        "top_n": len(trimmed),
        "papers": trimmed,
    }


def write_request(
    request: dict,
    shared_data: Path,
    request_filename: str = DEFAULT_REQUEST_FILE,
) -> Path:
    shared_data.mkdir(parents=True, exist_ok=True)
    out = shared_data / request_filename
    with out.open("w", encoding="utf-8") as f:
        json.dump(request, f, ensure_ascii=False, indent=2)
    return out


def run(
    top_n: int = 10,
    language: str = "en",
    mode: str = "abstract",
    shared_data: Optional[Path] = None,
) -> dict:
    shared_data = Path(shared_data or (PROJECT_ROOT / "shared_data"))
    papers = _load_papers(shared_data)
    if not papers:
        return {
            "ok": False,
            "reason": "No ranked_papers.json or papers.json in shared_data/",
            "request_path": None,
            "papers_to_summarize": 0,
        }
    request = build_request(papers, top_n=top_n, language=language, mode=mode)
    out_path = write_request(request, shared_data)
    return {
        "ok": True,
        "request_path": str(out_path),
        "papers_to_summarize": request["top_n"],
        "language": language,
        "mode": mode,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Skill 3 — prepare summarization request for the host LLM"
    )
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--language", choices=["en", "zh"], default="en")
    parser.add_argument("--mode", choices=["abstract", "pdf"], default="abstract")
    parser.add_argument("--shared-data", type=Path, default=None)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    result = run(
        top_n=args.top_n,
        language=args.language,
        mode=args.mode,
        shared_data=args.shared_data,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
