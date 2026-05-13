# Output Data Center Schema

## File Map

| File | Role | Consumer |
|------|------|----------|
| `manifest.json` | Run metadata & error log | Agent orchestrator |
| `papers.json` | Paper fact table | Skill 2, 3, 4, 5 |
| `authors.json` | Author dimension table | Skill 2, 3, 5 |
| `affiliations.json` | Institution dimension | Skill 5 |
| `edges/citations.json` | Citation graph edges | Skill 2 (PageRank) |
| `edges/coauthorship.json` | Co-authorship edges | Skill 2, 5 |
| `edges/author_paper.json` | Author-paper bipartite | Skill 2, 3 |
| `embeddings/paper_vecs.npy` | float32, shape (N, 384) | Skill 2 (similarity) |
| `embeddings/index.json` | `{arxiv_id: row_number}` | Skill 2 |
| `raw_papers.json` | Legacy flat view | Backward compat |

## Key Field Details

### papers.json
- `arxiv_id` — version-stripped (e.g. `2301.00001`)
- `published` / `updated` — ISO 8601 datetime
- `embedding_row` — index into paper_vecs.npy, null if no embedding

### authors.json
- `author_id` — unique key (S2 authorId or name_normalized)
- `paper_ids` — arxiv_ids this author appears in

### Edge Files
- Citations: `from`/`to` are arxiv_ids
- Coauthorship: `author_a`/`author_b` with integer `weight`
- `citations_external.json` includes edges to papers outside the fetched set

## Empty-Result Behavior

When no papers found: all files written but empty. `manifest.source_status.arxiv` = "empty".

## Incremental Fetch

Deduplication removes version/category duplicates within a single run. Each run is independent — no cross-run deduplication state is kept.
