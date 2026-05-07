"""Stage 1 + Orchestrator: Main pipeline entry point for data_collector.

Usage:
    python -m skills.data_collector.scripts.pipeline --config config.json

Config JSON keys:
    categories, keywords, date_range {start, end}, max_results, backtrack_days,
    negative_keywords, sources, user_interest_text
"""

import argparse
import json
import time
from datetime import datetime

from .utils import (
    SHARED_DATA, save_json, load_last_fetch, save_last_fetch, short_hash,
)
from .fetch_arxiv import fetch_arxiv_papers, filter_by_negative_keywords
from .dedup import dedup_papers, update_seen_ids
from .enrich_semantic_scholar import enrich_papers
from .build_graph_edges import build_all_edges
from .embed import embed_papers
from .validate import validate_all


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
    last_fetch = load_last_fetch()
    papers, dedup_stats = dedup_papers(papers, last_fetch.get("seen_ids", []))
    warnings.append(f"Dedup: {dedup_stats}")

    # Stage 4: Enrich via Semantic Scholar
    papers, citations_edges, authors_list, affiliations_list, enrich_warnings = enrich_papers(papers)
    warnings.extend(enrich_warnings)

    # Stage 5: Build graph edges
    edges = build_all_edges(papers, authors_list, citations_edges)
    papers = edges.pop("papers", papers)
    authors_list = edges.pop("authors_list", authors_list)

    # Stage 6: Compute embeddings
    vecs, embed_index, embed_warnings = embed_papers(papers)
    warnings.extend(embed_warnings)

    # Stage 7: Validate
    validated, validation_errors = validate_all(
        papers, authors_list, affiliations_list, edges
    )
    if validation_errors:
        errors.extend(validation_errors)

    # Stage 7b: Write all output files
    _write_outputs(validated)

    # Stage 7c: Write legacy view
    _write_legacy_raw_papers(validated["papers"])

    # State: update last_fetch
    new_seen = update_seen_ids(last_fetch, validated["papers"])
    save_last_fetch(new_seen, config)

    # Stage 8: Manifest
    elapsed = round(time.time() - t0, 2)
    manifest = {
        "run_id": run_id,
        "timestamp": datetime.now().isoformat(),
        "params": config,
        "source_status": {
            "arxiv": "ok" if fetch_count > 0 else "empty",
            "semantic_scholar": "ok" if not enrich_warnings else "partial",
            "embeddings": "ok" if not embed_warnings else "skipped",
        },
        "counts": {
            "fetched": fetch_count,
            "after_dedup": dedup_stats["output_count"],
            "with_s2_data": sum(1 for p in validated["papers"] if p.get("s2_paper_id")),
            "citation_edges": len(validated["edges"]["citations"]),
            "citation_edges_external": len(validated["edges"].get("citations_external", [])),
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
    save_json(SHARED_DATA / "manifest.json", manifest)

    return manifest


def _write_outputs(validated):
    """Write all validated data files to shared_data/."""
    save_json(SHARED_DATA / "papers.json", validated["papers"])
    save_json(SHARED_DATA / "authors.json", validated["authors"])
    save_json(SHARED_DATA / "affiliations.json", validated["affiliations"])

    edges_dir = SHARED_DATA / "edges"
    edges_dir.mkdir(parents=True, exist_ok=True)
    save_json(edges_dir / "citations.json", validated["edges"]["citations"])
    save_json(edges_dir / "coauthorship.json", validated["edges"]["coauthorship"])
    save_json(edges_dir / "author_paper.json", validated["edges"]["author_paper"])

    if validated["edges"].get("citations_external"):
        save_json(edges_dir / "citations_external.json",
                  validated["edges"]["citations_external"])


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
    save_json(SHARED_DATA / "raw_papers.json", legacy)


def main():
    parser = argparse.ArgumentParser(description="Data Collector Pipeline")
    parser.add_argument("--config", required=True, help="Path to JSON config file")
    args = parser.parse_args()

    with open(args.config, encoding="utf-8") as f:
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
