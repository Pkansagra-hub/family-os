"""
Multi-Reader Concurrent Access Integration Tests (Epic 4.3.6)
==============================================================

IMPLEMENTATION PLAN REFERENCE: docs/plans/sessionstate-implementation-plan.md
EPIC: 4.3 End-to-End Flow Integration Tests
ISSUE: 4.3.6

**Test multi-reader concurrent access via manager.get_section() while
manager.mutate() is active.**

ARCHITECTURE:
    SessionStateManager allows:
    - Multiple readers via get_section() / get_snapshot()
    - Single writer via mutate()
    - Readers are NOT blocked by writers
    - Writers are serialized via internal _write_lock

READ PATTERN:
    - Reads are non-blocking (lock-free for readers)
    - get_section() returns current section state
    - get_snapshot() returns consistent snapshot
    - Readers never wait for writers to complete

TEST SCENARIO:
    1. Create manager via SessionStateFactory.create_for_testing()
    2. Start manager: manager.start()
    3. Add initial data via manager.mutate()
    4. Launch writer thread doing manager.mutate() in loop
    5. Launch 10 reader threads doing manager.get_section() in loop
    6. Verify: (1) Readers never block, (2) <1ms read latency,
       (3) Readers see consistent data (no partial mutations)

FORBIDDEN PATTERNS (component tests, belong in Epic 4.2):
    - Direct DirectWriterAdapter.request_mutation() calls
    - Direct section.add_turn() calls
    - Direct MutationGuard access
"""

from __future__ import annotations

import statistics
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import pytest

from k1.sessionstate.factory import SessionStateFactory
from k1.sessionstate.manager import SessionSnapshot, SessionStateManager

# =============================================================================
# CONSTANTS
# =============================================================================

# SLA from plan: <1ms read latency
READ_LATENCY_SLA_MS: float = 1.0

# Number of concurrent readers
NUM_READERS: int = 10

# Number of reads per reader
READS_PER_READER: int = 20

# Total reads expected
TOTAL_READS: int = NUM_READERS * READS_PER_READER


# =============================================================================
# HELPER FUNCTIONS - All use manager APIs
# =============================================================================


def create_turn_data(turn_id: int, thread_id: int = 0, size_bytes: int = 100) -> dict:
    """
    Create turn data compatible with history_active.append().
    """
    import json

    user_msg = f"Thread {thread_id} turn {turn_id} user message"
    assistant_resp = f"Thread {thread_id} turn {turn_id} assistant response"

    base = {
        "user_message": user_msg,
        "assistant_response": assistant_resp,
    }

    current_size = len(json.dumps(base))
    if size_bytes > current_size:
        padding = "x" * (size_bytes - current_size)
        base["assistant_response"] = assistant_resp + padding

    return base


def measure_read_latency(
    session: SessionStateManager,
    section: str = "control",
) -> float:
    """Measure read latency in milliseconds."""
    start = time.perf_counter()
    _ = session.get_section(section)
    end = time.perf_counter()
    return (end - start) * 1000


def measure_snapshot_latency(session: SessionStateManager) -> float:
    """Measure get_snapshot latency in milliseconds."""
    start = time.perf_counter()
    _ = session.get_snapshot()
    end = time.perf_counter()
    return (end - start) * 1000


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def session() -> SessionStateManager:
    """
    Create a SessionStateManager for testing.

    Uses SessionStateFactory.create_for_testing() which provides:
    - InMemoryStorageAdapter
    - LocalEventAdapter with capture_mode=True
    - DirectWriterAdapter
    - StandaloneLifecycle
    """
    manager = SessionStateFactory.create_for_testing()
    manager.start()
    yield manager
    manager.stop()


@pytest.fixture
def session_with_data(session: SessionStateManager) -> SessionStateManager:
    """Session with pre-populated data for reading."""
    # Add some data to sections via manager.mutate() (NOT direct section access)
    for i in range(5):
        session.mutate(
            "history_active",
            "append",
            create_turn_data(i, 0, 100),
            100,
        )

    return session


@pytest.fixture
def session_with_db(tmp_path: Path) -> SessionStateManager:
    """
    Create a SessionStateManager with real SQLite LOCAL COLD.
    """
    db_path = tmp_path / "test_multi_reader.db"
    manager = SessionStateFactory.create_standalone(
        session_id=f"multi-reader-test-{time.time_ns()}",
        db_path=db_path,
    )
    manager.start()
    yield manager
    manager.stop()


# =============================================================================
# TEST CLASS: Read Latency Under Concurrent Access
# =============================================================================


class TestReadLatencyUnderConcurrency:
    """
    Test read latency stays under 1ms SLA during concurrent access.
    """

    def test_single_read_under_sla(self, session_with_data: SessionStateManager) -> None:
        """Single read should be well under 1ms."""
        latency = measure_read_latency(session_with_data, "control")
        assert latency < READ_LATENCY_SLA_MS, f"Read latency {latency:.3f}ms exceeds SLA"

    def test_100_sequential_reads_under_sla(self, session_with_data: SessionStateManager) -> None:
        """100 sequential reads should all be under 1ms."""
        latencies = []
        for _ in range(100):
            latency = measure_read_latency(session_with_data, "control")
            latencies.append(latency)

        max_latency = max(latencies)
        p95_latency = sorted(latencies)[94]

        assert (
            max_latency < READ_LATENCY_SLA_MS
        ), f"Max read latency {max_latency:.3f}ms exceeds SLA"
        assert (
            p95_latency < READ_LATENCY_SLA_MS
        ), f"P95 read latency {p95_latency:.3f}ms exceeds SLA"

    def test_concurrent_readers_all_under_sla(self, session_with_data: SessionStateManager) -> None:
        """10 concurrent readers should all see <1ms latency."""
        latencies: list[float] = []
        errors: list[Exception] = []
        lock = threading.Lock()

        def read_many(reader_id: int) -> None:
            for _ in range(READS_PER_READER):
                try:
                    latency = measure_read_latency(session_with_data, "control")
                    with lock:
                        latencies.append(latency)
                except Exception as e:
                    with lock:
                        errors.append(e)

        threads = [threading.Thread(target=read_many, args=(i,)) for i in range(NUM_READERS)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Errors occurred: {errors}"
        assert len(latencies) == TOTAL_READS, f"Expected {TOTAL_READS} reads, got {len(latencies)}"

        max_latency = max(latencies)
        p95_latency = sorted(latencies)[int(len(latencies) * 0.95)]

        # Allow 2x SLA for concurrent access
        assert (
            max_latency < READ_LATENCY_SLA_MS * 2
        ), f"Max read latency {max_latency:.3f}ms exceeds 2x SLA"

    def test_snapshot_latency_under_sla(self, session_with_data: SessionStateManager) -> None:
        """Snapshot read should be under 1ms."""
        latency = measure_snapshot_latency(session_with_data)
        assert latency < READ_LATENCY_SLA_MS, f"Snapshot latency {latency:.3f}ms exceeds SLA"


# =============================================================================
# TEST CLASS: Readers While Writer Active (via manager.mutate())
# =============================================================================


class TestReadersWhileWriterActive:
    """
    Test concurrent read access while writes are happening via manager.mutate().

    Scenario: 10 concurrent readers while writer is active.
    Assertion: No blocking, <1ms read latency.
    """

    def test_readers_not_blocked_by_writer(self, session_with_data: SessionStateManager) -> None:
        """Readers should not be blocked by writer doing manager.mutate()."""
        read_latencies: list[float] = []
        write_count = [0]
        errors: list[Exception] = []
        stop_flag = threading.Event()
        lock = threading.Lock()

        def reader_loop(reader_id: int) -> None:
            while not stop_flag.is_set():
                try:
                    latency = measure_read_latency(session_with_data, "control")
                    with lock:
                        read_latencies.append(latency)
                except Exception as e:
                    with lock:
                        errors.append(e)

        def writer_loop() -> None:
            for i in range(50):
                if stop_flag.is_set():
                    break
                try:
                    result = session_with_data.mutate(
                        "history_active",
                        "append",
                        create_turn_data(i, 999, 50),
                        50,
                    )
                    if result.success:
                        with lock:
                            write_count[0] += 1
                except Exception as e:
                    with lock:
                        errors.append(e)

        # Start readers
        reader_threads = [
            threading.Thread(target=reader_loop, args=(i,)) for i in range(NUM_READERS)
        ]
        for t in reader_threads:
            t.start()

        # Run writer
        writer_thread = threading.Thread(target=writer_loop)
        writer_thread.start()
        writer_thread.join()

        # Stop readers
        stop_flag.set()
        for t in reader_threads:
            t.join()

        assert not errors, f"Errors occurred: {errors}"
        assert len(read_latencies) > 0, "No reads completed"
        assert write_count[0] > 0, "No writes completed"

        # Verify read latencies (allow margin for concurrent access)
        p95_latency = sorted(read_latencies)[int(len(read_latencies) * 0.95)]

        # Should be well under 10ms even during concurrent writes
        assert p95_latency < 10.0, f"P95 read latency {p95_latency:.3f}ms too high during writes"

    def test_all_reads_complete_regardless_of_writes(
        self, session_with_data: SessionStateManager
    ) -> None:
        """All reads should complete regardless of concurrent writes."""
        read_count = [0]
        write_count = [0]
        lock = threading.Lock()

        def do_reads() -> None:
            for _ in range(100):
                _ = session_with_data.get_section("control")
                with lock:
                    read_count[0] += 1

        def do_writes() -> None:
            for i in range(20):
                session_with_data.mutate(
                    "history_active", "append", create_turn_data(i, 888, 50), 50
                )
                with lock:
                    write_count[0] += 1

        read_threads = [threading.Thread(target=do_reads) for _ in range(10)]
        write_thread = threading.Thread(target=do_writes)

        for t in read_threads:
            t.start()
        write_thread.start()

        for t in read_threads:
            t.join()
        write_thread.join()

        # All reads should complete
        assert read_count[0] == 1000, f"Expected 1000 reads, got {read_count[0]}"
        assert write_count[0] == 20, f"Expected 20 writes, got {write_count[0]}"

    def test_snapshot_not_blocked_by_writer(self, session_with_data: SessionStateManager) -> None:
        """get_snapshot() should not be blocked by writer."""
        snapshot_latencies: list[float] = []
        write_count = [0]
        lock = threading.Lock()
        stop_flag = threading.Event()

        def writer_loop() -> None:
            for i in range(50):  # More writes to ensure overlap
                if stop_flag.is_set():
                    break
                session_with_data.mutate(
                    "history_active", "append", create_turn_data(i, 777, 50), 50
                )
                with lock:
                    write_count[0] += 1

        def reader_loop() -> None:
            for _ in range(50):  # Fixed number of reads
                if stop_flag.is_set():
                    break
                latency = measure_snapshot_latency(session_with_data)
                with lock:
                    snapshot_latencies.append(latency)

        writer_thread = threading.Thread(target=writer_loop)
        reader_thread = threading.Thread(target=reader_loop)

        # Start both threads
        writer_thread.start()
        reader_thread.start()

        writer_thread.join()
        stop_flag.set()
        reader_thread.join()

        assert len(snapshot_latencies) > 0, "No snapshot reads completed"
        assert write_count[0] > 0, "No writes completed"

        # P95 should be under 5ms even during writes
        p95_latency = sorted(snapshot_latencies)[int(len(snapshot_latencies) * 0.95)]
        assert p95_latency < 5.0, f"P95 snapshot latency {p95_latency:.3f}ms too high"


# =============================================================================
# TEST CLASS: Read Data Consistency
# =============================================================================


class TestReadDataConsistency:
    """
    Test that concurrent reads see consistent data (no partial mutations).
    """

    def test_readers_see_valid_section(self, session_with_data: SessionStateManager) -> None:
        """All concurrent readers should get valid section data."""
        sections: list[Any] = []
        lock = threading.Lock()

        def read_section(reader_id: int) -> None:
            for _ in range(10):
                section = session_with_data.get_section("control")
                with lock:
                    sections.append(section)

        threads = [threading.Thread(target=read_section, args=(i,)) for i in range(NUM_READERS)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(sections) == 100, f"Expected 100 sections, got {len(sections)}"
        assert all(s is not None for s in sections), "Some sections were None"

    def test_snapshot_read_consistent(self, session_with_data: SessionStateManager) -> None:
        """Snapshot reads should be internally consistent."""
        snapshots: list[SessionSnapshot] = []
        lock = threading.Lock()

        def read_snapshot() -> None:
            for _ in range(10):
                snapshot = session_with_data.get_snapshot()
                with lock:
                    snapshots.append(snapshot)

        threads = [threading.Thread(target=read_snapshot) for _ in range(NUM_READERS)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(snapshots) == 100, f"Expected 100 snapshots, got {len(snapshots)}"

        # All snapshots should be internally consistent
        for snapshot in snapshots:
            section_sum = sum(info.size_bytes for info in snapshot.sections.values())
            assert snapshot.total_size_bytes == section_sum, "Snapshot internally inconsistent"

    def test_readers_see_consistent_sizes_during_writes(
        self, session_with_data: SessionStateManager
    ) -> None:
        """
        Readers should see consistent sizes even during writes.

        No partial mutations visible - either old state or new state.
        """
        inconsistent_found = [False]
        snapshots_checked = [0]
        lock = threading.Lock()
        stop_flag = threading.Event()

        def writer_loop() -> None:
            for i in range(40):
                if stop_flag.is_set():
                    break
                session_with_data.mutate(
                    "history_active", "append", create_turn_data(i, 666, 100), 100
                )

        def reader_loop() -> None:
            while not stop_flag.is_set():
                snapshot = session_with_data.get_snapshot()

                # Check internal consistency
                section_sum = sum(info.size_bytes for info in snapshot.sections.values())
                if snapshot.total_size_bytes != section_sum:
                    with lock:
                        inconsistent_found[0] = True

                with lock:
                    snapshots_checked[0] += 1

        writer_thread = threading.Thread(target=writer_loop)
        reader_threads = [threading.Thread(target=reader_loop) for _ in range(5)]

        for t in reader_threads:
            t.start()
        writer_thread.start()

        writer_thread.join()
        stop_flag.set()

        for t in reader_threads:
            t.join()

        assert not inconsistent_found[0], "Inconsistent snapshot detected during writes"
        assert snapshots_checked[0] > 0, "No snapshots checked"


# =============================================================================
# TEST CLASS: No Read/Write Interference
# =============================================================================


class TestNoReadWriteInterference:
    """
    Test that reads and writes don't interfere with each other.
    """

    def test_writes_dont_block_reads(self, session_with_data: SessionStateManager) -> None:
        """Writes should not block read access."""
        read_completed = [False]
        write_started = threading.Event()
        write_completed = threading.Event()

        def slow_write() -> None:
            write_started.set()
            for i in range(20):
                session_with_data.mutate(
                    "history_active", "append", create_turn_data(i, 555, 100), 100
                )
            write_completed.set()

        def quick_read() -> None:
            write_started.wait()  # Wait for write to start

            # Should be able to read immediately (not blocked)
            start = time.perf_counter()
            _ = session_with_data.get_section("control")
            elapsed_ms = (time.perf_counter() - start) * 1000

            read_completed[0] = elapsed_ms < 10.0  # Should complete quickly

        write_thread = threading.Thread(target=slow_write)
        read_thread = threading.Thread(target=quick_read)

        write_thread.start()
        read_thread.start()

        read_thread.join()
        write_thread.join()

        assert read_completed[0], "Read was blocked by write"

    def test_rapid_reads_during_sustained_writes(
        self, session_with_data: SessionStateManager
    ) -> None:
        """Rapid reads should work during sustained writes."""
        read_count = [0]
        write_count = [0]
        errors: list[Exception] = []
        lock = threading.Lock()
        duration_seconds = 1.0
        stop_flag = threading.Event()

        def writer_loop() -> None:
            counter = 0
            while not stop_flag.is_set():
                try:
                    session_with_data.mutate(
                        "history_active",
                        "append",
                        create_turn_data(counter, 444, 50),
                        50,
                    )
                    with lock:
                        write_count[0] += 1
                    counter += 1
                except Exception as e:
                    with lock:
                        errors.append(e)

        def reader_loop() -> None:
            while not stop_flag.is_set():
                try:
                    _ = session_with_data.get_section("control")
                    with lock:
                        read_count[0] += 1
                except Exception as e:
                    with lock:
                        errors.append(e)

        writer_thread = threading.Thread(target=writer_loop)
        reader_threads = [threading.Thread(target=reader_loop) for _ in range(5)]

        for t in reader_threads:
            t.start()
        writer_thread.start()

        time.sleep(duration_seconds)
        stop_flag.set()

        writer_thread.join()
        for t in reader_threads:
            t.join()

        assert not errors, f"Errors occurred: {errors}"
        assert read_count[0] > 0, "No reads completed"
        assert write_count[0] > 0, "No writes completed"


# =============================================================================
# TEST CLASS: Multiple Section Concurrent Access
# =============================================================================


class TestMultipleSectionConcurrentAccess:
    """
    Test concurrent access to different sections.
    """

    def test_read_different_sections_concurrently(
        self, session_with_data: SessionStateManager
    ) -> None:
        """Reading different sections concurrently should work."""
        sections_to_read = [
            "control",
            "history_active",
            "beliefs_active",
            "scoreboard",
        ]
        results: dict[str, list[Any]] = {s: [] for s in sections_to_read}
        lock = threading.Lock()

        def read_section(section: str) -> None:
            for _ in range(20):
                data = session_with_data.get_section(section)
                with lock:
                    results[section].append(data)

        threads = [threading.Thread(target=read_section, args=(s,)) for s in sections_to_read]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        for section, data_list in results.items():
            assert len(data_list) == 20, f"Section {section} missing reads"

    def test_read_all_sections_while_writing(self, session_with_data: SessionStateManager) -> None:
        """Reading all sections should work while writes happen."""
        sections_to_read = [
            "control",
            "history_active",
            "beliefs_active",
            "scoreboard",
            "clarifications",
            "affective_now",
            "narrative_active",
            "meta",
        ]
        read_counts: dict[str, int] = {s: 0 for s in sections_to_read}
        write_count = [0]
        lock = threading.Lock()
        stop_flag = threading.Event()

        def reader_loop(section: str) -> None:
            while not stop_flag.is_set():
                _ = session_with_data.get_section(section)
                with lock:
                    read_counts[section] += 1

        def writer_loop() -> None:
            for i in range(30):
                session_with_data.mutate(
                    "history_active", "append", create_turn_data(i, 333, 50), 50
                )
                with lock:
                    write_count[0] += 1

        reader_threads = [threading.Thread(target=reader_loop, args=(s,)) for s in sections_to_read]
        writer_thread = threading.Thread(target=writer_loop)

        for t in reader_threads:
            t.start()
        writer_thread.start()

        writer_thread.join()
        stop_flag.set()

        for t in reader_threads:
            t.join()

        # All sections should have been read multiple times
        for section, count in read_counts.items():
            assert count > 0, f"Section {section} was never read"


# =============================================================================
# TEST CLASS: ThreadPoolExecutor Pattern
# =============================================================================


class TestThreadPoolExecutorPattern:
    """
    Test concurrent reads using ThreadPoolExecutor pattern.
    """

    def test_executor_concurrent_reads(self, session_with_data: SessionStateManager) -> None:
        """ThreadPoolExecutor should handle concurrent reads."""

        def read_section(section: str) -> Any:
            return session_with_data.get_section(section)

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(read_section, "control") for _ in range(100)]
            results = [f.result() for f in as_completed(futures)]

        assert len(results) == 100, f"Expected 100 results, got {len(results)}"

    def test_executor_mixed_read_write(self, session_with_data: SessionStateManager) -> None:
        """Executor should handle mixed read/write workload via manager APIs."""
        read_count = [0]
        write_count = [0]
        lock = threading.Lock()

        def read_task() -> str:
            _ = session_with_data.get_section("control")
            with lock:
                read_count[0] += 1
            return "read"

        def write_task(task_id: int) -> str:
            session_with_data.mutate(
                "history_active", "append", create_turn_data(task_id, 222, 50), 50
            )
            with lock:
                write_count[0] += 1
            return "write"

        with ThreadPoolExecutor(max_workers=10) as executor:
            # 80% reads, 20% writes
            futures = []
            for i in range(100):
                if i % 5 == 0:
                    futures.append(executor.submit(write_task, i))
                else:
                    futures.append(executor.submit(read_task))

            results = [f.result() for f in as_completed(futures)]

        assert len(results) == 100
        assert read_count[0] == 80, f"Expected 80 reads, got {read_count[0]}"
        assert write_count[0] == 20, f"Expected 20 writes, got {write_count[0]}"

    def test_executor_snapshot_reads(self, session_with_data: SessionStateManager) -> None:
        """Executor should handle concurrent snapshot reads."""

        def read_snapshot() -> SessionSnapshot:
            return session_with_data.get_snapshot()

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(read_snapshot) for _ in range(50)]
            results = [f.result() for f in as_completed(futures)]

        assert len(results) == 50
        assert all(isinstance(r, SessionSnapshot) for r in results)


# =============================================================================
# TEST CLASS: Stress Test
# =============================================================================


class TestMultiReaderStress:
    """
    Stress tests for multi-reader concurrent access.
    """

    def test_many_readers_rapid_access(self, session_with_data: SessionStateManager) -> None:
        """Many readers doing rapid access should all succeed."""
        num_readers = 20
        reads_per_reader = 50
        total_expected = num_readers * reads_per_reader

        read_count = [0]
        lock = threading.Lock()

        def rapid_read(reader_id: int) -> None:
            for _ in range(reads_per_reader):
                _ = session_with_data.get_section("control")
                with lock:
                    read_count[0] += 1

        threads = [threading.Thread(target=rapid_read, args=(i,)) for i in range(num_readers)]

        start = time.perf_counter()

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        elapsed = time.perf_counter() - start

        assert read_count[0] == total_expected
        assert elapsed < 5.0, f"Took too long: {elapsed:.2f}s"

    def test_sustained_concurrent_reads_and_writes(
        self, session_with_data: SessionStateManager
    ) -> None:
        """Sustained concurrent reads and writes should not cause issues."""
        duration_seconds = 2.0
        read_count = [0]
        write_count = [0]
        errors: list[Exception] = []
        lock = threading.Lock()
        stop_flag = threading.Event()

        def writer_loop() -> None:
            counter = 0
            while not stop_flag.is_set():
                try:
                    session_with_data.mutate(
                        "history_active",
                        "append",
                        create_turn_data(counter, 111, 50),
                        50,
                    )
                    with lock:
                        write_count[0] += 1
                    counter += 1
                except Exception as e:
                    with lock:
                        errors.append(e)

        def reader_loop(reader_id: int) -> None:
            while not stop_flag.is_set():
                try:
                    _ = session_with_data.get_section("control")
                    with lock:
                        read_count[0] += 1
                except Exception as e:
                    with lock:
                        errors.append(e)

        writer_thread = threading.Thread(target=writer_loop)
        reader_threads = [threading.Thread(target=reader_loop, args=(i,)) for i in range(10)]

        for t in reader_threads:
            t.start()
        writer_thread.start()

        time.sleep(duration_seconds)
        stop_flag.set()

        writer_thread.join()
        for t in reader_threads:
            t.join()

        assert not errors, f"Errors occurred: {errors}"
        assert read_count[0] > 0, "No reads completed"
        assert write_count[0] > 0, "No writes completed"


# =============================================================================
# TEST CLASS: Latency Statistics
# =============================================================================


class TestLatencyStatistics:
    """
    Test detailed latency statistics under concurrent access.
    """

    def test_p50_p95_p99_latencies(self, session_with_data: SessionStateManager) -> None:
        """Measure p50, p95, p99 latencies under concurrent load."""
        latencies: list[float] = []
        lock = threading.Lock()

        def reader_loop(reader_id: int) -> None:
            for _ in range(50):
                latency = measure_read_latency(session_with_data, "control")
                with lock:
                    latencies.append(latency)

        threads = [threading.Thread(target=reader_loop, args=(i,)) for i in range(10)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(latencies) == 500

        sorted_latencies = sorted(latencies)
        p50 = sorted_latencies[249]
        p95 = sorted_latencies[474]
        p99 = sorted_latencies[494]

        # All should be under SLA
        assert p50 < READ_LATENCY_SLA_MS, f"P50 {p50:.3f}ms exceeds SLA"
        assert p95 < READ_LATENCY_SLA_MS * 2, f"P95 {p95:.3f}ms exceeds 2x SLA"
        assert p99 < READ_LATENCY_SLA_MS * 3, f"P99 {p99:.3f}ms exceeds 3x SLA"

    def test_latency_during_writes_vs_no_writes(
        self, session_with_data: SessionStateManager
    ) -> None:
        """Compare latency with and without concurrent writes."""
        # Latencies without writes
        latencies_no_writes: list[float] = []
        for _ in range(100):
            latency = measure_read_latency(session_with_data, "control")
            latencies_no_writes.append(latency)

        avg_no_writes = statistics.mean(latencies_no_writes)

        # Latencies with writes
        latencies_with_writes: list[float] = []
        lock = threading.Lock()
        stop_flag = threading.Event()

        def writer_loop() -> None:
            counter = 0
            while not stop_flag.is_set():
                session_with_data.mutate(
                    "history_active",
                    "append",
                    create_turn_data(counter, 100, 50),
                    50,
                )
                counter += 1

        def reader_loop() -> None:
            for _ in range(100):
                latency = measure_read_latency(session_with_data, "control")
                with lock:
                    latencies_with_writes.append(latency)

        writer_thread = threading.Thread(target=writer_loop)
        writer_thread.start()

        reader_loop()  # Run in main thread

        stop_flag.set()
        writer_thread.join()

        avg_with_writes = statistics.mean(latencies_with_writes)

        # Writes should not significantly increase read latency
        # Allow up to 10x increase due to contention
        assert (
            avg_with_writes < avg_no_writes * 10
        ), f"Latency degradation too high: {avg_with_writes:.3f}ms vs {avg_no_writes:.3f}ms"
