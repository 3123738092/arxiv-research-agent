# API Rate Limits & Retry Strategy

## arXiv API

| Parameter | Value |
|-----------|-------|
| Rate limit | Polite: 1 req / 3s |
| Results/req | Max 100 |
| Retry on | 429, 503 |
| Backoff | 4s → 8s → 16s → 32s → 60s (max 5 attempts) |

## Semantic Scholar API

| Parameter | Free (no key) | Free (with key) |
|-----------|--------------|-----------------|
| Rate limit | 1 req/s | 100 req/s |
| Batch size | 500/req | 500/req |
| Key signup | N/A | semanticscholar.org/product/api |

## Sentence Transformers (Local)

| Parameter | Value |
|-----------|-------|
| Model | all-MiniLM-L6-v2 |
| Dimension | 384 |
| Memory | ~90 MB |
| Speed | ~1,000 sentences/sec (CPU) |

## Tenacity Usage

All API calls use `@retry` decorator with exponential backoff.
See `scripts/fetch_arxiv.py` and `scripts/enrich_semantic_scholar.py`.
