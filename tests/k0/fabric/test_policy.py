"""
Tests for ContextPolicyEnforcer.

Issue 2.1.5: Fabric Context Policy Enforcement

Coverage:
- INHERIT policy (capability intersection)
- ISOLATED policy (returns None)
- SYNTHETIC policy (minimal trace-only context)
- Capability extraction from various formats
- Statistics gathering
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from k0.fabric.policy import (
    ContextPolicyEnforcer,
    get_context_policy_enforcer,
    reset_context_policy_enforcer,
)


@pytest.fixture(autouse=True)
def reset_enforcer():
    """Reset global enforcer before and after each test."""
    reset_context_policy_enforcer()
    yield
    reset_context_policy_enforcer()


@dataclass
class MockContext:
    """Mock PipelineContext for testing."""

    capabilities: set[str] | None = None
    trace_id: str | None = None
    logger: Any = None
    syscalls: Any = None
    config: dict[str, Any] | None = None


class TestInheritPolicy:
    """Tests for INHERIT context policy."""

    def test_inherit_policy_intersects_capabilities(self) -> None:
        """INHERIT policy returns intersection of caller and provider caps."""
        enforcer = ContextPolicyEnforcer()

        caller_ctx = MockContext(
            capabilities={"cap_a", "cap_b", "cap_c"},
            trace_id="trace-123",
        )
        provider_caps = {"cap_b", "cap_c", "cap_d"}

        result = enforcer.enforce(caller_ctx, "inherit", provider_caps)

        # Should have intersection: {cap_b, cap_c}
        assert result is not None
        assert result.capabilities == {"cap_b", "cap_c"}

    def test_inherit_policy_empty_caller_caps(self) -> None:
        """INHERIT with empty caller caps returns empty effective caps."""
        enforcer = ContextPolicyEnforcer()

        caller_ctx = MockContext(capabilities=set(), trace_id="trace-123")
        provider_caps = {"cap_a", "cap_b"}

        result = enforcer.enforce(caller_ctx, "inherit", provider_caps)

        assert result is not None
        assert result.capabilities == set()

    def test_inherit_policy_empty_provider_caps(self) -> None:
        """INHERIT with empty provider caps returns empty effective caps."""
        enforcer = ContextPolicyEnforcer()

        caller_ctx = MockContext(
            capabilities={"cap_a", "cap_b"},
            trace_id="trace-123",
        )
        provider_caps: set[str] = set()

        result = enforcer.enforce(caller_ctx, "inherit", provider_caps)

        assert result is not None
        assert result.capabilities == set()

    def test_inherit_policy_no_overlap(self) -> None:
        """INHERIT with no overlapping caps returns empty effective caps."""
        enforcer = ContextPolicyEnforcer()

        caller_ctx = MockContext(
            capabilities={"cap_a", "cap_b"},
            trace_id="trace-123",
        )
        provider_caps = {"cap_x", "cap_y"}

        result = enforcer.enforce(caller_ctx, "inherit", provider_caps)

        assert result is not None
        assert result.capabilities == set()

    def test_inherit_policy_preserves_trace_id(self) -> None:
        """INHERIT policy preserves trace_id for auditing."""
        enforcer = ContextPolicyEnforcer()

        caller_ctx = MockContext(
            capabilities={"cap_a"},
            trace_id="trace-xyz",
        )
        provider_caps = {"cap_a"}

        result = enforcer.enforce(caller_ctx, "inherit", provider_caps)

        assert result is not None
        assert result.trace_id == "trace-xyz"


class TestIsolatedPolicy:
    """Tests for ISOLATED context policy."""

    def test_isolated_policy_returns_none(self) -> None:
        """ISOLATED policy returns None (no context inheritance)."""
        enforcer = ContextPolicyEnforcer()

        caller_ctx = MockContext(
            capabilities={"cap_a", "cap_b"},
            trace_id="trace-123",
        )
        provider_caps = {"cap_a"}

        result = enforcer.enforce(caller_ctx, "isolated", provider_caps)

        assert result is None

    def test_isolated_policy_case_insensitive(self) -> None:
        """ISOLATED policy is case-insensitive."""
        enforcer = ContextPolicyEnforcer()

        caller_ctx = MockContext(capabilities={"cap_a"})

        assert enforcer.enforce(caller_ctx, "ISOLATED", set()) is None
        assert enforcer.enforce(caller_ctx, "Isolated", set()) is None
        assert enforcer.enforce(caller_ctx, "isolated", set()) is None


class TestSyntheticPolicy:
    """Tests for SYNTHETIC context policy."""

    def test_synthetic_policy_creates_minimal_context(self) -> None:
        """SYNTHETIC policy creates minimal context."""
        enforcer = ContextPolicyEnforcer()

        caller_ctx = MockContext(
            capabilities={"cap_a", "cap_b"},
            trace_id="trace-123",
            syscalls="some_syscalls",
        )
        provider_caps = {"cap_a"}

        result = enforcer.enforce(caller_ctx, "synthetic", provider_caps)

        # Should return a PipelineContext with minimal fields
        assert result is not None
        assert result.syscalls is None  # No syscalls in synthetic
        assert result.config == {}
        assert result.bus_dispatcher is None
        assert result.fabric is None


class TestCapabilityExtraction:
    """Tests for capability extraction from various formats."""

    def test_extract_capabilities_from_set(self) -> None:
        """Extracts capabilities from set."""
        enforcer = ContextPolicyEnforcer()

        ctx = MockContext(capabilities={"a", "b", "c"})
        caps = enforcer._get_capabilities(ctx)

        assert caps == {"a", "b", "c"}

    def test_extract_capabilities_from_list(self) -> None:
        """Extracts capabilities from list."""
        enforcer = ContextPolicyEnforcer()

        @dataclass
        class CtxWithList:
            capabilities: list[str] | None = None

        ctx = CtxWithList(capabilities=["a", "b", "c"])
        caps = enforcer._get_capabilities(ctx)

        assert caps == {"a", "b", "c"}

    def test_extract_capabilities_from_frozenset(self) -> None:
        """Extracts capabilities from frozenset."""
        enforcer = ContextPolicyEnforcer()

        @dataclass
        class CtxWithFrozen:
            capabilities: frozenset[str] | None = None

        ctx = CtxWithFrozen(capabilities=frozenset(["a", "b"]))
        caps = enforcer._get_capabilities(ctx)

        assert caps == {"a", "b"}

    def test_extract_capabilities_none(self) -> None:
        """Returns empty set when capabilities is None."""
        enforcer = ContextPolicyEnforcer()

        ctx = MockContext(capabilities=None)
        caps = enforcer._get_capabilities(ctx)

        assert caps == set()

    def test_extract_capabilities_missing_attribute(self) -> None:
        """Returns empty set when no capabilities attribute."""
        enforcer = ContextPolicyEnforcer()

        @dataclass
        class NoCapabilities:
            other: str = "value"

        ctx = NoCapabilities()
        caps = enforcer._get_capabilities(ctx)

        assert caps == set()


class TestUnknownPolicy:
    """Tests for unknown policy handling."""

    def test_unknown_policy_defaults_to_isolated(self) -> None:
        """Unknown policy defaults to ISOLATED (secure by default)."""
        enforcer = ContextPolicyEnforcer()

        caller_ctx = MockContext(capabilities={"cap_a"})

        result = enforcer.enforce(caller_ctx, "unknown_policy", {"cap_a"})

        # Should default to isolated (returns None)
        assert result is None


class TestNoneContext:
    """Tests for None caller context."""

    def test_none_context_returns_none(self) -> None:
        """None caller context returns None regardless of policy."""
        enforcer = ContextPolicyEnforcer()

        assert enforcer.enforce(None, "inherit", {"cap_a"}) is None
        assert enforcer.enforce(None, "isolated", {"cap_a"}) is None
        assert enforcer.enforce(None, "synthetic", {"cap_a"}) is None


class TestPolicyStats:
    """Tests for policy statistics."""

    def test_get_stats_inherit_policy(self) -> None:
        """Stats show capability counts for INHERIT policy."""
        enforcer = ContextPolicyEnforcer()

        caller_ctx = MockContext(capabilities={"a", "b", "c"})
        provider_caps = {"b", "c", "d"}

        stats = enforcer.get_stats(caller_ctx, "inherit", provider_caps)

        assert stats["caller_caps_count"] == 3
        assert stats["effective_caps_count"] == 2  # intersection: {b, c}

    def test_get_stats_isolated_policy(self) -> None:
        """Stats show zero effective for ISOLATED policy."""
        enforcer = ContextPolicyEnforcer()

        caller_ctx = MockContext(capabilities={"a", "b"})

        stats = enforcer.get_stats(caller_ctx, "isolated", {"a"})

        assert stats["caller_caps_count"] == 2
        assert stats["effective_caps_count"] == 0

    def test_get_stats_none_context(self) -> None:
        """Stats show zeros for None context."""
        enforcer = ContextPolicyEnforcer()

        stats = enforcer.get_stats(None, "inherit", {"a"})

        assert stats["caller_caps_count"] == 0
        assert stats["effective_caps_count"] == 0


class TestGlobalEnforcer:
    """Tests for global enforcer singleton."""

    def test_get_enforcer_returns_same_instance(self) -> None:
        """get_context_policy_enforcer returns same instance."""
        enforcer1 = get_context_policy_enforcer()
        enforcer2 = get_context_policy_enforcer()

        assert enforcer1 is enforcer2

    def test_reset_clears_enforcer(self) -> None:
        """reset_context_policy_enforcer clears singleton."""
        enforcer1 = get_context_policy_enforcer()
        reset_context_policy_enforcer()
        enforcer2 = get_context_policy_enforcer()

        assert enforcer1 is not enforcer2
