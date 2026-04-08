from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import asdict
from flask import Flask, flash, request, redirect, url_for, render_template, send_file, session
from werkzeug.exceptions import RequestEntityTooLarge

from harmony import (
    HarmonyResult,
    HarmonyWeights,
    MAX_PROGRESSION_INPUT_CHARS,
    MAX_PROGRESSION_CHORDS,
    parse_progression,
    generate_harmony,
    default_weights,
    parse_weights_from_form,
    weights_form_snapshot,
    weights_from_dict,
    get_chord_alternatives,
    midi_to_name,
    progressions_equivalent_for_ui,
)
from midi_handler import export_harmony_to_midi  # type: ignore
from lock_parsing import parse_locked_voicings as _parse_locked_voicings

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-insecure-change-for-public-deployment")
# Cap POST body size so pasted progressions cannot exhaust memory (slightly above text limit).
app.config["MAX_CONTENT_LENGTH"] = max(MAX_PROGRESSION_INPUT_CHARS * 4, 512 * 1024)
logger = logging.getLogger(__name__)

# What-if recomputes voicings per step; skip beyond this to keep responses fast.
WHATIF_MAX_CHORDS = 32

SESSION_STICKY_KEY = "harmony_sticky_v1"
MIDI_FILENAME = "output.mid"
APP_ROOT = os.path.abspath(os.path.dirname(__file__))
MIDI_OUTPUT_PATH = os.path.join(APP_ROOT, MIDI_FILENAME)
STICKY_DISK_FILENAME = ".harmony_sticky_fallback.json"
STICKY_DISK_PATH = os.path.join(APP_ROOT, STICKY_DISK_FILENAME)
STICKY_DISK_VERSION = 1


def _chord_rows_from_result(result: HarmonyResult):
    """Lowest→highest voicing per step; chord_voicings + JSON strings + path tuples."""
    n = len(result.voices)
    num_chords = len(result.chords)
    path_voicings = [
        tuple(result.voices[n - 1 - v][t] for v in range(n)) for t in range(num_chords)
    ]
    chord_voicings = [list(p) for p in path_voicings]
    chord_voicings_json_list = [json.dumps(cv) for cv in chord_voicings]
    return chord_voicings, chord_voicings_json_list, path_voicings


def _alternatives_from_path(
    chords,
    voices: int,
    weights: HarmonyWeights,
    path_voicings: list,
) -> list:
    alternatives_per_chord = []
    num_chords = len(chords)
    if num_chords > WHATIF_MAX_CHORDS:
        return [[] for _ in range(num_chords)]
    for k in range(num_chords):
        alts = get_chord_alternatives(chords, voices, weights, path_voicings, k)
        current = path_voicings[k]
        options = []
        for voicing, cost in alts:
            midi_list = list(voicing)
            options.append(
                {
                    "midi": midi_list,
                    "midi_json": json.dumps(midi_list),
                    "midi_str": ", ".join(str(m) for m in midi_list),
                    "note_names": ", ".join(midi_to_name(m) for m in midi_list),
                    "cost": round(cost, 2),
                    "is_current": voicing == current,
                }
            )
        alternatives_per_chord.append(options)
    return alternatives_per_chord


def _piano_roll_bounds(result):
    """Return (pitch_min, pitch_max) for the result's full pitch range."""
    if not result or not result.voices:
        return 48, 72
    all_pitches = [n for v in result.voices for n in v]
    return min(all_pitches), max(all_pitches)


# Register filter so template can show note names from MIDI numbers
@app.template_filter("midi_to_name")
def _midi_to_name_filter(midi_num):
    if midi_num is None:
        return ""
    try:
        return midi_to_name(int(midi_num))
    except (TypeError, ValueError):
        return ""


def _display_music_accidentals(s: str) -> str:
    """
    UI-only: ASCII # / b → Unicode ♯ / ♭ for chord and note display.
    Does not affect parsing or stored data. Suffix flats only after A–G to avoid
    touching English words (e.g. 'ab').
    """
    if s is None:
        return ""
    t = str(s).replace("#", "\u266f")
    t = re.sub(r"(?<=[A-G])b", "\u266d", t)
    t = re.sub(r"^b(?=[A-G])", "\u266d", t)
    return t


@app.template_filter("display_music")
def _display_music_filter(s):
    return _display_music_accidentals(s)


def _weights_to_form(w) -> dict:
    """Convert HarmonyWeights to dict of string values for form pre-fill."""
    return {
        "cost_static": str(w.cost_static),
        "cost_stepwise": str(w.cost_stepwise),
        "cost_medium_step": str(w.cost_medium_step),
        "cost_large_leap_base": str(w.cost_large_leap_base),
        "cost_large_leap_per": str(w.cost_large_leap_per),
        "cost_parallel_5_8": str(w.cost_parallel_5_8),
        "cost_direct_5_8": str(w.cost_direct_5_8),
        "cost_voice_crossing": str(w.cost_voice_crossing),
        "bonus_contrary": str(w.bonus_contrary),
        "cost_wide_gap_base": str(w.cost_wide_gap_base),
        "cost_wide_gap_per": str(w.cost_wide_gap_per),
        "spacing_octave": str(w.spacing_octave),
        "cost_span_tight": str(w.cost_span_tight),
        "cost_span_wide": str(w.cost_span_wide),
        "span_tight_threshold": str(w.span_tight_threshold),
        "span_wide_threshold": str(w.span_wide_threshold),
        "range_low": str(w.range_low) if w.range_low is not None else "",
        "range_high": str(w.range_high) if w.range_high is not None else "",
        "max_spread": str(w.max_spread),
        "bonus_leading_tone": str(w.bonus_leading_tone),
        "bonus_seventh_resolve": str(w.bonus_seventh_resolve),
        "cost_slash_bass_mismatch": str(w.cost_slash_bass_mismatch),
        "max_voicings_per_chord": str(w.max_voicings_per_chord),
        "beam_width": str(w.beam_width),
    }


def _compute_result_extras(
    chords,
    voices: int,
    weights: HarmonyWeights,
    result: HarmonyResult,
):
    """Build chord_voicings, JSON list, and alternatives for template."""
    chord_voicings, chord_voicings_json_list, path_voicings = _chord_rows_from_result(
        result
    )
    alternatives_per_chord = _alternatives_from_path(
        chords, voices, weights, path_voicings
    )
    return chord_voicings, chord_voicings_json_list, alternatives_per_chord


def _sticky_base_dict(
    progression_text: str,
    voices: int,
    result: HarmonyResult,
    weights: HarmonyWeights,
    midi_available: bool,
    midi_mode: str,
    midi_pattern: str,
    midi_bpm_form: str,
    midi_export_error: str | None,
    locked_voicings_form: dict[str, list[int]],
    saved_at: float,
) -> dict:
    return {
        "progression": progression_text,
        "num_voices": voices,
        "voices_midi": result.voices,
        "weights": asdict(weights),
        "midi_available": midi_available,
        "midi_mode": midi_mode,
        "midi_pattern": midi_pattern,
        "midi_bpm_form": midi_bpm_form or "",
        "midi_export_error": (midi_export_error or ""),
        "locked_voicings": locked_voicings_form,
        "_saved_at": saved_at,
    }


def _persist_sticky_snapshot(
    progression_text: str,
    voices: int,
    result: HarmonyResult,
    weights: HarmonyWeights,
    midi_available: bool,
    midi_mode: str,
    midi_pattern: str,
    midi_bpm_form: str,
    midi_export_error: str | None,
    alternatives_per_chord: list,
    locked_voicings_form: dict[str, list[int]],
) -> tuple[bool, bool, float]:
    """
    Save last success to session (compact) and disk (includes What-if cache).
    Returns (session_ok, disk_ok, saved_at).
    """
    saved_at = time.time()
    base = _sticky_base_dict(
        progression_text,
        voices,
        result,
        weights,
        midi_available,
        midi_mode,
        midi_pattern,
        midi_bpm_form,
        midi_export_error,
        locked_voicings_form,
        saved_at,
    )
    session_ok = True
    try:
        session[SESSION_STICKY_KEY] = base
    except Exception as exc:  # pragma: no cover - cookie size etc.
        logger.warning("Could not store session snapshot of last result: %s", exc)
        session.pop(SESSION_STICKY_KEY, None)
        session_ok = False

    disk_ok = False
    disk_payload = {
        **base,
        "_v": STICKY_DISK_VERSION,
        "alternatives_per_chord": alternatives_per_chord,
    }
    try:
        with open(STICKY_DISK_PATH, "w", encoding="utf-8") as f:
            json.dump(disk_payload, f, ensure_ascii=False)
        disk_ok = True
    except OSError as exc:
        logger.warning("Could not write sticky disk backup: %s", exc)
    return session_ok, disk_ok, saved_at


def _read_disk_sticky_dict() -> dict | None:
    if not os.path.isfile(STICKY_DISK_PATH):
        return None
    try:
        with open(STICKY_DISK_PATH, encoding="utf-8") as f:
            disk = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not read sticky disk backup: %s", exc)
        return None
    if not isinstance(disk, dict) or disk.get("_v") != STICKY_DISK_VERSION:
        return None
    return disk


def _sticky_timestamp(raw: dict, *, is_disk: bool) -> float:
    t = raw.get("_saved_at")
    if isinstance(t, (int, float)):
        return float(t)
    if is_disk:
        try:
            return os.path.getmtime(STICKY_DISK_PATH)
        except OSError:
            return 0.0
    return 0.0


def _load_sticky_raw() -> tuple[dict | None, str]:
    """
    Prefer the newest snapshot between session and disk (by _saved_at, else disk mtime).
    On equal timestamps, prefer disk (includes What-if cache).
    """
    s_raw = session.get(SESSION_STICKY_KEY)
    s = s_raw if isinstance(s_raw, dict) else None
    d = _read_disk_sticky_dict()
    if s and d:
        ts_s = _sticky_timestamp(s, is_disk=False)
        ts_d = _sticky_timestamp(d, is_disk=True)
        if ts_d > ts_s:
            return d, "disk"
        if ts_s > ts_d:
            return s, "session"
        return d, "disk"
    if s:
        return s, "session"
    if d:
        return d, "disk"
    return None, ""


def _discard_sticky_source(source: str) -> None:
    if source == "session":
        session.pop(SESSION_STICKY_KEY, None)
    elif source == "disk":
        try:
            os.remove(STICKY_DISK_PATH)
        except OSError as exc:
            logger.warning("Could not remove corrupt sticky disk file: %s", exc)


def _resolve_sticky_payload() -> tuple[dict | None, bool]:
    """
    Build display parts from the newest sticky snapshot.
    Returns (parts, warn_user): warn_user is True if backup data existed but was unusable
    and had to be removed (nothing usable left).
    """
    raw, src = _load_sticky_raw()
    if not raw:
        return None, False
    parts = _sticky_display_parts(raw, src)
    if parts:
        return parts, False
    logger.warning("Unusable sticky from %s; discarding that copy.", src)
    _discard_sticky_source(src)
    raw2, src2 = _load_sticky_raw()
    if not raw2:
        return None, True
    parts2 = _sticky_display_parts(raw2, src2)
    if not parts2:
        logger.warning("Unusable sticky from %s; discarding that copy.", src2)
        _discard_sticky_source(src2)
        return None, True
    return parts2, False


def _normalize_locked_form(raw_lv) -> dict[str, list[int]]:
    if not isinstance(raw_lv, dict):
        return {}
    out: dict[str, list[int]] = {}
    for k, v in raw_lv.items():
        if not isinstance(v, list) or not v or not all(isinstance(x, int) for x in v):
            continue
        try:
            out[str(int(k))] = v
        except (ValueError, TypeError):
            continue
    return out


def _sticky_display_parts(raw: dict, source: str) -> dict | None:
    """Rebuild harmony UI data from a sticky payload; None if invalid."""
    try:
        w = weights_from_dict(raw["weights"])
        prog = raw["progression"]
        chords = parse_progression(prog)
        result = HarmonyResult(chords=chords, voices=raw["voices_midi"])
    except Exception as exc:
        logger.warning("Invalid sticky payload (%s): %s", source, exc)
        return None

    nv = raw["num_voices"]
    if len(result.voices) != nv:
        return None
    n_steps = len(chords)
    if n_steps == 0 or any(len(row) != n_steps for row in result.voices):
        return None

    chord_voicings, chord_voicings_json_list, path_voicings = _chord_rows_from_result(
        result
    )
    disk_alts = raw.get("alternatives_per_chord")
    if (
        source == "disk"
        and isinstance(disk_alts, list)
        and len(disk_alts) == n_steps
        and n_steps <= WHATIF_MAX_CHORDS
    ):
        alternatives_per_chord = disk_alts
    else:
        alternatives_per_chord = _alternatives_from_path(
            chords, nv, w, path_voicings
        )

    mer = (raw.get("midi_export_error") or "").strip()
    locked_form = _normalize_locked_form(raw.get("locked_voicings"))
    return {
        "result": result,
        "note_names_by_voice": result.as_note_names(),
        "chord_voicings": chord_voicings,
        "chord_voicings_json_list": chord_voicings_json_list,
        "alternatives_per_chord": alternatives_per_chord,
        "weights": w,
        "num_voices": nv,
        "progression": raw.get("progression") or "",
        "midi_available": bool(raw.get("midi_available")),
        "midi_export_error": mer if mer else None,
        "midi_mode": (raw.get("midi_mode") or "woodwind").strip() or "woodwind",
        "midi_pattern": (raw.get("midi_pattern") or "default").strip() or "default",
        "midi_bpm_form": (raw.get("midi_bpm_form") or "").strip(),
        "locked_form": locked_form,
    }


def _try_restore_sticky(
    error: str | None,
    form_voices_int: int | None,
    current_progression: str,
    form_midi_mode: str,
    form_midi_pattern: str,
    form_midi_bpm: str,
    form_weights: HarmonyWeights | None,
) -> tuple[dict | None, bool]:
    """
    If there is an error and a prior successful result in session or disk, return
    (fields dict, False). If backup existed but was unusable, returns (None, True).
    Otherwise (None, False).
    """
    if not error:
        return None, False
    parts, unusable_evicted = _resolve_sticky_payload()
    if not parts:
        return None, unusable_evicted

    nv = parts["num_voices"]
    saved_prog = parts["progression"]
    w = parts["weights"]
    notices: list[str] = []
    if not progressions_equivalent_for_ui(current_progression, saved_prog):
        notices.append(
            "The chord progression in the text box does not match the chord row in the table "
            "(the parser treats some spellings as different chords, e.g. major 7 vs minor 7). "
            "The table is your last successful generation."
        )
    if form_voices_int is not None and form_voices_int != nv:
        notices.append(
            f"The table is your last successful result ({nv} voices); the form currently requests {form_voices_int}."
        )
    sm = parts["midi_mode"]
    sp = parts["midi_pattern"]
    sb = parts["midi_bpm_form"]
    fm = (form_midi_mode or "").strip()
    fp = (form_midi_pattern or "").strip()
    fb = (form_midi_bpm or "").strip()
    if fm != sm or fp != sp or fb != sb:
        notices.append(
            "MIDI mode, pattern, or BPM in the form may differ from the last successful run; "
            "the download link reflects that run’s export, not necessarily the controls as shown."
        )
    if form_weights is None:
        notices.append(
            "The Weights section could not be read (see errors above). "
            "The harmony table uses the last successful run’s weights."
        )
    elif form_weights != w:
        notices.append(
            "The Weights section differs from the last successful run. "
            "The table and What-if alternatives use the saved run’s weights until you click Generate again."
        )
    notices.append(
        "Fix the error above and click Generate again to recalculate. "
        "The download link assumes the MIDI file from that run is still on disk."
    )
    return {
        "result": parts["result"],
        "note_names_by_voice": parts["note_names_by_voice"],
        "chord_voicings": parts["chord_voicings"],
        "chord_voicings_json_list": parts["chord_voicings_json_list"],
        "alternatives_per_chord": parts["alternatives_per_chord"],
        "midi_available": parts["midi_available"],
        "midi_export_error": parts["midi_export_error"],
        "sticky_notices": notices,
        "sticky_saved_progression": saved_prog,
    }, False


def _reconcile_midi_with_file(
    midi_available: bool, midi_export_error: str | None
) -> tuple[bool, str | None]:
    """If the UI says MIDI exists but the file is gone, adjust flags and message."""
    if midi_available and not os.path.isfile(MIDI_OUTPUT_PATH):
        return False, (
            midi_export_error
            or "The MIDI file is no longer on disk (it may have been moved or deleted). Generate again to export."
        )
    return midi_available, midi_export_error


@app.errorhandler(RequestEntityTooLarge)
def handle_request_too_large(_e: RequestEntityTooLarge):
    flash(
        "That request was too large (for example, an extremely long chord list). "
        "Shorten the progression and try again.",
        "error",
    )
    return redirect(url_for("index"))


@app.route("/", methods=["GET", "POST"])
def index():
    error = None
    result = None
    note_names_by_voice = None
    voices = 4
    voices_display = "4"
    voices_int_for_sticky: int | None = 4
    progression_text = ""
    midi_mode = "woodwind"
    midi_pattern = "default"
    midi_bpm_form = ""
    midi_export_error = None
    midi_available = False
    weights_form = _weights_to_form(default_weights())
    chord_voicings = []
    chord_voicings_json_list = []
    alternatives_per_chord = []
    locked_voicings_json = "{}"
    locked_chord_indices = set()
    lock_warnings: list[str] = []
    sticky_notices: list[str] = []
    post_weights: HarmonyWeights | None = None
    post_weight_errs: list[str] = []

    if request.method == "GET":
        g_parts, g_sticky_warn = _resolve_sticky_payload()
        if g_parts:
            result = g_parts["result"]
            note_names_by_voice = g_parts["note_names_by_voice"]
            chord_voicings = g_parts["chord_voicings"]
            chord_voicings_json_list = g_parts["chord_voicings_json_list"]
            alternatives_per_chord = g_parts["alternatives_per_chord"]
            progression_text = g_parts["progression"]
            voices = g_parts["num_voices"]
            voices_display = str(voices)
            voices_int_for_sticky = voices
            weights_form = _weights_to_form(g_parts["weights"])
            midi_mode = g_parts["midi_mode"]
            midi_pattern = g_parts["midi_pattern"]
            midi_bpm_form = g_parts["midi_bpm_form"]
            midi_available = g_parts["midi_available"]
            midi_export_error = g_parts["midi_export_error"]
            lf = g_parts["locked_form"]
            locked_voicings_json = json.dumps(lf) if lf else "{}"
            locked_chord_indices = set()
            for k in lf:
                try:
                    locked_chord_indices.add(int(k))
                except ValueError:
                    pass
        elif g_sticky_warn:
            flash(
                "Saved harmony could not be restored (invalid or incomplete backup data). "
                "It was cleared—generate again to rebuild.",
                "warning",
            )

    if request.method == "POST":
        progression_text = request.form.get("progression", "").strip()
        voices_raw = request.form.get("voices", "").strip() or "4"
        voices_display = voices_raw
        midi_mode = request.form.get("midi_mode", "").strip() or "woodwind"
        midi_pattern = request.form.get("midi_pattern", "").strip() or "default"
        midi_bpm_form = request.form.get("midi_bpm", "").strip()
        weights_form = weights_form_snapshot(request.form)
        post_weights, post_weight_errs = parse_weights_from_form(request.form)
        raw_locked = request.form.get("locked_voicings", "") or ""
        locked_voicings_json = raw_locked.strip() if raw_locked.strip() else "{}"

        try:
            voices = int(voices_raw)
            if not (4 <= voices <= 6):
                raise ValueError
            voices_int_for_sticky = voices
        except ValueError:
            error = "Number of voices must be an integer between 4 and 6."
            voices_int_for_sticky = None
        else:
            weights: HarmonyWeights | None = None
            midi_bpm_override = None
            if midi_bpm_form:
                try:
                    bpm_val = int(float(midi_bpm_form))
                except ValueError:
                    error = "BPM must be a number, or leave blank for the pattern default."
                else:
                    if not (20 <= bpm_val <= 400):
                        error = "BPM must be between 20 and 400."
                    else:
                        midi_bpm_override = bpm_val
            if not error:
                if post_weight_errs:
                    error = "Weights: " + " · ".join(post_weight_errs)
                else:
                    weights = post_weights
            if not error and not progression_text:
                error = "Please enter at least one chord."
            if not error and progression_text and weights is not None:
                try:
                    chords = parse_progression(progression_text)
                except ValueError as e:
                    error = f"Error parsing progression: {e}"
                    if raw_locked.strip():
                        try:
                            json.loads(raw_locked)
                        except json.JSONDecodeError:
                            lock_warnings.append(
                                "Lock data was not valid JSON; locks were cleared."
                            )
                            locked_voicings_json = "{}"
                else:
                    locked_backend, locked_form, lock_warnings = _parse_locked_voicings(
                        raw_locked, voices, len(chords)
                    )
                    locked_voicings_json = json.dumps(locked_form) if locked_form else "{}"
                    locked_chord_indices = (
                        set(int(k) for k in locked_form) if locked_form else set()
                    )
                    try:
                        result = generate_harmony(
                            chords,
                            num_voices=voices,
                            weights=weights,
                            locked_voicings=locked_backend if locked_backend else None,
                        )
                    except ValueError as e:
                        msg = str(e)
                        if "Locked voicing" in msg:
                            error = (
                                f"{msg} Clear or re-apply locks so each locked chord has exactly "
                                f"{voices} notes, then try again."
                            )
                        else:
                            error = f"Error generating harmony: {e}"
                    except RuntimeError as e:
                        msg = str(e)
                        if "No voicings generated" in msg:
                            error = (
                                "Could not build voicings for at least one chord with the current "
                                "pitch range and spread. Try widening Range low / high (under Weights), "
                                "increasing max chord spread, or using a simpler chord symbol."
                            )
                        else:
                            error = f"Error generating harmony: {e}"
                    except Exception as e:  # pragma: no cover - defensive
                        error = f"Error generating harmony: {e}"
                    else:
                        note_names_by_voice = result.as_note_names()
                        midi_export_error = None
                        try:
                            export_harmony_to_midi(
                                result,
                                filename=MIDI_OUTPUT_PATH,
                                mode=midi_mode,
                                pattern=midi_pattern,
                                bpm=midi_bpm_override,
                            )
                            midi_available = True
                        except ImportError as exc:
                            midi_available = False
                            logger.warning("MIDI export skipped (music21 missing): %s", exc)
                            midi_export_error = (
                                "Could not export MIDI: music21 is not installed. "
                                "Install dependencies from requirements.txt."
                            )
                        except Exception as exc:
                            midi_available = False
                            logger.exception("MIDI export failed")
                            midi_export_error = f"MIDI export failed: {exc}"

                        (
                            chord_voicings,
                            chord_voicings_json_list,
                            alternatives_per_chord,
                        ) = _compute_result_extras(chords, voices, weights, result)
                        sess_ok, disk_ok, _saved_ts = _persist_sticky_snapshot(
                            progression_text,
                            voices,
                            result,
                            weights,
                            midi_available,
                            midi_mode,
                            midi_pattern,
                            midi_bpm_form,
                            midi_export_error,
                            alternatives_per_chord,
                            locked_form,
                        )
                        if not sess_ok:
                            if disk_ok:
                                flash(
                                    "Could not save a browser-cookie backup (progression may be very long). "
                                    "A server-side backup file was saved—you can still recover the last table after errors.",
                                    "warning",
                                )
                            else:
                                flash(
                                    "Could not save browser or file backup of this result. "
                                    "If a later submit fails, the previous table may not reappear.",
                                    "warning",
                                )
                        return redirect(url_for("index"))

    form_weights_for_sticky = (
        post_weights if request.method == "POST" and not post_weight_errs else None
    )

    if error:
        sticky, sticky_unusable = _try_restore_sticky(
            error,
            voices_int_for_sticky,
            progression_text,
            midi_mode,
            midi_pattern,
            midi_bpm_form,
            form_weights_for_sticky,
        )
        if sticky_unusable:
            flash(
                "Saved harmony could not be restored (invalid or incomplete backup data). "
                "It was cleared—generate again to rebuild.",
                "warning",
            )
        if sticky:
            result = sticky["result"]
            note_names_by_voice = sticky["note_names_by_voice"]
            chord_voicings = sticky["chord_voicings"]
            chord_voicings_json_list = sticky["chord_voicings_json_list"]
            alternatives_per_chord = sticky["alternatives_per_chord"]
            midi_available = sticky["midi_available"]
            midi_export_error = sticky.get("midi_export_error")
            sticky_notices = sticky["sticky_notices"]
            if not progressions_equivalent_for_ui(
                progression_text, sticky.get("sticky_saved_progression", "")
            ):
                locked_voicings_json = "{}"
                locked_chord_indices = set()
                lock_warnings.append(
                    "Locks were cleared because your progression does not match the harmony "
                    "shown below as parsed by the app (some spellings look similar but are different chords)."
                )

    ux_warnings = list(lock_warnings)

    midi_available, midi_export_error = _reconcile_midi_with_file(
        midi_available, midi_export_error
    )

    pitch_min, pitch_max = _piano_roll_bounds(result) if result else (48, 72)
    result_num_voices = len(result.voices) if result else 0
    piano_roll_num_pitches = (pitch_max - pitch_min + 1) if result else 25
    weights_defaults_form = _weights_to_form(default_weights())

    return render_template(
        "index.html",
        error=error,
        result=result,
        note_names_by_voice=note_names_by_voice,
        result_step_count=len(result.chords) if result else 0,
        result_num_voices=result_num_voices,
        pitch_min=pitch_min,
        pitch_max=pitch_max,
        piano_roll_num_pitches=piano_roll_num_pitches,
        midi_mode=midi_mode,
        midi_pattern=midi_pattern,
        midi_bpm_form=midi_bpm_form,
        midi_export_error=midi_export_error,
        voices=voices,
        voices_display=voices_display,
        progression=progression_text,
        midi_available=midi_available,
        weights_form=weights_form,
        weights_defaults=weights_defaults_form,
        chord_voicings=chord_voicings,
        chord_voicings_json_list=chord_voicings_json_list,
        alternatives_per_chord=alternatives_per_chord,
        locked_voicings_json=locked_voicings_json,
        locked_chord_indices=locked_chord_indices,
        sticky_notices=sticky_notices,
        ux_warnings=ux_warnings,
        whatif_disabled=bool(result and len(result.chords) > WHATIF_MAX_CHORDS),
        whatif_max_chords=WHATIF_MAX_CHORDS,
        max_progression_chars=MAX_PROGRESSION_INPUT_CHARS,
        max_progression_chords=MAX_PROGRESSION_CHORDS,
        enumerate=enumerate,
        range=range,
    )


@app.route("/download-midi")
def download_midi():
    path = MIDI_OUTPUT_PATH
    if not os.path.isfile(path):
        flash(
            "No MIDI file is available yet. Generate harmony successfully first (with music21 installed).",
            "error",
        )
        return redirect(url_for("index"))
    try:
        return send_file(path, as_attachment=True, download_name=MIDI_FILENAME)
    except Exception as exc:
        logger.exception("download-midi failed")
        flash(f"Could not download MIDI: {exc}", "error")
        return redirect(url_for("index"))


if __name__ == "__main__":
    # Run the app in debug mode for development; you can change host/port here.
    app.run(debug=True, port=5001)

