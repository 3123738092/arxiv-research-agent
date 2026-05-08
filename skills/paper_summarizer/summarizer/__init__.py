"""Skill 3: paper-summarizer.

Extract structured summaries (one-line summary, key contributions, methods,
keywords) from ranked arXiv papers using Claude.

Public API:
    summarize(papers, top_n=..., ...)  -> list[dict]
    SummarizerConfig                    dataclass for all tunables

These are exposed lazily so that importing the package does not require
``anthropic`` to be installed — useful in tests that only exercise the
prompt/schema/cache modules.
"""

from __future__ import annotations

__version__ = "0.2.0"
__all__ = ["summarize", "SummarizerConfig"]


def __getattr__(name: str):
    if name == "SummarizerConfig":
        from .config import SummarizerConfig
        return SummarizerConfig
    if name == "summarize":
        from .core import summarize
        return summarize
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
