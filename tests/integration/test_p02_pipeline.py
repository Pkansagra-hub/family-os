"""
P02 Pipeline Integration Tests

Tests the full P02 Write pipeline (Episodic Memory Formation) using the
runtime PipelineRunner with YAML-based declarative specification.

Contract: k0/contracts/pipelines/p02_write.v1.yaml
Runtime: k0/runtime/pipeline_runner.py (PipelineRunner)
Related: Epic 6.1.1 (P02 End-to-End Integration)

Test Scope:
- Pipeline YAML contract validation
- PipelineRunner initialization from YAML
- DAG execution (16 modules across 8 stages)
- Parallel stage execution within levels
- Atomic storage writes (st_hipp_events + st_embedding_queue)
- Exit event emission to st_outbox
"""

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def mock_bus_message():
    """Create mock BusMessage for testing"""

    def _create_message(envelope: dict, topic: str = "cognitive.memory.write.committed.v1"):
        msg = MagicMock()
        msg.topic = topic
        msg.payload = json.dumps(envelope).encode("utf-8")
        msg.offset = envelope.get("wal_pos", 1000)
        msg.trace_id = envelope.get("cognitive_trace_id", str(uuid.uuid4()))
        msg.space_id = envelope.get("space_id", "test_space")
        msg.metadata = {}
        return msg

    return _create_message


@pytest.fixture
def minimal_envelope():
    """Create minimal valid P02 input envelope"""
    cognitive_trace_id = str(uuid.uuid4())
    timestamp = int(datetime.now(timezone.utc).timestamp())

    return {
        # Identity & Trace
        "cognitive_trace_id": cognitive_trace_id,
        "wal_pos": 1000,
        "tenant_id": "test_tenant",
        "space_id": "personal:test_user",
        "topic": "memory.episodic.formation",
        "schema_version": "1.0.0",
        # Policy
        "band": "GREEN",
        "policy_version": "2025-11-01",
        "policy_decision": "ALLOW",
        "policy_stamp": {"visible_to": ["test_user"], "obligations": []},
        # Actor & Device
        "actor": "test_user",
        "device_id": "test_device",
        # Timestamps
        "ts": timestamp,
        "ingested_at": timestamp,
        # Body
        "body": {
            "text": "Test memory event",
            "activity_type": "routine",
            "event_time": datetime.now(timezone.utc).isoformat(),
        },
    }


@pytest.fixture
def mock_pipeline_context():
    """Create mock PipelineContext"""
    ctx = MagicMock()

    # Mock syscalls with in-memory storage
    syscalls = MagicMock()
    syscalls._storage = {
        "hipp_events": {},
        "embedding_queue": {},
        "pipeline_processed": set(),
        "outbox": [],
    }

    async def _check_processed(wal_pos: int) -> bool:
        return wal_pos in syscalls._storage["pipeline_processed"]

    async def _mark_processed(wal_pos: int):
        syscalls._storage["pipeline_processed"].add(wal_pos)

    async def _insert_hipp_event(**kwargs):
        event_id = kwargs["event_id"]
        syscalls._storage["hipp_events"][event_id] = kwargs
        return {"status": "inserted", "event_id": event_id}

    async def _insert_embedding_job(**kwargs):
        embed_id = kwargs["embedding_id"]
        syscalls._storage["embedding_queue"][embed_id] = kwargs
        return {"status": "queued", "embedding_id": embed_id}

    async def _emit_events(events: list):
        syscalls._storage["outbox"].extend(events)
        return {"status": "emitted", "count": len(events)}

    syscalls.check_pipeline_processed = AsyncMock(side_effect=_check_processed)
    syscalls.mark_pipeline_processed = AsyncMock(side_effect=_mark_processed)
    syscalls.insert_hipp_event = AsyncMock(side_effect=_insert_hipp_event)
    syscalls.insert_embedding_job = AsyncMock(side_effect=_insert_embedding_job)
    syscalls.emit_events = AsyncMock(side_effect=_emit_events)

    ctx.syscalls = syscalls
    ctx.config = {}
    ctx.logger = MagicMock()
    ctx.preloaded_models = None

    return ctx


# =============================================================================
# Contract Validation Tests
# =============================================================================


@pytest.mark.asyncio
async def test_p02_contract_structure():
    """
    Test that P02 pipeline contract exists and has required fields.

    Validates:
    - Contract file exists at k0/contracts/pipelines/p02_write.v1.yaml
    - Required fields: pipeline_id, version, entry_topic, exit_topic, dag
    - DAG has 16 modules (M01-M17, excluding M03 per v1 spec)
    """
    from pathlib import Path

    import yaml

    contract_path = Path("k0/contracts/pipelines/p02_write.v1.yaml")
    assert contract_path.exists(), f"P02 contract not found: {contract_path}"

    with open(contract_path) as f:
        contract = yaml.safe_load(f)

    # Validate required top-level fields
    assert contract["pipeline_id"] == "P02_WRITE"
    assert contract["version"] == "v1"
    assert contract["entry_topic"] == "cognitive.memory.write.committed.v1"
    assert contract["exit_topic"] == "p02.write.complete.v1"
    assert "dag" in contract
    assert isinstance(contract["dag"], list)

    # Validate DAG structure (16 stages per spec: M01-M17 excluding M03)
    dag = contract["dag"]
    assert len(dag) == 16, f"Expected 16 DAG stages, got {len(dag)}"

    # Validate each stage has required fields
    for stage in dag:
        assert "id" in stage
        assert "module" in stage
        assert "after" in stage
        assert "description" in stage

    # Validate entry point (stage_10 has no dependencies)
    entry_stages = [s for s in dag if not s["after"]]
    assert len(entry_stages) == 1
    assert entry_stages[0]["id"] == "stage_10_dg_pattern_separate"


@pytest.mark.asyncio
async def test_p02_pipeline_runner_initialization():
    """
    Test that P02 pipeline can be initialized from YAML contract using PipelineRunner.

    Validates:
    - PipelineSpec loads from p02_write.v1.yaml
    - PipelineRunner implements PipelineProtocol interface
    - Pipeline properties match contract specifications
    """
    from pathlib import Path

    from k0.runtime.module_registry import ModuleRegistry
    from k0.runtime.pipeline_runner import PipelineRunner
    from k0.runtime.schemas import PipelineSpec

    # Load P02 contract
    contract_path = Path("k0/contracts/pipelines/p02_write.v1.yaml")
    assert contract_path.exists(), f"P02 contract not found: {contract_path}"

    spec = PipelineSpec.load(str(contract_path))

    # Create module registry (empty for this test)
    registry = ModuleRegistry()

    # Create pipeline runner
    runner = PipelineRunner(spec, registry)

    # Validate PipelineProtocol interface
    assert hasattr(runner, "pipeline_id")
    assert runner.pipeline_id == "P02_WRITE"

    assert hasattr(runner, "contract_version")
    assert runner.contract_version == 1

    assert hasattr(runner, "declared_topics")
    assert "cognitive.memory.write.committed.v1" in runner.declared_topics

    assert hasattr(runner, "concurrency")
    assert runner.concurrency == 1  # Sequential per contract

    assert hasattr(runner, "max_queue")
    assert runner.max_queue == 512  # Per contract

    # Validate lifecycle methods exist
    assert hasattr(runner, "on_startup")
    assert hasattr(runner, "on_shutdown")
    assert hasattr(runner, "handle")


# =============================================================================
# Message Processing Tests
# =============================================================================


# Remaining tests require full P02 module implementations and are deferred
# until all 16 modules (M01-M17 excluding M03) are completed with Phase 2 signatures.
#
# Test coverage will include:
# - End-to-end envelope processing with real modules
# - Idempotency verification
# - Enrichment flow validation
# - Parallel stage execution within DAG levels
# - Error handling and retry logic
# - Exit event emission
#
# See tests/k0/runtime/ for DAG execution unit tests
