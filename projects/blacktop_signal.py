"""Produce Blacktop Signal, an original trap instrumental and animated night drive."""

import argparse
import math
import os
from pathlib import Path
import subprocess

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from scipy.signal import butter, sosfilt
import soundfile as sf


BPM, BARS, RATE, FPS = 146, 64, 48000, 24
BEAT = 60 / BPM
LENGTH = BARS * 4 * BEAT
SIZE = 960, 540
TITLE = 'Blacktop Signal'
ROOTS = (29, 25, 32, 27)
CHORDS = ((53, 60, 63, 68), (49, 56, 60, 65), (51, 56, 60, 63), (51, 58, 62, 65))
HOOK = (
    ((0, 77), (0.75, 72), (1.5, 75), (2.75, 68), (3.5, 72)),
    ((0, 77), (1.25, 72), (2, 68), (3.25, 73)),
    ((0, 75), (0.75, 72), (1.75, 70), (2.75, 68)),
    ((0, 74), (1, 77), (2.5, 70), (3.5, 67)),
)


def hz(note):
    return 440 * 2 ** ((note - 69) / 12)


def clock(seconds):
    return np.arange(round(RATE * seconds), dtype=np.float64) / RATE


def envelope(time, attack, decay, release):
    return np.minimum(time / attack, 1) * np.exp(-time * decay) * np.minimum((time[-1] - time) / release, 1)


def add(bus, signal, beat, level, pan=0):
    start = round(beat * BEAT * RATE)
    stop = min(start + len(signal), len(bus))
    if stop > start:
        angle = (pan + 1) * math.pi / 4
        bus[start:stop] += signal[:stop - start, None] * (level * np.array([math.cos(angle), math.sin(angle)]))


def noise_band(rng, time, frequencies, kind):
    return sosfilt(butter(2, frequencies, fs=RATE, btype=kind, output='sos'), rng.standard_normal(len(time)))


def bell(note, bright):
    t = clock(0.92)
    phase = 2 * np.pi * hz(note) * t
    strike = np.sin(phase + 1.9 * np.exp(-12 * t) * np.sin(phase * 2.005))
    body = 0.65 * strike + 0.23 * np.sin(phase * 1.999) + 0.12 * np.exp(-11 * t) * np.sin(phase * 3.02)
    return body * envelope(t, 0.007, 4 if bright else 6, 0.06)


def bass(note, beats, slide):
    t = clock(beats * BEAT)
    frequency = hz(note) * (1 + 0.22 * np.exp(-52 * t))
    if slide:
        frequency *= np.exp2(slide * np.clip((t - t[-1] + 0.12) / 0.12, 0, 1) / 12)
    phase = 2 * np.pi * np.cumsum(frequency) / RATE
    return np.tanh(1.5 * (np.sin(phase) + 0.12 * np.sin(2 * phase))) * envelope(t, 0.012, 1.4, 0.06)


def make_audio(path):
    rng = np.random.default_rng(2801)
    music = np.zeros((round(LENGTH * RATE), 2))
    drums = np.zeros_like(music)

    t = clock(0.24)
    phase = 2 * np.pi * (48 * t + 112 * (1 - np.exp(-39 * t)) / 39)
    kick = (np.sin(phase) + 0.24 * np.exp(-13 * t) * np.sin(phase * 2)) * envelope(t, 0.002, 16, 0.04)
    t = clock(0.25)
    clap = noise_band(rng, t, (1050, 8100), 'bandpass')
    flam = sum(np.exp(-145 * np.maximum(0, t - offset)) * (t >= offset) for offset in (0, 0.012, 0.025))
    clap = (clap * (flam * 0.44 + np.exp(-24 * t) * 0.37) + 0.22 * np.sin(2 * np.pi * 185 * t)
            * np.exp(-33 * t)) * envelope(t, 0.002, 4, 0.04)
    t = clock(0.18)
    hat = noise_band(rng, t, 7600, 'highpass') * envelope(t, 0.001, 55, 0.03)
    open_hat = noise_band(rng, t, 4600, 'highpass') * envelope(t, 0.003, 15, 0.04)
    t = clock(0.2)
    metal = (np.sin(2 * np.pi * 916 * t) + 0.33 * np.sin(2 * np.pi * 1421 * t)) * envelope(t, 0.002, 36, 0.03)
    t = clock(4 * BEAT)
    rise = noise_band(rng, t, (460, 4100), 'bandpass') * (t / t[-1]) ** 2.8
    rise *= np.minimum((t[-1] - t) / 0.045, 1)
    pad_time = clock(5 * BEAT)
    voice_time = clock(0.56)

    for bar in range(BARS):
        position = bar * 4
        chord = bar % 4
        drop = 8 <= bar < 24 or 32 <= bar < 60
        peak = 48 <= bar < 60
        breakdown = 24 <= bar < 32

        for part, note in enumerate(CHORDS[chord]):
            p = 2 * np.pi * hz(note) * pad_time
            wobble = 0.18 * np.sin(2 * np.pi * (0.91 + part / 8) * pad_time)
            strings = (0.56 * np.sin(p * 0.997 + wobble) + 0.35 * np.sin(p * 1.004 - wobble)
                       + 0.11 * np.sin(p * 2.01 + 2 * wobble))
            pad = strings * envelope(pad_time, 0.33, 0.13, 0.43)
            add(music, pad, position, 0.080 if breakdown else 0.061, (-0.72, 0.55, -0.38, 0.78)[part])

        motif = HOOK[chord]
        for index, (step, note) in enumerate(motif):
            if breakdown and index in (1, 3):
                continue
            pluck = bell(note - (12 if breakdown else 0), drop)
            pan = (-0.25, 0.23, -0.12, 0.35, -0.42)[index]
            add(music, pluck, position + step, 0.245 if peak else 0.191, pan)
            add(music, pluck, position + step + 0.75, 0.054, -0.7)
            add(music, pluck, position + step + 1.5, 0.028, 0.71)

        if bar in (3, 7, 23, 31, 47, 59):
            add(music, rise, position, 0.21, -0.27)
        if bar % 4 in (0, 3):
            # A pitched, wordless formant synth answers the lead.
            pitch = hz(CHORDS[chord][2] - 5)
            cycle = (voice_time * pitch + 0.09 * np.sin(2 * np.pi * 4.7 * voice_time)) * 2 * np.pi
            formant = 840 + 430 * np.sin(2 * np.pi * 1.6 * voice_time)
            voice = sum(np.sin(cycle * k) * np.exp(-((k * pitch - formant) / 310) ** 2) / math.sqrt(k)
                        for k in range(2, 13))
            voice *= envelope(voice_time, 0.045, 3.3, 0.11)
            add(music, voice, position + 2.75, 0.18, 0.49)
            add(music, voice, position + 3.5, 0.08, -0.63)

        if drop:
            kick_steps = ((0, 0.75, 1.5, 2.75, 3.5), (0, 1.25, 2.5, 3.25),
                          (0, 0.5, 1.75, 2.75, 3.5), (0, 1, 2.25, 3, 3.75))[chord]
            for index, step in enumerate(kick_steps):
                add(drums, kick, position + step, 0.69 if index == 0 else 0.55)
            bass_steps = (0, 1.5, 2.75) if chord in (0, 2) else (0, 1.25, 3)
            for index, (start, end) in enumerate(zip(bass_steps, (*bass_steps[1:], 4))):
                slide = 12 if index == 2 and bar % 8 in (3, 7) else 0
                add(drums, bass(ROOTS[chord], end - start - 0.045, slide), position + start, 0.51)
            add(drums, clap, position + 2, 0.48)
            add(drums, clap, position + 2.025, 0.14, -0.55)
            add(drums, clap, position + 2.046, 0.10, 0.55)
            add(drums, open_hat, position + 0.5, 0.115, 0.48)
            add(drums, metal, position + 3.25 + (0.25 if chord == 2 else 0), 0.13, -0.54)
            for step in range(8):
                add(drums, hat, position + step / 2 + 0.014 * (step % 2), 0.095 if step % 2 else 0.137,
                    (-0.4, -0.13, 0.16, 0.42)[step % 4])
            if chord in (1, 3) or peak:
                for index in range(4):
                    add(drums, hat, position + 3 + index / 8, 0.13 - index * 0.011, -0.48 + index * 0.29)
        elif bar in (5, 6, 7, 28, 29, 30, 31):
            add(drums, bass(ROOTS[chord], 2.8, 0), position, 0.29)
            add(drums, metal, position + 2, 0.09, 0.35)
            if bar in (7, 31):
                for index in range(8):
                    add(drums, clap, position + 2 + index * 0.25, 0.08 + 0.031 * index, (index % 3 - 1) * 0.3)

    master = np.tanh((music + drums) * 1.18)
    fade_in = round(0.13 * RATE)
    fade_out = round(2.6 * RATE)
    master[:fade_in] *= np.linspace(0, 1, fade_in)[:, None]
    master[-fade_out:] *= np.linspace(1, 0, fade_out)[:, None]
    master *= 10 ** (-1.65 / 20) / np.max(np.abs(master))
    sf.write(path, master, RATE, subtype='PCM_24')


def night_backdrop(mode):
    w, h = SIZE
    colors = ((12, 18, 34), (15, 12, 38), (8, 18, 24))
    sky = np.zeros((h, w, 3), dtype=np.float64)
    y, x = np.ogrid[:h, :w]
    horizon = np.exp(-((y - h * 0.55) / (h * 0.25)) ** 2)
    glow = np.exp(-(((x - w * 0.69) / (w * 0.62)) ** 2 + ((y - h * 0.35) / (h * 0.34)) ** 2))
    sky[:] = np.array(colors[mode]) + glow[..., None] * (42, 10, 20) + horizon[..., None] * (7, 15, 17)
    rng = np.random.default_rng(429 + mode)
    sky += rng.normal(0, 1.0, (h, w, 1))
    base = Image.fromarray(np.uint8(np.clip(sky, 0, 255)))

    light = Image.new('RGB', SIZE)
    glow_draw = ImageDraw.Draw(light)
    moon_x, moon_y, radius = (663, 169, 118) if mode == 0 else (308, 135, 94)
    if mode < 2:
        glow_draw.ellipse((moon_x - radius, moon_y - radius, moon_x + radius, moon_y + radius), fill=(124, 30, 25))
        base = Image.fromarray(np.uint8(np.minimum(255, np.asarray(base, dtype=np.int16)
                                                   + np.asarray(light.filter(ImageFilter.GaussianBlur(45))))))
        draw = ImageDraw.Draw(base)
        for row in range(-radius, radius):
            width = math.sqrt(radius**2 - row**2)
            shade = (row + radius) / (2 * radius)
            color = (int(220 - 84 * shade), int(83 - 47 * shade), int(63 - 22 * shade))
            if row > 18 and row % 10 > 6:
                continue
            draw.line((moon_x - width, moon_y + row, moon_x + width, moon_y + row), fill=color)
    else:
        draw = ImageDraw.Draw(base)

    for layer in range(3):
        ground = 300 + layer * 13
        pos = -20
        while pos < w:
            span = int(rng.integers(15, 55)) * (1 + layer)
            height = int(rng.integers(32, 113)) + 8 * layer
            roof = ground - height
            right = pos + span - 4
            fill = (26 - layer * 7, 28 - layer * 7, 43 - layer * 9)
            draw.rectangle((pos, roof, right, ground), fill=fill)
            draw.line((pos, roof, right, roof), fill=(52 - layer * 10, 40 - layer * 6, 54 - layer * 7))
            if rng.random() < 0.25:
                draw.line((pos + span // 2, roof, pos + span // 2, roof - 12), fill=(46, 35, 49))
                draw.point((pos + span // 2, roof - 12), fill=(236, 66, 68))
            for wx in range(pos + 5, right - 2, 7 + layer * 2):
                for wy in range(roof + 8, ground - 4, 9):
                    choice = rng.random()
                    if choice < 0.29:
                        tint = (111, 60, 62) if choice < 0.09 else (39, 78, 88)
                        draw.rectangle((wx, wy, wx + 2, wy + 1 + layer), fill=tint)
            pos += span
    draw.rectangle((0, 327, w, h), fill=(8, 11, 19))
    if mode == 1:
        for index in range(1450):
            yy = int(rng.integers(328, h))
            xx = int(rng.integers(0, w))
            streak = int(rng.integers(1, 20 + (yy - 325) // 3))
            color = ((27, 24, 38), (46, 23, 35), (13, 36, 45))[index % 3]
            draw.line((xx, yy, xx + streak, yy), fill=color)
    return base


def font_file(bold=False):
    location = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts'
    windows_font = location / ('arialbi.ttf' if bold else 'bahnschrift.ttf')
    return windows_font if windows_font.is_file() else ('DejaVuSans-BoldOblique.ttf' if bold else 'DejaVuSans.ttf')


def title_overlay():
    overlay = Image.new('RGBA', SIZE)
    draw = ImageDraw.Draw(overlay)
    big = ImageFont.truetype(str(font_file(True)), 82)
    small = ImageFont.truetype(str(font_file()), 17)
    draw.rectangle((45, 100, 335, 102), fill=(241, 83, 71, 240))
    draw.text((46, 72), 'O R I G I N A L   M U S I C   V I D E O', font=small, fill=(248, 185, 160, 255))
    draw.text((35, 101), 'BLACKTOP', font=big, fill=(11, 12, 20, 240), stroke_width=3)
    draw.text((32, 98), 'BLACKTOP', font=big, fill=(248, 228, 211, 255))
    draw.text((34, 174), 'SIGNAL', font=big, fill=(255, 105, 87, 255), stroke_width=1, stroke_fill=(57, 23, 35, 255))
    return overlay, overlay.getbbox()


def moving_road(draw, time, mode, beat_glow):
    w, h = SIZE
    vanishing_x = 475 + 58 * math.sin(time * 0.43)
    vanishing_y = 315 if mode == 0 else 280
    draw.polygon(((vanishing_x - 14, vanishing_y), (vanishing_x + 14, vanishing_y),
                  (w + 50, h), (-50, h)), fill=(19, 21, 31))
    for edge in (-1, 1):
        end = vanishing_x + edge * 520
        draw.line((vanishing_x, vanishing_y, end, h), fill=(65, 47, 56), width=3)
        draw.line((vanishing_x, vanishing_y, vanishing_x + edge * 447, h), fill=(61, 56, 68), width=2)

    for mark in range(12):
        depth = (mark / 12 + time * 0.56) % 1
        inner = depth**2
        outer = min(1, depth + 0.045)**2
        yin, yout = (vanishing_y + (h - vanishing_y) * factor for factor in (inner, outer))
        for edge in (-1, 1):
            xin, xout = (vanishing_x + edge * 147 * factor for factor in (inner, outer))
            draw.polygon(((xin - 2 * inner, yin), (xin + 2 * inner, yin),
                          (xout + 5 * outer, yout), (xout - 5 * outer, yout)), fill=(135, 105, 96))

    for lamp in range(10):
        depth = ((lamp / 10 + time * 0.33) % 1)**2
        y = vanishing_y + (h - vanishing_y) * depth
        for edge in (-1, 1):
            x = vanishing_x + edge * 483 * depth
            tall = (174 if mode == 0 else 140) * depth
            if mode == 0:
                draw.line((x, y, x, y - tall, x - edge * tall * 0.28, y - tall - 3),
                          fill=(73, 54, 68), width=max(1, int(4 * depth)))
                x -= edge * tall * 0.28
            size = max(1, 13 * depth)
            cy = y - tall
            tint = (246, 99, 74) if edge == 1 else (76, 185, 191)
            draw.ellipse((x - size, cy - size / 3, x + size, cy + size / 3), fill=tint)
        if mode == 2:
            left, right = vanishing_x - 483 * depth, vanishing_x + 483 * depth
            crest = cy - 142 * depth
            shade = int(41 + 20 * beat_glow * depth)
            draw.line((left, y, left, cy, vanishing_x - 300 * depth, crest,
                       vanishing_x + 300 * depth, crest, right, cy, right, y),
                      fill=(shade, shade - 2, shade + 12), width=max(1, int(8 * depth)))


def coupe(draw, time, pulse):
    x = 533 + 35 * math.sin(time * 0.51)
    y = 437 + 4 * math.sin(time * 1.13)
    draw.ellipse((x - 160, y + 24, x + 158, y + 54), fill=(9, 11, 17))
    for offset in (-100, 100):
        draw.rounded_rectangle((x + offset - 17, y + 8, x + offset + 17, y + 38), 6, fill=(7, 9, 15))
    draw.polygon(((x - 130, y + 5), (x - 116, y - 24), (x - 72, y - 33), (x - 39, y - 55),
                  (x + 42, y - 55), (x + 79, y - 33), (x + 119, y - 26), (x + 132, y + 5),
                  (x + 114, y + 27), (x - 115, y + 27)), fill=(17, 22, 33), outline=(96, 93, 108), width=2)
    draw.polygon(((x - 70, y - 31), (x - 37, y - 50), (x + 39, y - 50), (x + 70, y - 31)),
                 fill=(29, 37, 53), outline=(73, 82, 96))
    draw.line((x - 118, y + 8, x + 120, y + 8), fill=(54, 58, 72), width=2)
    draw.rectangle((x - 21, y + 4, x + 21, y + 17), fill=(125, 110, 99))
    for side in (-1, 1):
        tx = x + side * 84
        draw.rounded_rectangle((tx - 29, y - 14, tx + 29, y - 2), 4, fill=(int(212 + 43 * pulse), 42, 58))
        draw.line((tx - 25, y - 10, tx + 25, y - 10), fill=(250, 123, 105), width=2)
        draw.polygon(((tx - 27, y + 34), (tx + 28, y + 34), (tx + 47, y + 63), (tx - 47, y + 63)),
                     fill=(48, 20, 31))


def render_frame(time, backdrops, rain, title, still=False):
    beat = time / BEAT
    bar = int(beat / 4)
    shot = (0, 2, 0, 1, 2, 0, 2, 1)[min(7, bar // 8)]
    if still:
        shot = 0
    pulse = math.exp(-7 * (beat % 1))
    frame = backdrops[shot].copy()
    draw = ImageDraw.Draw(frame)
    if shot != 1:
        moving_road(draw, time, shot, pulse)
        coupe(draw, time, pulse)
    else:
        # Foreground rail and reflected navigation lights.
        draw.line((0, 439, 960, 537), fill=(38, 29, 40), width=7)
        draw.line((0, 431, 960, 529), fill=(69, 53, 61), width=2)
        for index in range(11):
            x = (index * 104 - time * 21) % 1100 - 60
            y = 439 + x * 0.103
            draw.line((x, y, x, 540), fill=(35, 27, 39), width=6)
    for x, y, speed, length, color in rain:
        px = (x - time * speed * 0.16) % SIZE[0]
        py = (y + time * speed) % SIZE[1]
        draw.line((px, py, px - length * 0.35, py + length), fill=color, width=1)
    draw.rectangle((0, 0, SIZE[0], 17), fill=(8, 10, 16))
    draw.rectangle((0, SIZE[1] - 18, SIZE[0], SIZE[1]), fill=(8, 10, 16))
    if still or bar < 5 or bar >= 61:
        image, bbox = title
        layer = image.crop(bbox)
        opacity = 1 if still else min(1, time / 0.6, max(0, LENGTH - time) / 0.8)
        if not still and bar < 5:
            opacity *= min(1, max(0, 5 * 4 * BEAT - time) / 0.7)
        frame.paste(layer, bbox[:2], layer.getchannel('A').point(lambda a: int(a * opacity)))
    if not still and (time < 0.38 or time > LENGTH - 1.05):
        brightness = max(0, min(1, time / 0.38, (LENGTH - time) / 1.05))
        frame = Image.blend(Image.new('RGB', SIZE), frame, brightness)
    return frame


def make_video(folder, audio):
    backdrops = [night_backdrop(mode) for mode in range(3)]
    rng = np.random.default_rng(667)
    rain = [(rng.uniform(0, 960), rng.uniform(0, 540), rng.uniform(100, 470), rng.uniform(2, 16),
             ((46, 56, 73), (68, 66, 83), (44, 69, 77))[index % 3]) for index in range(104)]
    title = title_overlay()
    thumbnail = render_frame(2.15, backdrops, rain, title, still=True).resize((1280, 720), Image.Resampling.LANCZOS)
    thumbnail.save(folder / 'Blacktop Signal - Thumbnail.jpg', quality=95)
    video = folder / 'Blacktop Signal.mp4'
    command = ['ffmpeg', '-nostdin', '-v', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', '960x540',
               '-r', str(FPS), '-i', '-', '-i', str(audio), '-vf', 'scale=1280:720:flags=lanczos',
               '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '18', '-pix_fmt', 'yuv420p',
               '-c:a', 'aac', '-b:a', '256k', '-movflags', '+faststart', str(video)]
    with subprocess.Popen(command, stdin=subprocess.PIPE) as process:
        try:
            for index in range(round(LENGTH * FPS)):
                if index % (FPS * 20) == 0:
                    print(f'Rendering {index // FPS}s / {LENGTH:.0f}s', flush=True)
                frame = render_frame(index / FPS, backdrops, rain, title)
                process.stdin.write(frame.tobytes())
        finally:
            process.stdin.close()
        if process.wait():
            raise RuntimeError('FFmpeg could not encode the video')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('runs/blacktop-signal'))
    args = parser.parse_args()
    folder = args.output.resolve()
    folder.mkdir(parents=True, exist_ok=False)
    audio = folder / f'{TITLE}.wav'
    print(f'Producing {TITLE} at {BPM} BPM', flush=True)
    make_audio(audio)
    make_video(folder, audio)
    print(f'Saved WAV, MP4, and thumbnail in {folder}', flush=True)


if __name__ == '__main__':
    main()
