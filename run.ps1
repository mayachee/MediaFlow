# YouTube Audio/Video Workflow - PowerShell Script
param(
    [Parameter(Position=0)]
    [ValidateSet("setup", "search", "download", "download-trim", "metadata", "copy", "generate", "upload", "batch", "full", "all", "clean", "help")]
    [string]$Target = "help"
)
$Root = "C:\Users\Dima D'origine\OneDrive\Bureau\scripts"

function Invoke-Setup {
    Write-Host "=== Setting up YouTube Audio/Video Workflow ===" -ForegroundColor Green
    pip install -r "$Root\youtube_automation\requirements.txt"
    Set-Location "$Root\youtube_automation"; python -m playwright install chromium 2>$null; Set-Location $Root
    pip install -r "$Root\music_video_generator\requirements.txt"
    pip install -r "$Root\automatic_YouTube_upload\requirements.txt"
    Write-Host "Setup complete!" -ForegroundColor Green
}

function Invoke-Search {
    Set-Location "$Root\youtube_automation"; python main.py; Set-Location $Root
}

function Invoke-Download {
    Set-Location "$Root\youtube_automation"; python download_mp3.py; Set-Location $Root
}

function Invoke-DownloadTrim {
    Write-Host "=== Downloading + trimming silence ===" -ForegroundColor Green
    Set-Location "$Root\youtube_automation"; python download_mp3.py --trim; Set-Location $Root
}

function Invoke-Metadata {
    Write-Host "=== Generating AI metadata ===" -ForegroundColor Green
    if (-not $env:OPENAI_API_KEY) {
        Write-Host "WARNING: OPENAI_API_KEY is not set." -ForegroundColor Yellow
        Write-Host "Get a free key at: https://openrouter.ai/keys" -ForegroundColor Yellow
    }
    Set-Location "$Root\youtube_automation"; python generate_metadata.py; Set-Location $Root
}

function Invoke-Generate {
    Set-Location "$Root\music_video_generator"; python -u main.py; Set-Location $Root
}

function Invoke-Upload {
    Write-Host "=== Uploading to YouTube ===" -ForegroundColor Green
    Set-Location "$Root\automatic_YouTube_upload"
    python -u youtube_uploader.py --video "..\music_video_generator\output\music_video.mp4" --metadata "..\youtube_automation\metadata.json" --privacy public
    Set-Location $Root
}

function Invoke-Full {
    Write-Host "=== Running full pipeline (smart mode) ===" -ForegroundColor Green
    python run_all.py --max-songs 3
}

function Invoke-Copy {
    Write-Host "=== Copying audio to music_video_generator ===" -ForegroundColor Green
    $src = "$Root\youtube_automation\downloads"
    $dst = "$Root\music_video_generator\input\audio"
    if (-not (Test-Path $dst)) { New-Item -ItemType Directory -Path $dst -Force | Out-Null }
    if (Test-Path $src) {
        Copy-Item -Path "$src\*.mp3" -Destination $dst -Force -ErrorAction SilentlyContinue
        Copy-Item -Path "$src\*.webm" -Destination $dst -Force -ErrorAction SilentlyContinue
        Copy-Item -Path "$src\*.mp4" -Destination $dst -Force -ErrorAction SilentlyContinue
    }
    Write-Host "Copied audio files!" -ForegroundColor Green
}

function Invoke-Batch {
    Write-Host "=== Running 93-Song Batch Pipeline (31 Videos x 3 Songs) ===" -ForegroundColor Green
    python -u "$Root\batch_pipeline.py"
}

function Invoke-All { Invoke-Search; Invoke-Download; Invoke-Metadata; Invoke-Copy; Invoke-Generate; Invoke-Upload }

function Invoke-Clean {
    Write-Host "=== Cleaning all generated files ===" -ForegroundColor Green
    Write-Host "  Cleaning youtube_automation..."
    Remove-Item -Path "$Root\youtube_automation\youtube_links.txt" -Force -ErrorAction SilentlyContinue
    Remove-Item -Path "$Root\youtube_automation\downloads" -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -Path "$Root\youtube_automation\__pycache__" -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -Path "$Root\youtube_automation\metadata.json" -Force -ErrorAction SilentlyContinue
    Remove-Item -Path "$Root\youtube_automation\metadata.txt" -Force -ErrorAction SilentlyContinue
    Write-Host "  Cleaning music_video_generator..."
    Remove-Item -Path "$Root\music_video_generator\output" -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -Path "$Root\music_video_generator\__pycache__" -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -Path "$Root\music_video_generator\src\__pycache__" -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -Path "$Root\music_video_generator\input\audio\*.webm" -Force -ErrorAction SilentlyContinue
    Remove-Item -Path "$Root\music_video_generator\input\audio\*.mp3" -Force -ErrorAction SilentlyContinue
    Remove-Item -Path "$Root\music_video_generator\input\audio\*.wav" -Force -ErrorAction SilentlyContinue
    Remove-Item -Path "$Root\music_video_generator\input\images\*" -Force -ErrorAction SilentlyContinue
    Write-Host "  Cleaning automatic_YouTube_upload..."
    Remove-Item -Path "$Root\automatic_YouTube_upload\token.pickle" -Force -ErrorAction SilentlyContinue
    Remove-Item -Path "$Root\automatic_YouTube_upload\*.log" -Force -ErrorAction SilentlyContinue
    Remove-Item -Path "$Root\automatic_YouTube_upload\*.mp3" -Force -ErrorAction SilentlyContinue
    Remove-Item -Path "$Root\automatic_YouTube_upload\*.webm" -Force -ErrorAction SilentlyContinue
    Remove-Item -Path "$Root\automatic_YouTube_upload\*.wav" -Force -ErrorAction SilentlyContinue
    Remove-Item -Path "$Root\automatic_YouTube_upload\__pycache__" -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "=== All cleaned! ===" -ForegroundColor Green
}

function Show-Help {
    Write-Host "YouTube Audio/Video Workflow - Global Runner"
    Write-Host ""
    Write-Host "  .\run.ps1 setup    - Install all dependencies"
    Write-Host "  .\run.ps1 search   - Search YouTube for song links"
    Write-Host "  .\run.ps1 download - Download MP3 files from links"
    Write-Host "  .\run.ps1 download-trim - Download and trim silence from audio"
    Write-Host "  .\run.ps1 metadata - Generate AI-powered titles & descriptions"
    Write-Host "  .\run.ps1 copy     - Copy downloads to video generator input"
    Write-Host "  .\run.ps1 generate - Create music video from audio + images"
    Write-Host "  .\run.ps1 upload   - Upload video to YouTube"
    Write-Host "  .\run.ps1 full     - Run full pipeline with smart fallbacks"
    Write-Host "  .\run.ps1 batch    - Run 31-video batch pipeline (auto-deletes after upload)"
    Write-Host "  .\run.ps1 all      - Run full pipeline"
    Write-Host "  .\run.ps1 clean    - Remove all generated files"
    Write-Host "  .\run.ps1 help     - Show this help"
}

switch ($Target) {
    "setup" { Invoke-Setup }
    "search" { Invoke-Search }
    "download" { Invoke-Download }
    "download-trim" { Invoke-DownloadTrim }
    "metadata" { Invoke-Metadata }
    "copy" { Invoke-Copy }
    "generate" { Invoke-Generate }
    "upload" { Invoke-Upload }
    "full" { Invoke-Full }
    "batch" { Invoke-Batch }
    "all" { Invoke-All }
    "clean" { Invoke-Clean }
    "help" { Show-Help }
}

