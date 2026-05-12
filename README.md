# arXiv Research Briefing Agent

A daily, host-LLM-driven multi-skill agent that turns the arXiv firehose into a curated research briefing.

The agent is **one orchestrator + five skills**, communicating through a star-schema shared data layer (`shared_data/`). No skill imports another skill's Python modules; everything flows through versioned JSON files.

**SNA Final Project — Topic 2 (Daily arXiv Research Briefing Agent).**

---

## Architecture

```
                    ┌──────────────────────────┐
                    │   arxiv_agent.py (CLI)   │
                    │   unified orchestrator   │
                    └────────────┬─────────────┘
                                 │
         ┌───────────┬───────────┼───────────┬─────────────┐
         ▼           ▼           ▼           ▼             ▼
   Skill 1       Skill 2     Skill 3      Skill 4       Skill 5
   data-         paper-      paper-       briefing-     papers-
   collector     ranker      summarizer   report        analysis-viz
         │           │           │           │             │
         └───────────┴──────►shared_data/◄───┴─────────────┘
                  (papers, edges, embeddings, rankings,
                   summaries, dashboard.html, briefing.md)
```

Pipeline order: **1 → 2 → 3 → 4 → 5**

Skill 3 has a **two-step host-LLM gate** between `prepare` and `finalize`: the host model running this Agent (Claude Code / WorkBuddy) summarizes papers in-context using its own conversation API. No extra LLM API key is required.

---

## Skill Inventory

| # | Skill | Directory | Responsibility |
|---|-------|-----------|----------------|
| 1 | data_collector | `skills/data_collector/` | Fetch arXiv, embed (MiniLM), build semantic similarity graph + coauthorship graph |
| 2 | paper_ranker | `skills/paper_ranker/` | PageRank on similarity graph + interest/novelty scoring |
| 3 | paper_summarizer | `skills/paper_summarizer/` | Prepare host-LLM request → summarize in-context → finalize/normalize |
| 4 | briefing_report | `skills/briefing_report/` | Render Markdown daily briefing |
| 5 | papers-analysis-visualizer | `skills/papers-analysis-visualizer/` | HTML dashboard + optional Notion sync |

Each skill ships its own `SKILL.md` manifest and is independently runnable.

---

## Quickstart

```bash
# 1. install dependencies
pip install -r requirements.txt

# 2. run the full daily pipeline
python arxiv_agent.py daily

# Outputs you can inspect:
#   shared_data/manifest.json          → run params + counts
#   shared_data/rankings.json          → ranked paper list
#   shared_data/summarize_request.json → host-LLM request (Skill 3 prepare)
#   shared_data/summarized_papers.json → host-LLM output (after finalize)
#   shared_data/briefing.md            → daily Markdown briefing
#   output/dashboard.html              → interactive dashboard
```

### Running individual skills

```bash
python arxiv_agent.py fetch --categories cs.CL --keywords agent
python arxiv_agent.py rank --interest "agent skill tool use LLM"
python arxiv_agent.py summarize --top-n 10 --language en   # Skill 3 prepare
# (host LLM writes shared_data/summarized_papers.json)
python arxiv_agent.py finalize-summary                     # Skill 3 finalize
python arxiv_agent.py viz --skip-notion                    # Skill 5
python arxiv_agent.py report                               # Skill 4
python arxiv_agent.py status                               # Inspect shared_data
```

---

## Skill 3 — Host-LLM Flow

```
[prepare]   python arxiv_agent.py summarize --top-n 10
            └─► writes shared_data/summarize_request.json
                  (system+user prompt, output schema, top-N papers)

[host LLM]  Reads summarize_request.json,
            generates one_line_summary / key_contributions / methods / keywords,
            writes shared_data/summarized_papers.json

[finalize]  python arxiv_agent.py finalize-summary
            └─► normalizes fields, merges upstream metadata,
                re-emits canonical envelope
                {count, summarized_count, model, mode, language, papers[]}
```

A legacy standalone Anthropic-API path remains in `skills/paper_summarizer/summarizer/core.py` for offline use, but the agent itself does not invoke it.

---

## Shared Data Contract

All inter-skill communication goes through `shared_data/`. See `shared/loader.py` for the typed loading API.

| Producer | File | Shape |
|----------|------|-------|
| Skill 1 | `papers.json` | `[{arxiv_id, title, abstract, embedding_row, …}]` |
| Skill 1 | `authors.json` | `[{author_id, name}]` |
| Skill 1 | `edges/similarity.json` | `[{from, to, weight}]` (cosine top-K from MiniLM embeddings) |
| Skill 1 | `edges/coauthorship.json` | `[{author_a, author_b, weight}]` |
| Skill 1 | `embeddings/paper_vecs.npy` | float32 (N, 384) |
| Skill 1 | `manifest.json` | `{run_id, params, counts, errors, warnings}` |
| Skill 2 | `rankings.json` | `[{arxiv_id, pagerank_score, interest_score, novelty_score, rank}]` |
| Skill 2 | `ranked_papers.json` | Augmented papers (upstream order) with `relevance_score`/`novelty_score` |
| Skill 3 | `summarize_request.json` | Host-LLM input (prompt + schema + top-N papers) |
| Skill 3 | `summarized_papers.json` | `{count, summarized_count, model, mode, language, papers[…with one_line_summary, key_contributions, methods, keywords]}` |
| Skill 5 | `output/dashboard.html` | Standalone HTML dashboard |
| Skill 5 | `output/notion_mapping.json` | Optional Notion page mapping |
| Skill 4 | `briefing.md` | Daily briefing in Markdown |

---

## Configuration

Optional environment variables:

| Var | Used By | Purpose |
|-----|---------|---------|
| `HF_TOKEN` | Skill 1 | Higher rate limits when downloading the MiniLM embedder |
| `NOTION_API_TOKEN` | Skill 5 | Enables Notion sync (skipped if unset) |
| `NOTION_PARENT_PAGE_ID` / `NOTION_DATABASE_ID` | Skill 5 | Notion target |

No LLM API key is needed for Skill 3 — the host model already has a conversation API loaded.

---

## Project Layout

```
arxiv-research-agent/
├── arxiv_agent.py              # Unified orchestrator (CLI entry)
├── AGENTS.md                   # Agent manifest (host registry)
├── README.md                   # This file
├── requirements.txt
├── shared/                     # shared loader (no skill imports)
│   └── loader.py
├── shared_data/                # ← all inter-skill JSON (gitignored)
├── output/                     # dashboard.html, notion_mapping.json (gitignored)
└── skills/
    ├── data_collector/
    ├── paper_ranker/
    ├── paper_summarizer/
    ├── briefing_report/
    └── papers-analysis-visualizer/
```

---

## Design Constraints

- **No implementation imports between skills** — only data dependencies via JSON files
- **Schema-first** — every skill validates its inputs and emits a documented shape
- **Idempotent** — re-running a skill overwrites its own output files
- **Fail-fast** — missing inputs raise clear errors; pipeline skips downstream when Skill 1 returns 0 papers
- **Host-LLM friendly** — Skill 3 piggybacks on the conversation model rather than spending a second API budget

---

## License

Educational project for SNA Final Project — Topic 2.
