---
name: arxiv-research-agent
description: >
  Daily arXiv Research Briefing Agent — multi-skill AI agent that fetches,
  ranks, detects communities in, visualizes, and reports on daily arXiv papers.
version: 1.0.0
skills:
  - data-collector
  - paper-ranker
  - community-detector
  - briefing-report
  - visualizer
pipeline:
  order: [data-collector, paper-ranker, community-detector, visualizer, briefing-report]
---

# arXiv Research Briefing Agent

Daily arXiv paper ingestion, ranking, community detection, visualization, and report generation.

## Skill Inventory

| # | Skill | Directory | Purpose |
|---|-------|-----------|---------|
| 1 | **data-collector** | `skills/data_collector/` | Fetch arXiv papers, enrich with S2, embed, build graphs → `shared_data/` |
| 2 | **paper-ranker** | `skills/paper_ranker/` | PageRank + interest scoring on citation graph → ranked paper list |
| 3 | **community-detector** | `skills/community_detector/` | Louvain/Leiden community detection on co-authorship graph → clusters |
| 4 | **briefing-report** | `skills/briefing_report/` | Generate Markdown/PDF daily briefing with top papers and insights |
| 5 | **visualizer** | `skills/visualizer/` | Network visualization, trend charts, author collaboration graphs |

## Execution Order

Skills have **data dependencies** (not implementation dependencies):

```
Skill 1 (data-collector) ──► shared_data/
                                 │
          ┌──────────────────────┼──────────────────────┐
          ▼                      ▼                      ▼
     Skill 2 (ranker)      Skill 3 (community)    Skill 5 (visualizer)
          │                      │                      │
          └──────────────────────┼──────────────────────┘
                                 ▼
                          Skill 4 (report)
```

- Skill 1 MUST run first (produces all data)
- Skills 2, 3, 5 can run in parallel after Skill 1
- Skill 4 runs last (aggregates output from 2, 3, 5)

## Intent Routing Table

| User Says | Route To | Trigger |
|-----------|----------|---------|
| "fetch today's papers" / "抓取论文" | Skill 1 | Keywords: fetch, arXiv, 抓取, 论文 |
| "rank papers about X" / "哪些论文最重要" | Skill 2 | Keywords: rank, PageRank, 重要, 排名 |
| "find research communities" / "这个领域有哪些团队" | Skill 3 | Keywords: community, cluster, 社区, 团队 |
| "generate daily briefing" / "生成简报" | Skill 4 | Keywords: report, briefing, 简报, 报告 |
| "show collaboration graph" / "可视化" | Skill 5 | Keywords: visualize, graph, chart, 可视化 |
| "daily briefing" / "今日简报" | Pipeline | Run Skills 1→2→3→5→4 in order |

## Shared Data Contract

All inter-skill communication goes through `shared_data/`. See `shared/loader.py` for the typed loading API.

### Files produced by Skill 1 (data-collector)

| File | Type | Contents |
|------|------|----------|
| `papers.json` | Fact table | `[{arxiv_id, title, abstract, citation_count, embedding_row, ...}]` |
| `authors.json` | Dimension | `[{author_id, name, s2_author_id, ...}]` |
| `affiliations.json` | Dimension | `[{affiliation_id, name, country}]` |
| `edges/citations.json` | Edge table | `[{from, to}]` |
| `edges/coauthorship.json` | Edge table | `[{author_a, author_b, weight}]` |
| `edges/author_paper.json` | Edge table | `[{author_id, paper_id}]` |
| `embeddings/paper_vecs.npy` | Binary | float32 (N, 384) |
| `embeddings/index.json` | Index | `{arxiv_id: row}` |
| `manifest.json` | Metadata | Run params, counts, errors |
| `raw_papers.json` | Legacy | Flat list for backward compat |

### Files produced by downstream skills

| Skill | File | Contents |
|-------|------|----------|
| Skill 2 | `shared_data/rankings.json` | `[{arxiv_id, pagerank_score, interest_score, rank}]` |
| Skill 3 | `shared_data/communities.json` | `[{community_id, members[], label, size}]` |
| Skill 4 | `shared_data/briefing.md` | Daily briefing in Markdown |
| Skill 5 | `shared_data/visualizations/` | PNG/SVG/HTML output files |

## Testing Each Skill Independently

Every skill can be tested in isolation using fixture data:

```python
from shared.loader import load_papers
from pathlib import Path

fixtures = Path("skills/data_collector/tests/fixtures")
papers = load_papers(data_dir=fixtures)
```

Each skill directory should have:
```
skills/<skill_name>/tests/fixtures/
├── papers.json
├── authors.json
├── edges/
│   ├── citations.json
│   ├── coauthorship.json
│   └── author_paper.json
└── embeddings/
    ├── paper_vecs.npy
    └── index.json
```

## Development Workflow

1. **Skill 1 runs first** — populates `shared_data/` via `python -m skills.data_collector.scripts.pipeline --config config.json`
2. **Other skills read via loader** — `from shared.loader import load_papers`
3. **Each skill writes its own outputs** — to `shared_data/` (rankings, communities, briefing, visualizations)
4. **Agent orchestrates** — `arxiv_agent.py` calls skills in order: 1→2→3→5→4

## Constraints

- **No implementation imports between skills** — only data dependencies via JSON files
- **Schema-first** — every file conforms to a JSON Schema in `contracts/`
- **Idempotent** — re-running a skill overwrites its own output files
- **Fail-fast** — if Skill 1 fails, downstream skills receive a clear `SkillInputMissingError`
