from summarizer.prompts import build_user_prompt, get_system_prompt


def test_system_prompt_language_switch():
    assert "JSON array" in get_system_prompt("en")
    assert "JSON" in get_system_prompt("zh")
    assert get_system_prompt("zh") != get_system_prompt("en")


def test_user_prompt_contains_all_papers(sample_papers):
    prompt = build_user_prompt(sample_papers, mode="abstract")
    for i, p in enumerate(sample_papers):
        assert f"[{i}]" in prompt
        assert p["title"][:30] in prompt


def test_user_prompt_pdf_mode_prefers_full_text(sample_papers):
    papers = [dict(sample_papers[0])]
    papers[0]["full_text"] = "FULL TEXT CONTENT XYZ"
    prompt = build_user_prompt(papers, mode="pdf")
    assert "FULL TEXT CONTENT XYZ" in prompt
    assert "full_text" in prompt  # label shown


def test_user_prompt_pdf_falls_back_when_no_full_text(sample_papers):
    # no full_text -> use abstract even in pdf mode
    prompt = build_user_prompt(sample_papers[:1], mode="pdf")
    assert "abstract" in prompt.lower()
