param(
    [Parameter(Position=0)]
    [ValidateSet('search', 'test', 'help')]
    [string]$Target = 'help',
    [string]$Audio,
    [string]$Keywords,
    [string]$Mood = 'cinematic',
    [int]$Count = 10,
    [int]$DownloadTop = 0
)

$pythonExecutable = 'py'
$pythonArguments = @('-3.11')
$localPython = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
if (Test-Path -LiteralPath $localPython) { $pythonExecutable=$localPython; $pythonArguments=@() }
Push-Location $PSScriptRoot
try {
    switch ($Target) {
        'search' {
            if (-not $Audio) { throw 'Supply -Audio with a song path' }
            $searchArguments = @('find_matching_clips.py', '--audio', $Audio, '--mood', $Mood,
                                '--count', "$Count", '--download-top', "$DownloadTop")
            if ($Keywords) { $searchArguments += @('--keywords', $Keywords) }
            & $pythonExecutable @pythonArguments @searchArguments
            if ($LASTEXITCODE -ne 0) { throw 'Clip search failed; see the saved diagnostics' }
        }
        'test' {
            & $pythonExecutable @pythonArguments -m unittest discover -s tests -v
            if ($LASTEXITCODE -ne 0) { throw 'Clip finder tests failed' }
        }
        'help' {
            Write-Host '.\run.ps1 search -Audio <song-path> -Keywords <visual-topic> [-DownloadTop 2]'
            Write-Host '.\run.ps1 test'
            Write-Host 'Dependencies: py -3.11 -m pip install -r requirements.txt'
            Write-Host 'Uses its own .venv when present, otherwise py -3.11.'
        }
    }
} finally { Pop-Location }
