param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("up", "down", "restart", "status", "logs")]
    [string]$Command,

    [switch]$Rebuild,
    [switch]$Migrate,
    [switch]$Verify,
    [int]$WaitSeconds = 10,

    [string]$Service
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

# Paths
$DeployRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent (Split-Path -Parent $DeployRoot)
$ComposeKernel = Join-Path $DeployRoot "docker-compose.yml"
$ComposeTelemetry = Join-Path $DeployRoot "local-single-node-telemetry.yml"
$EnvDir = Join-Path $DeployRoot "env"
$DataDir = Join-Path $DeployRoot "data"
$SecretsDir = Join-Path $DeployRoot "secrets"
$GeneratedDir = Join-Path $DeployRoot "generated"
$TelemetryDir = Join-Path $DeployRoot "telemetry"
$DbPath = Join-Path $DataDir "kernel.sqlite3"
$ProjectName = "k0"

function Write-Info($msg) { Write-Host "[k0] $msg" -ForegroundColor Cyan }
function Write-Ok($msg) { Write-Host "[k0] $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "[k0] $msg" -ForegroundColor Yellow }
function Write-Err($msg) { Write-Host "[k0] $msg" -ForegroundColor Red }

function Get-ManifestFingerprint {
    param([string]$ManifestPath)

    if (-not (Test-Path $ManifestPath)) {
        Write-Err "Manifest not found: $ManifestPath"
        return $null
    }

    try {
        $content = Get-Content -Path $ManifestPath -Raw
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($content)
        $hash = [System.Security.Cryptography.SHA256]::Create().ComputeHash($bytes)
        $fingerprint = [System.Convert]::ToBase64String($hash)
        return $fingerprint
    }
    catch {
        Write-Err "Failed to compute fingerprint for $ManifestPath : $_"
        return $null
    }
}

function Validate-Manifest {
    param([string]$ManifestPath)

    Write-Info "Validating policy manifest: $ManifestPath"

    if (-not (Test-Path $ManifestPath)) {
        Write-Err "Policy manifest not found: $ManifestPath"
        return $false
    }

    try {
        $content = Get-Content -Path $ManifestPath -Raw
        $json = $content | ConvertFrom-Json
        Write-Ok "Manifest valid JSON structure"

        $fingerprint = Get-ManifestFingerprint $ManifestPath
        Write-Info "Manifest fingerprint: $fingerprint"

        return $true
    }
    catch {
        Write-Err "Failed to validate manifest: $_"
        return $false
    }
}

function Ensure-Compose-Prereqs {
    Write-Info "Ensuring deploy directories and files"

    New-Item -ItemType Directory -Path $EnvDir -Force | Out-Null
    New-Item -ItemType Directory -Path $DataDir -Force | Out-Null
    New-Item -ItemType Directory -Path $SecretsDir -Force | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $GeneratedDir "manifests") -Force | Out-Null

    $EnvFile = Join-Path $EnvDir "k0.env"
    if (-not (Test-Path $EnvFile)) { New-Item -ItemType File -Path $EnvFile | Out-Null }

    # Policy schema bind: expected host path is ../contracts/policy/pep.schema.json from k0/deploy
    $ContractsRoot = Join-Path $RepoRoot "contracts"
    $ContractsPolicy = Join-Path $ContractsRoot "policy"
    $PolicyDest = Join-Path $ContractsPolicy "pep.schema.json"

    if (-not (Test-Path $PolicyDest)) {
        $K0Policy = Join-Path (Join-Path $RepoRoot "k0\contracts\policy") "pep.schema.json"
        if (Test-Path $K0Policy) {
            New-Item -ItemType Directory -Path $ContractsPolicy -Force | Out-Null
            Copy-Item -Path $K0Policy -Destination $PolicyDest -Force
            Write-Info "Copied policy schema to $PolicyDest"
        }
        else {
            Write-Warn "Policy schema not found at $PolicyDest or $K0Policy. Compose may fail to mount."
        }
    }

    # Ensure bridge policy contract is available
    $BridgePolicyDest = Join-Path $ContractsPolicy "bridge_policy.yml"
    if (-not (Test-Path $BridgePolicyDest)) {
        $K0BridgePolicy = Join-Path (Join-Path $RepoRoot "k0\contracts\policy") "bridge_policy.yml"
        if (Test-Path $K0BridgePolicy) {
            Copy-Item -Path $K0BridgePolicy -Destination $BridgePolicyDest -Force
            Write-Info "Copied bridge policy contract to $BridgePolicyDest"
        }
        else {
            Write-Warn "Bridge policy contract not found at $K0BridgePolicy"
        }
    }

    # Ensure default policy manifests exist in generated/manifests
    # These are actual policy instances (for device provisioning and RBAC)
    $ManifestsDir = Join-Path $GeneratedDir "manifests"
    New-Item -ItemType Directory -Path $ManifestsDir -Force | Out-Null

    $AllowAllManifest = Join-Path $ManifestsDir "allow_all.json"
    if (-not (Test-Path $AllowAllManifest)) {
        Write-Info "Creating default allow_all.json manifest for device provisioning"
        $defaultManifest = @{
            version     = "1.0"
            tenant      = "tenant-001"
            space       = "space-home"
            description = "Default development manifest - allows all operations with audit logging"
            bands       = @{
                GREEN = @{
                    description = "Development - all access allowed"
                    deny        = $false
                    obligations = @()
                }
            }
            roles       = @(
                @{
                    name         = "admin"
                    description  = "Administrator role - full access"
                    max_band     = "RED"
                    allow_topics = @("*")
                    obligations  = @()
                },
                @{
                    name         = "device"
                    description  = "Device role - all write access"
                    max_band     = "GREEN"
                    allow_topics = @("commands.*")
                    obligations  = @()
                }
            )
            policies    = @(
                @{
                    name        = "allow_all"
                    band        = "GREEN"
                    description = "Development policy - allows all actions with audit trail"
                    rules       = @(
                        @{
                            action      = "ALLOW"
                            target      = "*"
                            obligations = @("kernel.audit.log")
                        }
                    )
                }
            )
        } | ConvertTo-Json -Depth 10
        Set-Content -Path $AllowAllManifest -Value $defaultManifest
        Write-Ok "Created manifest for device provisioning: $AllowAllManifest"
    }

    # Validate manifest before deploy
    if (-not (Validate-Manifest $AllowAllManifest)) {
        Write-Err "Manifest validation failed. Deploy cannot proceed."
        exit 1
    }

    # Verify telemetry configs exist
    $need = @(
        (Join-Path $TelemetryDir "prometheus.yml"),
        (Join-Path $TelemetryDir "alertmanager.yml"),
        (Join-Path $TelemetryDir "tempo.yaml"),
        (Join-Path $TelemetryDir "grafana\provisioning\datasources"),
        (Join-Path $TelemetryDir "grafana\provisioning\dashboards"),
        (Join-Path $GeneratedDir "rules"),
        (Join-Path $GeneratedDir "dashboards")
    )
    foreach ($p in $need) {
        if (-not (Test-Path $p)) {
            Write-Warn "Missing expected telemetry path: $p"
        }
    }
}

function Ensure-Image {
    $imagePresent = (docker images --format "{{.Repository}}:{{.Tag}}" | Select-String -SimpleMatch "k0-kernel-local:latest")
    if ($Rebuild -or -not $imagePresent) {
        Write-Info "Building image k0-kernel-local:latest"
        docker build -t k0-kernel-local:latest -f (Join-Path $RepoRoot "Dockerfile") $RepoRoot | Write-Host
    }
}

function Ensure-Database {
    if ($Migrate -or -not (Test-Path $DbPath)) {
        Write-Info "Bootstrapping SQLite database at $DbPath"
        $env:PYTHONPATH = $RepoRoot
        $py = "from k0.automation.migrate import apply_migrations; from pathlib import Path; p=Path(r'''$DbPath'''); r=apply_migrations(p); print('Applied:', sum(1 for x in r if x.action=='applied'), 'Skipped:', sum(1 for x in r if x.action=='skipped'))"
        python -c $py | Write-Host
    }
}

function Compose-Args {
    "-p", $ProjectName, "-f", $ComposeKernel, "-f", $ComposeTelemetry
}

function Do-Up {
    Ensure-Compose-Prereqs
    Ensure-Image
    Ensure-Database
    Write-Info "Starting services (kernel + telemetry)"
    docker compose @(Compose-Args) up -d | Write-Host
    if ($Verify) {
        if ($WaitSeconds -gt 0) {
            Write-Info "Waiting $WaitSeconds seconds before verification"
            Start-Sleep -Seconds $WaitSeconds
        }
        Do-Verify
    }
}

function Do-Down {
    Write-Info "Stopping services"
    docker compose @(Compose-Args) down | Write-Host
}

function Do-Restart {
    Do-Down
    Do-Up
}

function Do-Status {
    docker compose @(Compose-Args) ps
}

function Do-Logs {
    if ($Service) {
        docker compose @(Compose-Args) logs -f --no-log-prefix --tail=200 -- $Service
    }
    else {
        docker compose @(Compose-Args) logs -f --no-log-prefix --tail=100
    }
}

function Do-Verify {
    Write-Info "Verifying service health"
    $checks = @(
        @{ Name = "kernel /healthz"; Url = "http://localhost:8080/healthz" },
        @{ Name = "kernel /readyz"; Url = "http://localhost:8080/readyz" },
        @{ Name = "prometheus"; Url = "http://localhost:9090/-/ready" },
        @{ Name = "grafana"; Url = "http://localhost:3000/api/health" },
        @{ Name = "alertmanager"; Url = "http://localhost:9093/-/ready" },
        @{ Name = "tempo"; Url = "http://localhost:3200/metrics" }
    )
    foreach ($c in $checks) {
        try {
            $code = (Invoke-WebRequest -UseBasicParsing -TimeoutSec 5 -Uri $c.Url).StatusCode
            if ($code -ge 200 -and $code -lt 300) {
                Write-Ok ("{0}: {1}" -f $c.Name, $code)
            }
            else {
                Write-Warn ("{0}: {1}" -f $c.Name, $code)
            }
        }
        catch {
            Write-Err ("{0}: {1}" -f $c.Name, $_.Exception.Message)
        }
    }
}

switch ($Command) {
    "up" { Do-Up }
    "down" { Do-Down }
    "restart" { Do-Restart }
    "status" { Do-Status }
    "logs" { Do-Logs }
}
