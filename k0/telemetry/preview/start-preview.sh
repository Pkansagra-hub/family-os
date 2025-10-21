#!/usr/bin/env bash
# K0 Telemetry Preview Stack Helper Script (Linux/macOS)

set -e

echo "🚀 Starting K0 Telemetry Preview Stack..."

# Change to preview directory
cd "$(dirname "$0")"

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker first."
    exit 1
fi

# Render dashboards and rules first
echo "📊 Rendering dashboards and alert rules..."
REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
pushd "$REPO_ROOT" > /dev/null
python -m k0.telemetry.render --verbose || {
    popd > /dev/null
    echo "❌ Failed to render telemetry artifacts."
    exit 1
}
popd > /dev/null

# Start Docker Compose stack
echo "🐳 Starting Docker Compose services..."
docker-compose up -d

echo ""
echo "✅ K0 Telemetry Preview Stack is running!"
echo ""
echo "📊 Grafana:    http://localhost:3000  (admin/admin)"
echo "📈 Prometheus: http://localhost:9090"
echo ""
echo "💡 Tip: Start the K0 kernel on port 8080 (or run the container bundle) to expose metrics at /metrics."
echo ""
echo "To stop: docker-compose down"
