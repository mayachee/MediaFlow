param(
    [Parameter(Mandatory, Position = 0)]
    [string]$SongList,
    [string]$OutputCsv = (Join-Path (Get-Location) 'youtube-song-links.csv'),
    [string]$Destination,
    [ValidateSet('mp3', 'm4a', 'wav')]
    [string]$Format = 'mp3',
    [switch]$LinksOnly
)

$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
$apiKey = $env:YOUTUBE_API_KEY
$ytDlp = Get-Command yt-dlp -CommandType Application -ErrorAction SilentlyContinue
$songs = @(Get-Content -LiteralPath $SongList -Encoding UTF8 | ForEach-Object {
    $song = ($_ -replace '^\s*(?:\d+[.)]\s+|[-*]\s+)', '').Trim()
    if ($song) { $song }
})
if ($songs.Count -eq 0) { throw 'Add at least one song to the input file.' }

function ConvertTo-MatchText([string]$Text) {
    $unaccented = $Text.Normalize([Text.NormalizationForm]::FormD) -replace '\p{Mn}', ''
    $noApostrophes = $unaccented.ToLowerInvariant() -replace "['\u2018\u2019]", ''
    return ' ' + ($noApostrophes -replace '[^\p{L}\p{Nd}]+', ' ').Trim() + ' '
}

function Find-YouTubeCandidates([string]$Query) {
    if ($apiKey) {
        $endpoint = 'https://www.googleapis.com/youtube/v3/search?part=snippet&type=video&maxResults=5&q=' +
            [uri]::EscapeDataString($Query)
        try {
            $response = Invoke-RestMethod -Uri $endpoint -Headers @{ 'X-Goog-Api-Key' = $apiKey } -TimeoutSec 20
            if ($response.items) {
                foreach ($item in $response.items) {
                    [pscustomobject]@{
                        id = $item.id.videoId
                        title = [Net.WebUtility]::HtmlDecode($item.snippet.title)
                        channel = [Net.WebUtility]::HtmlDecode($item.snippet.channelTitle)
                    }
                }
                return
            }
        } catch {
            Write-Verbose 'YouTube Data API lookup failed. Trying yt-dlp.'
        }
    }

    if (-not $ytDlp) { throw 'Install yt-dlp and ensure it is on PATH.' }
    $json = & $ytDlp.Source --ignore-config --no-cache-dir --no-update --flat-playlist --dump-single-json --socket-timeout 15 --retries 1 -- "ytsearch5:$Query"
    if ($LASTEXITCODE -ne 0) { throw 'yt-dlp could not search YouTube.' }
    ($json | ConvertFrom-Json).entries
}

$savedLinks = @{}
if (Test-Path -LiteralPath $OutputCsv -PathType Leaf) {
    foreach ($row in (Import-Csv -LiteralPath $OutputCsv -Encoding UTF8)) {
        if ($row.Song -and $row.VideoUrl -cmatch '^https://www\.youtube\.com/watch\?v=[A-Za-z0-9_-]{11}$') {
            $savedLinks[$row.Song] = $row
        }
    }
}

$results = foreach ($song in $songs) {
    if ($savedLinks.ContainsKey($song)) {
        $savedLinks[$song]
        continue
    }

    Write-Host "Finding $song"
    $query = $song -replace '\s+\((?:trailer\s+\d+|launch trailer and soundtrack|pre-load video and soundtrack|original score)\)$', ''
    $parts = $query -split '\s+[-\u2013\u2014]\s+', 2
    $title = ConvertTo-MatchText $parts[-1]
    $artist = $null
    if ($parts.Count -eq 2) {
        $mainArtist = ($parts[0] -split '(?:,|\s+&\s+|\s+feat\.?\s+)', 2)[0] -replace '^the\s+', ''
        $artist = ConvertTo-MatchText $mainArtist
    }
    $term = "$($parts -join ' ') official audio"
    $result = [ordered]@{
        Song = $song
        VideoUrl = ''
        VideoTitle = ''
        Channel = ''
        SearchUrl = 'https://www.youtube.com/results?search_query=' + [uri]::EscapeDataString($term)
        Status = 'No matching video'
    }

    try {
        $video = Find-YouTubeCandidates $term | Where-Object {
            $_.id -cmatch '^[A-Za-z0-9_-]{11}$' -and
            (ConvertTo-MatchText $_.title).Contains($title) -and
            (-not $artist -or (ConvertTo-MatchText "$($_.title) $($_.channel)").Contains($artist))
        } | Select-Object -First 1
        if ($video) {
            $result.VideoUrl = 'https://www.youtube.com/watch?v=' + $video.id
            $result.VideoTitle = $video.title
            $result.Channel = $video.channel
            $result.Status = 'Matched'
        }
    } catch {
        Write-Warning "Lookup failed for ${song}. $($_.Exception.Message)"
        $result.Status = 'Lookup failed'
    }
    [pscustomobject]$result
}

$results | Select-Object Song,VideoUrl,VideoTitle,Channel,SearchUrl,Status |
    Export-Csv -LiteralPath $OutputCsv -NoTypeInformation -Encoding UTF8
$matched = @($results | Where-Object VideoUrl).Count
Write-Host "Saved $matched of $($songs.Count) direct video links to $OutputCsv"

if (-not $LinksOnly) {
    if ($matched -eq 0) { throw 'No direct video links are available to download.' }
    & (Join-Path $PSScriptRoot 'save-youtube-song-audio.ps1') -InputCsv $OutputCsv -Destination $Destination -Format $Format
}
