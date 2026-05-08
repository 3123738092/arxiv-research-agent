"""Shared fixtures + sys.path setup so tests run from the Skill root."""

import json
import os
import sys

import pytest

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


@pytest.fixture
def sample_ranked():
    path = os.path.join(_ROOT, "data", "fixtures", "ranked_papers_sample.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def sample_papers(sample_ranked):
    return sample_ranked["papers"]


@pytest.fixture
def tmp_cfg(tmp_path):
    from summarizer.config import SummarizerConfig
    return SummarizerConfig(
        api_key="test-key",
        top_n=3,
        batch_size=2,
        enable_local_cache=True,
        cache_dir=str(tmp_path / "cache"),
        shared_data_dir=str(tmp_path / "shared"),
    )
