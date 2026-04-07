from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, List, Tuple, Sequence, Dict, Optional, Mapping

# Chord-tone roles for omission priority (when voices < chord tones).
# Inclusion order: root, 3rd, 7th, 9th, 6th, 13th, 11th, 5th → 5th is always first to omit (e.g. G13 keeps 13th, F6/9 omits 5th).
ROOT, THIRD, FIFTH, SEVENTH, NINTH, ELEVENTH, THIRTEENTH, SIXTH = 0, 1, 2, 3, 4, 5, 6, 7
INCLUSION_ORDER = (ROOT, THIRD, SEVENTH, NINTH, SIXTH, THIRTEENTH, ELEVENTH, FIFTH)


PITCH_CLASS_MAP: Dict[str, int] = {
    "C": 0,
    "C#": 1,
    "Db": 1,
    "D": 2,
    "D#": 3,
    "Eb": 3,
    "E": 4,
    "F": 5,
    "F#": 6,
    "Gb": 6,
    "G": 7,
    "G#": 8,
    "Ab": 8,
    "A": 9,
    "A#": 10,
    "Bb": 10,
    "B": 11,
}


VOICE_RANGES: Dict[int, Tuple[int, int]] = {
    # Default MIDI range (low, high) per voice count. More voices use a looser (wider) range.
    4: (48, 79),   # C3–G5 (typical SATB)
    5: (43, 83),   # G2–B5 (wider for 5 voices)
    6: (40, 86),   # E2–D6 (wider for 6 voices)
}


@dataclass(frozen=True)
class HarmonyWeights:
    """
    Tunable weights for voice-leading cost. Used by the web UI so users can
    adjust style without editing code. All costs are additive; higher = stronger penalty.
    """
    # Motion
    cost_static: float = 0.5           # voice doesn't move
    cost_stepwise: float = 0.2        # move 1–2 semitones (preferred)
    cost_medium_step: float = 0.5     # move 3–5 semitones
    cost_large_leap_base: float = 1.5  # large leap penalty base
    cost_large_leap_per: float = 0.1   # per semitone above 5
    # Parallels and motion
    cost_parallel_5_8: float = 4.0     # parallel 5ths or octaves
    cost_direct_5_8: float = 3.0      # direct (hidden) 5ths/8ves
    cost_voice_crossing: float = 2.5  # voices swap order
    bonus_contrary: float = 0.25      # subtracted when outer voices move contrary
    # Spacing
    cost_wide_gap_base: float = 1.0   # adjacent voices > octave apart
    cost_wide_gap_per: float = 0.1    # per semitone above octave
    spacing_octave: int = 12
    # Chord span (internal): "span" = distance in semitones from lowest to highest note in the chord
    cost_span_tight: float = 1.0      # penalty when span < span_tight_threshold
    cost_span_wide: float = 1.0      # penalty when span > span_wide_threshold
    span_tight_threshold: int = 8     # below this many semitones, chord is "too tight"
    span_wide_threshold: int = 24     # above this many semitones, chord is "too wide"
    # Voicing generator (optional overrides)
    range_low: Optional[int] = None   # if set, override default low bound (MIDI)
    range_high: Optional[int] = None  # if set, override default high bound (MIDI)
    max_spread: int = 31              # max semitones between lowest and highest note in a chord


def default_weights() -> HarmonyWeights:
    return HarmonyWeights()


# Form field names in UI order (for snapshot / repopulation).
WEIGHT_FORM_KEYS: Tuple[str, ...] = (
    "cost_static",
    "cost_stepwise",
    "cost_medium_step",
    "cost_large_leap_base",
    "cost_large_leap_per",
    "cost_parallel_5_8",
    "cost_direct_5_8",
    "cost_voice_crossing",
    "bonus_contrary",
    "cost_wide_gap_base",
    "cost_wide_gap_per",
    "spacing_octave",
    "cost_span_tight",
    "cost_span_wide",
    "span_tight_threshold",
    "span_wide_threshold",
    "range_low",
    "range_high",
    "max_spread",
)

# Broad limits: large |cost| allowed for experimentation; MIDI 0–127; wide spread.
_WEIGHT_FLOAT_ABS_MAX = 1.0e7
_SPACING_OCTAVE_BOUNDS = (1, 96)
_SPAN_THRESHOLD_BOUNDS = (0, 127)
_MAX_SPREAD_BOUNDS = (1, 127)
_MIDI_NOTE_BOUNDS = (0, 127)

_WEIGHT_FLOAT_FIELDS: Tuple[Tuple[str, str], ...] = (
    ("cost_static", "Static voice"),
    ("cost_stepwise", "Stepwise motion"),
    ("cost_medium_step", "Medium step"),
    ("cost_large_leap_base", "Large leap (base)"),
    ("cost_large_leap_per", "Large leap (per semitone)"),
    ("cost_parallel_5_8", "Parallel 5ths/8ves"),
    ("cost_direct_5_8", "Direct 5ths/8ves"),
    ("cost_voice_crossing", "Voice crossing"),
    ("bonus_contrary", "Contrary motion bonus"),
    ("cost_wide_gap_base", "Wide gap (base)"),
    ("cost_wide_gap_per", "Wide gap (per semitone)"),
    ("cost_span_tight", "Chord span tight cost"),
    ("cost_span_wide", "Chord span wide cost"),
)


def weights_form_snapshot(form: Mapping[str, str]) -> Dict[str, str]:
    """Raw strings from the form for every weight field (for repopulating the UI)."""
    return {k: (form.get(k) or "").strip() for k in WEIGHT_FORM_KEYS}


def parse_weights_from_form(form: Mapping[str, str]) -> Tuple[Optional[HarmonyWeights], List[str]]:
    """
    Parse HarmonyWeights from form data. Empty fields use defaults.

    Returns (weights, errors). If errors is non-empty, weights is None.
    Accepts broad numeric ranges (see module constants).
    """
    errors: List[str] = []
    d = default_weights()

    float_vals: Dict[str, float] = {}
    for key, label in _WEIGHT_FLOAT_FIELDS:
        raw = (form.get(key) or "").strip()
        if not raw:
            float_vals[key] = getattr(d, key)
            continue
        try:
            x = float(raw)
        except ValueError:
            errors.append(f"{label}: not a valid number")
            continue
        if not math.isfinite(x):
            errors.append(f"{label}: must be a finite number")
            continue
        if abs(x) > _WEIGHT_FLOAT_ABS_MAX:
            errors.append(f"{label}: absolute value must be ≤ {_WEIGHT_FLOAT_ABS_MAX:g}")
            continue
        float_vals[key] = x

    if errors:
        return None, errors

    def parse_int_field(
        key: str, label: str, default: int, lo: int, hi: int
    ) -> Optional[int]:
        raw = (form.get(key) or "").strip()
        if not raw:
            return default
        try:
            xf = float(raw)
        except ValueError:
            errors.append(f"{label}: not a valid number")
            return None
        if not math.isfinite(xf):
            errors.append(f"{label}: must be a finite number")
            return None
        iv = int(xf)
        if abs(xf - iv) > 1e-9:
            errors.append(f"{label}: must be a whole number")
            return None
        if not (lo <= iv <= hi):
            errors.append(f"{label}: must be between {lo} and {hi} (inclusive)")
            return None
        return iv

    def parse_optional_midi(key: str, label: str) -> Optional[int]:
        raw = (form.get(key) or "").strip()
        if not raw:
            return None
        lo, hi = _MIDI_NOTE_BOUNDS
        try:
            xf = float(raw)
        except ValueError:
            errors.append(f"{label}: not a valid number")
            return None
        if not math.isfinite(xf):
            errors.append(f"{label}: must be a finite number")
            return None
        iv = int(xf)
        if abs(xf - iv) > 1e-9:
            errors.append(f"{label}: must be a whole number")
            return None
        if not (lo <= iv <= hi):
            errors.append(f"{label}: must be between {lo} and {hi} (MIDI)")
            return None
        return iv

    spacing_octave = parse_int_field(
        "spacing_octave", "Spacing (octave in semitones)", d.spacing_octave, *_SPACING_OCTAVE_BOUNDS
    )
    span_tight_threshold = parse_int_field(
        "span_tight_threshold",
        "Span tight threshold",
        d.span_tight_threshold,
        *_SPAN_THRESHOLD_BOUNDS,
    )
    span_wide_threshold = parse_int_field(
        "span_wide_threshold",
        "Span wide threshold",
        d.span_wide_threshold,
        *_SPAN_THRESHOLD_BOUNDS,
    )
    max_spread = parse_int_field(
        "max_spread", "Max chord spread", d.max_spread, *_MAX_SPREAD_BOUNDS
    )

    range_low = parse_optional_midi("range_low", "Range low (MIDI)")
    range_high = parse_optional_midi("range_high", "Range high (MIDI)")

    if errors:
        return None, errors

    assert spacing_octave is not None
    assert span_tight_threshold is not None
    assert span_wide_threshold is not None
    assert max_spread is not None

    if span_tight_threshold >= span_wide_threshold:
        errors.append(
            "Span tight threshold must be less than span wide threshold."
        )
    if range_low is not None and range_high is not None and range_low > range_high:
        errors.append("Range low (MIDI) must be less than or equal to range high (MIDI).")
    if errors:
        return None, errors

    w = HarmonyWeights(
        cost_static=float_vals["cost_static"],
        cost_stepwise=float_vals["cost_stepwise"],
        cost_medium_step=float_vals["cost_medium_step"],
        cost_large_leap_base=float_vals["cost_large_leap_base"],
        cost_large_leap_per=float_vals["cost_large_leap_per"],
        cost_parallel_5_8=float_vals["cost_parallel_5_8"],
        cost_direct_5_8=float_vals["cost_direct_5_8"],
        cost_voice_crossing=float_vals["cost_voice_crossing"],
        bonus_contrary=float_vals["bonus_contrary"],
        cost_wide_gap_base=float_vals["cost_wide_gap_base"],
        cost_wide_gap_per=float_vals["cost_wide_gap_per"],
        spacing_octave=spacing_octave,
        cost_span_tight=float_vals["cost_span_tight"],
        cost_span_wide=float_vals["cost_span_wide"],
        span_tight_threshold=span_tight_threshold,
        span_wide_threshold=span_wide_threshold,
        range_low=range_low,
        range_high=range_high,
        max_spread=max_spread,
    )
    return w, []


def weights_from_form(form: Dict[str, str]) -> HarmonyWeights:
    """Strict parse; raises ValueError if any submitted field is invalid."""
    w, errs = parse_weights_from_form(form)
    if errs:
        raise ValueError("; ".join(errs))
    assert w is not None
    return w


@dataclass(frozen=True)
class Chord:
    symbol: str
    pitches: List[int]  # pitch classes 0–11 (unique, unordered)
    root_pc: int        # pitch class of the harmonic root
    bass_pc: Optional[int] = None  # explicit bass (for slash chords), else None
    # (pc, role) for omission: when voices < len(pitches), drop 5th first, then 9th, 11th, 13th.
    tone_roles: Optional[Tuple[Tuple[int, int], ...]] = None  # ((pc, role), ...); role in INCLUSION_ORDER


@dataclass
class HarmonyResult:
    chords: List[Chord]
    voices: List[List[int]]  # voices[v][t] = MIDI pitch number at time t

    def as_note_names(self) -> List[List[str]]:
        return [[midi_to_name(p) for p in voice] for voice in self.voices]


def midi_to_name(m: int) -> str:
    names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    pc = m % 12
    octave = m // 12 - 1
    return f"{names[pc]}{octave}"


def parse_chord_symbol(symbol: str) -> Chord:
    s = symbol.strip()
    if not s:
        raise ValueError("Empty chord symbol")

    # Handle inversions / slash chords, e.g. C/E, Am/G.
    # Important: patterns like "F6/9" are NOT slash chords; "/9" is part of the quality,
    # so only treat "/" as a bass separator when the part after "/" starts with a pitch letter.
    bass_pc: Optional[int] = None
    if "/" in s:
        main, bass = s.split("/", 1)
        tentative_bass = bass.strip()
        if tentative_bass and tentative_bass[0].upper() in "ABCDEFG":
            s_main = main.strip()
            s_bass = tentative_bass
        else:
            # e.g. "F6/9" → keep entire symbol as main quality, no explicit bass
            s_main = s
            s_bass = ""
    else:
        s_main = s
        s_bass = ""

    # Parse bass, if given
    if s_bass:
        # Bass can be like E, Eb, F#
        bass_root = s_bass[0].upper()
        bass_rest = s_bass[1:]
        if bass_rest and bass_rest[0] in ("b", "#"):
            # Keep accidental case as in map keys (e.g. "Ab", "Db")
            bass_root += bass_rest[0]
        if bass_root not in PITCH_CLASS_MAP:
            raise ValueError(f"Unknown bass in chord symbol: {symbol}")
        bass_pc = PITCH_CLASS_MAP[bass_root]

    # Root (with possible accidental)
    root = s_main[0].upper()
    rest = s_main[1:]
    if rest and rest[0] in ("b", "#"):
        # Keep accidental case as in map keys (e.g. "Ab", "Db")
        root += rest[0]
        rest = rest[1:]

    if root not in PITCH_CLASS_MAP:
        raise ValueError(f"Unknown root in chord symbol: {symbol}")

    pc = PITCH_CLASS_MAP[root]
    quality = rest

    structure = _build_chord_structure(pc, quality)
    pcs = sorted(set(pc for pc, _ in structure))
    roles = tuple(structure) if structure else None

    return Chord(symbol=symbol, pitches=pcs, root_pc=pc, bass_pc=bass_pc, tone_roles=roles)


def _build_chord_structure(root_pc: int, quality: str) -> List[Tuple[int, int]]:
    """
    Build chord as list of (pitch_class, role) for omission priority.
    When voices < chord tones, we drop tones by role: 5th first, then 9th, 11th, 13th.
    """
    q = quality.strip()
    q_lower = q.lower()

    def pc_of(semitones: int) -> int:
        return (root_pc + semitones) % 12

    out: List[Tuple[int, int]] = []
    third = 4
    fifth = 7
    # Altered fifth on top of basic qualities (e.g. maj7#5, maj7b5)
    if "#5" in q_lower:
        fifth = 8
    elif "b5" in q_lower:
        fifth = 6

    # Triad base
    if "sus2" in q_lower:
        out = [(pc_of(0), ROOT), (pc_of(2), THIRD), (pc_of(fifth), FIFTH)]
    elif "sus4" in q_lower or ("sus" in q_lower and "sus2" not in q_lower):
        out = [(pc_of(0), ROOT), (pc_of(5), THIRD), (pc_of(fifth), FIFTH)]
    elif any(q_lower.startswith(x) for x in ("m7b5", "ø7", "ø")):
        return [(pc_of(0), ROOT), (pc_of(3), THIRD), (pc_of(6), FIFTH), (pc_of(10), SEVENTH)]
    elif any(q_lower.startswith(x) for x in ("dim7", "o7")):
        return [(pc_of(0), ROOT), (pc_of(3), THIRD), (pc_of(6), FIFTH), (pc_of(9), SEVENTH)]
    elif q_lower.startswith(("dim", "o")):
        out = [(pc_of(0), ROOT), (pc_of(3), THIRD), (pc_of(6), FIFTH)]
    # Minor–major 7th chords (e.g. CmM7, CminMaj7): minor triad, major 7th added below.
    # Use q (original) so "M7" (major 7th) is not misread as minor when lowercased to "m7".
    elif q.startswith(("m", "min", "mi", "-")) and (
        "maj7" in q_lower or "M7" in q
    ):
        out = [(pc_of(0), ROOT), (pc_of(3), THIRD), (pc_of(fifth), FIFTH)]
    elif q_lower.startswith(("m", "min", "mi", "-")) and "maj" not in q_lower and "M7" not in q:
        out = [(pc_of(0), ROOT), (pc_of(3), THIRD), (pc_of(fifth), FIFTH)]
    elif q_lower.startswith(("aug", "+")):
        out = [(pc_of(0), ROOT), (pc_of(4), THIRD), (pc_of(8), FIFTH)]
    else:
        out = [(pc_of(0), ROOT), (pc_of(4), THIRD), (pc_of(fifth), FIFTH)]

    # 6th
    if "6/9" in q_lower or "69" in q_lower:
        out.append((pc_of(9), SIXTH))
        out.append((pc_of(14), NINTH))
    elif "6" in q_lower and "add6" not in q_lower:
        out.append((pc_of(9), SIXTH))

    # 7th: major 7th for maj7/maj9/maj11/maj13/maj#11; minor 7th for dominant 7,9,11,13
    if (
        any(x in q_lower for x in ("maj7", "maj9", "maj11", "maj13", "maj#11", "Δ7", "Δ"))
        or "M7" in q
    ):
        out.append((pc_of(11), SEVENTH))
    # For dominant / extended chords (C7, C9, C11, C13) add minor 7th; not for 6/9 or maj* extensions
    elif not ("6/9" in q_lower or "69" in q_lower) and any(
        x in q_lower for x in ("7", "9", "11", "13")
    ):
        out.append((pc_of(10), SEVENTH))

    # Extensions (natural 9/11/13 only when not altered; b9/#9, b11/#11, b13/#13 handled below)
    if "9" in q_lower and "b9" not in q_lower and "#9" not in q_lower:
        out.append((pc_of(14), NINTH))
    if "11" in q_lower and "b11" not in q_lower and "#11" not in q_lower:
        out.append((pc_of(17), ELEVENTH))
    if "13" in q_lower and "b13" not in q_lower and "#13" not in q_lower:
        out.append((pc_of(21), THIRTEENTH))
    if "add2" in q_lower or "add9" in q_lower:
        out.append((pc_of(14), NINTH))
    if "add4" in q_lower or "add11" in q_lower:
        out.append((pc_of(17), ELEVENTH))
    if "add6" in q_lower:
        out.append((pc_of(9), SIXTH))
    if "b9" in q_lower:
        out.append((pc_of(13), NINTH))
    if "#9" in q_lower:
        out.append((pc_of(15), NINTH))
    if "b11" in q_lower:
        out.append((pc_of(16), ELEVENTH))
    if "#11" in q_lower:
        out.append((pc_of(18), ELEVENTH))
        # In practice, #11 tensions almost always come with a 9; add 9 if not already requested.
        if "9" not in q_lower and "add9" not in q_lower and "b9" not in q_lower and "#9" not in q_lower:
            out.append((pc_of(14), NINTH))
    if "b13" in q_lower:
        out.append((pc_of(20), THIRTEENTH))
    if "#13" in q_lower:
        out.append((pc_of(22), THIRTEENTH))

    # Dedupe by pc, keeping first occurrence (so root/3rd/7th stay)
    seen: set[int] = set()
    unique: List[Tuple[int, int]] = []
    for pc, role in out:
        if pc not in seen:
            seen.add(pc)
            unique.append((pc, role))
    return unique


def _effective_chord_tones(chord: Chord, num_voices: int) -> List[int]:
    """
    When chord has more tones than voices, omit by role: 5th first, then 9th, 11th, 13th.
    E.g. G9 with 4 voices → use root, 3rd, 7th, 9th (omit 5th).
    """
    pcs = chord.pitches
    if len(pcs) <= num_voices or chord.tone_roles is None:
        return list(pcs)
    # Sort by inclusion priority (root, 3rd, 7th, 9th, 5th, …), take first num_voices
    order_idx = {r: i for i, r in enumerate(INCLUSION_ORDER)}
    sorted_roles = sorted(
        chord.tone_roles,
        key=lambda x: order_idx.get(x[1], 99),
    )
    return [pc for pc, _ in sorted_roles[:num_voices]]


def parse_progression(text: str) -> List[Chord]:
    # Split on common separators
    tokens: List[str] = []
    for part in text.replace("|", " ").replace(",", " ").split():
        tokens.append(part)
    if not tokens:
        raise ValueError("No chords found in progression.")
    return [parse_chord_symbol(tok) for tok in tokens]


def chord_structure_fingerprint(ch: Chord) -> Tuple[Any, ...]:
    """Stable tuple for comparing progressions using parser semantics (not lowercased text)."""
    return (ch.root_pc, ch.bass_pc, tuple(sorted(ch.pitches)), ch.tone_roles)


def progression_structure_fingerprint(text: str) -> Optional[Tuple[Tuple[Any, ...], ...]]:
    """Return None if empty or progression cannot be parsed."""
    if not (text or "").strip():
        return None
    try:
        chords = parse_progression(text)
    except ValueError:
        return None
    return tuple(chord_structure_fingerprint(c) for c in chords)


def progressions_structurally_equal(a: str, b: str) -> bool:
    fa = progression_structure_fingerprint(a)
    fb = progression_structure_fingerprint(b)
    if fa is None or fb is None:
        return False
    return fa == fb


def chord_harmonic_fingerprint(ch: Chord) -> Tuple[int, Optional[int], Tuple[int, ...]]:
    """Root, slash bass, and pitch classes only (ignores tone_roles / internal tuple shape)."""
    return (ch.root_pc, ch.bass_pc, tuple(sorted(ch.pitches)))


def progression_harmonic_fingerprint(text: str) -> Optional[Tuple[Tuple[int, Optional[int], Tuple[int, ...]], ...]]:
    if not (text or "").strip():
        return None
    try:
        chords = parse_progression(text)
    except ValueError:
        return None
    return tuple(chord_harmonic_fingerprint(c) for c in chords)


def progressions_harmonically_equal(a: str, b: str) -> bool:
    ha = progression_harmonic_fingerprint(a)
    hb = progression_harmonic_fingerprint(b)
    if ha is None or hb is None:
        return False
    return ha == hb


def progressions_equivalent_for_ui(a: str, b: str) -> bool:
    """Structural match, or same root/bass/pitch-class set per step (handles tone_roles drift)."""
    if progressions_structurally_equal(a, b):
        return True
    return progressions_harmonically_equal(a, b)


def generate_harmony(
    progression: Sequence[Chord],
    num_voices: int = 4,
    base_octave: int = 4,
    weights: Optional[HarmonyWeights] = None,
    locked_voicings: Optional[Dict[int, Sequence[int]]] = None,
) -> HarmonyResult:
    """
    locked_voicings: optional dict chord_index -> voicing (list/tuple of MIDI, lowest to highest).
    Locked chords use that single voicing; others are optimized.
    """
    if num_voices < 4:
        raise ValueError("At least 4 voices are required.")
    if num_voices > 6:
        raise ValueError("More than 6 voices is not supported in this simple model.")

    w = weights or default_weights()
    pr = VOICE_RANGES.get(num_voices, (48, 79))
    low = w.range_low if w.range_low is not None else pr[0]
    high = w.range_high if w.range_high is not None else pr[1]

    locked = locked_voicings or {}
    candidates_per_step: List[List[Tuple[int, ...]]] = []
    for i, chord in enumerate(progression):
        if i in locked:
            raw = locked[i]
            if len(raw) != num_voices:
                raise ValueError(
                    f"Locked voicing for chord {i + 1} has {len(raw)} notes; expected {num_voices}."
                )
            candidates_per_step.append([tuple(sorted(raw))])
            continue
        candidates = generate_voicings_for_chord(
            chord, num_voices, low, high, base_octave, max_spread=w.max_spread
        )
        if not candidates:
            raise RuntimeError(f"No voicings generated for chord {chord.symbol}")
        candidates_per_step.append(candidates)

    paths: List[Dict[int, Tuple[float, Optional[int]]]] = []
    first_chord = progression[0]
    last_chord = progression[-1]

    first_step: Dict[int, Tuple[float, Optional[int]]] = {}
    for i, voicing in enumerate(candidates_per_step[0]):
        cost = voice_leading_cost(None, voicing, w, curr_chord=first_chord)
        cost += _bass_root_preference_cost(voicing, first_chord)
        first_step[i] = (cost, None)
    paths.append(first_step)

    for step in range(1, len(progression)):
        prev_states = paths[-1]
        curr_states: Dict[int, Tuple[float, Optional[int]]] = {}
        same_as_prev = progression[step].symbol == progression[step - 1].symbol
        is_last = step == len(progression) - 1
        for i, curr_voicing in enumerate(candidates_per_step[step]):
            best_cost = float("inf")
            best_prev: Optional[int] = None
            for j, (prev_cost, _) in prev_states.items():
                prev_voicing = candidates_per_step[step - 1][j]
                c = prev_cost + voice_leading_cost(
                    prev_voicing, curr_voicing, w, same_chord=same_as_prev,
                    curr_chord=progression[step],
                )
                if is_last:
                    c += _bass_root_preference_cost(curr_voicing, last_chord)
                if c < best_cost:
                    best_cost = c
                    best_prev = j
            curr_states[i] = (best_cost, best_prev)
        paths.append(curr_states)

    # Backtrack best path
    final_states = paths[-1]
    last_idx = min(final_states, key=lambda k: final_states[k][0])

    indices: List[int] = [last_idx]
    for step in range(len(progression) - 1, 0, -1):
        _, prev_idx = paths[step][indices[-1]]
        assert prev_idx is not None
        indices.append(prev_idx)
    indices.reverse()

    chosen_voicings = [candidates_per_step[step][idx] for step, idx in enumerate(indices)]

    # Transpose into voices (chord_voicing is lowest to highest)
    voices: List[List[int]] = [[] for _ in range(num_voices)]
    for chord_voicing in chosen_voicings:
        for v_idx, note in enumerate(chord_voicing):
            voices[v_idx].append(note)

    # Return highest voice first, then descending to lowest
    voices = list(reversed(voices))

    return HarmonyResult(chords=list(progression), voices=voices)


def get_chord_alternatives(
    progression: Sequence[Chord],
    num_voices: int,
    weights: Optional[HarmonyWeights],
    path_voicings: List[Tuple[int, ...]],
    chord_index: int,
    top_n: int = 8,
) -> List[Tuple[Tuple[int, ...], float]]:
    """
    Return alternative voicings for one chord, scored by local cost (prev -> cand -> next).
    path_voicings[t] = voicing at step t (lowest to highest). Returns list of (voicing, cost) sorted by cost.
    """
    if chord_index < 0 or chord_index >= len(progression):
        return []
    w = weights or default_weights()
    pr = VOICE_RANGES.get(num_voices, (48, 79))
    low = w.range_low if w.range_low is not None else pr[0]
    high = w.range_high if w.range_high is not None else pr[1]

    prev = path_voicings[chord_index - 1] if chord_index > 0 else None
    next_v = (
        path_voicings[chord_index + 1]
        if chord_index + 1 < len(path_voicings)
        else None
    )
    chord = progression[chord_index]
    same_as_prev = (
        chord_index > 0
        and progression[chord_index].symbol == progression[chord_index - 1].symbol
    )
    same_as_next = (
        chord_index + 1 < len(progression)
        and progression[chord_index].symbol == progression[chord_index + 1].symbol
    )
    candidates = generate_voicings_for_chord(
        chord, num_voices, low, high, base_octave=4, max_spread=w.max_spread
    )
    is_first = chord_index == 0
    is_last = chord_index == len(progression) - 1
    scored: List[Tuple[Tuple[int, ...], float]] = []
    for c in candidates:
        cost = voice_leading_cost(prev, c, w, same_chord=same_as_prev, curr_chord=chord)
        if next_v is not None:
            cost += voice_leading_cost(
                c, next_v, w, same_chord=same_as_next,
                curr_chord=progression[chord_index + 1],
            )
        if is_first or is_last:
            cost += _bass_root_preference_cost(c, chord)
        scored.append((c, cost))
    scored.sort(key=lambda x: x[1])
    return scored[:top_n]


def generate_voicings_for_chord(
    chord: Chord,
    num_voices: int,
    low: int,
    high: int,
    base_octave: int = 4,
    max_spread: int = 16,
) -> List[Tuple[int, ...]]:
    # When chord has more tones than voices (e.g. G9 with 4 voices), use effective set:
    # omit 5th first, then 9th, 11th, 13th (see _effective_chord_tones).
    effective_pcs = _effective_chord_tones(chord, num_voices)
    if len(effective_pcs) == 0:
        return []

    root_pc = chord.root_pc
    bass_pc = chord.bass_pc

    # Slash chord with bass not in chord (e.g. Dm7b5/E): bass takes one slot, upper voices from chord.
    if bass_pc is not None and bass_pc not in effective_pcs:
        return _voicings_slash_bass_outside(
            chord, num_voices, low, high, base_octave, max_spread, effective_pcs
        )

    # Build candidate chord tones from effective set only (bass may be in chord, e.g. Gsus/C)
    tone_midis: List[int] = []
    for octave in range(2, 7):
        for pc in effective_pcs:
            m = pc + 12 * octave
            if low <= m <= high:
                tone_midis.append(m)

    tone_midis = sorted(set(tone_midis))

    # When we have more voices than chord tones (e.g. GM7 with 6 voices), allow doubling beyond root.
    max_root = 2
    max_other = 2 if num_voices > len(effective_pcs) else 1
    max_per_pc = max(2, (num_voices + len(effective_pcs) - 1) // len(effective_pcs))
    max_other = min(max_other, max_per_pc)

    voicings: List[Tuple[int, ...]] = []

    def backtrack(
        current: List[int],
        start_idx: int,
        used_pcs: set[int],
        counts: Dict[int, int],
    ) -> None:
        if len(current) == num_voices:
            if current[-1] - current[0] <= max_spread:
                if all(pc in used_pcs for pc in effective_pcs):
                    if bass_pc is not None and (current[0] % 12) != bass_pc:
                        return
                    voicings.append(tuple(current))
            return

        for i in range(start_idx, len(tone_midis)):
            note = tone_midis[i]
            if current and note < current[-1]:
                continue
            pc = note % 12
            if pc not in effective_pcs:
                continue
            existing = counts.get(pc, 0)
            cap = max_root if pc == root_pc else max_other
            if existing >= cap:
                continue
            new_used = set(used_pcs)
            new_used.add(pc)
            new_counts = dict(counts)
            new_counts[pc] = existing + 1
            backtrack(current + [note], i, new_used, new_counts)

    backtrack([], 0, set(), {})

    # Limit number of voicings for performance
    if len(voicings) > 500:
        voicings = voicings[:500]

    return voicings


def _voicings_slash_bass_outside(
    chord: Chord,
    num_voices: int,
    low: int,
    high: int,
    base_octave: int,
    max_spread: int,
    effective_pcs: List[int],
) -> List[Tuple[int, ...]]:
    """Generate voicings when bass is not a chord tone (e.g. Dm7b5/E): one bass note + (n-1) chord tones above."""
    assert chord.bass_pc is not None
    bass_pc = chord.bass_pc
    upper_count = num_voices - 1
    if upper_count <= 0:
        return []
    effective_upper = _effective_chord_tones(chord, upper_count)
    if len(effective_upper) == 0:
        return []

    voicings: List[Tuple[int, ...]] = []
    for octave in range(2, 6):
        bass_note = bass_pc + 12 * octave
        if bass_note < low or bass_note > high:
            continue
        upper_low = bass_note + 1
        if upper_low > high:
            continue
        upper_candidates = _generate_upper_voicings(
            chord, upper_count, upper_low, high, max_spread, effective_upper
        )
        for u in upper_candidates:
            if u[0] - bass_note <= max_spread:
                voicings.append((bass_note,) + u)
    if len(voicings) > 500:
        voicings = voicings[:500]
    return voicings


def _generate_upper_voicings(
    chord: Chord,
    num_voices: int,
    low: int,
    high: int,
    max_spread: int,
    effective_pcs: List[int],
) -> List[Tuple[int, ...]]:
    """Generate (num_voices) notes from chord in [low, high], all from effective_pcs."""
    root_pc = chord.root_pc
    tone_midis = []
    for octave in range(2, 7):
        for pc in effective_pcs:
            m = pc + 12 * octave
            if low <= m <= high:
                tone_midis.append(m)
    tone_midis = sorted(set(tone_midis))
    max_root = 2
    max_other = 2 if num_voices > len(effective_pcs) else 1
    max_per_pc = max(2, (num_voices + len(effective_pcs) - 1) // len(effective_pcs))
    max_other = min(max_other, max_per_pc)

    out: List[Tuple[int, ...]] = []

    def backtrack(
        current: List[int],
        start_idx: int,
        used_pcs: set[int],
        counts: Dict[int, int],
    ) -> None:
        if len(current) == num_voices:
            if current[-1] - current[0] <= max_spread and all(
                pc in used_pcs for pc in effective_pcs
            ):
                out.append(tuple(current))
            return
        for i in range(start_idx, len(tone_midis)):
            note = tone_midis[i]
            if current and note < current[-1]:
                continue
            pc = note % 12
            if pc not in effective_pcs:
                continue
            existing = counts.get(pc, 0)
            cap = max_root if pc == root_pc else max_other
            if existing >= cap:
                continue
            new_used = set(used_pcs)
            new_used.add(pc)
            new_counts = dict(counts)
            new_counts[pc] = existing + 1
            backtrack(current + [note], i, new_used, new_counts)

    backtrack([], 0, set(), {})
    return out


def voice_leading_cost(
    prev: Optional[Tuple[int, ...]],
    curr: Tuple[int, ...],
    weights: Optional[HarmonyWeights] = None,
    same_chord: bool = False,
    curr_chord: Optional[Chord] = None,
) -> float:
    """
    Cost for a single chord-to-chord transition (basic harmony/counterpoint rules).
    Voicing tuples are ordered lowest to highest (bass = index 0, soprano = index -1).
    same_chord: when True, identical adjacent chords — static voice gets no penalty.
    curr_chord: when provided, used to penalize bass = chord's major 7th (e.g. 3rd inversion maj7).
    """
    w = weights or default_weights()
    cost = 0.0
    # Strong penalty when chord has a major 7th and the bass is that 7th (root in bass preferred)
    if curr_chord is not None and len(curr) > 0:
        major_7th_pc = (curr_chord.root_pc + 11) % 12
        if major_7th_pc in curr_chord.pitches and (curr[0] % 12) == major_7th_pc:
            cost += 6.0
    # Penalty for doubling the 3rd in triads (major or minor)
    if curr_chord is not None:
        cost += _doubling_third_cost(curr, curr_chord)
    if prev is None:
        return cost + chord_internal_cost(curr, w)

    n = len(prev)

    for p, c in zip(prev, curr):
        step = abs(c - p)
        if step == 0:
            if not same_chord:
                cost += w.cost_static
        elif step == 1 or step == 2:
            cost += w.cost_stepwise
        elif step <= 5:
            cost += w.cost_medium_step
        else:
            cost += w.cost_large_leap_base + w.cost_large_leap_per * (step - 5)

    for i in range(n):
        for j in range(i + 1, n):
            interval_prev = abs(prev[j] - prev[i]) % 12
            interval_curr = abs(curr[j] - curr[i]) % 12
            if interval_prev in (7, 0) and interval_curr == interval_prev:
                cost += w.cost_parallel_5_8

    if n >= 2:
        bass_prev, bass_curr = prev[0], curr[0]
        sop_prev, sop_curr = prev[-1], curr[-1]
        interval_curr = abs(sop_curr - bass_curr) % 12
        if interval_curr in (0, 7):
            bass_dir = bass_curr - bass_prev
            sop_dir = sop_curr - sop_prev
            if bass_dir != 0 and sop_dir != 0 and (bass_dir > 0) == (sop_dir > 0):
                cost += w.cost_direct_5_8

    for i in range(n):
        for j in range(i + 1, n):
            if (prev[i] - prev[j]) * (curr[i] - curr[j]) < 0:
                cost += w.cost_voice_crossing

    if n >= 2:
        bass_dir = curr[0] - prev[0]
        sop_dir = curr[-1] - prev[-1]
        if bass_dir != 0 and sop_dir != 0 and (bass_dir > 0) != (sop_dir > 0):
            cost -= w.bonus_contrary

    octave = w.spacing_octave
    for i in range(len(curr) - 1):
        dist = curr[i + 1] - curr[i]
        if dist > octave:
            cost += w.cost_wide_gap_base + w.cost_wide_gap_per * (dist - octave)
        # Lowest two voices (bass and next): penalty when 1 or 2 semitones apart (muddy spacing)
        if i == 0 and (dist == 1 or dist == 2):
            cost += 2.0
        # Bass and 2nd lowest forming a perfect 4th (5 semitones) — avoid in classical-style spacing
        if i == 0 and dist % 12 == 5:
            cost += 2.0
        # Inner voices (indices 1..n-2): extra penalty if gap too wide
        if 1 <= i <= n - 2 and dist > octave:
            cost += 0.4
        # Adjacent voices: avoid major 7th (11 semitones) and minor 9th (13 semitones)
        if dist == 11 or dist == 13:
            cost += 2.0

    # Outer voices (bass and soprano): strong penalty for minor 2nd or derivatives (e.g. minor 9th)
    if n >= 2:
        outer_interval = (curr[-1] - curr[0]) % 12
        if outer_interval == 1:  # minor 2nd / minor 9th / etc.
            cost += 6.0

    # Interval penalty by pitch range: close intervals (1–2, 3–4, 5–6 semitones) more muddy in lower register
    for i in range(len(curr) - 1):
        dist = curr[i + 1] - curr[i]
        if 1 <= dist <= 6:
            cost += _interval_in_range_penalty(curr[i], dist)

    cost += chord_internal_cost(curr, w)
    return cost


def _interval_in_range_penalty(low_note_midi: int, interval_semitones: int) -> float:
    """
    Penalty for a close interval between adjacent voices, scaled by the lower note's
    register (lower = more penalty). Intervals are grouped: 1–2 st use same cost as 2,
    3–4 st as 4, 5–6 st as 6.
    """
    # Bucket: 1–2 semitones → idx 0, 3–4 → idx 1, 5–6 → idx 2
    if interval_semitones < 1 or interval_semitones > 6:
        return 0.0
    bucket = (interval_semitones - 1) // 2  # 0, 0, 1, 1, 2, 2 for 1..6
    # (range_low_midi, range_high_midi): (cost for 1–2st, for 3–4st, for 5–6st)
    # C2 = 36, C3 = 48, C4 = 60, C5 = 72, C6 = 84
    RANGE_TABLE = [
        (24, 35),   # C1–B1: very low
        (36, 47),   # C2–B2
        (48, 59),   # C3–B3
        (60, 71),   # C4–B4
        (72, 83),   # C5–B5
        (84, 127),  # C6 and above
    ]
    PENALTIES = [
        (1.5, 1.0, 0.3),   # C1–B1
        (1.2, 0.8, 0.2),   # C2–B2
        (0.6, 0.4, 0.2),   # C3–B3
        (0.3, 0.2, 0.1),   # C4–B4
        (0.15, 0.1, 0.05), # C5–B5
        (0.0, 0.0, 0.0),   # C6+ no penalty
    ]
    for (lo, hi), (c_12, c_34, c_56) in zip(RANGE_TABLE, PENALTIES):
        if lo <= low_note_midi <= hi:
            return (c_12, c_34, c_56)[bucket]
    return 0.0


def _third_pc(chord: Chord) -> Optional[int]:
    """Pitch class of the chord's 3rd (major or minor) if present (triad or triad-based). Else None."""
    root = chord.root_pc
    major_3rd = (root + 4) % 12
    minor_3rd = (root + 3) % 12
    if major_3rd in chord.pitches:
        return major_3rd
    if minor_3rd in chord.pitches:
        return minor_3rd
    return None


def _doubling_third_cost(voicing: Tuple[int, ...], chord: Chord) -> float:
    """Penalty when the 3rd of a triad is doubled (two or more voices on the 3rd)."""
    third = _third_pc(chord)
    if third is None or not voicing:
        return 0.0
    count = sum(1 for n in voicing if (n % 12) == third)
    return 2.0 if count >= 2 else 0.0


def _bass_root_preference_cost(voicing: Tuple[int, ...], chord: Chord) -> float:
    """Cost added when bass is not the chord root (for first/last chord preference). Strong so root position is very likely."""
    if not voicing:
        return 0.0
    bass_pc = voicing[0] % 12
    return 0.0 if bass_pc == chord.root_pc else 4.0


def chord_internal_cost(
    voicing: Tuple[int, ...],
    weights: Optional[HarmonyWeights] = None,
) -> float:
    w = weights or default_weights()
    low, high = min(voicing), max(voicing)
    span = high - low
    cost = 0.0
    if span < w.span_tight_threshold:
        cost += w.cost_span_tight
    if span > w.span_wide_threshold:
        cost += w.cost_span_wide
    return cost


def export_to_midi(result: HarmonyResult, filename: str = "output.mid") -> None:
    """
    Backwards-compatible wrapper for MIDI export.

    Delegates to the shared midi_handler module using the default \"woodwind\" mode,
    so existing code keeps the original behaviour while newer code can call
    midi_handler.export_harmony_to_midi with richer options.
    """
    from midi_handler import export_harmony_to_midi  # type: ignore

    export_harmony_to_midi(result, filename=filename, mode="woodwind")

