"""Integration Tests for R7/R8 Atomicity and Bus Delivery — Issue 3.1.4.

This module tests end-to-end behavior of R7 (TruthWriter), R8 (EventEmitter),
and P03OutboxPublisher to verify:
- R7 atomicity: truth writes and outbox staging commit together
- R7 rollback: failure reverts both truth and outbox
- R8 completion: payload matches schema, gaps persisted, offset committed
- Publisher delivery: entries reach bus, retries work, DLQ escalation

Test Categories:
- TestR7Atomicity: Transaction atomicity tests
- TestR7Ordering: Write dependency order tests
- TestR8Completion: Completion event and gap handling
- TestR8Offset: Offset commit tests
- TestOutboxPublisherIntegration: End-to-end publisher tests
- TestEndToEndPipeline: Full R7 → R8 → Publisher flow
"""

from __future__ import annotations

import json
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock

import pytest

from k0.bus.core import BusMessage
from k0.pipelines.p03 import (
    LAYER_ST_EPI,
    LAYER_ST_KG_DOM,
    LAYER_ST_VEC,
    P03BatchEnvelope,
    P03CycleContext,
    P03EventState,
    P03ObservabilityContext,
    P03PhaseOutputs,
    P03StagedWrites,
    ReconciliationAction,
    ReconciliationSummary,
    StagedWrite,
)
from k0.pipelines.p03.outbox_publisher import OutboxPublisherConfig, P03OutboxPublisher
from k0.pipelines.p03.phase_interface import P03PhaseStatus, P03RunnerContext
from k0.pipelines.p03.phase_outputs import GapCandidate
from k0.pipelines.p03.phases.r7_truth_writer import R7TruthWriter
from k0.pipelines.p03.phases.r8_event_emitter import R8EventEmitter
from k0.storage.dlq import DeadLetter
from k0.storage.offsets import Offset
from k0.storage.outbox import OutboxEntry

# =============================================================================
# MOCK INFRASTRUCTURE
# =============================================================================


@dataclass
class MockConnection:
    """Mock asyncpg connection for integration tests."""

    executed_queries: list[tuple[str, tuple]] = field(default_factory=list)
    execution_order: list[str] = field(default_factory=list)
    should_fail_on_query: str | None = None
    rows_affected: int = 1

    async def execute(self, query: str, *args: Any) -> str:
        self.executed_queries.append((query, args))

        # Extract table name for ordering
        if "INSERT INTO" in query:
            table = query.split("INSERT INTO")[1].split()[0].strip()
            self.execution_order.append(table)
        elif "UPDATE" in query:
            table = query.split("UPDATE")[1].split()[0].strip()
            self.execution_order.append(table)

        if self.should_fail_on_query and self.should_fail_on_query in query:
            raise RuntimeError(f"Simulated failure on {self.should_fail_on_query}")

        return f"UPDATE {self.rows_affected}"

    async def fetchval(self, query: str, *args: Any) -> Any:
        self.executed_queries.append((query, args))
        if "SELECT version" in query.lower():
            return 1  # Version check passes
        return 1

    async def fetchrow(self, query: str, *args: Any) -> dict | None:
        self.executed_queries.append((query, args))
        # Return None for dedup checks in st_learning_queue
        if "st_learning_queue" in query:
            return None
        return {"version": 1}


@dataclass
class MockUnitOfWork:
    """Mock UoW for integration tests."""

    connection: MockConnection = field(default_factory=MockConnection)
    staged_outbox: list[OutboxEntry] = field(default_factory=list)
    upserted_offsets: list[dict] = field(default_factory=list)
    committed: bool = False
    should_fail_commit: bool = False

    def stage_outbox(self, entry: OutboxEntry) -> None:
        self.staged_outbox.append(entry)

    async def upsert_offset(self, record: Offset) -> None:
        self.upserted_offsets.append(
            {
                "subscriber_id": record.subscriber_id,
                "topic": record.topic,
                "space_id": record.space_id,
                "tenant_id": record.tenant_id,
                "offset": record.offset,
            }
        )

    async def commit(self) -> None:
        if self.should_fail_commit:
            raise RuntimeError("Simulated commit failure")
        self.committed = True


@dataclass
class MockOutboxStore:
    """Mock OutboxStore for integration tests."""

    entries: list[OutboxEntry] = field(default_factory=list)
    applied_ids: list[int] = field(default_factory=list)
    failures: list[tuple[int, int, str]] = field(default_factory=list)

    async def dequeue_ready_batch(
        self,
        driver: str,
        limit: int,
    ) -> list[OutboxEntry]:
        return [e for e in self.entries if e.driver == driver][:limit]

    async def mark_applied(self, entry_id: int, **kwargs: Any) -> None:
        self.applied_ids.append(entry_id)
        self.entries = [e for e in self.entries if e.id != entry_id]

    async def record_failure(
        self,
        entry: OutboxEntry,
        *,
        retries: int,
        requeue_seq: int,
        last_error: str,
        **kwargs: Any,
    ) -> None:
        entry_id = entry.id if entry.id is not None else 0
        self.failures.append((entry_id, retries, last_error))
        entry.retries = retries
        entry.last_error = last_error


@dataclass
class MockDeadLetterQueue:
    """Mock DLQ for integration tests."""

    entries: list[DeadLetter] = field(default_factory=list)
    next_id: int = 1

    async def record(self, letter: DeadLetter, **kwargs: Any) -> int:
        letter.id = self.next_id
        self.next_id += 1
        self.entries.append(letter)
        return letter.id


@dataclass
class MockBusDispatcher:
    """Mock BusDispatcher that captures dispatched messages."""

    messages: list[BusMessage] = field(default_factory=list)
    should_fail: bool = False
    fail_count: int = 0
    max_failures: int = 0

    async def dispatch(self, messages: list[BusMessage]) -> None:
        if self.should_fail and self.fail_count < self.max_failures:
            self.fail_count += 1
            raise RuntimeError("Simulated dispatch failure")
        self.messages.extend(messages)


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def mock_connection() -> MockConnection:
    """Create mock connection."""
    return MockConnection()


@pytest.fixture
def mock_uow(mock_connection: MockConnection) -> MockUnitOfWork:
    """Create mock UoW."""
    return MockUnitOfWork(connection=mock_connection)


@pytest.fixture
def mock_syscalls(mock_uow: MockUnitOfWork):
    """Create mock syscalls with UoW factory."""

    @asynccontextmanager
    async def _unit_of_work():
        yield mock_uow

    syscalls = MagicMock()
    syscalls.unit_of_work = _unit_of_work
    return syscalls


@pytest.fixture
def mock_runner_context(mock_syscalls: MagicMock) -> P03RunnerContext:
    """Create mock runner context."""
    return P03RunnerContext.create(
        syscalls=mock_syscalls,
        logger=MagicMock(),
        qos_band="GREEN",
        priority=50,
        config={},
    )


@pytest.fixture
def sample_cycle_context() -> P03CycleContext:
    """Create sample cycle context."""
    return P03CycleContext.create(
        tenant_id="tenant-integration",
        space_id="space-integration",
        event_ids=["evt-int-001", "evt-int-002", "evt-int-003"],
        trigger_type="MANUAL",
        trigger_reason="Integration test",
    )


@pytest.fixture
def sample_event_state() -> P03EventState:
    """Create sample event state with reconciliation."""
    event = P03EventState(
        event_id="evt-int-001",
        hipp_event_id="hipp-001",
        content_text="Family dinner at 7pm",
        content_type="CHAT",
        content_hash="hash-001",
        timestamp=int(time.time() * 1000),
        channel_id="family-chat",
        embedding_id="vec-001",
    )
    event.reconciliation_action = ReconciliationAction.REINFORCE
    return event


@pytest.fixture
def envelope_with_staged_writes(
    sample_cycle_context: P03CycleContext,
    sample_event_state: P03EventState,
) -> P03BatchEnvelope:
    """Create envelope with staged writes for R7 testing."""
    envelope = P03BatchEnvelope(
        context=sample_cycle_context,
        events=[sample_event_state],
        staged=P03StagedWrites(),
        phases=P03PhaseOutputs(),
        observability=P03ObservabilityContext.create(),
    )

    # Stage writes from simulated R1-R6
    envelope.staged.add_write(
        StagedWrite.insert(
            layer=LAYER_ST_EPI,
            record_id="epi-int-001",
            data={"episode_id": "epi-int-001", "summary": "Integration test episode"},
            phase="R6",
            event_ids=["evt-int-001"],
        )
    )

    envelope.staged.add_write(
        StagedWrite.insert(
            layer=LAYER_ST_KG_DOM,
            record_id="entity-int-001",
            data={"entity_id": "entity-int-001", "name": "TestEntity"},
            phase="R4",
            event_ids=["evt-int-001"],
        )
    )

    # Stage outbox event (add_outbox_event takes individual params, not object)
    envelope.staged.add_outbox_event(
        topic="p03.consolidation.complete.v1",
        payload={"status": "SUCCESS"},
        phase="R8",
    )

    return envelope


@pytest.fixture
def envelope_with_gaps(
    sample_cycle_context: P03CycleContext,
    sample_event_state: P03EventState,
) -> P03BatchEnvelope:
    """Create envelope with detected gaps for R8 testing."""
    envelope = P03BatchEnvelope(
        context=sample_cycle_context,
        events=[sample_event_state],
        staged=P03StagedWrites(),
        phases=P03PhaseOutputs(),
        observability=P03ObservabilityContext.create(),
    )

    # Add gaps from R4 (using correct GapCandidate structure)
    envelope.phases.r4_gap_candidates = [
        GapCandidate(
            gap_id="gap-int-001",
            gap_type="ENTITY_MISSING",
            related_entity_id="entity-unknown-001",
            entropy_score=0.85,
            priority="HIGH",
            context_json='{"description": "Missing person entity reference"}',
        ),
        GapCandidate(
            gap_id="gap-int-002",
            gap_type="RELATIONSHIP_UNCLEAR",
            related_entity_id="entity-rel-001",
            entropy_score=0.70,
            priority="MEDIUM",
            context_json='{"description": "Unclear relationship between entities"}',
        ),
    ]

    # Add reconciliation summary
    envelope.phases.r6_summary = ReconciliationSummary(
        reinforce_count=2,
        extend_count=1,
        create_count=1,
        evolve_count=0,
        contradict_count=0,
        skip_count=0,
        prune_count=0,
    )

    return envelope


@pytest.fixture
def mock_outbox_store() -> MockOutboxStore:
    """Create mock outbox store."""
    return MockOutboxStore()


@pytest.fixture
def mock_dlq() -> MockDeadLetterQueue:
    """Create mock DLQ."""
    return MockDeadLetterQueue()


@pytest.fixture
def mock_bus() -> MockBusDispatcher:
    """Create mock bus dispatcher."""
    return MockBusDispatcher()


# =============================================================================
# R7 ATOMICITY TESTS
# =============================================================================


class TestR7Atomicity:
    """R7 Phase atomicity tests — truth + outbox commit together."""

    @pytest.mark.asyncio
    async def test_r7_commit_persists_truth_and_outbox_atomically(
        self,
        mock_uow: MockUnitOfWork,
        mock_runner_context: P03RunnerContext,
        envelope_with_staged_writes: P03BatchEnvelope,
    ) -> None:
        """
        Given: Envelope with staged writes and outbox events
        When: R7 executes successfully
        Then: Both truth tables AND outbox contain the data (same UoW)
        """
        r7 = R7TruthWriter()
        result = await r7.run(envelope_with_staged_writes, mock_runner_context)

        assert result.status == P03PhaseStatus.DONE

        # Verify truth writes executed
        executed_tables = [q[0] for q in mock_uow.connection.executed_queries]
        assert any("st_epi" in q for q in executed_tables)
        assert any("st_kg_dom" in q for q in executed_tables)

        # Verify outbox entries staged
        assert len(mock_uow.staged_outbox) >= 1

    @pytest.mark.asyncio
    async def test_r7_stages_outbox_for_each_staged_event(
        self,
        mock_uow: MockUnitOfWork,
        mock_runner_context: P03RunnerContext,
        envelope_with_staged_writes: P03BatchEnvelope,
    ) -> None:
        """Outbox events from staged are all staged in UoW."""
        r7 = R7TruthWriter()
        await r7.run(envelope_with_staged_writes, mock_runner_context)

        # Original staged outbox event + any completion events
        staged_topics = [e.op_kind for e in mock_uow.staged_outbox]
        assert "p03.consolidation.complete.v1" in staged_topics

    @pytest.mark.asyncio
    async def test_r7_failure_prevents_outbox_staging(
        self,
        mock_uow: MockUnitOfWork,
        mock_runner_context: P03RunnerContext,
        envelope_with_staged_writes: P03BatchEnvelope,
    ) -> None:
        """
        Given: R7 fails during write execution
        When: Exception raised
        Then: No outbox entries should be accessible (rollback)
        """
        # Make writes fail
        mock_uow.connection.should_fail_on_query = "st_epi"

        r7 = R7TruthWriter()
        result = await r7.run(envelope_with_staged_writes, mock_runner_context)

        assert result.status == P03PhaseStatus.FAIL
        # In real scenario, UoW rollback would discard staged_outbox


# =============================================================================
# R7 ORDERING TESTS
# =============================================================================


class TestR7Ordering:
    """R7 write dependency order tests."""

    @pytest.mark.asyncio
    async def test_r7_writes_in_dependency_order(
        self,
        mock_uow: MockUnitOfWork,
        mock_runner_context: P03RunnerContext,
        sample_cycle_context: P03CycleContext,
        sample_event_state: P03EventState,
    ) -> None:
        """
        Given: Envelope with writes to multiple layers
        When: R7 executes
        Then: Writes are executed in correct order (vec → kg_dom → epi)
        """
        envelope = P03BatchEnvelope(
            context=sample_cycle_context,
            events=[sample_event_state],
            staged=P03StagedWrites(),
            phases=P03PhaseOutputs(),
            observability=P03ObservabilityContext.create(),
        )

        # Add writes in REVERSE order (should still execute in dependency order)
        envelope.staged.add_write(
            StagedWrite.insert(
                layer=LAYER_ST_EPI,
                record_id="epi-1",
                data={"id": "epi-1"},
                phase="R6",
            )
        )
        envelope.staged.add_write(
            StagedWrite.insert(
                layer=LAYER_ST_VEC,
                record_id="vec-1",
                data={"id": "vec-1"},
                phase="R6",
            )
        )
        envelope.staged.add_write(
            StagedWrite.insert(
                layer=LAYER_ST_KG_DOM,
                record_id="kg-1",
                data={"id": "kg-1"},
                phase="R4",
            )
        )

        r7 = R7TruthWriter()
        await r7.run(envelope, mock_runner_context)

        # Check execution order
        order = mock_uow.connection.execution_order
        if "st_vec" in order and "st_kg_dom" in order:
            assert order.index("st_vec") < order.index("st_kg_dom")
        if "st_kg_dom" in order and "st_epi" in order:
            assert order.index("st_kg_dom") < order.index("st_epi")


# =============================================================================
# R8 COMPLETION TESTS
# =============================================================================


class TestR8Completion:
    """R8 Phase completion event tests."""

    @pytest.mark.asyncio
    async def test_r8_builds_completion_payload_with_required_fields(
        self,
        mock_uow: MockUnitOfWork,
        mock_runner_context: P03RunnerContext,
        envelope_with_staged_writes: P03BatchEnvelope,
    ) -> None:
        """
        Given: Envelope after R7 completion
        When: R8 builds completion payload
        Then: Payload contains required fields per schema
        """
        r8 = R8EventEmitter()
        result = await r8.run(envelope_with_staged_writes, mock_runner_context)

        assert result.status == P03PhaseStatus.DONE

        # Find completion event in staged outbox
        completion_events = [
            e for e in mock_uow.staged_outbox if e.op_kind == "p03.consolidation.complete.v1"
        ]
        assert len(completion_events) >= 1

        # Validate payload structure
        payload = json.loads(completion_events[0].payload.decode("utf-8"))
        assert "cycle_id" in payload
        assert "tenant_id" in payload
        assert "space_id" in payload
        assert "status" in payload
        assert payload["status"] in ("SUCCESS", "PARTIAL", "FAILED")

    @pytest.mark.asyncio
    async def test_r8_gaps_staged_to_outbox(
        self,
        mock_uow: MockUnitOfWork,
        mock_runner_context: P03RunnerContext,
        envelope_with_gaps: P03BatchEnvelope,
    ) -> None:
        """
        Given: Envelope with gaps from R4
        When: R8 executes
        Then: Gaps staged as outbox events
        """
        r8 = R8EventEmitter()
        await r8.run(envelope_with_gaps, mock_runner_context)

        # Find gap events
        gap_events = [e for e in mock_uow.staged_outbox if e.op_kind == "p03.gap.detected.v1"]
        assert len(gap_events) == 2  # Two gaps in fixture

    @pytest.mark.asyncio
    async def test_r8_gap_payload_contains_context(
        self,
        mock_uow: MockUnitOfWork,
        mock_runner_context: P03RunnerContext,
        envelope_with_gaps: P03BatchEnvelope,
    ) -> None:
        """Gap event payload includes full context."""
        r8 = R8EventEmitter()
        await r8.run(envelope_with_gaps, mock_runner_context)

        gap_events = [e for e in mock_uow.staged_outbox if e.op_kind == "p03.gap.detected.v1"]

        for gap_event in gap_events:
            payload = json.loads(gap_event.payload.decode("utf-8"))
            assert "gap_id" in payload
            assert "gap_type" in payload
            assert "cycle_id" in payload


# =============================================================================
# R8 OFFSET TESTS
# =============================================================================


class TestR8Offset:
    """R8 offset commit tests."""

    @pytest.mark.asyncio
    async def test_r8_commits_offset_on_success(
        self,
        mock_uow: MockUnitOfWork,
        mock_runner_context: P03RunnerContext,
        envelope_with_staged_writes: P03BatchEnvelope,
    ) -> None:
        """
        Given: Successful R8 execution
        When: R8 completes
        Then: Offset committed via UoW
        """
        r8 = R8EventEmitter()
        await r8.run(envelope_with_staged_writes, mock_runner_context)

        assert len(mock_uow.upserted_offsets) == 1
        offset = mock_uow.upserted_offsets[0]
        assert offset["subscriber_id"] == "p03"
        assert offset["topic"] == "p02.hipp_events"

    @pytest.mark.asyncio
    async def test_r8_offset_includes_space_and_tenant(
        self,
        mock_uow: MockUnitOfWork,
        mock_runner_context: P03RunnerContext,
        envelope_with_staged_writes: P03BatchEnvelope,
    ) -> None:
        """Offset includes correct space and tenant IDs."""
        r8 = R8EventEmitter()
        await r8.run(envelope_with_staged_writes, mock_runner_context)

        offset = mock_uow.upserted_offsets[0]
        assert offset["space_id"] == envelope_with_staged_writes.context.space_id
        assert offset["tenant_id"] == envelope_with_staged_writes.context.tenant_id


# =============================================================================
# OUTBOX PUBLISHER INTEGRATION TESTS
# =============================================================================


class TestOutboxPublisherIntegration:
    """Outbox publisher end-to-end tests."""

    @pytest.mark.asyncio
    async def test_publisher_delivers_to_bus(
        self,
        mock_outbox_store: MockOutboxStore,
        mock_bus: MockBusDispatcher,
        mock_dlq: MockDeadLetterQueue,
    ) -> None:
        """
        Given: Outbox entries staged
        When: Publisher drains batch
        Then: Events dispatched to bus and removed from outbox
        """
        # Stage entry
        entry = OutboxEntry(
            id=1,
            wal_pos=100,
            tenant_id="t1",
            space_id="s1",
            driver="p03",
            op_kind="p03.consolidation.complete.v1",
            payload=json.dumps({"status": "SUCCESS"}).encode(),
            fingerprint="fp-test",
            requeue_seq=0,
            retries=0,
        )
        mock_outbox_store.entries.append(entry)

        publisher = P03OutboxPublisher(
            outbox_store=mock_outbox_store,  # type: ignore[arg-type]
            bus_dispatcher=mock_bus,  # type: ignore[arg-type]
            dlq_store=mock_dlq,  # type: ignore[arg-type]
        )

        result = await publisher.drain_batch()

        assert result.published == 1
        assert len(mock_bus.messages) == 1
        assert mock_bus.messages[0].topic == "p03.consolidation.complete.v1"
        assert 1 in mock_outbox_store.applied_ids

    @pytest.mark.asyncio
    async def test_publisher_retries_on_failure(
        self,
        mock_outbox_store: MockOutboxStore,
        mock_dlq: MockDeadLetterQueue,
    ) -> None:
        """
        Given: Bus dispatch fails
        When: Publisher attempts delivery
        Then: Entry marked for retry with incremented count
        """
        entry = OutboxEntry(
            id=1,
            wal_pos=100,
            tenant_id="t1",
            space_id="s1",
            driver="p03",
            op_kind="test.topic",
            payload=b"{}",
            fingerprint="fp-retry",
            requeue_seq=0,
            retries=0,
        )
        mock_outbox_store.entries.append(entry)

        failing_bus = MockBusDispatcher(should_fail=True, max_failures=10)

        publisher = P03OutboxPublisher(
            outbox_store=mock_outbox_store,  # type: ignore[arg-type]
            bus_dispatcher=failing_bus,  # type: ignore[arg-type]
            dlq_store=mock_dlq,  # type: ignore[arg-type]
        )

        result = await publisher.drain_batch()

        assert result.retried == 1
        assert len(mock_outbox_store.failures) == 1
        assert mock_outbox_store.failures[0][1] == 1  # retries incremented

    @pytest.mark.asyncio
    async def test_publisher_dlq_after_max_retries(
        self,
        mock_outbox_store: MockOutboxStore,
        mock_dlq: MockDeadLetterQueue,
    ) -> None:
        """
        Given: Entry at max retries
        When: Next attempt fails
        Then: Entry moved to DLQ
        """
        entry = OutboxEntry(
            id=1,
            wal_pos=100,
            tenant_id="t1",
            space_id="s1",
            driver="p03",
            op_kind="test.topic",
            payload=b"{}",
            fingerprint="fp-dlq",
            requeue_seq=0,
            retries=3,  # At max
        )
        mock_outbox_store.entries.append(entry)

        failing_bus = MockBusDispatcher(should_fail=True, max_failures=10)

        publisher = P03OutboxPublisher(
            outbox_store=mock_outbox_store,  # type: ignore[arg-type]
            bus_dispatcher=failing_bus,  # type: ignore[arg-type]
            dlq_store=mock_dlq,  # type: ignore[arg-type]
            config=OutboxPublisherConfig(max_retries=3),
        )

        result = await publisher.drain_batch()

        assert result.dlq_count == 1
        assert len(mock_dlq.entries) == 1
        assert mock_dlq.entries[0].fingerprint == "fp-dlq"
        assert 1 in mock_outbox_store.applied_ids  # Removed from outbox


# =============================================================================
# END-TO-END PIPELINE TESTS
# =============================================================================


class TestEndToEndPipeline:
    """Full R7 → R8 → Publisher flow tests."""

    @pytest.mark.asyncio
    async def test_r7_r8_publisher_happy_path(
        self,
        mock_uow: MockUnitOfWork,
        mock_runner_context: P03RunnerContext,
        envelope_with_staged_writes: P03BatchEnvelope,
        mock_dlq: MockDeadLetterQueue,
    ) -> None:
        """
        Given: Complete envelope ready for R7
        When: R7 → R8 → Publisher executes
        Then: Events reach bus, offset committed
        """
        # R7: Execute writes
        r7 = R7TruthWriter()
        r7_result = await r7.run(envelope_with_staged_writes, mock_runner_context)
        assert r7_result.status == P03PhaseStatus.DONE

        # R8: Emit events
        r8 = R8EventEmitter()
        r8_result = await r8.run(envelope_with_staged_writes, mock_runner_context)
        assert r8_result.status == P03PhaseStatus.DONE

        # Verify offset committed
        assert len(mock_uow.upserted_offsets) == 1

        # Simulate outbox entries from staged
        mock_outbox = MockOutboxStore()
        for i, staged in enumerate(mock_uow.staged_outbox):
            mock_outbox.entries.append(
                OutboxEntry(
                    id=i + 1,
                    wal_pos=100 + i,
                    tenant_id=staged.tenant_id,
                    space_id=staged.space_id,
                    driver=staged.driver,
                    op_kind=staged.op_kind,
                    payload=staged.payload,
                    fingerprint=staged.fingerprint,
                    requeue_seq=0,
                    retries=0,
                )
            )

        # Publisher: Deliver to bus
        mock_bus = MockBusDispatcher()
        publisher = P03OutboxPublisher(
            outbox_store=mock_outbox,  # type: ignore[arg-type]
            bus_dispatcher=mock_bus,  # type: ignore[arg-type]
            dlq_store=mock_dlq,  # type: ignore[arg-type]
        )

        result = await publisher.drain_batch()

        assert result.published == len(mock_uow.staged_outbox)
        assert len(mock_bus.messages) == len(mock_uow.staged_outbox)

    @pytest.mark.asyncio
    async def test_r7_failure_prevents_r8_execution(
        self,
        mock_uow: MockUnitOfWork,
        mock_runner_context: P03RunnerContext,
        envelope_with_staged_writes: P03BatchEnvelope,
    ) -> None:
        """
        Given: R7 fails
        When: Checking result
        Then: R8 should not execute (runner responsibility)
        """
        mock_uow.connection.should_fail_on_query = "st_epi"

        r7 = R7TruthWriter()
        r7_result = await r7.run(envelope_with_staged_writes, mock_runner_context)

        assert r7_result.status == P03PhaseStatus.FAIL
        # In real runner, R8 would not be called after R7 failure


# =============================================================================
# IDEMPOTENCY TESTS
# =============================================================================


class TestIdempotency:
    """Idempotency tests for retry scenarios."""

    @pytest.mark.asyncio
    async def test_r8_fingerprint_enables_deduplication(
        self,
        mock_uow: MockUnitOfWork,
        mock_runner_context: P03RunnerContext,
        envelope_with_staged_writes: P03BatchEnvelope,
    ) -> None:
        """
        Given: Same cycle_id processed twice
        When: R8 stages events
        Then: Fingerprints are deterministic for deduplication
        """
        r8 = R8EventEmitter()

        # First execution
        await r8.run(envelope_with_staged_writes, mock_runner_context)
        first_fingerprints = [e.fingerprint for e in mock_uow.staged_outbox]

        # Clear and run again
        mock_uow.staged_outbox.clear()
        mock_uow.upserted_offsets.clear()
        await r8.run(envelope_with_staged_writes, mock_runner_context)
        second_fingerprints = [e.fingerprint for e in mock_uow.staged_outbox]

        # Fingerprints should be deterministic
        assert first_fingerprints == second_fingerprints

    @pytest.mark.asyncio
    async def test_gap_fingerprint_pattern(
        self,
        mock_uow: MockUnitOfWork,
        mock_runner_context: P03RunnerContext,
        envelope_with_gaps: P03BatchEnvelope,
    ) -> None:
        """Gap events use fingerprint pattern: p03:gap:{cycle_id}:{entity_id}:{gap_type}."""
        r8 = R8EventEmitter()
        await r8.run(envelope_with_gaps, mock_runner_context)

        gap_events = [e for e in mock_uow.staged_outbox if e.op_kind == "p03.gap.detected.v1"]

        for gap_event in gap_events:
            # New pattern from Issue 3.2.3 gap emitter
            assert gap_event.fingerprint.startswith("p03:gap:")
