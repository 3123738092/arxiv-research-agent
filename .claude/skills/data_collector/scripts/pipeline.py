"""Stage 1 + Orchestrator: Main pipeline entry point for data_collector.

Usage:
    python /path/to/skills/arxiv-research-agent/skills/data_collector/scripts/pipeline.py --config config.json

Config JSON keys:
    categories, keywords, date_range {start, end}, max_results, backtrack_days,
    negative_keywords, sources, user_interest_text

Note: This script uses path self-healing — it works from any working directory.
"""

import sys
from pathlib import Path

# --- 路径自修复：向上找到 skills/ 的父目录，适配任意平台/深度 ---
_current = Path(__file__).resolve()
for _ in range(10):
    if (_current / "skills" / "data_collector").is_dir():
        if str(_current) not in sys.path:
            sys.path.insert(0, str(_current))
        break
    if _current.parent == _current:
        break
    _current = _current.parent
# ---------------------------------------------------------

import argparse
import json
import time
from datetime import datetime

from skills.data_collector.scripts.utils import (
    set_shared_data, save_json, short_hash,
)
from skills.data_collector.scripts import utils  # access SHARED_DATA via utils.SHARED_DATA after set_shared_data()
from skills.data_collector.scripts.fetch_arxiv import fetch_arxiv_papers, filter_by_negative_keywords
from skills.data_collector.scripts.dedup import dedup_papers
from skills.data_collector.scripts.build_graph_edges import build_all_edges
from skills.data_collector.scripts.build_similarity_graph import build_similarity_graph
from skills.data_collector.scripts.embed import embed_papers
from skills.data_collector.scripts.validate import validate_all


def run_pipeline(config):
    """Execute the full data_collector pipeline.

    Args:
        config: dict with keys: categories, keywords, date_range, etc.

    Returns:
        manifest dict summarizing the run.
    """
    t0 = time.time()
    run_id = short_hash(f"{config}{t0}")
    warnings = []
    errors = []

    categories = config["categories"]
    keywords = config["keywords"]
    date_range = config["date_range"]
    max_results = config.get("max_results", 200)
    backtrack_days = config.get("backtrack_days", 3)
    negative_keywords = config.get("negative_keywords", [])

    # Stage 2: Fetch from arXiv
    papers, actual_date, fetch_warnings = fetch_arxiv_papers(
        categories, keywords,
        date_start=date_range["start"],
        date_end=date_range["end"],
        max_results=max_results,
        backtrack_days=backtrack_days,
    )
    warnings.extend(fetch_warnings)
    fetch_count = len(papers)

    papers = filter_by_negative_keywords(papers, negative_keywords)
    neg_filtered = fetch_count - len(papers)
    if neg_filtered:
        warnings.append(f"Filtered {neg_filtered} papers by negative keywords")

    # Stage 3: Deduplicate
    papers, dedup_stats = dedup_papers(papers)
    warnings.append(f"Dedup: {dedup_stats}")

    # Stage 4: Build co-authorship / author edges (from arXiv metadata, no S2 needed)
    _edges_result = build_all_edges(papers, authors_list=None, citations_edges=[])
    papers = _edges_result.pop("papers", papers)
    authors_list = _edges_result["authors_list"]
    affiliations_list = []  # no S2 — affiliations derived from arXiv metadata only

    # Stage 5: Compute embeddings (needed before similarity graph)
    vecs, embed_index, embed_warnings = embed_papers(papers)
    warnings.extend(embed_warnings)

    # Stage 6: Build semantic similarity graph from embeddings (replaces S2 citation graph)
    papers_index = {p["arxiv_id"]: p for p in papers}
    similarity_edges = build_similarity_graph(papers_index, (vecs, embed_index))

    # Build complete edges dict for validation and output
    edges = _edges_result  # contains: coauthorship, author_paper
    edges["similarity"] = similarity_edges

    # Stage 7: Validate
    validated, validation_errors = validate_all(
        papers, authors_list, affiliations_list, edges
    )
    if validation_errors:
        errors.extend(validation_errors)

    # Stage 7b: Write all output files
    _write_outputs(validated, similarity_edges)

    # Stage 7c: Write legacy view
    _write_legacy_raw_papers(validated["papers"])

    # Stage 8: Manifest
    elapsed = round(time.time() - t0, 2)
    manifest = {
        "run_id": run_id,
        "timestamp": datetime.now().isoformat(),
        "params": config,
        "source_status": {
            "arxiv": "ok" if fetch_count > 0 else "empty",
            "similarity_graph": "ok" if similarity_edges else "empty",
            "embeddings": "ok" if not embed_warnings else "skipped",
        },
        "counts": {
            "fetched": fetch_count,
            "after_dedup": dedup_stats["output_count"],
            "similarity_edges": len(similarity_edges),
            "coauthorship_edges": len(validated["edges"]["coauthorship"]),
            "author_paper_edges": len(validated["edges"]["author_paper"]),
            "authors": len(validated["authors"]),
            "affiliations": len(validated["affiliations"]),
            "embeddings_dim": vecs.shape[1] if vecs.size else 0,
        },
        "errors": errors,
        "warnings": warnings,
        "elapsed_seconds": elapsed,
    }
    save_json(utils.SHARED_DATA / "manifest.json", manifest)

    return manifest


def _write_outputs(validated, similarity_edges):
    """Write all validated data files to shared_data/."""
    save_json(utils.SHARED_DATA / "papers.json", validated["papers"])
    save_json(utils.SHARED_DATA / "authors.json", validated["authors"])
    save_json(utils.SHARED_DATA / "affiliations.json", validated["affiliations"])

    edges_dir = utils.SHARED_DATA / "edges"
    edges_dir.mkdir(parents=True, exist_ok=True)
    # Write similarity edges (replaces citation graph)
    save_json(edges_dir / "similarity.json", similarity_edges)
    save_json(edges_dir / "coauthorship.json", validated["edges"]["coauthorship"])
    save_json(edges_dir / "author_paper.json", validated["edges"]["author_paper"])


def _write_legacy_raw_papers(papers):
    """Write the legacy raw_papers.json for backward compatibility."""
    legacy = [
        {
            "arxiv_id": p["arxiv_id"],
            "title": p["title"],
            "abstract": p["abstract"],
            "authors": p.get("authors_raw", []),
            "published": p.get("published"),
            "arxiv_url": p.get("arxiv_url"),
            "pdf_url": p.get("pdf_url"),
            "categories": p.get("categories", []),
            "primary_category": p.get("primary_category"),
            "comment": p.get("comment"),
            "citation_count": p.get("citation_count"),
            "code_url": p.get("code_url"),
        }
        for p in papers
    ]
    save_json(utils.SHARED_DATA / "raw_papers.json", legacy)


def main():
    parser = argparse.ArgumentParser(description="Data Collector Pipeline")
    parser.add_argument("--config", required=True, help="Path to JSON config file")
    parser.add_argument(
        "--shared-data",
        default=None,
        dest="shared_data",
        help=(
            "Output directory for shared_data/. "
            "Priority: --shared-data > WORKBUDDY_SHARED_DATA env > ~/.workbuddy/shared_data"
        ),
    )
    args = parser.parse_args()

    # Apply path override before any I/O — must happen before run_pipeline
    if args.shared_data:
        set_shared_data(args.shared_data)

    # Support inline JSON config on Windows (where /dev/stdin doesn't exist)
    # If --config starts with '{', treat it as the JSON content directly
    config_arg = args.config.strip()
    if config_arg.startswith("{"):
        import tempfile
        import atexit
        _tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8")
        _tmp.write(config_arg)
        _tmp.close()
        atexit.register(lambda: Path(_tmp.name).unlink(missing_ok=True))
        config_path = _tmp.name
    else:
        config_path = config_arg

    with open(config_path, encoding="utf-8") as f:
        config = json.load(f)

    manifest = run_pipeline(config)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    if manifest["errors"]:
        print(f"\n[ERRORS] {len(manifest['errors'])} validation failures")
        for e in manifest["errors"][:5]:
            print(f"  - {e}")
    return 0 if not manifest["errors"] else 1


if __name__ == "__main__":
    exit(main())
