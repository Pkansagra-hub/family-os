#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Submit sample events to K0 kernel for testing.

.DESCRIPTION
    Provides quick access to different event submission scripts:
    - Diverse events (tests P03 algorithms)
    - Real-life events (realistic daily schedule)
    - Test events (focused algorithm testing)
    - Gap clarifications (resolve ambiguous entities)

.PARAMETER Type
    Type of events to submit: diverse, reallife, test, gaps, all

.PARAMETER Count
    Number of events to submit (where applicable)

.EXAMPLE
    .\submit_sample_events.ps1 -Type diverse
    Submit diverse test events

.EXAMPLE
    .\submit_sample_events.ps1 -Type reallife
    Submit realistic daily schedule events

.EXAMPLE
    .\submit_sample_events.ps1 -Type all
    Submit all event types in sequence
#>

param(
    [Parameter(Mandatory = $false)]
    [ValidateSet("diverse", "reallife", "test", "gaps", "all")]
    [string]$Type = "diverse",

    [Parameter(Mandatory = $false)]
    [int]$Count = 0
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$EventsDir = Join-Path $ScriptDir "scripts\events"

Write-Host "=" * 80 -ForegroundColor Cyan
Write-Host "K0 EVENT SUBMISSION" -ForegroundColor Cyan
Write-Host "=" * 80 -ForegroundColor Cyan
Write-Host ""

function Submit-DiverseEvents {
    Write-Host "Submitting diverse test events..." -ForegroundColor Yellow
    Write-Host "  - Tests R2 clustering, R3 deduplication, R4 entity extraction" -ForegroundColor Gray
    python "$EventsDir\submit_diverse_events.py"
}

function Submit-RealLifeEvents {
    Write-Host "Submitting realistic daily schedule events..." -ForegroundColor Yellow
    Write-Host "  - Simulates actual daily routines with realistic timing" -ForegroundColor Gray
    python "$EventsDir\submit_reallife_events.py"
}

function Submit-TestEvents {
    Write-Host "Submitting algorithm-specific test events..." -ForegroundColor Yellow
    Write-Host "  - Focused testing of specific P03 algorithms" -ForegroundColor Gray
    python "$EventsDir\submit_test_events.py"
}

function Submit-GapClarifications {
    Write-Host "Submitting gap clarification events..." -ForegroundColor Yellow
    Write-Host "  - Resolves ambiguous entities in learning queue" -ForegroundColor Gray
    python "$EventsDir\submit_gap_clarifications.py"
}

switch ($Type) {
    "diverse" { Submit-DiverseEvents }
    "reallife" { Submit-RealLifeEvents }
    "test" { Submit-TestEvents }
    "gaps" { Submit-GapClarifications }
    "all" {
        Submit-DiverseEvents
        Write-Host ""
        Submit-RealLifeEvents
        Write-Host ""
        Submit-TestEvents
        Write-Host ""
        Submit-GapClarifications
    }
}

Write-Host ""
Write-Host "=" * 80 -ForegroundColor Green
Write-Host "EVENTS SUBMITTED" -ForegroundColor Green
Write-Host "=" * 80 -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  1. Run consolidation: python scripts\data_management\consolidate_batches.py" -ForegroundColor White
Write-Host "  2. Validate results: .\run_validation.ps1" -ForegroundColor White
