#!/usr/bin/env python3
"""
P08 FAISS Indexer - Scheduled Batch Runner

Runs P08 FAISS indexing as a standalone scheduled job.
Queries st_vec for READY embeddings and adds them to FAISS index.

ADR Reference: ADR-K003 v1.2 (Inline Embedding via UltraBERT)

Usage:
    # Batch mode (default): Process up to 100 READY embeddings
    python k0/scripts/run_p08_indexer.py --batch-size 100

    # Single embedding mode: Process specific embedding
    python k0/scripts/run_p08_indexer.py --single emb_uuid_123

    # Continuous mode: Run every 5 minutes
    python k0/scripts/run_p08_indexer.py --continuous --interval 300

    # Filter by tenant/space
    python k0/scripts/run_p08_indexer.py --tenant-id tenant_abc --space-id space_xyz

Cron example (every 5 minutes):
    */5 * * * * cd /path/to/familyos && python k0/scripts/run_p08_indexer.py --batch-size 100

Version: 1.0.0
Last Updated: 2025-12-13
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
from pathlib import Path
from types import SimpleNamespace

# Add project root to path for imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from k0.kernel.syscalls import Syscalls
from k0.modules.embedding.faiss_indexer import run as faiss_indexer_run
from k0.uow.unit_of_work import UnitOfWork

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("p08_indexer")


def get_uow_factory():
    """
    Get UnitOfWork factory for database connections.

    Returns a factory function that creates UnitOfWork instances.
    UnitOfWork uses the global connection pool configured via connection_scope.
    """

    def factory():
        return UnitOfWork()

    return factory


async def run_indexer(
    batch_size: int = 100,
    single_embedding_id: str | None = None,
    tenant_id: str | None = None,
    space_id: str | None = None,
) -> dict:
    """
    Run the FAISS indexer with the given configuration.

    Args:
        batch_size: Maximum embeddings to process per batch
        single_embedding_id: Specific embedding to process (single mode)
        tenant_id: Optional tenant filter
        space_id: Optional space filter

    Returns:
        Result dictionary from faiss_indexer module
    """
    # Create syscalls with required capabilities
    syscalls = Syscalls(
        pipeline_id="P08_INDEXER",
        granted_caps={
            "st_vec.read",
            "st_vec.write",
            "faiss.read",
            "faiss.write",
        },
        uow_factory=get_uow_factory(),
    )

    # Create context with syscalls and logger
    context = SimpleNamespace(
        syscalls=syscalls,
        logger=logger,
    )

    # Build configuration
    config = {
        "batch_size": batch_size,
        "tenant_id": tenant_id,
        "space_id": space_id,
    }

    if single_embedding_id:
        config["embedding_id"] = single_embedding_id

    # Run the indexer
    start_time = time.perf_counter()
    result = await faiss_indexer_run(None, context, **config)
    elapsed_ms = (time.perf_counter() - start_time) * 1000

    logger.info(
        f"P08 Indexer complete: {result.get('indexed', 0)} indexed, "
        f"{result.get('failures', 0)} failures, "
        f"{elapsed_ms:.1f}ms elapsed"
    )

    return result


async def run_continuous(
    interval_seconds: int,
    batch_size: int,
    tenant_id: str | None = None,
    space_id: str | None = None,
) -> None:
    """
    Run the indexer continuously at the specified interval.

    Args:
        interval_seconds: Seconds between runs
        batch_size: Maximum embeddings to process per batch
        tenant_id: Optional tenant filter
        space_id: Optional space filter
    """
    logger.info(f"Starting P08 continuous indexer (interval={interval_seconds}s)")

    run_count = 0
    total_indexed = 0

    while True:
        run_count += 1
        logger.info(f"P08 Indexer run #{run_count}")

        try:
            result = await run_indexer(
                batch_size=batch_size,
                tenant_id=tenant_id,
                space_id=space_id,
            )
            total_indexed += result.get("indexed", 0)

            logger.info(f"Run #{run_count} complete. Total indexed so far: {total_indexed}")

        except Exception as e:
            logger.error(f"Run #{run_count} failed: {e}")

        # Wait for next interval
        logger.debug(f"Sleeping {interval_seconds}s until next run...")
        await asyncio.sleep(interval_seconds)


async def main(args: argparse.Namespace) -> int:
    """
    Main entry point.

    Args:
        args: Parsed command-line arguments

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    try:
        if args.continuous:
            # Continuous mode - run indefinitely
            await run_continuous(
                interval_seconds=args.interval,
                batch_size=args.batch_size,
                tenant_id=args.tenant_id,
                space_id=args.space_id,
            )
            return 0  # Never reached unless interrupted

        else:
            # Single run mode
            result = await run_indexer(
                batch_size=args.batch_size,
                single_embedding_id=args.single,
                tenant_id=args.tenant_id,
                space_id=args.space_id,
            )

            # Print summary
            print(f"Indexed: {result.get('indexed', 0)}")
            print(f"Failures: {result.get('failures', 0)}")
            print(f"Batch size: {result.get('batch_size', 0)}")

            if result.get("empty"):
                print("No READY embeddings found.")

            return 0 if result.get("failures", 0) == 0 else 1

    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        return 0

    except Exception as e:
        logger.error(f"P08 Indexer failed: {e}")
        return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="P08 FAISS Indexer - Scheduled Batch Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Process up to 100 READY embeddings
    python run_p08_indexer.py --batch-size 100

    # Process a specific embedding
    python run_p08_indexer.py --single emb_uuid_abc123

    # Run continuously every 5 minutes
    python run_p08_indexer.py --continuous --interval 300

    # Filter by tenant
    python run_p08_indexer.py --tenant-id tenant_abc
        """,
    )

    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Maximum embeddings to process per batch (default: 100)",
    )
    parser.add_argument(
        "--single",
        type=str,
        metavar="EMBEDDING_ID",
        help="Process a single embedding by ID (debug mode)",
    )
    parser.add_argument(
        "--tenant-id",
        type=str,
        help="Filter embeddings by tenant_id",
    )
    parser.add_argument(
        "--space-id",
        type=str,
        help="Filter embeddings by space_id",
    )
    parser.add_argument(
        "--continuous",
        action="store_true",
        help="Run continuously at the specified interval",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=300,
        help="Seconds between runs in continuous mode (default: 300 = 5 min)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose (DEBUG) logging",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    exit_code = asyncio.run(main(args))
    sys.exit(exit_code)
