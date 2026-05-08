"""Main orchestrator for the arXiv Research Briefing Agent.

Entry point for WorkBuddy. Coordinates all 5 skills in pipeline order:
Skill 1 (data-collector) → Skill 2 (ranker) → Skill 3 (community) → Skill 5 (viz) → Skill 4 (report)

Usage:
    python arxiv_agent.py daily                          # Full daily pipeline
    python arxiv_agent.py fetch --categories cs.CL --keywords agent  # Skill 1 only
    python arxiv_agent.py status                         # Check data freshness
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
SHARED_DATA = PROJECT_ROOT / "shared_data"
sys.path.insert(0, str(PROJECT_ROOT))


def _pipeline_module():
    from skills.data_collector.scripts.pipeline import run_pipeline
    return run_pipeline


def run_skill1_fetch(categories, keywords, date_start=None, date_end=None,
                     max_results=200, backtrack_days=3, negative_keywords=None):
    """Execute Skill 1: fetch papers and populate shared_data/.

    Returns the pipeline manifest dict.
    """
    if date_end is None:
        date_end = datetime.now().strftime("%Y-%m-%d")
    if date_start is None:
        date_start = date_end

    config = {
        "categories": categories,
        "keywords": keywords,
        "date_range": {"start": date_start, "end": date_end},
        "max_results": max_results,
        "backtrack_days": backtrack_days,
        "negative_keywords": negative_keywords or [],
    }

    run_pipeline = _pipeline_module()
    manifest = run_pipeline(config)

    if manifest["errors"]:
        print(f"[Skill 1] Completed with {len(manifest['errors'])} errors")
    else:
        n = manifest["counts"]["after_dedup"]
        print(f"[Skill 1] Fetched {n} papers in {manifest['elapsed_seconds']}s")

    return manifest


# --------------------------------------------------------------------------
# Skill 2 (implemented) + Skill stubs (Skills 3-5)
# --------------------------------------------------------------------------

def run_skill2_rank(user_interest=""):
    """Skill 2 — PageRank + interest scoring."""
    from skills.paper_ranker.rank import rank_papers, save_rankings, save_ranked_papers, SkillInputMissingError
    try:
        rankings = rank_papers(
            user_interest=user_interest, data_dir=SHARED_DATA,
        )
        path1 = save_rankings(rankings, data_dir=SHARED_DATA)
        path2 = save_ranked_papers(rankings, data_dir=SHARED_DATA)
        print(f"[Skill 2] Ranked {len(rankings)} papers")
        print(f"  summary   → {path1}")
        print(f"  augmented → {path2}")
        for r in rankings[:5]:
            title = r.get("title", "")[:80]
            print(f"  #{r['rank']:2d} | PR={r['pagerank_score']:.6f} "
                  f"interest={r['interest_score']:.1f} "
                  f"novelty={r['novelty_score']:.1f} "
                  f"→ {r['score']:.1f} | {title}")
    except SkillInputMissingError as e:
        print(f"[Skill 2] Skipped — data not available: {e}")


def run_skill3_community():
    """Stub: Skill 3 — community detection."""
    from shared.loader import load_coauthorship_edges, SkillInputMissingError
    try:
        edges = load_coauthorship_edges(data_dir=SHARED_DATA)
        print(f"[Skill 3] Ready to detect communities in {len(edges)} co-authorship edges")
    except SkillInputMissingError as e:
        print(f"[Skill 3] Skipped — data not available: {e}")


def run_skill4_report():
    """Skill 4 — generate daily briefing (Markdown + agent hook JSON)."""
    import os

    from shared.loader import SkillInputMissingError
    from skills.briefing_report.generate import run_briefing_report

    try:
        out = run_briefing_report(
            data_dir=SHARED_DATA,
            interest_query=os.environ.get("BRIEFING_INTEREST"),
        )
        print(f"[Skill 4] Wrote briefing → {out}")
    except SkillInputMissingError as e:
        print(f"[Skill 4] Skipped — data not available: {e}")


def run_skill5_viz():
    """Stub: Skill 5 — visualization."""
    from shared.loader import load_coauthor_graph, SkillInputMissingError
    try:
        g = load_coauthor_graph(data_dir=SHARED_DATA)
        print(f"[Skill 5] Ready to visualize co-authorship graph ({g.number_of_nodes()} nodes)")
    except SkillInputMissingError as e:
        print(f"[Skill 5] Skipped — data not available: {e}")


# --------------------------------------------------------------------------
# Full pipeline
# --------------------------------------------------------------------------

def run_daily_pipeline(categories=None, keywords=None, date_start=None, date_end=None):
    """Run the full daily briefing pipeline: Skills 1→2→3→5→4."""
    categories = categories or ["cs.CL", "cs.LG", "cs.CV", "cs.AI", "cs.MA"]
    keywords = keywords or ["agent", "skill", "tool use", "LLM", "language model"]

    print("=" * 60)
    print(f"Daily Pipeline — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    print("\n[1/5] Data Collector (fetch + enrich + embed)")
    manifest = run_skill1_fetch(categories, keywords, date_start, date_end)

    if manifest["errors"]:
        print("[ABORT] Skill 1 had validation errors — stopping pipeline")
        return 1
    if manifest["counts"]["after_dedup"] == 0:
        print("[SKIP] No papers collected — nothing to do for downstream skills")
        return 0

    user_interest = " ".join(keywords) if keywords else ""
    print(f"\n[2/5] Paper Ranker (PageRank + interest: \"{user_interest}\")")
    run_skill2_rank(user_interest=user_interest)

    print("\n[3/5] Community Detector (co-authorship clustering)")
    run_skill3_community()

    print("\n[4/5] Visualizer (graphs + charts)")
    run_skill5_viz()

    print("\n[5/5] Briefing Report (daily Markdown/PDF)")
    run_skill4_report()

    print("\n" + "=" * 60)
    print("Pipeline complete.")
    return 0


# --------------------------------------------------------------------------
# Status check
# --------------------------------------------------------------------------

def check_status():
    """Report on the current state of shared_data/."""
    from shared.loader import load_manifest, SkillInputMissingError

    print("shared_data/ status:")
    for f in ["papers.json", "authors.json", "affiliations.json",
              "edges/citations.json", "edges/coauthorship.json",
              "edges/author_paper.json", "embeddings/paper_vecs.npy",
              "manifest.json", "raw_papers.json",
              "rankings.json", "ranked_papers.json"]:
        exists = (SHARED_DATA / f).exists()
        print(f"  {'[x]' if exists else '[ ]'} {f}")

    try:
        manifest_data = load_manifest(data_dir=SHARED_DATA)
        print(f"\n  Last run: {manifest_data.get('timestamp', 'unknown')}")
        print(f"  Run ID:   {manifest_data.get('run_id', 'unknown')}")
        counts = manifest_data.get("counts", {})
        print(f"  Papers:   {counts.get('after_dedup', '?')}")
    except SkillInputMissingError:
        print("\n  No manifest — Skill 1 has not been run yet")


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="arXiv Research Briefing Agent — orchestrator"
    )
    sub = parser.add_subparsers(dest="command")

    daily = sub.add_parser("daily", help="Run full daily pipeline (Skills 1→2→3→5→4)")
    daily.add_argument("--categories", nargs="*", help="arXiv categories")
    daily.add_argument("--keywords", nargs="*", help="Search keywords")
    daily.add_argument("--date-start", help="Start date YYYY-MM-DD")
    daily.add_argument("--date-end", help="End date YYYY-MM-DD")

    fetch_p = sub.add_parser("fetch", help="Run Skill 1 only (data collection)")
    fetch_p.add_argument("--categories", nargs="+", required=True)
    fetch_p.add_argument("--keywords", nargs="+", required=True)
    fetch_p.add_argument("--date-start", help="Start date YYYY-MM-DD")
    fetch_p.add_argument("--date-end", help="End date YYYY-MM-DD")
    fetch_p.add_argument("--max-results", type=int, default=200)
    fetch_p.add_argument("--backtrack-days", type=int, default=3)
    fetch_p.add_argument("--negative-keywords", nargs="*")

    rank_p = sub.add_parser("rank", help="Run Skill 2 only (PageRank + interest)")
    rank_p.add_argument("--interest", type=str, default="",
                        help="User research interest text")

    sub.add_parser("status", help="Check shared_data/ state")

    args = parser.parse_args()

    if args.command == "daily":
        return run_daily_pipeline(
            categories=getattr(args, "categories", None),
            keywords=getattr(args, "keywords", None),
            date_start=getattr(args, "date_start", None),
            date_end=getattr(args, "date_end", None),
        )
    elif args.command == "fetch":
        run_skill1_fetch(
            categories=args.categories,
            keywords=args.keywords,
            date_start=args.date_start,
            date_end=args.date_end,
            max_results=args.max_results,
            backtrack_days=args.backtrack_days,
            negative_keywords=args.negative_keywords,
        )
        return 0
    elif args.command == "rank":
        run_skill2_rank(user_interest=args.interest)
        return 0
    elif args.command == "status":
        check_status()
        return 0
    else:
        check_status()
        return 0


if __name__ == "__main__":
    sys.exit(main())
