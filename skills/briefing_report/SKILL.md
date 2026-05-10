---
name: briefing_report
description: "Render the daily Markdown briefing for the arXiv Research Briefing Agent. Reads ranked + summarized papers from shared_data/ and writes shared_data/briefing.md with top-N picks, key contributions, methods, keywords, and trend analysis. Trigger when user asks: '生成今天的简报', '导出 Markdown 简报', 'write the briefing', 'render daily report', 'regenerate briefing.md', 'give me the Markdown of today's papers'. This is Skill 4 of 5 in the agent — final output stage. Do NOT use this skill to fetch or rank papers; only to render the report once shared_data/ already contains rankings + summaries."
version: 1.0.0
author: Han
agent_created: true
tags: [arxiv, briefing, markdown, report, daily-digest, social-network-analysis]
metadata:
  openclaw:
    requires:
      bins:
        - python3
      env: []
---

# Briefing Report Skill — arXiv Research Briefing Agent

## Purpose

You are the **report rendering module** (Skill 4 of 5) for the Daily arXiv Research Briefing Agent. Your job is to read ranked + summarized paper data from `shared_data/` and produce a single, human-readable Markdown briefing at `shared_data/briefing.md`.

You do NOT fetch papers, do NOT rank, do NOT summarize. Those are upstream skills (1–3). You only render.

## When to invoke

Use this skill when the user asks for:

- "Generate / render / write the daily briefing"
- "Regenerate `briefing.md`"
- "Give me a Markdown report of today's papers"
- "导出今日简报" / "把今天的论文写成 Markdown"
- The final stage of a full pipeline run (orchestrated by the root agent SKILL.md)

Do NOT activate when the user wants to (re)fetch, (re)rank, or (re)summarize — invoke `data_collector`, `paper_ranker`, or `paper_summarizer` instead.

## Inputs (from `shared_data/`)

| File | Required | Source skill | Purpose |
|------|:--:|------|------|
| `papers.json` / `raw_papers.json` | ✅ | Skill 1 | Paper metadata (title, abstract, authors, …) |
| `manifest.json` | ✅ | Skill 1 | Run params, counts, errors |
| `rankings.json` | ✅ | Skill 2 | PageRank + interest + novelty scores |
| `summarized_papers.json` | ⚠️ recommended | Skill 3 | Per-paper `one_line_summary` / `key_contributions` / `methods` / `keywords` |
| `edges/citations.json` | optional | Skill 1 | For trend / centrality enrichment |
| `embeddings/paper_vecs.npy` | optional | Skill 1 | For topic clustering in the trend section |
| `communities.json` | optional | (legacy) | Skipped if absent |

If `summarized_papers.json` is missing, the briefing falls back to abstract excerpts (lower quality but non-fatal).

## Output

`shared_data/briefing.md` — single Markdown file with:

- **Header**: date, run_id, paper count, top theme
- **Top-N papers**: title, authors, arxiv link, scores, `one_line_summary`, `key_contributions`, `methods`, `keywords`
- **Trend analysis**: top keywords / categories from the corpus
- **Manifest summary**: counts, warnings, errors

## How to invoke

### Recommended — via the agent orchestrator

```bash
python arxiv_agent.py report
```

This calls `run_briefing_report()` with default arguments and writes `shared_data/briefing.md`.

### Direct (Python) — for testing

```python
from pathlib import Path
from skills.briefing_report.generate import run_briefing_report

out = run_briefing_report(
    data_dir=Path("shared_data"),
    output_path=Path("shared_data/briefing.md"),
    interest_query="agent skill tool use LLM",   # optional, biases the trend analysis
    trend_category_prefix="cs.CV",                # optional, focus trend section on this category
)
print(f"Wrote briefing to: {out}")
```

## Failure modes

- **`papers.json` missing** → raises `SkillInputMissingError`. Run Skill 1 (`fetch`) first.
- **`rankings.json` missing** → raises `SkillInputMissingError`. Run Skill 2 (`rank`) first.
- **`summarized_papers.json` missing** → no error; briefing renders with abstract excerpts (degraded quality). Tell the user to run Skill 3 (`summarize` + `finalize-summary`) for full quality.
- **`embeddings/paper_vecs.npy` missing** → trend section omitted; rest of briefing renders normally.

## Constraints

- **Do not import other skills' Python modules.** Read everything via local `_io.py`.
- **Idempotent.** Re-running overwrites `briefing.md` in place.
- **No external API calls.** All rendering is local string manipulation.
- **No emoji** in output unless explicitly requested by the user.

## Testing

```bash
python -m pytest skills/briefing_report/tests/ -q
```

## Position in the agent

| Stage | Skill | Output |
|-------|-------|--------|
| 1 | data_collector | `papers.json`, `edges/*`, `embeddings/*`, `manifest.json` |
| 2 | paper_ranker | `rankings.json`, `ranked_papers.json` |
| 3 | paper_summarizer | `summarize_request.json` → host-LLM mid-step → `summarized_papers.json` |
| 5 | papers-analysis-visualizer | `output/dashboard.html` |
| **4** | **briefing_report (this skill)** | **`briefing.md`** |

See `AGENTS.md` at repo root for the full agent contract.
