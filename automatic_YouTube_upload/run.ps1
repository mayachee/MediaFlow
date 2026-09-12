# YouTube Uploader - PowerShell Script

param(
    [Parameter(Position=0)]
    [ValidateSet("install", "upload", "upload-thumb", "clean", "help")]
    [string]$Target = "help",

    [Parameter(Position=1)]
    [string]$VideoId = "",

    [Parameter(Position=2)]
    [string]$Thumbnail = ""
)

function Install-Dependencies {
    Write-Host "Installing dependencies..." -ForegroundColor Green
    pip install -r requirements.txt
    Write-Host "Setup complete!" -ForegroundColor Green
}

function Upload-Video {
    Write-Host "Uploading video to YouTube..." -ForegroundColor Green
    $video = "..\music_video_generator\output\music_video.mp4"
    python -u youtube_uploader.py --video $video --title "My Music Video" --description "Auto-generated music video" --tags "music,video,lyrics" --privacy public
}

function Upload-Thumbnail {
    if (-not $VideoId) {
        Write-Host "ERROR: Video ID required. Usage:" -ForegroundColor Red
        Write-Host "  .\run.ps1 upload-thumb <YOUTUBE_VIDEO_ID> <THUMBNAIL_PATH>"
        return
    }
    Write-Host "Uploading thumbnail to video $VideoId..." -ForegroundColor Green
    python -u youtube_uploader.py --video-id $VideoId --thumbnail $Thumbnail
}

function Clean-Files {
    Write-Host "Cleaning..." -ForegroundColor Green
    Remove-Item -Path "token.pickle" -Force -ErrorAction SilentlyContinue
    Remove-Item -Path "*.log" -Force -ErrorAction SilentlyContinue
    Write-Host "Cleaned!" -ForegroundColor Green
}

function Show-Help {
    Write-Host "YouTube Uploader - Usage:"
    Write-Host ""
    Write-Host "  .\run.ps1 install                       - Install dependencies"
    Write-Host "  .\run.ps1 upload                        - Upload video to YouTube"
    Write-Host "  .\run.ps1 upload-thumb <ID> <IMAGE>     - Upload thumbnail to existing video"
    Write-Host "  .\run.ps1 clean                         - Remove token and logs"
    Write-Host "  .\run.ps1 help                          - Show this help"
}

switch ($Target) {
    "install" { Install-Dependencies }
    "upload" { Upload-Video }
    "upload-thumb" { Upload-Thumbnail }
    "clean" { Clean-Files }
    "help" { Show-Help }
}