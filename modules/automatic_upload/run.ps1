# YouTube Automation - PowerShell Script

param(
    [Parameter(Position=0)]
    [ValidateSet("install", "search", "download", "download-trim", "metadata", "pinterest", "all", "clean", "help")]
    [string]$Target = "help",

    [Parameter(Position=1)]
    [string]$VideoId = "",

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$DownloadArgs = @()
)

$venv = ".venv"
$python = ".venv\Scripts\python.exe"
$pip = ".venv\Scripts\pip.exe"

function Install-Dependencies {
    Write-Host "Setting up virtual environment..." -ForegroundColor Green
    if (-not (Test-Path $python)) {
        python -m venv .venv
    }
    & $pip install -r requirements.txt
    & $python -m playwright install chromium
    Write-Host "Setup complete!" -ForegroundColor Green
}

function Search-Links {
    Write-Host "Searching YouTube for links..." -ForegroundColor Green
    if (Test-Path $python) { & $python main.py } else { python main.py }
}

function Download-MP3s {
    Write-Host "Downloading MP3 files (320kbps)..." -ForegroundColor Green
    if ($DownloadArgs.Count -gt 0) {
        Write-Host "  args: $($DownloadArgs -join ' ')" -ForegroundColor DarkGray
    }
    if (Test-Path $python) { & $python download_mp3.py @DownloadArgs } else { python download_mp3.py @DownloadArgs }
}

function Download-Trim {
    Write-Host "Downloading and trimming silence..." -ForegroundColor Green
    $pyargs = "--trim"
    if (Test-Path $python) { & $python download_mp3.py $pyargs } else { python download_mp3.py $pyargs }
}

function Generate-Metadata {
    Write-Host "Generating AI metadata for songs..." -ForegroundColor Green
    if (-not $env:OPENAI_API_KEY) {
        Write-Host "WARNING: OPENAI_API_KEY is not set. Set it with: `$env:OPENAI_API_KEY='your-key'" -ForegroundColor Yellow
    }
    if (Test-Path $python) { & $python generate_metadata.py } else { python generate_metadata.py }
}

function Pinterest-Upload {
    Write-Host "YouTube-to-Pinterest image automation..." -ForegroundColor Green
    if (-not $VideoId) {
        Write-Host "ERROR: Video ID required. Usage:" -ForegroundColor Red
        Write-Host "  .\run.ps1 pinterest <YOUTUBE_VIDEO_ID>"
        return
    }
    if (Test-Path $python) { & $python -u pinterest_uploader.py --video-id $VideoId } else { python -u pinterest_uploader.py --video-id $VideoId }
}

function Clean-Generated {
    Write-Host "Cleaning generated files..." -ForegroundColor Green
    Remove-Item -Path "youtube_links.txt" -Force -ErrorAction SilentlyContinue
    Remove-Item -Path "downloads" -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -Path "metadata.json" -Force -ErrorAction SilentlyContinue
    Remove-Item -Path "metadata.txt" -Force -ErrorAction SilentlyContinue
    Get-ChildItem -Filter "*.mp3" | Remove-Item -Force -ErrorAction SilentlyContinue
    Get-ChildItem -Filter "*.wav" | Remove-Item -Force -ErrorAction SilentlyContinue
    Write-Host "Cleaned!" -ForegroundColor Green
}

function Show-Help {
    Write-Host "YouTube Automation - Usage:"
    Write-Host ""
    Write-Host "  .\run.ps1 install     - Set up venv and install dependencies"
    Write-Host "  .\run.ps1 search      - Find YouTube links from input.txt"
    Write-Host "  .\run.ps1 download    - Download MP3 files (320kbps)"
    Write-Host "  .\run.ps1 download-trim - Download and trim silence from audio"
    Write-Host "  .\run.ps1 metadata     - Generate AI-powered titles & descriptions"
    Write-Host "  .\run.ps1 pinterest    - After YouTube upload: extract images -> upload to Pinterest"
    Write-Host "  .\run.ps1 all         - Search then download"
    Write-Host "  .\run.ps1 clean        - Remove generated files"
    Write-Host "  .\run.ps1 help          - Show this help"
}

Push-Location $PSScriptRoot
try {
switch ($Target) {
    "install" { Install-Dependencies }
    "search" { Search-Links }
    "download" { Download-MP3s }
    "download-trim" { Download-Trim }
    "metadata" { Generate-Metadata }
    "pinterest" { Pinterest-Upload }
    "all" { Generate-Metadata; Search-Links; Download-MP3s }
    "clean" { Clean-Generated }
    "help" { Show-Help }
}
} finally { Pop-Location }
