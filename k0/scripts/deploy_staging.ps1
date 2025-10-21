# Deploy staging environment using Pulumi-generated compose files
# Run from PowerShell on Windows (where Docker Desktop is installed)

$ComposeDir = "D:\memory_kernel\k0\deployment\compose\generated\local-single-node"
$StackName = "edge-cluster"

Write-Host "[staging] Deploying $StackName stack to Docker" -ForegroundColor Cyan
Write-Host "[staging] Compose directory: $ComposeDir" -ForegroundColor Cyan

Set-Location $ComposeDir

Write-Host "[staging] Starting services..." -ForegroundColor Yellow
docker-compose -f docker-compose.yml -f local-single-node-telemetry.yml up -d

Write-Host "[staging] Waiting for services to be healthy..." -ForegroundColor Yellow
Start-Sleep -Seconds 10

Write-Host "[staging] Service status:" -ForegroundColor Green
docker-compose -f docker-compose.yml -f local-single-node-telemetry.yml ps

Write-Host ""
Write-Host "[staging] Deployment complete!" -ForegroundColor Green
Write-Host "[staging] Services available at:" -ForegroundColor Green
Write-Host "  - Kernel:       http://localhost:8080"
Write-Host "  - Prometheus:   http://localhost:9090"
Write-Host "  - Grafana:      http://localhost:3000 (admin/ChangeMe!)"
Write-Host "  - Alertmanager: http://localhost:9093"
Write-Host ""
Write-Host "[staging] Next: Run traffic generator with:" -ForegroundColor Cyan
Write-Host "  python scripts/traffic_generator.py --endpoint http://localhost:8080 --rate 100 --duration 1h --scenario baseline"
