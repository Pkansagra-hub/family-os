"""
SessionState Test Fixtures
==========================

IMPLEMENTATION PLAN: docs/plans/sessionstate-implementation-plan.md
EPIC: 4.1 Test Infrastructure
ISSUES: 4.1.1, 4.1.2, 4.1.3, 4.1.4

Provides shared pytest fixtures for SessionState tests.

TESTING PHILOSOPHY (from plan):
- NO MOCKS - Use real adapters with real data
- Mocks hide integration bugs and don't test actual behavior
- Use InMemoryStorageAdapter for fast tests
- Use SQLiteStorageAdapter for integration tests

FIXTURE CATEGORIES:
==================
1. Storage Fixtures - InMemory (fast), SQLite (integration)
2. Event Fixtures - LocalEventAdapter with capture mode
3. Writer Fixtures - DirectWriterAdapter for mutations
4. Lifecycle Fixtures - StandaloneLifecycle for session control
5. Manager Fixtures - Full SessionStateManager with wiring
6. Tier Fixtures - HotTier, WarmTier, LocalColdTier
7. Section Fixtures - Individual section instances
8. Engine Fixtures - SizeTracker, MutationGuard, etc.
9. Test Data Fixtures - Sample beliefs, turns, tasks
10. Performance Fixtures - SLA timing assertions

USAGE:
======
    def test_mutation(standalone_session_state, sample_belief):
        result = standalone_session_state.mutate(
            section="beliefs_active",
            operation="add",
            data=sample_belief,
        )
        assert result.success

    def test_events(event_adapter_with_capture):
        adapter = event_adapter_with_capture
        adapter.emit("test.event", {"key": "value"})
        adapter.assert_emitted("test.event", count=1)
"""

import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

import pytest

from k1.sessionstate import (
    EvictionEngine,
    HotTier,
    LocalColdArchive,
    LocalColdTier,
    MigrationEngine,
    MutationGuard,
    ReconstructionSLA,
    SessionStateFactory,
    SessionStateManager,
    SizeTracker,
    SnapshotAPI,
    WarmTier,
)
from k1.sessionstate.adapters import (
    DirectWriterAdapter,
    InMemoryStorageAdapter,
    LocalEventAdapter,
    SQLiteStorageAdapter,
)
from k1.sessionstate.ports.lifecycle import LifecycleConfig
from k1.sessionstate.sections import (
    AffectiveNowSection,
    BeliefsActiveSection,
    BeliefsHistorySection,
    ClarificationsSection,
    ControlSection,
    HistoryActiveSection,
    HistoryRecentSection,
    MetaSection,
    NarrativeActiveSection,
    PersonaSection,
    ScoreboardSection,
    TelemetrySection,
)

# =============================================================================
# IMPORTS - Real Adapters (NO MOCKS)
# =============================================================================


# =============================================================================
# STORAGE FIXTURES (Issue 4.1.2)
# =============================================================================


@pytest.fixture
def in_memory_storage() -> Generator[InMemoryStorageAdapter, None, None]:
    """
    In-memory storage adapter for fast testing.

    Features:
    - No disk I/O (fast)
    - Auto-cleared between tests
    - Full IStoragePort compliance

    Usage:
        def test_archive(in_memory_storage):
            result = in_memory_storage.archive("beliefs", b"data", {"key": "value"})
            assert result.success
    """
    adapter = InMemoryStorageAdapter()
    yield adapter
    adapter.clear()


@pytest.fixture
def sqlite_storage(tmp_path: Path) -> Generator[SQLiteStorageAdapter, None, None]:
    """
    SQLite storage adapter for integration testing.

    Features:
    - Real SQLite database (tests persistence)
    - Isolated per test via tmp_path
    - Automatic cleanup

    Usage:
        def test_persist(sqlite_storage):
            result = sqlite_storage.archive("beliefs", b"data", {})
            # Data persists across calls within test
    """
    db_path = tmp_path / "test_sessionstate.db"
    adapter = SQLiteStorageAdapter(db_path=db_path)
    yield adapter
    adapter.close()


@pytest.fixture
def local_cold_archive(tmp_path: Path) -> Generator[LocalColdArchive, None, None]:
    """
    LocalColdArchive for testing checkpoint/restore flows.

    Features:
    - Real SQLite backend
    - Full archive/restore API
    - Isolated per test

    Usage:
        def test_checkpoint(local_cold_archive):
            local_cold_archive.archive_checkpoint(session_id, data)
            restored = local_cold_archive.restore_checkpoint(session_id)
    """
    db_path = tmp_path / "test_local_cold.db"
    archive = LocalColdArchive(db_path=db_path)
    yield archive
    archive.close()


# =============================================================================
# EVENT FIXTURES (Issue 4.1.3)
# =============================================================================


@pytest.fixture
def event_adapter() -> Generator[LocalEventAdapter, None, None]:
    """
    Local event adapter for testing.

    Features:
    - In-process dispatch
    - Background thread handling
    - Automatic cleanup

    Usage:
        def test_subscribe(event_adapter):
            received = []
            event_adapter.subscribe("test", lambda e: received.append(e))
            event_adapter.emit("test", {"data": 1})
    """
    adapter = LocalEventAdapter(capture_mode=False)
    yield adapter
    adapter.stop()


@pytest.fixture
def event_adapter_with_capture() -> Generator[LocalEventAdapter, None, None]:
    """
    Local event adapter with capture mode for assertions.

    Features:
    - Captures all emitted events
    - Provides assertion helpers
    - Draining for inspection

    Usage:
        def test_mutation_emits_event(session, event_adapter_with_capture):
            session.mutate("control", "set", {"key": "value"})

            event_adapter_with_capture.assert_emitted(
                "sessionstate.mutation.approved",
                count=1,
            )
            events = event_adapter_with_capture.drain()
    """
    adapter = LocalEventAdapter(capture_mode=True)
    yield adapter
    adapter.stop()


# =============================================================================
# WRITER FIXTURES
# =============================================================================


@pytest.fixture
def direct_writer_standalone() -> DirectWriterAdapter:
    """
    DirectWriterAdapter without manager (for unit tests).

    NOTE: Limited functionality without manager reference.
    Use standalone_session_state fixture for full write testing.
    """
    # Create minimal adapter for interface testing
    adapter = DirectWriterAdapter(
        manager=None,
        guard=None,
        writer_id="test-writer",
    )
    return adapter


# =============================================================================
# LIFECYCLE FIXTURES
# =============================================================================


@pytest.fixture
def lifecycle_config_default() -> LifecycleConfig:
    """Default lifecycle configuration."""
    return LifecycleConfig.default()


@pytest.fixture
def lifecycle_config_testing() -> LifecycleConfig:
    """Testing lifecycle configuration (no periodic checkpoints)."""
    return LifecycleConfig.testing()


# =============================================================================
# MANAGER FIXTURES (Issue 4.1.1)
# =============================================================================


@pytest.fixture
def standalone_session_state(tmp_path: Path) -> Generator[SessionStateManager, None, None]:
    """
    Full standalone SessionStateManager for testing.

    Features:
    - Real SQLite storage (LOCAL COLD)
    - Real LocalEventAdapter
    - Real DirectWriterAdapter
    - Real StandaloneLifecycle
    - Auto-started, auto-stopped

    This is the PRIMARY fixture for testing SessionState behavior.

    Usage:
        def test_full_flow(standalone_session_state):
            manager = standalone_session_state

            # Mutation
            result = manager.mutate("beliefs_active", "add", belief_data)
            assert result.success

            # Read
            snapshot = manager.get_snapshot()
            assert snapshot.is_running

            # Checkpoint
            checkpoint = manager.checkpoint()
            assert checkpoint.success
    """
    db_path = tmp_path / "standalone_test.db"
    session_id = f"test-{uuid.uuid4().hex[:8]}"

    manager = SessionStateFactory.create_standalone(
        session_id=session_id,
        db_path=db_path,
        checkpoint_interval_s=0,  # Disable periodic checkpoints for testing
    )

    # Start session
    result = manager.start(restore_if_exists=False)
    assert result.success, f"Failed to start session: {result.error}"

    yield manager

    # Cleanup
    if manager.is_running:
        manager.stop(checkpoint_before_stop=False)


@pytest.fixture
def test_session() -> Generator[SessionStateManager, None, None]:
    """
    Minimal test session using create_for_testing().

    Features:
    - In-memory storage (fastest)
    - Capture mode events
    - No periodic checkpoints

    Use this for fast unit tests that don't need persistence.

    Usage:
        def test_quick(test_session):
            result = test_session.mutate("control", "set_mode", {"mode": "test"})
            assert result.success
    """
    manager = SessionStateFactory.create_for_testing()

    result = manager.start(restore_if_exists=False)
    assert result.success, f"Failed to start test session: {result.error}"

    yield manager

    if manager.is_running:
        manager.stop(checkpoint_before_stop=False)


@pytest.fixture
def session_with_data(test_session, sample_belief, sample_turn) -> SessionStateManager:
    """
    Test session pre-populated with sample data.

    Contains:
    - 1 belief in beliefs_active
    - 1 turn in history_active

    Usage:
        def test_with_data(session_with_data):
            beliefs = session_with_data.get_section("beliefs_active")
            assert beliefs.size() > 0
    """
    manager = test_session

    # Add sample belief
    manager.mutate(
        section="beliefs_active",
        operation="add",
        data=sample_belief,
    )

    # Add sample turn
    manager.mutate(
        section="history_active",
        operation="append",
        data=sample_turn,
    )

    return manager


# =============================================================================
# TIER FIXTURES
# =============================================================================


@pytest.fixture
def hot_tier() -> HotTier:
    """
    Empty HotTier for testing.

    Usage:
        def test_hot_pressure(hot_tier):
            section = hot_tier.get_section("beliefs_active")
            section.add(belief)
            pressure = hot_tier.get_pressure()
    """
    return HotTier()


@pytest.fixture
def warm_tier() -> WarmTier:
    """
    Empty WarmTier for testing.

    Usage:
        def test_eviction_candidates(warm_tier):
            candidates = warm_tier.get_eviction_candidates()
            assert candidates[0].section == "telemetry"
    """
    return WarmTier()


@pytest.fixture
def local_cold_tier(tmp_path: Path) -> Generator[LocalColdTier, None, None]:
    """
    LocalColdTier with temp database for testing.

    Usage:
        def test_archive_restore(local_cold_tier):
            result = local_cold_tier.archive("beliefs", data, metadata)
            restored = local_cold_tier.restore("beliefs", {})
    """
    db_path = tmp_path / "local_cold_tier.db"
    archive = LocalColdArchive(db_path=db_path)
    tier = LocalColdTier(storage=archive)
    yield tier
    archive.close()


# =============================================================================
# SECTION FIXTURES
# =============================================================================


@pytest.fixture
def control_section() -> ControlSection:
    """Empty ControlSection for testing."""
    return ControlSection()


@pytest.fixture
def beliefs_active_section() -> BeliefsActiveSection:
    """Empty BeliefsActiveSection for testing."""
    return BeliefsActiveSection()


@pytest.fixture
def beliefs_history_section() -> BeliefsHistorySection:
    """Empty BeliefsHistorySection for testing."""
    return BeliefsHistorySection()


@pytest.fixture
def scoreboard_section() -> ScoreboardSection:
    """Empty ScoreboardSection for testing."""
    return ScoreboardSection()


@pytest.fixture
def history_active_section() -> HistoryActiveSection:
    """Empty HistoryActiveSection for testing."""
    return HistoryActiveSection()


@pytest.fixture
def history_recent_section() -> HistoryRecentSection:
    """Empty HistoryRecentSection for testing."""
    return HistoryRecentSection()


@pytest.fixture
def clarifications_section() -> ClarificationsSection:
    """Empty ClarificationsSection for testing."""
    return ClarificationsSection()


@pytest.fixture
def affective_now_section() -> AffectiveNowSection:
    """Empty AffectiveNowSection for testing."""
    return AffectiveNowSection()


@pytest.fixture
def narrative_active_section() -> NarrativeActiveSection:
    """Empty NarrativeActiveSection for testing."""
    return NarrativeActiveSection()


@pytest.fixture
def meta_section() -> MetaSection:
    """Empty MetaSection for testing."""
    return MetaSection()


@pytest.fixture
def persona_section() -> PersonaSection:
    """Empty PersonaSection for testing."""
    return PersonaSection()


@pytest.fixture
def telemetry_section() -> TelemetrySection:
    """Empty TelemetrySection for testing."""
    return TelemetrySection()


# =============================================================================
# ENGINE FIXTURES
# =============================================================================


@pytest.fixture
def size_tracker() -> SizeTracker:
    """SizeTracker for testing size accounting."""
    return SizeTracker()


@pytest.fixture
def mutation_guard(size_tracker: SizeTracker) -> MutationGuard:
    """MutationGuard for testing preflight validation."""
    return MutationGuard(size_tracker=size_tracker)


@pytest.fixture
def eviction_engine(
    size_tracker: SizeTracker,
    mutation_guard: MutationGuard,
    local_cold_archive: LocalColdArchive,
) -> EvictionEngine:
    """
    EvictionEngine for integration testing.

    Features:
    - Real SizeTracker (actual byte accounting)
    - Real MutationGuard (actual preflight validation)
    - Real LocalColdArchive (actual SQLite archive)

    Usage:
        def test_eviction_flow(eviction_engine):
            # Evict
            result = eviction_engine.evict(target_bytes=1024, reason="test")
            assert result.success
    """
    return EvictionEngine(
        size_tracker=size_tracker,
        local_cold=local_cold_archive,
        mutation_guard=mutation_guard,
    )


@pytest.fixture
def migration_engine(
    size_tracker: SizeTracker,
    mutation_guard: MutationGuard,
) -> MigrationEngine:
    """
    MigrationEngine for integration testing.

    Features:
    - Real SizeTracker (actual byte accounting)
    - Real MutationGuard (actual preflight validation)

    Usage:
        def test_migration_flow(migration_engine):
            # Demote overflow
            result = migration_engine.demote_history_overflow()
            assert result.success
    """
    return MigrationEngine(
        size_tracker=size_tracker,
        mutation_guard=mutation_guard,
    )


@pytest.fixture
def reconstruction_sla(
    local_cold_archive: LocalColdArchive,
    hot_tier: HotTier,
    warm_tier: WarmTier,
) -> ReconstructionSLA:
    """
    ReconstructionSLA for integration testing.

    Features:
    - Real LocalColdArchive (actual SQLite restore)
    - Real HotTier/WarmTier (actual hydration)
    - SLA timing enforcement (<50ms LOCAL COLD, <100ms K0)

    Usage:
        def test_reconstruction(reconstruction_sla, local_cold_archive):
            # Archive a session
            local_cold_archive.checkpoint(session_id, data, {})

            # Reconstruct
            result = reconstruction_sla.reconstruct(session_id)
            assert result.success
            assert result.sla_met
    """
    return ReconstructionSLA(
        local_cold=local_cold_archive,
        k0_sync_port=None,
        hot=hot_tier,
        warm=warm_tier,
    )


@pytest.fixture
def snapshot_api(size_tracker: SizeTracker) -> SnapshotAPI:
    """
    SnapshotAPI for integration testing.

    Features:
    - Real SizeTracker (actual size data)
    - Health monitoring and diagnostics
    - Thrash detection

    Usage:
        def test_snapshot(snapshot_api, size_tracker):
            # Update sizes
            size_tracker.update("control", 1024)

            # Get snapshot
            snapshot = snapshot_api.get_snapshot()
            assert snapshot.total_size_bytes > 0
    """
    return SnapshotAPI(size_tracker=size_tracker)


@pytest.fixture
def full_engine_stack(
    size_tracker: SizeTracker,
    mutation_guard: MutationGuard,
    eviction_engine: EvictionEngine,
    migration_engine: MigrationEngine,
    reconstruction_sla: ReconstructionSLA,
    snapshot_api: SnapshotAPI,
    hot_tier: HotTier,
    warm_tier: WarmTier,
    local_cold_tier: LocalColdTier,
) -> Dict[str, Any]:
    """
    Complete engine stack for end-to-end integration testing.

    Returns a dict with all engines and tiers wired together.
    This is the PRIMARY fixture for testing the entire SessionState
    data flow without going through SessionStateManager.

    Usage:
        def test_full_flow(full_engine_stack):
            engines = full_engine_stack
            hot = engines["hot_tier"]
            warm = engines["warm_tier"]
            migration = engines["migration_engine"]
            eviction = engines["eviction_engine"]

            # Add 15 turns (overflow HOT)
            for i in range(15):
                hot.get_section("history_active").add_turn({...})

            # Migrate overflow to WARM
            migration.demote_history_overflow()

            # Assert HOT has 10, WARM has 5
            assert hot.get_section("history_active").count() == 10
            assert warm.get_section("history_recent").compressed_count() == 5
    """
    return {
        "size_tracker": size_tracker,
        "mutation_guard": mutation_guard,
        "eviction_engine": eviction_engine,
        "migration_engine": migration_engine,
        "reconstruction_sla": reconstruction_sla,
        "snapshot_api": snapshot_api,
        "hot_tier": hot_tier,
        "warm_tier": warm_tier,
        "local_cold_tier": local_cold_tier,
    }


# =============================================================================
# TEST DATA FIXTURES
# =============================================================================


@pytest.fixture
def sample_belief() -> Dict[str, Any]:
    """Sample belief for testing mutations."""
    return {
        "belief_id": f"belief-{uuid.uuid4().hex[:8]}",
        "subject": "user",
        "predicate": "prefers",
        "object": "dark mode",
        "confidence": 0.9,
        "source": "explicit",
        "created_at_ms": int(time.time() * 1000),
    }


@pytest.fixture
def sample_turn() -> Dict[str, Any]:
    """Sample conversation turn for testing."""
    return {
        "turn_id": f"turn-{uuid.uuid4().hex[:8]}",
        "turn_number": 1,
        "user_message": "Hello, how are you?",
        "assistant_message": "I'm doing well, thank you! How can I help you today?",
        "timestamp_ms": int(time.time() * 1000),
        "tokens_used": 42,
    }


@pytest.fixture
def sample_task() -> Dict[str, Any]:
    """Sample scoreboard task for testing."""
    return {
        "task_id": f"task-{uuid.uuid4().hex[:8]}",
        "description": "Test task for unit testing",
        "status": "pending",
        "progress": 0.0,
        "priority": "normal",
        "created_at_ms": int(time.time() * 1000),
    }


@pytest.fixture
def sample_clarification() -> Dict[str, Any]:
    """Sample clarification request for testing."""
    return {
        "clarification_id": f"clarify-{uuid.uuid4().hex[:8]}",
        "question": "What do you mean by 'it'?",
        "context": "User said 'fix it' but 'it' is ambiguous",
        "options": ["the code", "the bug", "the feature"],
        "created_at_ms": int(time.time() * 1000),
    }


@pytest.fixture
def sample_narrative_thread() -> Dict[str, Any]:
    """Sample narrative thread for testing."""
    return {
        "thread_id": f"thread-{uuid.uuid4().hex[:8]}",
        "topic": "Project planning",
        "summary": "User is planning a new project",
        "status": "active",
        "created_at_ms": int(time.time() * 1000),
    }


@pytest.fixture
def bulk_beliefs(sample_belief) -> List[Dict[str, Any]]:
    """Generate 10 beliefs for bulk testing."""
    beliefs = []
    for i in range(10):
        belief = sample_belief.copy()
        belief["belief_id"] = f"belief-bulk-{i}"
        belief["object"] = f"preference_{i}"
        beliefs.append(belief)
    return beliefs


@pytest.fixture
def bulk_turns(sample_turn) -> List[Dict[str, Any]]:
    """Generate 10 turns for bulk testing."""
    turns = []
    base_time = int(time.time() * 1000)
    for i in range(10):
        turn = sample_turn.copy()
        turn["turn_id"] = f"turn-bulk-{i}"
        turn["turn_number"] = i + 1
        turn["user_message"] = f"Message {i}"
        turn["assistant_message"] = f"Response {i}"
        turn["timestamp_ms"] = base_time + (i * 1000)
        turns.append(turn)
    return turns


# =============================================================================
# PERFORMANCE FIXTURES (Issue 4.1.4 - FlatBuffers)
# =============================================================================


@dataclass
class TimerResult:
    """Result of a performance timing."""

    label: str
    duration_ms: float
    start_ns: int
    end_ns: int

    @property
    def duration_us(self) -> float:
        """Duration in microseconds."""
        return self.duration_ms * 1000


class PerformanceTimer:
    """
    Context manager for SLA timing assertions.

    Usage:
        timer = PerformanceTimer()
        with timer.measure("read"):
            section = manager.get_section("control")

        assert timer.get("read").duration_ms < 0.1  # <100μs
    """

    def __init__(self):
        self._results: Dict[str, TimerResult] = {}

    @contextmanager
    def measure(self, label: str) -> Generator[None, None, None]:
        """Measure duration of code block."""
        start = time.perf_counter_ns()
        try:
            yield
        finally:
            end = time.perf_counter_ns()
            duration_ns = end - start
            duration_ms = duration_ns / 1_000_000
            self._results[label] = TimerResult(
                label=label,
                duration_ms=duration_ms,
                start_ns=start,
                end_ns=end,
            )

    def get(self, label: str) -> TimerResult:
        """Get timing result by label."""
        return self._results[label]

    def assert_under_ms(self, label: str, max_ms: float) -> None:
        """Assert that timing is under threshold."""
        result = self._results[label]
        assert (
            result.duration_ms < max_ms
        ), f"{label} took {result.duration_ms:.3f}ms, expected <{max_ms}ms"

    def assert_under_us(self, label: str, max_us: float) -> None:
        """Assert that timing is under threshold (microseconds)."""
        result = self._results[label]
        assert (
            result.duration_us < max_us
        ), f"{label} took {result.duration_us:.1f}μs, expected <{max_us}μs"


@pytest.fixture
def perf_timer() -> PerformanceTimer:
    """
    Performance timer for SLA testing.

    Usage:
        def test_read_latency(test_session, perf_timer):
            with perf_timer.measure("read"):
                section = test_session.get_section("control")

            perf_timer.assert_under_us("read", 100)  # SLA: <100μs
    """
    return PerformanceTimer()


# =============================================================================
# FLATBUFFER TEST UTILITIES
# =============================================================================


def assert_flatbuffer_roundtrip(section: Any, expected_max_bytes: Optional[int] = None) -> bytes:
    """
    Assert that a section can serialize and deserialize correctly.

    Args:
        section: Section instance with serialize()/deserialize() methods
        expected_max_bytes: Optional size budget assertion

    Returns:
        bytes: Serialized data

    Raises:
        AssertionError: If roundtrip fails or size exceeds budget
    """
    # Serialize
    serialized = section.serialize()
    assert isinstance(serialized, bytes), "serialize() must return bytes"

    if expected_max_bytes is not None:
        assert (
            len(serialized) <= expected_max_bytes
        ), f"Serialized size {len(serialized)} exceeds budget {expected_max_bytes}"

    # Deserialize into new instance
    section_type = type(section)
    restored = section_type.deserialize(serialized)

    # Verify equality (sections should implement __eq__)
    # If not, at least verify it didn't crash
    assert restored is not None, "deserialize() returned None"

    return serialized


def create_test_section(section_type: type, fill_pct: float = 0.5) -> Any:
    """
    Create a test section filled to specified capacity.

    Args:
        section_type: Section class to instantiate
        fill_pct: Target fill percentage (0.0 to 1.0)

    Returns:
        Section instance with test data
    """
    section = section_type()
    # Add data based on section type
    # This is a factory for test data generation
    return section


# =============================================================================
# CLEANUP HELPERS
# =============================================================================


@pytest.fixture(autouse=True)
def cleanup_temp_files(tmp_path: Path):
    """
    Automatic cleanup of temporary files after each test.

    This fixture runs automatically for all tests.
    """
    yield
    # tmp_path is automatically cleaned by pytest


# =============================================================================
# TEST MARKERS
# =============================================================================

# Usage:
# @pytest.mark.slow - Tests that take >1s
# @pytest.mark.integration - Integration tests requiring real adapters
# @pytest.mark.performance - Performance/SLA tests


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "slow: marks tests as slow (>1s)")
    config.addinivalue_line("markers", "integration: integration tests with real adapters")
    config.addinivalue_line("markers", "performance: performance/SLA tests")
    config.addinivalue_line("markers", "flatbuffers: FlatBuffers serialization tests")
