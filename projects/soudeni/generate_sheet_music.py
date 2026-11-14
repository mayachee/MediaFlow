"""
Generate sheet music for Soudeni - Aya Moghraman piano cover
Creates MusicXML and a printable PDF chord chart.
"""
import music21
from music21 import stream, note, chord, meter, tempo
import music21.key as modKey
import music21.metadata
import music21.instrument
import music21.volume
import os

s = stream.Score()
s.metadata = music21.metadata.Metadata()
s.metadata.title = "Soudeni - Aya Moghraman (Piano Cover)"
s.metadata.composer = "Arranged for Piano"
s.metadata.key = "A minor"
s.metadata.tempo = "72 BPM"

piano = instrument = music21.instrument.Piano()
piano.partName = "Piano"

p = stream.Part(piano)

# Key signature: A minor (no accidentals)
ks = modKey.Key('a')
ts = meter.TimeSignature('4/4')
mm = tempo.MetronomeMark(number=72)

p.append(ks)
p.append(ts)
p.append(mm)

# Note to pitch mapping
NOTE_MAP = {
    'A3': 'A3', 'B3': 'B3', 'C4': 'C4', 'D4': 'D4', 'E4': 'E4', 'F4': 'F4', 'G4': 'G4',
    'A4': 'A4', 'B4': 'B4', 'C5': 'C5', 'D5': 'D5', 'E5': 'E5', 'F5': 'F5', 'G5': 'G5',
    'A5': 'A5', 'B5': 'B5',
}

def add_melody(notes_list, offset):
    """Add melody notes to the part."""
    for pitch_name, dur in notes_list:
        if pitch_name != '-':
            n = note.Note(NOTE_MAP.get(pitch_name, 'C4'), quarterLength=dur)
            p.insert(offset, n)
        offset += dur

def add_chord_in_lh(chord_name, offset, dur):
    """Add a chord for left hand."""
    chord_notes = {
        'Am': ['A2', 'C4', 'E4'],
        'F': ['F3', 'A3', 'C4'],
        'G': ['G3', 'B3', 'D4'],
        'E7': ['E2', 'G#3', 'B3', 'D4'],
        'E': ['E2', 'G#3', 'B3'],
        'Dm': ['D3', 'F3', 'A3'],
        'E/G#': ['G#2', 'B3', 'E4'],
    }
    notes_list = chord_notes.get(chord_name, ['A2', 'C4', 'E4'])
    c = chord.Chord(notes_list, quarterLength=dur)
    c.volume = music21.volume.Volume(velocity=65)  # Softer
    p.insert(offset, c)

# Build the arrangement
# Section 1: Intro (4 bars)
add_chord_in_lh('Am', 0, 2); add_chord_in_lh('F', 2, 2); add_chord_in_lh('G', 4, 2); add_chord_in_lh('E7', 6, 2)
# Intro melody
add_melody([("A4",0.5),("C5",0.5),("E5",0.5),("A5",0.5),("F4",0.5),("A4",0.5),("C5",0.5),("F5",0.5),("G4",0.5),("B4",0.5),("D5",0.5),("G5",0.5)], 0)
add_melody([("E5",1.0),("C5",0.5),("E5",0.5),("A4",1.0)], 6)

offset = 8  # After intro

# Hook 1 (8 bars)
add_chord_in_lh('Am', offset, 2); add_chord_in_lh('F', offset+2, 2); add_chord_in_lh('G', offset+4, 2); add_chord_in_lh('E7', offset+6, 2)
add_chord_in_lh('Am', offset+8, 2); add_chord_in_lh('F', offset+10, 2); add_chord_in_lh('G', offset+12, 2); add_chord_in_lh('E7', offset+14, 2)

# Hook melody (first 4 bars)
add_melody([
    ("A4",0.5),("F4",0.5),("A4",0.5),("F4",0.5),("G4",0.5),("A4",0.5),("C5",0.5),("A4",0.5),
    ("F4",0.5),("A4",0.5),("G4",0.5),("A4",0.5),("F4",0.5),("E4",0.5),("A4",1.0),("-",1.0),
], offset)

# Hook melody (second 4 bars)
add_melody([
    ("A4",0.5),("C5",0.5),("E5",0.5),("C5",0.5),("A4",0.5),("F4",0.5),("A4",0.5),("C5",0.5),
    ("B4",0.5),("A4",0.5),("G4",0.5),("A4",0.5),("F4",0.5),("A4",0.5),("G4",1.0),("A4",0.5),
    ("E4",0.5),("F4",0.5),("E4",0.5),("D4",0.5),("C4",1.0),("E4",0.5),("A3",1.0),("-",1.0),
], offset+8)

offset += 16  # After hook

# Verse 2 (8 bars): Am - Dm - E - Am (x2)
add_chord_in_lh('Am', offset, 2); add_chord_in_lh('Dm', offset+2, 2); add_chord_in_lh('E', offset+4, 2); add_chord_in_lh('Am', offset+6, 2)
add_chord_in_lh('Am', offset+8, 2); add_chord_in_lh('Dm', offset+10, 2); add_chord_in_lh('E', offset+12, 2); add_chord_in_lh('Am', offset+14, 2)

# Verse 2 melody
add_melody([
    ("B4",0.5),("C5",0.5),("A4",0.5),("G4",0.5),("E4",0.5),("A4",0.5),("G4",0.5),("E4",0.5),
    ("D4",0.5),("E4",0.5),("F4",0.5),("G4",0.5),("A4",0.5),("B4",0.5),("C5",0.5),("B4",0.5),
    ("A4",0.5),("G4",0.5),("A4",0.5),("C5",0.5),("E5",0.5),("C5",0.5),("A4",0.5),("G4",0.5),
    ("F4",0.5),("A4",1.0),("G4",0.5),("E4",0.5),("A4",0.5),("F4",0.5),("E4",1.0),("A4",0.5),
], offset)

offset += 16  # After verse 2

# Hook 2 (8 bars) - same as Hook 1
add_chord_in_lh('Am', offset, 2); add_chord_in_lh('F', offset+2, 2); add_chord_in_lh('G', offset+4, 2); add_chord_in_lh('E7', offset+6, 2)
add_chord_in_lh('Am', offset+8, 2); add_chord_in_lh('F', offset+10, 2); add_chord_in_lh('G', offset+12, 2); add_chord_in_lh('E7', offset+14, 2)

add_melody([
    ("A4",0.5),("F4",0.5),("A4",0.5),("F4",0.5),("G4",0.5),("A4",0.5),("C5",0.5),("A4",0.5),
    ("F4",0.5),("A4",0.5),("G4",0.5),("A4",0.5),("F4",0.5),("E4",0.5),("A4",1.0),("-",1.0),
    ("A4",0.5),("C5",0.5),("E5",0.5),("C5",0.5),("A4",0.5),("F4",0.5),("A4",0.5),("C5",0.5),
    ("B4",0.5),("A4",0.5),("G4",0.5),("A4",0.5),("F4",0.5),("A4",0.5),("G4",1.0),("A4",0.5),
    ("E4",0.5),("F4",0.5),("E4",0.5),("D4",0.5),("C4",1.0),("E4",0.5),("A3",1.0),("-",1.0),
], offset)

offset += 16

# Verse 3 (8 bars): Am - F - G - E (x2)
add_chord_in_lh('Am', offset, 2); add_chord_in_lh('F', offset+2, 2); add_chord_in_lh('G', offset+4, 2); add_chord_in_lh('E', offset+6, 2)
add_chord_in_lh('Am', offset+8, 2); add_chord_in_lh('F', offset+10, 2); add_chord_in_lh('G', offset+12, 2); add_chord_in_lh('E', offset+14, 2)

add_melody([
    ("A4",0.5),("C5",0.5),("E5",0.5),("G5",0.5),("A5",0.5),("G5",0.5),("E5",0.5),("C5",0.5),
    ("A4",0.5),("F4",0.5),("A4",0.5),("C5",0.5),("E5",0.5),("C5",0.5),("A4",0.5),("F4",0.5),
    ("G4",0.5),("A4",0.5),("B4",0.5),("C5",0.5),("B4",0.5),("A4",1.0),("F4",0.5),("-",0.5),
    ("A4",0.5),("G4",0.5),("E4",0.5),("G4",0.5),("A4",0.5),("C5",0.5),("B4",0.5),("A4",1.0),
], offset)

offset += 16

# Verse 4 (8 bars): Dm - Am - E - Am (x2)
add_chord_in_lh('Dm', offset, 2); add_chord_in_lh('Am', offset+2, 2); add_chord_in_lh('E', offset+4, 2); add_chord_in_lh('Am', offset+6, 2)
add_chord_in_lh('Dm', offset+8, 2); add_chord_in_lh('Am', offset+10, 2); add_chord_in_lh('E', offset+12, 2); add_chord_in_lh('Am', offset+14, 2)

add_melody([
    ("G4",0.5),("A4",0.5),("B4",0.5),("C5",0.5),("D5",0.5),("C5",0.5),("B4",0.5),("A4",0.5),
    ("G4",0.5),("F4",0.5),("E4",0.5),("F4",0.5),("G4",0.5),("A4",0.5),("B4",0.5),("C5",0.5),
    ("D5",0.5),("C5",0.5),("B4",0.5),("A4",0.5),("G4",0.5),("F4",0.5),("E4",0.5),("D4",0.5),
    ("C4",0.5),("D4",0.5),("E4",0.5),("F4",0.5),("G4",1.0),("A4",0.5),("B4",0.5),("C5",0.5),
    ("B4",0.5),("A4",0.5),("G4",0.5),("A4",1.0),
], offset)

offset += 16

# Hook 3 (8 bars) - same as Hook 1
add_chord_in_lh('Am', offset, 2); add_chord_in_lh('F', offset+2, 2); add_chord_in_lh('G', offset+4, 2); add_chord_in_lh('E7', offset+6, 2)
add_chord_in_lh('Am', offset+8, 2); add_chord_in_lh('F', offset+10, 2); add_chord_in_lh('G', offset+12, 2); add_chord_in_lh('E7', offset+14, 2)

add_melody([
    ("A4",0.5),("F4",0.5),("A4",0.5),("F4",0.5),("G4",0.5),("A4",0.5),("C5",0.5),("A4",0.5),
    ("F4",0.5),("A4",0.5),("G4",0.5),("A4",0.5),("F4",0.5),("E4",0.5),("A4",1.0),("-",1.0),
    ("A4",0.5),("C5",0.5),("E5",0.5),("C5",0.5),("A4",0.5),("F4",0.5),("A4",0.5),("C5",0.5),
    ("B4",0.5),("A4",0.5),("G4",0.5),("A4",0.5),("F4",0.5),("A4",0.5),("G4",1.0),("A4",0.5),
    ("E4",0.5),("F4",0.5),("E4",0.5),("D4",0.5),("C4",1.0),("E4",0.5),("A3",1.0),("-",1.0),
], offset)

offset += 16

# Outro (10 bars): Am - E/G# - F - G - Am (x2)
add_chord_in_lh('Am', offset, 2); add_chord_in_lh('E/G#', offset+2, 2); add_chord_in_lh('F', offset+4, 2); add_chord_in_lh('G', offset+6, 2); add_chord_in_lh('Am', offset+8, 2)
add_chord_in_lh('Am', offset+10, 2); add_chord_in_lh('E/G#', offset+12, 2); add_chord_in_lh('F', offset+14, 2); add_chord_in_lh('G', offset+16, 2); add_chord_in_lh('Am', offset+18, 2)

add_melody([
    ("A4",0.5),("G4",0.5),("A4",0.5),("C5",0.5),("E5",0.5),("C5",0.5),("A4",0.5),("G4",0.5),
    ("E4",0.5),("A4",0.5),("C5",0.5),("E5",0.5),("G5",0.5),("E5",0.5),("C5",0.5),("A4",0.5),
    ("F4",0.5),("A4",0.5),("C5",0.5),("E5",0.5),("D5",0.5),("C5",0.5),("A4",0.5),("G4",0.5),
    ("E4",0.5),("G4",0.5),("A4",1.0),("-",1.0),("A4",0.5),("C5",0.5),("E5",0.5),("C5",0.5),
    ("A4",1.0),("-",1.0),("-",1.0),("-",1.0),
], offset)

p.makeRests(fillGaps=False)
s.insert(0, p)

# Save as MusicXML
xml_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "soudeni_aya_moghraman_cover.xml")
s.write('musicxml', fp=xml_path)
print(f"Sheet music saved to: {xml_path}")

# Also save as MIDI
midi_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "soudeni_aya_moghraman_cover.musicxml.mid")
s.write('midi', fp=midi_path)
print(f"MIDI saved to: {midi_path}")

# Try to render to PDF/LilyPond if available
try:
    pdf_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "soudeni_aya_moghraman_cover.pdf")
    s.write('lily.pdf', fp=pdf_path)
    print(f"PDF saved to: {pdf_path}")
except Exception as e:
    print(f"PDF generation skipped: {e}")
    # Try musicpdf instead
    try:
        s.show('musicxml.png')
        print(f"PNG saved")
    except:
        print("PNG generation also skipped")
