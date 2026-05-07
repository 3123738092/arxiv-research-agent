"""Generate Skill 4 daily briefing Markdown into shared_data/briefing.md.

Reads: papers (+ optional rankings, communities, embeddings, manifest) via shared.loader.
Does not import other skills — only JSON / numpy artifacts.
"""

from __future__ import annotations

import json
import math
import os
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

from shared.loader import (
    DATA_DIR,
    SkillInputMissingError,
    load_citation_edges,
    load_communities,
    load_embeddings,
    load_manifest,
    load_papers_list,
    load_rankings,
)

_STOP = frozenset(
    """
    the this with that from have been were they their which will would could
    about into such than then them these those some what when where while
    over under both each most more most other also only very much many few
    using used use based approach paper work study results model models data
    method methods learning proposed new show shows shown via for and not are
    but our can may has had was were being between among within without
    through during including included include includes including
    """.split()
)


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-zA-Z][a-zA-Z0-9\-]{3,}", (text or "").lower())


def _paper_text(p: dict) -> str:
    return f"{p.get('title', '')} {p.get('abstract', '')}"


def _dedupe_papers(papers: List[dict]) -> List[dict]:
    best: Dict[str, dict] = {}
    for p in papers:
        aid = p.get("arxiv_id")
        if not aid:
            continue
        base = aid.split("v")[0] if "v" in aid else aid
        cur = best.get(base)
        if cur is None:
            best[base] = p
            continue
        t_new = p.get("updated") or p.get("published") or ""
        t_old = cur.get("updated") or cur.get("published") or ""
        if t_new >= t_old:
            best[base] = p
    return list(best.values())


def _in_degree(edges: List[dict]) -> Counter:
    c: Counter = Counter()
    for e in edges:
        to_id = e.get("to")
        if to_id:
            c[to_id] += 1
    return c


def _composite_scores(
    papers: List[dict],
    edges: List[dict],
    rankings: Optional[List[dict]],
) -> Dict[str, float]:
    """Higher = more important for ordering."""
    if rankings:
        out: Dict[str, float] = {}
        for row in rankings:
            aid = row.get("arxiv_id")
            if not aid:
                continue
            pr = float(row.get("pagerank_score") or 0.0)
            intr = float(row.get("interest_score") or 0.0)
            rk = row.get("rank")
            rank_bonus = 1.0 / (1.0 + float(rk)) if rk is not None else 0.0
            out[aid] = pr + intr + rank_bonus
        return out

    indeg = _in_degree(edges)
    out = {}
    for p in papers:
        aid = p.get("arxiv_id")
        if not aid:
            continue
        cites = int(p.get("citation_count") or 0)
        out[aid] = cites + 0.5 * indeg.get(aid, 0)
    return out


def _ordered_papers(
    papers: List[dict], scores: Dict[str, float]
) -> List[dict]:
    return sorted(
        papers,
        key=lambda p: scores.get(p.get("arxiv_id", ""), 0.0),
        reverse=True,
    )


def _trend_for_prefix(
    papers: List[dict],
    scores: Dict[str, float],
    category_prefix: str,
) -> Tuple[str, List[str], List[str]]:
    """Return (paragraph, main_directions, heating_terms)."""
    prefix = category_prefix.strip()
    subset = [
        p
        for p in papers
        if prefix in (p.get("primary_category") or "")
        or any(
            (c or "").startswith(prefix) for c in (p.get("categories") or [])
        )
    ]
    if not subset:
        return (
            f"No papers tagged `{prefix}` in this run — trend section uses all categories.",
            [],
            [],
        )

    prim = Counter(
        (p.get("primary_category") or "unknown") for p in subset
    ).most_common(8)
    main_dirs = [f"{k} ({n})" for k, n in prim[:5]]

    # "Heating": terms enriched in top third vs rest by score
    ordered = _ordered_papers(subset, scores)
    n = max(1, len(ordered) // 3)
    top_set = set(p.get("arxiv_id") for p in ordered[:n])
    def term_counts(ps: Iterable[dict]) -> Counter:
        c: Counter = Counter()
        for p in ps:
            for w in _tokenize(_paper_text(p)):
                if w not in _STOP and not w.startswith("cs."):
                    c[w] += 1
        return c

    top_c = term_counts(p for p in subset if p.get("arxiv_id") in top_set)
    rest_c = term_counts(p for p in subset if p.get("arxiv_id") not in top_set)
    heat: List[Tuple[str, float]] = []
    for term, a in top_c.items():
        if a < 2:
            continue
        b = rest_c.get(term, 0)
        ratio = (a + 1) / (b + 1)
        if ratio >= 1.35:
            heat.append((term, ratio))
    heat.sort(key=lambda x: -x[1])
    heating = [t for t, _ in heat[:8]]

    para = (
        f"Among **{len(subset)}** papers in `{prefix}`, primary categories concentrate on: "
        + ", ".join(main_dirs[:4])
        + ". "
    )
    if heating:
        para += (
            "Lexically **rising** themes in the top-ranked third (vs the rest) include: "
            + ", ".join(f"`{h}`" for h in heating[:6])
            + "."
        )
    else:
        para += "No strong lexical surge vs baseline — corpus may be small or uniform."
    return para, main_dirs, heating


def _novelty_blurbs(
    top: Sequence[dict],
    embeddings: Optional[Tuple[np.ndarray, dict]],
) -> List[Tuple[str, str]]:
    """(arxiv_id, one-line why novel)."""
    if not top:
        return []
    blurbs: List[Tuple[str, str]] = []
    if embeddings is None:
        for p in top[:5]:
            aid = p.get("arxiv_id", "")
            cats = p.get("categories") or []
            blurbs.append(
                (
                    aid,
                    f"Topic mix {cats[:3]} differs from the batch mode — treat as exploratory until embeddings run.",
                )
            )
        return blurbs

    vecs, index = embeddings
    if vecs.size == 0:
        return _novelty_blurbs(top, None)

    rows = []
    ids = []
    for p in top:
        aid = p.get("arxiv_id")
        if not aid or aid not in index:
            continue
        r = index[aid]
        rows.append(vecs[int(r)])
        ids.append(aid)
    if not rows:
        return _novelty_blurbs(top, None)

    mat = np.stack(rows, axis=0)
    centroid = mat.mean(axis=0, keepdims=True)
    centroid = centroid / (np.linalg.norm(centroid) + 1e-9)
    norms = np.linalg.norm(mat, axis=1, keepdims=True) + 1e-9
    normed = mat / norms
    sim = (normed * centroid).sum(axis=1)
    dist = 1.0 - sim

    order = np.argsort(-dist)
    for j in order[:5]:
        aid = ids[int(j)]
        d = float(dist[int(j)])
        blurbs.append(
            (
                aid,
                f"Embedding is **{d:.2f}** away from today's centroid (1−cosine to mean direction) — more distinctive than neighbors.",
            )
        )
    return blurbs


def _interest_recommendations(
    papers: List[dict],
    scores: Dict[str, float],
    query: str,
    top_k: int = 5,
) -> List[Tuple[dict, str, float]]:
    """Return [(paper, relevance_label, blended_score), ...]."""
    q_tokens = set(_tokenize(query))
    if not q_tokens:
        return []

    ranked = _ordered_papers(papers, scores)
    out: List[Tuple[dict, str, float]] = []
    for p in ranked:
        pt = set(_tokenize(_paper_text(p)))
        inter = q_tokens & pt
        if not inter:
            continue
        overlap = len(inter) / max(len(q_tokens), 1)
        base = scores.get(p.get("arxiv_id", ""), 0.0)
        blended = overlap * 10.0 + math.log1p(max(base, 0.0))
        if overlap >= 0.35:
            label = "highly relevant"
        elif overlap >= 0.2:
            label = "partially relevant"
        else:
            label = "tangential"
        out.append((p, label, blended))
    out.sort(key=lambda x: -x[2])
    return out[:top_k]


def _idea_bullets(
    heating: List[str],
    top_titles: Sequence[str],
) -> List[str]:
    a = heating[0] if heating else "representation learning"
    b = heating[1] if len(heating) > 1 else "efficient finetuning"
    t0 = top_titles[0] if top_titles else "the top-ranked method"
    ideas = [
        f"Combine **{a}** + **{b}** in a single training stage to trade off quality and compute.",
        f"Take the core idea from «{t0[:80]}» and stress-test it on a **long-tail** subdomain with scarce labels.",
        f"Apply **{a}**-style objectives to a **video / 3D** benchmark where similar papers are still sparse (gap in today's dump).",
    ]
    return ideas


def _fmt_paper_line(rank: int, p: dict) -> str:
    aid = p.get("arxiv_id", "")
    title = (p.get("title") or "").replace("\n", " ")
    url = p.get("arxiv_url") or f"https://arxiv.org/abs/{aid}"
    return f"{rank}. [{title}]({url}) — `{aid}`"


def run_briefing_report(
    data_dir: Optional[Path] = None,
    output_path: Optional[Path] = None,
    interest_query: Optional[str] = None,
    trend_category_prefix: str = "cs.CV",
) -> Path:
    """Write briefing Markdown; return path written."""
    base = Path(data_dir or DATA_DIR)
    out = Path(output_path or (base / "briefing.md"))

    papers_raw = load_papers_list(data_dir=base)
    papers = _dedupe_papers(papers_raw)

    manifest = None
    try:
        manifest = load_manifest(data_dir=base)
    except SkillInputMissingError:
        manifest = {}

    edges = []
    try:
        edges = load_citation_edges(data_dir=base)
    except SkillInputMissingError:
        pass

    rankings = load_rankings(data_dir=base)
    communities = load_communities(data_dir=base) or []

    embeddings = None
    try:
        embeddings = load_embeddings(data_dir=base)
    except SkillInputMissingError:
        embeddings = None

    scores = _composite_scores(papers, edges, rankings)
    ordered = _ordered_papers(papers, scores)

    interest = (interest_query or os.environ.get("BRIEFING_INTEREST") or "").strip()
    if not interest and manifest:
        kws = (manifest.get("params") or {}).get("keywords") or []
        if kws:
            interest = " ".join(str(k) for k in kws[:5])

    trend_para, main_dirs, heating = _trend_for_prefix(
        papers, scores, trend_category_prefix
    )
    novelty = _novelty_blurbs(ordered[:15], embeddings)
    recs = _interest_recommendations(papers, scores, interest) if interest else []
    ideas = _idea_bullets(heating, [p.get("title") or "" for p in ordered[:3]])

    ts = manifest.get("timestamp") if manifest else None
    dr = (manifest.get("params") or {}).get("date_range") if manifest else None
    header_date = ts or datetime.utcnow().strftime("%Y-%m-%dT%H:%MZ")

    lines: List[str] = []
    lines.append(f"# Daily arXiv Briefing\n\n_Generated: {header_date}_\n")
    if dr:
        lines.append(
            f"_Date range:_ `{dr.get('start')}` → `{dr.get('end')}`\n"
        )

    lines.append("## TL;DR\n")
    lines.append(f"- **Papers (deduped):** {len(papers)}\n")
    lines.append(
        f"- **Ranking source:** {'`rankings.json` (Skill 2)' if rankings else '_fallback: citations + inbound citation edges_'}\n"
    )
    if communities:
        lines.append(
            f"- **Communities:** {len(communities)} clusters (from `communities.json`)\n"
        )
    else:
        lines.append(
            "- **Communities:** _none — run Skill 3 for co-authorship clusters_\n"
        )

    lines.append("\n## Top papers\n")
    for i, p in enumerate(ordered[:10], start=1):
        lines.append(_fmt_paper_line(i, p) + "\n")

    lines.append("\n## Trend Summary\n")
    lines.append(f"{trend_para}\n")
    if main_dirs:
        lines.append("\n**Primary directions (counts):**\n")
        for d in main_dirs[:6]:
            lines.append(f"- {d}\n")

    lines.append("\n## Novelty Insight\n")
    lines.append("_Why it stands out relative to today's batch (embedding centroid when available):_\n")
    for aid, blurb in novelty[:5]:
        lines.append(f"- **`{aid}`** — {blurb}\n")

    lines.append("\n## Personalized Recommendations\n")
    if interest:
        lines.append(f'Based on your interest in **"{interest}"**:\n')
        if recs:
            for p, label, _ in recs:
                aid = p.get("arxiv_id")
                title = (p.get("title") or "")[:120]
                lines.append(f"- **{aid}** — _{label}_ — {title}\n")
            lines.append("\n**Suggested reading priority:**\n")
            for i, (p, _, _) in enumerate(recs[:3], start=1):
                lines.append(f"{i}. `{p.get('arxiv_id')}`\n")
        else:
            lines.append(
                "_No lexical overlap with corpus — widen keywords or rerun Skill 1 with broader queries._\n"
            )
    else:
        lines.append(
            "Set `BRIEFING_INTEREST` or pass `interest_query` / pipeline keywords in manifest to enable this block.\n"
        )

    lines.append("\n## Idea Generator\n")
    for i, idea in enumerate(ideas, start=1):
        lines.append(f"{i}. {idea}\n")

    lines.append("\n## Action layer\n")

    top_ids = [p.get("arxiv_id") for p in ordered[:5] if p.get("arxiv_id")]
    id_a = top_ids[0] if top_ids else "top-1"
    id_b = top_ids[1] if len(top_ids) > 1 else id_a
    id_c = top_ids[2] if len(top_ids) > 2 else id_b
    comm_note = (
        f"Community **{communities[0].get('label') or communities[0].get('community_id')}**"
        if communities
        else "the largest co-authorship community (Skill 3)"
    )

    lines.append("\n### Reading Plan\n")
    top5_txt = ", ".join(f"`{x}`" for x in top_ids) or "_no papers_"
    lines.append(
        "\n```\n"
        "## 📚 Suggested Reading Plan\n\n"
        "If you have 2 hours:\n\n"
        f"- 30 min: read summaries of top 5 papers ({top5_txt})\n"
        "- 60 min: deep dive into Paper 1 & 2 in the ranked list\n"
        f"- 30 min: explore {comm_note} trend\n"
        "```\n"
    )

    lines.append("\n### Follow-up Questions\n")
    lines.append(
        "\n```\n"
        "## ❓ You may want to ask:\n\n"
        f'- "Explain `{id_c}` in detail"\n'
        f'- "Compare `{id_a}` and `{id_b}`"\n'
        '- "Which paper is most implementable?"\n'
        "```\n"
    )

    if communities:
        lines.append("\n## Research communities (Skill 3)\n")
        for c in sorted(
            communities,
            key=lambda x: int(x.get("size") or 0),
            reverse=True,
        )[:5]:
            label = c.get("label") or c.get("community_id")
            size = c.get("size")
            lines.append(f"- **{label}** — size {size}\n")

    viz_dir = base / "visualizations"
    if viz_dir.is_dir():
        figures = sorted(
            [p for p in viz_dir.iterdir() if p.suffix.lower() in {".png", ".svg", ".html"}]
        )[:12]
        if figures:
            lines.append("\n## Visualizations (Skill 5)\n")
            for fig in figures:
                lines.append(f"- `{fig.relative_to(base).as_posix()}`\n")

    lines.append(
        "\n---\n\n_Data contract: `shared/loader.py` + optional "
        "`rankings.json`, `communities.json`, `visualizations/`._\n"
    )

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(lines), encoding="utf-8")

    # Machine-readable hook for downstream agents
    hook = {
        "generated_at": header_date,
        "top_arxiv_ids": [p.get("arxiv_id") for p in ordered[:15]],
        "interest_query": interest or None,
        "trend_category_prefix": trend_category_prefix,
        "follow_up_prompts": [
            f"Explain {id_c} in detail",
            f"Compare {id_a} and {id_b}",
            "Which paper is most implementable?",
        ],
    }
    hook_path = out.with_name("briefing.hooks.json")
    hook_path.write_text(json.dumps(hook, indent=2), encoding="utf-8")

    return out


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Write shared_data/briefing.md")
    ap.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="Directory with papers.json (default: shared_data/)",
    )
    ap.add_argument("--out", type=Path, default=None, help="Output briefing.md path")
    ap.add_argument(
        "--interest",
        default=None,
        help="Personalization query (overrides BRIEFING_INTEREST)",
    )
    ap.add_argument(
        "--trend-prefix",
        default="cs.CV",
        help="arXiv category prefix for Trend Summary (e.g. cs.CV)",
    )
    args = ap.parse_args()
    p = run_briefing_report(
        data_dir=args.data_dir,
        output_path=args.out,
        interest_query=args.interest,
        trend_category_prefix=args.trend_prefix,
    )
    print(f"Wrote {p}")
