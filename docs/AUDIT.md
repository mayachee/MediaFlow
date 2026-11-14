# Workspace audit — 12 November 2026

The audit examined first-party Python/PowerShell sources and the main file
handoffs. It excluded vendor source, dependency folders, editor worktrees, and
credentials from source execution. Existing user changes and deleted tracked
files were preserved. Media assets were not moved or removed.

## Verified results

- All first-party Python sources passed AST syntax parsing; see the current
  count and file list in [health-check.json](health-check.json).
- All nine PowerShell scripts passed the PowerShell parser.
- Ten offline regression tests in `tests/`, plus the workflow regression with
  success/render-failure/quality-failure subcases, passed.
- Real local rendering covered mixed 44.1 kHz stereo / 22.05 kHz mono inputs,
  original/slow/reverse effects, single-song multiple-image scheduling, and the
  batch adapter. The refreshed [media-smoke report](media-smoke.json) also records
  the short full-HD motion render and real beat-detection checks.
- Both bundled FluidSynth executables rendered a synthetic MIDI note to WAV.
  Each produced about 3.11 seconds including synth release/reverb tail.
- The standalone PowerShell slow/reverse script produced both WAV outputs from
  a synthetic source; all three subfolder runner help commands worked from root.
- Three existing 256.34-second instrumental files were measured across their
  full duration. No non-finite or near-full-scale samples were found.

| Existing file in `violin-remix/output/` | Format | Integrated loudness | True peak | Comment |
|---|---|---:|---:|---|
| `Aya_Moghraman_pro_instrumental.wav` | 44.1 kHz stereo, PCM 24-bit | −16.05 LUFS | −1.64 dBTP | Technical headroom present |
| `Aya_Moghraman_rhodes_instrumental.wav` | 44.1 kHz stereo, PCM 24-bit | −15.91 LUFS | −1.04 dBTP | Less true-peak margin than the other master |
| `pro_instrumental_premaster.wav` | 44.1 kHz stereo, PCM 16-bit | −16.51 LUFS | −1.61 dBTP | Existing file is 16-bit; future premaster generation now writes float |

These measurements do not establish that the melody, arrangement, vocals, or
artwork are artistically correct. A full listening/watch-through remains necessary.

## Confirmed blocker and environment issues

**Vocal separation is currently blocked.** Running the actual Demucs CLI with
`--help` fails before separation, while importing PyTorch, with Windows error 126
loading `torch/lib/shm.dll` or one of its dependencies. The runtime also prints
that the Microsoft Visual C++ Redistributable is absent. The system DLL probes
did not find the usual `vcruntime140`, `vcruntime140_1`, or `msvcp140` DLLs in
System32. This points to a missing native runtime, but a complete DLL dependency
trace was not performed. Repair the native runtime/PyTorch environment and rerun
the CLI check before downloading models or attempting a full song.

No system installer was run. The separate Demucs environment exists and has
packages, but package presence alone is not a successful runtime test.

**The global Python environment is inconsistent.** `pip check` reports conflicts
between installed Gradio and NumPy/Pandas/WebSockets, plus Matplotlib/PyParsing.
The media smoke tests worked despite those unrelated global conflicts. Use a
dedicated workflow environment and rerun checks there. The direct dependency
snapshot was not validated by reinstalling into a fresh environment.

## Changes made during the audit

| Problem found | Change |
|---|---|
| Main/Make/batch paths referenced deleted `youtube_automation/` | Pointed them to current `automatic_upload/` |
| `.env` loader iterated a `Path` | Read text lines correctly |
| Required-step return values were ignored | Legacy runner stops with nonzero status on search/download/render/upload failure |
| Shell-based invocation was fragile with spaces/apostrophes | Main runner uses subprocess argument lists with `shell=False` |
| Failed or stale video could be uploaded | Main runner checks fresh renderer output; integrated jobs have unique paths |
| `librosa.beat_track` received unsupported `backtrack` | Removed argument; normalized array tempo before formatting |
| Missing duration silently became 180 seconds | Unknown/invalid duration now fails explicitly |
| First detected beat removed the opening; short scenes were stretched to one second | Start at zero and retain exact positive timing intervals |
| Multiple visuals for one song were truncated to one | Preserved the selected scene list |
| Scene failures were logged and skipped | Abort rather than create an incomplete video |
| Batch constructed obsolete `Scene(image_path=...)` | Updated to shared `source_path` interface |
| Mismatched audio formats used concat demuxer/MP3 intermediates | Decode/resample into a compatible stream and use 24-bit WAV playlist intermediates |
| Scene and final encodes used unrelated hardcoded CRF values | Honor configured scene CRF/preset and stream-copy completed scene video during muxing |
| Ken Burns configuration was ignored and helper expression was invalid | Connected a bounded zoompan expression and honored enabled/fade settings |
| `--mp3` could remove audio from a video | Deprecated renderer flag no longer drops the audio stream |
| Nonempty file was the only output check | Added audio/video stream, duration, dimensions, and fps validation before integrated upload |
| Thumbnail error turned an already successful video upload into a failure | Save server ID receipt first; thumbnail failure remains retryable separately |
| Batch deleted local video before writing progress | Atomically persist progress before cleanup |
| Resume keys only used batch number | Use song-content identity; older progress requires reconciliation |
| Downloader ignored error return codes | Report failure to calling process rather than return successful exit status |
| Stereo channels were trimmed independently | Use one shared trim interval; retain the original source file |
| Standalone effects reprocessed generated files in the input directory | Separate WAV output directory, skip generated suffixes, check FFmpeg exit status |
| Violin scripts expected obsolete `output/vocals.wav` path | Shared explicit `VOCAL_SOURCE` resolution and unambiguous stem discovery |
| Structure analysis assumed sample-rate alignment | Resample to analysis rate and reject missing voiced sections |
| Root PowerShell runner hardcoded one machine's path | Use `$PSScriptRoot`; check Python exit statuses |
| Redirected Python warnings aborted the PowerShell runner | Preserve native stderr logs and use the actual process exit code |
| Subfolder PowerShell runners depended on caller's current directory | Scope their working directory with `Push-Location` / `finally` |
| No root ignore rules or centralized checks | Added `.gitignore`, doctor/test/smoke commands, dependency snapshot, and this guide |
| Personal browser automation embedded login passwords | Read four explicit environment variables; fail before opening browser if absent |

## Remaining work and unverified paths

1. Repair and test the Demucs native runtime; then separate a short authorized
   local song and listen for vocal bleed, transient loss, and watery artifacts.
2. Verify YouTube search/download against the intended real inputs. No browser
   session, download, external metadata request, or upload was run in this audit.
   Search selects a first result; it cannot guarantee the correct song/version.
3. Review the Pinterest production entry point and retire the many one-off cookie
   extraction/debugging scripts after choosing an authentication approach. They
   were not executed and are not certified to work against the live service.
4. Regenerate and listen to the full violin/Soudeni productions. Fixed-output
   project stages still share song-specific JSON/stem files, and the simplistic
   TTS/pitch-shift approach is not equivalent to a singing model.
5. Retire duplicate legacy orchestration once callers have migrated. `run_all.py`
   and legacy `all` still scan shared folders; `workflow.py` gives isolated jobs.
   Old Makefile `all` is not designed for parallel `make -j` execution.
6. Review OAuth client tracking and previously embedded passwords separately.
   Ignoring a tracked file does not remove its contents from repository history.
7. Strengthen release management with a fully resolved dependency lock and a
   clean-environment install test. The audit did not upgrade or uninstall packages.
8. Add automatic resume/retention only after defining desired behavior. No
   automatic deletion, bulk relocation, or batch-progress migration occurred.

See [WORKSPACE_GUIDE.md](WORKSPACE_GUIDE.md) for four connection diagrams, file
contracts, the folder catalog, commands, and the maintenance routine.
