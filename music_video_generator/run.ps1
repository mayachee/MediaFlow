# Music Video Generator - PowerShell Script

param(
    [Parameter(Position=0)]
    [ValidateSet("install", "generate", "clean", "help")]
    [string]$Target = "help"
)

function Install-Dependencies {
    Write-Host "Installing dependencies..." -ForegroundColor Green
    pip install -r requirements.txt
    if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
        Write-Host "FFmpeg not found. Please install it:" -ForegroundColor Yellow
        Write-Host "  winget install ffmpeg" -ForegroundColor Yellow
    }
    Write-Host "Setup complete!" -ForegroundColor Green
}

function Generate-Video {
    Write-Host "Generating music video..." -ForegroundColor Green
    python -u main.py
    Write-Host "Done! Output: output\music_video.mp4" -ForegroundColor Green
}

function Clean-Output {
    Write-Host "Cleaning generated files..." -ForegroundColor Green
    Remove-Item -Path "output" -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -Path "src\__pycache__" -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "Cleaned!" -ForegroundColor Green
}

function Show-Help {
    Write-Host "Music Video Generator - Usage:"
    Write-Host ""
    Write-Host "  .\run.ps1 install     - Install Python dependencies"
    Write-Host "  .\run.ps1 generate    - Create music video"
    Write-Host "  .\run.ps1 clean       - Remove generated files"
    Write-Host "  .\run.ps1 help        - Show this help"
}

switch ($Target) {
    "install" { Install-Dependencies }
    "generate" { Generate-Video }
    "clean" { Clean-Output }
    "help" { Show-Help }
}