param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("up", "down", "restart", "status", "logs", "watch")]
    [string]$Command,

    [switch]$Rebuild,
    [switch]$Migrate,
    [switch]$Verify,
    [int]$WaitSeconds = 10,

    [string]$Service,
    [switch]$HotReload,
    [switch]$GPU
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

# Paths
$DeployRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent (Split-Path -Parent $DeployRoot)
$ComposeKernel = Join-Path $DeployRoot "docker-compose.yml"
$ComposeGPU = Join-Path $DeployRoot "docker-compose.gpu.yml"
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
    if ($GPU) {
        $imageName = "k0-kernel-gpu:latest"
        $dockerFile = Join-Path $DeployRoot "Dockerfile.gpu"
    }
    else {
        $imageName = "k0-kernel-local:latest"
        $dockerFile = Join-Path $DeployRoot "Dockerfile"
    }
    $imagePresent = (docker images --format "{{.Repository}}:{{.Tag}}" | Select-String -SimpleMatch $imageName)
    if ($Rebuild -or -not $imagePresent) {
        Write-Info "Building image $imageName"
        docker build -t $imageName -f $dockerFile $RepoRoot | Write-Host
    }
}

function Ensure-Database {
    # DEPRECATED: SQLite is no longer used. PostgreSQL migrations handled by Ensure-PostgreSQL-Schema
    Write-Info "Skipping SQLite database setup (using PostgreSQL now)"
}

function Ensure-PostgreSQL-Schema {
    if ($Migrate) {
        Write-Info "Running Alembic migrations for PostgreSQL"
        $env:PYTHONPATH = $RepoRoot

        # Load PostgreSQL environment variables from k0.env
        $envFile = Join-Path $EnvDir "k0.env"
        if (Test-Path $envFile) {
            Get-Content $envFile | ForEach-Object {
                if ($_ -match '^([^=]+)=(.*)$') {
                    $key = $matches[1].Trim()
                    $value = $matches[2].Trim()
                    if ($key -match '^K0_POSTGRES_' -or $key -match '^POSTGRES_') {
                        [System.Environment]::SetEnvironmentVariable($key, $value, [System.EnvironmentVariableTarget]::Process)
                    }
                }
            }
        }

        # Set environment for Alembic (connect to localhost since running from host)
        $env:K0_POSTGRES_HOST = "localhost"
        $env:K0_POSTGRES_PORT = "5432"
        $env:K0_POSTGRES_DB = "k0_kernel"
        $env:K0_POSTGRES_USER = "k0user"
        $env:K0_POSTGRES_PASSWORD = if ($env:POSTGRES_PASSWORD) { $env:POSTGRES_PASSWORD } else { "changeme" }

        try {
            # Run Alembic migrations from the k0/db directory
            Push-Location (Join-Path $RepoRoot "k0" "db")
            Write-Info "Running: alembic upgrade head"
            alembic upgrade head 2>&1 | Write-Host
            $exitCode = $LASTEXITCODE
            Pop-Location

            if ($exitCode -eq 0) {
                Write-Ok "PostgreSQL migrations completed successfully"
            }
            else {
                Write-Err "Alembic migration failed with exit code $exitCode"
            }
        }
        catch {
            Write-Err "Failed to run PostgreSQL migrations: $_"
        }
    }
}

function Ensure-Neo4j-Schema {
    if ($Migrate) {
        Write-Info "Bootstrapping Neo4j schema"
        $env:PYTHONPATH = $RepoRoot

        # Load Neo4j environment variables from k0.env
        $envFile = Join-Path $EnvDir "k0.env"
        if (Test-Path $envFile) {
            Get-Content $envFile | ForEach-Object {
                if ($_ -match '^([^=]+)=(.*)$') {
                    $key = $matches[1].Trim()
                    $value = $matches[2].Trim()
                    if ($key -match '^NEO4J_') {
                        [System.Environment]::SetEnvironmentVariable($key, $value, [System.EnvironmentVariableTarget]::Process)
                    }
                }
            }
        }

        # Use localhost for host-side migration (not container name)
        $neo4jUri = "neo4j://localhost:7687"
        $neo4jUser = $env:NEO4J_USERNAME
        $neo4jPass = $env:NEO4J_PASSWORD
        $neo4jDb = $env:NEO4J_DATABASE

        if (-not $neo4jUser) {
            Write-Warn "NEO4J_USERNAME not set, skipping Neo4j migrations"
            return
        }

        $neo4jPy = "from k0.automation.migrate_neo4j import apply_cypher_migrations; r=apply_cypher_migrations('$neo4jUri', '$neo4jUser', '$neo4jPass', '$neo4jDb'); print('Applied:', sum(1 for x in r if x.action=='applied'), 'Skipped:', sum(1 for x in r if x.action=='skipped'))"
        python -c $neo4jPy | Write-Host
    }
}

function Sync-Telemetry-Artifacts {
    Write-Info "Syncing telemetry artifacts from source to deployment"

    $SourceTelemetryDir = "$RepoRoot\k0\telemetry\generated"
    $DeployDashboardsDir = "$GeneratedDir\dashboards"
    $DeployRulesDir = "$GeneratedDir\rules"

    # Create deploy directories if they don't exist
    New-Item -ItemType Directory -Path $DeployDashboardsDir -Force | Out-Null
    New-Item -ItemType Directory -Path $DeployRulesDir -Force | Out-Null

    # Sync dashboards from source to deploy
    if (Test-Path "$SourceTelemetryDir\dashboards") {
        Write-Info "Syncing dashboards: $SourceTelemetryDir/dashboards -> $DeployDashboardsDir"
        Get-ChildItem -Path "$SourceTelemetryDir\dashboards" -Filter "*.json" | ForEach-Object {
            Copy-Item -Path $_.FullName -Destination $DeployDashboardsDir -Force
        }
        Write-Ok "Dashboards synced"
    }
    else {
        Write-Warn "Source dashboards not found at $SourceTelemetryDir/dashboards (run 'python -m k0.automation.telemetry_renderer' first)"
    }

    # Sync alert rules from source to deploy
    if (Test-Path "$SourceTelemetryDir\rules") {
        Write-Info "Syncing alert rules: $SourceTelemetryDir/rules -> $DeployRulesDir"
        Get-ChildItem -Path "$SourceTelemetryDir\rules" -Filter "*.yaml" | ForEach-Object {
            Copy-Item -Path $_.FullName -Destination $DeployRulesDir -Force
        }
        Write-Ok "Alert rules synced"
    }
    else {
        Write-Warn "Source alert rules not found at $SourceTelemetryDir/rules (run 'python -m k0.automation.telemetry_renderer' first)"
    }

    # Sync checksum files for validation
    if (Test-Path "$SourceTelemetryDir\checksums_dashboards.json") {
        Copy-Item -Path "$SourceTelemetryDir\checksums_dashboards.json" -Destination $GeneratedDir -Force
    }
    if (Test-Path "$SourceTelemetryDir\checksums_rules.json") {
        Copy-Item -Path "$SourceTelemetryDir\checksums_rules.json" -Destination $GeneratedDir -Force
    }
}

function Compose-Args {
    if ($GPU) {
        "-p", $ProjectName, "-f", $ComposeGPU, "-f", $ComposeTelemetry
    }
    else {
        "-p", $ProjectName, "-f", $ComposeKernel, "-f", $ComposeTelemetry
    }
}

function Start-HotReloadWatcher {
    param(
        [string]$WatchDir = $RepoRoot,
        [string]$ContainerName = "k0-kernel",
        [string]$HealthCheckUrl = "http://localhost:8080/readyz",
        [int]$GracePeriod = 5,
        [int]$RestartTimeout = 30
    )

    Write-Info "Starting hot reload watcher for development"
    Write-Info "  Watch Directory: $WatchDir"
    Write-Info "  Container Name: $ContainerName"
    Write-Info "  Health Check URL: $HealthCheckUrl"
    Write-Info "  Grace Period: $GracePeriod seconds"
    Write-Info "  Restart Timeout: $RestartTimeout seconds"

    # Verify Python environment
    try {
        $pythonCheck = python -c "import k0.automation.hot_reload_watcher; print('OK')" 2>&1
        if ($pythonCheck -notmatch "OK") {
            Write-Err "Failed to import hot_reload_watcher module"
            Write-Err "Ensure k0.automation package is in PYTHONPATH"
            return $false
        }
    }
    catch {
        Write-Err "Python module not found: $_"
        Write-Info "Install dependencies: pip install -r k0/automation/requirements.txt"
        return $false
    }

    # Launch watcher in background process
    try {
        $watcherCmd = @(
            "-m", "k0.automation.hot_reload_watcher",
            "--watch-dirs", $WatchDir,
            "--container-name", $ContainerName,
            "--health-check-url", $HealthCheckUrl,
            "--grace-period", $GracePeriod,
            "--restart-timeout", $RestartTimeout,
            "--verbose"
        )

        Write-Ok "Launching watcher process..."
        $process = Start-Process python -ArgumentList $watcherCmd -PassThru -WindowStyle Minimized -NoNewWindow

        if ($process -and $process.Id) {
            Write-Ok "Hot reload watcher started (PID: $($process.Id))"
            Write-Info "Watching $WatchDir for changes..."
            Write-Info "Press Ctrl+C to stop (in the watcher window)"
            Write-Warn "Watcher is running in background - use 'docker compose logs -f k0-kernel' to monitor restarts"
            return $true
        }
        else {
            Write-Err "Failed to start watcher process"
            return $false
        }
    }
    catch {
        Write-Err "Error starting hot reload watcher: $_"
        return $false
    }
}

function Do-Up {
    Ensure-Compose-Prereqs
    Sync-Telemetry-Artifacts
    Ensure-Image
    Ensure-Database

    Write-Info "Starting services (kernel + telemetry)"
    docker compose @(Compose-Args) up -d | Write-Host

    # Wait for PostgreSQL to be ready before running migrations
    if ($Migrate) {
        Write-Info "Waiting for PostgreSQL to be ready..."
        $maxRetries = 30
        $retryCount = 0
        $pgReady = $false

        while (-not $pgReady -and $retryCount -lt $maxRetries) {
            $retryCount++
            $healthCheck = docker compose @(Compose-Args) ps postgres --format json | ConvertFrom-Json
            if ($healthCheck.Health -eq "healthy") {
                $pgReady = $true
                Write-Ok "PostgreSQL is healthy"
            }
            else {
                Write-Host "." -NoNewline
                Start-Sleep -Seconds 2
            }
        }

        if (-not $pgReady) {
            Write-Warn "PostgreSQL did not become healthy in time, but continuing anyway"
        }

        Ensure-PostgreSQL-Schema

        # Wait for Neo4j to be ready
        Write-Info "Waiting for Neo4j to be ready..."
        $maxRetries = 30
        $retryCount = 0
        $neo4jReady = $false

        while (-not $neo4jReady -and $retryCount -lt $maxRetries) {
            $retryCount++
            $healthCheck = docker compose @(Compose-Args) ps neo4j --format json | ConvertFrom-Json
            if ($healthCheck.Health -eq "healthy") {
                $neo4jReady = $true
                Write-Ok "Neo4j is healthy"
            }
            else {
                Write-Host "." -NoNewline
                Start-Sleep -Seconds 2
            }
        }

        if (-not $neo4jReady) {
            Write-Warn "Neo4j did not become healthy in time, but continuing anyway"
        }

        Ensure-Neo4j-Schema
    }

    if ($Verify) {
        if ($WaitSeconds -gt 0) {
            Write-Info "Waiting $WaitSeconds seconds before verification"
            Start-Sleep -Seconds $WaitSeconds
        }
        Do-Verify
    }

    # Start hot reload watcher if -HotReload flag is set
    if ($HotReload) {
        Write-Info "Hot reload flag detected"
        $watcherHealthUrl = "http://localhost:8080/readyz"
        Start-HotReloadWatcher -WatchDir $RepoRoot -ContainerName "k0-kernel" -HealthCheckUrl $watcherHealthUrl -GracePeriod 5 -RestartTimeout 30 | Out-Null
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
    "watch" { Start-HotReloadWatcher -WatchDir $RepoRoot -ContainerName "k0-kernel" -HealthCheckUrl "http://localhost:8080/readyz" -GracePeriod 5 -RestartTimeout 30 }
}
