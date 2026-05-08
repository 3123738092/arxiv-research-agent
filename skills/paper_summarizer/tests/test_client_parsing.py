from summarizer.client import extract_json_array


def test_plain_json():
    text = '[{"index": 0, "one_line_summary": "hi"}]'
    assert extract_json_array(text) == [{"index": 0, "one_line_summary": "hi"}]


def test_fenced_json():
    text = '```json\n[{"index": 0}]\n```'
    assert extract_json_array(text) == [{"index": 0}]


def test_prose_then_json():
    text = 'Sure, here you go:\n[{"index": 0, "one_line_summary": "x"}]\nThanks!'
    out = extract_json_array(text)
    assert out == [{"index": 0, "one_line_summary": "x"}]


def test_unparseable_returns_empty_list():
    assert extract_json_array("no json here") == []
    assert extract_json_array("") == []


def test_non_array_json_returns_empty():
    assert extract_json_array('{"index": 0}') == []
