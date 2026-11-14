"""
Full Song Cover Orchestration
Builds a multi-instrument MIDI arrangement from the piano cover, adding:
- Piano (already in original MIDI)
- String section (strings ensemble)
- Electric bass
- Ambient pads
- Acoustic guitar (strumming)
- Drums (light, for rhythmic foundation)

Uses pyfluidsynth + FluidR3_GM SoundFont for high-quality rendering.
"""

import os
import sys
import struct
import numpy as np

# Set up FluidSynth native library path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WORKSPACE_DIR = os.path.dirname(os.path.dirname(SCRIPT_DIR))
FLUIDSYNTH_BIN = os.path.join(WORKSPACE_DIR, "vendor", "fluidsynth-bin", "fluidsynth-v2.6.1-win10-x64-cpp11", "bin")
os.environ["PATH"] = FLUIDSYNTH_BIN + os.pathsep + os.environ.get("PATH", "")
os.environ["FLUIDSYNTH_LIB"] = os.path.join(FLUIDSYNTH_BIN, "libfluidsynth-3.dll")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from midiutil import MIDIFile

# File paths
midi_path = os.path.join(SCRIPT_DIR, "soudeni_aya_moghraman_cover.mid")
orchestrated_midi = os.path.join(SCRIPT_DIR, "soudeni_aya_moghraman_cover_orchestrated.mid")
full_production_wav = os.path.join(SCRIPT_DIR, "soudeni_aya_moghraman_cover_full_production.wav")
piano_only_wav = os.path.join(SCRIPT_DIR, "soudeni_aya_moghraman_piano_cover.wav")
soundfont = os.path.join(WORKSPACE_DIR, "assets", "soundfonts", "SoundFont.sf2")

# ============================================================
# ARRANGEMENT: Multi-instrument orchestration
# ============================================================
# GM Program numbers:
#   0  - Acoustic Grand Piano
#   24 - Nylon String Guitar
#   33 - Electric Bass (finger)
#   48 - String Ensemble 1
#   96 - Pad 1 (new age) -> use 89 (Pad 1) for GM compatibility
#
# Drums on Channel 10 (GM Standard Kit):
#   36 - Kick, 38 - Snare, 42 - Hi-Hat Closed, 49 - Crash

# Chord progressions
SECTION_CHORDS = {
    "Intro":       [("Am", 4), ("F", 4), ("G", 4), ("E7", 4)],
    "Hook":        [("Am", 4), ("F", 4), ("G", 4), ("E7", 4)],
    "Verse_2":     [("Am", 4), ("Dm", 4), ("E", 4),  ("Am", 4)],
    "Verse_3":     [("Am", 4), ("F", 4), ("G", 4), ("E", 4)],
    "Verse_4":     [("Dm", 4), ("Am", 4), ("E", 4),  ("Am", 4)],
    "Outro":       [("Am", 4), ("E/G#", 4), ("F", 4), ("G", 4), ("Am", 4)],
}

# Structure: section_name, bars, pattern_name
# Bars match the chord progression length (each chord = 4 beats = 1 bar)
STRUCTURE = [
    ("Intro",     4,  "arpeggio"),       # 4 chords
    ("Hook",      4,  "walking_bass"),   # 4 chords
    ("Verse_2",   4,  "oom_pah"),       # 4 chords
    ("Hook",      4,  "walking_bass"),   # 4 chords
    ("Verse_3",   4,  "oom_pah"),       # 4 chords
    ("Verse_4",   4,  "oom_pah"),       # 4 chords
    ("Hook",      4,  "walking_bass"),   # 4 chords
    ("Outro",     5,  "arpeggio"),       # 5 chords
]

CHORD_ROOTS = {
    "Am":  57, "F": 53, "G": 55, "E7": 64, "E": 64, "Dm": 62, "E/G#": 64,
}

CHORD_NOTES = {
    "Am":  [57, 60, 64],
    "F":   [53, 57, 60],
    "G":   [55, 59, 62],
    "E7":  [64, 68, 71, 74],
    "E":   [64, 68, 71],
    "Dm":  [62, 65, 69],
    "E/G#": [64, 68, 71],
}

# Drum notes
KICK, SNARE, HAT_CLOSED, HAT_OPEN, CRASH, TOM_LOW, TOM_MID, TOM_HIGH, RIDE = \
    36, 38, 42, 46, 49, 43, 45, 47, 51


def build_orchestrated_midi():
    """Create a multi-track MIDI with piano, strings, bass, guitar, pads, drums."""
    CH = {"piano": 0, "strings": 1, "bass": 2, "guitar": 3, "pad": 4, "drums": 5}
    
    midi = MIDIFile(len(CH))
    tempo = 72
    time = 0
    
    for t in range(len(CH)):
        midi.addTempo(t, time, tempo)
    
    # Setup programs
    midi.addTrackName(CH["piano"], time, "Piano")
    midi.addProgramChange(CH["piano"], 0, time, 0)  # Acoustic Grand Piano, channel 0
    
    midi.addTrackName(CH["strings"], time, "Strings")
    midi.addProgramChange(CH["strings"], 0, time, 48)  # String Ensemble 1
    
    midi.addTrackName(CH["bass"], time, "Bass")
    midi.addProgramChange(CH["bass"], 0, time, 33)  # Electric Bass (finger)
    
    midi.addTrackName(CH["guitar"], time, "Guitar")
    midi.addProgramChange(CH["guitar"], 0, time, 24)  # Nylon String Guitar
    
    midi.addTrackName(CH["pad"], time, "Pad")
    midi.addProgramChange(CH["pad"], 0, time, 89)  # Pad 1 (new age)
    
    midi.addTrackName(CH["drums"], time, "Drums")
    # Drums on channel 10 (index 9)
    
    # Calculate section start times
    section_times = []
    current_time = 0
    for sec_name, bars, pattern in STRUCTURE:
        start = current_time
        end = current_time + bars * 4  # bars * 4 beats
        section_times.append((sec_name, start, end, pattern))
        current_time = end
    
    for sec_name, start_time, end_time, pattern in section_times:
        chords = SECTION_CHORDS.get(sec_name, [])
        chord_time = start_time
        
        for chord, chord_beats in chords:
            notes = CHORD_NOTES.get(chord, [60])
            root = CHORD_ROOTS.get(chord, 60)
            fifth = root + 7
            
            if sec_name == "Intro":
                # Arpeggiated piano + ambient pad
                for i, note in enumerate(notes):
                    offset = chord_time + (chord_beats / len(notes)) * i
                    midi.addNote(CH["piano"], 0, note, offset, 0.25, 70)
                    midi.addNote(CH["piano"], 0, note + 12, offset + 0.5, 0.25, 65)
                
                # Strings sustained
                for note in notes:
                    midi.addNote(CH["strings"], 0, note + 12, chord_time, chord_beats, 50)
                
                # Ambient pad
                midi.addNote(CH["pad"], 0, root + 12, chord_time, chord_beats * 2, 35)
            
            elif sec_name == "Hook":
                # Walking bass + full strings + driving rhythm
                for note in notes:
                    midi.addNote(CH["strings"], 0, note + 12, chord_time, chord_beats, 60)
                
                # Bass walking pattern
                for i in range(int(chord_beats * 2)):
                    beat = chord_time + i * 0.5
                    if i % 4 == 0:
                        midi.addNote(CH["bass"], 0, root, beat, 0.4, 85)
                    elif i % 4 == 1:
                        midi.addNote(CH["bass"], 0, fifth, beat, 0.4, 75)
                    elif i % 4 == 2:
                        midi.addNote(CH["bass"], 0, root, beat, 0.4, 80)
                    else:
                        midi.addNote(CH["bass"], 0, root + 12, beat, 0.4, 70)
                
                # Guitar strumming
                for i in range(int(chord_beats * 4)):
                    beat = chord_time + i * 0.25
                    for note in notes:
                        midi.addNote(CH["guitar"], 0, note + 12, beat, 0.15, 55)
                
                # Piano chord stabs on 2 and 4
                for beat_offset in [1, 3]:
                    for note in notes:
                        midi.addNote(CH["piano"], 0, note, chord_time + beat_offset, 0.5, 60)
                
                # Drums
                for i in range(int(chord_beats * 4)):
                    beat = chord_time + i * 0.25
                    if i % 4 == 0 or i % 4 == 2:
                        midi.addNote(CH["drums"], 9, KICK, beat, 0.1, 90)
                    if i % 4 == 1 or i % 4 == 3:
                        midi.addNote(CH["drums"], 9, SNARE, beat, 0.1, 80)
                    midi.addNote(CH["drums"], 9, HAT_CLOSED, beat, 0.05, 55)
                    if i == 0:
                        midi.addNote(CH["drums"], 9, CRASH, beat, 0.5, 100)
            
            elif sec_name in ("Verse_2", "Verse_3", "Verse_4"):
                # Oom-pah pattern, intimate strings, gentle guitar
                for note in notes:
                    midi.addNote(CH["strings"], 0, note + 12, chord_time, chord_beats, 40)
                
                # Bass oom-pah
                for i in range(int(chord_beats)):
                    beat = chord_time + i
                    if i % 2 == 0:
                        midi.addNote(CH["bass"], 0, root, beat, 0.8, 75)
                    else:
                        midi.addNote(CH["bass"], 0, fifth, beat, 0.8, 65)
                
                # Guitar gentle strumming
                for i in range(int(chord_beats * 2)):
                    beat = chord_time + i * 0.5
                    for note in notes:
                        midi.addNote(CH["guitar"], 0, note + 12, beat, 0.2, 45)
                
                # Piano chord stabs on off-beats
                for i in range(int(chord_beats)):
                    if i % 2 == 1:
                        for note in notes:
                            midi.addNote(CH["piano"], 0, note, chord_time + i + 0.5, 0.3, 55)
                
                # Light drums on 2 and 4
                midi.addNote(CH["drums"], 9, SNARE, chord_time + 1, 0.2, 55)
                midi.addNote(CH["drums"], 9, SNARE, chord_time + 3, 0.2, 55)
                midi.addNote(CH["drums"], 9, HAT_CLOSED, chord_time + 0.5, 0.1, 35)
                midi.addNote(CH["drums"], 9, HAT_CLOSED, chord_time + 2.5, 0.1, 35)
            
            elif sec_name == "Outro":
                # Arpeggiated piano, strings fading
                for i, note in enumerate(notes):
                    offset = chord_time + (chord_beats / len(notes)) * i
                    midi.addNote(CH["piano"], 0, note, offset, 0.3, 65)
                    midi.addNote(CH["piano"], 0, note + 12, offset + 0.5, 0.3, 60)
                
                for note in notes:
                    midi.addNote(CH["strings"], 0, note + 12, chord_time, chord_beats, 50)
                
                midi.addNote(CH["pad"], 0, root + 12, chord_time, chord_beats * 2, 35)
            
            chord_time += chord_beats
    
    # Write MIDI
    with open(orchestrated_midi, "wb") as f:
        midi.writeFile(f)
    print(f"Orchestrated MIDI saved: {orchestrated_midi}")
    return orchestrated_midi


def render_fluidsynth(midi_file, output_wav, soundfont_path):
    """Render MIDI to audio using FluidSynth CLI."""
    import subprocess
    
    if not os.path.exists(soundfont_path):
        print(f"ERROR: SoundFont not found: {soundfont_path}")
        return False
    
    fluidsynth_exe = os.path.join(FLUIDSYNTH_BIN, "fluidsynth.exe")
    
    print(f"Loading SoundFont: {os.path.basename(soundfont_path)}")
    print(f"Loading MIDI: {os.path.basename(midi_file)}")
    
    # Use FluidSynth CLI to render
    sample_rate = 48000
    print(f"  Rendering at {sample_rate}Hz...")
    
    result = subprocess.run([
        fluidsynth_exe, "-n", "-i",  # -n: No audio (file output)
        "-g", "1.5",  # gain
        "-r", str(sample_rate),
        "-F", output_wav,
        "-O", "s16",
        soundfont_path,
        midi_file,
    ], capture_output=True, text=True, timeout=120)
    
    if result.returncode == 0 and os.path.exists(output_wav) and os.path.getsize(output_wav) > 44:
        file_size = os.path.getsize(output_wav)
        print(f"  WAV created: {output_wav}")
        print(f"  File size: {file_size / (1024*1024):.1f} MB")
        return True
    else:
        print(f"  Render output: {result.stdout}")
        print(f"  Render errors: {result.stderr}")
        return False


import wave

if __name__ == "__main__":
    print("=" * 60)
    print("  FULL PRODUCTION ORCHESTRATOR")
    print("  Soudeni - Aya Moghraman")
    print("=" * 60)
    print()
    
    # Step 1: Build orchestrated MIDI
    print("Step 1: Building multi-instrument MIDI...")
    build_orchestrated_midi()
    print()
    
    # Step 2: Render with FluidSynth
    print("Step 2: Rendering with FluidSynth + SoundFont...")
    try:
        if not render_fluidsynth(orchestrated_midi, full_production_wav, soundfont):
            sys.exit(1)
    except Exception as e:
        print(f"  Render error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    print()
    print("Done!")
