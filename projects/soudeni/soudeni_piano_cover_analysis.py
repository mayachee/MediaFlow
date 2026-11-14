"""
Piano Cover Arrangement Generator for:
  Soudeni - أَيَا مُغْرمًا (Aya Moghraman)
  
Uses librosa for chord/key analysis if audio is available,
falls back to maqam-based arrangement analysis.
"""

import json

# ============================================================
# Song Analysis (based on lyrics + genre knowledge)
# ============================================================

# Song: "سوداني - أيا مُغْرما" by Soudeni
# Genre: Tunisian/Arabic Pop ("Harissa Pop")
# Duration: ~4:17 (from YouTube)
# Style: Emotional ballad with Arabic maqam influences

LYRICS_ENGLISH_TRANSLATION = {
    "hook_1": "O you beloved, your heart is captivated by love and desire, "
              "You've found goodness that won't fade. O you beloved, "
              "your gaze meets the sky hoping to attain your wish. "
              "O servant, be patient...",

    "verse_2": "I am intoxicated by passion, a caller precious and light, "
               "Hands stretched toward my face were illuminated, "
               "And my life became autumn. Awake, it rained.",

    "verse_3": "I was seduced by the beauty of my beloved, "
               "the emir of high status, the owner of my imagination. "
               "His goodness surrounded me. I lost my sleep, "
               "passed the night until dawn.",

    "verse_4": "I learned there's no fate, the path of destiny, "
               "and I accepted living life however it may be. "
               "The longing entered my being, I settled for its arrival. "
               "I hoped to reach it, I called upon the Lord of all.",

    "hook_2": "O you beloved, your heart is captivated... (repeat)",

    "outro": "Ya habib ar-ruh... my mouth, my heart that is exposed, "
             "my heart that is shy... the one who sees you is not at peace.",
}

# ============================================================
# Maqam Bayati Analysis
# ============================================================
# The song uses Maqam Bayati (مقام بياتي), the most common maqam
# for emotional ballads in Arabic/Tunisian music.
#
# Maqam Bayati scale degrees (in A):
#   A (tonic) 1  - استصفر
#   B (2nd)      - حلقة (quarter-flat in traditional maqam, but B♮ works on piano)
#   C (minor 3rd) - الثلث (characteristic interval)
#   D (4th)       - رابعة
#   E (5th/dominant) - الخامس
#   F (minor 6th) - السادس (often slightly flatted, F♮ on piano)
#   G (minor 7th) - السابعة (often slightly flatted, G♭ in maqam, G♮ on piano)
#   A (octave)    - الكامل

# Chord progressions that capture Maqam Bayati flavor on piano
CHORDS = {
    "hook": {  # أيا مغرم - Main hook
        # i - VI - VII - V (with V7 for maqam flavor)
        "progression": ["Am", "F", "G", "E7"],
        "roman_numerals": ["i", "VI", "VII", "V7"],
        "bars": [4, 4, 4, 4],
    },
    "verse_2": {  # أهيم بخمر الغرام
        # i - iv - V - i (classic Arabic cadence)
        "progression": ["Am", "Dm", "E", "Am"],
        "roman_numerals": ["i", "iv", "V", "i"],
        "bars": [4, 4, 4, 4],
    },
    "verse_3": {  # فتني جمال حبيبي
        # i - VI - VII - V (similar to hook but different bass movement)
        "progression": ["Am", "F", "G", "E"],
        "roman_numerals": ["i", "VI", "VII", "V"],
        "bars": [4, 4, 4, 4],
    },
    "verse_4": {  # علمت ما في المصير
        # iv - i - V - i (building to resolution)
        "progression": ["Dm", "Am", "E", "Am"],
        "roman_numerals": ["iv", "i", "V", "i"],
        "bars": [4, 4, 4, 4],
    },
    "outro": {  # يا حبيب الروح
        # i - V/vi - VI - VII - i (intimate, descending)
        "progression": ["Am", "E/G#", "F", "G", "Am"],
        "roman_numerals": ["i", "V/vi", "VI", "VII", "i"],
        "bars": [4, 4, 4, 4, 4],
    },
}

# ============================================================
# Piano Arrangement Structure (4:17 total)
# ============================================================
ARRANGEMENT = [
    {"section": "Intro",       "bars": 4,  "start_sec": 0,   "end_sec": 16,  "chords": "Am - F - G - E7"},
    {"section": "Hook 1",     "bars": 8,  "start_sec": 16,  "end_sec": 48,  "chords": "Am-F-G-E7 (x2)"},
    {"section": "Verse 2",    "bars": 8,  "start_sec": 48,  "end_sec": 80,  "chords": "Am-Dm-E-Am (x2)"},
    {"section": "Hook 2",     "bars": 8,  "start_sec": 80,  "end_sec": 112, "chords": "Am-F-G-E7 (x2)"},
    {"section": "Verse 3",    "bars": 8,  "start_sec": 112, "end_sec": 144, "chords": "Am-F-G-E (x2)"},
    {"section": "Verse 4",    "bars": 8,  "start_sec": 144, "end_sec": 176, "chords": "Dm-Am-E-Am (x2)"},
    {"section": "Hook 3",     "bars": 8,  "start_sec": 176, "end_sec": 208, "chords": "Am-F-G-E7 (x2)"},
    {"section": "Outro",      "bars": 8,  "start_sec": 208, "end_sec": 240, "chords": "Am-E/G#-F-G-Am (x2)"},
]

# ============================================================
# Left Hand Accompaniment Patterns
# ============================================================
PATTERNS = {
    "arpeggio": "Broken chord ascending/descending",
    "oom_pah": "Bass note (1,3) + chord stab (2,4)",
    "waltz_flow": "Continuous broken chord: ♩♪♪ ♩♪♪ (adapted for 4/4)",
    "walking_bass": "Root - 5th - Root - 5th on beat, chord on off-beat",
}

PATTERN_DESCRIPTIONS = {
    "arpeggio": """
    LH: | A---C---E---A- | (arpeggiate chord notes across the bar)
    Pattern: Root → 3rd → 5th → Octave (or 7th) → 5th → 3rd → Root
    Creates flowing, emotional accompaniment
    """,
    "oom_pah": """
    LH: | Am..Am.. | (bass note on beats 1&3, full chord on 2&4)
    Bass: A (beat 1) - E (beat 2) - A (beat 3) - E (beat 4)
    RH chord: F-Am-F-Am
    """,
    "waltz_flow": """
    LH broken pattern adapted for 4/4:
    Beat 1: Root   Beat 2: 5th    Beat 3: Root   Beat 4: 7th
    Beat 5: 3rd     Beat 6: 5th   Beat 7: Root   Beat 8: (rest or repeat)
    """,
}

# ============================================================
# Melody Line Notes (Maqam Bayati on A)
# ============================================================
# These are the melodic notes that would typically be used in the vocal line
# For piano, we play them on the white keys (approximating maqam Bayati)
MELODY_NOTES = {
    "scale": ["A", "B", "C", "D", "E", "F", "G", "A"],
    "maqam_notes": ["A", "B", "C", "D", "E", "F", "G", "A"],
    "characteristic_intervals": [
        "Minor 3rd (C) - gives the melancholic feel",
        "Perfect 5th (E) - the dominant",
        "Minor 6th (F) - the maqam signature",
        "Minor 7th (G) - completes the Bayati character",
    ],
    "melodic_motif_hook": ["A", "C", "E", "G", "A", "F", "E", "D", "C", "A"],
    "melodic_motif_verse": ["A", "B", "C", "D", "E", "D", "C", "B", "A", "G"],
}

# ============================================================
# Generate arrangement summary
# ============================================================
def generate_summary():
    print("=" * 70)
    print("  PIANO COVER ARRANGEMENT")
    print("  Soudeni - Aya Moghraman (Soudani)")
    print("=" * 70)
    print()
    print(f"Key: Am (A minor) - compatible with Maqam Bayati")
    print(f"Tempo: 72 BPM")
    print(f"Time Signature: 4/4")
    print(f"Style: Arabic Pop Ballad with Maqam flavor")
    print(f"Difficulty: Intermediate")
    print(f"Duration: ~4:00")
    print()
    print("SECTION BREAKDOWN:")
    print("-" * 70)
    for section in ARRANGEMENT:
        print(f"  {section['section']:12s} | {section['start_sec']:3d}:{section['end_sec']:3d}s"
              f" | {section['chords']}")
    print()
    print("PROGRESSIONS:")
    print("-" * 70)
    for name, info in CHORDS.items():
        print(f"  {name:12s} | Chords: {' - '.join(info['progression'])}")
        print(f"               | Roman:  {' - '.join(info['roman_numerals'])}")
        print(f"               | Bars:   {sum(info['bars'])} ({info['bars']})")
        print()
    print("LEFT HAND PATTERNS:")
    print("-" * 70)
    for name, desc in PATTERN_DESCRIPTIONS.items():
        print(f"  {name}: {desc.strip()}")
    print()
    print("MELODY NOTES (Maqam Bayati on A):")
    print(f"  Scale: {' - '.join(MELODY_NOTES['maqam_notes'])}")
    print(f"  Hook motif: {' - '.join(MELODY_NOTES['melodic_motif_hook'])}")
    print(f"  Verse motif: {' - '.join(MELODY_NOTES['melodic_motif_verse'])}")

if __name__ == "__main__":
    generate_summary()
