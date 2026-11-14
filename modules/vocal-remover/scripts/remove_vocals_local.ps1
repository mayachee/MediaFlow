<#
.SYNOPSIS
    Split a local audio/video file into instrumental and vocal stems using demucs.

.DESCRIPTION
    Resolves a source file (explicit path, filename inside $Downloads, or the newest
    media file in $Downloads), converts it to 44.1 kHz stereo wav, runs demucs, then
    writes the results to output\instrumental\ and output\vocals\.

.EXAMPLE
    .\remove_vocals_local.ps1
    Splits the newest file found in ..\automatic_upload\downloads.

.EXAMPLE
    .\remove_vocals_local.ps1 -File "GENER8ION - STORM starring Yung Lean.mp4"
    Splits a specific file from the downloads folder.

.EXAMPLE
    .\remove_vocals_local.ps1 -File "D:\music\song.flac" -Model htdemucs_ft
    Splits an absolute path with a different demucs model.
#>

param(
    [Parameter(Mandatory = $false, Position = 0)]
    [string]$File,

    [string]$Model = "htdemucs",

    [string]$Downloads
)

$ErrorActionPreference = "Stop"

# ffmpeg and demucs write progress to stderr. In Windows PowerShell 5.1 that
# surfaces as a NativeCommandError, so "Stop" would abort a perfectly healthy
# run. Native calls are validated with $LASTEXITCODE and file checks instead.
$ErrorActionPreference = "Continue"

$root       = Split-Path -Parent $PSScriptRoot
$python     = Join-Path $root ".venv\Scripts\python.exe"
$workDir    = Join-Path $root "work"
$outputDir  = Join-Path $root "output"
$instDir    = Join-Path $outputDir "instrumental"
$vocalsDir  = Join-Path $outputDir "vocals"

$MediaExtensions = @(".mp4", ".mkv", ".webm", ".mov", ".avi", ".m4a", ".mp3", ".wav", ".flac", ".ogg")

if ([string]::IsNullOrWhiteSpace($Downloads)) {
    $Downloads = Join-Path (Split-Path -Parent $root) "automatic_upload\downloads"
}

if (-not (Test-Path -LiteralPath $python)) {
    throw "Missing venv at $python. Run: make install  (or  .\run.ps1 install)"
}

New-Item -ItemType Directory -Path $workDir, $instDir, $vocalsDir -Force | Out-Null

function Resolve-Source {
    param([string]$Requested)

    if ([string]::IsNullOrWhiteSpace($Requested)) {
        if (-not (Test-Path -LiteralPath $Downloads)) {
            throw "Downloads folder not found: $Downloads  (override with -Downloads <path>)"
        }
        $newest = Get-ChildItem -LiteralPath $Downloads -File |
            Where-Object { $MediaExtensions -contains $_.Extension.ToLower() } |
            Sort-Object LastWriteTime -Descending |
            Select-Object -First 1
        if (-not $newest) { throw "No media files found in $Downloads" }
        return $newest.FullName
    }

    if (Test-Path -LiteralPath $Requested -PathType Leaf) {
        return (Resolve-Path -LiteralPath $Requested).Path
    }

    $candidate = Join-Path $Downloads $Requested
    if (Test-Path -LiteralPath $candidate -PathType Leaf) {
        return (Resolve-Path -LiteralPath $candidate).Path
    }

    throw "File not found: $Requested  (also tried $candidate)"
}

$src = Resolve-Source -Requested $File
$stem = [IO.Path]::GetFileNameWithoutExtension($src) -replace '[\\/:*?"<>|]', '_'

Write-Host "Source : $src"
Write-Host "Model  : $Model"
Write-Host "Output : $outputDir"

$wav      = Join-Path $workDir "$stem.wav"
$demucsDir = Join-Path $workDir (Join-Path $Model $stem)

Write-Host "[1/3] Converting to 44.1 kHz stereo wav..."
& ffmpeg -y -i $src -ar 44100 -ac 2 -c:a pcm_s16le $wav 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) { throw "ffmpeg failed while converting $src" }
if (-not (Test-Path -LiteralPath $wav)) { throw "ffmpeg produced no wav at $wav" }

Write-Host "[2/3] Separating stems (this takes a few minutes on CPU)..."
& $python -m demucs --two-stems=vocals -n $Model --out $workDir $wav 2>&1 | Out-Host
if ($LASTEXITCODE -ne 0) { throw "demucs failed (exit $LASTEXITCODE)" }

if (-not (Test-Path -LiteralPath $demucsDir)) {
    throw "demucs produced no output at $demucsDir"
}

$noVocals = Join-Path $demucsDir "no_vocals.wav"
$vocals   = Join-Path $demucsDir "vocals.wav"

Write-Host "[3/3] Writing stems..."
& ffmpeg -y -i $noVocals -c:a libmp3lame -q:a 2 (Join-Path $instDir   "$stem.mp3") 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) { throw "ffmpeg failed encoding the instrumental mp3" }
& ffmpeg -y -i $vocals   -c:a libmp3lame -q:a 2 (Join-Path $vocalsDir "$stem.mp3") 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) { throw "ffmpeg failed encoding the vocals mp3" }
Copy-Item $noVocals (Join-Path $instDir   "$stem.wav") -Force
Copy-Item $vocals   (Join-Path $vocalsDir "$stem.wav") -Force

Remove-Item $demucsDir -Recurse -Force
Remove-Item $wav -Force

Write-Host ""
Write-Host "Done."
Write-Host "  Instrumental: $instDir\$stem.mp3"
Write-Host "  Vocals      : $vocalsDir\$stem.mp3"
