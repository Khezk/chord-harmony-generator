"""Tests for chord parsing, progression parsing, weights form parsing, and harmony generation."""

from __future__ import annotations

from dataclasses import replace

import pytest

from harmony import (
    MAX_PROGRESSION_CHORDS,
    MAX_PROGRESSION_INPUT_CHARS,
    default_weights,
    generate_harmony,
    parse_chord_symbol,
    parse_progression,
    parse_weights_from_form,
    progressions_structurally_equal,
    tendency_tone_adjustment,
    voice_leading_cost,
    weights_form_snapshot,
    weights_from_dict,
)


def test_parse_chord_symbol_major_and_minor() -> None:
    c = parse_chord_symbol("Cmaj")
    assert "C" in c.symbol
    assert c.root_pc == 0
    am = parse_chord_symbol("Am")
    assert am.root_pc == 9
    cmaj7 = parse_chord_symbol("Cmaj7")
    # Regression: maj7 must not be parsed as minor-major.
    assert 4 in cmaj7.pitches
    assert 3 not in cmaj7.pitches


def test_parse_chord_symbol_leading_sharp_and_flat() -> None:
    """#F and bC prefix forms match F# and Cb; suffix forms unchanged."""
    assert parse_chord_symbol("#F").root_pc == 6
    assert parse_chord_symbol("#Fmaj").root_pc == 6
    assert parse_chord_symbol("#F7").root_pc == 6
    assert parse_chord_symbol("F#").root_pc == 6
    # bC / Cb: root spelling Cb (same pitch class as B in 12-TET).
    assert parse_chord_symbol("bC").root_pc == 11
    assert parse_chord_symbol("bCmaj7").root_pc == 11
    assert parse_chord_symbol("Cb").root_pc == 11


def test_parse_chord_symbol_bm_still_b_minor() -> None:
    """Leading 'b' + note letter only; 'bm' remains B minor, not ambiguous."""
    bm = parse_chord_symbol("bm")
    assert bm.root_pc == 11
    assert 2 in bm.pitches  # D (minor third above B)


def test_parse_chord_symbol_slash_bass_leading_accidentals() -> None:
    c = parse_chord_symbol("C/#F")
    assert c.root_pc == 0
    assert c.bass_pc == 6
    d = parse_chord_symbol("D/bC")
    assert d.root_pc == 2
    assert d.bass_pc == 11


def test_equivalent_root_spellings_same_harmony() -> None:
    """#F=F#, bC=Cb, bD=Db, etc.: same root_pc, pitches, and structural fingerprint."""
    pairs = [
        ("#F", "F#"),
        ("#Fmaj7", "F#maj7"),
        ("bC", "Cb"),
        ("bD", "Db"),
        ("bB", "Bb"),
        ("#G", "G#"),
        ("#C", "C#"),
    ]
    for a, b in pairs:
        ca, cb = parse_chord_symbol(a), parse_chord_symbol(b)
        assert ca.root_pc == cb.root_pc
        assert ca.pitches == cb.pitches
        assert ca.bass_pc == cb.bass_pc
    assert progressions_structurally_equal("#F | bC | bD", "F# | Cb | Db")


def test_unicode_accidentals_normalized_to_ascii() -> None:
    """Unicode sharp/flat signs parse like ASCII; stored symbol uses conventional spelling."""
    sharp_f = "\u266fFmaj"
    c = parse_chord_symbol(sharp_f)
    assert c.symbol == "F#maj"
    assert c.root_pc == parse_chord_symbol("F#maj").root_pc
    flat_b = "\u266dB"
    d = parse_chord_symbol(flat_b)
    assert d.symbol == "Bb"
    assert d.root_pc == parse_chord_symbol("Bb").root_pc


def test_canonical_chord_symbol_suffix_accidentals() -> None:
    """Leading #/b in user input becomes suffix F#/Bb in stored symbol."""
    assert parse_chord_symbol("#Fmaj7").symbol == "F#maj7"
    assert parse_chord_symbol("bB").symbol == "Bb"
    assert parse_chord_symbol("bC").symbol == "Cb"
    assert parse_chord_symbol("C/#F").symbol == "C/F#"
    assert parse_chord_symbol("D/bC").symbol == "D/Cb"


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
    assert "beam_width" in snap


def test_weights_from_dict_fills_missing_keys() -> None:
    w = weights_from_dict({"cost_static": 123.0})
    assert w.cost_static == 123.0
    assert w.beam_width == default_weights().beam_width


def test_weights_from_dict_non_mapping_returns_defaults() -> None:
    d = default_weights()
    assert weights_from_dict(None) == d  # type: ignore[arg-type]
    assert weights_from_dict([]) == d  # type: ignore[arg-type]


def test_weights_from_dict_invalid_values_fall_back_to_defaults() -> None:
    d = default_weights()
    w = weights_from_dict(
        {
            "beam_width": "oops",
            "max_voicings_per_chord": "999999999",
            "range_low": "not-a-number",
            "cost_static": "nan",
        }
    )
    assert w.beam_width == d.beam_width
    assert w.max_voicings_per_chord == d.max_voicings_per_chord
    assert w.range_low == d.range_low
    assert w.cost_static == d.cost_static


def test_weights_from_dict_enforces_cross_field_invariants() -> None:
    d = default_weights()
    w = weights_from_dict(
        {
            "span_tight_threshold": 30,
            "span_wide_threshold": 10,
            "range_low": 90,
            "range_high": 50,
        }
    )
    assert w.span_tight_threshold == d.span_tight_threshold
    assert w.span_wide_threshold == d.span_wide_threshold
    assert w.range_low == d.range_low
    assert w.range_high == d.range_high


def test_tendency_leading_tone_and_seventh_bonuses() -> None:
    g7 = parse_chord_symbol("G7")
    cmaj = parse_chord_symbol("C")
    w = default_weights()
    # B3 -> C4 in voice 1 (leading tone resolution)
    prev = (43, 59, 62, 65)
    curr = (48, 60, 64, 67)
    assert tendency_tone_adjustment(prev, curr, g7, cmaj, w) < 0
    # F4 -> E4 (seventh resolves down onto chord tone)
    prev2 = (43, 59, 62, 65)
    curr2 = (48, 60, 64, 64)
    assert tendency_tone_adjustment(prev2, curr2, g7, cmaj, w) < 0


def test_slash_bass_mismatch_increases_cost() -> None:
    w = default_weights()
    ch = parse_chord_symbol("C/E")
    wrong_bass = (43, 60, 64, 67)
    right_bass = (52, 60, 64, 67)
    assert voice_leading_cost(None, wrong_bass, w, curr_chord=ch) > voice_leading_cost(
        None, right_bass, w, curr_chord=ch
    )


def test_long_progression_completes() -> None:
    text = " ".join(["C", "F", "G", "C"] * 25)
    chords = parse_progression(text)
    assert len(chords) == 100
    generate_harmony(chords, num_voices=4)


def test_exotic_chords_generate() -> None:
    for prog in ("Cmaj7#11", "C7b9", "Cm7b5"):
        generate_harmony(parse_progression(prog), num_voices=4)


def test_all_voices_locked() -> None:
    chords = parse_progression("C F G")
    locks = {
        0: (60, 64, 67, 72),
        1: (59, 62, 67, 71),
        2: (57, 62, 65, 69),
    }
    generate_harmony(chords, locked_voicings=locks)


def test_beam_width_zero_is_exact_dp() -> None:
    w2 = replace(default_weights(), beam_width=0)
    r = generate_harmony(parse_progression("C F G C"), num_voices=4, weights=w2)
    assert len(r.chords) == 4


def test_parse_progression_collapses_empty_slots() -> None:
    assert len(parse_progression("C | | F")) == 2


def test_parse_progression_rejects_too_many_chords() -> None:
    tokens = " ".join(["C"] * (MAX_PROGRESSION_CHORDS + 1))
    with pytest.raises(ValueError, match="Too many chords"):
        parse_progression(tokens)


def test_parse_progression_rejects_oversized_input() -> None:
    blob = "x" * (MAX_PROGRESSION_INPUT_CHARS + 1)
    with pytest.raises(ValueError, match="too long"):
        parse_progression(blob)


def test_parse_weights_from_form_rejects_too_large_performance_knobs() -> None:
    w, errs = parse_weights_from_form(
        {
            "beam_width": "99999",
            "max_voicings_per_chord": "99999",
        }
    )
    assert w is None
    assert any("Beam width" in e for e in errs)
    assert any("Max voicings per chord" in e for e in errs)


def test_parse_chord_symbol_rejects_invalid_slash_bass_suffix() -> None:
    with pytest.raises(ValueError):
        parse_chord_symbol("C/Efoo")


def test_generate_harmony_rejects_empty_progression() -> None:
    with pytest.raises(ValueError, match="at least one chord"):
        generate_harmony([])


def test_generate_harmony_rejects_locked_voicing_out_of_range() -> None:
    chords = parse_progression("C F")
    with pytest.raises(ValueError, match="active range"):
        generate_harmony(chords, locked_voicings={0: (12, 24, 36, 48)})
