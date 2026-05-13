---
name: data_collector
description: "抓取、收集和查找 arXiv 论文的核心能力。当用户请求搜索/抓取论文时（例如\"今天cs.CL分类里关于agent的文章\"、\"抓取XX方向的论文\"、\"查找论文\"、\"今日新论文\"），必须调用此 skill，禁止自行使用 WebSearch 或 WebFetch 代替。支持按分类(cs.CL/cs.LG等)和关键词筛选，构建 semantic similarity graph（替代 citation graph），deduplicate，pre-compute embeddings。"
version: 1.0.0
author: Han
agent_created: true
tags: [arxiv, paper, data-collection, research, social-network-analysis]
metadata:
  openclaw:
    requires:
      bins:
        - python3
      env: []
    envVars:
      - name: WORKBUDDY_SHARED_DATA
        required: false
        note: "Output path fallback (lowest priority). --shared-data CLI arg overrides this. Without either, output goes to ~/.workbuddy/shared_data/ — likely wrong workspace."
---

# Data Collector Skill — arXiv Research Briefing Agent

## Purpose

You are the **sole data ingestion module** for the Daily arXiv Research Briefing Agent.
Your job is to:

1. Fetch papers from arXiv API by category + keyword + date range
2. Deduplicate across versions and categories
3. Build a **semantic similarity graph** from title+abstract embeddings (replaces the old citation graph)
4. Pre-compute text embeddings for downstream ranking
5. Build co-authorship graph from arXiv metadata (no external API required)
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

> **WARNING: Required env var**: Always set `WORKBUDDY_SHARED_DATA` to the current workspace's
> `shared_data/` directory before running. Without it, output files will be written to
> `~/.workbuddy/shared_data/` instead of the workspace — silent data loss.
>
> ```bash
> export WORKBUDDY_SHARED_DATA="/path/to/workspace/shared_data"
> # Windows (git bash): export WORKBUDDY_SHARED_DATA="C:/Users/.../shared_data"
> ```

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

### Stage 4 — Build Co-authorship Graph
- Script: `scripts/build_graph_edges.py`
- Uses `authors_raw` from arXiv API (no external API needed)
- `edges/coauthorship.json`: author ↔ author collaboration edges
- `edges/author_paper.json`: author → paper bipartite edges

### Stage 5 — Compute Embeddings
- Script: `scripts/embed.py`
- Model: `all-MiniLM-L6-v2` (384-dim, local, no API cost)
- Encode `title + " " + abstract` for each paper
- Output: `embeddings/paper_vecs.npy` (float32 binary) + `embeddings/index.json` (arxiv_id → row)

### Stage 6 — Build Semantic Similarity Graph
- Script: `scripts/build_similarity_graph.py`
- Computes pairwise cosine similarity on title+abstract embeddings
- Each paper connects to its top-K most similar peers (K=5, threshold=0.2)
- Output: `edges/similarity.json`: `[{from, to, weight}, ...]`

### Stage 7 — Validate & Write
- Script: `scripts/validate.py`
- Pydantic models for all output files
- Validate before writing — fail early if schema violations detected
- Write all files to `shared_data/`

### Stage 8 — Report Summary
- Output `manifest.json` with: run metadata, per-source paper counts, API errors, timing

---

## Output Data Center Structure

```
shared_data/
├── manifest.json              # Run metadata: params, timings, source status, error log
├── papers.json                # Fact table: [ { arxiv_id, title, abstract,
│                              #   authors_raw[], published_date, pdf_url,
│                              #   categories, primary_category, source } ]
├── authors.json               # Dimension table: [ { author_id, name, paper_ids[] } ]
├── edges/
│   ├── similarity.json        # [{from: arxiv_id, to: arxiv_id, weight: float}]
│   ├── coauthorship.json      # [{author_a, author_b, weight}]
│   └── author_paper.json      # [{author_id, paper_id}]
└── embeddings/
    ├── paper_vecs.npy         # float32, shape (N, 384)
    └── index.json             # { arxiv_id: row_number }
```

All JSON schemas are in `contracts/`. Downstream Skills MUST read from these files —
never call data_collector scripts directly.

---

## Constraints

1. **Deterministic core**: fetching, dedup, validation, and file I/O use Python scripts exclusively.
   The LLM is only involved in query expansion and user-facing summaries.
2. **Schema-first**: every output file conforms to a JSON Schema in `contracts/`. Pydantic
   validation runs before any write.
3. **Rate limits**: arXiv API: ≥3s between requests. Use `tenacity` exponential backoff on 429/503 responses.
4. **Idempotent writes**: output files are fully overwritten each run.
5. **No side effects**: this skill only writes to `shared_data/` and reads from arXiv API. It does
   not call other Skills or external services (no S2 required).

---

## Failure Modes

| Scenario | Behavior |
|----------|----------|
| arXiv API returns empty | Auto-backtrack up to `backtrack_days` days; if still empty, write empty papers.json and flag in manifest |
| Embedding model not installed | Skip embedding stage, set `embeddings/enabled: false` in manifest; similarity graph stage still runs |

---

## Examples

### Example 1: Daily fetch for a single topic

**User says**: "帮我抓今天 cs.CL 关于 agent 的论文"

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

**Pipeline runs**: `python /path/to/skills/arxiv-research-agent/skills/data_collector/scripts/pipeline.py --config config.json`

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

**LLM expands keywords**: "LoRA" → ["LoRA", "low-rank adaptation", "PEFT", "adapter tuning", "parameter-efficient fine-tuning"]

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

## Setup（首次使用，仅需一次）

```bash
# 1. 安装依赖
pip install arxiv tenacity pydantic sentence-transformers requests numpy

# 2. 设置共享数据目录（可选，不设则自动检测项目根下的 shared_data/）
export WORKBUDDY_SHARED_DATA="/path/to/your/workspace/shared_data"
```

之后每次调用无需重复配置。

---
