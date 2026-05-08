"""Integration-ish test for summarize() without hitting the network.

We monkey-patch SummarizerClient.complete to return a canned JSON array
that matches the paper count. This exercises the full cache + schema + I/O
path end-to-end.
"""

import json
import os

import pytest

from summarizer import core


@pytest.fixture
def fake_response():
    def make(n: int) -> str:
        arr = [
            {
                "index": i,
                "one_line_summary": f"Summary of paper {i}.",
                "key_contributions": [f"contribution {i}.a", f"contribution {i}.b"],
                "methods": [f"method{i}", "transformer"],
                "keywords": [f"kw{i}", "robotics"],
            }
            for i in range(n)
        ]
        return json.dumps(arr)
    return make


def test_summarize_end_to_end(monkeypatch, tmp_cfg, sample_papers, fake_response):
    # intercept the network call
    def fake_complete(self, user_prompt):
        # count [i] tokens in the prompt to know the batch size
        n = user_prompt.count("] Title:")
        return fake_response(n)

    monkeypatch.setattr(core.SummarizerClient, "complete", fake_complete)
    # avoid the API key check in __init__
    monkeypatch.setattr(
        core.SummarizerClient,
        "__init__",
        lambda self, cfg: setattr(self, "cfg", cfg) or None,
    )

    result = core.summarize(sample_papers, cfg=tmp_cfg)
    assert len(result) == len(sample_papers)
    for p in result[: tmp_cfg.top_n]:
        assert p["one_line_summary"].startswith("Summary of paper")
        assert len(p["key_contributions"]) == 2
        assert "transformer" in p["methods"]

    # persisted
    out_path = os.path.join(tmp_cfg.shared_data_dir, tmp_cfg.output_filename)
    assert os.path.isfile(out_path)
    with open(out_path) as f:
        payload = json.load(f)
    assert payload["summarized_count"] == len(sample_papers)


def test_summarize_is_cached_on_second_run(monkeypatch, tmp_cfg, sample_papers, fake_response):
    calls = {"n": 0}

    def fake_complete(self, user_prompt):
        calls["n"] += 1
        return fake_response(user_prompt.count("] Title:"))

    monkeypatch.setattr(core.SummarizerClient, "complete", fake_complete)
    monkeypatch.setattr(
        core.SummarizerClient, "__init__",
        lambda self, cfg: setattr(self, "cfg", cfg) or None,
    )

    core.summarize(sample_papers, cfg=tmp_cfg)
    first_calls = calls["n"]
    assert first_calls >= 1

    # second run — all papers should come from disk cache
    core.summarize(sample_papers, cfg=tmp_cfg)
    assert calls["n"] == first_calls, "cache should prevent any new API calls"


def test_summarize_tolerates_bad_json(monkeypatch, tmp_cfg, sample_papers):
    monkeypatch.setattr(core.SummarizerClient, "complete",
                        lambda self, p: "not json at all")
    monkeypatch.setattr(
        core.SummarizerClient, "__init__",
        lambda self, cfg: setattr(self, "cfg", cfg) or None,
    )

    result = core.summarize(sample_papers, cfg=tmp_cfg)
    # no crash — empty summaries everywhere
    assert all(p["one_line_summary"] == "" for p in result[: tmp_cfg.top_n])
    assert all(p["key_contributions"] == [] for p in result[: tmp_cfg.top_n])
