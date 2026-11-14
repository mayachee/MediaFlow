"""
Piano Cover Arrangement Generator for:
  Soudeni - Aya Moghraman (Soudani - أَيَا مُغْرمًن)

Generates a playable piano arrangement with chords, melody,
and left-hand accompaniment patterns based on Maqam Bayati.
Also generates a MIDI file for reference playback.

Usage: python soudeni_piano_cover.py
"""

import os
import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# ============================================================
# Song: Soudeni - Aya Moghraman (Soudani)
# Genre: Tunisian/Arabic Pop ("Harissa Pop")
# Duration: ~4:17 (YouTube)
# Maqam: Bayati (مقام بياتي) - most common maqam for emotional ballads
# ============================================================

# ============================================================
# CHORD PROGRESSIONS
# ============================================================
# Key: Am (A minor) - compatible with Maqam Bayati scale: A B C D E F G
# Tempo: 72 BPM, 4/4 time

# Each section maps to a portion of the lyrics:
# - Hook ("Aya Mughraman"): i - VI - VII - V7
# - Verse 2 ("Ahim bi-khamr al-gharam"): i - iv - V - i
# - Verse 3 ("Fatani jamal hubbi"): i - VI - VII - V
# - Verse 4 ("Alimtu ma fi al-misir"): iv - i - V - i
# - Outro ("Ya habib ar-ruh"): i - V/vi - VI - VII - i

SECTION_CHORDS = {
    "Intro":       [ ("Am", 4), ("F", 4), ("G", 4), ("E7", 4) ],
    "Hook":        [ ("Am", 4), ("F", 4), ("G", 4), ("E7", 4) ],
    "Verse_2":     [ ("Am", 4), ("Dm", 4), ("E", 4),  ("Am", 4) ],
    "Verse_3":     [ ("Am", 4), ("F", 4), ("G", 4), ("E", 4) ],
    "Verse_4":     [ ("Dm", 4), ("Am", 4), ("E", 4),  ("Am", 4) ],
    "Outro":       [ ("Am", 4), ("E/G#", 4), ("F", 4), ("G", 4), ("Am", 4) ],
}

SECTION_LYRICS = {
    "Hook": "أَيَا مُغْرمًا تَعلَّقَ قَلْبُكَ بِالهَوى بِالوِدَادِ...",
    "Verse_2": "أَهِيمُ بِخَمْرِ الغَرَامِ مُنادٍ عَزِيزًا خَفِيفَ الظِّلاَلِ...",
    "Verse_3": "فَتَنِّي جَمَالُ حُبِيبِ فُؤَادِي أَمِيرُ المَعَالِي...",
    "Verse_4": "عَلِمْتُ ما في المَصِيرِ، سَيْر القَدَر و قَبِلْتُ عَيْشَ الحَيَاةِ...",
    "Outro": "يَا حَبِيب الرُّوحْ مَاهُو فُمِّي قَلْبِي اللِّي يْبُوح...",
}

# ============================================================
# LEFT HAND ACCOMPANIMENT PATTERNS
# ============================================================
# Pattern 1: Arpeggio (Intro/Outro)
#   RH: | A-C-E-A | C-E-A-C | etc. (8th notes ascending/descending)
# Pattern 2: Oom-pah (Verses)  
#   LH bass: Root on beat 1, 5th on beat 2, Root on beat 3, 5th on beat 4
#   RH: Chord stab on beats 2 and 4
# Pattern 3: Walking bass (Hook/Chorus)
#   LH: Root-5th-Octave walking pattern on 8th notes
#   RH: Melody or chord stabs

LH_PATTERNS = {
    "arpeggio": {
        "description": "Broken chord arpeggio (8th notes)",
        "example": "Am: A-C-E-A-C-E-A-C | (octaves A5-A4 for upper voices)",
    },
    "oom_pah": {
        "description": "Bass note on 1&3, chord on 2&4",
        "example": "Beat:  1     2     3     4\nLH:   Root  Chord Root  Chord",
    },
    "walking_bass": {
        "description": "Walking bass line (8th notes)",
        "example": "Am: A(1) E(2) A(3) E(4) C(5) E(6) A(7) rest(8)",
    },
}

# ============================================================
# RIGHT HAND MELODY LINE (Maqam Bayati on A)
# ============================================================
# The vocal melody uses notes from A natural minor (approximates Maqam Bayati)
# Key melodic notes: A, B, C, D, E, F, G
# Characteristic intervals: minor 3rd (C), minor 6th (F), minor 7th (G)

# Melody mapped to the lyrics, note values are relative to 4/4 bar
# Each note: (pitch, duration_in_beats)

MELODY = {
    "Intro": [
        ("A4", 0.5), ("C5", 0.5), ("E5", 0.5), ("A5", 0.5),
        ("F4", 0.5), ("A4", 0.5), ("C5", 0.5), ("F5", 0.5),
        ("G4", 0.5), ("B4", 0.5), ("D5", 0.5), ("G5", 0.5),
        ("E5", 1.0), ("C5", 0.5), ("E5", 0.5), ("A4", 1.0),
    ],
    "Hook": [
        # أَيَا مُغْرمًا تَعلَّقَ قَلْبُكَ
        ("A4", 0.5), ("F4", 0.5), ("A4", 0.5), ("F4", 0.5),
        ("G4", 0.5), ("A4", 0.5), ("C5", 0.5), ("A4", 0.5),
        # بِالهَوى بِالوِدَادِ تَوَسَّمَ خَيْرًا
        ("F4", 0.5), ("A4", 0.5), ("G4", 0.5), ("A4", 0.5),
        ("F4", 0.5), ("E4", 0.5), ("A4", 1.0), ("-", 1.0),
        # لا يَزُولْ أَيَا مُغْرمًا قَدْ شَبَّ
        ("A4", 0.5), ("C5", 0.5), ("E5", 0.5), ("C5", 0.5),
        ("A4", 0.5), ("F4", 0.5), ("A4", 0.5), ("C5", 0.5),
        # ناظِرُكَ السَّماء آملًا نَيْلَ
        ("B4", 0.5), ("A4", 0.5), ("G4", 0.5), ("A4", 0.5),
        ("F4", 0.5), ("A4", 0.5), ("G4", 1.0), ("A4", 0.5),
        # الْمُنَى فَيَا عَبْدُ كُنْ صَبُورْ
        ("E4", 0.5), ("F4", 0.5), ("E4", 0.5), ("D4", 0.5),
        ("C4", 1.0), ("E4", 0.5), ("A3", 1.0), ("-", 1.0),
    ],
    "Verse_2": [
        # أَهِيمُ بِخَمْرِ الغَرَامِ مُنادٍ
        ("B4", 0.5), ("C5", 0.5), ("A4", 0.5), ("G4", 0.5),
        ("E4", 0.5), ("A4", 0.5), ("G4", 0.5), ("E4", 0.5),
        # عَزِيزًا خَفِيفَ الظِّلاَلِ أيادٍ
        ("D4", 0.5), ("E4", 0.5), ("F4", 0.5), ("G4", 0.5),
        ("A4", 0.5), ("B4", 0.5), ("C5", 0.5), ("B4", 0.5),
        # مُدَّت لِوُجْهي اسْتَنَارَ و صَارتْ
        ("A4", 0.5), ("G4", 0.5), ("A4", 0.5), ("C5", 0.5),
        ("E5", 0.5), ("C5", 0.5), ("A4", 0.5), ("G4", 0.5),
        # خَرِيفًا حَيَاتِي صَحْوٌ - مَطَرْ
        ("F4", 0.5), ("A4", 1.0), ("G4", 0.5), ("E4", 0.5),
        ("A4", 0.5), ("F4", 0.5), ("E4", 1.0), ("A4", 0.5),
    ],
    "Verse_3": [
        # فَتَنِّي جَمَالُ حُبِيبِ فُؤَادِي أَمِيرُ
        ("A4", 0.5), ("C5", 0.5), ("E5", 0.5), ("G5", 0.5),
        ("A5", 0.5), ("G5", 0.5), ("E5", 0.5), ("C5", 0.5),
        # المَعَالِي و مَالِك خَيَالي فَحُسْنُه
        ("A4", 0.5), ("F4", 0.5), ("A4", 0.5), ("C5", 0.5),
        ("E5", 0.5), ("C5", 0.5), ("A4", 0.5), ("F4", 0.5),
        # سَبَانِي فَقَدْتُ سُبَاتِي
        ("G4", 0.5), ("A4", 0.5), ("B4", 0.5), ("C5", 0.5),
        ("B4", 0.5), ("A4", 1.0), ("F4", 0.5), ("-", 0.5),
        # سَهِرْتُ اللَّيَالِي لِحَدِّ السَّحَرْ
        ("A4", 0.5), ("G4", 0.5), ("E4", 0.5), ("G4", 0.5),
        ("A4", 0.5), ("C5", 0.5), ("B4", 0.5), ("A4", 1.0),
    ],
    "Verse_4": [
        # عَلِمْتُ ما فِي المَصِيرِ، سَيْر القَدَر
        ("G4", 0.5), ("A4", 0.5), ("B4", 0.5), ("C5", 0.5),
        ("D5", 0.5), ("C5", 0.5), ("B4", 0.5), ("A4", 0.5),
        # وَ قَبِلْتُ عَيْشَ الْحَيَاةِ كَيْفَمَا كَانْ
        ("G4", 0.5), ("F4", 0.5), ("E4", 0.5), ("F4", 0.5),
        ("G4", 0.5), ("A4", 0.5), ("B4", 0.5), ("C5", 0.5),
        # الشَّوْقُ أقْـبَلَ فِي كِيَاني
        ("D5", 0.5), ("C5", 0.5), ("B4", 0.5), ("A4", 0.5),
        ("G4", 0.5), ("F4", 0.5), ("E4", 0.5), ("D4", 0.5),
        # اسْتَقَرَ رَجَوْتُ وَصْلَهُ، دَعَوْتُ
        ("C4", 0.5), ("D4", 0.5), ("E4", 0.5), ("F4", 0.5),
        ("G4", 1.0), ("A4", 0.5), ("B4", 0.5), ("C5", 0.5),
        # مَوْلاى الأَنَامْ
        ("B4", 0.5), ("A4", 0.5), ("G4", 0.5), ("A4", 1.0),
    ],
    "Outro": [
        # يَا حَبِيب الرُّوحْ مَاهُو
        ("A4", 0.5), ("G4", 0.5), ("A4", 0.5), ("C5", 0.5),
        ("E5", 0.5), ("C5", 0.5), ("A4", 0.5), ("G4", 0.5),
        # فُمِّي قَلْبِي الَّذِي يُبُوح
        ("E4", 0.5), ("A4", 0.5), ("C5", 0.5), ("E5", 0.5),
        ("G5", 0.5), ("E5", 0.5), ("C5", 0.5), ("A4", 0.5),
        # قَلْبِي الَّذِي يَهَابُوهْ
        ("F4", 0.5), ("A4", 0.5), ("C5", 0.5), ("E5", 0.5),
        ("D5", 0.5), ("C5", 0.5), ("A4", 0.5), ("G4", 0.5),
        # مِ الَّذِي شَافِك مَا عَادَ إرْتَاح
        ("E4", 0.5), ("G4", 0.5), ("A4", 1.0), ("-", 1.0),
        ("A4", 0.5), ("C5", 0.5), ("E5", 0.5), ("C5", 0.5),
        ("A4", 1.0), ("-", 1.0), ("-", 1.0), ("-", 1.0),
    ],
}


def print_chord_diagram(chord_name):
    """Print a simple ASCII chord diagram for piano."""
    diagrams = {
        "Am":   "x 0 0 2 1 0  (A-C-E-A-C-E)",
        "F":    "1 3 3 2 1 1  (F-A-C-F-A-C)",
        "G":    "3 2 0 0 0 3  (G-B-D-G-B-D)",
        "E7":   "0 2 0 1 0 0  (E-G#-B-D-E-G#-B)",
        "E":    "0 2 2 1 0 0  (E-G#-B-E-G#-B)",
        "Dm":   "x 0 0 2 1 1  (D-F-A-D-F-A)",
        "E/G#": "4 2 2 1 0 0  (E-G#-B-E-G#-B, bass on G#)",
    }
    return diagrams.get(chord_name, chord_name)


def generate_midi():
    """Generate a MIDI file with the piano arrangement."""
    try:
        from midiutil import MIDIFile
        
        track = 0
        time = 0
        tempo = 72
        volume_chords = 80
        volume_melody = 100
        
        midi = MIDIFile(3)  # 3 tracks: LH chords, LH bass, RH melody
        midi.addTempo(track, time, tempo)
        
        # Track 0: LH Chords
        chord_track = 0
        midi.addTrackName(chord_track, time, "LH Chords")
        time = 0
        bar = 0
        
        chord_to_notes = {
            "Am": [57, 60, 64],  # A3, C4, E4 (midi notes A=57, C=60, E=64)
            "F":  [53, 57, 60],   # F3, A3, C4
            "G":  [55, 59, 62],   # G3, B3, D4
            "E7": [64, 68, 71],   # E4, G#4, B4 (plus D5)
            "E":  [52, 56, 64],   # E3, G#3, B3
            "Dm": [62, 65, 69],   # D4, F4, A4
        }
        
        # Add chord progressions
        section_time = 0
        for section_name in ["Intro", "Hook", "Verse_2", "Hook", "Verse_3", "Verse_4", "Hook", "Outro"]:
            if section_name in SECTION_CHORDS:
                for chord, beats in SECTION_CHORDS[section_name]:
                    notes = chord_to_notes.get(chord, [60])
                    for n in notes:
                        midi.addNote(chord_track, 0, n, section_time, beats, volume_chords)
                    section_time += beats
        
        # Track 1: RH Melody
        melody_track = 1
        midi.addTrackName(melody_track, time, "RH Melody")
        
        note_to_midi = {
            'C3': 48, 'D3': 50, 'E3': 52, 'F3': 53, 'G3': 55, 'A3': 57, 'B3': 59,
            'C4': 60, 'D4': 62, 'E4': 64, 'F4': 65, 'G4': 67, 'A4': 69, 'B4': 71,
            'C5': 72, 'D5': 74, 'E5': 76, 'F5': 77, 'G5': 79, 'A5': 81, 'B5': 83,
        }
        
        # Calculate section start times for melody
        melody_time = 0
        section_bars = {
            "Intro": 4, "Hook": 8, "Verse_2": 8, "Verse_3": 8,
            "Verse_4": 8, "Outro": 10,
        }
        
        for section_name in ["Intro", "Hook", "Verse_2", "Hook", "Verse_3", "Verse_4", "Hook", "Outro"]:
            if section_name in MELODY:
                for pitch, duration in MELODY[section_name]:
                    if pitch != "-":
                        note = note_to_midi.get(pitch, 60)
                        midi.addNote(melody_track, 0, note, melody_time, duration, volume_melody)
                    melody_time += duration
        
        # Write to file
        output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 
                                    "soudeni_aya_moghraman_cover.mid")
        with open(output_path, "wb") as f:
            midi.writeFile(f)
        print(f"MIDI file saved to: {output_path}")
        return True
        
    except ImportError:
        print("midiutil not installed - skipping MIDI generation")
        return False
    except Exception as e:
        print(f"MIDI error: {e}")
        return False


def print_cover_sheet():
    """Print the complete piano cover arrangement."""
    print("=" * 70)
    print("  PIANO COVER: Soudeni - Aya Moghraman (Soudani)")
    print("  Key: Am (A minor) | Tempo: 72 BPM | 4/4")
    print("=" * 70)
    print()
    
    print("--- SONG STRUCTURE ---")
    print()
    structure = [
        ("Intro",     4,  "Instrumental - establish maqam",            "arpeggio LH"),
        ("Hook 1",    8,  "أَيَا مُغْرمًا... تَوَسَّمَ خَيْرًا",          "walking bass + melody"),
        ("Verse 2",   8,  "أَهِيمُ بِخَمْرِ الغَرَامِ...",              "oom-pah + melody"),
        ("Hook 2",    8,  "أَيَا مُغْرمًا... (repeat)",                 "walking bass + melody"),
        ("Verse 3",   8,  "فَتَنِّي جَمَالُ حُبِيبِ فُؤَادِي...",        "oom-pah + melody"),
        ("Verse 4",   8,  "عَلِمْتُ ما في المَصِيرِ...",              "oom-pah + melody"),
        ("Hook 3",    8,  "أَيَا مُغْرمًا... (repeat)",                 "walking bass + melody"),
        ("Outro",    10,  "يَا حَبِيب الرُّوحْ...",                     "arpeggio LH + descending melody"),
    ]
    
    print(f"{'Section':12s} {'Bars':>4s}  {'Lyrics (Arabic)':35s}  {'LH Pattern':>20s}")
    print("-" * 82)
    total_bars = 0
    for sec, bars, lyrics, pattern in structure:
        print(f"{sec:12s} {bars:4d}  {lyrics:35s}  {pattern:>20s}")
        total_bars += bars
    print("-" * 82)
    print(f"{'TOTAL':12s} {total_bars:4d}")
    print()
    
    print("--- CHORD PROGRESSIONS ---")
    print()
    for sec_name, chords_list in SECTION_CHORDS.items():
        chord_str = " | ".join([f"{c} ({b} bars)" for c, b in chords_list])
        roman = ""
        if sec_name in ("Intro", "Hook"):
            roman = "i - VI - VII - V7"
        elif sec_name == "Verse_2":
            roman = "i - iv - V - i"
        elif sec_name == "Verse_3":
            roman = "i - VI - VII - V"
        elif sec_name == "Verse_4":
            roman = "iv - i - V - i"
        elif sec_name == "Outro":
            roman = "i - V/vi - VI - VII - i"
        print(f"  [{sec_name:8s}] {chord_str}")
        print(f"             Roman: {roman}")
        print(f"             Piano: {', '.join([print_chord_diagram(c) for c, _ in chords_list])}")
        print()
    
    print("--- LEFT HAND PATTERNS ---")
    print()
    for name, info in LH_PATTERNS.items():
        print(f"  {name}:")
        print(f"    {info['description']}")
        print(f"    Example: {info['example']}")
        print()
    
    print("--- RIGHT HAND MELODY ---")
    print()
    print("  Scale: A natural minor (Maqam Bayati approximation)")
    print("  Notes: A - B - C - D - E - F - G - A")
    print("  Characteristic intervals:")
    print("    Minor 3rd (C) - melancholic, core of maqam")
    print("    Minor 6th (F) - maqam Bayati signature")
    print("    Minor 7th (G) - completes the character")
    print()
    print("  Hook Motif: A-F-A-F-G-A-C-A-F-A (descent then rise on 'mukraman')")
    print("  Verse Motif: B-C-A-G-E-A-G-E (walking tension and release)")
    print("  Outro Motif: A-G-A-C-E-C-A-G (intimate, narrow range)")
    print()
    
    print("--- PLAYING TIPS ---")
    print()
    print("  1. Use pedal (sustain) on chord changes for smooth flow")
    print("  2. Emphasize beat 1 in verses (oom-pah pattern)")
    print("  3. In the hook, use dynamic contrast (softer verses, brighter chorus)")
    print("  4. Add grace notes (C->D->E) for Arabic ornamentation flavor")
    print("  5. Use rubato (flexible tempo) in the outro for emotional expression")
    print("  6. For authentic maqam feel, slide between notes where possible")
    print()

    print("--- FULL MELODY WITH CHORDS ---")
    print()
    for section_name in ["Intro", "Hook", "Verse_2", "Hook", "Verse_3", "Verse_4", "Hook", "Outro"]:
        if section_name in MELODY:
            # Get corresponding chord
            if section_name in SECTION_CHORDS:
                chord_str = " | ".join([f"{c}" for c, _ in SECTION_CHORDS[section_name]])
            else:
                chord_str = ""
            print(f"  [{section_name}] Chords: {chord_str}")
            if section_name in SECTION_LYRICS:
                print(f"  Arabic: {SECTION_LYRICS[section_name]}")
            line = "  Melody: "
            for pitch, dur in MELODY[section_name]:
                if pitch != "-":
                    line += f"{pitch}({dur:g}) "
                else:
                    line += f"rest({dur:g}) "
            print(line)
            print()


if __name__ == "__main__":
    print_cover_sheet()
    generate_midi()
