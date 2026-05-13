# API Rate Limits & Retry Strategy

## arXiv API

| Parameter | Value |
|-----------|-------|
| Rate limit | Polite: 1 req / 3s |
| Results/req | Max 100 |
| Retry on | 429, 503 |
| Backoff | 4s → 8s → 16s → 32s → 60s (max 5 attempts) |

## Sentence Transformers (Local)

| Parameter | Value |
|-----------|-------|
| Model | all-MiniLM-L6-v2 |
| Dimension | 384 |
| Memory | ~90 MB |
| Speed | ~1,000 sentences/sec (CPU) |

## Similarity Graph (Local)

| Parameter | Value |
|-----------|-------|
| Top-K neighbors | 5 |
| Cosine threshold | 0.2 |
| Builder script | `scripts/build_similarity_graph.py` |

## Tenacity Usage

arXiv API calls use `@retry` decorator with exponential backoff.
See `scripts/fetch_arxiv.py`.
