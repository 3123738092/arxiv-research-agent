"""Optional PDF loader — enables the "pdf" mode for deeper summarization.

We try `pypdf` first (pure-python, light) and fall back to `pdfminer.six`.
If neither is installed we simply return None so the caller can fall back to
abstract-only mode without crashing.
"""

from __future__ import annotations

import io
import logging
import os
import tempfile
import urllib.request
from typing import Optional

log = logging.getLogger(__name__)


def _extract_with_pypdf(data: bytes) -> Optional[str]:
    try:
        from pypdf import PdfReader  # type: ignore
    except ImportError:
        return None
    try:
        reader = PdfReader(io.BytesIO(data))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception as e:
        log.warning("pypdf extraction failed: %s", e)
        return None


def _extract_with_pdfminer(data: bytes) -> Optional[str]:
    try:
        from pdfminer.high_level import extract_text  # type: ignore
    except ImportError:
        return None
    try:
        return extract_text(io.BytesIO(data))
    except Exception as e:
        log.warning("pdfminer extraction failed: %s", e)
        return None


def download_pdf(url: str, timeout: int = 30) -> Optional[bytes]:
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "arxiv-briefing-agent/1.0"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except Exception as e:
        log.warning("PDF download failed for %s: %s", url, e)
        return None


def fetch_full_text(
    pdf_url: str,
    max_chars: int = 20000,
    timeout: int = 30,
) -> Optional[str]:
    """Download a PDF and extract plain text, capped at ``max_chars``.

    Returns None on any failure so the caller can degrade gracefully.
    """
    if not pdf_url:
        return None
    data = download_pdf(pdf_url, timeout=timeout)

    if not data:
        return None

    text = _extract_with_pypdf(data) or _extract_with_pdfminer(data)
    if not text:
        return None

    # collapse whitespace a bit and trim
    text = " ".join(text.split())
    if len(text) > max_chars:
        text = text[:max_chars] + " ... [truncated]"
    return text


def augment_with_full_text(
    papers: list[dict],
    max_chars: int = 20000,
    timeout: int = 30,
) -> list[dict]:
    """Mutate papers in place: add `full_text` when available."""
    for p in papers:
        if p.get("full_text"):
            continue
        text = fetch_full_text(p.get("pdf_url", ""), max_chars=max_chars, timeout=timeout)
        if text:
            p["full_text"] = text
    return papers
