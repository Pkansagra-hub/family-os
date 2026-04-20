# Boot the K1 Concierge chat REPL with Google Gemini via Model Hub.
#
# Usage:
#   pwsh scripts/boot_kernel.ps1                # production (Gemini)
#   pwsh scripts/boot_kernel.ps1 -Test          # canned "OK" responses
#   pwsh scripts/boot_kernel.ps1 -LogLevel INFO # verbose logs
#
# Loads .env from poc/chat_experience_poc/.env (git-ignored) so
# GOOGLE_API_KEY / GOOGLE_MODEL / LLM_PROVIDER are available to the REPL.
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
Where-Object { $_ -match '^(GOOGLE_API_KEY|GOOGLE_MODEL|LLM_PROVIDER|GOOGLE_PROJECT_ID|GOOGLE_LOCATION|VERTEX_MODEL)=' -and $_ -notmatch '^\s*#' } |
ForEach-Object {
    $pair = $_ -split '=', 2
    $key = $pair[0].Trim()
    $val = $pair[1].Trim().Trim('"').Trim("'")
    Set-Item -Path "env:$key" -Value $val
    $loadedKeys += $key
}

if ($loadedKeys -notcontains 'GOOGLE_API_KEY' -and -not $Test) {
    Write-Error "GOOGLE_API_KEY not found in $EnvFile"
    exit 1
}

Write-Host "Loaded env: $($loadedKeys -join ', ')" -ForegroundColor DarkGray
Write-Host "GOOGLE_MODEL: $env:GOOGLE_MODEL" -ForegroundColor DarkGray
Write-Host ""

$pyArgs = @("--log-level=$LogLevel")
if (-not $Test) { $pyArgs += "--model-hub" }

python -m k1.kernel.chat_repl @pyArgs
