#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Deploy K0 Kernel to Azure for 48-hour burn-in test.

.DESCRIPTION
    Builds fresh Docker image, pushes to ACR, updates Azure VM deployment,
    and starts comprehensive traffic generation.

.PARAMETER ResourceGroup
    Azure resource group name (default: k0-burnin-rg)

.PARAMETER AcrName
    Azure Container Registry name (auto-detect if not specified)

.PARAMETER VmName
    Azure VM name (default: k0-burnin-vm)

.PARAMETER SkipBuild
    Skip Docker build and use existing local image

.PARAMETER SkipTraffic
    Skip traffic generator (deploy only)

.EXAMPLE
    .\scripts\deploy_azure_burnin.ps1

.EXAMPLE
    .\scripts\deploy_azure_burnin.ps1 -ResourceGroup my-rg -AcrName myacr1234
#>

param(
    [string]$ResourceGroup = "k0-burnin-rg",
    [string]$AcrName = "",
    [string]$VmName = "k0-burnin-vm",
    [switch]$SkipBuild,
    [switch]$SkipTraffic
)

$ErrorActionPreference = "Stop"
$startTime = Get-Date

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  K0 AZURE 48-HOUR BURN-IN DEPLOYMENT" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

Write-Host "[CONFIG]" -ForegroundColor Yellow
Write-Host "  Resource Group: $ResourceGroup" -ForegroundColor White
Write-Host "  VM Name: $VmName" -ForegroundColor White
Write-Host "  Skip Build: $SkipBuild" -ForegroundColor White
Write-Host "  Skip Traffic: $SkipTraffic`n" -ForegroundColor White

# ============================================================================
# STEP 1: Verify Azure Resources
# ============================================================================

Write-Host "[STEP 1/6] Verifying Azure resources..." -ForegroundColor Cyan

try {
    # Check if logged in
    $account = az account show 2>$null | ConvertFrom-Json
    Write-Host "  [OK] Logged in as: $($account.user.name)" -ForegroundColor Green
}
catch {
    Write-Host "  [ERROR] Not logged in to Azure. Run: az login" -ForegroundColor Red
    exit 1
}

# Check resource group exists
try {
    az group show --name $ResourceGroup --output none 2>$null
    Write-Host "  [OK] Resource group exists: $ResourceGroup" -ForegroundColor Green
}
catch {
    Write-Host "  [ERROR] Resource group not found: $ResourceGroup" -ForegroundColor Red
    Write-Host "  Create it with: az group create --name $ResourceGroup --location eastus" -ForegroundColor Yellow
    exit 1
}

# Auto-detect ACR if not specified
if ([string]::IsNullOrEmpty($AcrName)) {
    Write-Host "  [INFO] Auto-detecting ACR name..." -ForegroundColor Yellow
    $acrs = az acr list --resource-group $ResourceGroup --query "[].name" -o tsv 2>$null
    if ($acrs) {
        $AcrName = $acrs.Split("`n")[0].Trim()
        Write-Host "  [OK] Found ACR: $AcrName" -ForegroundColor Green
    }
    else {
        Write-Host "  [ERROR] No ACR found in resource group" -ForegroundColor Red
        Write-Host "  Create one with Step 1.4 from the burn-in plan" -ForegroundColor Yellow
        exit 1
    }
}

# Get ACR details
$acrLoginServer = az acr show --name $AcrName --resource-group $ResourceGroup --query loginServer -o tsv
$acrUsername = $AcrName
$acrPassword = az acr credential show --name $AcrName --resource-group $ResourceGroup --query "passwords[0].value" -o tsv

Write-Host "  [OK] ACR Login Server: $acrLoginServer" -ForegroundColor Green

# Check VM exists
try {
    $vmIp = az vm show -d --resource-group $ResourceGroup --name $VmName --query publicIps -o tsv 2>$null
    Write-Host "  [OK] VM exists: $VmName ($vmIp)" -ForegroundColor Green
}
catch {
    Write-Host "  [ERROR] VM not found: $VmName" -ForegroundColor Red
    Write-Host "  Create it with Step 3.2A from the burn-in plan" -ForegroundColor Yellow
    exit 1
}

# ============================================================================
# STEP 2: Build Docker Image
# ============================================================================

if (-not $SkipBuild) {
    Write-Host "`n[STEP 2/6] Building fresh Docker image..." -ForegroundColor Cyan

    $imageName = "k0-kernel-local:latest"
    $buildStart = Get-Date

    Write-Host "  [INFO] Running: docker build -t $imageName ." -ForegroundColor Yellow

    # Build from repo root
    Push-Location $PSScriptRoot\..
    try {
        docker build -t $imageName -f Dockerfile .
        if ($LASTEXITCODE -ne 0) {
            Write-Host "  [ERROR] Docker build failed" -ForegroundColor Red
            exit 1
        }

        $buildDuration = ((Get-Date) - $buildStart).TotalSeconds
        Write-Host "  [OK] Build completed in $([math]::Round($buildDuration, 1))s" -ForegroundColor Green
    }
    finally {
        Pop-Location
    }
}
else {
    Write-Host "`n[STEP 2/6] Skipping build (using existing image)..." -ForegroundColor Yellow
}

# ============================================================================
# STEP 3: Tag and Push to ACR
# ============================================================================

Write-Host "`n[STEP 3/6] Pushing image to Azure Container Registry..." -ForegroundColor Cyan

$taggedImage = "${acrLoginServer}/k0-kernel:burnin-v$(Get-Date -Format 'yyyyMMdd-HHmmss')"
$latestImage = "${acrLoginServer}/k0-kernel:burnin-latest"

Write-Host "  [INFO] Logging in to ACR..." -ForegroundColor Yellow
az acr login --name $AcrName 2>&1 | Out-Null

Write-Host "  [INFO] Tagging images..." -ForegroundColor Yellow
docker tag k0-kernel-local:latest $taggedImage
docker tag k0-kernel-local:latest $latestImage

Write-Host "  [INFO] Pushing to ACR (this may take a few minutes)..." -ForegroundColor Yellow
$pushStart = Get-Date

docker push $taggedImage
if ($LASTEXITCODE -ne 0) {
    Write-Host "  [ERROR] Docker push failed" -ForegroundColor Red
    exit 1
}

docker push $latestImage
if ($LASTEXITCODE -ne 0) {
    Write-Host "  [ERROR] Docker push failed" -ForegroundColor Red
    exit 1
}

$pushDuration = ((Get-Date) - $pushStart).TotalSeconds
Write-Host "  [OK] Pushed to ACR in $([math]::Round($pushDuration, 1))s" -ForegroundColor Green
Write-Host "  [INFO] Tagged as: $taggedImage" -ForegroundColor Cyan
Write-Host "  [INFO] Latest: $latestImage" -ForegroundColor Cyan

# ============================================================================
# STEP 4: Update VM Deployment
# ============================================================================

Write-Host "`n[STEP 4/6] Updating deployment on Azure VM..." -ForegroundColor Cyan

Write-Host "  [INFO] Connecting to VM: azureuser@$vmIp" -ForegroundColor Yellow

# Pull latest image
Write-Host "  [INFO] Pulling latest image on VM..." -ForegroundColor Yellow
ssh azureuser@$vmIp "sudo docker login $acrLoginServer -u $acrUsername -p $acrPassword" 2>&1 | Out-Null
ssh azureuser@$vmIp "sudo docker pull $latestImage"
ssh azureuser@$vmIp "sudo docker tag $latestImage k0-kernel-local:latest"

# Restart services
Write-Host "  [INFO] Restarting container stack..." -ForegroundColor Yellow
ssh azureuser@$vmIp "cd memory_kernel/k0/deployment/compose/generated/local-single-node && sudo docker compose -f docker-compose.yml -f local-single-node-telemetry.yml down"
ssh azureuser@$vmIp "cd memory_kernel/k0/deployment/compose/generated/local-single-node && sudo docker compose -f docker-compose.yml -f local-single-node-telemetry.yml up -d"

# Wait for services to be healthy
Write-Host "  [INFO] Waiting for services to start (30s)..." -ForegroundColor Yellow
Start-Sleep -Seconds 30

# ============================================================================
# STEP 5: Verify Deployment
# ============================================================================

Write-Host "`n[STEP 5/6] Verifying deployment..." -ForegroundColor Cyan

$allHealthy = $true

# Check kernel
try {
    $response = Invoke-WebRequest -Uri "http://${vmIp}:8080/healthz" -UseBasicParsing -TimeoutSec 10
    Write-Host "  [OK] Kernel API: http://${vmIp}:8080" -ForegroundColor Green
}
catch {
    Write-Host "  [ERROR] Kernel health check failed" -ForegroundColor Red
    $allHealthy = $false
}

# Check Prometheus
try {
    $response = Invoke-WebRequest -Uri "http://${vmIp}:9090/-/healthy" -UseBasicParsing -TimeoutSec 10
    Write-Host "  [OK] Prometheus: http://${vmIp}:9090" -ForegroundColor Green
}
catch {
    Write-Host "  [ERROR] Prometheus health check failed" -ForegroundColor Red
    $allHealthy = $false
}

# Check Grafana
try {
    $response = Invoke-WebRequest -Uri "http://${vmIp}:3000/api/health" -UseBasicParsing -TimeoutSec 10
    Write-Host "  [OK] Grafana: http://${vmIp}:3000 (admin/ChangeMe!)" -ForegroundColor Green
}
catch {
    Write-Host "  [ERROR] Grafana health check failed" -ForegroundColor Red
    $allHealthy = $false
}

if (-not $allHealthy) {
    Write-Host "`n  [WARN] Some services failed health checks" -ForegroundColor Yellow
    Write-Host "  Check logs: ssh azureuser@$vmIp 'cd memory_kernel/k0/deployment/compose/generated/local-single-node && sudo docker compose logs'" -ForegroundColor Yellow
}

# ============================================================================
# STEP 6: Start Traffic Generation
# ============================================================================

if (-not $SkipTraffic) {
    Write-Host "`n[STEP 6/6] Starting 48-hour traffic generation..." -ForegroundColor Cyan

    # Check if Python venv exists
    if (-not (Test-Path ".venv\Scripts\python.exe")) {
        Write-Host "  [WARN] Python venv not found - traffic generator requires setup" -ForegroundColor Yellow
        Write-Host "  Run: python -m venv .venv && .venv\Scripts\pip install -r requirements.txt" -ForegroundColor Yellow
        $SkipTraffic = $true
    }

    if (-not $SkipTraffic) {
        $pythonExe = Resolve-Path ".venv\Scripts\python.exe"
        $kernelEndpoint = "http://${vmIp}:8080"

        # Check if traffic generator exists and has required deps
        if (-not (Test-Path "scripts\traffic_generator.py")) {
            Write-Host "  [WARN] Traffic generator not found: scripts\traffic_generator.py" -ForegroundColor Yellow
            Write-Host "  Creating simple HTTP-based traffic instead..." -ForegroundColor Yellow

            # Create simple traffic script
            $simpleTrafficScript = @'
import asyncio
import httpx
import time
from datetime import datetime

async def generate_traffic(endpoint: str, duration_hours: int = 48):
    """Generate simple HTTP traffic for burn-in testing."""
    print(f"Starting 48-hour traffic generation to {endpoint}")
    print(f"Start time: {datetime.now()}")

    start_time = time.time()
    duration_seconds = duration_hours * 3600
    request_count = 0
    error_count = 0

    async with httpx.AsyncClient(timeout=5.0) as client:
        while time.time() - start_time < duration_seconds:
            try:
                # Health check (should succeed)
                await client.get(f"{endpoint}/healthz")
                request_count += 1

                # Metrics endpoint
                await client.get(f"{endpoint}/metrics")
                request_count += 1

                # Command submission (will fail validation but generates metrics)
                await client.post(f"{endpoint}/k0/command.submit", json={"test": "data"})
                request_count += 1

                # Wait 1 second between bursts (3 req/sec)
                await asyncio.sleep(1)

                # Progress report every 5 minutes
                if request_count % 900 == 0:
                    elapsed = (time.time() - start_time) / 3600
                    print(f"[{datetime.now()}] Progress: {elapsed:.1f}h elapsed, {request_count} requests, {error_count} errors")

            except Exception as e:
                error_count += 1
                if error_count % 10 == 0:
                    print(f"Error count: {error_count}")

    print(f"\nTraffic generation complete!")
    print(f"Total requests: {request_count}")
    print(f"Total errors: {error_count}")
    print(f"Duration: {(time.time() - start_time) / 3600:.1f} hours")

if __name__ == "__main__":
    import sys
    endpoint = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8080"
    asyncio.run(generate_traffic(endpoint, 48))
'@

            $simpleTrafficScript | Out-File -FilePath "scripts\simple_traffic.py" -Encoding UTF8

            # Start traffic in background job
            $job = Start-Job -ScriptBlock {
                param($python, $script, $endpoint)
                & $python $script $endpoint
            } -ArgumentList $pythonExe, (Resolve-Path "scripts\simple_traffic.py"), $kernelEndpoint

            Write-Host "  [OK] Started traffic generation (Job ID: $($job.Id))" -ForegroundColor Green
            Write-Host "  [INFO] Target: $kernelEndpoint" -ForegroundColor Cyan
            Write-Host "  [INFO] Duration: 48 hours (172,800 seconds)" -ForegroundColor Cyan
            Write-Host "  [INFO] Rate: ~3 req/sec (steady)" -ForegroundColor Cyan
            Write-Host "`n  Monitor job: Get-Job -Id $($job.Id)" -ForegroundColor Yellow
            Write-Host "  View output: Receive-Job -Id $($job.Id) -Keep" -ForegroundColor Yellow
        }
    }
}
else {
    Write-Host "`n[STEP 6/6] Skipping traffic generation..." -ForegroundColor Yellow
}

# ============================================================================
# DEPLOYMENT SUMMARY
# ============================================================================

$totalDuration = ((Get-Date) - $startTime).TotalSeconds

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  DEPLOYMENT COMPLETE" -ForegroundColor Green
Write-Host "========================================`n" -ForegroundColor Cyan

Write-Host "[TIMING]" -ForegroundColor Yellow
Write-Host "  Total deployment time: $([math]::Round($totalDuration, 1))s`n" -ForegroundColor White

Write-Host "[ENDPOINTS]" -ForegroundColor Yellow
Write-Host "  Kernel API:  http://${vmIp}:8080" -ForegroundColor White
Write-Host "  Metrics:     http://${vmIp}:8080/metrics" -ForegroundColor White
Write-Host "  Grafana:     http://${vmIp}:3000 (admin/ChangeMe!)" -ForegroundColor White
Write-Host "  Prometheus:  http://${vmIp}:9090" -ForegroundColor White
Write-Host "  Alertmanager: http://${vmIp}:9093`n" -ForegroundColor White

Write-Host "[DASHBOARDS]" -ForegroundColor Yellow
Write-Host "  SLO Burn Rate:    http://${vmIp}:3000/d/k0-slo-burn-rate/k0-slo-burn-rate" -ForegroundColor Cyan
Write-Host "  Kernel Overview:  http://${vmIp}:3000/d/k0-kernel-overview/k0-kernel-overview" -ForegroundColor Cyan
Write-Host "  Golden Signals:   http://${vmIp}:3000/d/k0-golden-signals/k0-golden-signals" -ForegroundColor Cyan
Write-Host "  Incident Response: http://${vmIp}:3000/d/k0-incident-response/k0-incident-response`n" -ForegroundColor Cyan

Write-Host "[MONITORING]" -ForegroundColor Yellow
Write-Host "  SSH into VM:  ssh azureuser@$vmIp" -ForegroundColor White
Write-Host "  View logs:    ssh azureuser@$vmIp 'cd memory_kernel/k0/deployment/compose/generated/local-single-node && sudo docker compose logs -f k0-kernel'" -ForegroundColor White
Write-Host "  Check status: ssh azureuser@$vmIp 'cd memory_kernel/k0/deployment/compose/generated/local-single-node && sudo docker compose ps'`n" -ForegroundColor White

Write-Host "[NEXT STEPS]" -ForegroundColor Yellow
Write-Host "  1. Open Grafana dashboards to monitor burn-in progress" -ForegroundColor White
Write-Host "  2. Check traffic generation: Get-Job | Where-Object { `$_.State -eq 'Running' }" -ForegroundColor White
Write-Host "  3. Monitor costs: az consumption usage list --billing-period-name `$(Get-Date -Format 'yyyyMM')" -ForegroundColor White
Write-Host "  4. After 48 hours, run cleanup: az group delete --name $ResourceGroup --yes`n" -ForegroundColor White

Write-Host "[SUCCESS] 48-hour burn-in test is now running!" -ForegroundColor Green
Write-Host "Check back in 24 hours for progress update.`n" -ForegroundColor Yellow
