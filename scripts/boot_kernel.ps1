# Boot the K1 Concierge chat REPL with Google Gemini via Model Hub.
#
# Usage:
#   pwsh scripts/boot_kernel.ps1                # production (Gemini)
#   pwsh scripts/boot_kernel.ps1 -Test          # canned "OK" responses
#   pwsh scripts/boot_kernel.ps1 -LogLevel INFO # verbose logs
#
# Loads .env from poc/chat_experience_poc/.env (git-ignored) so
# GOOGLE_API_KEY / GOOGLE_MODEL / LLM_PROVIDER / Google Cloud project vars are available to the REPL.
param(
    [switch]$Test,
    [string]$LogLevel = "WARNING",
    [string]$EnvFile = "poc\chat_experience_poc\.env"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $EnvFile)) {
    Write-Error ".env file not found at $EnvFile"
    exit 1
}

# Load only the keys we care about; strip surrounding quotes.
$loadedKeys = @()
Get-Content $EnvFile |
Where-Object { $_ -match '^(GOOGLE_API_KEY|GOOGLE_MODEL|LLM_PROVIDER|GOOGLE_GENAI_USE_VERTEXAI|GOOGLE_CLOUD_PROJECT|GOOGLE_CLOUD_LOCATION|GOOGLE_CLOUD_MODEL|GOOGLE_PROJECT_ID|GOOGLE_LOCATION|VERTEX_MODEL)=' -and $_ -notmatch '^\s*#' } |
ForEach-Object {
    $pair = $_ -split '=', 2
    $key = $pair[0].Trim()
    $val = $pair[1].Trim().Trim('"').Trim("'")
    Set-Item -Path "env:$key" -Value $val
    $loadedKeys += $key
}

if (-not $env:LLM_PROVIDER) {
    $env:LLM_PROVIDER = "google"
}
$llmProvider = $env:LLM_PROVIDER.Trim().ToLowerInvariant()
$vertexProviders = @("vertex", "vertex-ai", "vertex_ai", "agent-platform", "agent_platform", "gemini-enterprise", "gemini_enterprise", "google-cloud", "google_cloud")
$googleProviders = @("google", "gemini", "developer", "ai-studio", "ai_studio", "google-ai", "google_ai")
$deepseekProviders = @("deepseek", "deepseek-v4", "deepseek_v4")

if (-not $Test) {
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
            Write-Error "LLM_PROVIDER=vertex requires GOOGLE_CLOUD_PROJECT or GOOGLE_PROJECT_ID"
            exit 1
        }
    }
    elseif ($googleProviders -contains $llmProvider) {
        if (-not $env:GOOGLE_API_KEY) {
            Write-Error "LLM_PROVIDER=google requires GOOGLE_API_KEY"
            exit 1
        }
    }
    elseif ($deepseekProviders -contains $llmProvider) {
        if (-not $env:DEEPSEEK_API_KEY) {
            Write-Error "LLM_PROVIDER=deepseek requires DEEPSEEK_API_KEY"
            exit 1
        }
    }
    else {
        Write-Error "Unsupported LLM_PROVIDER '$llmProvider'. Supported: google, vertex, deepseek."
        exit 1
    }
}

Write-Host "Loaded env: $($loadedKeys -join ', ')" -ForegroundColor DarkGray
Write-Host "LLM_PROVIDER: $env:LLM_PROVIDER" -ForegroundColor DarkGray
if ($vertexProviders -contains $llmProvider) {
    Write-Host "GOOGLE_CLOUD_PROJECT: $env:GOOGLE_CLOUD_PROJECT" -ForegroundColor DarkGray
    Write-Host "GOOGLE_CLOUD_LOCATION: $env:GOOGLE_CLOUD_LOCATION" -ForegroundColor DarkGray
    Write-Host "VERTEX_MODEL: $env:VERTEX_MODEL" -ForegroundColor DarkGray
}
else {
    Write-Host "GOOGLE_MODEL: $env:GOOGLE_MODEL" -ForegroundColor DarkGray
}
Write-Host ""

$pyArgs = @("--log-level=$LogLevel")
if (-not $Test) { $pyArgs += "--model-hub" }

python -m k1.kernel.chat_repl @pyArgs
