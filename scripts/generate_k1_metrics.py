"""
Generate K1 Metrics for Testing

This script generates sample K1 metrics by making command submissions.
Run this alongside the K1 metrics server to populate Prometheus.

Usage:
    python scripts/generate_k1_metrics.py
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from k1.l5_infrastructure.observability import get_metrics, get_tracer


async def generate_sample_metrics():
    """Generate sample K1 metrics by creating command submissions"""

    print("🔧 Initializing K1 observability...")
    _metrics = get_metrics()  # Initialize but don't use directly
    _tracer = get_tracer()  # Initialize but don't use directly

    print("✅ Metrics initialized")
    print("✅ Tracer initialized")
    print()

    # Create command client (this initializes command metrics)
    print("🔧 Creating command client...")
    # Force reload to re-initialize metrics in this process
    import importlib

    from k1.l5_infrastructure.bridge_k0 import command_client

    importlib.reload(command_client)

    print("✅ Command client created")
    print()

    # Manually increment some test metrics
    print("📊 Generating sample metrics...")

    # Access the module-level metrics
    command_client.command_requests_total.labels(band="GREEN", status="success").inc()
    command_client.command_requests_total.labels(band="GREEN", status="success").inc()
    command_client.command_requests_total.labels(band="AMBER", status="success").inc()
    command_client.command_requests_total.labels(band="GREEN", status="error").inc()

    command_client.command_latency_ms.labels(band="GREEN").observe(45.5)
    command_client.command_latency_ms.labels(band="GREEN").observe(120.3)
    command_client.command_latency_ms.labels(band="AMBER").observe(78.2)

    command_client.command_retries_total.labels(band="GREEN", reason="timeout").inc()
    command_client.command_retries_total.labels(band="GREEN", reason="5xx").inc()

    print("✅ Generated sample metrics:")
    print("   - k1_intelligence_command_requests_total{band=GREEN,status=success}: 2")
    print("   - k1_intelligence_command_requests_total{band=AMBER,status=success}: 1")
    print("   - k1_intelligence_command_requests_total{band=GREEN,status=error}: 1")
    print("   - k1_intelligence_command_latency_ms{band=GREEN}: 2 observations")
    print("   - k1_intelligence_command_latency_ms{band=AMBER}: 1 observation")
    print("   - k1_intelligence_command_retries_total{band=GREEN}: 2")
    print()

    print("📡 Metrics are now available at http://localhost:8081/metrics")
    print("🔍 Check Prometheus at http://localhost:9090/targets")
    print()
    print("Press Ctrl+C to stop keeping metrics alive...")

    try:
        # Keep the process alive so metrics server can scrape
        while True:
            await asyncio.sleep(10)
            print(".", end="", flush=True)
    except KeyboardInterrupt:
        print("\n")
        print("👋 Shutting down")


if __name__ == "__main__":
    asyncio.run(generate_sample_metrics())
