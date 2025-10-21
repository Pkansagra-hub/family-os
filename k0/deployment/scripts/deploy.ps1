param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("local-single-node", "edge-cluster", "datacenter-ha")]
    [string]$Stack,

    [switch]$Preview,

    [string]$Inventory = "",

    [string]$ArtifactsRoot = "artifacts",

    [switch]$Mock
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

# Resolve paths
$RepoRoot = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
$DeploymentRoot = Join-Path $RepoRoot "k0\deployment"
$ArtifactsDir = Join-Path $RepoRoot $ArtifactsRoot
$Timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$TimelineFile = Join-Path $ArtifactsDir "deployment-timeline-$Stack-$Timestamp.json"

# Ensure artifacts directory exists up front
New-Item -Path $ArtifactsDir -ItemType Directory -Force | Out-Null

# Initialize timeline
$Timeline = @{
    stack      = $Stack
    mode       = if ($Preview) { "preview" } else { "apply" }
    started_at = (Get-Date).ToString("o")
    steps      = @()
}

function Add-TimelineStep {
    param([string]$Name, [string]$Status, [hashtable]$Metadata = @{})
    $Timeline.steps += @{
        name      = $Name
        status    = $Status
        timestamp = (Get-Date).ToString("o")
        metadata  = $Metadata
    }
}

function Save-Timeline {
    New-Item -Path (Split-Path $TimelineFile) -ItemType Directory -Force | Out-Null
    $Timeline | ConvertTo-Json -Depth 10 | Set-Content -Path $TimelineFile -Encoding UTF8
    Write-Host "[k0] Timeline saved to: $TimelineFile" -ForegroundColor Gray
}

try {
    Write-Host "[k0] Starting deployment for stack '$Stack'" -ForegroundColor Cyan
    Write-Host "[k0] Mode: $(if ($Preview) { 'PREVIEW' } else { 'APPLY' })" -ForegroundColor Cyan

    if ($Mock) {
        Write-Host "[k0] Mock mode enabled - simulating tool execution" -ForegroundColor Yellow
    }

    # Step 1: Pulumi operation
    Add-TimelineStep -Name "pulumi_operation" -Status "started"

    $PulumiCmd = if ($Preview) { "preview" } else { "up --yes" }
    $PulumiArtifactsDir = Join-Path $ArtifactsDir "pulumi\$Stack"
    New-Item -Path $PulumiArtifactsDir -ItemType Directory -Force | Out-Null
    $PulumiLogPath = Join-Path $PulumiArtifactsDir "pulumi-$Timestamp.log"
    $PulumiStackExportPath = Join-Path $PulumiArtifactsDir "stack-export-$Timestamp.json"
    $PulumiStackExportLogPath = Join-Path $PulumiArtifactsDir "stack-export-$Timestamp.log"

    Write-Host "[k0] Running Pulumi $PulumiCmd for stack '$Stack'" -ForegroundColor Cyan

    if ($Mock) {
        # Mock mode: Simulate Pulumi execution
        Write-Host "  [MOCK] pulumi stack select $Stack" -ForegroundColor DarkGray
        Write-Host "  [MOCK] pulumi $PulumiCmd --stack $Stack" -ForegroundColor DarkGray

        # Create mock artifacts
        @{
            stack     = $Stack
            mode      = $(if ($Preview) { "preview" } else { "apply" })
            resources = @()
            mocked    = $true
        } | ConvertTo-Json | Set-Content -Path (Join-Path $PulumiArtifactsDir "mock-output.json")

        "Mock Pulumi execution for stack $Stack" | Set-Content -Path $PulumiLogPath -Encoding UTF8
        "Mock stack export for stack $Stack" | Set-Content -Path $PulumiStackExportLogPath -Encoding UTF8
        '{}' | Set-Content -Path $PulumiStackExportPath -Encoding UTF8

        Start-Sleep -Milliseconds 500

        Add-TimelineStep -Name "pulumi_operation" -Status "completed" -Metadata @{
            command           = "pulumi $PulumiCmd"
            exit_code         = 0
            mocked            = $true
            log_path          = $PulumiLogPath
            stack_export_path = $PulumiStackExportPath
            stack_export_log  = $PulumiStackExportLogPath
        }

        Write-Host "[k0] Pulumi operation completed successfully (mocked)" -ForegroundColor Green
    }
    else {
        # Real mode: Execute Pulumi
        Push-Location (Join-Path $DeploymentRoot "pulumi")
        $originalPulumiPassphrase = $env:PULUMI_CONFIG_PASSPHRASE
        $passphraseInjected = $false
        try {
            if ($null -ne $originalPulumiPassphrase) {
                Write-Host "[k0] Using pre-configured Pulumi passphrase from environment" -ForegroundColor Gray
            }
            else {
                # Default to empty string only when the caller has not provided a passphrase.
                $env:PULUMI_CONFIG_PASSPHRASE = ""
                $passphraseInjected = $true
            }
            $PulumiOutput = & pulumi stack select $Stack 2>&1
            if ($LASTEXITCODE -ne 0) {
                throw "Pulumi stack select failed: $PulumiOutput"
            }

            $PulumiArgs = $PulumiCmd -split ' '
            & pulumi @PulumiArgs --stack $Stack 2>&1 |
            Tee-Object -FilePath $PulumiLogPath

            if ($LASTEXITCODE -ne 0) {
                throw "Pulumi operation failed with exit code $LASTEXITCODE"
            }

            if (-not $Preview) {
                & pulumi stack export --stack $Stack --file $PulumiStackExportPath 2>&1 |
                Tee-Object -FilePath $PulumiStackExportLogPath

                if ($LASTEXITCODE -ne 0) {
                    throw "Pulumi stack export failed with exit code $LASTEXITCODE"
                }
            }

            $PulumiMetadata = @{
                command   = "pulumi $PulumiCmd"
                exit_code = 0
                log_path  = $PulumiLogPath
            }

            if (-not $Preview) {
                $PulumiMetadata.stack_export_path = $PulumiStackExportPath
                $PulumiMetadata.stack_export_log = $PulumiStackExportLogPath
            }

            Add-TimelineStep -Name "pulumi_operation" -Status "completed" -Metadata $PulumiMetadata

            Write-Host "[k0] Pulumi operation completed successfully" -ForegroundColor Green
        }
        finally {
            if ($passphraseInjected) {
                Remove-Item Env:PULUMI_CONFIG_PASSPHRASE -ErrorAction SilentlyContinue
            }
            elseif ($null -ne $originalPulumiPassphrase) {
                $env:PULUMI_CONFIG_PASSPHRASE = $originalPulumiPassphrase
            }
            Pop-Location
        }
    }

    # Step 2: Ansible playbook execution (only for apply mode)
    if (-not $Preview) {
        Add-TimelineStep -Name "ansible_playbook" -Status "started"

        $AnsibleArtifactsDir = Join-Path $ArtifactsDir "ansible\$Stack"
        New-Item -Path $AnsibleArtifactsDir -ItemType Directory -Force | Out-Null
        $AnsibleLogPath = Join-Path $AnsibleArtifactsDir "ansible-$Timestamp.log"

        # Auto-detect inventory based on stack
        if (-not $Inventory) {
            $InventoryMap = @{
                "local-single-node" = "sample-dev"
                "edge-cluster"      = "sample-prod"
                "datacenter-ha"     = "sample-prod"
            }
            $Inventory = $InventoryMap[$Stack]
        }

        $InventoryPath = Join-Path $DeploymentRoot "ansible\inventories\$Inventory\hosts.yml"
        $PlaybookPath = Join-Path $DeploymentRoot "ansible\playbooks\site.yml"

        if (-not (Test-Path $InventoryPath)) {
            throw "Inventory not found: $InventoryPath"
        }

        Write-Host "[k0] Running Ansible playbook with inventory '$Inventory'" -ForegroundColor Cyan

        if ($Mock) {
            # Mock mode: Simulate Ansible execution
            Write-Host "  [MOCK] ansible-playbook -i $InventoryPath $PlaybookPath" -ForegroundColor DarkGray

            Start-Sleep -Milliseconds 800

            "Mock Ansible execution for inventory $Inventory" | Set-Content -Path $AnsibleLogPath -Encoding UTF8

            Add-TimelineStep -Name "ansible_playbook" -Status "completed" -Metadata @{
                inventory = $Inventory
                playbook  = "site.yml"
                exit_code = 0
                mocked    = $true
                log_path  = $AnsibleLogPath
            }

            Write-Host "[k0] Ansible playbook completed successfully (mocked)" -ForegroundColor Green
        }
        else {
            # Real mode: Execute Ansible
            $env:FAMILYOS_REPO_ROOT = $RepoRoot
            $env:FAMILYOS_TELEMETRY_SNAPSHOT = Join-Path $ArtifactsDir "telemetry"

            & ansible-playbook -i $InventoryPath $PlaybookPath 2>&1 |
            Tee-Object -FilePath $AnsibleLogPath

            if ($LASTEXITCODE -ne 0) {
                throw "Ansible playbook failed with exit code $LASTEXITCODE"
            }

            Add-TimelineStep -Name "ansible_playbook" -Status "completed" -Metadata @{
                inventory = $Inventory
                playbook  = "site.yml"
                exit_code = 0
                log_path  = $AnsibleLogPath
            }

            Write-Host "[k0] Ansible playbook completed successfully" -ForegroundColor Green
        }

        # Step 3: Capture telemetry snapshot
        Add-TimelineStep -Name "telemetry_snapshot" -Status "started"

        $TelemetryDir = Join-Path $ArtifactsDir "telemetry\$Stack"
        New-Item -Path $TelemetryDir -ItemType Directory -Force | Out-Null
        $TelemetryLogPath = Join-Path $TelemetryDir "telemetry-$Timestamp.log"

        Write-Host "[k0] Capturing telemetry snapshot" -ForegroundColor Cyan

        if ($Mock) {
            # Mock mode: Create mock telemetry data
            Write-Host "  [MOCK] python -m k0.automation.verify_security_telemetry -d $TelemetryDir" -ForegroundColor DarkGray

            @{
                stack     = $Stack
                timestamp = (Get-Date).ToString("o")
                metrics   = @("security_scan_passed", "telemetry_verified")
                mocked    = $true
            } | ConvertTo-Json | Set-Content -Path (Join-Path $TelemetryDir "mock-snapshot.json")

            Start-Sleep -Milliseconds 300

            "Mock telemetry verification" | Set-Content -Path $TelemetryLogPath -Encoding UTF8

            Add-TimelineStep -Name "telemetry_snapshot" -Status "completed" -Metadata @{
                directory = $TelemetryDir
                mocked    = $true
                log_path  = $TelemetryLogPath
            }
            Write-Host "[k0] Telemetry snapshot captured (mocked)" -ForegroundColor Green
        }
        else {
            # Real mode: Execute telemetry verification
            & python -m k0.automation.verify_security_telemetry -d $TelemetryDir 2>&1 |
            Tee-Object -FilePath $TelemetryLogPath

            if ($LASTEXITCODE -eq 0) {
                Add-TimelineStep -Name "telemetry_snapshot" -Status "completed" -Metadata @{
                    directory = $TelemetryDir
                    log_path  = $TelemetryLogPath
                }
                Write-Host "[k0] Telemetry snapshot captured" -ForegroundColor Green
            }
            else {
                Add-TimelineStep -Name "telemetry_snapshot" -Status "warning" -Metadata @{
                    message  = "Telemetry verification had warnings"
                    log_path = $TelemetryLogPath
                }
                Write-Host "[k0] Telemetry snapshot captured with warnings" -ForegroundColor Yellow
            }
        }
    }

    # Success
    $Timeline.completed_at = (Get-Date).ToString("o")
    $Timeline.status = "success"
    Save-Timeline

    Write-Host "[k0] Deployment completed successfully!" -ForegroundColor Green
    exit 0

}
catch {
    $Timeline.completed_at = (Get-Date).ToString("o")
    $Timeline.status = "failed"
    $Timeline.error = $_.Exception.Message
    Save-Timeline

    Write-Host "[k0] Deployment failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
