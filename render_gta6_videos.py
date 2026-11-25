"""Render one H.264/AAC video per track using the GTA6 artwork and song CSV."""
import argparse
import csv
import json
import math
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import random
import re
import shutil
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw, ImageFont

from modules.music_video_generator.src.image_processor import ImageProcessor


ROOT = Path(__file__).resolve().parent
SIZE = (1920, 1080)
FPS = 25
SHOT_SECONDS = 7
TITLE_SECONDS = 5
RHYNO_ID = "3Ev1PQEm7ns"
RHYNO_ART = "Gemini_Generated_Image_qk4ln6qk4ln6qk4l.jpg"
GTA_V_ART = "Gemini_Generated_Image_s7rjoes7rjoes7rj.jpg"


def run(tool, *args):
    result = subprocess.run([tool, *map(str, args)], capture_output=True, check=False)
    if result.returncode:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace").strip())
    return result.stdout


def probe(ffprobe, path):
    return json.loads(run(ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", path))


def load_tracks():
    audio_by_id = {}
    for path in (ROOT / "gta6-songs").glob("*.mp3"):
        match = re.search(r"\[([\w-]{11})\]$", path.stem, re.ASCII)
        if match:
            video_id = match[1]
            if video_id in audio_by_id:
                raise ValueError(f"Multiple audio files for video ID {video_id}")
            audio_by_id[video_id] = path

    with (ROOT / "youtube-song-links.csv").open(encoding="utf-8-sig", newline="") as source:
        for index, row in enumerate(csv.DictReader(source), 1):
            video_id = row["VideoUrl"].partition("?v=")[2]
            artist, title = row["Song"].split(" \u2013 ", 1)
            title = re.sub(
                r"\s+\((?:trailer \d+|launch trailer and soundtrack|pre-load video and soundtrack|original score)\)$",
                "", title, flags=re.IGNORECASE,
            )
            if video_id not in audio_by_id:
                raise ValueError(f"Missing MP3 for {row['Song']}")
            stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", f"{index:02d}. {artist} - {title}").strip(" .")
            yield index, video_id, artist, title, audio_by_id[video_id], stem


def title_card(image, artist, title):
    card = image.convert("RGBA")
    ramp = Image.new("L", (1, SIZE[1]))
    ramp.putdata([round(233 * max(0, (y - 455) / (SIZE[1] - 455)) ** 1.08) for y in range(SIZE[1])])
    shade = Image.new("RGBA", SIZE, (12, 9, 23))
    shade.putalpha(ramp.resize(SIZE))
    card = Image.alpha_composite(card, shade).convert("RGB")
    draw = ImageDraw.Draw(card)
    fonts = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"

    def fit_font(value, filename, start_size):
        for size in range(start_size, 14, -2):
            font = ImageFont.truetype(str(fonts / filename), size)
            if draw.textlength(value, font=font) <= 1700:
                return font
        raise ValueError(f"Title card text is too long: {value}")

    left = 106
    draw.rectangle((left, 755, left + 88, 762), fill="#ff647f")
    draw.text((left, 860), title, font=fit_font(title, "arialbd.ttf", 80),
              fill="#fff7f2", anchor="ls", stroke_width=1, stroke_fill="#211326")
    draw.text((left + 3, 926), artist, font=fit_font(artist, "arial.ttf", 42),
              fill="#ffe0e6", anchor="ls", stroke_width=1, stroke_fill="#211326")
    return card


def encode_clip(ffmpeg, image, target, seconds, motion=None):
    source = target.with_suffix(".jpg")
    image.save(source, quality=95, subsampling=0)
    filters = f"fps={FPS}" if motion is None else motion
    run(ffmpeg, "-nostdin", "-v", "error", "-filter_threads", "1",
        "-loop", "1", "-framerate", "1", "-i", source, "-vf", filters + ",setsar=1,format=yuv420p",
        "-frames:v", seconds * FPS, "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-threads", "1", "-bf", "0", "-g", str(2 * FPS), "-an", "-y", target)
    source.unlink()


def check_video(ffprobe, target, duration):
    info = probe(ffprobe, target)
    streams = {stream["codec_type"]: stream for stream in info["streams"]}
    video, audio = streams.get("video", {}), streams.get("audio", {})
    if (video.get("codec_name") != "h264" or audio.get("codec_name") != "aac"
            or (video.get("width"), video.get("height")) != SIZE
            or any(abs(float(stream.get("duration", 0)) - duration) > 0.15 for stream in (video, audio))):
        raise ValueError(f"Wrong format or duration for {target.name}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--track", type=int, help="Render a single numbered track")
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--replace-existing", action="store_true", help="Replace existing exports after verification")
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error("--jobs must be positive")
    tools = [shutil.which(tool) for tool in ("ffmpeg", "ffprobe")]
    if not all(tools):
        raise RuntimeError("FFmpeg and FFprobe are required on PATH.")
    ffmpeg, ffprobe = tools
    tracks = list(load_tracks())
    tracks = [track for track in tracks if args.track is None or track[0] == args.track]
    if not tracks:
        parser.error("No matching track in the CSV")

    assets = ROOT / "GTA6"
    images = sorted(path for path in assets.iterdir()
                    if path.is_file() and not path.name.startswith(".") and path.name != GTA_V_ART
                    and path.suffix.lower() in {".jpg", ".jpeg", ".png"})
    if len(images) < 2:
        raise ValueError("GTA6 needs at least two artwork images.")
    rhyno_cover = next((i for i, path in enumerate(images) if path.name == RHYNO_ART), None)
    general_art = [i for i in range(len(images)) if i != rhyno_cover]
    if len(general_art) < 2:
        raise ValueError("GTA6 needs at least two shared artwork images.")
    output = assets / "videos"
    output.mkdir(exist_ok=True)
    processor = ImageProcessor(*SIZE)

    def prepared(path):
        image = processor.load_and_prepare(str(path), enhance=False)
        if image is None:
            raise ValueError(f"Could not open {path.name}")
        return image

    with tempfile.TemporaryDirectory(prefix=".render-", dir=output) as work_dir:
        work = Path(work_dir)
        shots = [work / f"shot-{i:02d}.mp4" for i in range(len(images))]

        def make_shot(index):
            motion = processor.generate_zoompan_filter(
                SHOT_SECONDS, fps=FPS, motion=("zoom_in" if index % 2 == 0 else "zoom_out"),
                zoom_factor=1.07, frames_per_image=SHOT_SECONDS * FPS,
            )
            encode_clip(ffmpeg, prepared(images[index]), shots[index], SHOT_SECONDS, "scale=2880:1620," + motion)

        pending = []
        for track in tracks:
            index, _, _, _, audio, stem = track
            duration = float(probe(ffprobe, audio)["format"]["duration"])
            target = output / (stem + ".mp4")
            if target.exists() and not args.replace_existing:
                check_video(ffprobe, target, duration)
                print(f"Verified existing {index:02d}  {target.name}", flush=True)
            else:
                pending.append((track, target, duration))
        if not pending:
            return

        with ThreadPoolExecutor(max_workers=args.jobs) as pool:
            print(f"Preparing {len(images)} reusable animated shots", flush=True)
            list(pool.map(make_shot, range(len(images))))

            def render(item):
                (index, video_id, artist, title, audio, _), target, duration = item
                rng = random.Random(video_id)
                order = general_art.copy()
                rng.shuffle(order)
                if video_id == RHYNO_ID and rhyno_cover is not None:
                    order.insert(0, rhyno_cover)
                intro = work / f"intro-{index:02d}.mp4"
                encode_clip(ffmpeg, title_card(prepared(images[order[0]]), artist, title), intro, TITLE_SECONDS)
                order = order[1:] + order[:1]
                shot_count = max(1, math.ceil((duration - TITLE_SECONDS + 1 / FPS) / SHOT_SECONDS))
                segments = [intro] + [shots[order[i % len(order)]] for i in range(shot_count)]
                playlist = work / f"track-{index:02d}.ffconcat"
                playlist.write_text("".join(f"file '{segment.name}'\n" for segment in segments), encoding="ascii")
                partial = work / f"track-{index:02d}.mp4"
                run(ffmpeg, "-nostdin", "-v", "error", "-f", "concat", "-safe", "1", "-i", playlist,
                    "-i", audio, "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac",
                    "-b:a", "256k", "-t", f"{duration:.6f}", "-movflags", "+faststart",
                    "-metadata", f"title={title}", "-metadata", f"artist={artist}", "-y", partial)
                check_video(ffprobe, partial, duration)
                if args.replace_existing:
                    partial.replace(target)
                else:
                    partial.rename(target)
                print(f"Rendered {index:02d}  {target.name}  ({duration:.1f}s)", flush=True)

            list(pool.map(render, pending))


if __name__ == "__main__":
    sys.stdout.reconfigure(errors="backslashreplace")
    main()
