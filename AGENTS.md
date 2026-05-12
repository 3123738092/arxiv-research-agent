---
name: arxiv-research-agent
description: Daily arXiv Research Briefing Agent — host-LLM driven multi-skill agent that fetches, ranks, summarizes, visualizes, and reports on daily arXiv papers.
version: 1.1.0
skills:
  - data_collector
  - paper_ranker
  - paper_summarizer
  - papers-analysis-visualizer
  - briefing_report
pipeline:
  order: [data_collector, paper_ranker, paper_summarizer, briefing_report, papers-analysis-visualizer]
---

# arXiv Research Briefing Agent

Daily arXiv ingestion, ranking, host-LLM summarization, dashboard visualization, and report generation.

> **Entry point for natural-language invocation:** [`SKILL.md`](./SKILL.md) at repo root.
> The host LLM (Claude Code / WorkBuddy / OpenClaw) matches the user's request against
> the root `SKILL.md` frontmatter, then follows its 7-step recipe to drive the 5 sub-skills.
> AGENTS.md (this file) is the **registry-facing manifest**; the runtime entry point is `SKILL.md`.

## Skill Inventory

| # | Skill | Directory | Purpose |
|---|-------|-----------|---------|
| 1 | **data_collector** | `skills/data_collector/` | Fetch arXiv papers, enrich with Semantic Scholar, embed (MiniLM), build star-schema graphs → `shared_data/` |
| 2 | **paper_ranker** | `skills/paper_ranker/` | PageRank on citation graph + interest/novelty scoring → `rankings.json`, `ranked_papers.json` |
| 3 | **paper_summarizer** | `skills/paper_summarizer/` | Two-step host-LLM flow: prepare request → host LLM summarizes in-context → finalize/normalize |
| 4 | **briefing_report** | `skills/briefing_report/` | Generate Markdown daily briefing with top papers and one-line summaries |
| 5 | **papers-analysis-visualizer** | `skills/papers-analysis-visualizer/` | Build interactive HTML dashboard (top papers, keywords, history); optional Notion sync |

## Execution Order

Skills have **data dependencies** (not implementation imports):

```
Skill 1 (data_collector) ──► shared_data/ (papers, authors, edges, embeddings)
                                 │
                                 ▼
                          Skill 2 (paper_ranker) ──► rankings.json, ranked_papers.json
                                 │
                                 ▼
                          Skill 3 (paper_summarizer)
                          ├─ prepare → summarize_request.json
                          ├─ HOST LLM summarizes in-context
                          └─ finalize → summarized_papers.json
                                 │
                          ┌──────┴──────┐
                          ▼             ▼
                     Skill 4 (briefing)   Skill 5 (viz)
                     briefing.md  dashboard.html
```

- Skill 1 MUST run first (produces all data)
- Skill 2 runs after Skill 1
- Skill 3 has a **two-step host-LLM gate** between `prepare` and `finalize`
- Skills 4 and 5 read finalized summaries

## Skill 3 — Host-LLM Flow (Important)

Skill 3 does **NOT** call any external LLM API. Summarization is performed by the host model running this Agent (Claude Code / WorkBuddy).

```
[prepare]   python -m skills.paper_summarizer.scripts.prepare --top-n 10
            └─► writes shared_data/summarize_request.json (system+user prompt + top-N papers)

[host LLM]  Reads summarize_request.json, generates summaries in-context,
            writes shared_data/summarized_papers.json (bare list or canonical envelope)

[finalize]  python arxiv_agent.py finalize-summary
            └─► normalizes fields, merges upstream metadata, re-emits canonical envelope
```

A legacy standalone Anthropic-API path remains in `skills/paper_summarizer/summarizer/core.py` but is not used by the agent.

## Intent Routing Table

| User Says | Route To | Trigger |
|-----------|----------|---------|
| "fetch today's papers" / "抓取论文" | Skill 1 | Keywords: fetch, arXiv, 抓取, 论文 |
| "rank papers about X" / "哪些论文最重要" | Skill 2 | Keywords: rank, PageRank, 重要, 排名 |
| "summarize top papers" / "总结论文" | Skill 3 | Keywords: summarize, summary, 总结, 摘要 |
| "build dashboard" / "可视化" | Skill 5 | Keywords: visualize, dashboard, chart, 可视化 |
| "generate daily briefing" / "生成简报" | Skill 4 | Keywords: report, briefing, 简报, 报告 |
| "daily briefing" / "今日简报" | Pipeline | Run Skills 1→2→3→4→5 in order |

## Shared Data Contract

All inter-skill communication goes through `shared_data/`. Each skill owns its `_io.py` for typed data loading. **No skill imports another skill's Python modules.**

### Files produced by Skill 1 (data_collector)

| File | Type | Contents |
|------|------|----------|
| `papers.json` | Fact | `[{arxiv_id, title, abstract, citation_count, embedding_row, ...}]` |
| `authors.json` | Dimension | `[{author_id, name, s2_author_id, ...}]` |
| `affiliations.json` | Dimension | `[{affiliation_id, name, country}]` |
| `edges/citations.json` | Edge | `[{from, to}]` |
| `edges/coauthorship.json` | Edge | `[{author_a, author_b, weight}]` |
| `edges/author_paper.json` | Edge | `[{author_id, paper_id}]` |
| `embeddings/paper_vecs.npy` | Binary | float32 (N, 384) |
| `embeddings/index.json` | Index | `{arxiv_id: row}` |
| `manifest.json` | Metadata | Run params, counts, errors |
| `raw_papers.json` | Legacy | Flat list for backward compat |
| `last_fetch.json` | State | Cross-date dedup `seen_ids` |

### Files produced by downstream skills

| Skill | File | Contents |
|-------|------|----------|
| Skill 2 | `rankings.json` | `[{arxiv_id, pagerank_score, interest_score, novelty_score, rank}]` |
| Skill 2 | `ranked_papers.json` | Augmented papers in upstream order, with `relevance_score`/`novelty_score` |
| Skill 3 | `summarize_request.json` | System+user prompt, schema, top-N papers (host-LLM input) |
| Skill 3 | `summarized_papers.json` | `{count, summarized_count, model, mode, language, papers[]}` with `one_line_summary`/`key_contributions`/`methods`/`keywords` |
| Skill 5 | `visualizer_input.json` | Field-adapted input (paper_id ← arxiv_id, url ← arxiv_url, …) |
| Skill 5 | `output/dashboard.html` | Standalone HTML dashboard |
| Skill 5 | `output/notion_mapping.json` | Optional Notion page mapping |
| Skill 4 | `briefing.md` | Daily briefing in Markdown |

## Orchestrator Commands

The unified entry point is `arxiv_agent.py`:

```bash
python arxiv_agent.py daily                                    # Full pipeline
python arxiv_agent.py fetch --categories cs.CL --keywords agent
python arxiv_agent.py rank --interest "agent skill tool use"
python arxiv_agent.py summarize --top-n 10 --language en       # Skill 3 prepare
python arxiv_agent.py finalize-summary                         # Skill 3 finalize
python arxiv_agent.py viz --skip-notion                        # Skill 5 only
python arxiv_agent.py report                                   # Skill 4 only
python arxiv_agent.py status                                   # Inspect shared_data
```

## Constraints

- **No implementation imports between skills** — only data dependencies via JSON files in `shared_data/`
- **Schema-first** — every skill validates its inputs and emits a documented shape
- **Idempotent** — re-running a skill overwrites its own output files
- **Fail-fast** — missing inputs raise clear errors; pipeline skips downstream when Skill 1 returns 0 papers
- **No extra LLM API keys** — Skill 3 uses the host conversation API; only `NOTION_API_TOKEN` (optional) and `HF_TOKEN` (optional) are read from env
