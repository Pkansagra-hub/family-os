#!/usr/bin/env python3
"""
Integration Dashboard Demo

Demonstrates the Integration Health Dashboard with live component monitoring.

Usage:
    python scripts/demo_integration_dashboard.py
    python scripts/demo_integration_dashboard.py --refresh  # Auto-refresh every 5s
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


async def main():
    """Run dashboard demo."""
    from monitoring.integration_dashboard import get_integration_dashboard

    dashboard = get_integration_dashboard()

    # Check for --refresh flag
    refresh = "--refresh" in sys.argv

    if refresh:
        print("🔄 Integration Dashboard - Auto-Refresh Mode (Ctrl+C to exit)")
        print("=" * 70)
        try:
            await dashboard.display_status(refresh=True)
        except KeyboardInterrupt:
            print("\n\n👋 Dashboard stopped.")
    else:
        print("📊 Integration Dashboard - Snapshot")
        print("=" * 70)
        status = await dashboard.display_status(refresh=False)
        print(status)
        print("\n💡 Tip: Run with --refresh flag for live updates every 5s")


if __name__ == "__main__":
    asyncio.run(main())
