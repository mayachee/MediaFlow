# Folder organization

The root contains the main entry points. Supporting code, projects, assets,
downloaded software, credentials, and generated results have separate homes.

```text
scripts/
├── README.md                  start here
├── workflow.py                integrated audio/video job runner
├── run.ps1                    Windows command launcher
├── Makefile                   command shortcuts
├── modules/                   reusable media components
│   ├── clip_finder/           online footage discovery and optional downloads
│   ├── automatic_upload/      search, download, metadata, Pinterest
│   ├── automatic_YouTube_upload/  YouTube uploader
│   ├── music_video_generator/ renderer and configuration
│   └── vocal-remover/         separation scripts and Demucs environment
├── pipelines/                 coordination and shared output validation
│   ├── batch_pipeline.py
│   ├── run_all.py             older shared-folder runner
│   ├── media_quality.py
│   └── audio_production.py     exports, measurements, and reference matching
├── projects/
│   └── soudeni/               score, synthesis, vocals, PDF and MIDI utilities
├── assets/
│   └── soundfonts/            shared SoundFont.sf2
├── vendor/                    downloaded dependencies; not project source
│   ├── fluidsynth-bin/
│   ├── archives/              original downloaded ZIP
│   └── javascript/            package files and node_modules
├── config/
│   └── credentials/           local OAuth client configuration; ignored by Git
├── requirements/
│   ├── workflow.txt
│   └── production.txt
├── tools/                     maintenance and smoke checks
│   ├── legacy/                older standalone diagnostics/download helper
│   └── personal/              unrelated browser-login utility
├── tests/                     automated offline tests
├── docs/
│   ├── STRUCTURE.md           this map
│   ├── WORKSPACE_GUIDE.md     detailed connections and diagrams
│   ├── PRODUCTION.md          presets, reference comparison, and optional normalization
│   ├── AUDIT.md               earlier audit and known blockers
│   ├── folder-moves.json      exact old → new path record
│   └── diagrams/              diagram images previously at the root
└── runs/                      generated jobs and their manifests
```

## Commands

The main root commands remain:

```powershell
.\run.ps1 help
.\run.ps1 test
.\run.ps1 doctor
.\run.ps1 smoke
.\run.ps1 workflow -Audio "path/to/song.wav"
py -3.11 workflow.py --help
```

For an individual component, include its new location:

```powershell
.\modules\automatic_upload\run.ps1 help
.\modules\music_video_generator\run.ps1 help
.\modules\vocal-remover\run.ps1 help
py -3.11 pipelines/batch_pipeline.py --help
py -3.11 projects/soudeni/soudeni_piano_cover.py
```

Project scripts can create outputs alongside the project scripts. Supply a
finished project WAV to root `workflow.py --audio` when ready for a video.
Credentials resolve from `config/credentials/client_secret.json`; a component's
own local credential file remains supported. External shortcuts to old paths
need to be updated using `folder-moves.json`.

## Where new files belong

- Reusable processing components go under `modules/`.
- Song-specific scripts and source notes go under their own `projects/<name>/`.
- Shared instrument samples and assets go under `assets/`.
- Third-party executables and installation archives go under `vendor/`.
- Generated integrated jobs go under `runs/`.
- Tests go under `tests/`; environment requirement files go under `requirements/`.
- Explanations and diagrams go under `docs/`; maintenance commands go under `tools/`.
- Local credentials stay under `config/credentials/` and out of version control.

No media was deleted or duplicate dependencies removed as part of organizing.
Some folders mentioned in the earlier audit were already absent at the start of
this reorganization; absent projects were not recreated. Earlier JSON reports
and old run logs are historical snapshots and may contain their original paths.
Virtual environment activation scripts can also contain old absolute paths;
the workspace runners use the environment's Python executable directly.

## Verification after moving

All 33 recorded moves were checked: each destination exists and its old location
is absent. The 11 offline regression tests and seven real media checks passed
after relocation, including the short full-HD render and batch adapter. The
shared FluidSynth installation rendered from `vendor/`, and component CLI/help
entry points ran from their new locations. Current syntax checks passed for
53 Python files and seven PowerShell scripts.

The existing Demucs DLL-loading failure and global Python dependency conflicts
remain visible in `health-check.json`; folder organization does not repair those
environment issues. No external download or upload was performed.
