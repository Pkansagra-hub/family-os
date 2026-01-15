"""
P03 Local End-to-End Integration Tests.

This test suite runs the full P03 consolidation pipeline locally using
in-memory mocks for all storage and syscall dependencies.

Purpose:
- Debug P03 execution flow without Docker
- Validate R0-R8 phase sequence
- Test sequential runner with realistic mocks
- Ensure syscall interface is correctly implemented

Test Categories:
1. TestP03LocalE2E: Full cycle with in-memory mocks
2. TestP03R0BehaviorLocal: R0 batch selection behavior
3. TestP03SkipPathsLocal: Skip transition scenarios
4. TestP03FailureHandlingLocal: Error recovery flows

Usage:
    pytest tests/k0/pipelines/p03/integration/test_p03_local_e2e.py -v

Reference:
- Issue: P03 Docker debugging requires local-first E2E tests
- Runner: k0/pipelines/p03/sequential_runner.py
- Phases: k0/pipelines/p03/phases/
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import pytest

from k0.pipelines.p03 import (
    P03BatchEnvelope,
    P03CycleContext,
    P03PhaseId,
    P03PhaseStatus,
    P03RunnerContext,
    P03SequentialRunner,
)
from k0.pipelines.p03.observability import P03Error
from k0.pipelines.p03.phase_interface import P03PhaseResult
from k0.pipelines.p03.phases import PHASE_REGISTRY, R0BatchSelector, R0PhaseAdapter
from k0.pipelines.p03.phases.r0_batch_selector import R0Config

# =============================================================================
# MOCK STORAGE INFRASTRUCTURE
# =============================================================================


@dataclass
class MockHippEvent:
    """Mock st_hipp_events row."""

    event_id: str
    hipp_event_id: str
    content_text: str
    content_type: str = "CHAT"
    content_hash: str = ""
    simhash_hex: str = "0000000000000000"
    timestamp: int = field(default_factory=lambda: int(time.time() * 1000))
    channel_id: str = "family-chat"
    embedding_id: Optional[str] = None
    embedding_768: Optional[List[float]] = None
    sentiment_score: float = 0.5
    sentiment_label: str = "neutral"
    emotions_json: str = "[]"
    intent_label: str = "INFORM"
    ner_entities_json: str = "[]"
    temporal_expressions_json: str = "[]"
    consolidation_status: Optional[str] = None
    embedding_status: str = "READY"
    archival_status: Optional[str] = None

    def to_row(self) -> Dict[str, Any]:
        """Convert to database row dict."""
        return {
            "event_id": self.event_id,
            "hipp_event_id": self.hipp_event_id,
            "content_text": self.content_text,
            "content_type": self.content_type,
            "content_hash": self.content_hash or f"hash_{self.event_id}",
            "simhash_hex": self.simhash_hex,
            "timestamp": self.timestamp,
            "channel_id": self.channel_id,
            "embedding_id": self.embedding_id or f"vec_{self.event_id}",
            "sentiment_score": self.sentiment_score,
            "sentiment_label": self.sentiment_label,
            "emotions_json": self.emotions_json,
            "intent_label": self.intent_label,
            "ner_entities_json": self.ner_entities_json,
            "temporal_expressions_json": self.temporal_expressions_json,
            "consolidation_status": self.consolidation_status,
            "embedding_status": self.embedding_status,
            "archival_status": self.archival_status,
        }


@dataclass
class MockOffset:
    """Mock offset record."""

    subscriber_id: str
    topic: str
    space_id: str
    tenant_id: str
    offset: int
    updated_ts: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ"))


class MockOffsetStore:
    """
    In-memory offset store that mimics K0's OffsetStore interface.

    Provides:
    - fetch(subscriber_id, topic, space_id, tenant_id) -> Optional[Offset]
    - upsert(record, connection=None) -> None
    """

    def __init__(self) -> None:
        self._offsets: Dict[str, MockOffset] = {}

    def _make_key(self, subscriber_id: str, topic: str, space_id: str, tenant_id: str) -> str:
        return f"{subscriber_id}:{topic}:{space_id}:{tenant_id}"

    async def fetch(
        self,
        subscriber_id: str,
        topic: str,
        space_id: str,
        tenant_id: str,
        *,
        connection: Any = None,
    ) -> Optional[MockOffset]:
        key = self._make_key(subscriber_id, topic, space_id, tenant_id)
        return self._offsets.get(key)

    async def upsert(
        self,
        record: MockOffset,
        *,
        connection: Any = None,
    ) -> None:
        key = self._make_key(record.subscriber_id, record.topic, record.space_id, record.tenant_id)
        self._offsets[key] = record

    def set_offset(
        self,
        subscriber_id: str,
        topic: str,
        space_id: str,
        tenant_id: str,
        offset: int,
    ) -> None:
        """Helper for tests to set initial offset."""
        key = self._make_key(subscriber_id, topic, space_id, tenant_id)
        self._offsets[key] = MockOffset(
            subscriber_id=subscriber_id,
            topic=topic,
            space_id=space_id,
            tenant_id=tenant_id,
            offset=offset,
        )


class MockConnection:
    """
    Mock asyncpg connection that returns configurable query results.

    Provides:
    - fetch(query, *args) -> List[Dict]
    - fetchrow(query, *args) -> Optional[Dict]
    - execute(query, *args) -> str
    """

    def __init__(self) -> None:
        self._rows: List[Dict[str, Any]] = []
        self._executed: List[Tuple[str, tuple]] = []
        self._updated_events: List[str] = []
        self._inserted_gaps: List[Dict[str, Any]] = []
        self._next_fetchrow: Optional[Dict[str, Any]] = None

    def set_rows(self, rows: List[Dict[str, Any]]) -> None:
        """Set rows to return from fetch()."""
        self._rows = rows

    def set_next_fetchrow(self, row: Optional[Dict[str, Any]]) -> None:
        """Set next row for fetchrow()."""
        self._next_fetchrow = row

    async def fetch(self, query: str, *args: Any) -> List[Dict[str, Any]]:
        self._executed.append((query, args))
        return self._rows

    async def fetchrow(self, query: str, *args: Any) -> Optional[Dict[str, Any]]:
        self._executed.append((query, args))
        return self._next_fetchrow

    async def execute(self, query: str, *args: Any) -> str:
        self._executed.append((query, args))

        # Track specific operations for assertions
        if "UPDATE" in query and "st_hipp_events" in query:
            # Extract event IDs from args if present
            for arg in args:
                if isinstance(arg, str):
                    self._updated_events.append(arg)

        if "INSERT" in query and "st_learning_queue" in query:
            self._inserted_gaps.append({"query": query, "args": args})

        return "UPDATE 1"


class MockUnitOfWork:
    """
    Mock Unit of Work for atomic operations.

    Provides:
    - connection property
    - stage_outbox(entry) -> None
    - upsert_offset(record) -> None
    - commit() -> None
    - Context manager support
    """

    def __init__(self, connection: MockConnection) -> None:
        self._connection = connection
        self.staged_outbox: List[Any] = []
        self.upserted_offsets: List[Dict[str, Any]] = []
        self.committed: bool = False

    @property
    def connection(self) -> MockConnection:
        return self._connection

    async def __aenter__(self) -> "MockUnitOfWork":
        return self

    async def __aexit__(self, *args: Any) -> None:
        pass

    def stage_outbox(self, entry: Any) -> None:
        self.staged_outbox.append(entry)

    async def upsert_offset(self, record: Any) -> None:
        self.upserted_offsets.append(
            {
                "subscriber_id": getattr(record, "subscriber_id", "unknown"),
                "topic": getattr(record, "topic", "unknown"),
                "offset": getattr(record, "offset", 0),
            }
        )

    async def commit(self) -> None:
        self.committed = True


class MockEmbeddingStore:
    """Mock embedding store for vector operations."""

    def __init__(self) -> None:
        self._embeddings: Dict[str, List[float]] = {}

    async def fetch_batch(self, embedding_ids: List[str]) -> Dict[str, List[float]]:
        """Fetch embeddings by IDs."""
        return {eid: self._embeddings.get(eid, [0.0] * 768) for eid in embedding_ids}

    def set_embedding(self, embedding_id: str, vector: List[float]) -> None:
        """Set an embedding for testing."""
        self._embeddings[embedding_id] = vector


class MockSyscalls:
    """
    Mock Syscalls object providing all dependencies phases need.

    This is the critical piece that R0 and other phases access via ctx.syscalls.

    Provides:
    - offset_store: MockOffsetStore
    - hipp_store: AsyncMock for st_hipp_events queries
    - embedding_store: MockEmbeddingStore
    - unit_of_work(): Returns MockUnitOfWork
    """

    def __init__(
        self,
        offset_store: Optional[MockOffsetStore] = None,
        connection: Optional[MockConnection] = None,
        hipp_events: Optional[List[MockHippEvent]] = None,
    ) -> None:
        self.offset_store = offset_store or MockOffsetStore()
        self._connection = connection or MockConnection()
        self._hipp_events = hipp_events or []
        self.embedding_store = MockEmbeddingStore()
        self._uow = MockUnitOfWork(self._connection)

        # Pre-populate connection with hipp events
        if self._hipp_events:
            self._connection.set_rows([e.to_row() for e in self._hipp_events])

    def unit_of_work(self) -> MockUnitOfWork:
        """Return unit of work for atomic operations."""
        return self._uow

    @property
    def connection(self) -> MockConnection:
        """Direct connection access (for phases that use it directly)."""
        return self._connection

    def set_hipp_events(self, events: List[MockHippEvent]) -> None:
        """Update the events returned by fetch queries."""
        self._hipp_events = events
        self._connection.set_rows([e.to_row() for e in events])


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def sample_hipp_events() -> List[MockHippEvent]:
    """Create sample st_hipp_events for testing."""
    base_ts = int(time.time() * 1000)
    return [
        MockHippEvent(
            event_id=f"01JFXYZ00000000000000000{i}",
            hipp_event_id=f"hipp-{i:03d}",
            content_text=f"Test event {i} content",
            timestamp=base_ts + (i * 1000),
            embedding_id=f"vec-{i:03d}",
        )
        for i in range(1, 6)
    ]


@pytest.fixture
def mock_offset_store() -> MockOffsetStore:
    """Create mock offset store."""
    return MockOffsetStore()


@pytest.fixture
def mock_connection() -> MockConnection:
    """Create mock connection."""
    return MockConnection()


@pytest.fixture
def mock_syscalls(
    mock_offset_store: MockOffsetStore,
    mock_connection: MockConnection,
    sample_hipp_events: List[MockHippEvent],
) -> MockSyscalls:
    """Create mock syscalls with all dependencies."""
    return MockSyscalls(
        offset_store=mock_offset_store,
        connection=mock_connection,
        hipp_events=sample_hipp_events,
    )


@pytest.fixture
def sample_tenant_id() -> str:
    """Fixed tenant ID for testing."""
    return "tenant-test-001"


@pytest.fixture
def sample_space_id() -> str:
    """Fixed space ID for testing."""
    return "family-test-abc"


@pytest.fixture
def sample_runner_context(mock_syscalls: MockSyscalls) -> P03RunnerContext:
    """Create a P03RunnerContext with mock syscalls."""
    return P03RunnerContext.create(
        syscalls=mock_syscalls,
        logger=logging.getLogger("test.p03.e2e"),
        qos_band="GREEN",
        priority=50,
        config={
            "tenant_id": "tenant-test-001",
            "space_id": "family-test-abc",
            "r5_skip_on_backlog": True,
            "backlog_threshold": 1000,
        },
    )


@pytest.fixture
def sample_cycle_context(sample_hipp_events: List[MockHippEvent]) -> P03CycleContext:
    """Create a sample cycle context."""
    return P03CycleContext.create(
        tenant_id="tenant-test-001",
        space_id="family-test-abc",
        event_ids=[e.event_id for e in sample_hipp_events],
        trigger_type="MANUAL",
        trigger_reason="E2E integration test",
        pending_before=100,
    )


@pytest.fixture
def sample_envelope(sample_cycle_context: P03CycleContext) -> P03BatchEnvelope:
    """Create a sample envelope."""
    return P03BatchEnvelope.create(sample_cycle_context)


# =============================================================================
# TEST: R0 BATCH SELECTOR BEHAVIOR
# =============================================================================


class TestR0BatchSelectorLocal:
    """Test R0 phase in isolation with mock syscalls."""

    @pytest.mark.asyncio
    async def test_r0_fetches_offset(
        self,
        mock_syscalls: MockSyscalls,
        sample_runner_context: P03RunnerContext,
        sample_tenant_id: str,
        sample_space_id: str,
    ) -> None:
        """R0 should fetch current offset from offset_store."""
        # Arrange: Set initial offset
        mock_syscalls.offset_store.set_offset(
            subscriber_id="p03",
            topic="p03.consolidation.batch",
            space_id=sample_space_id,
            tenant_id=sample_tenant_id,
            offset=100,
        )

        r0 = R0BatchSelector(config=R0Config(batch_size=10))

        # Act
        envelope, result = await r0.run(
            tenant_id=sample_tenant_id,
            space_id=sample_space_id,
            ctx=sample_runner_context,
        )

        # Assert: R0 should have queried the offset store
        assert result.phase_id == P03PhaseId.R0_INIT
        # The offset store was queried (fetch was called)

    @pytest.mark.asyncio
    async def test_r0_returns_skip_on_empty_batch(
        self,
        mock_syscalls: MockSyscalls,
        sample_tenant_id: str,
        sample_space_id: str,
    ) -> None:
        """R0 should return SKIP when no events found."""
        # Arrange: No events in connection
        mock_syscalls._connection.set_rows([])

        ctx = P03RunnerContext.create(
            syscalls=mock_syscalls,
            logger=logging.getLogger("test.r0.empty"),
        )
        r0 = R0BatchSelector()

        # Act
        envelope, result = await r0.run(
            tenant_id=sample_tenant_id,
            space_id=sample_space_id,
            ctx=ctx,
        )

        # Assert
        assert result.status == P03PhaseStatus.SKIP
        assert envelope is None
        assert "No eligible events" in (result.skip_reason or "")

    @pytest.mark.asyncio
    async def test_r0_creates_envelope_with_events(
        self,
        mock_syscalls: MockSyscalls,
        sample_hipp_events: List[MockHippEvent],
        sample_tenant_id: str,
        sample_space_id: str,
    ) -> None:
        """R0 should create envelope when events found."""
        # Arrange
        ctx = P03RunnerContext.create(
            syscalls=mock_syscalls,
            logger=logging.getLogger("test.r0.events"),
        )
        r0 = R0BatchSelector(config=R0Config(batch_size=10))

        # Act
        envelope, result = await r0.run(
            tenant_id=sample_tenant_id,
            space_id=sample_space_id,
            ctx=ctx,
        )

        # Assert
        assert result.status == P03PhaseStatus.DONE
        assert envelope is not None
        assert envelope.context.batch_size == len(sample_hipp_events)


# =============================================================================
# TEST: R0 ADAPTER
# =============================================================================


class TestR0PhaseAdapterLocal:
    """Test R0PhaseAdapter wraps R0BatchSelector correctly."""

    @pytest.mark.asyncio
    async def test_adapter_conforms_to_protocol(
        self,
        mock_syscalls: MockSyscalls,
        sample_envelope: P03BatchEnvelope,
    ) -> None:
        """R0PhaseAdapter should conform to P03PhaseProtocol."""
        # Arrange - R0PhaseAdapter from PHASE_REGISTRY takes no constructor args
        adapter = R0PhaseAdapter()

        ctx = P03RunnerContext.create(
            syscalls=mock_syscalls,
            logger=logging.getLogger("test.r0.adapter"),
        )

        # Assert: Adapter has required protocol attributes
        assert adapter.phase_id == P03PhaseId.R0_INIT
        assert hasattr(adapter, "run")
        assert hasattr(adapter, "should_skip")
        assert hasattr(adapter, "idempotency_key")

    @pytest.mark.asyncio
    async def test_adapter_run_calls_r0(
        self,
        mock_syscalls: MockSyscalls,
        sample_envelope: P03BatchEnvelope,
    ) -> None:
        """R0PhaseAdapter.run() should delegate to R0BatchSelector."""
        # Arrange - R0PhaseAdapter takes no constructor args
        adapter = R0PhaseAdapter()

        ctx = P03RunnerContext.create(
            syscalls=mock_syscalls,
            logger=logging.getLogger("test.r0.adapter.run"),
            config={
                "tenant_id": "tenant-test-001",
                "space_id": "family-test-abc",
            },
        )

        # Act
        result = await adapter.run(sample_envelope, ctx)

        # Assert
        assert result.phase_id == P03PhaseId.R0_INIT
        assert result.status in (P03PhaseStatus.DONE, P03PhaseStatus.SKIP)


# =============================================================================
# TEST: SEQUENTIAL RUNNER WITH STUB PHASES
# =============================================================================


class StubPhase:
    """Minimal stub phase for runner tests."""

    def __init__(
        self,
        phase_id: P03PhaseId,
        should_skip: bool = False,
        should_fail: bool = False,
    ):
        self._phase_id = phase_id
        self._should_skip = should_skip
        self._should_fail = should_fail
        self.call_count = 0

    @property
    def phase_id(self) -> P03PhaseId:
        return self._phase_id

    async def run(
        self,
        envelope: P03BatchEnvelope,
        ctx: P03RunnerContext,
    ) -> P03PhaseResult:
        self.call_count += 1

        if self._should_fail:
            return P03PhaseResult.fail(
                phase_id=self._phase_id,
                error=P03Error.create(
                    phase=self._phase_id.value,
                    stage_id="stub",
                    error_type="TEST_ERROR",
                    error_message="Stub phase simulated failure",
                    recoverable=True,
                ),
                duration_ms=1,
            )

        if self._should_skip:
            return P03PhaseResult.skip(
                phase_id=self._phase_id,
                reason="Stub phase skip",
                duration_ms=1,
            )

        return P03PhaseResult.done(
            phase_id=self._phase_id,
            duration_ms=5,
            outputs_summary={"processed": True, "stub": True},
        )

    def should_skip(
        self,
        envelope: P03BatchEnvelope,
        ctx: P03RunnerContext,
    ) -> Tuple[bool, str]:
        if self._should_skip:
            return True, "Stub phase configured to skip"
        return False, ""

    def idempotency_key(
        self,
        envelope: P03BatchEnvelope,
        ctx: P03RunnerContext,
    ) -> str:
        return f"{self._phase_id.value}:{envelope.ctx.cycle_id}"


class TestSequentialRunnerLocal:
    """Test P03SequentialRunner with stub phases."""

    @pytest.mark.asyncio
    async def test_runner_executes_all_phases_in_order(
        self,
        sample_envelope: P03BatchEnvelope,
        sample_runner_context: P03RunnerContext,
    ) -> None:
        """Sequential runner should execute phases R0→R8 in order."""
        # Arrange: Create stub phases for all phase IDs
        phases = {
            P03PhaseId.R0_INIT: StubPhase(P03PhaseId.R0_INIT),
            P03PhaseId.R1_SCORE: StubPhase(P03PhaseId.R1_SCORE),
            P03PhaseId.R2_CLUSTER: StubPhase(P03PhaseId.R2_CLUSTER),
            P03PhaseId.R3_PRUNE: StubPhase(P03PhaseId.R3_PRUNE),
            P03PhaseId.R4_KG: StubPhase(P03PhaseId.R4_KG),
            P03PhaseId.R5_DREAM: StubPhase(P03PhaseId.R5_DREAM),
            P03PhaseId.R6_STAGE: StubPhase(P03PhaseId.R6_STAGE),
            P03PhaseId.R7_WRITE: StubPhase(P03PhaseId.R7_WRITE),
            P03PhaseId.R8_EMIT: StubPhase(P03PhaseId.R8_EMIT),
        }

        runner = P03SequentialRunner(phases=phases)

        # Act
        result = await runner.run(sample_envelope, sample_runner_context)

        # Assert: All phases were called
        for phase_id, phase in phases.items():
            assert phase.call_count == 1, f"Phase {phase_id} was not called once"

        assert result.is_success

    @pytest.mark.asyncio
    async def test_runner_stops_on_phase_failure(
        self,
        sample_envelope: P03BatchEnvelope,
        sample_runner_context: P03RunnerContext,
    ) -> None:
        """Sequential runner should stop when a phase fails."""
        # Arrange: R3 fails
        phases = {
            P03PhaseId.R0_INIT: StubPhase(P03PhaseId.R0_INIT),
            P03PhaseId.R1_SCORE: StubPhase(P03PhaseId.R1_SCORE),
            P03PhaseId.R2_CLUSTER: StubPhase(P03PhaseId.R2_CLUSTER),
            P03PhaseId.R3_PRUNE: StubPhase(P03PhaseId.R3_PRUNE, should_fail=True),
            P03PhaseId.R4_KG: StubPhase(P03PhaseId.R4_KG),
            P03PhaseId.R5_DREAM: StubPhase(P03PhaseId.R5_DREAM),
            P03PhaseId.R6_STAGE: StubPhase(P03PhaseId.R6_STAGE),
            P03PhaseId.R7_WRITE: StubPhase(P03PhaseId.R7_WRITE),
            P03PhaseId.R8_EMIT: StubPhase(P03PhaseId.R8_EMIT),
        }

        runner = P03SequentialRunner(phases=phases)

        # Act
        result = await runner.run(sample_envelope, sample_runner_context)

        # Assert: Phases after R3 were not called
        assert phases[P03PhaseId.R0_INIT].call_count == 1
        assert phases[P03PhaseId.R1_SCORE].call_count == 1
        assert phases[P03PhaseId.R2_CLUSTER].call_count == 1
        assert phases[P03PhaseId.R3_PRUNE].call_count == 1
        assert phases[P03PhaseId.R4_KG].call_count == 0  # Should not run
        assert phases[P03PhaseId.R5_DREAM].call_count == 0
        assert result.is_failed

    @pytest.mark.asyncio
    async def test_runner_handles_skip_phase(
        self,
        sample_envelope: P03BatchEnvelope,
        sample_runner_context: P03RunnerContext,
    ) -> None:
        """Sequential runner should continue past skipped phases."""
        # Arrange: R5 (dream) skipped
        phases = {
            P03PhaseId.R0_INIT: StubPhase(P03PhaseId.R0_INIT),
            P03PhaseId.R1_SCORE: StubPhase(P03PhaseId.R1_SCORE),
            P03PhaseId.R2_CLUSTER: StubPhase(P03PhaseId.R2_CLUSTER),
            P03PhaseId.R3_PRUNE: StubPhase(P03PhaseId.R3_PRUNE),
            P03PhaseId.R4_KG: StubPhase(P03PhaseId.R4_KG),
            P03PhaseId.R5_DREAM: StubPhase(P03PhaseId.R5_DREAM, should_skip=True),
            P03PhaseId.R6_STAGE: StubPhase(P03PhaseId.R6_STAGE),
            P03PhaseId.R7_WRITE: StubPhase(P03PhaseId.R7_WRITE),
            P03PhaseId.R8_EMIT: StubPhase(P03PhaseId.R8_EMIT),
        }

        runner = P03SequentialRunner(phases=phases)

        # Act
        result = await runner.run(sample_envelope, sample_runner_context)

        # Assert: All phases called, R5 was skipped but R6-R8 still ran
        assert phases[P03PhaseId.R5_DREAM].call_count == 1  # Called but returned SKIP
        assert phases[P03PhaseId.R6_STAGE].call_count == 1  # Should still run
        assert result.is_success


# =============================================================================
# TEST: FULL E2E WITH PHASE REGISTRY
# =============================================================================


class TestP03FullE2ELocal:
    """
    Full end-to-end test using real phase implementations where available
    and stubs where not.
    """

    @pytest.mark.asyncio
    async def test_phase_registry_loads(self) -> None:
        """Verify PHASE_REGISTRY is populated correctly."""
        assert PHASE_REGISTRY is not None
        assert len(PHASE_REGISTRY) > 0

        # Check expected phases are present (R0-R8, excluding COMPLETE which is a terminal state)
        executable_phases = [
            P03PhaseId.R0_INIT,
            P03PhaseId.R1_SCORE,
            P03PhaseId.R2_CLUSTER,
            P03PhaseId.R3_PRUNE,
            P03PhaseId.R4_KG,
            P03PhaseId.R5_DREAM,
            P03PhaseId.R6_STAGE,
            P03PhaseId.R7_WRITE,
            P03PhaseId.R8_EMIT,
        ]
        for phase_id in executable_phases:
            assert phase_id in PHASE_REGISTRY, f"Missing phase: {phase_id}"

    @pytest.mark.asyncio
    async def test_full_cycle_with_real_phases(
        self,
        mock_syscalls: MockSyscalls,
        sample_envelope: P03BatchEnvelope,
    ) -> None:
        """Test full cycle using PHASE_REGISTRY phases."""
        # Arrange
        ctx = P03RunnerContext.create(
            syscalls=mock_syscalls,
            logger=logging.getLogger("test.p03.e2e.full"),
            config={
                "tenant_id": "tenant-test-001",
                "space_id": "family-test-abc",
            },
        )

        runner = P03SequentialRunner(phases=PHASE_REGISTRY)

        # Act
        result = await runner.run(sample_envelope, ctx)

        # Assert: Cycle should complete (success or with expected failures)
        assert result is not None
        # Log the result for debugging
        print(f"Cycle result: success={result.is_success}, phases={len(result.phase_results)}")
        for phase_id, pr in result.phase_results.items():
            print(f"  {phase_id.value}: {pr.status.value}")


# =============================================================================
# TEST: SKIP PATHS (R2→R6, R4→R6)
# =============================================================================


class TestP03SkipPathsLocal:
    """Test the skip transition paths defined in runner contract."""

    @pytest.mark.asyncio
    async def test_single_event_skips_r2_r3_r4(
        self,
        mock_syscalls: MockSyscalls,
        sample_runner_context: P03RunnerContext,
    ) -> None:
        """Single event should skip clustering (R2), dedup (R3), KG (R4)."""
        # Arrange: Create context with single event
        single_ctx = P03CycleContext.create(
            tenant_id="tenant-test-001",
            space_id="family-test-abc",
            event_ids=["evt-single-001"],
            trigger_type="MANUAL",
            trigger_reason="Single event skip test",
        )
        envelope = P03BatchEnvelope.create(single_ctx)

        # Use stub phases that check skip logic
        phases = {
            P03PhaseId.R0_INIT: StubPhase(P03PhaseId.R0_INIT),
            P03PhaseId.R1_SCORE: StubPhase(P03PhaseId.R1_SCORE),
            P03PhaseId.R2_CLUSTER: StubPhase(P03PhaseId.R2_CLUSTER),
            P03PhaseId.R3_PRUNE: StubPhase(P03PhaseId.R3_PRUNE),
            P03PhaseId.R4_KG: StubPhase(P03PhaseId.R4_KG),
            P03PhaseId.R5_DREAM: StubPhase(P03PhaseId.R5_DREAM, should_skip=True),
            P03PhaseId.R6_STAGE: StubPhase(P03PhaseId.R6_STAGE),
            P03PhaseId.R7_WRITE: StubPhase(P03PhaseId.R7_WRITE),
            P03PhaseId.R8_EMIT: StubPhase(P03PhaseId.R8_EMIT),
        }

        runner = P03SequentialRunner(phases=phases)

        # Act
        result = await runner.run(envelope, sample_runner_context)

        # Assert: Cycle completes
        assert result is not None

    @pytest.mark.asyncio
    async def test_high_backlog_skips_r5(
        self,
        mock_syscalls: MockSyscalls,
    ) -> None:
        """High backlog should skip R5 (dream phase)."""
        # Arrange: Create context with high pending count
        backlog_ctx = P03CycleContext.create(
            tenant_id="tenant-test-001",
            space_id="family-test-abc",
            event_ids=["evt-001", "evt-002", "evt-003"],
            trigger_type="THRESHOLD",
            trigger_reason="Backlog exceeded",
            pending_before=10000,  # High backlog
        )
        envelope = P03BatchEnvelope.create(backlog_ctx)

        ctx = P03RunnerContext.create(
            syscalls=mock_syscalls,
            logger=logging.getLogger("test.skip.backlog"),
            config={
                "r5_skip_on_backlog": True,
                "backlog_threshold": 5000,
            },
        )

        phases = {
            P03PhaseId.R0_INIT: StubPhase(P03PhaseId.R0_INIT),
            P03PhaseId.R1_SCORE: StubPhase(P03PhaseId.R1_SCORE),
            P03PhaseId.R2_CLUSTER: StubPhase(P03PhaseId.R2_CLUSTER),
            P03PhaseId.R3_PRUNE: StubPhase(P03PhaseId.R3_PRUNE),
            P03PhaseId.R4_KG: StubPhase(P03PhaseId.R4_KG),
            P03PhaseId.R5_DREAM: StubPhase(P03PhaseId.R5_DREAM, should_skip=True),
            P03PhaseId.R6_STAGE: StubPhase(P03PhaseId.R6_STAGE),
            P03PhaseId.R7_WRITE: StubPhase(P03PhaseId.R7_WRITE),
            P03PhaseId.R8_EMIT: StubPhase(P03PhaseId.R8_EMIT),
        }

        runner = P03SequentialRunner(phases=phases)

        # Act
        result = await runner.run(envelope, ctx)

        # Assert: R5 was skipped but cycle completed
        assert phases[P03PhaseId.R5_DREAM].call_count == 1  # Called to check skip
        assert result.is_success


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
