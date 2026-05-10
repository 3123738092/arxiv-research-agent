"""Main orchestrator for the arXiv Research Briefing Agent.

Entry point for WorkBuddy. Coordinates all 5 skills in pipeline order:
Skill 1 (data_collector) → Skill 2 (paper_ranker) → Skill 3 (paper_summarizer) → Skill 4 (briefing_report) → Skill 5 (viz)

Usage:
    python arxiv_agent.py daily                          # Full daily pipeline
    python arxiv_agent.py fetch --categories cs.CL --keywords agent  # Skill 1 only
    python arxiv_agent.py summarize --top-n 10           # Skill 3 only
    python arxiv_agent.py viz                            # Skill 5 only
    python arxiv_agent.py status                         # Check data freshness
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
SHARED_DATA = PROJECT_ROOT / "shared_data"
VIZ_OUTPUT = PROJECT_ROOT / "output"
sys.path.insert(0, str(PROJECT_ROOT))

VIZ_SCRIPTS_DIR = PROJECT_ROOT / "skills" / "papers-analysis-visualizer" / "scripts"


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
# Skills 2 / 3 / 4 / 5 wrappers
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


def run_skill3_summarize(top_n=10, mode="abstract", language="en"):
    """Skill 3 — prepare summarization request for the host LLM.

    Does NOT call any external API. Writes shared_data/summarize_request.json
    so the host LLM (Claude in WorkBuddy / Claude Code) can perform the
    summarization in its own conversation context, write
    shared_data/summarized_papers.json, then run finalize-summary to validate.
    """
    try:
        from skills.paper_summarizer.scripts.prepare import run as run_prepare
    except ImportError as e:
        print(f"[Skill 3] Skipped — prepare script not importable: {e}")
        return None

    result = run_prepare(top_n=top_n, language=language, mode=mode, shared_data=SHARED_DATA)
    if not result["ok"]:
        print(f"[Skill 3] Skipped — {result.get('reason', 'unknown')}")
        return result

    req_path = result["request_path"]
    n = result["papers_to_summarize"]
    print(f"[Skill 3] Prepared request for {n} papers ({language}, {mode})")
    print(f"  request   → {req_path}")
    print(f"  next step → host LLM reads {req_path}, summarizes in-context,")
    print(f"              writes shared_data/summarized_papers.json,")
    print(f"              then run: python arxiv_agent.py finalize-summary")
    return result


def run_finalize_summary():
    """Validate and normalize host-LLM summary output."""
    try:
        from skills.paper_summarizer.scripts.finalize import run as run_finalize
    except ImportError as e:
        print(f"[Skill 3 finalize] Skipped — finalize script not importable: {e}")
        return None

    result = run_finalize(shared_data=SHARED_DATA)
    if not result["ok"]:
        print(f"[Skill 3 finalize] {result.get('reason', 'unknown')}")
        return result

    print(
        f"[Skill 3 finalize] {result['summarized_count']}/{result['count']} papers "
        f"have non-empty summaries (model={result['model']}, lang={result['language']})"
    )
    if result["missing"]:
        print(f"  missing summaries for {len(result['missing'])} papers (showing up to 5):")
        for m in result["missing"][:5]:
            print(f"    - {m}")
    return result


def run_skill4_report():
    """Skill 4 — generate daily briefing (Markdown + agent hook JSON)."""
    import os

    from skills.briefing_report._io import SkillInputMissingError
    from skills.briefing_report.generate import run_briefing_report

    try:
        out = run_briefing_report(
            data_dir=SHARED_DATA,
            interest_query=os.environ.get("BRIEFING_INTEREST"),
        )
        print(f"[Skill 4] Wrote briefing → {out}")
    except SkillInputMissingError as e:
        print(f"[Skill 4] Skipped — data not available: {e}")


def _build_visualizer_input():
    """Adapt summarized_papers.json (or ranked_papers.json) to the
    field names expected by papers-analysis-visualizer.

    Required visualizer fields per paper: paper_id, title, url,
    relevance_score, novelty_score, one_line_summary, keywords.

    Returns the path to the adapter file, or None if no usable input.
    """
    summarized = SHARED_DATA / "summarized_papers.json"
    ranked = SHARED_DATA / "ranked_papers.json"

    raw_papers = []
    if summarized.is_file():
        with summarized.open(encoding="utf-8") as f:
            payload = json.load(f)
        raw_papers = payload.get("papers", payload if isinstance(payload, list) else [])
    elif ranked.is_file():
        with ranked.open(encoding="utf-8") as f:
            raw_papers = json.load(f)
    else:
        return None

    if not raw_papers:
        return None

    adapted = []
    for p in raw_papers:
        published = p.get("published") or ""
        published_date = published[:10] if published else None
        url = p.get("arxiv_url") or p.get("pdf_url") or p.get("url") or ""
        adapted.append({
            "paper_id": p.get("arxiv_id") or p.get("paper_id") or "",
            "title": p.get("title", ""),
            "url": url,
            "relevance_score": float(p.get("relevance_score", 0.0) or 0.0),
            "novelty_score": float(p.get("novelty_score", 0.0) or 0.0),
            "one_line_summary": p.get("one_line_summary", ""),
            "keywords": p.get("keywords") or [],
            "authors": p.get("authors_raw") or p.get("authors") or [],
            "published_date": published_date,
            "category": p.get("primary_category") or p.get("category") or "",
            "community_label": p.get("community_label", "Unknown"),
            "abstract": p.get("abstract", ""),
        })

    out_path = SHARED_DATA / "visualizer_input.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(adapted, f, ensure_ascii=False, indent=2)
    return out_path


def run_skill5_viz(skip_notion=False):
    """Skill 5 — Topic dashboard + optional Notion sync.

    Always tries to render the dashboard HTML. Notion sync runs only when
    NOTION_API_TOKEN is present and skip_notion is False.
    """
    adapter_path = _build_visualizer_input()
    if adapter_path is None:
        print("[Skill 5] Skipped — no ranked_papers.json or summarized_papers.json found")
        return

    VIZ_OUTPUT.mkdir(parents=True, exist_ok=True)
    dashboard_out = VIZ_OUTPUT / "dashboard.html"
    notion_mapping = VIZ_OUTPUT / "notion_mapping.json"

    dashboard_script = VIZ_SCRIPTS_DIR / "build_dashboard_html.py"
    if not dashboard_script.is_file():
        print(f"[Skill 5] Visualizer scripts not found at {VIZ_SCRIPTS_DIR}")
        return

    cmd = [
        sys.executable, str(dashboard_script),
        "--input", str(adapter_path),
        "--output", str(dashboard_out),
        "--notion-mapping", str(notion_mapping),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode == 0:
        print(f"[Skill 5] Dashboard → {dashboard_out}")
    else:
        print(f"[Skill 5] Dashboard build failed (exit {proc.returncode})")
        if proc.stderr:
            print(proc.stderr.strip().splitlines()[-1])
        return

    if skip_notion:
        return
    if not os.environ.get("NOTION_API_TOKEN"):
        print("[Skill 5] Notion sync skipped — set NOTION_API_TOKEN to enable")
        return

    sync_script = VIZ_SCRIPTS_DIR / "sync_to_notion.py"
    cmd = [
        sys.executable, str(sync_script),
        "--input", str(adapter_path),
        "--output", str(notion_mapping),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode == 0:
        print(f"[Skill 5] Notion mapping → {notion_mapping}")
    else:
        print(f"[Skill 5] Notion sync failed (exit {proc.returncode})")
        if proc.stderr:
            print(proc.stderr.strip().splitlines()[-1])


# --------------------------------------------------------------------------
# Full pipeline
# --------------------------------------------------------------------------

def run_daily_pipeline(categories=None, keywords=None, date_start=None, date_end=None):
    """Run the full daily briefing pipeline: Skills 1→2→3→4→5."""
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

    print("\n[3/5] Paper Summarizer (prepare request for host LLM)")
    run_skill3_summarize()

    print("\n[4/5] Visualizer (dashboard + Notion sync)")
    run_skill5_viz()

    print("\n[5/5] Briefing Report (daily Markdown)")
    run_skill4_report()

    print("\n" + "=" * 60)
    print("Pipeline complete.")
    return 0


# --------------------------------------------------------------------------
# Status check
# --------------------------------------------------------------------------

def check_status():
    """Report on the current state of shared_data/."""
    from skills.briefing_report._io import load_manifest, SkillInputMissingError

    print("shared_data/ status:")
    for f in ["papers.json", "authors.json", "affiliations.json",
              "edges/citations.json", "edges/coauthorship.json",
              "edges/author_paper.json", "embeddings/paper_vecs.npy",
              "manifest.json", "raw_papers.json",
              "rankings.json", "ranked_papers.json",
              "summarize_request.json", "summarized_papers.json",
              "visualizer_input.json", "briefing.md"]:
        exists = (SHARED_DATA / f).exists()
        print(f"  {'[x]' if exists else '[ ]'} {f}")

    print("\noutput/ status:")
    for f in ["dashboard.html", "notion_mapping.json"]:
        exists = (VIZ_OUTPUT / f).exists()
        print(f"  {'[x]' if exists else '[ ]'} output/{f}")

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

    daily = sub.add_parser("daily", help="Run full daily pipeline (Skills 1→2→3→4→5)")
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

    sum_p = sub.add_parser(
        "summarize",
        help="Run Skill 3 prepare step (host LLM does the summarization itself)",
    )
    sum_p.add_argument("--top-n", type=int, default=10)
    sum_p.add_argument("--mode", choices=["abstract", "pdf"], default="abstract")
    sum_p.add_argument("--language", choices=["en", "zh"], default="en")

    sub.add_parser(
        "finalize-summary",
        help="Validate + normalize summarized_papers.json written by the host LLM",
    )

    viz_p = sub.add_parser("viz", help="Run Skill 5 only (dashboard + optional Notion sync)")
    viz_p.add_argument("--skip-notion", action="store_true")

    sub.add_parser("report", help="Run Skill 4 only (briefing Markdown)")
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
    elif args.command == "summarize":
        run_skill3_summarize(
            top_n=args.top_n, mode=args.mode, language=args.language,
        )
        return 0
    elif args.command == "finalize-summary":
        run_finalize_summary()
        return 0
    elif args.command == "viz":
        run_skill5_viz(skip_notion=args.skip_notion)
        return 0
    elif args.command == "report":
        run_skill4_report()
        return 0
    elif args.command == "status":
        check_status()
        return 0
    else:
        check_status()
        return 0


if __name__ == "__main__":
    sys.exit(main())
