# YouTube Automation - PowerShell Script

param(
    [Parameter(Position=0)]
    [ValidateSet("install", "search", "download", "all", "clean", "help")]
    [string]$Target = "help"
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
    Write-Host "Downloading MP3 files..." -ForegroundColor Green
    if (Test-Path $python) { & $python download_mp3.py } else { python download_mp3.py }
}

function Clean-Generated {
    Write-Host "Cleaning generated files..." -ForegroundColor Green
    Remove-Item -Path "youtube_links.txt" -Force -ErrorAction SilentlyContinue
    Remove-Item -Path "downloads" -Recurse -Force -ErrorAction SilentlyContinue
    Get-ChildItem -Filter "*.mp3" | Remove-Item -Force -ErrorAction SilentlyContinue
    Write-Host "Cleaned!" -ForegroundColor Green
}

function Show-Help {
    Write-Host "YouTube Automation - Usage:"
    Write-Host ""
    Write-Host "  .\run.ps1 install     - Set up venv and install dependencies"
    Write-Host "  .\run.ps1 search      - Find YouTube links from input.txt"
    Write-Host "  .\run.ps1 download    - Download MP3 files"
    Write-Host "  .\run.ps1 all         - Search then download"
    Write-Host "  .\run.ps1 clean       - Remove generated files"
    Write-Host "  .\run.ps1 help        - Show this help"
}

switch ($Target) {
    "install" { Install-Dependencies }
    "search" { Search-Links }
    "download" { Download-MP3s }
    "all" { Search-Links; Download-MP3s }
    "clean" { Clean-Generated }
    "help" { Show-Help }
}