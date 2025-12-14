#!/usr/bin/env python
"""
Backfill Pending Embeddings - Migration Script

This script executes Epic 4.1 Issue 4.1.1: Execute Legacy Embedding Backfill.

Purpose:
- Count st_hipp_events records with embedding_status=PENDING
- Trigger P08 backfill via cognitive.backfill.requested.v1 events
- Monitor progress and verify completion

Usage:
    python k0/scripts/backfill_pending_embeddings.py --dry-run
    python k0/scripts/backfill_pending_embeddings.py --batch-size 100
    python k0/scripts/backfill_pending_embeddings.py --tenant-id <tenant> --space-id <space>

ADR Reference: ADR-K003 (Inline Embedding via UltraBERT)
"""

import argparse
import asyncio
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class BackfillExecutor:
    """Orchestrates embedding backfill for PENDING records."""

    def __init__(
        self,
        db_path: str,
        batch_size: int = 100,
        dry_run: bool = False,
        tenant_id: str | None = None,
        space_id: str | None = None,
    ):
        self.db_path = db_path
        self.batch_size = batch_size
        self.dry_run = dry_run
        self.tenant_id = tenant_id
        self.space_id = space_id
        self.conn: sqlite3.Connection | None = None

    def connect(self) -> None:
        """Connect to K0 runtime database."""
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        print(f"✅ Connected to database: {self.db_path}")

    def close(self) -> None:
        """Close database connection."""
        if self.conn:
            self.conn.close()
            print("✅ Database connection closed")

    def count_pending_records(self) -> dict[str, Any]:
        """Count PENDING embedding records by tenant/space."""
        if not self.conn:
            raise RuntimeError("Database not connected")

        query = """
            SELECT
                tenant_id,
                space_id,
                COUNT(*) as pending_count
            FROM st_hipp_events
            WHERE embedding_status = 'PENDING'
        """

        params = []
        if self.tenant_id:
            query += " AND tenant_id = ?"
            params.append(self.tenant_id)
        if self.space_id:
            query += " AND space_id = ?"
            params.append(self.space_id)

        query += " GROUP BY tenant_id, space_id ORDER BY pending_count DESC"

        cursor = self.conn.execute(query, params)
        results = cursor.fetchall()

        summary = {
            "total_pending": sum(row["pending_count"] for row in results),
            "by_tenant_space": [
                {
                    "tenant_id": row["tenant_id"],
                    "space_id": row["space_id"],
                    "pending_count": row["pending_count"],
                }
                for row in results
            ],
        }

        return summary

    def calculate_batch_count(self, total_pending: int) -> int:
        """Calculate number of batches required."""
        return (total_pending + self.batch_size - 1) // self.batch_size

    async def trigger_backfill_event(
        self, tenant_id: str, space_id: str, batch_num: int, total_batches: int
    ) -> bool:
        """
        Trigger cognitive.backfill.requested.v1 event.

        In production, this would emit to the event bus.
        For now, we'll simulate the trigger.
        """
        event_payload = {
            "topic": "cognitive.backfill.requested.v1",
            "payload": {
                "tenant_id": tenant_id,
                "space_id": space_id,
                "batch_size": self.batch_size,
                "batch_num": batch_num,
                "total_batches": total_batches,
                "requested_at": datetime.utcnow().isoformat(),
            },
            "metadata": {
                "correlation_id": f"backfill_{tenant_id}_{space_id}_{batch_num}",
                "source": "migration.backfill_pending_embeddings",
            },
        }

        if self.dry_run:
            print(f"  [DRY-RUN] Would emit event: {event_payload['topic']}")
            print(f"            Batch {batch_num}/{total_batches}, size {self.batch_size}")
            return True

        # TODO: In production, emit to actual event bus
        # await event_bus.emit(event_payload)
        print(f"  ⚠️ TODO: Emit {event_payload['topic']} to event bus")
        print(f"           Batch {batch_num}/{total_batches}")
        return False  # Not actually executed yet

    async def execute_backfill(self) -> dict[str, Any]:
        """Execute backfill for all PENDING records."""
        print("\n" + "=" * 60)
        print("BACKFILL PENDING EMBEDDINGS - MIGRATION SCRIPT")
        print("=" * 60)
        print(f"Batch Size: {self.batch_size}")
        print(f"Dry Run: {self.dry_run}")
        print(f"Tenant Filter: {self.tenant_id or 'ALL'}")
        print(f"Space Filter: {self.space_id or 'ALL'}")
        print("=" * 60 + "\n")

        # Step 1: Count PENDING records
        print("Step 1: Counting PENDING records...")
        summary = self.count_pending_records()
        total_pending = summary["total_pending"]

        print(f"\n📊 Total PENDING Records: {total_pending:,}")
        print(f"📊 Tenants/Spaces: {len(summary['by_tenant_space'])}")

        if total_pending == 0:
            print("\n✅ No PENDING records found. Backfill not needed.")
            return {"status": "complete", "pending_count": 0, "batches_triggered": 0}

        # Step 2: Calculate batch requirements
        total_batches = self.calculate_batch_count(total_pending)
        print(f"📦 Batches Required: {total_batches:,} (batch_size={self.batch_size})")

        # Step 3: Display breakdown by tenant/space
        print("\n📋 Breakdown by Tenant/Space:")
        for item in summary["by_tenant_space"][:10]:  # Show top 10
            print(f"   - {item['tenant_id']}/{item['space_id']}: {item['pending_count']:,} records")
        if len(summary["by_tenant_space"]) > 10:
            print(f"   ... and {len(summary['by_tenant_space']) - 10} more")

        # Step 4: Trigger backfill events
        print("\nStep 2: Triggering backfill events...")
        if self.dry_run:
            print("  [DRY-RUN] Simulating event emission...\n")

        batches_triggered = 0
        for item in summary["by_tenant_space"]:
            tenant_id = item["tenant_id"]
            space_id = item["space_id"]
            pending_count = item["pending_count"]
            batches_for_space = self.calculate_batch_count(pending_count)

            print(
                f"\n  Processing {tenant_id}/{space_id} ({pending_count:,} records, {batches_for_space} batches):"
            )

            for batch_num in range(1, batches_for_space + 1):
                success = await self.trigger_backfill_event(
                    tenant_id, space_id, batch_num, batches_for_space
                )
                if success or self.dry_run:
                    batches_triggered += 1

                # Small delay to avoid overwhelming the system
                if not self.dry_run:
                    await asyncio.sleep(0.1)

        # Step 5: Summary
        print("\n" + "=" * 60)
        print("BACKFILL SUMMARY")
        print("=" * 60)
        print(f"Total PENDING Records: {total_pending:,}")
        print(f"Batches Triggered: {batches_triggered:,}/{total_batches:,}")
        if self.dry_run:
            print("Dry Run: True (no actual events emitted)")
        print("=" * 60 + "\n")

        return {
            "status": "triggered" if batches_triggered > 0 else "pending",
            "pending_count": total_pending,
            "batches_triggered": batches_triggered,
            "dry_run": self.dry_run,
        }

    async def verify_completion(self) -> dict[str, Any]:
        """Verify that backfill completed successfully."""
        print("\nStep 3: Verifying backfill completion...")

        summary = self.count_pending_records()
        remaining_pending = summary["total_pending"]

        if remaining_pending == 0:
            print("✅ All records processed! No PENDING records remaining.")
            return {"status": "complete", "remaining_pending": 0}
        else:
            print(f"⚠️ {remaining_pending:,} PENDING records still remaining.")
            print("   - Check P08 backfill logs for errors")
            print("   - Verify UltraBERT is available")
            print("   - Re-run this script to retry failed records")
            return {"status": "incomplete", "remaining_pending": remaining_pending}


async def main():
    parser = argparse.ArgumentParser(
        description="Backfill PENDING embeddings for P02/P08 migration (Epic 4.1 Issue 4.1.1)"
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default="k0_runtime.sqlite3",
        help="Path to K0 runtime database (default: k0_runtime.sqlite3)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Batch size for backfill (default: 100)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate backfill without emitting events",
    )
    parser.add_argument(
        "--tenant-id",
        type=str,
        default=None,
        help="Filter by tenant_id (optional)",
    )
    parser.add_argument(
        "--space-id",
        type=str,
        default=None,
        help="Filter by space_id (optional)",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Only verify completion, don't trigger backfill",
    )

    args = parser.parse_args()

    executor = BackfillExecutor(
        db_path=args.db_path,
        batch_size=args.batch_size,
        dry_run=args.dry_run,
        tenant_id=args.tenant_id,
        space_id=args.space_id,
    )

    try:
        executor.connect()

        if args.verify_only:
            result = await executor.verify_completion()
        else:
            result = await executor.execute_backfill()

            if not args.dry_run and result["batches_triggered"] > 0:
                print("\n⏳ Waiting 5 seconds for backfill to process...")
                await asyncio.sleep(5)
                await executor.verify_completion()

        return 0 if result.get("status") == "complete" else 1

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
        return 1
    finally:
        executor.close()


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
