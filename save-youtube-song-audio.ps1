param(
    [string]$InputCsv = '.\youtube-song-links.csv',
    [string]$Destination,
    [ValidateSet('mp3', 'm4a', 'wav')]
    [string]$Format = 'mp3',
    [switch]$Preview
)

$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
if (-not $Destination) { $Destination = Join-Path $PSScriptRoot 'gta6-songs' }
$tracks = @(Import-Csv -LiteralPath $InputCsv -Encoding UTF8)
if ($tracks.Count -eq 0 -or 'VideoUrl' -notin $tracks[0].PSObject.Properties.Name) {
    throw 'The CSV must contain at least one row and a VideoUrl column.'
}

$missing = 0
$failed = 0
$downloader = $null
foreach ($track in $tracks) {
    if ($track.VideoUrl -notmatch '^https://www\.youtube\.com/watch\?v=([A-Za-z0-9_-]{11})$') {
        Write-Warning "Missing or invalid direct video link for $($track.Song)"
        $missing++
        continue
    }
    if ($Preview) {
        Write-Host "$($track.Song) -> $($track.VideoUrl)"
        continue
    }
    if (-not $downloader) {
        $downloader = (Get-Command yt-dlp -CommandType Application -ErrorAction Stop).Source
        Get-Command ffmpeg, ffprobe -CommandType Application -ErrorAction Stop | Out-Null
        $runtimeArgs = @()
        if (Get-Command node -CommandType Application -ErrorAction SilentlyContinue) {
            $runtimeArgs = @('--js-runtimes', 'node')
        }
        New-Item -ItemType Directory -Path $Destination -Force | Out-Null
        $archive = Join-Path $Destination "downloaded-$Format.txt"
        $downloadArgs = @(
            '--ignore-config', '--no-playlist', '--no-overwrites', '--no-progress'
            '--remote-components', 'ejs:github'
            '--socket-timeout', '15', '--retries', '2', '--fragment-retries', '2'
            '--download-archive', $archive
            '--extract-audio', '--audio-format', $Format
            '--windows-filenames', '--paths', $Destination
            '--output', '%(title).180B [%(id)s].%(ext)s'
        )
    }
    & $downloader @downloadArgs @runtimeArgs -- $track.VideoUrl
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Download failed for $($track.Song)"
        $failed++
    }
}

if ($missing -or $failed) { throw "$missing missing or invalid link(s), $failed failed download(s)." }
