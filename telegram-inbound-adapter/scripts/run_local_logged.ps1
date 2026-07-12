# Runs scripts/run_local.py and tees its console output (spans, metrics,
# logs, everything) to logs/<yyyy-MM-dd_HH-mm-ss>.txt, while still showing
# it live in the terminal.
#
# Run from the project root: .\scripts\run_local_logged.ps1 [port]

param(
    [int]$Port = 8000
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

# -u: unbuffered stdout/stderr. Without it, Python fully buffers its output
# once stdout isn't a real console (piped through cmd here), so nothing shows
# up live -- it just sits in a buffer until the process exits.
#
# Routed through cmd.exe so stdout+stderr merge as plain text before
# PowerShell sees them. Piping a native exe's stderr straight into PowerShell
# via 2>&1 wraps each line as a NativeCommandError (ugly output, $? goes
# false) -- cmd.exe avoids that entirely.
#
# Tee-Object has no -Encoding param in Windows PowerShell 5.1 and defaults to
# UTF-16, so write to the file manually via StreamWriter (UTF-8, no BOM)
# instead, flushing after every line so Ctrl+C doesn't lose buffered output.
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
$writer = New-Object System.IO.StreamWriter($logFile, $false, $utf8NoBom)
try {
    & cmd /c "`"$python`" -u `"$root\scripts\run_local.py`" $Port 2>&1" | ForEach-Object {
        Write-Host $_
        $writer.WriteLine($_)
        $writer.Flush()
    }
} finally {
    $writer.Close()
}
