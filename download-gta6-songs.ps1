param(
    [Parameter(Mandatory)]
    [string]$Manifest,

    [string]$Destination = (Join-Path $PSScriptRoot 'gta6-songs')
)

$ErrorActionPreference = 'Stop'
$tracks = Import-Csv -LiteralPath $Manifest
New-Item -ItemType Directory -Path $Destination -Force | Out-Null
$failed = 0

foreach ($track in $tracks) {
    $temporary = $null
    try {
        $name = $track.FileName
        if ($name -notmatch '^.+\.(mp3|wav|flac|m4a|aiff|ogg|zip)$' -or
            $name.IndexOfAny([IO.Path]::GetInvalidFileNameChars()) -ge 0) {
            throw 'Use a plain filename with a supported audio or ZIP extension.'
        }
        $url = [uri]$track.Url
        if (-not $url.IsAbsoluteUri -or $url.Scheme -ne 'https') {
            throw 'Use a direct HTTPS download URL.'
        }
        $target = Join-Path $Destination $name
        if (Test-Path -LiteralPath $target) {
            Write-Host "Already saved $name"
            continue
        }
        $temporary = Join-Path $Destination ([guid]::NewGuid().ToString() + '.part')
        $response = Invoke-WebRequest -Uri $url -OutFile $temporary -PassThru -UseBasicParsing
        $type = [string]($response.Headers['Content-Type'] | Select-Object -First 1)
        if ($type -notmatch '^(audio/|application/(octet-stream|zip|x-zip-compressed|x-flac|ogg))' -or
            (Get-Item -LiteralPath $temporary).Length -eq 0) {
            throw 'The server did not return an audio file or archive. Check for an expired link or a sign-in page.'
        }
        [IO.File]::Move((Get-Item -LiteralPath $temporary).FullName, [IO.Path]::Combine((Get-Item -LiteralPath $Destination).FullName, $name))
        Write-Host "Saved $name"
    }
    catch {
        $failed++
        Write-Warning "Could not save '$($track.FileName)' ($($_.Exception.GetType().Name)). Check the download link and filename."
    }
    finally {
        if ($temporary -and (Test-Path -LiteralPath $temporary)) {
            Remove-Item -LiteralPath $temporary -Force
        }
    }
}

if ($failed) { throw "$failed download(s) failed." }
