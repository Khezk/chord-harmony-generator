from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict
from flask import Flask, flash, request, redirect, url_for, render_template, send_file, session

from harmony import (
    HarmonyResult,
    HarmonyWeights,
    parse_progression,
    generate_harmony,
    default_weights,
    parse_weights_from_form,
    weights_form_snapshot,
    get_chord_alternatives,
    midi_to_name,
)
from midi_handler import export_harmony_to_midi  # type: ignore
from lock_parsing import parse_locked_voicings as _parse_locked_voicings

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-insecure-change-for-public-deployment")
logger = logging.getLogger(__name__)

SESSION_STICKY_KEY = "harmony_sticky_v1"
MIDI_FILENAME = "output.mid"


def _piano_roll_bounds(result):
    """Return (pitch_min, pitch_max) for the result's full pitch range."""
    if not result or not result.voices:
        return 48, 72
    all_pitches = [n for v in result.voices for n in v]
    return min(all_pitches), max(all_pitches)


# Register filter so template can show note names from MIDI numbers
@app.template_filter("midi_to_name")
def _midi_to_name_filter(midi_num):
    return midi_to_name(int(midi_num)) if midi_num is not None else ""


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
    }


def _compute_result_extras(
    chords,
    voices: int,
    weights: HarmonyWeights,
    result: HarmonyResult,
):
    """Build chord_voicings, JSON list, and alternatives for template."""
    n = len(result.voices)
    num_chords = len(result.chords)
    path_voicings = [
        tuple(result.voices[n - 1 - v][t] for v in range(n)) for t in range(num_chords)
    ]
    chord_voicings = [list(p) for p in path_voicings]
    alternatives_per_chord = []
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
    chord_voicings_json_list = [json.dumps(cv) for cv in chord_voicings]
    return chord_voicings, chord_voicings_json_list, alternatives_per_chord


def _save_sticky_session(
    progression_text: str,
    voices: int,
    result: HarmonyResult,
    weights: HarmonyWeights,
    midi_available: bool,
    midi_mode: str,
    midi_pattern: str,
    midi_bpm_form: str,
) -> None:
    try:
        session[SESSION_STICKY_KEY] = {
            "progression": progression_text,
            "num_voices": voices,
            "voices_midi": result.voices,
            "weights": asdict(weights),
            "midi_available": midi_available,
            "midi_mode": midi_mode,
            "midi_pattern": midi_pattern,
            "midi_bpm_form": midi_bpm_form or "",
        }
    except Exception as exc:  # pragma: no cover - cookie size etc.
        logger.warning("Could not store session snapshot of last result: %s", exc)
        session.pop(SESSION_STICKY_KEY, None)


def _try_restore_sticky(
    error: str | None,
    form_voices_int: int | None,
) -> dict | None:
    """
    If there is an error and a prior successful result in session, return kwargs
    to repopulate result UI; else None.
    """
    if not error:
        return None
    raw = session.get(SESSION_STICKY_KEY)
    if not raw or not isinstance(raw, dict):
        return None
    try:
        w = HarmonyWeights(**raw["weights"])
        chords = parse_progression(raw["progression"])
        result = HarmonyResult(chords=chords, voices=raw["voices_midi"])
    except Exception as exc:
        logger.warning("Discarding invalid sticky session: %s", exc)
        session.pop(SESSION_STICKY_KEY, None)
        return None

    nv = raw["num_voices"]
    if len(result.voices) != nv:
        session.pop(SESSION_STICKY_KEY, None)
        return None
    n_steps = len(chords)
    if n_steps == 0 or any(len(row) != n_steps for row in result.voices):
        session.pop(SESSION_STICKY_KEY, None)
        return None

    chord_voicings, chord_voicings_json_list, alternatives_per_chord = _compute_result_extras(
        chords, nv, w, result
    )
    parts = []
    if form_voices_int is not None and form_voices_int != nv:
        parts.append(
            f"The table below is your last successful result ({nv} voices). "
            f"The form currently requests {form_voices_int} voices."
        )
    parts.append(
        "Fix the error above and click Generate again to recalculate. "
        "MIDI download still refers to the file from your last successful export, if any."
    )
    banner = " ".join(parts)
    return {
        "result": result,
        "note_names_by_voice": result.as_note_names(),
        "chord_voicings": chord_voicings,
        "chord_voicings_json_list": chord_voicings_json_list,
        "alternatives_per_chord": alternatives_per_chord,
        "midi_available": bool(raw.get("midi_available")),
        "sticky_notice": banner,
    }


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
    sticky_notice = None

    if request.method == "POST":
        progression_text = request.form.get("progression", "").strip()
        voices_raw = request.form.get("voices", "").strip() or "4"
        voices_display = voices_raw
        midi_mode = request.form.get("midi_mode", "").strip() or "woodwind"
        midi_pattern = request.form.get("midi_pattern", "").strip() or "default"
        midi_bpm_form = request.form.get("midi_bpm", "").strip()
        weights_form = weights_form_snapshot(request.form)
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
                parsed, w_errs = parse_weights_from_form(request.form)
                if w_errs:
                    error = "Weights: " + " · ".join(w_errs)
                else:
                    weights = parsed
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
                                "pitch range and spread. Try widening **Range low / high** "
                                "(under Weights), increasing **max chord spread**, or using a "
                                "simpler chord symbol."
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
                                filename=MIDI_FILENAME,
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
                        _save_sticky_session(
                            progression_text,
                            voices,
                            result,
                            weights,
                            midi_available,
                            midi_mode,
                            midi_pattern,
                            midi_bpm_form,
                        )

    if error:
        sticky = _try_restore_sticky(error, voices_int_for_sticky)
        if sticky:
            result = sticky["result"]
            note_names_by_voice = sticky["note_names_by_voice"]
            chord_voicings = sticky["chord_voicings"]
            chord_voicings_json_list = sticky["chord_voicings_json_list"]
            alternatives_per_chord = sticky["alternatives_per_chord"]
            midi_available = sticky["midi_available"]
            sticky_notice = sticky["sticky_notice"]

    ux_warnings = list(lock_warnings)

    pitch_min, pitch_max = _piano_roll_bounds(result) if result else (48, 72)
    result_num_voices = len(result.voices) if result else 0
    piano_roll_num_pitches = (pitch_max - pitch_min + 1) if result else 25

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
        chord_voicings=chord_voicings,
        chord_voicings_json_list=chord_voicings_json_list,
        alternatives_per_chord=alternatives_per_chord,
        locked_voicings_json=locked_voicings_json,
        locked_chord_indices=locked_chord_indices,
        sticky_notice=sticky_notice,
        ux_warnings=ux_warnings,
        enumerate=enumerate,
        range=range,
    )


@app.route("/download-midi")
def download_midi():
    path = os.path.join(os.getcwd(), MIDI_FILENAME)
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

