#!/usr/bin/env pwsh
# Run 48-hour comprehensive traffic generation to Azure VM
# This script runs in a separate PowerShell window and continues even if VS Code closes

$ErrorActionPreference = "Stop"
$vm_ip = "4.227.232.239"
$repoRoot = "D:\memory_kernel"
$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"
$scriptPath = Join-Path $repoRoot "scripts\traffic_generator.py"

Write-Host "`n============================================" -ForegroundColor Cyan
Write-Host "  48-HOUR COMPREHENSIVE TRAFFIC GENERATOR" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Target:    Azure VM ($vm_ip)" -ForegroundColor Yellow
Write-Host "Scenario:  Comprehensive (commands + queries + SSE)" -ForegroundColor Yellow
Write-Host "Rate:      10 requests/second" -ForegroundColor Yellow
Write-Host "Duration:  48 hours" -ForegroundColor Yellow
Write-Host ""
Write-Host "This window will stay open and show real-time traffic logs." -ForegroundColor Gray
Write-Host "You can close VS Code - this will keep running!" -ForegroundColor Green
Write-Host ""
Write-Host "Press Ctrl+C to stop traffic generation." -ForegroundColor Red
Write-Host ""
Start-Sleep -Seconds 3

# Verify Python environment
if (-not (Test-Path $pythonExe)) {
    Write-Host "❌ ERROR: Python executable not found at $pythonExe" -ForegroundColor Red
    Write-Host "   Please ensure .venv is created: python -m venv .venv" -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit 1
}

if (-not (Test-Path $scriptPath)) {
    Write-Host "❌ ERROR: Traffic generator not found at $scriptPath" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

# Set environment
$env:PYTHONPATH = $repoRoot
Set-Location $repoRoot

Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Starting traffic generation..." -ForegroundColor Cyan
Write-Host ""

try {
    # Run traffic generator
    & $pythonExe $scriptPath --endpoint "http://${vm_ip}:8080" --rate 10 --duration 48h --scenario comprehensive

    Write-Host ""
    Write-Host "✅ Traffic generation completed successfully!" -ForegroundColor Green

}
catch {
    Write-Host ""
    Write-Host "❌ ERROR: Traffic generation failed" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host ""
    Write-Host "Troubleshooting:" -ForegroundColor Yellow
    Write-Host "  1. Check if Azure VM is accessible: curl http://${vm_ip}:8080/healthz" -ForegroundColor Gray
    Write-Host "  2. Verify Python packages: .venv\Scripts\python.exe -m pip list | findstr httpx" -ForegroundColor Gray
    Write-Host "  3. Check kernel logs: ssh azureuser@${vm_ip} 'sudo docker logs k0-kernel'" -ForegroundColor Gray
}

Write-Host ""
Write-Host "Press Enter to close this window..." -ForegroundColor Gray
Read-Host
