# scripts/boot_web.ps1 — Boot the K1 production Web UI layer.
#
# Wraps `python -m ui.web` so engineers do not have to remember the right
# PYTHONPATH and flag combinations. Mirrors `scripts/boot_kernel.ps1`.
#
# Usage:
#   .\scripts\boot_web.ps1                       # production mode (requires provider auth)
#   .\scripts\boot_web.ps1 -TestMode             # use in-process test LLM adapter (no key needed)
#   .\scripts\boot_web.ps1 -Port 9000 -Host 0.0.0.0
#   .\scripts\boot_web.ps1 -TestMode -LogLevel DEBUG
#
# Production provider selection:
#   $env:LLM_PROVIDER = "vertex"      # Google Cloud / Agent Platform billing
#   $env:GOOGLE_CLOUD_PROJECT = "..." # or legacy GOOGLE_PROJECT_ID
#   $env:GOOGLE_CLOUD_LOCATION = "us-central1"
#   $env:GOOGLE_API_KEY = "..."       # optional Cloud API-key auth; ADC also works
#
# Legacy Developer API mode remains available with:
#   $env:LLM_PROVIDER = "google"
#   $env:GOOGLE_API_KEY = "AIza..."

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
    }
    elseif ($env:PYTHONPATH -notlike "*$WorkspaceRoot*" -and $env:PYTHONPATH -notlike "*.*") {
        $env:PYTHONPATH = ".;$env:PYTHONPATH"
    }

    if (-not $env:K1_SPATIAL_GEOCODER) {
        $env:K1_SPATIAL_GEOCODER = "nominatim"
    }

    $argList = @("-m", "ui.web", "--port", $Port, "--host", $WebHost, "--log-level", $LogLevel)
    if ($TestMode) {
        $argList += "--test-mode"
    }

    Write-Host ""
    Write-Host "  FamilyOS K1 Concierge -- Web UI" -ForegroundColor Cyan
    Write-Host "  http://$WebHost`:$Port" -ForegroundColor Green
    Write-Host "  Spatial geocoder: $env:K1_SPATIAL_GEOCODER" -ForegroundColor DarkGray
    if ($TestMode) {
        Write-Host "  Mode: TEST (in-process LLM adapter)" -ForegroundColor Yellow
    }
    else {
        $llmProvider = if ($env:LLM_PROVIDER) { $env:LLM_PROVIDER.Trim().ToLowerInvariant() } elseif ($env:GOOGLE_GENAI_USE_VERTEXAI -match '^(1|true|yes|on)$') { "vertex" } else { "google" }
        $vertexProviders = @("vertex", "vertex-ai", "vertex_ai", "agent-platform", "agent_platform", "gemini-enterprise", "gemini_enterprise", "google-cloud", "google_cloud")
        $googleProviders = @("google", "gemini", "developer", "ai-studio", "ai_studio", "google-ai", "google_ai")

        if ($vertexProviders -contains $llmProvider) {
            $env:GOOGLE_GENAI_USE_VERTEXAI = "True"
            if (-not $env:GOOGLE_CLOUD_PROJECT -and $env:GOOGLE_PROJECT_ID) {
                $env:GOOGLE_CLOUD_PROJECT = $env:GOOGLE_PROJECT_ID
            }
            if (-not $env:GOOGLE_CLOUD_LOCATION -and $env:GOOGLE_LOCATION) {
                $env:GOOGLE_CLOUD_LOCATION = $env:GOOGLE_LOCATION
            }
            if (-not $env:GOOGLE_CLOUD_LOCATION) {
                $env:GOOGLE_CLOUD_LOCATION = "global"
            }
            if (-not $env:GOOGLE_CLOUD_PROJECT) {
                Write-Host "  ERROR: LLM_PROVIDER=vertex requires GOOGLE_CLOUD_PROJECT or GOOGLE_PROJECT_ID." -ForegroundColor Red
                exit 1
            }
            $authMode = if ($env:GOOGLE_API_KEY) { "Google Cloud API key" } else { "ADC/service account" }
            Write-Host "  Mode: PRODUCTION (Gemini Enterprise Agent Platform)" -ForegroundColor Green
            Write-Host "  Provider: vertex project=$env:GOOGLE_CLOUD_PROJECT location=$env:GOOGLE_CLOUD_LOCATION auth=$authMode" -ForegroundColor DarkGray
        }
        elseif ($googleProviders -contains $llmProvider) {
            if (-not $env:GOOGLE_API_KEY) {
                Write-Host "  ERROR: LLM_PROVIDER=google requires GOOGLE_API_KEY." -ForegroundColor Red
                Write-Host "  For Google Cloud billing, set LLM_PROVIDER=vertex plus GOOGLE_CLOUD_PROJECT/GOOGLE_CLOUD_LOCATION." -ForegroundColor Red
                exit 1
            }
            Write-Host "  Mode: PRODUCTION (Gemini Developer API via ModelHub)" -ForegroundColor Green
            Write-Host "  Provider: google endpoint=generativelanguage.googleapis.com" -ForegroundColor DarkGray
        }
        else {
            Write-Host "  ERROR: unsupported LLM_PROVIDER='$llmProvider'. Supported: google, vertex." -ForegroundColor Red
            exit 1
        }
    }
    Write-Host ""

    & python @argList
}
finally {
    Pop-Location
}
