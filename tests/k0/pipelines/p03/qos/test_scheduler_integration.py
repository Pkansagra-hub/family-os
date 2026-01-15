"""
Tests for P03SchedulerIntegration.

Issue 6.4.1: Token-based resource management for P03 operations.
"""

from __future__ import annotations

import pytest

from k0.pipelines.p03.qos.scheduler_integration import (
    P03_SCHEDULER_PROFILES,
    P03SchedulerIntegration,
    P03SchedulerProfile,
)
from k0.qos.scheduler import Scheduler, SchedulerCapacityError, SchedulerProfile


class TestP03SchedulerProfile:
    """Tests for P03SchedulerProfile dataclass."""

    def test_profile_creation(self) -> None:
        """Profile is created with correct defaults."""
        profile = P03SchedulerProfile(
            name="TEST",
            description="Test profile",
        )
        assert profile.name == "TEST"
        assert profile.description == "Test profile"
        assert profile.port == "command"
        assert profile.base_cost == 10
        assert profile.cost_per_event == 0.1

    def test_profile_custom_values(self) -> None:
        """Profile accepts custom values."""
        profile = P03SchedulerProfile(
            name="CUSTOM",
            description="Custom profile",
            port="query",
            base_cost=5,
            cost_per_event=0.2,
        )
        assert profile.port == "query"
        assert profile.base_cost == 5
        assert profile.cost_per_event == 0.2

    def test_profile_is_frozen(self) -> None:
        """Profile is immutable (frozen)."""
        profile = P03SchedulerProfile(name="TEST", description="Test")
        with pytest.raises(AttributeError):
            profile.name = "MODIFIED"  # type: ignore[misc]


class TestP03SchedulerProfiles:
    """Tests for P03_SCHEDULER_PROFILES constant."""

    def test_batch_consolidation_profile(self) -> None:
        """BATCH_CONSOLIDATION profile exists with correct config."""
        profile = P03_SCHEDULER_PROFILES["BATCH_CONSOLIDATION"]
        assert profile.name == "BATCH_CONSOLIDATION"
        assert profile.port == "command"
        assert profile.base_cost == 10
        assert profile.cost_per_event == 0.1

    def test_similarity_search_profile(self) -> None:
        """SIMILARITY_SEARCH profile exists with correct config."""
        profile = P03_SCHEDULER_PROFILES["SIMILARITY_SEARCH"]
        assert profile.name == "SIMILARITY_SEARCH"
        assert profile.port == "query"
        assert profile.base_cost == 5
        assert profile.cost_per_event == 0.05

    def test_dream_exploration_profile(self) -> None:
        """DREAM_EXPLORATION profile exists with correct config."""
        profile = P03_SCHEDULER_PROFILES["DREAM_EXPLORATION"]
        assert profile.name == "DREAM_EXPLORATION"
        assert profile.port == "command"
        assert profile.base_cost == 20
        assert profile.cost_per_event == 0.2

    def test_all_profiles_exist(self) -> None:
        """All expected profiles are defined."""
        expected = {"BATCH_CONSOLIDATION", "SIMILARITY_SEARCH", "DREAM_EXPLORATION"}
        assert set(P03_SCHEDULER_PROFILES.keys()) == expected


class TestP03SchedulerIntegration:
    """Tests for P03SchedulerIntegration class."""

    @pytest.fixture
    def scheduler(self) -> Scheduler:
        """Create K0 Scheduler with default profile."""
        profile = SchedulerProfile(
            name="test",
            description="Test scheduler",
            port_limits={"command": 100, "query": 100, "sse": 50},
            default_port_limit=50,
        )
        return Scheduler(profile=profile)

    @pytest.fixture
    def integration(self, scheduler: Scheduler) -> P03SchedulerIntegration:
        """Create P03SchedulerIntegration instance."""
        return P03SchedulerIntegration(
            scheduler=scheduler,
            qos_metrics=None,
            pipeline_id="test_p03",
        )

    def test_init(self, scheduler: Scheduler) -> None:
        """Integration initializes correctly."""
        integration = P03SchedulerIntegration(scheduler=scheduler)
        assert integration.scheduler is scheduler
        assert integration.pipeline_id == "p03_consolidation"

    def test_custom_pipeline_id(self, scheduler: Scheduler) -> None:
        """Integration accepts custom pipeline_id."""
        integration = P03SchedulerIntegration(
            scheduler=scheduler,
            pipeline_id="custom_p03",
        )
        assert integration.pipeline_id == "custom_p03"

    def test_acquire_batch_token_success(self, integration: P03SchedulerIntegration) -> None:
        """acquire_batch_token returns valid token."""
        token = integration.acquire_batch_token(batch_size=100, band="GREEN")
        assert token is not None
        assert token.port == "command"
        assert token.cost == 20  # 10 + 100 * 0.1

    def test_acquire_batch_token_releases_on_context(
        self, integration: P03SchedulerIntegration
    ) -> None:
        """Token releases when used as context manager."""
        with integration.acquire_batch_token(batch_size=50, band="AMBER") as token:
            assert token.port == "command"
            active = integration.get_active_tokens("command")
            assert active == token.cost

        # After context exit, token should be released
        active_after = integration.get_active_tokens("command")
        assert active_after == 0

    def test_acquire_batch_token_amber_band(self, integration: P03SchedulerIntegration) -> None:
        """Amber band acquisition works."""
        token = integration.acquire_batch_token(batch_size=100, band="AMBER")
        assert token is not None
        token.release()

    def test_acquire_batch_token_red_band(self, integration: P03SchedulerIntegration) -> None:
        """Red band acquisition works."""
        token = integration.acquire_batch_token(batch_size=100, band="RED")
        assert token is not None
        token.release()

    def test_acquire_batch_token_unknown_profile_fallback(
        self, integration: P03SchedulerIntegration
    ) -> None:
        """Unknown profile falls back to BATCH_CONSOLIDATION."""
        token = integration.acquire_batch_token(
            batch_size=100,
            band="GREEN",
            profile_name="UNKNOWN_PROFILE",
        )
        assert token is not None
        assert token.port == "command"  # BATCH_CONSOLIDATION port
        token.release()

    def test_acquire_query_token(self, integration: P03SchedulerIntegration) -> None:
        """acquire_query_token returns valid token."""
        token = integration.acquire_query_token(query_count=10, band="AMBER")
        assert token is not None
        assert token.port == "query"
        # Cost: max(1, 5 + int(10 * 0.05)) = max(1, 5 + 0) = 5
        assert token.cost == 5
        token.release()

    def test_acquire_dream_token(self, integration: P03SchedulerIntegration) -> None:
        """acquire_dream_token returns valid token."""
        token = integration.acquire_dream_token(batch_size=100, band="GREEN")
        assert token is not None
        assert token.port == "command"
        assert token.cost == 40  # 20 + 100 * 0.2
        token.release()

    def test_release_token_explicit(self, integration: P03SchedulerIntegration) -> None:
        """Explicit release_token works."""
        token = integration.acquire_batch_token(batch_size=50, band="GREEN")
        active = integration.get_active_tokens("command")
        assert active > 0

        integration.release_token(token)
        active_after = integration.get_active_tokens("command")
        assert active_after == 0

    def test_get_active_tokens(self, integration: P03SchedulerIntegration) -> None:
        """get_active_tokens returns correct count."""
        assert integration.get_active_tokens("command") == 0

        token1 = integration.acquire_batch_token(batch_size=100, band="GREEN")
        assert integration.get_active_tokens("command") == token1.cost

        token2 = integration.acquire_batch_token(batch_size=50, band="GREEN")
        expected = token1.cost + token2.cost
        assert integration.get_active_tokens("command") == expected

        token1.release()
        token2.release()

    def test_get_contention_factor_low(self, integration: P03SchedulerIntegration) -> None:
        """Low contention returns 1.0."""
        factor = integration.get_contention_factor()
        assert factor == 1.0

    def test_get_contention_factor_medium(self, integration: P03SchedulerIntegration) -> None:
        """Medium contention returns 0.75."""
        # Need active tokens > 5 and <= 10
        # batch_size=0 gives cost = max(1, 10 + 0) = 10
        # 10 active tokens is at boundary (> 5, <= 10) -> 0.75
        token = integration.acquire_batch_token(batch_size=0, band="GREEN")
        assert token.cost == 10  # base_cost only
        factor = integration.get_contention_factor()
        assert factor == 0.75
        token.release()

    def test_get_contention_factor_high(self, integration: P03SchedulerIntegration) -> None:
        """High contention returns 0.5."""
        # Need active tokens > 10
        # batch_size=10 gives cost = 10 + int(10 * 0.1) = 10 + 1 = 11
        token = integration.acquire_batch_token(batch_size=10, band="GREEN")
        assert token.cost == 11  # > 10
        factor = integration.get_contention_factor()
        assert factor == 0.5
        token.release()

    def test_cost_calculation_minimum(self, integration: P03SchedulerIntegration) -> None:
        """Cost is at least 1."""
        token = integration.acquire_batch_token(batch_size=0, band="GREEN")
        assert token.cost >= 1
        token.release()


class TestSchedulerCapacity:
    """Tests for scheduler capacity limits."""

    @pytest.fixture
    def limited_scheduler(self) -> Scheduler:
        """Create scheduler with low capacity."""
        profile = SchedulerProfile(
            name="limited",
            description="Limited capacity",
            port_limits={"command": 20},
            default_port_limit=10,
        )
        return Scheduler(profile=profile)

    @pytest.fixture
    def integration(self, limited_scheduler: Scheduler) -> P03SchedulerIntegration:
        """Create integration with limited scheduler."""
        return P03SchedulerIntegration(scheduler=limited_scheduler)

    def test_capacity_exceeded_raises(self, integration: P03SchedulerIntegration) -> None:
        """Exceeding capacity raises SchedulerCapacityError."""
        # First acquisition should succeed
        token = integration.acquire_batch_token(batch_size=100, band="GREEN")
        assert token.cost == 20  # 10 + 100 * 0.1

        # Second should fail (already at limit)
        with pytest.raises(SchedulerCapacityError) as exc_info:
            integration.acquire_batch_token(batch_size=100, band="GREEN")

        assert exc_info.value.port == "command"
        token.release()

    def test_release_allows_reacquire(self, integration: P03SchedulerIntegration) -> None:
        """Releasing token allows new acquisition."""
        token1 = integration.acquire_batch_token(batch_size=100, band="GREEN")
        token1.release()

        # Should succeed after release
        token2 = integration.acquire_batch_token(batch_size=100, band="GREEN")
        assert token2 is not None
        token2.release()
