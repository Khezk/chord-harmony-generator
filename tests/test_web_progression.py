"""Tests for progression structural comparison (parser semantics)."""

from harmony import (
    progression_structure_fingerprint,
    progressions_equivalent_for_ui,
    progressions_harmonically_equal,
    progressions_structurally_equal,
)


def test_structural_equal_ignores_separators_and_case_root():
    assert progressions_structurally_equal("C | F G", "c, f g")


def test_cm7_vs_lowercase_cm7_differs():
    """Lowercasing the whole token can change maj7 vs min7; parser must drive equality."""
    assert not progressions_structurally_equal("CM7", "cm7")
    fp_maj = progression_structure_fingerprint("CM7")
    fp_min = progression_structure_fingerprint("cm7")
    assert fp_maj is not None and fp_min is not None
    assert fp_maj != fp_min


def test_invalid_current_not_equal_to_saved():
    assert not progressions_structurally_equal("not a chord", "C F G")


def test_both_invalid_parse_returns_false_for_equality():
    assert not progressions_structurally_equal("bad", "also bad")


def test_cm7_vs_cm7_minor_not_ui_equivalent():
    assert not progressions_equivalent_for_ui("CM7", "cm7")


def test_c6_vs_am7_not_harmonically_equal():
    """Same four pitch classes but different harmonic roots must not match."""
    assert not progressions_harmonically_equal("C6", "Am7")


def test_db_vs_csharp_major_ui_equivalent():
    assert progressions_equivalent_for_ui("Db", "C#")
