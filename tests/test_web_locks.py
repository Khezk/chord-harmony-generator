"""Tests for web_app lock parsing helpers."""

import json

from lock_parsing import parse_locked_voicings


def test_parse_locked_empty():
    a, b, w = parse_locked_voicings("", 4, 4)
    assert a == {} and b == {} and w == []


def test_parse_locked_invalid_json():
    a, b, w = parse_locked_voicings("{not json", 4, 4)
    assert a == {} and b == {}
    assert w and "JSON" in w[0]


def test_parse_locked_wrong_voice_count_filtered():
    raw = json.dumps({"0": [60, 64, 67, 72], "1": [60, 64, 67]})
    a, b, w = parse_locked_voicings(raw, 4, 4)
    assert 0 in a and len(a[0]) == 4
    assert 1 not in a
    assert any("voice count" in x.lower() for x in w)


def test_parse_locked_index_out_of_range():
    raw = json.dumps({"0": [60, 64, 67, 72], "9": [48, 52, 55, 60]})
    a, b, w = parse_locked_voicings(raw, 4, 2)
    assert 0 in a and 9 not in a
    assert any("range" in x.lower() for x in w)
