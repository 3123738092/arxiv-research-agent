---
name: paper_ranker
description: "Accepts papers.json, citations.json, and embeddings from the output of Skill 1, and outputs rankings.json. This skill must be used when the user asks \"which papers are the most important\", \"help me sort\", or \"rank papers\"."
version: 1.0.0
author: [your-name]
agent_created: true
tags: [ranking, pagerank, paper, social-network-analysis, centrality]
metadata:
  openclaw:
    requires:
      bins:
        - python3
      env: []
---

# Paper Ranker Skill — arXiv Research Briefing Agent

## Purpose

You are the **ranking module** for the Daily arXiv Research Briefing Agent. Your job is to:

1. Load papers, citation edges, and embeddings from `shared_data/`
2. Compute **PageRank** on the citation graph — identifying high-influence papers
3. Compute **interest similarity** between user's research interest and each paper's embedding
4. Compute **novelty scores** based on inverse citation impact
5. Combine scores into a final ranking and write `shared_data/rankings.json`

You are a **deterministic tool**, not a conversational agent. All core logic runs through
Python scripts — do NOT use LLM for data processing.

---

## When to Use This Skill

**Invoke when the user:**
- Asks to rank/score papers: "哪些论文最重要" / "rank papers about X"
- Wants to see top papers by influence: "show me the most important papers"
- Triggers the daily briefing pipeline (as part of Skills 1→2→3→4→5)

**Do NOT invoke when the user:**
- Wants to fetch new papers (delegate to Skill 1)
- Wants to summarize papers (delegate to Skill 3)
- Wants to generate a report (delegate to Skill 4)

---

## Required Inputs

| Field | Type | Source | Description |
|-------|------|--------|-------------|
| `papers.json` | File | Skill 1 | Paper fact table with arxiv_id, title, abstract, citation_count, embedding_row |
| `edges/citations.json` | File | Skill 1 | Citation edge table: `[{from, to}]` |
| `embeddings/paper_vecs.npy` + `index.json` | Files | Skill 1 | Pre-computed text embeddings (384-dim) |

## Optional Inputs

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `user_interest` | `str` | `""` | User's research interest text for similarity scoring |
| `alpha` | `float` | `0.4` | Weight for PageRank component |
| `beta` | `float` | `0.6` | Weight for interest similarity component |

---

## Core Algorithm

### 1. PageRank on Citation Graph (with Embedding Similarity Fallback)

**Primary**: Build a directed graph from citation edges (`citing_paper → cited_paper`).
Run NetworkX PageRank (α=0.85) to compute each paper's **structural influence** within the local paper set.

**Same-day fallback**: arXiv papers published today are NOT yet indexed by Semantic Scholar
(no citation counts, no reference lists). The citation graph will have 0 edges.
In this case, Skill 2 automatically builds a **topic proximity graph** from paper
embeddings — each paper connects to its top-5 semantically similar peers — and runs
PageRank on this graph instead.

**SNA significance**: PageRank identifies "authoritative" papers — those cited by many others
(real graph) or topically central papers (similarity graph). This captures the *network effect*
that pure text similarity misses.

### 2. Interest Similarity (Embedding)

Encode user interest text with `all-MiniLM-L6-v2` (same model as Skill 1).
Compute cosine similarity between the user vector and each paper's embedding.
Scale to 0–10 range.

**Fallback**: if embeddings are unavailable (Skill 1 embedding stage was skipped), interest scoring is set to 0 and only PageRank + novelty are used.

### 3. Novelty Scoring

Novelty rewards papers that are fresh, less-cited, and/or topically divergent:

- **When `citation_count` is available (S2 indexed)**: 
  `novelty = 10 / (1 + citation_count * 0.1) + min(out_degree * 0.5, 3)`  
- **When `citation_count` is null (same-day fresh papers)**: 
  Fall back to **embedding distance from centroid**. Papers whose embedding is
  farthest from today's batch centroid are considered more novel (outlier
  / divergent research directions).

### 4. Final Combined Score

```
relevance_score = alpha * pagerank_norm(0-10) + beta * interest(0-10)
final_score = relevance_score + gamma * novelty(0-10)    where gamma = 1 - alpha - beta
```

Papers are sorted by `final_score` descending and assigned integer ranks.

---

## Output: Two Files

**`shared_data/rankings.json`** — summary format (for AGENTS.md contract):

```json
[
  {
    "arxiv_id": "2301.00001",
    "title": "Tool-Augmented LLM Agents...",
    "pagerank_score": 0.15,
    "interest_score": 8.5,
    "novelty_score": 6.2,
    "relevance_score": 5.1,
    "score": 11.3,
    "rank": 1
  }
]
```

**`shared_data/ranked_papers.json`** — full format extending `raw_papers.json` (for project.md data contract):

```json
[
  {
    "arxiv_id": "...",
    "title": "...",
    "abstract": "...",
    "authors": ["..."],
    "published": "...",
    "arxiv_url": "...",
    "pdf_url": "...",
    "categories": ["..."],
    "primary_category": "cs.CL",
    "citation_count": 15,
    "relevance_score": 5.1,
    "novelty_score": 6.2,
    "ranking_reason": "Above-average network centrality; strong interest match; moderate novelty."
  }
]
```

---

## Usage

### Standalone (with real shared_data/)
```bash
python -m skills.paper_ranker.rank --interest "large language model agents and tool use"
```

### With test fixtures
```bash
python -m skills.paper_ranker.rank --interest "graph neural networks" --data-dir skills/paper_ranker/tests/fixtures
```

### Custom weights
```bash
python -m skills.paper_ranker.rank --interest "LLM agents" --alpha 0.3 --beta 0.5
```

---

## Constraints

1. **No implementation imports from other skills** — reads only via local `_io.py`
2. **Idempotent** — re-running overwrites `rankings.json`
3. **Graceful degradation** — works even without embeddings (interest scoring falls back to 0)
4. **Handles isolated nodes** — papers with no citation edges get PageRank = 0, not omitted

---

## Progressive Disclosure

| Reference File | When to Read |
|----------------|-------------|
| `_io.py` | Understanding data loading API and contracts |
| `skills/data_collector/contracts/papers.schema.json` | Debugging paper field availability |
