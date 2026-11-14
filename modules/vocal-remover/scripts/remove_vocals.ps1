<#
.SYNOPSIS
    Download audio from a URL and split it into instrumental and vocal stems.

.DESCRIPTION
    Downloads the best available audio with yt-dlp, converts it to 44.1 kHz stereo
    wav, runs demucs, then writes the results to output\instrumental\ and
    output\vocals\.

.EXAMPLE
    .\remove_vocals.ps1 -Url "https://www.youtube.com/watch?v=..."
#>

param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$Url,

    [string]$Model = "htdemucs"
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

if (-not (Test-Path -LiteralPath $python)) {
    throw "Missing venv at $python. Run: make install  (or  .\run.ps1 install)"
}

New-Item -ItemType Directory -Path $workDir, $instDir, $vocalsDir -Force | Out-Null

Write-Host "[1/4] Downloading audio..."
$raw = & yt-dlp -f "bestaudio/best" -o (Join-Path $workDir "%(id)s.%(ext)s") --no-playlist --print "%(id)s" --print "%(title)s" $Url
if ($LASTEXITCODE -ne 0) { throw "yt-dlp failed (exit $LASTEXITCODE)" }

$lines  = $raw -split "`n" | Where-Object { $_.Trim() -ne "" }
$id     = $lines[0].Trim()
$title  = $lines[1].Trim()
$safe   = $title -replace '[\\/:*?"<>|]', '_'
$stem   = "${id}_${safe}"

$ext = (Get-ChildItem -LiteralPath $workDir -Filter "$id.*" | Select-Object -First 1).Extension
$wav = Join-Path $workDir "$id.wav"

Write-Host "[2/4] Converting to 44.1 kHz stereo wav..."
& ffmpeg -y -i (Join-Path $workDir "$id$ext") -ar 44100 -ac 2 -c:a pcm_s16le $wav 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) { throw "ffmpeg failed while converting the downloaded audio" }

Write-Host "[3/4] Separating stems (this takes a few minutes on CPU)..."
& $python -m demucs --two-stems=vocals -n $Model --out $workDir $wav 2>&1 | Out-Host
if ($LASTEXITCODE -ne 0) { throw "demucs failed (exit $LASTEXITCODE)" }

$demucsDir = Join-Path $workDir (Join-Path $Model $id)
if (-not (Test-Path -LiteralPath $demucsDir)) {
    throw "demucs produced no output at $demucsDir"
}

$noVocals = Join-Path $demucsDir "no_vocals.wav"
$vocals   = Join-Path $demucsDir "vocals.wav"

Write-Host "[4/4] Writing stems..."
& ffmpeg -y -i $noVocals -c:a libmp3lame -q:a 2 (Join-Path $instDir   "$stem.mp3") 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) { throw "ffmpeg failed encoding the instrumental mp3" }
& ffmpeg -y -i $vocals   -c:a libmp3lame -q:a 2 (Join-Path $vocalsDir "$stem.mp3") 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) { throw "ffmpeg failed encoding the vocals mp3" }
Copy-Item $noVocals (Join-Path $instDir   "$stem.wav") -Force
Copy-Item $vocals   (Join-Path $vocalsDir "$stem.wav") -Force

Remove-Item $demucsDir -Recurse -Force
Remove-Item $wav -Force
Get-ChildItem -LiteralPath $workDir -Filter "$id.*" -Exclude "*.wav" | Remove-Item -Force -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "Done."
Write-Host "  Instrumental: $instDir\$stem.mp3"
Write-Host "  Vocals      : $vocalsDir\$stem.mp3"
