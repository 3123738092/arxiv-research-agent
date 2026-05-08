---
name: paper-summarizer
description: Extract one-line summary, key contributions, methods, and keywords from ranked arXiv papers using Claude. Used by the arXiv Research Briefing Agent as Skill 3 of 5.
version: 0.2.0
author: 成员 C
tags: [arxiv, summarization, llm, research, agent-skill]
---

# paper-summarizer

Skill 3 of the *arXiv Research Briefing Agent* (see `TEAM_GUIDE.md`).

Consumes ranked papers and produces structured summaries ready for report
rendering and visualization.

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

## How it works

1. Take top-N ranked papers (default N=20).
2. (Optional) Download each paper's PDF and extract plain text (`mode="pdf"`).
3. Check the local disk cache keyed on `arxiv_url + mode + model + language`.
4. Batch the uncached papers (default 10 per call) and send to Claude with a
   cacheable system prompt + strict JSON-only output instruction.
5. Parse the JSON (robust to code fences and stray prose), normalize the
   schema, write back into the paper dicts, persist, and return.

## Why these design choices

- **Batch + prompt caching**: the system prompt is ~1 KB and is identical for
  every batch; marking it `cache_control=ephemeral` cuts cost significantly
  when there are multiple batches in one run.
- **Local disk cache**: re-running the Agent during development or grading
  does not re-spend tokens on already-summarized papers.
- **Tolerant JSON extraction + empty-summary fallback**: one malformed batch
  should not crash the downstream report generator.
- **Schema normalization**: downstream Skills (`report_generator`,
  `visualizer`) can rely on the four fields always being present with
  correct types.

## Usage

Standalone:
```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY="sk-ant-..."
python -m summarizer                       # reads shared_data/ranked_papers.json
python -m summarizer --top-n 10 --mode pdf --language zh
```

From Python:
```python
from summarizer import summarize, SummarizerConfig

cfg = SummarizerConfig(top_n=10, mode="abstract", language="en")
papers = summarize(ranked_papers, cfg=cfg)
```

As a drop-in replacement for `skills/paper_summarizer.py` in the main Agent:
```python
# in arxiv_agent.py
from skill3_paper_summarizer.summarizer import summarize
```

## Extensions (per TEAM_GUIDE §4)

- `mode="pdf"` — read PDF full text (implemented; needs `pypdf`).
- `language="zh"` — Chinese output (implemented).
- Swap models — pass `SummarizerConfig(model="claude-opus-4-6")`.

## Testing

```bash
python -m pytest tests/ -q
```

20 unit + integration tests. `test_core_integration.py` monkey-patches the
Anthropic client so tests run fully offline.
