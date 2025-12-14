#!/usr/bin/env python3
"""
Local Pipeline Testing Script
==============================
Tests pipeline execution locally without Docker kernel.
Reusable for all future pipelines (P02, P03, P04, etc.).

Usage:
    python k0/scripts/test_pipeline_local.py --pipeline P02_WRITE
    python k0/scripts/test_pipeline_local.py --pipeline P02_WRITE --debug
    python k0/scripts/test_pipeline_local.py --pipeline P02_WRITE --envelope custom_envelope.json

Features:
- Loads actual pipeline YAML specifications
- Executes full DAG with parallel execution
- Uses real module implementations
- Validates contracts and enrichment flow
- Provides detailed execution metrics
- No Docker dependency
"""

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import structlog

from k0.bus.core import BusMessage
from k0.runtime.dag_builder import build_dag
from k0.runtime.module_registry import ModuleRegistry
from k0.runtime.pipeline_runner import PipelineRunner
from k0.runtime.schemas import PipelineSpec

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


class LocalPipelineContext:
    """Minimal context for local pipeline execution"""

    def __init__(self, pipeline_id: str, debug: bool = False):
        self.pipeline_id = pipeline_id
        self.logger = structlog.get_logger(f"local.{pipeline_id}")
        if debug:
            self.logger.setLevel(logging.DEBUG)

    def get_logger(self):
        return self.logger


class LocalSyscalls:
    """Local syscalls implementation for testing"""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or Path("k0_runtime.sqlite3")
        self.logger = structlog.get_logger("local.syscalls")
        self.writes = []  # Track all writes for verification

    async def write_hipp_event(self, record: Dict[str, Any]) -> None:
        """Simulate st_hipp_events.write"""
        self.logger.info(f"[WRITE] st_hipp_events: event_id={record.get('event_id')}")
        self.writes.append(("st_hipp_events", record))

    async def write_pipeline_processed(self, record: Dict[str, Any]) -> None:
        """Simulate st_pipeline_processed.write"""
        self.logger.info(f"[WRITE] st_pipeline_processed: trace_id={record.get('trace_id')}")
        self.writes.append(("st_pipeline_processed", record))

    async def write_embedding_queue(self, record: Dict[str, Any]) -> None:
        """Simulate st_embedding_queue.write"""
        self.logger.info(f"[WRITE] st_embedding_queue: job_id={record.get('job_id')}")
        self.writes.append(("st_embedding_queue", record))

    async def write_outbox(self, record: Dict[str, Any]) -> None:
        """Simulate st_outbox.write"""
        self.logger.info(f"[WRITE] st_outbox: topic={record.get('topic')}")
        self.writes.append(("st_outbox", record))

    async def hipp_events_upsert(self, **kwargs) -> Dict[str, Any]:
        """Simulate st_hipp_events.upsert"""
        self.logger.info(
            f"[UPSERT] st_hipp_events: event_id={kwargs.get('event_id')}, wal_pos={kwargs.get('wal_pos')}"
        )
        self.writes.append(("st_hipp_events", kwargs))
        return {"inserted": True, "status": "OK"}

    async def pipeline_processed_upsert(self, **kwargs) -> Dict[str, Any]:
        """Simulate st_pipeline_processed.upsert"""
        self.logger.info(
            f"[UPSERT] st_pipeline_processed: pipeline_id={kwargs.get('pipeline_id')}, wal_pos={kwargs.get('wal_pos')}"
        )
        self.writes.append(("st_pipeline_processed", kwargs))
        return {"inserted": True, "status": "OK"}

    def get_write_summary(self) -> Dict[str, int]:
        """Get summary of writes by table"""
        summary = {}
        for table, _ in self.writes:
            summary[table] = summary.get(table, 0) + 1
        return summary


def create_test_envelope(trace_id: Optional[str] = None) -> Dict[str, Any]:
    """Create a realistic test envelope"""
    now = datetime.now(timezone.utc)
    trace_id = trace_id or f"test-{now.timestamp()}"

    return {
        "cognitive_trace_id": trace_id,
        "tenant_id": "tenant-test",
        "space_id": "space-home",
        "topic": "memory.delta",
        "schema_uri": "schema://memory.delta",
        "schema_version": "1.0",
        "actor": "actor-test-123",
        "device_id": "device-test-1",
        "band": "GREEN",
        "policy_version": "2025-09-28",
        "ts": now.isoformat(),
        "payload_sha256": "test-sha256-hash",
        "sig_alg": "Ed25519SHA512",
        "sig_kid": "device-test-1",
        "sig": "test-signature",
        "envelope_sha256": "test-envelope-hash",
        "body": {
            "operation": "UPSERT",
            "text": "Hello from local test!",
            "timestamp": now.isoformat(),
            "value": 42,
        },
        # Additional fields for realistic processing
        "event": {
            "event_time_utc": now.isoformat(),
            "event_type": "observation",
        },
        "wal_pos": 1000,
        "bus_topic": "cognitive.memory.write.committed.v1",
        "bus_offset": 1,
    }


def load_envelope_from_file(filepath: Path) -> Dict[str, Any]:
    """Load envelope from JSON file"""
    with open(filepath, "r") as f:
        return json.load(f)


async def run_pipeline_test(
    pipeline_id: str, envelope: Optional[Dict[str, Any]] = None, debug: bool = False
) -> Dict[str, Any]:
    """
    Run full pipeline test locally

    Args:
        pipeline_id: Pipeline ID (e.g., "P02_WRITE")
        envelope: Custom envelope or None to use default test envelope
        debug: Enable debug logging

    Returns:
        Execution results with metrics and validation status
    """
    logger = structlog.get_logger("local.test")
    if debug:
        logging.getLogger().setLevel(logging.DEBUG)

    logger.info("=" * 80)
    logger.info(f"Local Pipeline Test: {pipeline_id}")
    logger.info("=" * 80)

    # 1. Load pipeline specification
    logger.info("\n[Step 1] Loading pipeline specification...")
    contracts_dir = project_root / "k0" / "contracts" / "pipelines"
    pipeline_file = contracts_dir / f"{pipeline_id.lower()}.v1.yaml"

    if not pipeline_file.exists():
        raise FileNotFoundError(f"Pipeline spec not found: {pipeline_file}")

    logger.info(f"   Found: {pipeline_file}")

    # 2. Load module registry
    logger.info("\n[Step 2] Loading module registry...")
    module_contracts_dir = project_root / "k0" / "contracts" / "modules"
    registry = ModuleRegistry()
    await registry.load_contracts(module_contracts_dir)
    logger.info(f"   Loaded {len(registry._contracts)} modules")

    # 3. Build DAG
    logger.info("\n Step 3: Building execution DAG...")
    spec = PipelineSpec.load(str(pipeline_file))
    dag = build_dag(spec)

    level_groups = dag.get_level_groups()
    max_parallelism = max(len(group) for group in level_groups)

    logger.info("   DAG built successfully")
    logger.info(f"   Stages: {len(dag)}")
    logger.info(f"   Execution levels: {len(level_groups)}")
    logger.info(f"   Max parallelism: {max_parallelism}")

    # Print level structure
    for level_idx, stages in enumerate(level_groups):
        stage_ids = [s.id for s in stages]
        logger.info(f"   Level {level_idx}: {len(stages)} stages - {stage_ids}")

    # 4. Create context and syscalls
    logger.info("\n  Step 4: Initializing context...")
    context = LocalPipelineContext(pipeline_id, debug=debug)
    syscalls = LocalSyscalls()

    # Inject syscalls into context
    context.syscalls = syscalls

    logger.info("   Context initialized")

    # 5. Create pipeline runner
    logger.info("\n[Step 5] Creating pipeline runner...")
    runner = PipelineRunner(spec=spec, registry=registry)
    runner._context = context
    logger.info("   Runner created")

    # 6. Prepare envelope
    logger.info("\n[Step 6] Preparing test envelope...")
    if envelope is None:
        envelope = create_test_envelope()

    trace_id = envelope.get("cognitive_trace_id", "unknown")
    logger.info("   Envelope ready")
    logger.info(f"   Trace ID: {trace_id}")
    logger.info(f"   Topic: {envelope.get('topic')}")
    logger.info(f"   Body: {json.dumps(envelope.get('body'), indent=2)}")

    # 7. Create bus message
    message = BusMessage(
        trace_id=trace_id,
        topic=spec.entry_topic,
        payload=json.dumps(envelope).encode("utf-8"),
        offset=envelope.get("bus_offset", 1),
        space_id=envelope.get("space_id"),
        metadata={"band": envelope.get("band", "GREEN"), "port": "bus"},
    )

    # 8. Execute pipeline
    logger.info("\n Step 7: Executing pipeline...")
    logger.info(f"   Starting execution at {datetime.now(timezone.utc).isoformat()}")

    start_time = datetime.now(timezone.utc)

    try:
        await runner.handle(message)
        success = True
        error = None
    except Exception as e:
        success = False
        error = str(e)
        logger.error(f"   ✗ Pipeline failed: {e}", exc_info=True)

    end_time = datetime.now(timezone.utc)
    duration_ms = (end_time - start_time).total_seconds() * 1000

    # 9. Collect results
    logger.info("\n Step 8: Collecting results...")

    results = {
        "success": success,
        "error": error,
        "pipeline_id": pipeline_id,
        "trace_id": trace_id,
        "duration_ms": round(duration_ms, 3),
        "stages": {
            "total": len(dag),
            "completed": len(runner._completed_stages),
            "failed": len(runner._failed_stages),
        },
        "execution_levels": len(level_groups),
        "max_parallelism": max_parallelism,
        "stage_timings_ms": {k: round(v, 3) for k, v in runner._stage_timings.items()},
        "syscall_writes": syscalls.get_write_summary(),
        "enriched_envelope_keys": (
            list(runner._enriched_envelope.keys()) if runner._enriched_envelope else []
        ),
    }

    # 10. Print summary
    logger.info("\n" + "=" * 80)
    if success:
        logger.info(" PIPELINE SUCCEEDED")
    else:
        logger.info(" PIPELINE FAILED")
    logger.info("=" * 80)

    logger.info("\nExecution Summary:")
    logger.info(f"  • Duration: {results['duration_ms']:.3f}ms")
    logger.info(
        f"  • Stages completed: {results['stages']['completed']}/{results['stages']['total']}"
    )
    logger.info(f"  • Stages failed: {results['stages']['failed']}")
    logger.info(f"  • Execution levels: {results['execution_levels']}")
    logger.info(f"  • Max parallelism: {results['max_parallelism']}")

    if results["syscall_writes"]:
        logger.info("\nDatabase Writes (simulated):")
        for table, count in results["syscall_writes"].items():
            logger.info(f"  {table}: {count} records")

    if results["enriched_envelope_keys"]:
        logger.info(f"\nEnvelope Enrichment Keys ({len(results['enriched_envelope_keys'])}):")
        for key in sorted(results["enriched_envelope_keys"])[:20]:  # Show first 20
            logger.info(f"  {key}")
        if len(results["enriched_envelope_keys"]) > 20:
            logger.info(f"  ... and {len(results['enriched_envelope_keys']) - 20} more")

    if runner._stage_timings:
        logger.info("\nTop 5 Slowest Stages:")
        sorted_timings = sorted(runner._stage_timings.items(), key=lambda x: x[1], reverse=True)
        for stage_id, timing in sorted_timings[:5]:
            logger.info(f"  {stage_id}: {timing:.3f}ms")

    if error:
        logger.info("\nError Details:")
        logger.info(f"  {error}")

    logger.info("\n" + "=" * 80)

    return results


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Test K0 pipelines locally without Docker",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Test P02 Write pipeline with default envelope
  python k0/scripts/test_pipeline_local.py --pipeline P02_WRITE

  # Test with debug logging
  python k0/scripts/test_pipeline_local.py --pipeline P02_WRITE --debug

  # Test with custom envelope
  python k0/scripts/test_pipeline_local.py --pipeline P02_WRITE --envelope my_envelope.json

  # Save results to file
  python k0/scripts/test_pipeline_local.py --pipeline P02_WRITE --output results.json
        """,
    )

    parser.add_argument("--pipeline", required=True, help="Pipeline ID (e.g., P02_WRITE, P03_READ)")
    parser.add_argument("--envelope", type=Path, help="Path to custom envelope JSON file")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--output", type=Path, help="Save results to JSON file")

    args = parser.parse_args()

    # Load custom envelope if provided
    envelope = None
    if args.envelope:
        if not args.envelope.exists():
            print(f"Error: Envelope file not found: {args.envelope}")
            sys.exit(1)
        envelope = load_envelope_from_file(args.envelope)

    # Run test
    results = asyncio.run(
        run_pipeline_test(pipeline_id=args.pipeline, envelope=envelope, debug=args.debug)
    )

    # Save results if requested
    if args.output:
        with open(args.output, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\n✓ Results saved to: {args.output}")

    # Exit with appropriate code
    sys.exit(0 if results["success"] else 1)


if __name__ == "__main__":
    main()
    main()
