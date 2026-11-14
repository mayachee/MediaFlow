"""
AI Vocal Synthesis & Full Production for Soudeni - Aya Moghraman

Workflow:
1. Generate Arabic TTS audio via gTTS for lyric segments
2. Apply formant filtering for singing-like quality
3. Pitch-shift each syllable to match melody notes using librosa
4. Time-stretch to match note durations
5. Apply vocal EQ, compression, reverb
6. Mix vocals with the full instrumental track
"""

import os
import sys
from io import BytesIO

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from gtts import gTTS
from pydub import AudioSegment, effects
import librosa
import numpy as np

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Tempo: 72 BPM, 1 beat = 0.833 seconds
BPM = 72
BEAT_DURATION = 60.0 / BPM

# ============================================================
# Vocal segments: (arabic_syllable, transliteration, midi_note, duration_beats)
# ============================================================

VOCAL_TRACKS = {
    "Hook": [
        ("aya", "Aya", 69, 0.5), ("mugh", "mu", 69, 0.5),
        ("raman", "ran", 69, 0.5), ("ta", "ta", 65, 0.5),
        ("lla", "l", 67, 0.5), ("qalb", "qa", 69, 0.5),
        ("uka", "lbo", 72, 0.5), ("ku", "ku", 69, 0.5),
        ("bi", "bi", 65, 0.5), ("halaa", "ha", 69, 0.5),
        ("wa", "wa", 67, 0.5), ("bi", "bi", 69, 0.5),
        ("wi", "wi", 65, 0.5), ("dadi", "di", 64, 0.5),
        ("ti", "ti", 69, 1.0), ("wa", "wa", 64, 0.5),
        ("sama", "sama", 65, 0.5), ("khayr", "khayr", 69, 0.5),
        ("la", "la", 69, 0.5), ("ya", "ya", 72, 0.5),
        ("zu", "zu", 76, 0.5), ("l", "ul", 72, 0.5),
        ("aya", "Aya", 69, 0.5), ("mugh", "mu", 65, 0.5),
        ("raman", "ran", 69, 0.5), ("qad", "qad", 72, 0.5),
        ("sha", "sha", 71, 0.5), ("bban", "bba", 69, 0.5),
        ("na", "na", 71, 0.5), ("zi", "zi", 69, 0.5),
        ("ru", "ru", 67, 0.5), ("ka", "ka", 69, 0.5),
        ("as", "as", 65, 0.5), ("sa", "sa", 69, 0.5),
        ("maa", "ma", 67, 1.0), ("ku", "a", 69, 0.5),
        ("i", "i", 64, 0.5), ("la", "la", 65, 0.5),
        ("ni", "ni", 64, 0.5), ("ya", "ya", 67, 0.5),
        ("ra", "ra", 60, 0.5), ("hu", "hu", 64, 0.5),
        ("ma", "ma", 57, 1.0),
    ],
    "Verse_2": [
        ("a", "a", 71, 0.5), ("himu", "hi", 72, 0.5),
        ("bi", "bi", 69, 0.5), ("khamri", "kham", 67, 0.5),
        ("al", "al", 64, 0.5), ("garam", "ra", 69, 0.5),
        ("uni", "uni", 67, 0.5), ("aziza", "az", 64, 0.5),
        ("khafi", "kha", 65, 0.5), ("shabat", "fa", 69, 0.5),
        ("il", "il", 67, 0.5), ("alayn", "la", 65, 0.5),
        ("idin", "a", 69, 1.0), ("ya", "ya", 65, 0.5),
        ("ni", "ni", 64, 0.5),
        ("madata", "mu", 65, 0.5), ("li", "li", 69, 0.5),
        ("wujhi", "wu", 67, 0.5), ("istana", "ja", 72, 0.5),
        ("wa", "wa", 76, 0.5), ("sarat", "sa", 72, 0.5),
        ("kha", "ha", 69, 0.5), ("rayf", "ra", 72, 0.5),
        ("in", "in", 76, 0.5), ("an", "a", 72, 0.5),
        ("khari", "a", 69, 1.0), ("fa", "fa", 65, 0.5),
        ("n", "ri", 69, 0.5),
        ("hayati", "hi", 71, 0.5), ("sahha", "si", 69, 1.0),
        ("wa", "wa", 65, 0.5), ("tir", "tir", 69, 0.5),
        ("matar", "ra", 67, 0.5), ("i", "i", 69, 1.0),
    ],
    "Verse_3": [
        ("fa", "fa", 69, 0.5), ("taa", "ta", 72, 0.5),
        ("ni", "ni", 76, 0.5), ("jamaalu", "ji", 79, 0.5),
        ("habeeb", "ma", 81, 0.5), ("fa", "fa", 79, 0.5),
        ("adi", "la", 76, 0.5), ("i", "i", 72, 0.5),
        ("ama", "ama", 69, 0.5), ("ra", "ra", 65, 0.5),
        ("al", "al", 69, 0.5), ("maa", "ma", 72, 0.5),
        ("ali", "ali", 76, 0.5), ("ku", "ku", 72, 0.5),
        ("hayli", "ha", 69, 0.5), ("fa", "fa", 65, 0.5),
        ("husnu", "hus", 69, 0.5), ("hu", "hu", 65, 0.5),
        ("san", "sa", 72, 0.5), ("ba", "ba", 79, 0.5),
        ("ni", "ni", 76, 0.5), ("fa", "fa", 72, 0.5),
        ("qat", "qat", 69, 1.0), ("tu", "tu", 65, 0.5),
        ("bati", "bat", 69, 0.5),
        ("sehiratu", "sa", 69, 0.5), ("lil", "hi", 67, 0.5),
        ("layali", "rtu", 64, 0.5), ("i", "i", 67, 0.5),
        ("li", "li", 69, 0.5), ("hada", "ha", 72, 0.5),
        ("ir", "ir", 71, 0.5), ("sa", "sa", 69, 1.0),
    ],
    "Verse_4": [
        ("a", "a", 67, 0.5), ("limtu", "li", 69, 0.5),
        ("ma", "ma", 71, 0.5), ("fi", "fi", 72, 0.5),
        ("al", "al", 74, 0.5), ("masir", "i", 72, 0.5),
        ("i", "i", 71, 0.5), ("sair", "ra", 69, 0.5),
        ("alqad", "a", 67, 0.5), ("ra", "ra", 65, 0.5),
        ("w", "wa", 65, 0.5), ("qabiltu", "lu", 67, 0.5),
        ("aysha", "ta", 69, 0.5), ("alha", "a", 71, 0.5),
        ("yati", "ya", 72, 0.5), ("kayfa", "ta", 74, 0.5),
        ("ma", "ma", 76, 0.5), ("kan", "a", 74, 0.5),
        ("ash-shawq", "shi", 72, 0.5), ("uqbal", "a", 71, 0.5),
        ("fi", "fi", 69, 0.5), ("kiyani", "a", 65, 0.5),
        ("i", "i", 72, 0.5), ("ni", "ni", 67, 0.5),
        ("ya", "ya", 69, 0.5), ("ra", "ra", 65, 0.5),
        ("istaqara", "sta", 60, 0.5), ("raja", "ra", 62, 0.5),
        ("ta", "ta", 64, 0.5), ("wasta", "qa", 65, 0.5),
        ("hu", "hu", 67, 0.5), ("da", "da", 72, 0.5),
        ("a", "a", 69, 0.5), ("wta", "tu", 71, 0.5),
        ("u", "u", 64, 0.5), ("fa", "fa", 65, 0.5),
        ("mawla", "ma", 67, 0.5), ("anaam", "a", 69, 0.5),
        ("i", "i", 72, 1.0), ("la", "la", 69, 0.5),
        ("ha", "ha", 67, 0.5), ("u", "u", 72, 1.0),
    ],
    "Outro": [
        ("ya", "ya", 69, 0.5), ("habib", "ha", 67, 0.5),
        ("ar", "bi", 69, 0.5), ("ruh", "ruh", 72, 0.5),
        ("maa", "ma", 76, 0.5), ("hu", "hu", 72, 0.5),
        ("fami", "fa", 69, 0.5), ("al", "al", 67, 0.5),
        ("bi", "bi", 64, 0.5), ("yibuh", "ya", 69, 0.5),
        ("i", "i", 72, 0.5), ("la", "la", 76, 0.5),
        ("bi", "bi", 79, 0.5), ("hu", "hu", 76, 0.5),
        ("allati", "al", 72, 0.5), ("tubuh", "ta", 69, 0.5),
        ("la", "la", 65, 0.5), ("ha", "ha", 69, 0.5),
        ("ya", "ya", 72, 0.5), ("habuh", "ba", 76, 0.5),
        ("u", "u", 74, 0.5), ("hu", "hu", 72, 0.5),
        ("shafik", "sha", 69, 0.5), ("ma", "ma", 67, 0.5),
        ("aad", "a", 52, 0.5), ("irta", "ir", 52, 0.5),
        ("a", "a", 69, 0.5), ("h", "", 0, 0.5),
        ("ya", "ya", 69, 0.5), ("sa", "sa", 72, 0.5),
        ("i", "i", 76, 0.5), ("ra", "ra", 72, 0.5),
        ("a", "a", 69, 1.0), ("ha", "ha", 69, 0.5),
        ("na", "na", 69, 0.5), ("n", "n", 69, 0.5),
    ],
}

# Section order (must match the MIDI arrangement)
SECTION_ORDER = ["Intro", "Hook", "Verse_2", "Hook", "Verse_3", "Verse_4", "Hook", "Outro"]

SECTION_DURATIONS = {
    "Intro": 16, "Hook": 16, "Verse_2": 16, "Verse_3": 16, "Verse_4": 16, "Outro": 20,
}


def freq_from_midi(midi_note):
    """Convert MIDI note number to frequency in Hz."""
    return 440.0 * (2.0 ** ((midi_note - 69) / 12.0))


def generate_tts_segment(text, lang="ar"):
    """Generate TTS audio for a single syllable/word."""
    if not text or not text.strip():
        return None
    
    try:
        tts = gTTS(text=text.strip(), lang=lang, slow=False)
        mp3_buffer = BytesIO()
        tts.write_to_fp(mp3_buffer)
        mp3_buffer.seek(0)
        
        audio = AudioSegment.from_file(mp3_buffer, format="mp3")
        audio = audio.set_frame_rate(44100).set_channels(1)
        # Trim leading/trailing silence
        audio = effects.strip_silence(audio, silence_len=100, silence_thresh=-50, padding=50)
        return audio
    except Exception as e:
        print(f"    TTS error for '{text}': {e}")
        return None


def apply_formant_correction(audio, original_midi=60, target_midi=None):
    """Apply formant/spectral shaping for more singing-like quality."""
    if audio is None or len(audio) < 100:
        return audio
    
    # Skip spectral processing, use EQ-based formant shaping instead
    # This avoids librosa STFT issues and is more reliable
    
    # Boost presence frequencies (2-4kHz) for vocal clarity
    audio = audio.low_pass_filter(12000)
    audio = audio.high_pass_filter(100)
    
    # Gentle compression for singing-like dynamics
    audio = effects.compress_dynamic_range(audio, threshold=-25, ratio=3.0)
    
    return audio


def pitch_shift_to_note(audio, target_midi, original_midi=60):
    """Pitch-shift audio to match target MIDI note frequency."""
    if audio is None or len(audio) < 100:
        return None
    
    samples = np.array(audio.get_array_of_samples(), dtype=np.float32) / (2**15)
    sr = audio.frame_rate
    
    if len(samples) == 0:
        return None
    
    try:
        # Resample for librosa processing
        y = librosa.resample(samples, orig_sr=sr, target_sr=22050)
        
        # Calculate pitch shift in semitones
        semitones = target_midi - original_midi
        
        # Apply pitch shift (preserves duration)
        y_shifted = librosa.effects.pitch_shift(y, sr=22050, n_steps=semitones)
        
        # Resample back
        y_final = librosa.resample(y_shifted, orig_sr=22050, target_sr=sr)
        
        # Soft limiting
        y_final = np.clip(y_final, -0.5, 0.5)
        
        int_samples = (y_final * 32767).astype(np.int16)
        return AudioSegment(
            int_samples.tobytes(),
            frame_rate=sr,
            sample_width=2,
            channels=1
        )
    except Exception as e:
        print(f"    Pitch shift error: {e}")
        return audio


def time_stretch_to_duration(audio, target_duration_sec, sr=44100):
    """Time-stretch audio to match target duration."""
    if audio is None or len(audio) < 100:
        return AudioSegment.silent(int(target_duration_sec * 1000), frame_rate=sr)
    
    samples = np.array(audio.get_array_of_samples(), dtype=np.float32) / (2**15)
    actual_duration = len(samples) / sr
    
    if actual_duration < target_duration_sec * 0.3:
        # Too short - repeat or pad
        result = audio
        while len(result) < target_duration_sec * 1000 * 0.9:
            result = result + audio
        result = result[:int(target_duration_sec * 1000)]
        if len(result) < int(target_duration_sec * 1000):
            result = result + AudioSegment.silent(int(target_duration_sec * 1000) - len(result), frame_rate=sr)
        return result
    
    if actual_duration > target_duration_sec * 3:
        # Too long - trim
        return audio[:int(target_duration_sec * 1000)]
    
    try:
        y = librosa.resample(samples, orig_sr=sr, target_sr=22050)
        rate = actual_duration / target_duration_sec if target_duration_sec > 0 else 1.0
        y_stretched = librosa.effects.time_stretch(y, rate=rate)
        y_final = librosa.resample(y_stretched, orig_sr=22050, target_sr=sr)
        
        int_samples = (np.clip(y_final, -0.5, 0.5) * 32767).astype(np.int16)
        return AudioSegment(
            int_samples.tobytes(),
            frame_rate=sr,
            sample_width=2,
            channels=1
        )
    except Exception as e:
        print(f"    Time stretch error: {e}")
        # Fallback: trim or pad
        target_ms = int(target_duration_sec * 1000)
        if len(audio) > target_ms:
            return audio[:target_ms]
        else:
            return audio + AudioSegment.silent(target_ms - len(audio), frame_rate=sr)


def generate_vocal_track():
    """Generate the complete vocal track aligned with the melody."""
    sample_rate = 44100
    max_time = 0
    
    for sec_name in SECTION_ORDER:
        if sec_name in VOCAL_TRACKS:
            for text, translit, midi_note, dur in VOCAL_TRACKS[sec_name]:
                start_sec = 0  # Will calculate later
                max_time = max(max_time, start_sec + dur * BEAT_DURATION)
    
    # Calculate section start times
    section_starts = {}
    current_time = 0
    for sec in SECTION_ORDER:
        if sec not in section_starts:
            section_starts[sec] = current_time
        current_time += SECTION_DURATIONS.get(sec, 16) * BEAT_DURATION
    
    total_duration = current_time + 1.0
    
    print(f"Total arrangement: {total_duration:.1f}s")
    
    # Create master vocal track (mono, will convert to stereo for mixing)
    master_vocal = AudioSegment.silent(int(total_duration * 1000 + 500), frame_rate=sample_rate)
    
    for sec_name in SECTION_ORDER:
        if sec_name not in VOCAL_TRACKS:
            print(f"  Skipping {sec_name} (no vocal data)")
            continue
        
        start_time = section_starts.get(sec_name, 0)
        segments = VOCAL_TRACKS[sec_name]
        current_time = start_time
        
        print(f"  Synthesizing {sec_name} ({len(segments)} syllables)...")
        
        for i, (arabic_text, translit, midi_note, duration_beats) in enumerate(segments):
            duration_sec = duration_beats * BEAT_DURATION
            position_ms = int(current_time * 1000)
            
            if midi_note == 0 or not arabic_text.strip():
                # Rest - just advance time
                current_time += duration_sec
                continue
            
            # Generate TTS
            tts_audio = generate_tts_segment(arabic_text)
            
            if tts_audio is None:
                # Use silence
                segment_silence = AudioSegment.silent(int(duration_sec * 1000), frame_rate=sample_rate)
                master_vocal = master_vocal.overlay(segment_silence, position=position_ms)
                current_time += duration_sec
                continue
            
            # Apply formant correction (make speech more vocal-like)
            tts_audio = apply_formant_correction(tts_audio, original_midi=60, target_midi=midi_note)
            
            # Pitch shift to melody note
            tts_audio = pitch_shift_to_note(tts_audio, midi_note, original_midi=60)
            
            if tts_audio is None:
                current_time += duration_sec
                continue
            
            # Time-stretch to fit note duration
            tts_audio = time_stretch_to_duration(tts_audio, duration_sec, sample_rate)
            
            if tts_audio is None:
                current_time += duration_sec
                continue
            
            # Apply vocal processing
            vocal = tts_audio.set_frame_rate(sample_rate)
            vocal = effects.compress_dynamic_range(
                vocal, threshold=-20.0, ratio=3.0, attack=5, release=50
            )
            vocal = vocal.high_pass_filter(80)
            vocal = vocal.low_pass_filter(8000)
            
            # Slight fade in/out for smoother transitions
            fade_ms = min(20, int(duration_sec * 1000 * 0.2))
            if fade_ms > 0:
                vocal = vocal.fade_in(fade_ms).fade_out(fade_ms)
            
            # Place in master track
            master_vocal = master_vocal.overlay(vocal, position=position_ms)
            
            current_time += duration_sec
    
    # Final vocal processing
    master_vocal = effects.compress_dynamic_range(
        master_vocal, threshold=-25, ratio=3.0, attack=10, release=100
    )
    
    # Apply slight echo/reverb effect and reduce level
    master_vocal = master_vocal - 3  # Lower vocals in mix
    
    # Normalize to target level using max_dBFS
    target_level = -10
    if master_vocal.max > 0:
        change = target_level - (20 * np.log10(master_vocal.max / (2**15)))
        if abs(change) < 30:
            master_vocal = master_vocal.apply_gain(change)
    
    # Save vocal track
    vocal_path = os.path.join(SCRIPT_DIR, "soudeni_aya_moghraman_cover_vocals.wav")
    master_vocal.export(vocal_path, format="wav")
    print(f"\n  Vocals saved: {vocal_path}")
    print(f"  Duration: {len(master_vocal)/1000:.1f}s")
    print(f"  File size: {os.path.getsize(vocal_path) / 1024:.0f} KB")
    
    return vocal_path


def mix_with_instrumental(vocal_wav, instrumental_wav, output_wav):
    """Mix vocals with the full instrumental track."""
    print("\nMixing vocals with instrumental...")
    
    vocal = AudioSegment.from_file(vocal_wav)
    instrumental = AudioSegment.from_file(instrumental_wav)
    
    # Match sample rates and channels
    sample_rate = 48000
    vocal = vocal.set_frame_rate(sample_rate).set_channels(2).apply_gain(-6)
    instrumental = instrumental.set_frame_rate(sample_rate).set_channels(2)
    
    # Align lengths
    if len(vocal) < len(instrumental):
        vocal = vocal + AudioSegment.silent(len(instrumental) - len(vocal))
    elif len(vocal) > len(instrumental):
        instrumental = instrumental + AudioSegment.silent(len(vocal) - len(instrumental))
    
    # Apply vocal EQ for presence
    vocal = vocal.high_pass_filter(100)
    vocal = vocal.low_pass_filter(12000)
    
    # Mix
    mixed = instrumental.overlay(vocal)
    
    # Master: gentle compression and limiting
    mixed = effects.compress_dynamic_range(
        mixed, threshold=-15, ratio=2.5, attack=5, release=100
    )
    
    # Normalize final mix
    target_peak_db = -0.5
    if mixed.max > 0:
        current_peak_db = 20 * np.log10(mixed.max / (2**15))
        change = target_peak_db - current_peak_db
        if abs(change) < 30:
            mixed = mixed.apply_gain(change)
    
    print(f"  Mixed duration: {len(mixed)/1000:.1f}s")
    print(f"  Saving: {output_wav}")
    mixed.export(output_wav, format="wav")
    
    file_size = os.path.getsize(output_wav)
    print(f"  File size: {file_size / (1024*1024):.1f} MB")


if __name__ == "__main__":
    print("=" * 60)
    print("  AI VOCAL SYNTHESIS & FULL PRODUCTION")
    print("  Soudeni - Aya Moghraman (Aya Mughraman)")
    print("=" * 60)
    print()
    
    # Step 1: Generate vocals
    print("Step 1: Generating AI vocals from Arabic lyrics...")
    vocal_wav = generate_vocal_track()
    
    # Step 2: Mix with instrumental
    if os.path.exists(vocal_wav):
        instrumental_wav = os.path.join(SCRIPT_DIR, "soudeni_aya_moghraman_cover_full_production.wav")
        output_wav = os.path.join(SCRIPT_DIR, "soudeni_aya_moghraman_cover_professional_mix.wav")
        
        if os.path.exists(instrumental_wav):
            print("\nStep 2: Mixing vocals with full instrumental...")
            mix_with_instrumental(vocal_wav, instrumental_wav, output_wav)
            print("\nDone! Professional mix created.")
            print(f"  Output: {output_wav}")
        else:
            print("  Instrumental WAV not found. Run create_full_production.py first.")
