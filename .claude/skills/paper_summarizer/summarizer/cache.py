"""On-disk cache keyed by arxiv_url + mode + model + language.

Avoids re-summarizing the same paper on re-runs — helpful during development
and during grading when the Agent may be executed multiple times.
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Optional


def _key(paper: dict, mode: str, model: str, language: str) -> str:
    basis = "|".join(
        [
            paper.get("arxiv_url") or paper.get("title", ""),
            mode,
            model,
            language,
        ]
    )
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:16]


class SummaryCache:
    def __init__(self, cache_dir: str, enabled: bool = True):
        self.enabled = enabled
        self.cache_dir = os.path.abspath(cache_dir)
        if self.enabled:
            os.makedirs(self.cache_dir, exist_ok=True)

    def _path(self, key: str) -> str:
        return os.path.join(self.cache_dir, f"{key}.json")

    def get(self, paper: dict, mode: str, model: str, language: str) -> Optional[dict]:
        if not self.enabled:
            return None
        path = self._path(_key(paper, mode, model, language))
        if not os.path.isfile(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return None

    def put(
        self, paper: dict, mode: str, model: str, language: str, summary: dict
    ) -> None:
        if not self.enabled:
            return
        path = self._path(_key(paper, mode, model, language))
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(summary, f, ensure_ascii=False, indent=2)
        except OSError:
            pass
