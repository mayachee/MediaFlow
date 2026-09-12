# YouTube Audio/Video Workflow - PowerShell Script

param(
    [Parameter(Position=0)]
    [ValidateSet("setup", "search", "download", "generate", "upload", "all", "clean", "help")]
    [string]$Target = "help"
)

$Root = "C:\Users\Dima D'origine\OneDrive\Bureau\scripts"

function Invoke-Setup {
    Write-Host "=== Setting up YouTube Audio/Video Workflow ===" -ForegroundColor Green
    Write-Host "Installing youtube_automation dependencies..."
    Set-Location "$Root\youtube_automation"
    pip install -r requirements.txt
    python -m playwright install chromium 2>$null
    
    Write-Host "Installing music_video_generator dependencies..."
    Set-Location "$Root\music_video_generator"
    pip install -r requirements.txt
    
    Write-Host "Installing automatic_YouTube_upload dependencies..."
    Set-Location "$Root\automatic_YouTube_upload"
    pip install -r requirements.txt
    
    if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
        Write-Host "WARNING: FFmpeg not found." -ForegroundColor Yellow
        Write-Host "  Windows: winget install ffmpeg" -ForegroundColor Yellow
        Write-Host "  macOS: brew install ffmpeg" -ForegroundColor Yellow
        Write-Host "  Linux: sudo apt install ffmpeg" -ForegroundColor Yellow
    }
    
    Set-Location $Root
    Write-Host "Setup complete!" -ForegroundColor Green
}

function Invoke-Search {
    Write-Host "=== Searching YouTube ===" -ForegroundColor Green
    Set-Location "$Root\youtube_automation"
    python main.py
    Set-Location $Root
}

function Invoke-Download {
    Write-Host "=== Downloading audio files ===" -ForegroundColor Green
    Set-Location "$Root\youtube_automation"
    python download_mp3.py
    Set-Location $Root
}

function Invoke-Generate {
    Write-Host "=== Generating music video ===" -ForegroundColor Green
    Set-Location "$Root\music_video_generator"
    python -u main.py
    Set-Location $Root
}

function Invoke-Upload {
    Write-Host "=== Uploading to YouTube ===" -ForegroundColor Green
    Set-Location "$Root\automatic_YouTube_upload"
    python -u youtube_uploader.py --video "..\music_video_generator\output\music_video.mp4" --title "My Music Video" --description "Auto-generated music video" --tags "music,video,lyrics" --privacy public
    Set-Location $Root
    Write-Host "Upload complete!" -ForegroundColor Green
}

function Invoke-All {
    Invoke-Search
    Invoke-Download
    Invoke-Generate
    Invoke-Upload
    Write-Host "=== Full workflow complete! ===" -ForegroundColor Green
}

function Invoke-Clean {
    Write-Host "Cleaning generated files..." -ForegroundColor Green
    Remove-Item -Path "$Root\youtube_automation\youtube_links.txt" -Force -ErrorAction SilentlyContinue
    Remove-Item -Path "$Root\music_video_generator\output" -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -Path "$Root\automatic_YouTube_upload\token.pickle" -Force -ErrorAction SilentlyContinue
    Remove-Item -Path "$Root\automatic_YouTube_upload\*.log" -Force -ErrorAction SilentlyContinue
    Get-ChildItem "$Root\youtube_automation\__pycache__" -Recurse -Force -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue
    Get-ChildItem "$Root\music_video_generator\__pycache__" -Recurse -Force -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue
    Get-ChildItem "$Root\music_video_generator\src\__pycache__" -Recurse -Force -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue
    Get-ChildItem "$Root\automatic_YouTube_upload\__pycache__" -Recurse -Force -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue
    Write-Host "Cleaned!" -ForegroundColor Green
}

function Show-Help {
    Write-Host "YouTube Audio/Video Workflow - Global Runner"
    Write-Host ""
    Write-Host "  .\run.ps1 setup    - Install all dependencies and check FFmpeg"
    Write-Host "  .\run.ps1 search   - Search YouTube for song links"
    Write-Host "  .\run.ps1 download - Download MP3 files from links"
    Write-Host "  .\run.ps1 generate - Create music video from audio + images"
    Write-Host "  .\run.ps1 upload   - Upload video to YouTube"
    Write-Host "  .\run.ps1 all      - Run full pipeline (search, download, generate, upload)"
    Write-Host "  .\run.ps1 clean    - Remove all generated files"
    Write-Host "  .\run.ps1 help     - Show this help"
}

switch ($Target) {
    "setup" { Invoke-Setup }
    "search" { Invoke-Search }
    "download" { Invoke-Download }
    "generate" { Invoke-Generate }
    "upload" { Invoke-Upload }
    "all" { Invoke-All }
    "clean" { Invoke-Clean }
    "help" { Show-Help }
}