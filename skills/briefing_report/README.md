# Skill 4: Briefing Report

Generate a daily arXiv briefing report from shared artifacts in `shared_data/`.

This skill is **file-contract based**: it does not call external APIs and does not import implementation code from other skills.

## What This Skill Does

- Reads paper data from `shared_data/`
- Builds ranked summaries (with fallback logic)
- Produces:
  - `shared_data/briefing.md`
  - `shared_data/briefing.hooks.json` (machine-readable prompts/ids for agent loop)

## Implemented Sections in `briefing.md`

- TL;DR
- Top papers
- Trend Summary
- Novelty Insight
- Personalized Recommendations
- Idea Generator
- Action layer
  - Reading Plan
  - Follow-up Questions
- Optional:
  - Research communities (if `communities.json` exists)
  - Visualizations list (if `visualizations/` exists)

## Input/Output Contract

### Required Input

- `shared_data/papers.json`

### Optional Inputs

- `shared_data/manifest.json`
- `shared_data/edges/citations.json`
- `shared_data/embeddings/paper_vecs.npy`
- `shared_data/embeddings/index.json`
- `shared_data/rankings.json` (from Skill 2)
- `shared_data/communities.json` (from Skill 3)
- `shared_data/visualizations/` (from Skill 5)

### Outputs

- `shared_data/briefing.md`
- `shared_data/briefing.hooks.json`

## How Ranking Works

- If `rankings.json` exists:
  - Uses `pagerank_score`, `interest_score`, and `rank`
- Otherwise fallback:
  - Uses `citation_count` + inbound citation edge degree

## Trend Category Prefix

Default trend prefix is `cs.CV` via:

- `run_briefing_report(..., trend_category_prefix="cs.CV")`

Override via CLI:

```bash
python -m skills.briefing_report.generate --trend-prefix cs.CL
```

## Usage

From project root:

```bash
python -m skills.briefing_report.generate
```

With personalization and custom trend focus:

```bash
python -m skills.briefing_report.generate --interest "LoRA fine-tuning" --trend-prefix cs.CV
```

Custom data directory / output path:

```bash
python -m skills.briefing_report.generate --data-dir shared_data --out shared_data/briefing.md
```

## Python API

```python
from skills.briefing_report import run_briefing_report

run_briefing_report(
    data_dir=None,                # default shared_data/
    output_path=None,             # default shared_data/briefing.md
    interest_query="LoRA",        # optional
    trend_category_prefix="cs.CV" # optional
)
```

## Tests

Run unit test:

```bash
python -m unittest skills.briefing_report.tests.test_generate -v
```

This verifies the skill can generate both markdown and hook JSON with fixture-like temporary data.

## Integration Notes (for teammates)

- Skill 2 should write `shared_data/rankings.json` with fields:
  - `arxiv_id`, `pagerank_score`, `interest_score`, `rank`
- Skill 3 should write `shared_data/communities.json` with fields:
  - `community_id`, `label`, `size`, `members`
- Skill 5 should write figures into:
  - `shared_data/visualizations/` (`.png`, `.svg`, `.html`)

As long as these files exist and follow the schema, Skill 4 picks them up automatically.
