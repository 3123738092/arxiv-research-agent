---
name: briefing_report
description: >
  Generate a daily arXiv briefing from shared_data artifacts, including trend
  summary, novelty insight, personalized recommendations, and action-oriented
  reading plan/follow-up prompts.
version: 1.0.0
author: Liu
tags: [report, briefing, arxiv, markdown, insight]
trigger_keywords:
  - generate briefing
  - daily briefing
  - report
  - 简报
  - 生成简报
  - 今日简报
metadata:
  openclaw:
    requires:
      bins:
        - python3
      env: []
    primaryEnv: BRIEFING_INTEREST
    envVars:
      - name: BRIEFING_INTEREST
        required: false
        description: >
          Optional interest query used by personalized recommendations,
          e.g. "LoRA fine-tuning".
---

# Briefing Report Skill (Skill 4)

## Purpose

This skill converts multi-skill outputs in `shared_data/` into a user-facing
daily research briefing.

It is a **file-contract skill**:

- Reads shared artifacts from other skills
- Does local analytics and markdown composition
- Writes report artifacts back to `shared_data/`
- Does **not** call external LLM/API services

## When to Use This Skill

Invoke when the user asks to:

- Generate the daily report/briefing
- Summarize today's papers with trends and recommendations
- Produce action items (reading plan, follow-up questions)

Do NOT invoke when the user asks to:

- Fetch/collect new papers (use Skill 1)
- Compute graph ranking/community from scratch (use Skill 2/3)
- Generate charts/figures only (use Skill 5)

## Inputs

### Required

- `shared_data/papers.json`

### Optional (auto-detected if present)

- `shared_data/manifest.json`
- `shared_data/edges/citations.json`
- `shared_data/embeddings/paper_vecs.npy`
- `shared_data/embeddings/index.json`
- `shared_data/rankings.json` (Skill 2)
- `shared_data/communities.json` (Skill 3)
- `shared_data/visualizations/` (Skill 5)

## Outputs

- `shared_data/briefing.md` (main report)
- `shared_data/briefing.hooks.json` (agent-loop helper payload)

## Core Behaviors

1. Deduplicate papers by `arxiv_id` (prefer newest updated/published record)
2. Rank papers:
   - Use `rankings.json` if available
   - Otherwise fallback to `citation_count + inbound-degree`
3. Produce sections:
   - TL;DR
   - Top papers
   - Trend Summary
   - Novelty Insight
   - Personalized Recommendations
   - Idea Generator
   - Action layer (Reading Plan + Follow-up Questions)
4. Append optional sections when inputs exist:
   - Research communities
   - Visualizations list

## Invocation

### Python API

```python
from skills.briefing_report import run_briefing_report

run_briefing_report(
    data_dir=None,
    output_path=None,
    interest_query="LoRA fine-tuning",
    trend_category_prefix="cs.CV",
)
```

### CLI

From project root:

```bash
python -m skills.briefing_report.generate --interest "LoRA fine-tuning" --trend-prefix cs.CV
```

## Parameters

- `interest_query`:
  - Manual personalization query
  - Fallback order: function arg -> `BRIEFING_INTEREST` -> `manifest.params.keywords`
- `trend_category_prefix`:
  - Category focus for trend section
  - Default: `cs.CV`

## Failure and Fallback

- If `papers.json` is missing: raise `SkillInputMissingError`
- If optional files are missing:
  - Keep generating report with available data
  - Use fallback ranking logic
  - Omit optional sections with clear text hints

## Testing

```bash
python -m unittest skills.briefing_report.tests.test_generate -v
```

This test verifies `briefing.md` and `briefing.hooks.json` are generated from
minimal fixture-like data.
