# K0 All Ports Test Runner
# Tests all K0 deployment ports and returns comprehensive results

Write-Host ""
Write-Host "╔════════════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║            K0 ALL PORTS TEST SUITE EXECUTION                       ║" -ForegroundColor Cyan
Write-Host "║  Posting requests to all K0 ports for comprehensive validation     ║" -ForegroundColor Cyan
Write-Host "╚════════════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# Set working directory
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

# Check Python installation
Write-Host "🔍 Checking Python installation..." -ForegroundColor Yellow
$PythonPath = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $PythonPath) {
    Write-Host "❌ Python not found in PATH" -ForegroundColor Red
    exit 1
}
Write-Host "✅ Python found: $PythonPath" -ForegroundColor Green

# Check required packages
Write-Host ""
Write-Host "📦 Verifying required packages..." -ForegroundColor Yellow
$RequiredPackages = @("requests", "nacl")
foreach ($Package in $RequiredPackages) {
    python -c "import $Package" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "❌ Missing package: $Package" -ForegroundColor Red
        Write-Host "   Installing with: pip install $Package" -ForegroundColor Yellow
        pip install $Package -q
    }
    else {
        Write-Host "✅ $Package installed" -ForegroundColor Green
    }
}

# Verify K0 deployment is running
Write-Host ""
Write-Host "🔗 Verifying K0 deployment is running..." -ForegroundColor Yellow
try {
    $HealthCheck = Invoke-WebRequest -Uri "http://localhost:8080/healthz" -TimeoutSec 5 -ErrorAction Stop
    if ($HealthCheck.StatusCode -eq 200) {
        Write-Host "✅ K0 kernel is responding on port 8080" -ForegroundColor Green
    }
}
catch {
    Write-Host "⚠️  K0 kernel may not be running on port 8080" -ForegroundColor Red
    Write-Host "   Please run: .\k0.ps1 up" -ForegroundColor Yellow
}

# Run the test suite
Write-Host ""
Write-Host "🚀 Running test suite..." -ForegroundColor Cyan
Write-Host ""

python test_all_ports.py

$TestResult = $LASTEXITCODE

# Print summary
Write-Host ""
if ($TestResult -eq 0) {
    Write-Host "╔════════════════════════════════════════════════════════════════════╗" -ForegroundColor Green
    Write-Host "║                    ✅ ALL TESTS PASSED ✅                         ║" -ForegroundColor Green
    Write-Host "║           All K0 ports are responding with 200 OK status           ║" -ForegroundColor Green
    Write-Host "║        Reference implementation ready for k0_bridge setup          ║" -ForegroundColor Green
    Write-Host "╚════════════════════════════════════════════════════════════════════╝" -ForegroundColor Green
}
else {
    Write-Host "╔════════════════════════════════════════════════════════════════════╗" -ForegroundColor Red
    Write-Host "║                   ⚠️  SOME TESTS FAILED ⚠️                        ║" -ForegroundColor Red
    Write-Host "║    Review output above for details on failed endpoints             ║" -ForegroundColor Red
    Write-Host "║    Verify K0 deployment is running and healthy                     ║" -ForegroundColor Red
    Write-Host "╚════════════════════════════════════════════════════════════════════╝" -ForegroundColor Red
}

Write-Host ""
exit $TestResult
