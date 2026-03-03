"""Real component tests for TopicRouter.

Tests route resolution from the actual outbox_routing.yaml contract --
no mocks, no fakes, real TopicRouter against real YAML.

Milestone: M2 Epic 2.15
"""

from __future__ import annotations

import pytest

from k0.ports.topic_router import RouteResult, TopicRouter, UnknownTopicError

# ---------------------------------------------------------------------------
# Fixture: real TopicRouter loaded from the production YAML contract
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def router() -> TopicRouter:
    """Construct a real TopicRouter from the actual outbox_routing.yaml."""
    return TopicRouter()


# ===========================================================================
# Exact route resolution
# ===========================================================================


class TestExactRouteResolution:
    """Verify every exact route defined in outbox_routing.yaml."""

    def test_memory_write_route(self, router: TopicRouter) -> None:
        route = router.resolve("memory.write")
        assert isinstance(route, RouteResult)
        assert route.outbox_driver == "st_epi"
        assert route.bus_topic == "cognitive.memory.write.committed.v1"
        assert route.pipeline == "P02"
        assert route.priority == "NORMAL"
        assert route.inline_body_limit == 4096

    def test_session_snapshot_route(self, router: TopicRouter) -> None:
        route = router.resolve("session.snapshot")
        assert route.outbox_driver == "st_session"
        assert route.bus_topic == "session.snapshot.committed.v1"
        assert route.pipeline is None
        assert route.priority == "HIGH"
        assert route.inline_body_limit == 8192

    def test_beliefs_archive_route(self, router: TopicRouter) -> None:
        route = router.resolve("beliefs.archive")
        assert route.outbox_driver == "st_beliefs"
        assert route.bus_topic == "beliefs.archive.committed.v1"
        assert route.pipeline is None
        assert route.priority == "NORMAL"
        assert route.inline_body_limit == 4096

    def test_history_archive_route(self, router: TopicRouter) -> None:
        route = router.resolve("history.archive")
        assert route.outbox_driver == "st_history"
        assert route.bus_topic == "history.archive.committed.v1"
        assert route.pipeline is None
        assert route.priority == "NORMAL"
        assert route.inline_body_limit == 4096

    def test_plan_committed_route(self, router: TopicRouter) -> None:
        route = router.resolve("plan.committed")
        assert route.outbox_driver == "st_epi"
        assert route.bus_topic == "cognitive.plan.committed.v1"
        assert route.pipeline == "P02"
        assert route.priority == "NORMAL"
        assert route.inline_body_limit == 4096

    def test_sync_delta_route(self, router: TopicRouter) -> None:
        route = router.resolve("sync.delta")
        assert route.outbox_driver == "st_sync"
        assert route.bus_topic == "sync.delta.committed.v1"
        assert route.pipeline == "P07"
        assert route.priority == "HIGH"
        assert route.inline_body_limit == 8192


# ===========================================================================
# Glob route resolution
# ===========================================================================


class TestGlobRouteResolution:
    """Verify glob pattern matching for ifl.* topics."""

    def test_ifl_health_fitbit_hr(self, router: TopicRouter) -> None:
        route = router.resolve("ifl.health.fitbit.hr")
        assert route.outbox_driver == "st_epi"
        assert route.bus_topic == "cognitive.ifl.event.committed.v1"
        assert route.pipeline == "P02"
        assert route.priority == "NORMAL"

    def test_ifl_single_segment(self, router: TopicRouter) -> None:
        """ifl.* glob matches single segment after ifl."""
        route = router.resolve("ifl.weather")
        assert route.outbox_driver == "st_epi"

    def test_ifl_exact_does_not_match(self, router: TopicRouter) -> None:
        """Bare 'ifl' does NOT match 'ifl.*' glob -- requires at least one char after dot."""
        with pytest.raises(UnknownTopicError):
            router.resolve("ifl")


# ===========================================================================
# Unknown topic handling
# ===========================================================================


class TestUnknownTopic:
    """Verify rejection of topics with no matching route."""

    def test_unknown_topic_raises(self, router: TopicRouter) -> None:
        with pytest.raises(UnknownTopicError) as exc_info:
            router.resolve("totally.unknown.topic")
        assert "totally.unknown.topic" in str(exc_info.value)
        assert exc_info.value.topic == "totally.unknown.topic"

    def test_empty_topic_raises(self, router: TopicRouter) -> None:
        with pytest.raises(UnknownTopicError):
            router.resolve("")

    def test_partial_match_not_resolved(self, router: TopicRouter) -> None:
        """'memory' alone does not match 'memory.write'."""
        with pytest.raises(UnknownTopicError):
            router.resolve("memory")

    def test_case_sensitive(self, router: TopicRouter) -> None:
        """Topics are case-sensitive; 'Memory.Write' is unknown."""
        with pytest.raises(UnknownTopicError):
            router.resolve("Memory.Write")


# ===========================================================================
# resolve_or_none
# ===========================================================================


class TestResolveOrNone:
    """Verify the non-raising resolve variant."""

    def test_returns_route_for_known(self, router: TopicRouter) -> None:
        result = router.resolve_or_none("memory.write")
        assert result is not None
        assert result.outbox_driver == "st_epi"

    def test_returns_none_for_unknown(self, router: TopicRouter) -> None:
        result = router.resolve_or_none("does.not.exist")
        assert result is None


# ===========================================================================
# known_routes
# ===========================================================================


class TestKnownRoutes:
    """Verify enumeration of registered exact patterns."""

    def test_known_routes_returns_all_exact(self, router: TopicRouter) -> None:
        routes = router.known_routes()
        expected = {
            "memory.write",
            "session.snapshot",
            "beliefs.archive",
            "history.archive",
            "plan.committed",
            "sync.delta",
        }
        assert set(routes) == expected

    def test_known_routes_excludes_glob(self, router: TopicRouter) -> None:
        """Glob patterns (ifl.*) should NOT appear in known_routes."""
        routes = router.known_routes()
        for r in routes:
            assert "*" not in r


# ===========================================================================
# Priority numeric conversion
# ===========================================================================


class TestPriorityNumeric:
    """Verify priority name to numeric mapping from outbox_routing.yaml."""

    def test_critical(self, router: TopicRouter) -> None:
        assert router.priority_numeric("CRITICAL") == 0

    def test_high(self, router: TopicRouter) -> None:
        assert router.priority_numeric("HIGH") == 1

    def test_normal(self, router: TopicRouter) -> None:
        assert router.priority_numeric("NORMAL") == 2

    def test_low(self, router: TopicRouter) -> None:
        assert router.priority_numeric("LOW") == 3

    def test_unknown_priority_returns_99(self, router: TopicRouter) -> None:
        assert router.priority_numeric("NONEXISTENT") == 99

    def test_ordering_is_correct(self, router: TopicRouter) -> None:
        """CRITICAL < HIGH < NORMAL < LOW (lower = higher priority)."""
        c = router.priority_numeric("CRITICAL")
        h = router.priority_numeric("HIGH")
        n = router.priority_numeric("NORMAL")
        lo = router.priority_numeric("LOW")
        assert c < h < n < lo


# ===========================================================================
# RouteResult immutability
# ===========================================================================


class TestRouteResultProperties:
    """Verify RouteResult is frozen dataclass."""

    def test_frozen(self, router: TopicRouter) -> None:
        route = router.resolve("memory.write")
        with pytest.raises(AttributeError):
            route.outbox_driver = "something_else"  # type: ignore[misc]

    def test_slots(self, router: TopicRouter) -> None:
        route = router.resolve("memory.write")
        assert hasattr(route, "__slots__")
