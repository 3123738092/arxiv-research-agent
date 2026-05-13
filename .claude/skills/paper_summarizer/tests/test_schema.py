from summarizer.schema import EMPTY_SUMMARY, merge_into_paper, normalize_summary


def test_normalize_handles_none():
    out = normalize_summary(None)
    assert out == EMPTY_SUMMARY
    # must be a fresh copy (downstream code may mutate)
    out["keywords"].append("x")
    assert EMPTY_SUMMARY["keywords"] == []


def test_normalize_coerces_string_list_to_list():
    out = normalize_summary({"keywords": "rl, robotics, rl"})
    assert out["keywords"] == ["rl", "robotics"]  # deduped


def test_normalize_truncates_long_lists():
    out = normalize_summary({"methods": [f"m{i}" for i in range(30)]})
    assert len(out["methods"]) <= 8


def test_normalize_ignores_unknown_fields():
    out = normalize_summary({"one_line_summary": "x", "garbage": 42})
    assert out["one_line_summary"] == "x"
    assert "garbage" not in out


def test_merge_into_paper_preserves_other_fields():
    paper = {"title": "T", "abstract": "A"}
    merge_into_paper(paper, {"one_line_summary": "Hi", "keywords": ["k"]})
    assert paper["title"] == "T"
    assert paper["one_line_summary"] == "Hi"
    assert paper["keywords"] == ["k"]
    assert paper["methods"] == []
