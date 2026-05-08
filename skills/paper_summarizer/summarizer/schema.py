"""Lightweight schema / validation for summarizer output.

We intentionally avoid pydantic to keep dependencies minimal; the guide's
requirements.txt does not list it. Instead we validate with plain Python and
return a normalized dict with consistent types, filling defaults for missing
fields so downstream Skills (report_generator, visualizer) never crash.
"""

from __future__ import annotations

from typing import Any

SUMMARY_FIELDS = ("one_line_summary", "key_contributions", "methods", "keywords")


def empty_summary() -> dict:
    """Fresh empty-summary dict — always call this; never share the module-level copy."""
    return {
        "one_line_summary": "",
        "key_contributions": [],
        "methods": [],
        "keywords": [],
    }


EMPTY_SUMMARY = empty_summary()  # kept for backwards-compat, read-only


def _as_str(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v.strip()
    return str(v).strip()


def _as_str_list(v: Any, max_items: int = 10) -> list[str]:
    if v is None:
        return []
    if isinstance(v, str):
        # sometimes the model returns a comma-separated string
        items = [s.strip() for s in v.split(",") if s.strip()]
    elif isinstance(v, (list, tuple)):
        items = [_as_str(x) for x in v if _as_str(x)]
    else:
        items = [_as_str(v)]
    # dedupe preserving order
    seen: set[str] = set()
    out: list[str] = []
    for it in items:
        if it.lower() in seen:
            continue
        seen.add(it.lower())
        out.append(it)
        if len(out) >= max_items:
            break
    return out


def normalize_summary(obj: dict | None) -> dict:
    """Return a dict with exactly SUMMARY_FIELDS, all types normalized.

    Missing / malformed fields become empty defaults. This never raises.
    """
    if not isinstance(obj, dict):
        return empty_summary()
    return {
        "one_line_summary": _as_str(obj.get("one_line_summary")),
        "key_contributions": _as_str_list(obj.get("key_contributions"), max_items=5),
        "methods": _as_str_list(obj.get("methods"), max_items=8),
        "keywords": _as_str_list(obj.get("keywords"), max_items=6),
    }


def merge_into_paper(paper: dict, summary: dict) -> dict:
    """Augment an existing paper dict with summary fields (in place and return)."""
    norm = normalize_summary(summary)
    for k in SUMMARY_FIELDS:
        paper[k] = norm[k]
    return paper
