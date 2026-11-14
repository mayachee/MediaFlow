"""
Generate audio (WAV/MP3) from the piano cover MIDI.
Uses numpy vectorized synthesis for piano-like sound.
"""
import os
import math
import subprocess
import numpy as np
import wave
import struct

# File paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
midi_path = os.path.join(SCRIPT_DIR, "soudeni_aya_moghraman_cover.mid")
wav_path = os.path.join(SCRIPT_DIR, "soudeni_aya_moghraman_piano_cover.wav")
mp3_path = os.path.join(SCRIPT_DIR, "soudeni_aya_moghraman_piano_cover.mp3")

print(f"MIDI file: {midi_path}")
print(f"Output WAV: {wav_path}")

# Parse MIDI file
def read_midi(filepath):
    """Parse MIDI file: returns (notes_list, bpm, ppq).
    notes_list: [(start_sec, midi_note, velocity, duration_sec), ...]"""
    with open(filepath, 'rb') as f:
        data = f.read()
    
    # Parse header chunk
    if data[:4] != b'MThd':
        raise ValueError("Not a MIDI file")
    header_len = struct.unpack('>I', data[4:8])[0]
    fmt = struct.unpack('>H', data[8:10])[0]
    num_tracks = struct.unpack('>H', data[10:12])[0]
    ppq = struct.unpack('>H', data[12:14])[0]  # Pulses per quarter note
    print(f"MIDI: Format={fmt}, Tracks={num_tracks}, PPQ={ppq}")
    
    idx = 14  # Start after header (6 bytes header data + 8 byte header)
    tempo_us = 500000  # Default 120 BPM
    notes = []
    
    # Scan all tracks for tempo and notes
    for track in range(num_tracks):
        if data[idx:idx+4] != b'MTrk':
            print(f"  Skipping non-MTrk at track {track}")
            break
        track_len = struct.unpack('>I', data[idx+4:idx+8])[0]
        idx += 8
        track_end = idx + track_len
        
        current_tick = 0
        status = 0
        active_notes = {}  # note_num -> (start_tick, velocity)
        
        while idx < track_end:
            # Read delta time (variable-length quantity)
            delta = 0
            while True:
                b = data[idx]
                idx += 1
                delta = (delta << 7) | (b & 0x7F)
                if not (b & 0x80):
                    break
            current_tick += delta
            
            # Read event
            b = data[idx]
            if b == 0xFF:  # Meta event
                idx += 1
                meta_type = data[idx]
                idx += 1
                length = 0
                while True:
                    b = data[idx]
                    idx += 1
                    length = (length << 7) | (b & 0x7F)
                    if not (b & 0x80):
                        break
                
                if meta_type == 0x51 and length == 3:  # Tempo
                    tempo_bytes = data[idx:idx+3]
                    tempo_us = (tempo_bytes[0] << 16) | (tempo_bytes[1] << 8) | tempo_bytes[2]
                idx += length
            else:
                status = b
                idx += 1
                
                if (status & 0xF0) == 0x90:  # Note On
                    note_num = data[idx]
                    velocity = data[idx + 1]
                    idx += 2
                    if velocity > 0:
                        active_notes[note_num] = (current_tick, velocity)
                elif (status & 0xF0) == 0x80:  # Note Off
                    note_num = data[idx]
                    idx += 2
                    if note_num in active_notes:
                        start_tick, vel = active_notes.pop(note_num)
                        dur_ticks = current_tick - start_tick
                        notes.append((start_tick, note_num, vel, dur_ticks))
                elif (status & 0xF0) in (0xB0, 0xE0):
                    idx += 2
                elif (status & 0xF0) in (0xC0, 0xD0):
                    idx += 1
        
        # Handle notes still active at end of track
        for note_num, (start_tick, vel) in active_notes.items():
            notes.append((start_tick, note_num, vel, ppq))  # Default 1 beat duration
    
    bpm = 60000000 / tempo_us
    print(f"  Tempo: {tempo_us} us/beat = {bpm:.1f} BPM")
    print(f"  Total notes: {len(notes)}")
    
    # Convert ticks to seconds
    sec_per_tick = tempo_us / (ppq * 1000000.0)
    notes_sec = [(tick * sec_per_tick, note, vel, dur_ticks * sec_per_tick) 
                  for (tick, note, vel, dur_ticks) in notes]
    
    # Sort by start time
    notes_sec.sort(key=lambda x: x[0])
    
    return notes_sec, bpm, ppq

# Read MIDI
notes, detected_bpm, detected_ppq = read_midi(midi_path)
print(f"\nBPM: {detected_bpm}")

if not notes:
    print("ERROR: No notes extracted!")
    exit(1)

print(f"Total notes: {len(notes)}")
max_end = max(n[0] + n[3] for n in notes)
print(f"Duration: {max_end:.1f}s")

sample_rate = 44100

# Calculate total audio duration
total_duration = max_end + 1.0  # Add 1 second of fade
total_samples = int(total_duration * sample_rate)
print(f"Total samples: {total_samples:,}")

def freq(midi_note):
    return 440.0 * (2.0 ** ((midi_note - 69) / 12.0))

# Piano harmonics
HARMONICS = [
    (1.0, 1.0),
    (2.0, 0.35),
    (3.0, 0.15),
    (4.0, 0.10),
    (5.0, 0.05),
    (6.0, 0.04),
    (7.0, 0.03),
]

# Generate audio using vectorized approach
audio = np.zeros(total_samples, dtype=np.float64)
print("\nSynthesizing piano audio...")

for note_i, (start_sec, midi_num, velocity, dur_sec) in enumerate(notes):
    start_sample = int(start_sec * sample_rate)
    num_samples = min(int(dur_sec * sample_rate), total_samples - start_sample)
    
    if start_sample >= total_samples or num_samples <= 0:
        continue
    
    t = np.arange(num_samples, dtype=np.float64) / sample_rate
    f = freq(midi_num)
    vol = velocity / 127.0
    
    # Piano envelope
    attack = 0.002
    decay = 0.05 + (max(0, 60 - midi_num) / 60.0) * 0.1
    sustain_level = 0.25
    release = min(dur_sec * 0.3, 0.2)
    sustain_end = dur_sec - release
    
    env = np.zeros(num_samples, dtype=np.float64)
    
    # Attack
    attack_mask = t < attack
    env[attack_mask] = t[attack_mask] / attack
    
    # Decay
    decay_mask = (t >= attack) & (t < attack + decay)
    if np.any(decay_mask):
        env[decay_mask] = 1.0 - (1.0 - sustain_level) * ((t[decay_mask] - attack) / max(decay, 0.001))
    
    # Sustain
    sustain_mask = (t >= attack + decay) & (t < sustain_end)
    if np.any(sustain_mask):
        tremolo = 1.0 + 0.02 * np.sin(t[sustain_mask] * 8.0)
        env[sustain_mask] = sustain_level * tremolo
    
    # Release
    release_mask = t >= sustain_end
    if np.any(release_mask):
        release_t = (t[release_mask] - sustain_end) / max(release, 0.01)
        env[release_mask] = sustain_level * np.maximum(0, 1.0 - release_t)
    
    # Generate waveform (sum of harmonics)
    sample_val = np.zeros(num_samples, dtype=np.float64)
    for harmonic, amplitude in HARMONICS:
        sample_val += amplitude * np.sin(2 * np.pi * f * harmonic * t)
    
    sample_val *= env * vol * 0.4
    
    audio[start_sample:start_sample + num_samples] += sample_val

print("Mixing and normalizing...")
# Normalize
max_val = np.max(np.abs(audio))
if max_val > 0:
    audio /= max_val
    audio *= 0.95  # Leave headroom

# Convert to stereo
stereo = np.column_stack([audio, audio])

# Convert to 16-bit
stereo_int = (stereo * 32767).astype(np.int16)

print("Writing WAV file...")
with wave.open(wav_path, 'wb') as w:
    w.setnchannels(2)
    w.setsampwidth(2)
    w.setframerate(sample_rate)
    # Write in chunks
    chunk_size = sample_rate * 2  # 1 second chunks
    for i in range(0, len(stereo_int), chunk_size):
        w.writeframes(stereo_int[i:i+chunk_size].tobytes())

file_size = os.path.getsize(wav_path)
print(f"WAV file created: {wav_path}")
print(f"File size: {file_size:,} bytes ({file_size/1024:.0f} KB)")

# Convert to MP3 using FFmpeg
print("\nConverting to MP3...")
try:
    result = subprocess.run([
        "ffmpeg", "-i", wav_path, 
        "-codec:a", "libmp3lame", "-qscale:a", "2", 
        "-ab", "192k", "-y", mp3_path
    ], capture_output=True, text=True, timeout=120)
    if os.path.exists(mp3_path):
        print(f"MP3 file created: {mp3_path}")
        print(f"MP3 file size: {os.path.getsize(mp3_path):,} bytes ({os.path.getsize(mp3_path)/1024:.0f} KB)")
    else:
        print(f"FFmpeg error: {result.stderr[-500:]}")
except FileNotFoundError:
    print("FFmpeg not found for MP3 conversion")
except Exception as e:
    print(f"MP3 conversion error: {e}")

print("\nDone!")
