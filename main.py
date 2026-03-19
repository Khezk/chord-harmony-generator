from __future__ import annotations

from harmony import parse_progression, generate_harmony, export_to_midi


def main() -> None:
    print("=== Chord Harmony Generator ===")
    print("This tool generates multi-part harmony for a chord progression.\n")

    while True:
        try:
            num_voices_str = input("Number of voices (>=4, <=6, default 4): ").strip()
        except EOFError:
            return

        if not num_voices_str:
            num_voices = 4
            break
        try:
            num_voices = int(num_voices_str)
            if 4 <= num_voices <= 6:
                break
            print("Please enter an integer between 4 and 6.")
        except ValueError:
            print("Please enter a valid integer.")

    print(
        "\nEnter chord progression (examples):\n"
        "  Cmaj | Fmaj | G7 | Cmaj\n"
        "  Am Dm G C\n"
        "Chord tokens can be separated by spaces, '|' or commas.\n"
    )

    while True:
        try:
            progression_text = input("Chord progression: ").strip()
        except EOFError:
            return
        if progression_text:
            break
        print("Please enter at least one chord.")

    try:
        chords = parse_progression(progression_text)
    except ValueError as e:
        print(f"Error parsing progression: {e}")
        return

    print("\nGenerating harmony...")
    try:
        result = generate_harmony(chords, num_voices=num_voices)
    except Exception as e:
        print(f"Error generating harmony: {e}")
        return

    note_names_by_voice = result.as_note_names()

    print("\n=== Harmony Result ===")
    print("Chords:")
    print("  " + " | ".join(ch.symbol for ch in result.chords))
    print("\nVoices (highest to lowest):")
    for idx, voice_notes in enumerate(note_names_by_voice):
        print(f"Voice {idx + 1}: " + ", ".join(voice_notes))

    # Try MIDI export
    save = input("\nWrite MIDI file 'output.mid'? [Y/n]: ").strip().lower()
    if save in ("", "y", "yes"):
        try:
            export_to_midi(result, filename="output.mid")
            print("Wrote MIDI file: output.mid")
        except ImportError:
            print("music21 is not installed; cannot export MIDI.")
            print("Install with: pip install -r requirements.txt")
        except Exception as e:
            print(f"Failed to write MIDI: {e}")


if __name__ == "__main__":
    main()

