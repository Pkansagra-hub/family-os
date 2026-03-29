"""
Run P03 consolidation in batches until all events are consolidated.

This script triggers the P03_CONSOLIDATION pipeline repeatedly until
all PENDING events have been processed.

Usage:
    python consolidate_batches.py [--max-batches N] [--batch-size N] [--delay-seconds N]

Options:
    --max-batches N      Maximum number of batches to run (default: unlimited)
    --batch-size N       Events per batch (default: 100, max: 1000)
    --delay-seconds N    Delay between batches in seconds (default: 2)
    --dry-run            Show pending count without running consolidation
"""

import argparse
import subprocess
import sys
import time

import requests

# =============================================================================
# CONFIGURATION
# =============================================================================

BASE_URL = "http://localhost:8080"
PG_USER = "k0user"
PG_DB = "k0_kernel"
DEFAULT_BATCH_SIZE = 100
DEFAULT_DELAY_SECONDS = 2


def get_pending_count() -> tuple[int, int, int]:
    """Get count of pending and consolidated events.

    Returns:
        Tuple of (pending_count, consolidated_count, total_count)
    """
    cmd = [
        "docker",
        "exec",
        "k0-postgres",
        "psql",
        "-U",
        PG_USER,
        "-d",
        PG_DB,
        "-t",
        "-A",
        "-c",
        """
        SELECT
            COALESCE(SUM(CASE WHEN consolidation_status IS NULL THEN 1 ELSE 0 END), 0) as pending,
            COALESCE(SUM(CASE WHEN consolidation_status = 'CONSOLIDATED' THEN 1 ELSE 0 END), 0) as consolidated,
            COUNT(*) as total
        FROM st_hipp_events;
        """,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"ERROR querying database: {result.stderr}")
        sys.exit(1)

    parts = result.stdout.strip().split("|")
    if len(parts) == 3:
        return int(parts[0]), int(parts[1]), int(parts[2])
    return 0, 0, 0


def trigger_consolidation(
    batch_size: int = 100,
    skip_r5: bool = False,
    tenant_id: str = "tenant-test",
    space_id: str = "space-home",
) -> dict:
    """Trigger P03 consolidation pipeline.

    Args:
        batch_size: Maximum events to process in this batch
        skip_r5: Whether to skip the dream exploration phase (faster)
        tenant_id: Target tenant for consolidation
        space_id: Target space for consolidation

    Returns:
        Response JSON from the API
    """
    url = f"{BASE_URL}/k0/admin/pipelines/P03_CONSOLIDATION/trigger"
    payload = {
        "reason": f"Batch consolidation (batch_size={batch_size})",
        "options": {
            "max_events": batch_size,
            "skip_r5": skip_r5,
            "tenant_id": tenant_id,
            "space_id": space_id,
        },
    }

    try:
        response = requests.post(url, json=payload, timeout=300)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        return {"success": False, "error": str(e)}


def run_consolidation_loop(
    max_batches: int | None = None,
    batch_size: int = 100,
    delay_seconds: float = 2.0,
    skip_r5: bool = False,
    tenant_id: str = "tenant-test",
    space_id: str = "space-home",
) -> None:
    """Run consolidation in a loop until all events are processed.

    Args:
        max_batches: Maximum number of batches to run (None = unlimited)
        batch_size: Events per batch
        delay_seconds: Delay between batches
        skip_r5: Whether to skip R5 dream exploration
        tenant_id: Target tenant for consolidation
        space_id: Target space for consolidation
    """
    print("=" * 60)
    print("P03 BATCH CONSOLIDATION")
    print("=" * 60)
    print(f"  Batch size: {batch_size}")
    print(f"  Delay between batches: {delay_seconds}s")
    print(f"  Max batches: {max_batches or 'unlimited'}")
    print(f"  Skip R5 (dream exploration): {skip_r5}")
    print(f"  Tenant ID: {tenant_id}")
    print(f"  Space ID: {space_id}")
    print("=" * 60)

    batch_num = 0
    total_consolidated = 0
    start_time = time.time()

    while True:
        # Check current status
        pending, consolidated, total = get_pending_count()

        if pending == 0:
            print("\n✅ ALL EVENTS CONSOLIDATED!")
            print(f"   Total events: {total}")
            print(f"   Consolidated: {consolidated}")
            break

        if max_batches is not None and batch_num >= max_batches:
            print(f"\n⚠️  Reached max batches limit ({max_batches})")
            print(f"   Remaining pending: {pending}")
            break

        batch_num += 1
        batches_needed = (pending + batch_size - 1) // batch_size

        print(f"\n--- BATCH {batch_num} ---")
        print(f"  Pending: {pending} | Consolidated: {consolidated} | Total: {total}")
        print(f"  Estimated batches remaining: {batches_needed}")

        # Trigger consolidation
        print("  Triggering P03 consolidation...")
        result = trigger_consolidation(
            batch_size=batch_size, skip_r5=skip_r5, tenant_id=tenant_id, space_id=space_id
        )

        if result.get("success"):
            print(f"  ✓ Trigger successful: {result.get('message', 'OK')}")

            # Wait for consolidation to complete
            # P03 typically takes 3-10 seconds depending on batch size
            wait_time = max(delay_seconds, batch_size / 50)  # ~2s per 100 events
            print(f"  Waiting {wait_time:.1f}s for completion...")
            time.sleep(wait_time)

            # Check results
            new_pending, new_consolidated, _ = get_pending_count()
            events_processed = pending - new_pending
            total_consolidated += events_processed

            if events_processed > 0:
                print(f"  ✓ Processed {events_processed} events this batch")
            else:
                print("  ⚠️  No events processed (may need longer wait)")
                time.sleep(2)  # Extra wait
        else:
            print(f"  ✗ Trigger failed: {result.get('error', 'Unknown error')}")
            time.sleep(5)  # Back off on error

    # Final summary
    elapsed = time.time() - start_time
    print("\n" + "=" * 60)
    print("CONSOLIDATION SUMMARY")
    print("=" * 60)
    print(f"  Batches run: {batch_num}")
    print(f"  Events consolidated: {total_consolidated}")
    print(f"  Time elapsed: {elapsed:.1f}s")
    if batch_num > 0:
        print(f"  Avg time per batch: {elapsed / batch_num:.1f}s")

    # Final status
    pending, consolidated, total = get_pending_count()
    print("\n  Final status:")
    print(f"    Pending: {pending}")
    print(f"    Consolidated: {consolidated}")
    print(f"    Total: {total}")


def main():
    parser = argparse.ArgumentParser(description="Run P03 consolidation in batches")
    parser.add_argument(
        "--max-batches",
        "-n",
        type=int,
        default=None,
        help="Maximum number of batches to run (default: unlimited)",
    )
    parser.add_argument(
        "--batch-size",
        "-b",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f"Events per batch (default: {DEFAULT_BATCH_SIZE})",
    )
    parser.add_argument(
        "--delay-seconds",
        "-d",
        type=float,
        default=DEFAULT_DELAY_SECONDS,
        help=f"Delay between batches in seconds (default: {DEFAULT_DELAY_SECONDS})",
    )
    parser.add_argument(
        "--skip-r5",
        action="store_true",
        help="Skip R5 dream exploration phase (faster consolidation)",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Show pending count without running consolidation"
    )
    parser.add_argument(
        "--tenant-id",
        type=str,
        default="tenant-test",
        help="Target tenant ID (default: tenant-test)",
    )
    parser.add_argument(
        "--space-id", type=str, default="space-home", help="Target space ID (default: space-home)"
    )

    args = parser.parse_args()

    if args.dry_run:
        pending, consolidated, total = get_pending_count()
        print("CURRENT STATUS:")
        print(f"  Pending: {pending}")
        print(f"  Consolidated: {consolidated}")
        print(f"  Total: {total}")
        batches_needed = (pending + args.batch_size - 1) // args.batch_size if pending > 0 else 0
        print(
            f"\nWith batch_size={args.batch_size}, need {batches_needed} batches to consolidate all"
        )
        return

    run_consolidation_loop(
        max_batches=args.max_batches,
        batch_size=args.batch_size,
        delay_seconds=args.delay_seconds,
        skip_r5=args.skip_r5,
        tenant_id=args.tenant_id,
        space_id=args.space_id,
    )


if __name__ == "__main__":
    main()
