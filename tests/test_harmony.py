"""Tests for chord parsing, progression parsing, weights form parsing, and harmony generation."""

from __future__ import annotations

import pytest

from harmony import (
    default_weights,
    generate_harmony,
    parse_chord_symbol,
    parse_progression,
    parse_weights_from_form,
    weights_form_snapshot,
)


def test_parse_chord_symbol_major_and_minor() -> None:
    c = parse_chord_symbol("Cmaj")
    assert "C" in c.symbol
    assert c.root_pc == 0
    am = parse_chord_symbol("Am")
    assert am.root_pc == 9


def test_parse_progression_splits_separators() -> None:
    chords = parse_progression("C | F G")
    assert len(chords) == 3
    assert chords[0].root_pc == 0
    assert chords[1].root_pc == 5


def test_parse_progression_rejects_empty() -> None:
    with pytest.raises(ValueError, match="No chords"):
        parse_progression("   |  , ")


def test_generate_harmony_four_voices() -> None:
    chords = parse_progression("C F G C")
    result = generate_harmony(chords, num_voices=4)
    assert len(result.chords) == 4
    assert len(result.voices) == 4
    assert all(len(voice) == 4 for voice in result.voices)


def test_parse_weights_from_form_empty_uses_defaults() -> None:
    w, errs = parse_weights_from_form({})
    assert not errs
    assert w is not None
    assert w == default_weights()


def test_parse_weights_from_form_broad_negative_float() -> None:
    w, errs = parse_weights_from_form({"cost_static": "-999.5"})
    assert not errs
    assert w is not None
    assert w.cost_static == -999.5


def test_parse_weights_from_form_invalid_number() -> None:
    w, errs = parse_weights_from_form({"cost_static": "not-a-number"})
    assert w is None
    assert errs


def test_parse_weights_from_form_span_order() -> None:
    w, errs = parse_weights_from_form(
        {"span_tight_threshold": "20", "span_wide_threshold": "10"}
    )
    assert w is None
    assert any("tight" in e.lower() and "wide" in e.lower() for e in errs)


def test_parse_weights_from_form_range_order() -> None:
    w, errs = parse_weights_from_form({"range_low": "80", "range_high": "60"})
    assert w is None
    assert errs


def test_weights_form_snapshot_roundtrip_keys() -> None:
    form = {"cost_static": "1.25", "range_low": ""}
    snap = weights_form_snapshot(form)
    assert snap["cost_static"] == "1.25"
    assert snap["range_low"] == ""
    assert "max_spread" in snap
