"""Anthropic client wrapper: retries, prompt caching, robust JSON extraction."""

from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any

import anthropic

from .config import SummarizerConfig
from .prompts import get_system_prompt

log = logging.getLogger(__name__)


class SummarizerClient:
    def __init__(self, cfg: SummarizerConfig):
        # Let the SDK auto-pick credentials from env when not set explicitly.
        # Supported env: ANTHROPIC_API_KEY, ANTHROPIC_AUTH_TOKEN, ANTHROPIC_BASE_URL.
        # ANTHROPIC_AUTH_TOKEN sends `Authorization: Bearer ...` — used by
        # most Anthropic-compatible gateways.
        has_any_cred = bool(
            cfg.api_key
            or os.environ.get("ANTHROPIC_API_KEY")
            or os.environ.get("ANTHROPIC_AUTH_TOKEN")
        )
        if not has_any_cred:
            raise RuntimeError(
                "No Anthropic credentials. Set ANTHROPIC_API_KEY or "
                "ANTHROPIC_AUTH_TOKEN (env), or pass cfg.api_key."
            )
        self.cfg = cfg
        kwargs: dict[str, Any] = {}
        if cfg.api_key:
            kwargs["api_key"] = cfg.api_key
        if cfg.base_url:
            kwargs["base_url"] = cfg.base_url
        self._client = anthropic.Anthropic(**kwargs)

    def _system_blocks(self) -> list[dict[str, Any]]:
        """System prompt split into cacheable blocks.

        The whole system prompt is constant across a run, so we mark it with
        cache_control=ephemeral. After the first call Anthropic caches it for
        ~5 min and each subsequent batch in the same run hits the cache.
        """
        text = get_system_prompt(self.cfg.language)
        if self.cfg.enable_prompt_cache:
            return [
                {
                    "type": "text",
                    "text": text,
                    "cache_control": {"type": "ephemeral"},
                }
            ]
        return [{"type": "text", "text": text}]

    def complete(self, user_prompt: str) -> str:
        """Send one user prompt; return raw text. Retries on transient errors."""
        last_err: Exception | None = None
        for attempt in range(1, self.cfg.max_retries + 1):
            try:
                resp = self._client.messages.create(
                    model=self.cfg.model,
                    max_tokens=self.cfg.max_tokens,
                    system=self._system_blocks(),
                    messages=[{"role": "user", "content": user_prompt}],
                )
                usage = getattr(resp, "usage", None)
                if usage is not None:
                    log.info(
                        "usage: in=%s out=%s cache_read=%s cache_write=%s",
                        getattr(usage, "input_tokens", None),
                        getattr(usage, "output_tokens", None),
                        getattr(usage, "cache_read_input_tokens", None),
                        getattr(usage, "cache_creation_input_tokens", None),
                    )
                return resp.content[0].text
            except (
                anthropic.RateLimitError,
                anthropic.APIConnectionError,
                anthropic.InternalServerError,
            ) as e:
                last_err = e
                sleep = self.cfg.retry_backoff_sec * (2 ** (attempt - 1))
                log.warning(
                    "Claude transient error (%s). retry %d/%d after %.1fs",
                    type(e).__name__,
                    attempt,
                    self.cfg.max_retries,
                    sleep,
                )
                time.sleep(sleep)
            except anthropic.APIStatusError as e:
                # non-retryable — auth, bad request, etc.
                log.error("Claude APIStatusError: %s", e)
                raise
        assert last_err is not None
        raise last_err


_JSON_ARRAY_RE = re.compile(r"\[\s*\{.*\}\s*\]", re.DOTALL)


def extract_json_array(text: str) -> list[dict]:
    """Be forgiving: strip code fences, optional leading prose, etc.

    Returns [] if nothing parseable was produced (caller should fall back to
    empty summaries rather than crashing the pipeline).
    """
    if not text:
        return []
    s = text.strip()
    # strip ``` fences
    if s.startswith("```"):
        # drop first fence line
        s = s.split("\n", 1)[1] if "\n" in s else s
        if s.endswith("```"):
            s = s[:-3]
        s = s.strip()
    try:
        parsed = json.loads(s)
    except json.JSONDecodeError:
        m = _JSON_ARRAY_RE.search(s)
        if not m:
            log.warning("Could not parse JSON from model output: %s...", s[:200])
            return []
        try:
            parsed = json.loads(m.group(0))
        except json.JSONDecodeError:
            log.warning("Regex-extracted JSON still invalid.")
            return []
    if not isinstance(parsed, list):
        return []
    return [x for x in parsed if isinstance(x, dict)]
