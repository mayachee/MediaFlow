"""
Generate a printable PDF chord chart for Soudeni - Aya Moghraman piano cover.
"""
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.units import inch, mm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import landscape
import os

# Arabic text transliterations
SECTIONS = [
    {
        "name": "Intro (4 bars)",
        "arabic": "Instrumental - establish maqam",
        "transposed": "Instrumental - establish maqam",
        "chords": "Am | F | G | E7",
        "roman": "i - VI - VII - V7",
        "lh_pattern": "Arpeggio (8th notes)",
        "description": "Gentle broken chords, establish the maqam mood",
    },
    {
        "name": "Hook (8 bars)",
        "arabic": "أَيَا مُغْرمًا تَعلَّقَ قَلْبُكَ بِالهَوى بِالوِدَادِ...",
        "transposed": "Aya moghraman ta'allaqa qalbuka bil-hawa bi-l-widad...",
        "chords": "Am | F | G | E7 (x2)",
        "roman": "i - VI - VII - V7",
        "lh_pattern": "Walking bass + melody",
        "description": "Main hook - emotional peak, walking bass in LH",
    },
    {
        "name": "Verse 2 (8 bars)",
        "arabic": "أَهِيمُ بِخَمْرِ الغَرَامِ مُنادٍ عَزِيزًا...",
        "transposed": "Ahimu bi-khamr al-gharam, munadin azizan...",
        "chords": "Am | Dm | E | Am (x2)",
        "roman": "i - iv - V - i",
        "lh_pattern": "Oom-pah (bass 1&3, chord 2&4)",
        "description": "Intoxication of love - steady rhythm builds tension",
    },
    {
        "name": "Hook (8 bars)",
        "arabic": "أَيَا مُغْرمًا... (repeat)",
        "transposed": "Aya moghraman... (repeat)",
        "chords": "Am | F | G | E7 (x2)",
        "roman": "i - VI - VII - V7",
        "lh_pattern": "Walking bass + melody",
        "description": "Chorus returns - more dynamic",
    },
    {
        "name": "Verse 3 (8 bars)",
        "arabic": "فَتَنِّي جَمَالُ حُبِيبِ فُؤَادِي أَمِيرُ المَعَالِي...",
        "transposed": "Fatanni jamaalu hubbi fuwad.i amir al-ma'ali...",
        "chords": "Am | F | G | E (x2)",
        "roman": "i - VI - VII - V",
        "lh_pattern": "Oom-pah (bass 1&3, chord 2&4)",
        "description": "Seduced by beloved's beauty - lyrical melody",
    },
    {
        "name": "Verse 4 (8 bars)",
        "arabic": "عَلِمْتُ ما في المَصِيرِ، سَيْر القَدَر...",
        "transposed": "Alimtu ma fi al-masir, sayr al-qadar...",
        "chords": "Dm | Am | E | Am (x2)",
        "roman": "iv - i - V - i",
        "lh_pattern": "Oom-pah (bass 1&3, chord 2&4)",
        "description": "Accepting fate - builds toward final chorus",
    },
    {
        "name": "Hook (8 bars)",
        "arabic": "أَيَا مُغْرمًا... (repeat)",
        "transposed": "Aya moghraman... (repeat)",
        "chords": "Am | F | G | E7 (x2)",
        "roman": "i - VI - VII - V7",
        "lh_pattern": "Walking bass + melody",
        "description": "Final emotional peak",
    },
    {
        "name": "Outro (10 bars)",
        "arabic": "يَا حَبِيب الرُّوحْ مَاهُو فُمِّي قَلْبِي...",
        "transposed": "Ya habib ar-ruh mahhu fummi qalbi...",
        "chords": "Am | E/G# | F | G | Am (x2)",
        "roman": "i - V/vi - VI - VII - i",
        "lh_pattern": "Arpeggio (8th notes, gentle)",
        "description": "Intimate whispered ending - rubato",
    },
]

CHORD_DIAGRAMS = {
    "Am":   ["x", "0", "0", "2", "1", "0",  "A-C-E-A"],
    "F":    ["1", "3", "3", "2", "1", "1",  "F-A-C-F"],
    "G":    ["3", "2", "0", "0", "0", "3",  "G-B-D-G"],
    "E7":   ["0", "2", "0", "1", "0", "0",  "E-G#-B-D"],
    "E":    ["0", "2", "2", "1", "0", "0",  "E-G#-B-E"],
    "Dm":   ["x", "0", "0", "2", "1", "1",  "D-F-A-D"],
    "E/G#": ["4", "2", "2", "1", "0", "0",  "E-G#-B-E (G# bass)"],
}

MELODY_MOTIFS = {
    "Hook":    "A4 F4 A4 F4 | G4 A4 C5 A4 | F4 A4 G4 A4 | F4 E4 A4 - | A4 C5 E5 C5 | A4 F4 A4 C5 | B4 A4 G4 A4 | F4 A4 G5 A4 | E4 F4 E4 D4 | C4 E4 A3 -",
    "Verse_2": "B4 C5 A4 G4 | E4 A4 G4 E4 | D4 E4 F4 G4 | A4 B4 C5 B4 | A4 G4 A4 C5 | E5 C5 A4 G4 | F4 A5 G4 E4 | A4 F4 E4 A4",
    "Outro":   "A4 G4 A4 C5 | E5 C5 A4 G4 | E4 A4 C5 E5 | G5 E5 C5 A4 | F4 A4 C5 E5 | D5 C5 A4 G4 | E4 G4 A5 - | A4 C5 E5 C5 | A4 - - -",
}

def create_pdf():
    filename = os.path.join(os.path.dirname(os.path.abspath(__file__)), 
                            "soudeni_aya_moghraman_cover.pdf")
    
    doc = SimpleDocTemplate(filename, pagesize=landscape(A4),
                            rightMargin=20, leftMargin=20,
                            topMargin=20, bottomMargin=20)
    
    styles = getSampleStyleSheet()
    style_title = ParagraphStyle(
        'CustomTitle', parent=styles['Heading1'], fontSize=24, 
        alignment=TA_CENTER, spaceAfter=12, textColor=colors.HexColor('#2c3e50')
    )
    style_h2 = ParagraphStyle(
        'CustomH2', parent=styles['Heading2'], fontSize=14, 
        alignment=TA_LEFT, spaceAfter=6, textColor=colors.HexColor('#34495e')
    )
    style_body = ParagraphStyle(
        'CustomBody', parent=styles['BodyText'], fontSize=10, 
        leading=14, alignment=TA_LEFT
    )
    style_small = ParagraphStyle(
        'CustomSmall', parent=styles['BodyText'], fontSize=8, 
        leading=12, alignment=TA_CENTER
    )
    
    story = []
    
    # Title
    story.append(Paragraph("Soudeni - Aya Moghraman (سوداني - أيا مُغْرما)", style_title))
    story.append(Paragraph("Piano Cover Arrangement", style_h2))
    story.append(Paragraph("Key: Am (A minor) | Tempo: 72 BPM | Time: 4/4 | Maqam: Bayati", style_body))
    story.append(Paragraph("Genre: Tunisian/Arabic Pop (Harissa Pop) | Difficulty: Intermediate", style_body))
    story.append(Spacer(1, 0.2*inch))
    
    # Chord Diagrams
    story.append(Paragraph("CHORD DIAGRAMS", style_h2))
    chord_data = [["Chord", "Fingering", "Notes", "Piano"]]
    for name, info in CHORD_DIAGRAMS.items():
        chord_data.append([name, 
                          f"e|{info[0]}\nB|{info[1]}\nG|{info[2]}\nD|{info[3]}\nA|{info[4]}\nE|{info[5]}",
                          info[6].split('-')[0] if '-' not in info[6] else info[6].split(' (')[0],
                          info[6]])
    
    t = Table(chord_data, colWidths=[0.7*inch, 0.8*inch, 0.8*inch, 1.2*inch])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3498db')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 11),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('FONTNAME', (0, 1), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 1), (-1, -1), 10),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    story.append(t)
    story.append(Spacer(1, 0.15*inch))
    
    # Song Structure
    story.append(Paragraph("SONG STRUCTURE", style_h2))
    struct_data = [["Section", "Bars", "Chords", "LH Pattern", "Arabic Lyrics (Transliteration)"]]
    for sec in SECTIONS:
        struct_data.append([sec["name"], str(len(sec["chords"].split("|")) * 4), 
                           sec["chords"], sec["lh_pattern"], sec["transposed"][:40]])
    
    t2 = Table(struct_data, colWidths=[0.9*inch, 0.4*inch, 1.4*inch, 1.2*inch, 2.7*inch])
    t2.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e74c3c')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 3),
        ('RIGHTPADDING', (0, 0), (-1, -1), 3),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('ROWBACKGROUNDCOLOR', (0, 1), (-1, -1), colors.whitesmoke),
    ]))
    story.append(t2)
    story.append(Spacer(1, 0.15*inch))
    
    # Melody Motifs
    story.append(Paragraph("RIGHT HAND - MELODY MOTIFS", style_h2))
    for name, motif in MELODY_MOTIFS.items():
        story.append(Paragraph(f"{name}:", style_h2))
        story.append(Paragraph(f"  {motif}", style_small))
        story.append(Spacer(1, 0.05*inch))
    
    # Left Hand Patterns
    story.append(Paragraph("LEFT HAND - ACCOMPANIMENT PATTERNS", style_h2))
    patterns = [
        ("Arpeggio", "8th notes: Root-3rd-5th-Octave-5th-3rd-Root", 
         "Use for intro/outro - gentle, flowing"),
        ("Oom-Pah", "Bass on 1&3, chord stab on 2&4", 
         "Use for verses - steady, supportive"),
        ("Walking Bass", "Root-5th-Octave on 8th notes", 
         "Use for hook/chorus - driving, energetic"),
    ]
    pat_data = [["Pattern", "Rhythm", "Description"]]
    for p in patterns:
        pat_data.append(list(p))
    
    t3 = Table(pat_data, colWidths=[1.2*inch, 2.5*inch, 3.0*inch])
    t3.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#9b59b6')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('BACKGROUND', (0, 1), (-1, -1), colors.whitesmoke),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(t3)
    story.append(Spacer(1, 0.2*inch))
    
    # Playing Tips
    story.append(Paragraph("PLAYING TIPS", style_h2))
    tips = [
        "1. Use sustain pedal (hold) on chord changes for smooth flow",
        "2. Emphasize beat 1 in verses with oom-pah pattern (bass note louder)",
        "3. Build dynamics: soft verses, powerful hook, intimate outro",
        "4. Add Arabic ornamentation: grace notes (C-D-E) and slides between notes",
        "5. In the outro, play with rubato (flexible tempo) for emotional expression",
        "6. For authentic maqam feel, use the sustain pedal to create microtonal inflections",
        "7. The E7 chord in the hook creates tension - resolve to Am for maqam authenticity",
        "8. In Verse 2, the Dm-Am-E progression creates a modal feel typical of Arabic music",
    ]
    for tip in tips:
        story.append(Paragraph(tip, style_body))
    story.append(Spacer(1, 0.1*inch))
    
    story.append(Paragraph("Files generated: soudeni_piano_cover.py, soudeni_aya_moghraman_cover.mid,"
                          " soudeni_aya_moghraman_cover.xml (MusicXML for MuseScore/Sibelius)",
                          style_small))
    
    doc.build(story)
    print(f"PDF saved to: {filename}")
    
create_pdf()
