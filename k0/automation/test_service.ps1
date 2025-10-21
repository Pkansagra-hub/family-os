# Test K0 Remediation Service

Write-Host "Testing K0 Remediation Service..." -ForegroundColor Cyan

$BaseUrl = "http://localhost:8081"

# Test 1: Health check
Write-Host "`n[Test 1] Health Check" -ForegroundColor Yellow
try {
    $health = Invoke-RestMethod -Uri "$BaseUrl/health" -Method GET
    Write-Host "Health check passed" -ForegroundColor Green
    Write-Host "  - Status: $($health.status)"
    Write-Host "  - Automation Enabled: $($health.automation_enabled)"
    Write-Host "  - Dry Run: $($health.dry_run)"
    Write-Host "  - Max Remediations/Hour: $($health.max_remediations_per_hour)"
}
catch {
    Write-Host "Health check failed: $_" -ForegroundColor Red
    exit 1
}

# Test 2: Webhook with memory alert
Write-Host "`n[Test 2] Memory Alert Remediation" -ForegroundColor Yellow
$memoryAlert = @{
    status = "firing"
    alerts = @(
        @{
            status      = "firing"
            labels      = @{
                alertname = "K0MemoryUsageHigh"
                severity  = "warning"
                component = "kernel"
            }
            annotations = @{
                summary     = "Memory usage >80%"
                description = "Process memory at 85%"
            }
            startsAt    = "2025-10-08T10:00:00Z"
        }
    )
} | ConvertTo-Json -Depth 5

try {
    $result = Invoke-RestMethod -Uri "$BaseUrl/webhook" -Method POST `
        -Body $memoryAlert -ContentType "application/json"

    Write-Host "Webhook processed" -ForegroundColor Green
    Write-Host "  - Status: $($result.status)"
    Write-Host "  - Dry Run: $($result.dry_run)"
    foreach ($r in $result.results) {
        Write-Host "  - Alert: $($r.alert)"
        Write-Host "    Status: $($r.status)"
        Write-Host "    Action: $($r.action)"
    }
}
catch {
    Write-Host "Webhook test failed: $_" -ForegroundColor Red
}

# Test 3: Stats endpoint
Write-Host "`n[Test 3] Stats Check" -ForegroundColor Yellow
try {
    $stats = Invoke-RestMethod -Uri "$BaseUrl/stats" -Method GET
    Write-Host "Stats retrieved" -ForegroundColor Green
    Write-Host "  - Time Window: $($stats.time_window)"
    Write-Host "  - Total Remediations: $($stats.total_remediations)"
    Write-Host "  - Success Rate: $($stats.success_rate_percent)%"
    Write-Host "  - MTTR: $($stats.mean_time_to_remediation_seconds)s"
}
catch {
    Write-Host "Stats check failed: $_" -ForegroundColor Red
}

# Test 4: History endpoint
Write-Host "`n[Test 4] History Check" -ForegroundColor Yellow
try {
    $history = Invoke-RestMethod -Uri "$BaseUrl/history?limit=5" -Method GET
    Write-Host "History retrieved" -ForegroundColor Green
    Write-Host "  - Record Count: $($history.count)"
    if ($history.count -gt 0) {
        Write-Host "`nRecent Remediations:"
        foreach ($record in $history.history) {
            Write-Host "  - $($record.timestamp) | $($record.alertname) | $($record.action) | $($record.status)"
        }
    }
}
catch {
    Write-Host "History check failed: $_" -ForegroundColor Red
}

Write-Host "`nAll tests complete!" -ForegroundColor Cyan
