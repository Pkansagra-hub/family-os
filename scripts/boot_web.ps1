# scripts/boot_web.ps1 — Boot the K1 production Web UI layer.
#
# Wraps `python -m ui.web` so engineers do not have to remember the right
# PYTHONPATH and flag combinations. Mirrors `scripts/boot_kernel.ps1`.
#
# Usage:
#   .\scripts\boot_web.ps1                       # production mode (requires GOOGLE_API_KEY)
#   .\scripts\boot_web.ps1 -TestMode             # use in-process test LLM adapter (no key needed)
#   .\scripts\boot_web.ps1 -Port 9000 -Host 0.0.0.0
#   .\scripts\boot_web.ps1 -TestMode -LogLevel DEBUG
#
# Production mode requires GOOGLE_API_KEY to be set in the environment:
#   $env:GOOGLE_API_KEY = "AIza..."   (PowerShell)
#   export GOOGLE_API_KEY="AIza..."   (bash / zsh)

[CmdletBinding()]
param(
    [int] $Port = 8765,
    [string] $WebHost = "127.0.0.1",
    [switch] $TestMode,
    [ValidateSet("DEBUG", "INFO", "WARNING", "ERROR")]
    [string] $LogLevel = "INFO"
)

$ErrorActionPreference = "Stop"

# Resolve workspace root (this script lives at <root>\scripts\boot_web.ps1)
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$WorkspaceRoot = Split-Path -Parent $ScriptDir

Push-Location $WorkspaceRoot
try {
    if (-not $env:PYTHONPATH) {
        $env:PYTHONPATH = "."
    } elseif ($env:PYTHONPATH -notlike "*$WorkspaceRoot*" -and $env:PYTHONPATH -notlike "*.*") {
        $env:PYTHONPATH = ".;$env:PYTHONPATH"
    }

    $argList = @("-m", "ui.web", "--port", $Port, "--host", $WebHost, "--log-level", $LogLevel)
    if ($TestMode) {
        $argList += "--test-mode"
    }

    Write-Host ""
    Write-Host "  FamilyOS K1 Concierge -- Web UI" -ForegroundColor Cyan
    Write-Host "  http://$WebHost`:$Port" -ForegroundColor Green
    if ($TestMode) {
        Write-Host "  Mode: TEST (in-process LLM adapter)" -ForegroundColor Yellow
    } else {
        if (-not $env:GOOGLE_API_KEY) {
            Write-Host "  ERROR: GOOGLE_API_KEY is not set." -ForegroundColor Red
            Write-Host "  Set it first:  `$env:GOOGLE_API_KEY = 'AIza...'" -ForegroundColor Red
            exit 1
        }
        Write-Host "  Mode: PRODUCTION (Gemini via ModelHub)" -ForegroundColor Green
    }
    Write-Host ""

    & python @argList
}
finally {
    Pop-Location
}
