# YouTube Audio/Video Workflow - PowerShell Script
# Prefers the workspace environment, with py -3.11 as a fallback.
param(
    [Parameter(Position=0)]
    [ValidateSet("setup", "search", "download", "download-trim", "metadata", "copy", "generate", "upload", "batch", "full", "all", "workflow", "doctor", "test", "smoke", "clean", "help")]
    [string]$Target = "help",
    [string]$Audio,
    [string]$Url,
    [string]$Images,
    [string]$Timeline,
    [ValidateSet("original", "slow", "reverse")]
    [string]$Effect = "original",
    [switch]$Instrumental,
    [switch]$Upload,
    [ValidateSet("private", "unlisted", "public")]
    [string]$Privacy = "private",
    [ValidateSet("preview", "master", "video")]
    [string]$Preset,
    [string]$Reference,
    [ValidateSet("off", "peak", "loudness")]
    [string]$Normalize = "off",
    [switch]$AllowLimiting,
    [ValidateSet("24", "float")]
    [string]$WavFormat = "24",
    [ValidateSet(44100, 48000, 96000)]
    [int]$SampleRate = 48000,
    [double]$TargetLufs = -16,
    [double]$PeakDb = -1,
    [double]$TruePeak = -1.5,
    [double]$PreviewStart = 0,
    [Nullable[double]]$PreviewSeconds
)
$Root = $PSScriptRoot
$PyExe = "py"
$PyArgs = @("-3.11")
$WorkflowPython = Join-Path $Root ".venv\Scripts\python.exe"
if (Test-Path -LiteralPath $WorkflowPython) { $PyExe = $WorkflowPython; $PyArgs = @() }
$ErrorActionPreference = "Stop"

function Invoke-CheckedPython {
    # Windows PowerShell can treat ordinary native stderr logs as errors when
    # a caller redirects output. Use the process exit status as the result.
    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        & $PyExe @PyArgs @args
        $commandExitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousPreference
    }
    if ($commandExitCode -ne 0) { throw "Python command failed (exit $commandExitCode)" }
}

function Invoke-Workflow {
    if ((-not $Audio -and -not $Url) -or ($Audio -and $Url)) { throw "Supply exactly one of -Audio or -Url" }
    $workflowArgs = @("$Root\workflow.py", "--effect", $Effect, "--privacy", $Privacy)
    if ($Audio) { $workflowArgs += @("--audio", $Audio) }
    if ($Url) { $workflowArgs += @("--url", $Url) }
    if ($Images) { $workflowArgs += @("--images", $Images) }
    if ($Timeline) { $workflowArgs += @("--timeline", $Timeline) }
    if ($Instrumental) { $workflowArgs += "--instrumental" }
    if ($Upload) { $workflowArgs += "--upload" }
    if ($Preset) { $workflowArgs += @("--preset", $Preset) }
    if ($Reference) { $workflowArgs += @("--reference", $Reference) }
    $workflowArgs += @("--normalize", $Normalize, "--wav-format", $WavFormat, "--sample-rate", "$SampleRate",
                       "--target-lufs", $TargetLufs.ToString([Globalization.CultureInfo]::InvariantCulture),
                       "--peak-db", $PeakDb.ToString([Globalization.CultureInfo]::InvariantCulture),
                       "--true-peak", $TruePeak.ToString([Globalization.CultureInfo]::InvariantCulture),
                       "--preview-start", $PreviewStart.ToString([Globalization.CultureInfo]::InvariantCulture))
    if ($null -ne $PreviewSeconds) { $workflowArgs += @("--preview-seconds", ([double]$PreviewSeconds).ToString([Globalization.CultureInfo]::InvariantCulture)) }
    if ($AllowLimiting) { $workflowArgs += "--allow-limiting" }
    Invoke-CheckedPython @workflowArgs
}

function Invoke-Setup {
    Write-Host "=== Setting up YouTube Audio/Video Workflow ===" -ForegroundColor Green
    if (-not (Test-Path -LiteralPath $WorkflowPython)) {
        & py -3.11 -m venv (Join-Path $Root ".venv")
        if ($LASTEXITCODE -ne 0) { throw "Could not create workspace environment" }
    }
    $script:PyExe = $WorkflowPython
    $script:PyArgs = @()
    Invoke-CheckedPython -m pip install -r "$Root\requirements\workflow.txt"
    Invoke-CheckedPython -m playwright install chromium
    Write-Host "Setup complete!" -ForegroundColor Green
}

function Invoke-Search {
    Set-Location "$Root\modules\automatic_upload"; Invoke-CheckedPython main.py; Set-Location $Root
}

function Invoke-Download {
    Set-Location "$Root\modules\automatic_upload"; Invoke-CheckedPython download_mp3.py; Set-Location $Root
}

function Invoke-DownloadTrim {
    Write-Host "=== Downloading + trimming silence ===" -ForegroundColor Green
    Set-Location "$Root\modules\automatic_upload"; Invoke-CheckedPython download_mp3.py --trim; Set-Location $Root
}

function Invoke-Metadata {
    Write-Host "=== Generating AI metadata ===" -ForegroundColor Green
    if (-not $env:OPENAI_API_KEY) {
        Write-Host "WARNING: OPENAI_API_KEY is not set." -ForegroundColor Yellow
        Write-Host "Get a free key at: https://openrouter.ai/keys" -ForegroundColor Yellow
    }
    Set-Location "$Root\modules\automatic_upload"; Invoke-CheckedPython generate_metadata.py; Set-Location $Root
}

function Invoke-Generate {
    Set-Location "$Root\modules\music_video_generator"; Invoke-CheckedPython -u main.py; Set-Location $Root
}

function Invoke-Upload {
    Write-Host "=== Uploading to YouTube ===" -ForegroundColor Green
    Set-Location "$Root\modules\automatic_YouTube_upload"
    Invoke-CheckedPython -u youtube_uploader.py --video "..\music_video_generator\output\music_video.mp4" --metadata "..\automatic_upload\metadata.json" --privacy public
    Set-Location $Root
}

function Invoke-Full {
    Write-Host "=== Running full pipeline (smart mode) ===" -ForegroundColor Green
    Invoke-CheckedPython -u "$Root\pipelines\run_all.py" --max-songs 3
}

function Invoke-Copy {
    Write-Host "=== Copying audio to music_video_generator ===" -ForegroundColor Green
    $src = "$Root\modules\automatic_upload\downloads"
    $dst = "$Root\modules\music_video_generator\input\audio"
    if (-not (Test-Path $dst)) { New-Item -ItemType Directory -Path $dst -Force | Out-Null }
    if (Test-Path $src) {
        Copy-Item -Path "$src\*.mp3" -Destination $dst -Force -ErrorAction Stop
        Copy-Item -Path "$src\*.webm" -Destination $dst -Force -ErrorAction Stop
        Copy-Item -Path "$src\*.mp4" -Destination $dst -Force -ErrorAction Stop
    }
    Write-Host "Copied audio files!" -ForegroundColor Green
}

function Invoke-Batch {
    Write-Host "=== Running 93-Song Batch Pipeline (31 Videos x 3 Songs) ===" -ForegroundColor Green
    Invoke-CheckedPython -u "$Root\pipelines\batch_pipeline.py"
}

function Invoke-All { Invoke-Search; Invoke-Download; Invoke-Metadata; Invoke-Copy; Invoke-Generate; Invoke-Upload }

function Invoke-Clean {
    Write-Host "=== Cleaning all generated files ===" -ForegroundColor Green
    Write-Host "  Cleaning automatic_upload..."
    Remove-Item -Path "$Root\modules\automatic_upload\youtube_links.txt" -Force -ErrorAction SilentlyContinue
    Remove-Item -Path "$Root\modules\automatic_upload\downloads" -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -Path "$Root\modules\automatic_upload\__pycache__" -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -Path "$Root\modules\automatic_upload\metadata.json" -Force -ErrorAction SilentlyContinue
    Remove-Item -Path "$Root\modules\automatic_upload\metadata.txt" -Force -ErrorAction SilentlyContinue
    Write-Host "  Cleaning music_video_generator..."
    Remove-Item -Path "$Root\modules\music_video_generator\output" -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -Path "$Root\modules\music_video_generator\__pycache__" -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -Path "$Root\modules\music_video_generator\src\__pycache__" -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -Path "$Root\modules\music_video_generator\input\audio\*.webm" -Force -ErrorAction SilentlyContinue
    Remove-Item -Path "$Root\modules\music_video_generator\input\audio\*.mp3" -Force -ErrorAction SilentlyContinue
    Remove-Item -Path "$Root\modules\music_video_generator\input\audio\*.wav" -Force -ErrorAction SilentlyContinue
    Write-Host "  Cleaning automatic_YouTube_upload..."
    Remove-Item -Path "$Root\modules\automatic_YouTube_upload\*.log" -Force -ErrorAction SilentlyContinue
    Remove-Item -Path "$Root\modules\automatic_YouTube_upload\*.mp3" -Force -ErrorAction SilentlyContinue
    Remove-Item -Path "$Root\modules\automatic_YouTube_upload\*.webm" -Force -ErrorAction SilentlyContinue
    Remove-Item -Path "$Root\modules\automatic_YouTube_upload\*.wav" -Force -ErrorAction SilentlyContinue
    Remove-Item -Path "$Root\modules\automatic_YouTube_upload\__pycache__" -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "=== All cleaned! ===" -ForegroundColor Green
}

function Show-Help {
    Write-Host "YouTube Audio/Video Workflow - Global Runner"
    Write-Host "  Export presets: -Preset preview|master|video [-Reference <audio>] [-Normalize off|peak|loudness]"
    Write-Host "  .\run.ps1 doctor   - Check syntax, dependencies, tools, and Demucs runtime"
    Write-Host "  .\run.ps1 test     - Run offline regression tests"
    Write-Host "  .\run.ps1 smoke    - Render short local fixtures (no uploads)"
    Write-Host "  .\run.ps1 workflow -Audio <file-or-folder> [-Effect slow] [-Instrumental] [-Upload]"
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
    "workflow" { Invoke-Workflow }
    "doctor" { Invoke-CheckedPython "$Root\tools\doctor.py" --output "$Root\docs\health-check.json" }
    "test" { Push-Location $Root; try { Invoke-CheckedPython -m unittest discover -s tests -v } finally { Pop-Location } }
    "smoke" { Invoke-CheckedPython "$Root\tools\smoke_media.py" }
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
