# Try the production tools with demo music

Run these commands from the workspace root. The demo generates an original
eight-second musical phrase and artwork, so you do not need to supply files.
It uses local Python, FFmpeg, NumPy, SoundFile, and Pillow; it does not download
music, load Demucs models, or upload anything.

## One-command demonstration

```powershell
py -3.11 tools/demo_production.py
```

This runs four checks: an editable master, peak normalization, reference
comparison, and a four-second preview video. It prints `PASS` for each successful
check and the paths to the files you can open. Start with
`runs/production-demo/README.md`, which links to the reports and playable outputs.
Inputs are reused only when unchanged; reruns create new jobs and session logs.

## Try one feature at a time

| Command suffix | What to open | What you should see/hear |
|---|---|---|
| `--step prepare` | `runs/production-demo/input/mix.wav` and `reference.wav` | Same music; the reference is about 6.02 dB louder |
| `--step master` | Printed WAV path and export report | Editable float WAV, 48 kHz, normalization off; samples preserved |
| `--step normalize` | Printed WAV path and export report | Sample peak near −2 dBFS; louder audio without limiting |
| `--step compare` | Printed comparison report, then its matched WAV links | About −6.02 LU difference before matching; similar loudness in the listening clips |
| `--step preview` | Printed MP4 path | Four seconds from the music, at 854×480, with artwork and audio |
| `--step video` | Printed MP4 path | Full eight-second 1920×1080 video; takes longer to render |

For example:

```powershell
py -3.11 tools/demo_production.py --step compare
py -3.11 tools/demo_production.py --step preview
py -3.11 tools/demo_production.py --step video
```

The default demonstration omits full-HD rendering to keep the first run short.
Peak normalization controls sample peaks; it is not a true-peak limiter. The
reference is deliberately the same music at a different level, making the
comparison easy to understand before trying different real mixes.

## Use the generated files with the real commands

After preparing the demo inputs, you can run the workflow yourself:

```powershell
py -3.11 tools/demo_production.py --step prepare

.\run.ps1 workflow -Audio "runs/production-demo/input/mix.wav" -Preset master -WavFormat float

.\run.ps1 workflow -Audio "runs/production-demo/input/mix.wav" -Preset master -Normalize loudness -TargetLufs -18

.\run.ps1 workflow -Audio "runs/production-demo/input/mix.wav" -Images "runs/production-demo/input/artwork" -Preset preview -PreviewStart 2 -PreviewSeconds 4
```

Each workflow command prints a new job folder. Open `exports/export-report.md`
for audio measurements, `exports/master.wav` to listen, or
`video/music_video.mp4` to watch. Normalization remains off unless explicitly
selected. Nothing is published by these commands.

For the existing automated regression checks:

```powershell
.\run.ps1 test
py -3.11 tools/smoke_production.py
```

See [PRODUCTION.md](PRODUCTION.md) for presets, normalization choices, and
reference-analysis limitations. If you edit the demo inputs, choose a different
output directory with `--output runs/my-new-demo` rather than overwriting them.
