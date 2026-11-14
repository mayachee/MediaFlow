<#
.SYNOPSIS
    vocal-remover - split songs into instrumental and vocal stems with demucs.

.EXAMPLE
    .\run.ps1 local
    Splits the newest file in ..\automatic_upload\downloads

.EXAMPLE
    .\run.ps1 local "GENER8ION - STORM starring Yung Lean.mp4"
    Splits a specific file from the downloads folder

.EXAMPLE
    .\run.ps1 url "https://www.youtube.com/watch?v=..."
    Downloads the audio first, then splits it

.EXAMPLE
    .\run.ps1 help
    Shows all targets
#>

param(
    [Parameter(Position = 0)]
    [ValidateSet("install", "local", "latest", "url", "download", "track", "clean", "distclean", "help")]
    [string]$Target = "help",

    [Parameter(Position = 1)]
    [string]$Argument = "",

    [string]$Model = "htdemucs"
)

$ErrorActionPreference = "Stop"

$root    = $PSScriptRoot
$venv    = Join-Path $root ".venv"
$python  = Join-Path $venv "Scripts\python.exe"
$workDir = Join-Path $root "work"
$outDir  = Join-Path $root "output"
$upDir   = Join-Path (Split-Path -Parent $root) "automatic_upload"

function Install-Dependencies {
    Write-Host "Setting up virtual environment..." -ForegroundColor Green
    if (-not (Test-Path -LiteralPath $python)) {
        python -m venv $venv
    }
    & $python -m pip install --upgrade pip
    & $python -m pip install torch --index-url https://download.pytorch.org/whl/cpu
    & $python -m pip install demucs
    Write-Host "Setup complete." -ForegroundColor Green
}

function Assert-Ready {
    if (-not (Test-Path -LiteralPath $python)) {
        throw "Missing venv. Run: .\run.ps1 install"
    }
    if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
        throw "ffmpeg not found on PATH. Install: winget install Gyan.FFmpeg"
    }
}

function Invoke-Local {
    Assert-Ready
    $script = Join-Path $root "scripts\remove_vocals_local.ps1"
    if ([string]::IsNullOrWhiteSpace($Argument)) {
        & $script -Model $Model
    } else {
        & $script -File $Argument -Model $Model
    }
}

function Invoke-Url {
    if ([string]::IsNullOrWhiteSpace($Argument)) {
        throw "URL required. Usage: .\run.ps1 url <youtube-url>"
    }
    Assert-Ready
    & (Join-Path $root "scripts\remove_vocals.ps1") -Url $Argument -Model $Model
}

function Invoke-Download {
    if (-not (Test-Path -LiteralPath $upDir)) {
        throw "automatic_upload folder not found: $upDir"
    }
    Push-Location $upDir
    try { & (Join-Path $upDir "run.ps1") download } finally { Pop-Location }
}

function Invoke-Track {
    Invoke-Download
    Invoke-Local
}

function Clear-Work {
    if (Test-Path -LiteralPath $workDir) {
        Remove-Item $workDir -Recurse -Force
        Write-Host "Removed work/" -ForegroundColor Green
    }
    if (Test-Path -LiteralPath (Join-Path $root "input")) {
        Remove-Item (Join-Path $root "input") -Recurse -Force
        Write-Host "Removed input/" -ForegroundColor Green
    }
}

function Clear-Output {
    if (Test-Path -LiteralPath $outDir) {
        Remove-Item $outDir -Recurse -Force
        Write-Host "Removed output/" -ForegroundColor Green
    }
    New-Item -ItemType Directory -Force -Path (Join-Path $outDir "instrumental"), (Join-Path $outDir "vocals") | Out-Null
}

function Show-Help {
    Write-Host "vocal-remover - usage:"
    Write-Host ""
    Write-Host "  .\run.ps1 install                 Set up .venv (torch CPU + demucs)"
    Write-Host "  .\run.ps1 local [file]            Split newest file in ..\automatic_upload\downloads"
    Write-Host "  .\run.ps1 local <file>            Split a specific file (name or full path)"
    Write-Host "  .\run.ps1 latest                  Alias for 'local'"
    Write-Host "  .\run.ps1 url <url>               Download from URL, then split"
    Write-Host "  .\run.ps1 download                Run ..\automatic_upload\run.ps1 download"
    Write-Host "  .\run.ps1 track                   Download, then split the result"
    Write-Host "  .\run.ps1 clean                   Remove output/ and work/"
    Write-Host "  .\run.ps1 distclean               Remove output/, work/ and input/"
    Write-Host "  .\run.ps1 help                    Show this help"
    Write-Host ""
    Write-Host "Options:"
    Write-Host "  -Model <name>                    demucs model (default: htdemucs)"
    Write-Host ""
    Write-Host "Output: output\instrumental\<track>.mp3 and output\vocals\<track>.mp3"
}

switch ($Target) {
    "install"   { Install-Dependencies }
    "local"     { Invoke-Local }
    "latest"    { Invoke-Local }
    "url"       { Invoke-Url }
    "download"  { Invoke-Download }
    "track"     { Invoke-Track }
    "clean"     { Clear-Output; Clear-Work }
    "distclean" { Clear-Output; Clear-Work }
    "help"      { Show-Help }
}
