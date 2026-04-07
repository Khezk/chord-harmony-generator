"""Parse and validate locked-voicing JSON from the web form (no Flask dependency)."""

from __future__ import annotations

import json
from typing import Dict, List, Tuple


def parse_locked_voicings(
    form_value: str,
    num_voices: int,
    num_chords: int,
) -> Tuple[Dict[int, List[int]], Dict[str, List[int]], List[str]]:
    """
    Parse locked_voicings JSON. Filters entries that do not match num_voices or chord index.
    Returns (locked_backend, locked_form, warnings).
    """
    warnings: List[str] = []
    if not form_value or not form_value.strip():
        return {}, {}, warnings
    try:
        raw = json.loads(form_value)
    except json.JSONDecodeError:
        warnings.append(
            "Lock data was not valid JSON; all locks were cleared. Try locking chords again."
        )
        return {}, {}, warnings
    if not isinstance(raw, dict):
        warnings.append("Lock data had an unexpected shape; locks were cleared.")
        return {}, {}, warnings

    locked_backend: Dict[int, List[int]] = {}
    locked_form: Dict[str, List[int]] = {}
    dropped_voice = 0
    dropped_index = 0
    dropped_bad_type = 0

    for k, v in raw.items():
        try:
            idx = int(k)
        except (ValueError, TypeError):
            continue
        if not isinstance(v, list) or not v or not all(isinstance(x, int) for x in v):
            dropped_bad_type += 1
            continue
        if len(v) != num_voices:
            dropped_voice += 1
            continue
        if idx < 0 or idx >= num_chords:
            dropped_index += 1
            continue
        locked_backend[idx] = v
        locked_form[str(k)] = v

    if dropped_voice:
        warnings.append(
            f"Removed {dropped_voice} lock(s) that do not match the current voice count ({num_voices})."
        )
    if dropped_index:
        warnings.append(
            f"Removed {dropped_index} lock(s) that are out of range for this progression length."
        )
    if dropped_bad_type:
        warnings.append(
            f"Skipped {dropped_bad_type} invalid lock entr(y/ies) (expected a list of MIDI note numbers)."
        )
    return locked_backend, locked_form, warnings
