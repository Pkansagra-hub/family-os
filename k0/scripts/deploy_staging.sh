#!/usr/bin/env bash
# Deploy staging environment using Pulumi-generated compose files

set -euo pipefail

COMPOSE_DIR="/mnt/d/memory_kernel/k0/deployment/compose/generated/local-single-node"
STACK_NAME="edge-cluster"

echo "[staging] Deploying ${STACK_NAME} stack to Docker"
echo "[staging] Compose directory: ${COMPOSE_DIR}"

cd "${COMPOSE_DIR}"

# Check if docker is available
if ! command -v docker &> /dev/null; then
    echo "ERROR: Docker not available in WSL. Please run from Windows PowerShell:"
    echo ""
    echo "cd D:\\memory_kernel\\k0\\deployment\\compose\\generated\\local-single-node"
    echo "docker-compose -f docker-compose.yml -f local-single-node-telemetry.yml up -d"
    echo ""
    exit 1
fi

echo "[staging] Starting services..."
docker-compose -f docker-compose.yml -f local-single-node-telemetry.yml up -d

echo "[staging] Waiting for services to be healthy..."
sleep 10

echo "[staging] Service status:"
docker-compose -f docker-compose.yml -f local-single-node-telemetry.yml ps

echo ""
echo "[staging] Deployment complete!"
echo "[staging] Services available at:"
echo "  - Kernel:       http://localhost:8080"
echo "  - Prometheus:   http://localhost:9090"
echo "  - Grafana:      http://localhost:3000"
echo "  - Alertmanager: http://localhost:9093"
echo ""
echo "[staging] Next: Run traffic generator with:"
echo "  python scripts/traffic_generator.py --endpoint http://localhost:8080 --rate 100 --duration 1h --scenario baseline"
