"""Cheap offline evaluation for summarizer output quality.

Given a summarized_papers.json, compute simple heuristic metrics that do not
need human labels — they tell you whether the Skill is producing *usable*
structured output (not whether it's *correct*). Use this during development
to catch regressions when swapping models or prompts.

Metrics (per summarized paper, then averaged):
  * coverage_rate: fraction of papers where all 4 fields are non-empty
  * method_specificity: fraction of methods that are not in a generic-word list
  * keyword_abstract_overlap: fraction of keywords appearing in the abstract
  * summary_len_words: avg word count of one_line_summary (target ~15-30)

Run:
    python examples/evaluate_summaries.py [path_to_summarized_papers.json]
"""

from __future__ import annotations

import json
import os
import re
import sys
from statistics import mean

GENERIC_METHODS = {
    "machine learning", "deep learning", "neural network", "neural networks",
    "transformer", "reinforcement learning", "supervised learning",
    "model", "ai", "artificial intelligence",
}

TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_\-]+")


def _tokenize(text: str) -> set[str]:
    return {t.lower() for t in TOKEN_RE.findall(text or "")}


def evaluate(papers: list[dict]) -> dict:
    summarized = [p for p in papers if p.get("one_line_summary")]
    if not summarized:
        return {"n_summarized": 0}

    coverages = []
    specificities = []
    overlaps = []
    lengths = []

    for p in summarized:
        has_all = all(p.get(k) for k in ("one_line_summary", "key_contributions",
                                         "methods", "keywords"))
        coverages.append(1.0 if has_all else 0.0)

        methods = p.get("methods") or []
        if methods:
            non_generic = sum(1 for m in methods if m.lower() not in GENERIC_METHODS)
            specificities.append(non_generic / len(methods))

        abstract_tokens = _tokenize(p.get("abstract", ""))
        keywords = p.get("keywords") or []
        if keywords and abstract_tokens:
            hits = 0
            for kw in keywords:
                kw_tokens = _tokenize(kw)
                if kw_tokens and kw_tokens & abstract_tokens:
                    hits += 1
            overlaps.append(hits / len(keywords))

        lengths.append(len(p["one_line_summary"].split()))

    return {
        "n_summarized": len(summarized),
        "coverage_rate": round(mean(coverages), 3),
        "method_specificity": round(mean(specificities), 3) if specificities else None,
        "keyword_abstract_overlap": round(mean(overlaps), 3) if overlaps else None,
        "avg_summary_len_words": round(mean(lengths), 1),
    }


def _default_path() -> str:
    here = os.path.dirname(__file__)
    for cand in [
        os.path.abspath(os.path.join(here, "..", "..", "shared_data",
                                     "summarized_papers.json")),
        os.path.abspath(os.path.join(here, "..", "data",
                                     "summarized_papers.json")),
    ]:
        if os.path.isfile(cand):
            return cand
    raise SystemExit("No summarized_papers.json found. Run the Skill first.")


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else _default_path()
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    metrics = evaluate(data.get("papers", []))
    print(f"Evaluating {path}")
    print(json.dumps(metrics, indent=2, ensure_ascii=False))
