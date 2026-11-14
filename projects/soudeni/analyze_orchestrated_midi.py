from pathlib import Path
import struct

data = open(Path(__file__).resolve().parent / "soudeni_aya_moghraman_cover_orchestrated.mid", "rb").read()
ppq = struct.unpack(">H", data[12:14])[0]
print(f"PPQ: {ppq}")

# Check number of tracks
fmt = struct.unpack(">H", data[8:10])[0]
num_tracks = struct.unpack(">H", data[10:12])[0]
print(f"Format: {fmt}, Tracks: {num_tracks}")

idx = 14
for track_num in range(num_tracks):
    if data[idx:idx+4] != b"MTrk":
        print(f"Track {track_num}: Not MTrk")
        break
    
    track_len = struct.unpack(">I", data[idx+4:idx+8])[0]
    idx += 8
    
    max_tick = 0
    current_tick = 0
    tempo_us = 500000
    last_tempo_tick = 0
    note_count = 0
    
    while idx < 14 + 8 + track_len if track_num == 0 else idx < track_len + idx:
        # Read delta
        delta = 0
        while True:
            b = data[idx]; idx += 1
            delta = (delta << 7) | (b & 0x7F)
            if not (b & 0x80): break
        current_tick += delta
        
        b = data[idx]
        if b == 0xFF:
            idx += 1
            mtype = data[idx]; idx += 1
            length = 0
            while True:
                b2 = data[idx]; idx += 1
                length = (length << 7) | (b2 & 0x7F)
                if not (b2 & 0x80): break
            if mtype == 0x51:
                tb = data[idx:idx+3]
                tempo_us = (tb[0]<<16)|(tb[1]<<8)|tb[2]
                bpm = 60000000/tempo_us
            idx += length
        else:
            status = b
            idx += 1
            if status & 0xF0 == 0x90:
                nn = data[idx]; vel = data[idx+1]; idx += 2
                if vel > 0:
                    note_count += 1
                max_tick = max(max_tick, current_tick)
            elif status & 0xF0 == 0x80:
                idx += 2
                max_tick = max(max_tick, current_tick)
            elif status & 0xF0 in (0xB0, 0xE0):
                idx += 2
                max_tick = max(max_tick, current_tick)
            elif status & 0xF0 in (0xC0, 0xD0):
                idx += 1
            elif status == 0xF8 or status == 0xFA or status == 0xFC:
                pass
    
    if tempo_us:
        bpm = 60000000 / tempo_us
        duration_sec = max_tick * tempo_us / (ppq * 1000000)
        print(f"Track {track_num}: notes={note_count}, max_tick={max_tick}, "
              f"duration={duration_sec:.2f}s at {bpm:.1f} BPM")
    
    if track_num == 0:
        idx += track_len - (idx - (14 + 8))
        break
    idx = 14 + 8 + sum(struct.unpack(">I", data[t+4:t+8])[0] for t in range(0, 0)) + track_len if track_num == 0 else idx
