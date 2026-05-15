---
name: paper-summarizer
description: "Extract one-line summary, key contributions, methods and keywords for the top-N ranked arXiv papers. The host LLM running this Agent performs the summarization itself in-context — this skill prepares the request and validates the output. Skill 3 of 5 in the arXiv Research Briefing Agent."
version: 0.3.0
author: 成员 C
tags: [arxiv, summarization, llm, research, agent-skill]
---

# paper_summarizer

Skill 3 of the *arXiv Research Briefing Agent*.

Consumes ranked papers and produces structured summaries ready for report
rendering and visualization. **The host LLM (the model running this Agent)
does the summarization itself; this skill does NOT call any external API.**

## Two-step host-LLM flow

1. **Prepare** — `python -m skills.paper_summarizer.scripts.prepare --top-n 10 --language en --shared-data /path/to/workspace/shared_data`
   - Reads `shared_data/ranked_papers.json` (sorted by relevance + novelty).
   - Writes `shared_data/summarize_request.json` with: system prompt, user
     prompt, output schema, and the top-N paper objects.
2. **Host LLM summarizes** — the Agent's host model (Claude in WorkBuddy /
   Claude Code) reads `summarize_request.json`, generates summaries
   following the system prompt, and writes
   `shared_data/summarized_papers.json` either as a bare list or as the
   canonical envelope `{count, summarized_count, model, mode, language, papers}`.
3. **Finalize** — `python -m skills.paper_summarizer.scripts.finalize --shared-data /path/to/workspace/shared_data` or
   `python arxiv_agent.py finalize-summary`
   - Normalizes summary fields, merges upstream paper metadata, re-emits
     the canonical envelope, reports any missing summaries.

## Inputs

`shared_data/ranked_papers.json` — list of paper objects with at least:
- `title`, `abstract`, `arxiv_url`, `pdf_url`
- `relevance_score`, `novelty_score` (from Skill 2)

## Outputs

`shared_data/summarized_papers.json` — same papers, with top-N augmented by:
- `one_line_summary` — str
- `key_contributions` — list[str], 2-3 items
- `methods` — list[str]
- `keywords` — list[str], 3-5 items

Plus metadata: `count`, `summarized_count`, `model`, `mode`, `language`.

## How it works (host-LLM mode)

1. `prepare.py` sorts `ranked_papers.json` by `relevance_score + novelty_score`,
   takes top-N, and packages them with the system prompt + output schema into
   `shared_data/summarize_request.json`.
2. The host LLM (running this Agent) reads the request file, generates the
   four summary fields per paper in its own conversation context, and writes
   `shared_data/summarized_papers.json`.
3. `finalize.py` re-reads that file (tolerates bare list or envelope shape),
   normalizes the four summary fields, merges upstream metadata back in, and
   re-emits the canonical envelope.

## Why this design

- **No external API keys**: the host model already has its conversation API
  loaded; calling another Anthropic endpoint from a sub-skill would double the
  spend and make the skill require credentials of its own.
- **Schema normalization**: downstream Skills (`briefing_report`,
  `papers-analysis-visualizer`) can rely on the four summary fields always
  being present with correct types.
- **Tolerant ingestion**: `finalize.py` accepts either a bare list or an
  envelope, so the host LLM can write whichever is easier to produce.

## Shared data output path

All three entry points (`prepare`, `finalize`, `pipeline`) resolve `shared_data/` with the same priority:

| Priority | Source | Example |
|----------|--------|---------|
| 1 (highest) | `--shared-data` CLI arg | `--shared-data "C:/Users/31237/WorkBuddy/20260505170223/shared_data"` |
| 2 | `WORKBUDDY_SHARED_DATA` env var | `export WORKBUDDY_SHARED_DATA="C:/Users/31237/WorkBuddy/20260505170223/shared_data"` |
| 3 (fallback) | `PROJECT_ROOT/shared_data/` | auto-detected by tree walk |

> ⚠️ **Silent data loss warning**: Without either `--shared-data` or `WORKBUDDY_SHARED_DATA`,
> `prepare` and `finalize` fall back to `PROJECT_ROOT/shared_data/` which is the source
> tree (`D:\桌面\arxiv-research-agent/skills/shared_data/`), **not** your workspace.
> Always specify explicitly when running from the agent.

## Standalone (legacy, optional)

The original Anthropic-API path is preserved in `summarizer/core.py` +
`scripts/pipeline.py` and remains usable if you have an API key and want to
run Skill 3 outside an LLM session. The Agent itself no longer takes that
path.

```bash
pip install -r requirements.txt   # only if you want the legacy path
export ANTHROPIC_API_KEY="sk-ant-..."
python -m skills.paper_summarizer.scripts.pipeline
```

## Testing

```bash
python -m pytest tests/ -q
```

20 unit + integration tests. `test_core_integration.py` monkey-patches the
Anthropic client so tests run fully offline.
