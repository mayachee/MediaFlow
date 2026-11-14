from pathlib import Path
import struct

data = open(Path(__file__).resolve().parent / "soudeni_aya_moghraman_cover_orchestrated.mid", "rb").read()
ppq = struct.unpack(">H", data[12:14])[0]
print(f"PPQ: {ppq}")

idx = 14
while idx < len(data):
    b = data[idx]
    if b == 0xFF:  # Meta event
        idx += 1
        mtype = data[idx]; idx += 1
        length = 0
        while True:
            b2 = data[idx]; idx += 1
            length = (length << 7) | (b2 & 0x7F)
            if not (b2 & 0x80): break
        
        if mtype == 0x51 and length == 3:
            tb = data[idx:idx+3]
            tempo = (tb[0]<<16)|(tb[1]<<8)|tb[2]
            bpm = 60000000/tempo
            print(f"Tempo: {bpm:.1f} BPM ({tempo} us/beat)")
        idx += length
    elif b >= 0x80:
        status = b
        idx += 1
        # Read delta
        delta = 0
        while True:
            b2 = data[idx]; idx += 1
            delta = (delta << 7) | (b2 & 0x7F)
            if not (b2 & 0x80): break
        
        if status == 0xFF:
            mtype = data[idx]; idx += 1
            length = 0
            while True:
                b2 = data[idx]; idx += 1
                length = (length << 7) | (b2 & 0x7F)
                if not (b2 & 0x80): break
            if mtype == 0x51 and length == 3:
                tb = data[idx:idx+3]
                tempo = (tb[0]<<16)|(tb[1]<<8)|tb[2]
                bpm = 60000000/tempo
                print(f"Tempo: {bpm:.1f} BPM ({tempo} us/beat)")
            idx += length
        else:
            idx += 1
            if status & 0xF0 in (0x90, 0x80, 0xB0, 0xE0): idx += 2
            elif status & 0xF0 in (0xC0, 0xD0): idx += 1
    else:
        idx += 1
