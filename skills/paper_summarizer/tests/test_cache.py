from summarizer.cache import SummaryCache


def test_miss_then_hit(tmp_path):
    cache = SummaryCache(str(tmp_path / "c"))
    paper = {"arxiv_url": "http://arxiv.org/abs/0001"}
    assert cache.get(paper, "abstract", "m", "en") is None

    cache.put(paper, "abstract", "m", "en", {"one_line_summary": "ok"})
    assert cache.get(paper, "abstract", "m", "en") == {"one_line_summary": "ok"}


def test_key_depends_on_mode_model_lang(tmp_path):
    cache = SummaryCache(str(tmp_path / "c"))
    paper = {"arxiv_url": "http://arxiv.org/abs/0001"}
    cache.put(paper, "abstract", "m1", "en", {"one_line_summary": "a"})
    # same paper + different model = cache miss
    assert cache.get(paper, "abstract", "m2", "en") is None
    # same paper + different language = cache miss
    assert cache.get(paper, "abstract", "m1", "zh") is None
    # same paper + different mode = cache miss
    assert cache.get(paper, "pdf", "m1", "en") is None


def test_disabled_cache_never_hits(tmp_path):
    cache = SummaryCache(str(tmp_path / "c"), enabled=False)
    paper = {"arxiv_url": "http://arxiv.org/abs/0001"}
    cache.put(paper, "abstract", "m", "en", {"one_line_summary": "ok"})
    assert cache.get(paper, "abstract", "m", "en") is None
