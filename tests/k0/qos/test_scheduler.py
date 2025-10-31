"""Scheduler tests - migrated from ward to pytest."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Lock

import pytest

from k0.qos import Scheduler, SchedulerCapacityError, SchedulerProfile


class TestSchedulerCapacity:
    """Test suite for scheduler capacity enforcement."""

    def test_scheduler_enforces_per_port_capacity(self, configured_scheduler: Scheduler) -> None:
        """Scheduler rejects acquisitions exceeding port limit."""
        token_a = configured_scheduler.acquire(band="GREEN", port="command", cost=1)
        token_b = configured_scheduler.acquire(band="GREEN", port="command", cost=1)
        assert configured_scheduler.active_tokens("command") == 2

        # Port limit is 4, we have 2, try to get 3 more (would exceed)
        with pytest.raises(SchedulerCapacityError) as exc_info:
            configured_scheduler.acquire(band="GREEN", port="command", cost=3)

        assert exc_info.value.port == "command"
        assert exc_info.value.cost == 3
        assert exc_info.value.band == "GREEN"
        # Only 2 capacity remaining (4 limit - 2 active)
        assert exc_info.value.limit == 2

    def test_scheduler_allows_acquisition_within_limit(
        self, configured_scheduler: Scheduler
    ) -> None:
        """Scheduler allows acquisitions within port limit."""
        token = configured_scheduler.acquire(band="GREEN", port="query", cost=4)
        assert token is not None
        assert configured_scheduler.active_tokens("query") == 4

    def test_scheduler_rejects_zero_cost_acquisition(self, configured_scheduler: Scheduler) -> None:
        """Scheduler rejects zero cost acquisitions."""
        with pytest.raises(ValueError, match="cost must be positive"):
            configured_scheduler.acquire(band="GREEN", port="command", cost=0)

    def test_scheduler_rejects_negative_cost_acquisition(
        self, configured_scheduler: Scheduler
    ) -> None:
        """Scheduler rejects negative cost acquisitions."""
        with pytest.raises(ValueError, match="cost must be positive"):
            configured_scheduler.acquire(band="GREEN", port="command", cost=-1)

    def test_scheduler_uses_default_port_limit(self, configured_scheduler: Scheduler) -> None:
        """Scheduler uses default port limit for unknown ports."""
        # configured_scheduler has default_port_limit=4
        # Unknown port "unknown" should use default
        token = configured_scheduler.acquire(band="GREEN", port="unknown", cost=3)
        assert configured_scheduler.active_tokens("unknown") == 3

        with pytest.raises(SchedulerCapacityError):
            configured_scheduler.acquire(band="GREEN", port="unknown", cost=2)


class TestSchedulerTokenRelease:
    """Test suite for token release and refunding."""

    def test_token_release_frees_capacity(self, configured_scheduler: Scheduler) -> None:
        """Released token frees scheduler capacity."""
        token = configured_scheduler.acquire(band="GREEN", port="command", cost=2)
        assert configured_scheduler.active_tokens("command") == 2

        token.release()
        assert configured_scheduler.active_tokens("command") == 0

    def test_multiple_token_releases(self, configured_scheduler: Scheduler) -> None:
        """Multiple tokens released correctly refund capacity."""
        token_a = configured_scheduler.acquire(band="GREEN", port="query", cost=2)
        token_b = configured_scheduler.acquire(band="GREEN", port="query", cost=3)
        assert configured_scheduler.active_tokens("query") == 5

        token_a.release()
        assert configured_scheduler.active_tokens("query") == 3

        token_b.release()
        assert configured_scheduler.active_tokens("query") == 0

    def test_token_double_release_idempotent(self, configured_scheduler: Scheduler) -> None:
        """Releasing a token twice is idempotent (safe no-op)."""
        token = configured_scheduler.acquire(band="GREEN", port="command", cost=2)
        token.release()
        assert configured_scheduler.active_tokens("command") == 0

        # Second release should be no-op
        token.release()
        assert configured_scheduler.active_tokens("command") == 0

    def test_token_context_manager_releases_on_success(
        self, configured_scheduler: Scheduler
    ) -> None:
        """Token used as context manager releases on normal exit."""
        with configured_scheduler.acquire(band="GREEN", port="command", cost=1):
            assert configured_scheduler.active_tokens("command") == 1

        assert configured_scheduler.active_tokens("command") == 0

    def test_token_context_manager_releases_on_exception(
        self, configured_scheduler: Scheduler
    ) -> None:
        """Token released even if exception raised in context manager."""
        try:
            with configured_scheduler.acquire(band="GREEN", port="command", cost=2):
                assert configured_scheduler.active_tokens("command") == 2
                raise RuntimeError("test error")
        except RuntimeError:
            pass

        assert configured_scheduler.active_tokens("command") == 0


class TestSchedulerTightening:
    """Test suite for scheduler profile tightening."""

    def test_scheduler_tighten_applies_new_limits(
        self, configured_scheduler: Scheduler, hardened_profile: SchedulerProfile
    ) -> None:
        """Tightening applies new port limits."""
        # Original: command limit = 4
        assert configured_scheduler.profile.port_limits["command"] == 4

        # Apply hardened profile: command limit = 2
        configured_scheduler.tighten(hardened_profile)
        assert configured_scheduler.profile.port_limits["command"] == 2

    def test_scheduler_tighten_clamps_active_tokens(
        self, configured_scheduler: Scheduler, hardened_profile: SchedulerProfile
    ) -> None:
        """Tightening clamps active token counts to new limits."""
        # Acquire 4 tokens at command (limit is 4)
        tokens = [
            configured_scheduler.acquire(band="GREEN", port="command", cost=1) for _ in range(4)
        ]
        assert configured_scheduler.active_tokens("command") == 4

        # Tighten to limit 2 (should clamp active to 2)
        configured_scheduler.tighten(hardened_profile)
        assert configured_scheduler.active_tokens("command") == 2

    def test_scheduler_tighten_prevents_new_acquisitions_above_limit(
        self, configured_scheduler: Scheduler, hardened_profile: SchedulerProfile
    ) -> None:
        """After tightening, new acquisitions respect tighter limit."""
        tokens = [
            configured_scheduler.acquire(band="GREEN", port="command", cost=1) for _ in range(4)
        ]

        configured_scheduler.tighten(hardened_profile)
        # Limit now 2, active is clamped to 2
        with pytest.raises(SchedulerCapacityError):
            configured_scheduler.acquire(band="GREEN", port="command", cost=1)

    def test_scheduler_tighten_preserves_tokens(
        self, configured_scheduler: Scheduler, hardened_profile: SchedulerProfile
    ) -> None:
        """Released tokens from before tightening still work."""
        token_a = configured_scheduler.acquire(band="GREEN", port="command", cost=1)
        token_b = configured_scheduler.acquire(band="GREEN", port="command", cost=1)

        configured_scheduler.tighten(hardened_profile)

        # Release token_a
        token_a.release()
        assert configured_scheduler.active_tokens("command") == 1

        # Release token_b
        token_b.release()
        assert configured_scheduler.active_tokens("command") == 0

    def test_scheduler_tighten_multiple_ports(
        self, configured_scheduler: Scheduler, hardened_profile: SchedulerProfile
    ) -> None:
        """Tightening applies to multiple ports simultaneously."""
        # Acquire on multiple ports
        t_cmd = configured_scheduler.acquire(band="GREEN", port="command", cost=2)
        t_qry = configured_scheduler.acquire(band="GREEN", port="query", cost=4)
        t_sse = configured_scheduler.acquire(band="GREEN", port="sse", cost=1)

        configured_scheduler.tighten(hardened_profile)

        # All ports should be clamped
        assert configured_scheduler.active_tokens("command") == 2  # min(2, 2)
        assert configured_scheduler.active_tokens("query") == 3  # min(4, 3)
        assert configured_scheduler.active_tokens("sse") == 1  # min(1, 1)

        t_cmd.release()
        t_qry.release()
        t_sse.release()

    def test_scheduler_tighten_zero_limit(self, configured_scheduler: Scheduler) -> None:
        """Tightening to zero limit prevents all acquisitions."""
        zero_profile = SchedulerProfile(
            name="zero",
            description="Zero capacity",
            port_limits={"command": 0},
            default_port_limit=0,
        )

        configured_scheduler.tighten(zero_profile)

        with pytest.raises(SchedulerCapacityError):
            configured_scheduler.acquire(band="GREEN", port="command", cost=1)


class TestSchedulerBandIsolation:
    """Test suite for band isolation (if applicable)."""

    def test_scheduler_accepts_multiple_bands(self, configured_scheduler: Scheduler) -> None:
        """Scheduler tracks tokens across different bands."""
        token_green = configured_scheduler.acquire(band="GREEN", port="command", cost=1)
        token_amber = configured_scheduler.acquire(band="AMBER", port="command", cost=1)

        # Both should consume from same port capacity
        assert configured_scheduler.active_tokens("command") == 2

        token_green.release()
        token_amber.release()
        assert configured_scheduler.active_tokens("command") == 0


class TestSchedulerThreadSafety:
    """Test suite for scheduler thread safety."""

    def test_scheduler_concurrent_acquisitions(self, configured_scheduler: Scheduler) -> None:
        """Scheduler handles concurrent acquisitions safely."""
        acquired_tokens = []
        errors = []
        lock = Lock()

        def acquire_token() -> None:
            try:
                token = configured_scheduler.acquire(band="GREEN", port="query", cost=1)
                with lock:
                    acquired_tokens.append(token)
            except SchedulerCapacityError as e:
                with lock:
                    errors.append(e)

        # Query port limit is 8, try to acquire 10 tokens concurrently
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(acquire_token) for _ in range(10)]
            for f in futures:
                f.result()

        # Should have 8 successful acquisitions, 2 failures
        assert len(acquired_tokens) == 8
        assert len(errors) == 2

        # Clean up
        for token in acquired_tokens:
            token.release()

        assert configured_scheduler.active_tokens("query") == 0

    def test_scheduler_concurrent_release(self, configured_scheduler: Scheduler) -> None:
        """Scheduler handles concurrent releases safely."""
        tokens = [
            configured_scheduler.acquire(band="GREEN", port="command", cost=1) for _ in range(4)
        ]
        assert configured_scheduler.active_tokens("command") == 4

        # Release all tokens concurrently
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(token.release) for token in tokens]
            for f in futures:
                f.result()

        assert configured_scheduler.active_tokens("command") == 0


class TestSchedulerActiveTokensCounting:
    """Test suite for active token counting."""

    def test_active_tokens_unknown_port_returns_zero(self, configured_scheduler: Scheduler) -> None:
        """Active tokens for unknown port returns 0."""
        assert configured_scheduler.active_tokens("nonexistent_port") == 0

    def test_active_tokens_after_complete_release(self, configured_scheduler: Scheduler) -> None:
        """Active tokens returns 0 after all tokens released."""
        token = configured_scheduler.acquire(band="GREEN", port="command", cost=2)
        assert configured_scheduler.active_tokens("command") == 2

        token.release()
        assert configured_scheduler.active_tokens("command") == 0

    def test_active_tokens_partial_consumption(self, configured_scheduler: Scheduler) -> None:
        """Active tokens reflects partial consumption correctly."""
        t1 = configured_scheduler.acquire(band="GREEN", port="query", cost=2)
        assert configured_scheduler.active_tokens("query") == 2

        t2 = configured_scheduler.acquire(band="GREEN", port="query", cost=3)
        assert configured_scheduler.active_tokens("query") == 5

        t1.release()
        assert configured_scheduler.active_tokens("query") == 3
        assert configured_scheduler.active_tokens("query") == 3
