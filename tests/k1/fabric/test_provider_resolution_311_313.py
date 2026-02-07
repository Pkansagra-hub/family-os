"""
Integration tests for Provider Resolution Engine (Epic 3.1, issues 3.1.1-3.1.3).

Tests:
  3.1.1 -- ProviderRegistry (maps provider_id to ProviderConfig)
  3.1.2 -- ProviderMatcher (finds providers that fulfill a contract)
  3.1.3 -- ProviderSelector (deterministic selection per FAB-10)

Covers:
  ProviderRegistry:
    - register_provider / unregister_provider lifecycle
    - Duplicate provider_id -> DuplicateProviderError
    - Empty provider_id -> ValueError
    - lookup_provider, contains, list_by_type, list_all, list_ids, size
    - health_check initial state (UNKNOWN)
    - update_health with valid / invalid status
    - update_health -> ProviderNotFoundError for unknown id
    - list_healthy_providers
    - Event emission: registered, unregistered, health_changed
    - Thread-safety smoke test (concurrent register)

  ProviderMatcher:
    - match: valid provider_id returns single config
    - match: unknown provider_id returns empty list
    - match: UNHEALTHY provider filtered out
    - match: include_unhealthy=True bypasses health filter
    - match: prompt contract (no provider_id) returns []
    - match_or_raise: happy path
    - match_or_raise: NoProviderError on miss

  ProviderSelector:
    - select: single candidate
    - select: highest score wins
    - select: deterministic tie-breaking same score -> lower latency
    - select: deterministic tie-breaking same score + latency -> alphabetical id
    - select: NoCandidatesError on empty list
    - select: AllProvidersRejectedError when all allowed=False
    - select: mixed allowed/rejected -> filters correctly
    - select_top_n: returns top N ordered
    - FAB-10: repeated select is deterministic (100 iterations)
"""

from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional

import pytest

from k1.fabric.provider_resolution.provider_matcher import (
    NoProviderError,
    ProviderMatcher,
    ProviderMatcherError,
)
from k1.fabric.provider_resolution.provider_registry import (
    EVENT_PROVIDER_HEALTH_CHANGED,
    EVENT_PROVIDER_REGISTERED,
    EVENT_PROVIDER_UNREGISTERED,
    DuplicateProviderError,
    ProviderNotFoundError,
    ProviderRegistry,
    ProviderRegistryError,
)
from k1.fabric.provider_resolution.provider_selector import (
    AllProvidersRejectedError,
    NoCandidatesError,
    ProviderSelector,
    ProviderSelectorError,
    ScoredCandidate,
)
from k1.fabric.types import (
    Availability,
    CapabilityContract,
    InputSpec,
    PolicyResult,
    PromptContract,
    ProviderConfig,
    ProviderStatus,
    ProviderType,
    ResolvedProvider,
)

# =========================================================================
# Test Helpers
# =========================================================================


class FakeEventPort:
    """Captures emitted events for assertion."""

    def __init__(self) -> None:
        self.events: List[Dict[str, Any]] = []

    def emit(self, event_type: str, payload: Dict[str, Any]) -> None:
        self.events.append({"event_type": event_type, "payload": payload})


def _config(
    provider_id: str = "mcp-weather",
    provider_type: str = ProviderType.MCP.value,
    endpoint: Optional[str] = "http://localhost:8080",
    max_concurrent: int = 10,
    max_execution_ms: int = 30000,
) -> ProviderConfig:
    """Build a minimal ProviderConfig."""
    return ProviderConfig(
        provider_id=provider_id,
        provider_type=provider_type,
        endpoint=endpoint,
        max_concurrent=max_concurrent,
        max_execution_ms=max_execution_ms,
    )


def _tool(
    name: str = "tool.execute.weather",
    provider_id: str = "mcp-weather",
    avg_latency_ms: int = 50,
) -> CapabilityContract:
    """Build a minimal valid tool contract."""
    return CapabilityContract(
        name=name,
        version="1.0.0",
        domain=["WEATHER"],
        description="Weather tool",
        capabilities=["weather_lookup"],
        limitations=["none"],
        required_inputs=[InputSpec(name="loc", type="string", description="Location")],
        provider_type="MCP",
        provider_id=provider_id,
        safety_band_min="GREEN",
        availability=Availability.ONLINE.value,
        avg_latency_ms=avg_latency_ms,
    )


def _prompt(name: str = "greeting_v1") -> PromptContract:
    """Build a minimal prompt contract (no provider_id)."""
    return PromptContract(
        name=name,
        version="1.0.0",
        domain=["SOCIAL"],
        description="Greeting prompt",
        template_file="greeting.txt",
        variables=[],
        max_tokens=100,
    )


def _scored(
    provider_id: str = "mcp-weather",
    score: float = 0.8,
    allowed: bool = True,
    avg_latency_ms: int = 50,
    reasons: Optional[List[str]] = None,
) -> ScoredCandidate:
    """Build a ScoredCandidate for selector tests."""
    return ScoredCandidate(
        provider_config=_config(provider_id=provider_id),
        contract=_tool(provider_id=provider_id, avg_latency_ms=avg_latency_ms),
        policy_result=PolicyResult(
            allowed=allowed,
            score=score,
            reasons=reasons or [],
        ),
    )


# =========================================================================
# 3.1.1 -- ProviderRegistry Tests
# =========================================================================


class TestProviderRegistryRegisterUnregister:
    """Registration and unregistration lifecycle."""

    def test_register_and_lookup(self) -> None:
        reg = ProviderRegistry()
        cfg = _config(provider_id="p1")
        reg.register_provider("p1", cfg)

        assert reg.contains("p1")
        assert reg.lookup_provider("p1") is cfg
        assert reg.size == 1

    def test_register_multiple(self) -> None:
        reg = ProviderRegistry()
        reg.register_provider("p1", _config("p1"))
        reg.register_provider("p2", _config("p2", provider_type=ProviderType.WASM.value))

        assert reg.size == 2
        assert set(reg.list_ids()) == {"p1", "p2"}

    def test_register_duplicate_raises(self) -> None:
        reg = ProviderRegistry()
        reg.register_provider("p1", _config("p1"))

        with pytest.raises(DuplicateProviderError) as exc_info:
            reg.register_provider("p1", _config("p1"))
        assert exc_info.value.provider_id == "p1"

    def test_register_empty_id_raises_value_error(self) -> None:
        reg = ProviderRegistry()
        with pytest.raises(ValueError, match="must not be empty"):
            reg.register_provider("", _config(""))

    def test_unregister_existing_returns_true(self) -> None:
        reg = ProviderRegistry()
        reg.register_provider("p1", _config("p1"))
        assert reg.unregister_provider("p1") is True
        assert not reg.contains("p1")
        assert reg.size == 0

    def test_unregister_nonexistent_returns_false(self) -> None:
        reg = ProviderRegistry()
        assert reg.unregister_provider("ghost") is False

    def test_unregister_cleans_secondary_index(self) -> None:
        reg = ProviderRegistry()
        reg.register_provider("p1", _config("p1", provider_type=ProviderType.MCP.value))
        reg.register_provider("p2", _config("p2", provider_type=ProviderType.MCP.value))
        reg.unregister_provider("p1")

        mcp_configs = reg.list_by_type(ProviderType.MCP.value)
        assert len(mcp_configs) == 1
        assert mcp_configs[0].provider_id == "p2"

    def test_unregister_last_of_type_removes_type_key(self) -> None:
        reg = ProviderRegistry()
        reg.register_provider("p1", _config("p1", provider_type=ProviderType.WASM.value))
        reg.unregister_provider("p1")

        assert reg.list_by_type(ProviderType.WASM.value) == []

    def test_re_register_after_unregister(self) -> None:
        reg = ProviderRegistry()
        cfg1 = _config("p1", endpoint="http://old")
        reg.register_provider("p1", cfg1)
        reg.unregister_provider("p1")

        cfg2 = _config("p1", endpoint="http://new")
        reg.register_provider("p1", cfg2)
        assert reg.lookup_provider("p1") is cfg2


class TestProviderRegistryLookup:
    """Lookup and listing operations."""

    def test_lookup_nonexistent_returns_none(self) -> None:
        reg = ProviderRegistry()
        assert reg.lookup_provider("ghost") is None

    def test_contains_returns_false_for_unknown(self) -> None:
        reg = ProviderRegistry()
        assert not reg.contains("nope")

    def test_list_by_type(self) -> None:
        reg = ProviderRegistry()
        reg.register_provider("m1", _config("m1", provider_type=ProviderType.MCP.value))
        reg.register_provider("m2", _config("m2", provider_type=ProviderType.MCP.value))
        reg.register_provider("w1", _config("w1", provider_type=ProviderType.WASM.value))

        mcp = reg.list_by_type(ProviderType.MCP.value)
        assert len(mcp) == 2
        assert {c.provider_id for c in mcp} == {"m1", "m2"}

    def test_list_by_type_empty(self) -> None:
        reg = ProviderRegistry()
        assert reg.list_by_type(ProviderType.BRIDGE.value) == []

    def test_list_all(self) -> None:
        reg = ProviderRegistry()
        reg.register_provider("a", _config("a"))
        reg.register_provider("b", _config("b"))
        assert len(reg.list_all()) == 2

    def test_list_ids_sorted(self) -> None:
        reg = ProviderRegistry()
        reg.register_provider("zebra", _config("zebra"))
        reg.register_provider("alpha", _config("alpha"))
        assert reg.list_ids() == ["alpha", "zebra"]

    def test_size_empty(self) -> None:
        reg = ProviderRegistry()
        assert reg.size == 0


class TestProviderRegistryHealth:
    """Health tracking operations."""

    def test_initial_health_is_unknown(self) -> None:
        reg = ProviderRegistry()
        reg.register_provider("p1", _config("p1"))
        health = reg.health_check("p1")

        assert health.provider_id == "p1"
        assert health.status == ProviderStatus.UNKNOWN.value

    def test_update_health_to_healthy(self) -> None:
        reg = ProviderRegistry()
        reg.register_provider("p1", _config("p1"))
        reg.update_health("p1", ProviderStatus.HEALTHY.value, latency_ms=42)

        health = reg.health_check("p1")
        assert health.status == ProviderStatus.HEALTHY.value
        assert health.latency_ms == 42
        assert health.last_check_at != ""

    def test_update_health_to_unhealthy_with_error(self) -> None:
        reg = ProviderRegistry()
        reg.register_provider("p1", _config("p1"))
        reg.update_health("p1", ProviderStatus.UNHEALTHY.value, error="timeout")

        health = reg.health_check("p1")
        assert health.status == ProviderStatus.UNHEALTHY.value
        assert health.error == "timeout"

    def test_update_health_invalid_status_raises(self) -> None:
        reg = ProviderRegistry()
        reg.register_provider("p1", _config("p1"))
        with pytest.raises(ValueError, match="Invalid status"):
            reg.update_health("p1", "INVALID_STATUS")

    def test_update_health_unknown_provider_raises(self) -> None:
        reg = ProviderRegistry()
        with pytest.raises(ProviderNotFoundError):
            reg.update_health("ghost", ProviderStatus.HEALTHY.value)

    def test_health_check_unknown_provider_raises(self) -> None:
        reg = ProviderRegistry()
        with pytest.raises(ProviderNotFoundError):
            reg.health_check("ghost")

    def test_list_healthy_providers(self) -> None:
        reg = ProviderRegistry()
        reg.register_provider("p1", _config("p1"))
        reg.register_provider("p2", _config("p2"))
        reg.register_provider("p3", _config("p3"))

        reg.update_health("p1", ProviderStatus.HEALTHY.value)
        reg.update_health("p2", ProviderStatus.UNHEALTHY.value)
        reg.update_health("p3", ProviderStatus.HEALTHY.value)

        healthy = reg.list_healthy_providers()
        assert set(healthy) == {"p1", "p3"}

    def test_list_healthy_providers_empty_when_all_unknown(self) -> None:
        reg = ProviderRegistry()
        reg.register_provider("p1", _config("p1"))
        assert reg.list_healthy_providers() == []

    def test_unregister_cleans_health_cache(self) -> None:
        reg = ProviderRegistry()
        reg.register_provider("p1", _config("p1"))
        reg.update_health("p1", ProviderStatus.HEALTHY.value)
        reg.unregister_provider("p1")

        with pytest.raises(ProviderNotFoundError):
            reg.health_check("p1")


class TestProviderRegistryEvents:
    """Event emission on registration, unregistration, and health changes."""

    def test_register_emits_event(self) -> None:
        ep = FakeEventPort()
        reg = ProviderRegistry(event_port=ep)
        reg.register_provider("p1", _config("p1"))

        assert len(ep.events) == 1
        e = ep.events[0]
        assert e["event_type"] == EVENT_PROVIDER_REGISTERED
        assert e["payload"]["provider_id"] == "p1"

    def test_unregister_emits_event(self) -> None:
        ep = FakeEventPort()
        reg = ProviderRegistry(event_port=ep)
        reg.register_provider("p1", _config("p1"))
        ep.events.clear()
        reg.unregister_provider("p1")

        assert len(ep.events) == 1
        assert ep.events[0]["event_type"] == EVENT_PROVIDER_UNREGISTERED

    def test_unregister_nonexistent_no_event(self) -> None:
        ep = FakeEventPort()
        reg = ProviderRegistry(event_port=ep)
        reg.unregister_provider("ghost")
        assert len(ep.events) == 0

    def test_health_change_emits_event(self) -> None:
        ep = FakeEventPort()
        reg = ProviderRegistry(event_port=ep)
        reg.register_provider("p1", _config("p1"))
        ep.events.clear()

        # UNKNOWN -> HEALTHY triggers event
        reg.update_health("p1", ProviderStatus.HEALTHY.value)
        assert len(ep.events) == 1
        e = ep.events[0]
        assert e["event_type"] == EVENT_PROVIDER_HEALTH_CHANGED
        assert e["payload"]["old_status"] == ProviderStatus.UNKNOWN.value
        assert e["payload"]["new_status"] == ProviderStatus.HEALTHY.value

    def test_health_same_status_no_event(self) -> None:
        ep = FakeEventPort()
        reg = ProviderRegistry(event_port=ep)
        reg.register_provider("p1", _config("p1"))
        reg.update_health("p1", ProviderStatus.HEALTHY.value)
        ep.events.clear()

        # HEALTHY -> HEALTHY: no event
        reg.update_health("p1", ProviderStatus.HEALTHY.value)
        assert len(ep.events) == 0

    def test_no_event_port_no_crash(self) -> None:
        reg = ProviderRegistry()  # No event_port
        reg.register_provider("p1", _config("p1"))
        reg.update_health("p1", ProviderStatus.HEALTHY.value)
        reg.unregister_provider("p1")
        # Should not raise


class TestProviderRegistryThreadSafety:
    """Concurrent access smoke tests."""

    def test_concurrent_register(self) -> None:
        reg = ProviderRegistry()
        errors: List[Exception] = []

        def _register(pid: str) -> None:
            try:
                reg.register_provider(pid, _config(pid))
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=_register, args=(f"p{i}",)) for i in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert reg.size == 50


# =========================================================================
# 3.1.2 -- ProviderMatcher Tests
# =========================================================================


class TestProviderMatcherMatch:
    """ProviderMatcher.match() tests."""

    def test_match_valid_provider(self) -> None:
        reg = ProviderRegistry()
        cfg = _config("mcp-weather")
        reg.register_provider("mcp-weather", cfg)
        reg.update_health("mcp-weather", ProviderStatus.HEALTHY.value)

        matcher = ProviderMatcher(provider_registry=reg)
        contract = _tool(provider_id="mcp-weather")
        result = matcher.match(contract)

        assert len(result) == 1
        assert result[0].provider_id == "mcp-weather"

    def test_match_unknown_provider_returns_empty(self) -> None:
        reg = ProviderRegistry()
        matcher = ProviderMatcher(provider_registry=reg)
        contract = _tool(provider_id="nonexistent")
        assert matcher.match(contract) == []

    def test_match_unhealthy_filtered_by_default(self) -> None:
        reg = ProviderRegistry()
        reg.register_provider("p1", _config("p1"))
        reg.update_health("p1", ProviderStatus.UNHEALTHY.value)

        matcher = ProviderMatcher(provider_registry=reg)
        contract = _tool(provider_id="p1")
        assert matcher.match(contract) == []

    def test_match_degraded_not_filtered(self) -> None:
        reg = ProviderRegistry()
        reg.register_provider("p1", _config("p1"))
        reg.update_health("p1", ProviderStatus.DEGRADED.value)

        matcher = ProviderMatcher(provider_registry=reg)
        contract = _tool(provider_id="p1")
        assert len(matcher.match(contract)) == 1

    def test_match_unknown_health_not_filtered(self) -> None:
        """Providers with UNKNOWN health are included (new, not yet probed)."""
        reg = ProviderRegistry()
        reg.register_provider("p1", _config("p1"))
        # Initial health is UNKNOWN

        matcher = ProviderMatcher(provider_registry=reg)
        contract = _tool(provider_id="p1")
        assert len(matcher.match(contract)) == 1

    def test_match_include_unhealthy(self) -> None:
        reg = ProviderRegistry()
        reg.register_provider("p1", _config("p1"))
        reg.update_health("p1", ProviderStatus.UNHEALTHY.value)

        matcher = ProviderMatcher(provider_registry=reg)
        contract = _tool(provider_id="p1")
        result = matcher.match(contract, include_unhealthy=True)
        assert len(result) == 1

    def test_match_prompt_contract_returns_empty(self) -> None:
        """Prompt contracts have no provider_id, so matching returns []."""
        reg = ProviderRegistry()
        matcher = ProviderMatcher(provider_registry=reg)
        contract = _prompt()
        assert matcher.match(contract) == []


class TestProviderMatcherMatchOrRaise:
    """ProviderMatcher.match_or_raise() tests."""

    def test_match_or_raise_happy_path(self) -> None:
        reg = ProviderRegistry()
        reg.register_provider("p1", _config("p1"))
        reg.update_health("p1", ProviderStatus.HEALTHY.value)

        matcher = ProviderMatcher(provider_registry=reg)
        result = matcher.match_or_raise(_tool(provider_id="p1"))
        assert len(result) == 1

    def test_match_or_raise_no_provider(self) -> None:
        reg = ProviderRegistry()
        matcher = ProviderMatcher(provider_registry=reg)

        with pytest.raises(NoProviderError) as exc_info:
            matcher.match_or_raise(_tool(provider_id="ghost"))
        assert exc_info.value.provider_id == "ghost"

    def test_match_or_raise_unhealthy_raises(self) -> None:
        reg = ProviderRegistry()
        reg.register_provider("p1", _config("p1"))
        reg.update_health("p1", ProviderStatus.UNHEALTHY.value)

        matcher = ProviderMatcher(provider_registry=reg)
        with pytest.raises(NoProviderError):
            matcher.match_or_raise(_tool(provider_id="p1"))

    def test_match_or_raise_prompt_raises(self) -> None:
        reg = ProviderRegistry()
        matcher = ProviderMatcher(provider_registry=reg)
        with pytest.raises(NoProviderError):
            matcher.match_or_raise(_prompt())


# =========================================================================
# 3.1.3 -- ProviderSelector Tests
# =========================================================================


class TestProviderSelectorSelect:
    """ProviderSelector.select() tests."""

    def test_select_single_candidate(self) -> None:
        selector = ProviderSelector()
        c = _scored("p1", score=0.9)
        result = selector.select([c])

        assert isinstance(result, ResolvedProvider)
        assert result.provider_config.provider_id == "p1"
        assert result.policy_result.score == 0.9

    def test_select_highest_score_wins(self) -> None:
        selector = ProviderSelector()
        candidates = [
            _scored("p1", score=0.5),
            _scored("p2", score=0.9),
            _scored("p3", score=0.7),
        ]
        result = selector.select(candidates)
        assert result.provider_config.provider_id == "p2"

    def test_select_tiebreak_lower_latency_wins(self) -> None:
        """Same score -> lower avg_latency_ms wins."""
        selector = ProviderSelector()
        candidates = [
            _scored("p1", score=0.8, avg_latency_ms=100),
            _scored("p2", score=0.8, avg_latency_ms=50),
        ]
        result = selector.select(candidates)
        assert result.provider_config.provider_id == "p2"

    def test_select_tiebreak_alphabetical_id(self) -> None:
        """Same score + same latency -> alphabetical provider_id."""
        selector = ProviderSelector()
        candidates = [
            _scored("zebra", score=0.8, avg_latency_ms=50),
            _scored("alpha", score=0.8, avg_latency_ms=50),
        ]
        result = selector.select(candidates)
        assert result.provider_config.provider_id == "alpha"

    def test_select_filters_rejected_candidates(self) -> None:
        """Candidates with allowed=False are excluded."""
        selector = ProviderSelector()
        candidates = [
            _scored("p1", score=0.9, allowed=False, reasons=["security"]),
            _scored("p2", score=0.5, allowed=True),
        ]
        result = selector.select(candidates)
        assert result.provider_config.provider_id == "p2"

    def test_select_empty_raises_no_candidates(self) -> None:
        selector = ProviderSelector()
        with pytest.raises(NoCandidatesError):
            selector.select([])

    def test_select_all_rejected_raises(self) -> None:
        selector = ProviderSelector()
        candidates = [
            _scored("p1", score=0.9, allowed=False, reasons=["denied"]),
            _scored("p2", score=0.8, allowed=False, reasons=["blocked"]),
        ]
        with pytest.raises(AllProvidersRejectedError) as exc_info:
            selector.select(candidates, capability_name="tool.exec.x")
        assert exc_info.value.capability_name == "tool.exec.x"
        assert "denied" in exc_info.value.reasons
        assert "blocked" in exc_info.value.reasons


class TestProviderSelectorSelectTopN:
    """ProviderSelector.select_top_n() tests."""

    def test_select_top_1(self) -> None:
        selector = ProviderSelector()
        candidates = [
            _scored("p1", score=0.5),
            _scored("p2", score=0.9),
            _scored("p3", score=0.7),
        ]
        result = selector.select_top_n(candidates, n=1)
        assert len(result) == 1
        assert result[0].provider_config.provider_id == "p2"

    def test_select_top_3_ordered(self) -> None:
        selector = ProviderSelector()
        candidates = [
            _scored("p1", score=0.5),
            _scored("p2", score=0.9),
            _scored("p3", score=0.7),
        ]
        result = selector.select_top_n(candidates, n=3)
        ids = [r.provider_config.provider_id for r in result]
        assert ids == ["p2", "p3", "p1"]

    def test_select_top_n_exceeds_candidates(self) -> None:
        """Requesting more than available returns all available."""
        selector = ProviderSelector()
        candidates = [_scored("p1", score=0.8)]
        result = selector.select_top_n(candidates, n=10)
        assert len(result) == 1

    def test_select_top_n_filters_rejected(self) -> None:
        selector = ProviderSelector()
        candidates = [
            _scored("p1", score=0.9, allowed=False),
            _scored("p2", score=0.8),
            _scored("p3", score=0.7),
        ]
        result = selector.select_top_n(candidates, n=5)
        ids = [r.provider_config.provider_id for r in result]
        assert "p1" not in ids
        assert ids == ["p2", "p3"]

    def test_select_top_n_empty_raises(self) -> None:
        selector = ProviderSelector()
        with pytest.raises(NoCandidatesError):
            selector.select_top_n([], n=1)

    def test_select_top_n_all_rejected_raises(self) -> None:
        selector = ProviderSelector()
        candidates = [_scored("p1", allowed=False)]
        with pytest.raises(AllProvidersRejectedError):
            selector.select_top_n(candidates, n=1)


class TestProviderSelectorFAB10Determinism:
    """FAB-10: Provider selection is deterministic given same inputs + state."""

    def test_select_is_deterministic_100_iterations(self) -> None:
        selector = ProviderSelector()
        candidates = [
            _scored("alpha", score=0.8, avg_latency_ms=50),
            _scored("bravo", score=0.8, avg_latency_ms=50),
            _scored("charlie", score=0.8, avg_latency_ms=50),
        ]

        first_result = selector.select(candidates)
        for _ in range(100):
            result = selector.select(candidates)
            assert result.provider_config.provider_id == first_result.provider_config.provider_id

    def test_select_top_n_is_deterministic(self) -> None:
        selector = ProviderSelector()
        candidates = [
            _scored("bravo", score=0.8, avg_latency_ms=100),
            _scored("alpha", score=0.8, avg_latency_ms=100),
            _scored("charlie", score=0.7, avg_latency_ms=50),
        ]

        first_result = selector.select_top_n(candidates, n=3)
        first_ids = [r.provider_config.provider_id for r in first_result]
        for _ in range(100):
            result = selector.select_top_n(candidates, n=3)
            ids = [r.provider_config.provider_id for r in result]
            assert ids == first_ids

    def test_three_way_tiebreak_all_same_score_latency(self) -> None:
        """All same score and latency -> alphabetical provider_id wins."""
        selector = ProviderSelector()
        candidates = [
            _scored("charlie", score=0.8, avg_latency_ms=50),
            _scored("alpha", score=0.8, avg_latency_ms=50),
            _scored("bravo", score=0.8, avg_latency_ms=50),
        ]
        result = selector.select(candidates)
        assert result.provider_config.provider_id == "alpha"

        ranked = selector.select_top_n(candidates, n=3)
        ids = [r.provider_config.provider_id for r in ranked]
        assert ids == ["alpha", "bravo", "charlie"]


class TestProviderSelectorEdgeCases:
    """Edge cases for ProviderSelector."""

    def test_candidate_without_contract(self) -> None:
        """Candidate with no contract should default latency to 0."""
        selector = ProviderSelector()
        c = ScoredCandidate(
            provider_config=_config("p1"),
            contract=None,
            policy_result=PolicyResult(allowed=True, score=0.9),
        )
        result = selector.select([c])
        assert result.provider_config.provider_id == "p1"

    def test_resolved_provider_to_dict(self) -> None:
        """ResolvedProvider.to_dict() serializes correctly."""
        selector = ProviderSelector()
        c = _scored("p1", score=0.85)
        result = selector.select([c])
        d = result.to_dict()

        assert d["provider_config"]["provider_id"] == "p1"
        assert d["policy_result"]["score"] == 0.85
        assert d["policy_result"]["allowed"] is True

    def test_scored_candidate_is_frozen(self) -> None:
        c = _scored("p1", score=0.9)
        with pytest.raises(AttributeError):
            c.policy_result = PolicyResult()  # type: ignore[misc]


# =========================================================================
# Exception hierarchy tests
# =========================================================================


class TestExceptionHierarchy:
    """Exception class relationships."""

    def test_duplicate_provider_is_registry_error(self) -> None:
        assert issubclass(DuplicateProviderError, ProviderRegistryError)

    def test_not_found_is_registry_error(self) -> None:
        assert issubclass(ProviderNotFoundError, ProviderRegistryError)

    def test_no_provider_is_matcher_error(self) -> None:
        assert issubclass(NoProviderError, ProviderMatcherError)

    def test_all_rejected_is_selector_error(self) -> None:
        assert issubclass(AllProvidersRejectedError, ProviderSelectorError)

    def test_no_candidates_is_selector_error(self) -> None:
        assert issubclass(NoCandidatesError, ProviderSelectorError)
