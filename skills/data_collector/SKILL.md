---
name: data-collector
description: >
  Fetch daily arXiv papers by category and keyword, enrich with Semantic Scholar
  (references, citation counts, author IDs), deduplicate, pre-compute embeddings,
  and output a structured data center for downstream SNA Skills (PageRank,
  community detection, visualization, report generation).
version: 1.0.0
author: Han
tags: [arxiv, paper, data-collection, research, social-network-analysis]
trigger_keywords:
  - fetch papers
  - arXiv
  - daily briefing
  - 抓取论文
  - 今日论文
  - 最新论文
  - paper collection
  - research briefing
metadata:
  openclaw:
    requires:
      bins:
        - python3
      env: []
    primaryEnv: SEMANTIC_SCHOLAR_API_KEY
    envVars:
      - name: SEMANTIC_SCHOLAR_API_KEY
        required: false
        description: >
          Semantic Scholar API key for higher rate limits (100 req/s with key
          vs 1 req/s without). Free tier at semanticscholar.org.
---

# Data Collector Skill — arXiv Research Briefing Agent

## Purpose

You are the **sole data ingestion module** for the Daily arXiv Research Briefing Agent.
Your job is to:

1. Fetch papers from arXiv API by category + keyword + date range
2. Enrich each paper with Semantic Scholar data (references, citation counts, author IDs)
3. Deduplicate across versions, categories, and dates
4. Pre-compute text embeddings for downstream ranking
5. Build graph edge tables (citations, co-authorship, author-paper)
6. Output a structured **data center** to `shared_data/`

You are a **deterministic tool**, not a conversational agent. All core logic runs through
Python scripts — do NOT use LLM for data processing. The LLM's role is limited to:
- Parsing user intent into structured input parameters
- Query expansion (e.g., "LoRA" → ["low-rank adaptation", "PEFT"])
- Explaining what was fetched and any issues encountered

---

## When to Use This Skill

**Invoke when the user:**
- Asks for today's/newest arXiv papers: "今天有什么新论文" / "show me today's papers"
- Specifies a research topic to collect: "帮我抓取 multimodal learning 方向的论文"
- Triggers the daily briefing pipeline: "生成今日简报" / "daily briefing"
- Wants to search with filters: "这周 GNN 论文有哪些" / "cs.CL 分类最近3天的"

**Do NOT invoke when the user:**
- Only wants to read/rank/summarize already-collected papers (delegate to Skill 2/3)
- Wants to generate a report from existing data (delegate to Skill 4)
- Asks for visualization only (delegate to Skill 5)

---

## Required Inputs

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `categories` | `list[str]` | arXiv categories | `["cs.CL", "cs.LG", "cs.CV"]` |
| `keywords` | `list[str]` | Search keywords (OR logic) | `["agent", "skill", "tool use"]` |
| `date_range` | `{start, end}` | Date window | `{"start": "2026-05-04", "end": "2026-05-05"}` |

## Optional Inputs

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `negative_keywords` | `list[str]` | `[]` | Exclude papers matching these |
| `max_results` | `int` | `200` | Max papers to fetch per category |
| `backtrack_days` | `int` | `3` | Auto-backtrack when no results |
| `sources` | `list[str]` | `["arxiv"]` | Data sources (arxiv, huggingface, paperswithcode) |
| `user_interest_text` | `str` | `None` | User's research interest for embedding pre-filter |

---

## Core Functions & Execution Order

Run `python -m skills.data_collector.scripts.pipeline` with a JSON config file.

The pipeline executes these stages in strict order:

### Stage 1 — Parse & Expand
- Script: `scripts/pipeline.py` (entry point)
- Expand user keywords via LLM if needed (e.g., "agent" → ["LLM agent", "AI agent", "autonomous agent"])
- Validate categories against `references/arxiv_categories.md`

### Stage 2 — Fetch from arXiv
- Script: `scripts/fetch_arxiv.py`
- Query: `cat:<category> AND (all:<kw1> OR all:<kw2> OR ...)`
- Date filter by `submittedDate`
- Auto-backtrack: if today yields 0 results, retry yesterday, up to `backtrack_days`
- Weekend detection: arXiv publishes Mon–Fri; widen window on Sat/Sun

### Stage 3 — Deduplicate
- Script: `scripts/dedup.py`
- Strip version suffix from arxiv_id (e.g., `2301.00001v2` → `2301.00001`)
- Cross-category dedup by arxiv_id
- Cross-date dedup against `last_fetch.json` seen-set

### Stage 4 — Enrich via Semantic Scholar
- Script: `scripts/enrich_semantic_scholar.py`
- Batch query `/paper/batch` endpoint (up to 500 papers per request)
- For each paper, fetch: `references`, `citationCount`, `authors` (with S2 authorId)
- Store per-paper references as edges in `edges/citations.json`

### Stage 5 — Build Graph Edges
- Script: `scripts/build_graph_edges.py`
- `edges/citations.json`: paper → paper citation edges
- `edges/coauthorship.json`: author ↔ author collaboration edges (weighted by co-occurrence count)
- `edges/author_paper.json`: author → paper bipartite edges

### Stage 6 — Compute Embeddings
- Script: `scripts/embed.py`
- Model: `all-MiniLM-L6-v2` (384-dim, local, no API cost)
- Encode `title + " " + abstract` for each paper
- Output: `embeddings/paper_vecs.npy` (float32 binary) + `embeddings/index.json` (arxiv_id → row)

### Stage 7 — Validate & Write
- Script: `scripts/validate.py`
- Pydantic models for all output files
- Validate before writing — fail early if schema violations detected
- Write all files to `shared_data/`
- Update `last_fetch.json` with seen arxiv_ids

### Stage 8 — Report Summary
- Output `manifest.json` with: run metadata, per-source paper counts, API errors, timing

---

## Output Data Center Structure

```
shared_data/
├── manifest.json              # Run metadata: params, timings, source status, error log
├── papers.json                # Fact table: [ { arxiv_id, title, abstract, citation_count,
│                              #   embedding_row, author_ids[], affiliation_ids[], categories,
│                              #   published_date, pdf_url, source, code_url } ]
├── authors.json               # Dimension table: [ { author_id, name, s2_author_id,
│                              #   affiliation_ids[], paper_count } ]
├── affiliations.json          # Dimension table: [ { affiliation_id, name, country } ]
├── edges/
│   ├── citations.json         # [ { from: arxiv_id, to: arxiv_id } ]
│   ├── coauthorship.json      # [ { author_a, author_b, weight, evidence_paper_ids[] } ]
│   └── author_paper.json      # [ { author_id, paper_id } ]
├── embeddings/
│   ├── paper_vecs.npy         # float32, shape (N, 384)
│   └── index.json             # { arxiv_id: row_number }
├── raw_papers.json            # Legacy compatibility: flat list with all fields inlined
└── last_fetch.json            # State: { last_fetch_time, seen_ids[], params }
```

All JSON schemas are in `contracts/`. Downstream Skills MUST read from these files —
never call data-collector scripts directly.

---

## Constraints

1. **Deterministic core**: fetching, dedup, validation, and file I/O use Python scripts exclusively.
   The LLM is only involved in query expansion and user-facing summaries.
2. **Schema-first**: every output file conforms to a JSON Schema in `contracts/`. Pydantic
   validation runs before any write.
3. **Rate limits**: arXiv API: ≥3s between requests. Semantic Scholar: 1 req/s without API key,
   100 req/s with key. Use `tenacity` exponential backoff on 429/503 responses.
4. **Idempotent writes**: output files are fully overwritten each run. `last_fetch.json`
   enables incremental dedup across runs.
5. **No side effects**: this skill only writes to `shared_data/` and reads from APIs. It does
   not call other Skills.

---

## Failure Modes

| Scenario | Behavior |
|----------|----------|
| arXiv API returns empty | Auto-backtrack up to `backtrack_days` days; if still empty, write empty papers.json and flag in manifest |
| arXiv API rate-limited (503) | Exponential backoff via tenacity, max 5 retries |
| Semantic Scholar API down | Skip enrichment, write papers without citation_count/references, flag in manifest.errors |
| Semantic Scholar paper not found | Leave citation_count=null, references=[], flag as `s2_not_found` in manifest |
| Pydantic validation fails | Abort write, log validation errors to stderr, return error in manifest |
| Embedding model not installed | Skip embedding stage, set `embeddings/enabled: false` in manifest |

---

## Examples

### Example 1: Daily fetch for a single topic

**User says**: "帮我抓今天 cs.CL 分类里关于 agent 的论文"

**LLM parses to config**:
```json
{
  "categories": ["cs.CL"],
  "keywords": ["agent"],
  "date_range": {"start": "2026-05-05", "end": "2026-05-05"},
  "backtrack_days": 3,
  "max_results": 100
}
```

**Pipeline runs**: `python -m skills.data_collector.scripts.pipeline --config config.json`

**Output**: manifest shows 14 papers fetched, 2 deduped, 12 written to papers.json.

### Example 2: Multi-category with negative keywords

**User says**: "抓 cs.CV 和 cs.LG 最近3天关于 diffusion 但不是 medical imaging 的论文"

**Parsed config**:
```json
{
  "categories": ["cs.CV", "cs.LG"],
  "keywords": ["diffusion"],
  "negative_keywords": ["medical imaging", "MRI", "CT scan"],
  "date_range": {"start": "2026-05-02", "end": "2026-05-05"},
  "max_results": 200
}
```

### Example 3: Research topic with query expansion

**User says**: "I'm working on LoRA fine-tuning, fetch relevant papers from today"

**LLM expands keywords**: "LoRA" → `["LoRA", "low-rank adaptation", "PEFT", "adapter tuning", "parameter-efficient fine-tuning"]`

Then passes the expanded list to the pipeline config.

### Example 4: Weekend handling

**User says** (on Sunday): "给我今天的论文"

**Pipeline detects Sunday**, widens date window to Friday–Sunday, fetches with auto-backtrack.

---

## Progressive Disclosure

This SKILL.md is the **entry point**. Detailed reference material is in separate files —
the agent should read them **on demand** when it needs specific information:

| Reference File | When to Read |
|----------------|-------------|
| `references/output_schema.md` | User asks about field definitions or data format |
| `references/arxiv_categories.md` | User provides an invalid or unknown category |
| `references/api_limits.md` | Debugging rate-limit errors or planning batch jobs |
| `contracts/*.schema.json` | Validating output or integrating with downstream code |

---

## Quick Start

```bash
# Install dependencies
pip install arxiv tenacity pydantic sentence-transformers requests numpy

# Optional: Semantic Scholar API key for higher rate limits
# export SEMANTIC_SCHOLAR_API_KEY=your_key_here

# Run pipeline with sample config
python -m skills.data_collector.scripts.pipeline \
  --config fixtures/sample_config.json
```
