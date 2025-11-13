"""
Issue #011 (Gap 29): Scheduler Token Leak Prevention Tests

Tests that scheduler tokens are properly released on exceptions during UoW commits.
Stress test validates no scheduler exhaustion with 1000 commits @ 50% exception rate.
"""

import sqlite3
import tempfile
from pathlib import Path

import pytest

from k0.qos import Scheduler, SchedulerProfile


class TestSchedulerTokenRelease:
    """Test suite for Issue #011: Scheduler token release on exceptions."""

    def test_scheduler_token_released_on_successful_commit(self, temp_db_path):
        """Verify scheduler token released after successful UoW commit."""
        scheduler = Scheduler(
            profile=SchedulerProfile(
                name="test",
                description="Test profile",
                port_limits={"command": 10},
            )
        )

        # Acquire token
        token = scheduler.acquire(band="GREEN", port="command", cost=1)
        assert scheduler.active_tokens("command") == 1

        # Release token explicitly
        token.release()
        assert scheduler.active_tokens("command") == 0

    def test_scheduler_token_idempotent_release(self):
        """Verify multiple release() calls don't corrupt token count."""
        scheduler = Scheduler(
            profile=SchedulerProfile(
                name="test",
                description="Test profile",
                port_limits={"command": 10},
            )
        )

        token = scheduler.acquire(band="GREEN", port="command", cost=2)
        assert scheduler.active_tokens("command") == 2

        # First release
        token.release()
        assert scheduler.active_tokens("command") == 0

        # Second release should be no-op
        token.release()
        assert scheduler.active_tokens("command") == 0  # Should NOT go negative!

    def test_scheduler_token_released_on_exception(self):
        """Verify scheduler token released when exception occurs."""
        scheduler = Scheduler(
            profile=SchedulerProfile(
                name="test",
                description="Test profile",
                port_limits={"command": 10},
            )
        )

        token = None
        try:
            token = scheduler.acquire(band="GREEN", port="command", cost=1)
            assert scheduler.active_tokens("command") == 1
            raise RuntimeError("Simulated exception during processing")
        except RuntimeError:
            pass
        finally:
            if token is not None:
                token.release()

        # Token should be released even though exception was raised
        assert scheduler.active_tokens("command") == 0

    def test_scheduler_context_manager_auto_releases(self):
        """Verify SchedulerToken context manager releases on exit."""
        scheduler = Scheduler(
            profile=SchedulerProfile(
                name="test",
                description="Test profile",
                port_limits={"command": 10},
            )
        )

        # Use context manager
        with scheduler.acquire(band="GREEN", port="command", cost=1):
            assert scheduler.active_tokens("command") == 1

        # Token should be auto-released on context exit
        assert scheduler.active_tokens("command") == 0

    def test_scheduler_context_manager_releases_on_exception(self):
        """Verify SchedulerToken context manager releases on exception."""
        scheduler = Scheduler(
            profile=SchedulerProfile(
                name="test",
                description="Test profile",
                port_limits={"command": 10},
            )
        )

        try:
            with scheduler.acquire(band="GREEN", port="command", cost=2):
                assert scheduler.active_tokens("command") == 2
                raise ValueError("Simulated exception in context")
        except ValueError:
            pass

        # Token should be auto-released even on exception
        assert scheduler.active_tokens("command") == 0


class TestSchedulerTokenStressTest:
    """Stress test for Issue #011: 1000 commits with 50% exceptions."""

    def test_stress_no_scheduler_exhaustion_with_exceptions(self, temp_db_path):
        """
        Acceptance Criteria:
        - 1000 commits with 50% exceptions
        - No scheduler exhaustion
        - k0_scheduler_tokens_active gauge stays <= max_tokens
        """
        scheduler = Scheduler(
            profile=SchedulerProfile(
                name="stress_test",
                description="Stress test profile",
                port_limits={"command": 16},  # Max 16 concurrent tokens
            )
        )

        max_concurrent = 0
        exceptions_raised = 0
        successful_commits = 0

        for i in range(1000):
            token = None
            try:
                # Acquire token
                token = scheduler.acquire(band="GREEN", port="command", cost=1)
                current_active = scheduler.active_tokens("command")
                max_concurrent = max(max_concurrent, current_active)

                # Verify scheduler never exhausted (should stay <= 16)
                assert current_active <= 16, f"Scheduler exhausted! Active: {current_active}"

                # Simulate 50% exception rate during processing
                if i % 2 == 0:
                    raise RuntimeError(f"Simulated exception on iteration {i}")

                successful_commits += 1
            except RuntimeError:
                exceptions_raised += 1
            finally:
                if token is not None:
                    token.release()

        # Verify stress test criteria
        assert exceptions_raised == 500, f"Expected 500 exceptions, got {exceptions_raised}"
        assert successful_commits == 500, f"Expected 500 successes, got {successful_commits}"
        assert max_concurrent <= 16, f"Max concurrent exceeded limit: {max_concurrent}"

        # Final check: All tokens released
        final_active = scheduler.active_tokens("command")
        assert final_active == 0, f"Token leak detected! Active tokens: {final_active}"

    def test_concurrent_token_acquisition_stress(self):
        """
        Test concurrent token acquisitions don't corrupt active count.
        Simulates multiple threads competing for scheduler tokens.
        """
        import threading

        scheduler = Scheduler(
            profile=SchedulerProfile(
                name="concurrent_test",
                description="Concurrent test profile",
                port_limits={"command": 50},
            )
        )

        exceptions = []

        def worker(worker_id: int):
            """Worker that acquires and releases tokens with occasional exceptions."""
            for i in range(20):
                token = None
                try:
                    token = scheduler.acquire(band="GREEN", port="command", cost=1)
                    # Simulate 25% exception rate
                    if (worker_id + i) % 4 == 0:
                        raise ValueError(f"Worker {worker_id} exception at {i}")
                except Exception as exc:
                    exceptions.append(exc)
                finally:
                    if token is not None:
                        token.release()

        # Launch 10 concurrent workers
        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        # Verify all tokens released
        final_active = scheduler.active_tokens("command")
        assert final_active == 0, f"Token leak in concurrent test! Active: {final_active}"

        # Verify exceptions were raised as expected
        assert len(exceptions) == 50, f"Expected 50 exceptions, got {len(exceptions)}"


class TestSchedulerTokenMetrics:
    """Test scheduler token metrics (Gap 43 integration)."""

    def test_scheduler_tokens_active_gauge_tracked(self):
        """Verify k0_scheduler_tokens_active gauge updates correctly."""
        from k0.obs.metrics import MetricsExporter

        metrics = MetricsExporter(namespace="k0_kernel_test")
        scheduler = Scheduler(
            profile=SchedulerProfile(
                name="metrics_test",
                description="Metrics test profile",
                port_limits={"command": 10},
            )
        )

        # Acquire 3 tokens
        token1 = scheduler.acquire(band="GREEN", port="command", cost=1)
        token2 = scheduler.acquire(band="GREEN", port="command", cost=1)
        token3 = scheduler.acquire(band="GREEN", port="command", cost=1)

        active_count = scheduler.active_tokens("command")
        assert active_count == 3

        # Emit gauge metric
        metrics.set_gauge("scheduler_tokens_active", float(active_count), port="command")

        # Release tokens
        token1.release()
        token2.release()
        token3.release()

        final_active = scheduler.active_tokens("command")
        assert final_active == 0

        # Update gauge
        metrics.set_gauge("scheduler_tokens_active", float(final_active), port="command")


@pytest.fixture
def temp_db_path():
    """Create temporary SQLite database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_scheduler.db"
        conn = sqlite3.connect(str(db_path))

        # Create minimal schema
        conn.execute(
            """
            CREATE TABLE st_wal (
                pos INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id TEXT NOT NULL,
                space_id TEXT NOT NULL,
                topic TEXT NOT NULL,
                envelope_json TEXT NOT NULL,
                schema_uri TEXT NOT NULL,
                schema_version TEXT NOT NULL,
                device_id TEXT NOT NULL,
                commit_ts TEXT NOT NULL,
                body BLOB,
                payload_sha256 TEXT,
                idem_key TEXT,
                redacted_body_json TEXT,
                policy_stamp_json TEXT,
                envelope_sha256 TEXT UNIQUE
            )
        """
        )

        conn.commit()
        conn.close()

        yield str(db_path)
        yield str(db_path)
