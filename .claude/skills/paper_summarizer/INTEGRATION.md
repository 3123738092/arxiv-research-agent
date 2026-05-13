# paper_summarizer — Integration Notes

This skill ports `skill3_paper_summarizer/` into the agent project. It is
**not yet registered in `AGENTS.md`** — teammates will do that when ready.
The files below are self-contained and do not touch any teammate code.

## Pipeline position

```
data_collector  →  (paper_ranker, stub)  →  paper_summarizer  →  papers-analysis-visualizer
                                                              →  briefing_report
```

`papers-analysis-visualizer` expects its input to contain `one_line_summary`
and `keywords` (see its `README.md`). Those fields are written by this skill
into `shared_data/summarized_papers.json`.

## Input contract

`scripts/pipeline.py::resolve_input_papers` resolves the paper list in order:

1. `shared_data/ranked_papers.json` — produced by the ranker. Payload shape:
   `{"papers": [...]}` or a bare list.
2. `shared_data/papers.json` — produced by `data_collector`. Loaded through
   direct JSON read so downstream schema changes flow in automatically.

Each paper needs `title`, `abstract`, and (for `--mode pdf`) `pdf_url` /
`arxiv_url`. All of these are produced by `data_collector`.

## Output contract

Writes `shared_data/summarized_papers.json`:

```json
{
  "count": 42,
  "summarized_count": 20,
  "model": "claude-sonnet-4-6",
  "mode": "abstract",
  "language": "en",
  "papers": [
    {
      "title": "...",
      "abstract": "...",
      "arxiv_url": "...",
      "pdf_url": "...",
      "one_line_summary": "...",
      "key_contributions": ["..."],
      "methods": ["..."],
      "keywords": ["..."]
      // plus all fields from the input paper, untouched
    }
  ]
}
```

The top `cfg.top_n` papers are augmented with the four summary fields; the
rest pass through unchanged (with empty summary fields present via
`schema.merge_into_paper` when the top window was processed).

## Running it

Standalone from anywhere:

```bash
cd skills/paper_summarizer
pip install -r requirements.txt
export ANTHROPIC_API_KEY="sk-ant-..."
python -m summarizer                        # default: shared_data/ranked_papers.json
python -m summarizer --top-n 10 --mode pdf  # optional PDF full-text mode
```

From the project root, through the agent-facing wrapper:

```bash
python -m skills.paper_summarizer.scripts.pipeline
```

Programmatic use from `arxiv_agent.py` (when teammates want to wire it in):

```python
from skills.paper_summarizer.scripts.pipeline import run_pipeline

def run_skill3_summarize(top_n: int = 20, mode: str = "abstract"):
    return run_pipeline(config={"top_n": top_n, "mode": mode})
```

No changes to `arxiv_agent.py`, `AGENTS.md`, or root `requirements.txt`
are required to use the skill today.

## Tests

```bash
cd skills/paper_summarizer
python -m pytest tests/ -q
```

20 tests, fully offline — the Anthropic client is monkey-patched in
`tests/test_core_integration.py`.

## Dependencies

See `requirements.txt`:

- `anthropic>=0.40` — required
- `pypdf>=4.0` — optional (`--mode pdf`)
- `pdfminer.six>=20231228` — optional fallback PDF parser
- `pytest>=7.0` — dev only
