# Runs scripts/run_local.py and tees its console output (spans, metrics,
# logs, everything) to logs/<yyyy-MM-dd_HH-mm-ss>.txt, while still showing
# it live in the terminal.
#
# Run from the project root: .\scripts\run_local_logged.ps1 path\to\event.json

param(
    [Parameter(Mandatory = $true)]
    [string]$EventPath
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$logsDir = Join-Path $root "logs"
New-Item -ItemType Directory -Force -Path $logsDir | Out-Null

$timestamp = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"
$logFile = Join-Path $logsDir "$timestamp.txt"
$python = Join-Path $root ".venv\Scripts\python.exe"

Write-Host "Logging to $logFile"

# -u: unbuffered stdout/stderr, same reasoning as telegram-inbound-adapter's
# equivalent script -- see that project's run_local_logged.ps1 for details.
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
$writer = New-Object System.IO.StreamWriter($logFile, $false, $utf8NoBom)
try {
    & cmd /c "`"$python`" -u `"$root\scripts\run_local.py`" `"$EventPath`" 2>&1" | ForEach-Object {
        Write-Host $_
        $writer.WriteLine($_)
        $writer.Flush()
    }
} finally {
    $writer.Close()
}
