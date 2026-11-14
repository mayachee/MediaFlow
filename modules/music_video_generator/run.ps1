# Music Video Generator - PowerShell Script

param(
    [Parameter(Position=0)]
    [ValidateSet("install", "generate", "preview", "test", "clean", "help")]
    [string]$Target = "help",
    [ValidateSet("cinematic", "balanced", "energetic")]
    [string]$Style,
    [string]$Audio,
    [string]$Visuals,
    [int]$MaxSongs = 4,
    [double]$PreviewStart = 60,
    [double]$PreviewSeconds = 30
)

$VenvPython = ".\.venv\Scripts\python.exe"
$VenvPip = ".\.venv\Scripts\pip.exe"

function Ensure-Venv {
    if (-not (Test-Path $VenvPython)) {
        Write-Host "Creating virtual environment..." -ForegroundColor Green
        python -m venv .venv
        if (-not (Test-Path $VenvPython)) {
            Write-Host "Failed to create virtual environment." -ForegroundColor Red
            exit 1
        }
    }
}

function Install-Dependencies {
    Ensure-Venv
    Write-Host "Installing dependencies..." -ForegroundColor Green
    & $VenvPip install --no-cache-dir -r requirements.txt
    if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
        Write-Host "FFmpeg not found. Please install it:" -ForegroundColor Yellow
        Write-Host "  winget install ffmpeg" -ForegroundColor Yellow
    }
    Write-Host "Setup complete!" -ForegroundColor Green
}

function Generate-Video {
    param([switch]$Preview)
    Ensure-Venv
    Write-Host "Generating music video..." -ForegroundColor Green
    $generatorArgs = @('-u', 'main.py', '--max-songs', "$MaxSongs")
    if ($Style) { $generatorArgs += @('--style', $Style) }
    if ($Preview) {
        $generatorArgs = @('-u', 'main.py', '--max-songs', '1', '--preview-start',
            $PreviewStart.ToString([Globalization.CultureInfo]::InvariantCulture), '--preview-seconds',
            $PreviewSeconds.ToString([Globalization.CultureInfo]::InvariantCulture))
        if ($Style) { $generatorArgs += @('--style', $Style) }
    }
    if ($Audio) { $generatorArgs += @('--audio', $Audio) }
    if ($Visuals) { $generatorArgs += @('--visuals', $Visuals) }
    & $VenvPython @generatorArgs
    if ($LASTEXITCODE -ne 0) { throw "Video generation failed (exit $LASTEXITCODE)" }
    Write-Host "Done. See the video path printed above." -ForegroundColor Green
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
    Write-Host "  .\run.ps1 preview -Style cinematic -PreviewStart 60 -PreviewSeconds 30"
    Write-Host "  .\run.ps1 test        - Test musical direction and pacing"
    Write-Host "  .\run.ps1 clean       - Remove generated files"
    Write-Host "  .\run.ps1 help        - Show this help"
}

Push-Location $PSScriptRoot
try {
switch ($Target) {
    "install" { Install-Dependencies }
    "generate" { Generate-Video }
    "preview" { Generate-Video -Preview }
    "test" {
        Ensure-Venv
        & $VenvPython -m unittest discover -s tests -v
        if ($LASTEXITCODE -ne 0) { throw "Direction tests failed" }
    }
    "clean" { Clean-Output }
    "help" { Show-Help }
}
} finally { Pop-Location }
