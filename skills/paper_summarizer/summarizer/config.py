"""Configuration for the paper_summarizer Skill.

All tunables in one place. The main Agent's `config.py` can be imported as a
fallback so this Skill works both standalone and as part of the full pipeline.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _default_shared_dir() -> str:
    """Resolve shared_data/ by walking up from this module.

    Works in three deployment layouts:
      1. Inside arxiv-research-agent: skills/paper_summarizer/summarizer/config.py
         — the ancestor containing arxiv_agent.py has shared_data/ next to it.
      2. Standalone skill3_paper_summarizer: summarizer/config.py
         — ../shared_data exists if placed inside a larger project.
      3. Anything else: fall back to ../data relative to this file.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    cur = here
    for _ in range(6):
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        if os.path.isfile(os.path.join(parent, "arxiv_agent.py")):
            return os.path.join(parent, "shared_data")
        candidate = os.path.join(parent, "shared_data")
        if os.path.isdir(candidate):
            return candidate
        cur = parent
    return os.path.abspath(os.path.join(here, "..", "data"))


@dataclass
class SummarizerConfig:
    """Runtime configuration for one summarize() call."""

    # --- Anthropic ---
    api_key: str = field(default_factory=lambda: os.environ.get("ANTHROPIC_API_KEY", ""))
    base_url: str = ""              # optional custom endpoint (e.g. Anthropic-compatible gateway)
    model: str = "claude-sonnet-4-6"
    max_tokens: int = 4096

    # --- Summarization ---
    top_n: int = 20
    batch_size: int = 10
    language: str = "en"          # "en" | "zh"
    mode: str = "abstract"         # "abstract" | "pdf"

    # --- Prompt caching / retries ---
    enable_prompt_cache: bool = True
    max_retries: int = 3
    retry_backoff_sec: float = 2.0

    # --- Local result cache (by arxiv_url hash) ---
    enable_local_cache: bool = True
    cache_dir: str = field(default_factory=lambda: os.path.join(
        os.path.dirname(__file__), "..", "data", "cache"
    ))

    # --- I/O ---
    shared_data_dir: str = field(default_factory=_default_shared_dir)
    output_filename: str = "summarized_papers.json"

    # --- PDF mode ---
    pdf_max_chars: int = 20000     # cap per paper to control token cost
    pdf_timeout_sec: int = 30
