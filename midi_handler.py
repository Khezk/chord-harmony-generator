from __future__ import annotations

from typing import Literal

from harmony import HarmonyResult


MidiMode = Literal["woodwind", "rnb", "piano"]


def export_harmony_to_midi(
    result: HarmonyResult,
    filename: str = "output.mid",
    mode: MidiMode = "woodwind",
    pattern: str = "default",
) -> None:
    """
    High-level MIDI exporter that can be reused by other programs.

    Modes:
      - \"woodwind\": one part per voice, woodwind instruments (original behaviour)
      - \"rnb\": bass + guitar (+ simple drums) groove
      - \"piano\": single piano part with simple voicing patterns
    """
    if mode == "rnb":
        _export_rnb_band(result, filename, pattern=pattern)
    elif mode == "piano":
        _export_piano(result, filename, pattern=pattern)
    else:
        _export_woodwind(result, filename)


def _base_score():
    from music21 import stream, tempo  # type: ignore

    s = stream.Score()
    s.append(tempo.MetronomeMark(number=80))
    return s


def _export_woodwind(result: HarmonyResult, filename: str) -> None:
    from music21 import stream, note, chord, instrument  # type: ignore

    s = _base_score()
    num_voices = len(result.voices)

    woodwinds = [
        instrument.Flute(),
        instrument.Oboe(),
        instrument.Clarinet(),
        instrument.Bassoon(),
        instrument.AltoSaxophone(),
        instrument.BassClarinet(),
    ]

    parts = []
    for i in range(num_voices):
        part = stream.Part(id=f"Voice {i + 1}")
        inst = woodwinds[i % len(woodwinds)]
        part.insert(0, inst)
        parts.append(part)

    # One chord per bar (4 quarter notes in 4/4), voices are highest -> lowest
    quarter_length = 4.0
    for v_idx, voice in enumerate(result.voices):
        p = parts[v_idx]
        for midi_pitch in voice:
            n = note.Note(midi_pitch, quarterLength=quarter_length)
            p.append(n)
        s.append(p)

    chord_part = stream.Part(id="Chords")
    for ch in result.chords:
        c = chord.Chord([p + 60 for p in ch.pitches])
        c.quarterLength = quarter_length
        c.addLyric(ch.symbol)
        chord_part.append(c)
    s.append(chord_part)

    s.write("midi", fp=filename)


def _export_rnb_band(result: HarmonyResult, filename: str, pattern: str = "straight") -> None:
    from music21 import stream, note, instrument, meter  # type: ignore

    s = _base_score()
    s.append(meter.TimeSignature("4/4"))

    num_voices = len(result.voices)
    num_chords = len(result.chords)

    # voices[v][t]: v = 0 (highest) ... n-1 (lowest)
    n = num_voices

    # Bass part: lowest voice
    bass_part = stream.Part(id="Bass")
    bass_part.insert(0, instrument.ElectricBass())

    # Guitar part: remaining voices combined
    guitar_part = stream.Part(id="Guitar")
    guitar_part.insert(0, instrument.ElectricGuitar())

    # Simple drum part (kick, snare, hihat on GM percussion pitches)
    drum_part = stream.Part(id="Drums")
    drum_part.insert(0, instrument.Woodblock())  # placeholder timbre

    bar_len = 4.0

    for t in range(num_chords):
        offset_bar = t * bar_len
        # collect chord voicing at step t from all voices (highest -> lowest)
        chord_pitches = [result.voices[v][t] for v in range(n)]
        bass_pitch = chord_pitches[-1]
        upper_pitches = chord_pitches[:-1] if n > 1 else [bass_pitch]

        if pattern == "syncopated":
            # Slightly funkier: bass on 1 & \"and\" of 2; guitar on 1,2-and,4
            # Bass: beats 1 and \"&\" of 2
            for off in (0.0, 1.5):
                bass_part.insert(offset_bar + off, note.Note(bass_pitch, quarterLength=0.5))
            # Guitar: short stabs on 1, 2.5, and 3.5
            for off in (0.0, 1.5, 2.5):
                for p in upper_pitches:
                    guitar_part.insert(offset_bar + off, note.Note(p, quarterLength=0.5))
        else:
            # straight: bass quarters on each beat, guitar half-notes on 1 & 3
            for beat in range(4):
                bass_part.insert(offset_bar + beat, note.Note(bass_pitch, quarterLength=1.0))
            for off in (0.0, 2.0):
                for p in upper_pitches:
                    guitar_part.insert(offset_bar + off, note.Note(p, quarterLength=2.0))

        # Very simple drum pattern: kick on 1 & 3, snare on 2 & 4, hihat 8ths
        # Using MIDI pitches 35 (kick), 38 (snare), 42 (hihat)
        for beat in (0.0, 2.0):
            drum_part.insert(offset_bar + beat, note.Note(35, quarterLength=1.0))
        for beat in (1.0, 3.0):
            drum_part.insert(offset_bar + beat, note.Note(38, quarterLength=1.0))
        # hihat 8ths
        hh_time = 0.0
        while hh_time < bar_len:
            drum_part.insert(offset_bar + hh_time, note.Note(42, quarterLength=0.5))
            hh_time += 0.5

    s.append(bass_part)
    s.append(guitar_part)
    s.append(drum_part)
    s.write("midi", fp=filename)


def _export_piano(result: HarmonyResult, filename: str, pattern: str = "split") -> None:
    from music21 import stream, note, instrument, meter, chord as m21chord  # type: ignore

    s = _base_score()
    s.append(meter.TimeSignature("4/4"))

    num_voices = len(result.voices)
    num_chords = len(result.chords)
    n = num_voices

    piano = stream.Part(id="Piano")
    piano.insert(0, instrument.Piano())

    bar_len = 4.0

    for t in range(num_chords):
        offset_bar = t * bar_len
        chord_pitches = [result.voices[v][t] for v in range(n)]
        top = chord_pitches[0]
        bottom = chord_pitches[-1]
        inner = chord_pitches[1:-1] if n > 2 else []

        if pattern == "block":
            # Simple block chord on beat 1, sustain whole bar
            c = m21chord.Chord(chord_pitches, quarterLength=bar_len)
            piano.insert(offset_bar, c)
        else:
            # Default \"split\" pattern:
            # - Beat 1: highest + lowest, sustain whole bar
            # - Beat 2: inner voices enter and sustain until end of bar
            piano.insert(offset_bar, note.Note(top, quarterLength=bar_len))
            if n > 1:
                piano.insert(offset_bar, note.Note(bottom, quarterLength=bar_len))
            if inner:
                for p in inner:
                    piano.insert(offset_bar + 1.0, note.Note(p, quarterLength=bar_len - 1.0))

    s.append(piano)
    s.write("midi", fp=filename)

