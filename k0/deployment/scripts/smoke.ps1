param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("local-single-node", "edge-cluster", "datacenter-ha")]
    [string]$Stack
)

$ErrorActionPreference = "Stop"

Write-Host "[k0] Running smoke test for stack '$Stack'" -ForegroundColor Cyan

Write-Host "[k0] Executing Pulumi preview" -ForegroundColor Cyan
$artifactsDir = Join-Path "artifacts/pulumi" $Stack
python -m k0.deployment.pulumi.smoke --stack $Stack --artifacts-dir $artifactsDir | ForEach-Object { Write-Host $_ }

Write-Host "[k0] Validating bundle manifest schema" -ForegroundColor Cyan
$bundlePath = Join-Path $artifactsDir ("bundles/{0}" -f $Stack)
python -m k0.deployment.pulumi.validation $bundlePath | ForEach-Object { Write-Host $_ }

Write-Host "[k0] Executing telemetry verifier snapshot" -ForegroundColor Cyan
python -m k0.automation.verify_security_telemetry -d artifacts/telemetry 2>$null
