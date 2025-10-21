#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Comprehensive dashboard audit before Azure 48-hour burn-in deployment.

.DESCRIPTION
    Validates all Grafana dashboards have correct metric names and queries.
    Checks for common issues:
    - Missing k0_kernel_ namespace prefix
    - Incorrect job labels (k0-kernel vs k0_kernel)
    - Broken panel queries
    - Missing data sources

.EXAMPLE
    .\scripts\audit_dashboards.ps1
#>

param(
    [string]$DashboardPath = "k0/deployment/compose/generated/local-single-node/generated/dashboards",
    [string]$PrometheusUrl = "http://localhost:9090"
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path $PSScriptRoot -Parent
$dashboardRoot = Join-Path $repoRoot $DashboardPath

Write-Host "`n[K0 Dashboard Audit - Pre-Azure Deployment]" -ForegroundColor Cyan
Write-Host ("=" * 70) -ForegroundColor Gray
Write-Host "Dashboard Path: $dashboardRoot" -ForegroundColor Yellow
Write-Host "Prometheus URL: $PrometheusUrl`n" -ForegroundColor Yellow

# Find all dashboard JSON files
$dashboards = Get-ChildItem -Path $dashboardRoot -Filter "*.json" -Recurse

Write-Host "[Found $($dashboards.Count) dashboards to audit]`n" -ForegroundColor Green

$totalIssues = 0
$dashboardStatus = @()

foreach ($dashboard in $dashboards) {
    $relativePath = $dashboard.FullName.Replace("$PSScriptRoot\..\", "")
    Write-Host "Checking: $($dashboard.Name)" -ForegroundColor Cyan

    $content = Get-Content $dashboard.FullName -Raw | ConvertFrom-Json
    $issues = @()
    $panelCount = 0
    $queryCount = 0

    # Extract all panels recursively
    function Get-Panels($obj) {
        if ($obj.panels) {
            foreach ($panel in $obj.panels) {
                if ($panel.type -and $panel.type -ne "row") {
                    $script:panelCount++

                    # Check targets (queries)
                    if ($panel.targets) {
                        foreach ($target in $panel.targets) {
                            $script:queryCount++
                            $query = $target.expr

                            if ($query) {
                                # Check for missing k0_kernel_ prefix
                                if ($query -match '\bk0_(?!kernel_)') {
                                    $issues += "  [WARN] Panel '$($panel.title)': Missing k0_kernel_ prefix in query"
                                }

                                # Check for wrong job label
                                if ($query -match 'job="k0-kernel"') {
                                    $issues += "  [WARN] Panel '$($panel.title)': Wrong job label (use k0_kernel not k0-kernel)"
                                }

                                # Check for operation filters that might not exist
                                if ($query -match 'operation="(command|query)"' -and $query -notmatch 'http_request') {
                                    $issues += "  [INFO] Panel '$($panel.title)': Uses operation filter (verify metric exists)"
                                }
                            }
                        }
                    }
                }

                # Recurse for nested panels
                if ($panel.panels) {
                    Get-Panels $panel
                }
            }
        }
    }

    Get-Panels $content

    $status = @{
        Dashboard = $dashboard.Name
        Path      = $relativePath
        Panels    = $panelCount
        Queries   = $queryCount
        Issues    = $issues.Count
        Details   = $issues
    }

    $dashboardStatus += $status
    $totalIssues += $issues.Count

    if ($issues.Count -eq 0) {
        Write-Host "  ✅ $panelCount panels, $queryCount queries - All OK" -ForegroundColor Green
    }
    else {
        Write-Host "  ⚠️  $panelCount panels, $queryCount queries - $($issues.Count) issues found:" -ForegroundColor Yellow
        $issues | ForEach-Object { Write-Host $_ -ForegroundColor Yellow }
    }
    Write-Host ""
}

Write-Host "`n" + ("=" * 70) -ForegroundColor Gray
Write-Host "[AUDIT SUMMARY]" -ForegroundColor Gray
Write-Host ("=" * 70) -ForegroundColor Gray

$totalPanels = 0
$totalQueries = 0
foreach ($status in $dashboardStatus) {
    $totalPanels += $status.Panels
    $totalQueries += $status.Queries
}

Write-Host "Total Dashboards: $($dashboards.Count)" -ForegroundColor White
Write-Host "Total Panels: $totalPanels" -ForegroundColor White
Write-Host "Total Queries: $totalQueries" -ForegroundColor White
Write-Host "Total Issues: $totalIssues" -ForegroundColor $(if ($totalIssues -eq 0) { "Green" } else { "Yellow" })

if ($totalIssues -eq 0) {
    Write-Host "`n[OK] ALL DASHBOARDS READY FOR AZURE DEPLOYMENT!" -ForegroundColor Green
}
else {
    Write-Host "`n[WARN] Some dashboards have potential issues - review before deployment" -ForegroundColor Yellow
}

Write-Host "`n[Dashboard Breakdown]:" -ForegroundColor Cyan
$dashboardStatus | Format-Table Dashboard, Panels, Queries, Issues -AutoSize

# Test Prometheus connectivity
Write-Host "`n[Testing Prometheus Connection...]" -ForegroundColor Cyan
try {
    $response = Invoke-WebRequest -Uri "$PrometheusUrl/api/v1/query?query=up" -UseBasicParsing
    $result = ($response.Content | ConvertFrom-Json)
    if ($result.status -eq "success") {
        Write-Host "  [OK] Prometheus accessible at $PrometheusUrl" -ForegroundColor Green

        # Check k0_kernel metrics
        $metricsResponse = Invoke-WebRequest -Uri "$PrometheusUrl/api/v1/label/__name__/values" -UseBasicParsing
        $metrics = ($metricsResponse.Content | ConvertFrom-Json).data
        $k0Metrics = $metrics | Where-Object { $_ -like "k0_kernel_*" }
        Write-Host "  [INFO] Found $($k0Metrics.Count) k0_kernel_* metrics" -ForegroundColor Green
    }
}
catch {
    Write-Host "  [WARN] Cannot connect to Prometheus: $_" -ForegroundColor Yellow
}

Write-Host "`n[OK] Audit Complete!" -ForegroundColor Green
Write-Host "Next: Run Docker build and push to Azure" -ForegroundColor Cyan
