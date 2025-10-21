# K0 Telemetry Preview Stack Helper Scripts
#
# Usage:
#   PowerShell: .\start-preview.ps1
#   Bash/Zsh:   ./start-preview.sh

Write-Host "🚀 Starting K0 Telemetry Preview Stack..." -ForegroundColor Green

# Change to preview directory
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

# Check if Docker is running
try {
    docker info > $null 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "❌ Docker is not running. Please start Docker Desktop first." -ForegroundColor Red
        exit 1
    }
}
catch {
    Write-Host "❌ Docker is not installed or not in PATH." -ForegroundColor Red
    exit 1
}

# Render dashboards and rules first
Write-Host "📊 Rendering dashboards and alert rules..." -ForegroundColor Cyan
$RepoRoot = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $ScriptDir))
Push-Location $RepoRoot
python -m k0.telemetry.render --verbose
$RenderExitCode = $LASTEXITCODE
Pop-Location
if ($RenderExitCode -ne 0) {
    Write-Host "❌ Failed to render telemetry artifacts." -ForegroundColor Red
    exit 1
}

# Start Docker Compose stack
Write-Host "🐳 Starting Docker Compose services..." -ForegroundColor Cyan
docker-compose up -d

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "✅ K0 Telemetry Preview Stack is running!" -ForegroundColor Green
    Write-Host ""
    Write-Host "📊 Grafana:    http://localhost:3000  (admin/admin)" -ForegroundColor Yellow
    Write-Host "📈 Prometheus: http://localhost:9090" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "💡 Tip: Start the K0 kernel on port 8080 (or run the container bundle) to expose metrics at /metrics." -ForegroundColor Cyan
    Write-Host ""
    Write-Host "To stop: docker-compose down" -ForegroundColor Gray
}
else {
    Write-Host "❌ Failed to start preview stack." -ForegroundColor Red
    exit 1
}
