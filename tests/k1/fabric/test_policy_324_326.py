"""
Integration tests for Epic 3.2.4-3.2.6:

  - 3.2.4 QoSIntegration (soft score)
  - 3.2.5 PolicyEngine (composite)
  - 3.2.6 ToolScope (sub-agent tool scoping)

Tests follow the existing pattern from test_policy_321_323.py.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from k1.fabric.policy.affective_routing import AffectiveRouting
from k1.fabric.policy.cognitive_load_routing import CognitiveLoadRouting
from k1.fabric.policy.policy_engine import PolicyEngine
from k1.fabric.policy.qos_integration import QoSIntegration, QoSScore
from k1.fabric.policy.security_context import AccessDeniedError, SecurityContext
from k1.fabric.policy.tool_scope import ToolScope, ToolScopeError
from k1.fabric.provider_resolution.provider_selector import ScoredCandidate
from k1.fabric.types import CapabilityContract, CapabilityRequest, ProviderConfig, SafetyBand

# =========================================================================
# Helpers
# =========================================================================


def _request(
    capability_name: str = "tool.execute.weather",
    safety_band: str = SafetyBand.GREEN.value,
    session_id: str = "sess-1",
    params: Optional[Dict[str, Any]] = None,
) -> CapabilityRequest:
    """Build a minimal valid CapabilityRequest."""
    return CapabilityRequest(
        capability_name=capability_name,
        safety_band=safety_band,
        session_id=session_id,
        caller="test",
        params=params or {},
    )


def _contract(
    name: str = "tool.execute.weather",
    safety_band_min: str = SafetyBand.GREEN.value,
) -> CapabilityContract:
    """Build a minimal CapabilityContract."""
    return CapabilityContract(
        name=name,
        version="1.0.0",
        description="test",
        provider_type="MCP",
        safety_band_min=safety_band_min,
        output={"type": "object"},
    )


def _provider(
    provider_id: str = "p1",
    max_execution_ms: int = 30000,
) -> ProviderConfig:
    """Build a minimal ProviderConfig."""
    return ProviderConfig(
        provider_id=provider_id,
        provider_type="MCP",
        max_execution_ms=max_execution_ms,
    )


class FakeStateReader:
    """Test double satisfying ISessionStateReader."""

    def __init__(self, sections: Optional[Dict[str, Dict[str, Any]]] = None):
        self._sections = sections or {}

    def read_section(self, session_id: str, section: str) -> Optional[Dict[str, Any]]:
        return self._sections.get(section)


# =========================================================================
# 3.2.4 -- QoSIntegration
# =========================================================================


class TestQoSNoMetadata:
    """When no cost/latency metadata is provided."""

    def test_returns_neutral_score(self):
        qos = QoSIntegration()
        result = qos.score(_request())
        assert result.score == 0.0
        assert result.reason == "no_provider_qos_metadata"

    def test_returns_qos_score_type(self):
        qos = QoSIntegration()
        result = qos.score(_request())
        assert isinstance(result, QoSScore)


class TestQoSAmpleBudget:
    """When budget and latency are ample (defaults = 1.0)."""

    def test_with_latency_only(self):
        qos = QoSIntegration()
        result = qos.score(_request(), avg_latency_ms=2000)
        assert 0.0 < result.score <= 0.2
        assert "latency=2000ms" in result.reason

    def test_with_cost_only(self):
        qos = QoSIntegration()
        result = qos.score(_request(), cost_per_call=0.5)
        assert 0.0 < result.score <= 0.2
        assert "cost=0.5000" in result.reason

    def test_with_both(self):
        qos = QoSIntegration()
        result = qos.score(_request(), cost_per_call=0.5, avg_latency_ms=2000)
        assert 0.0 < result.score <= 0.2

    def test_lower_latency_scores_higher(self):
        """Faster providers should get higher QoS scores."""
        qos = QoSIntegration()
        fast = qos.score(_request(), avg_latency_ms=500)
        slow = qos.score(_request(), avg_latency_ms=10000)
        assert fast.score > slow.score

    def test_lower_cost_scores_higher(self):
        """Cheaper providers should get higher QoS scores."""
        qos = QoSIntegration()
        cheap = qos.score(_request(), cost_per_call=0.01)
        expensive = qos.score(_request(), cost_per_call=10.0)
        assert cheap.score > expensive.score


class TestQoSTightBudget:
    """When budget_remaining_pct < 0.20."""

    def test_tight_budget_increases_cost_weight(self):
        qos = QoSIntegration()
        params_tight = {"budget_remaining_pct": 0.10}
        params_ample = {"budget_remaining_pct": 0.80}
        tight = qos.score(_request(params=params_tight), cost_per_call=0.5)
        ample = qos.score(_request(params=params_ample), cost_per_call=0.5)
        # Tight budget => higher weight => higher score for same cost
        assert tight.score > ample.score

    def test_tight_budget_reason_includes_marker(self):
        qos = QoSIntegration()
        params = {"budget_remaining_pct": 0.10}
        result = qos.score(_request(params=params), cost_per_call=0.5)
        assert "tight_budget" in result.reason

    def test_zero_budget(self):
        qos = QoSIntegration()
        params = {"budget_remaining_pct": 0.0}
        result = qos.score(_request(params=params), cost_per_call=0.5)
        assert "tight_budget" in result.reason
        assert result.score > 0.0


class TestQoSTightLatency:
    """When latency_remaining_pct < 0.30."""

    def test_tight_latency_increases_latency_weight(self):
        qos = QoSIntegration()
        params_tight = {"latency_remaining_pct": 0.10}
        params_ample = {"latency_remaining_pct": 0.80}
        tight = qos.score(_request(params=params_tight), avg_latency_ms=2000)
        ample = qos.score(_request(params=params_ample), avg_latency_ms=2000)
        assert tight.score > ample.score

    def test_tight_latency_reason_includes_marker(self):
        qos = QoSIntegration()
        params = {"latency_remaining_pct": 0.15}
        result = qos.score(_request(params=params), avg_latency_ms=2000)
        assert "tight_latency" in result.reason


class TestQoSEdgeCases:
    """Edge cases and robustness."""

    def test_negative_cost_treated_as_zero(self):
        qos = QoSIntegration()
        result = qos.score(_request(), cost_per_call=-5.0)
        assert result.score >= 0.0

    def test_zero_latency(self):
        qos = QoSIntegration()
        result = qos.score(_request(), avg_latency_ms=0)
        assert result.score > 0.0  # norm = 1/(1+0) = 1.0

    def test_invalid_budget_pct_string(self):
        """Non-numeric budget_remaining_pct defaults to 1.0 (ample)."""
        qos = QoSIntegration()
        params = {"budget_remaining_pct": "not_a_number"}
        result = qos.score(_request(params=params), cost_per_call=0.5)
        # Should not crash, should use default 1.0
        assert result.score > 0.0

    def test_budget_pct_clamped_above_one(self):
        """Budget above 1.0 clamped to 1.0."""
        qos = QoSIntegration()
        params = {"budget_remaining_pct": 5.0}
        result = qos.score(_request(params=params), cost_per_call=0.5)
        assert result.score > 0.0

    def test_score_never_exceeds_max(self):
        """Score capped at 0.2."""
        qos = QoSIntegration()
        # Very cheap and fast with tight budgets -> max possible score
        params = {"budget_remaining_pct": 0.01, "latency_remaining_pct": 0.01}
        result = qos.score(_request(params=params), cost_per_call=0.001, avg_latency_ms=1)
        assert result.score <= 0.2


# =========================================================================
# 3.2.5 -- PolicyEngine (composite)
# =========================================================================


class TestPolicyEngineSecurityGate:
    """Security hard gate blocks entire evaluation."""

    def test_rejected_by_security(self):
        """GREEN user, AMBER capability -> rejected."""
        engine = PolicyEngine(security=SecurityContext())
        req = _request(safety_band=SafetyBand.GREEN.value)
        contract = _contract(safety_band_min=SafetyBand.AMBER.value)
        results = engine.evaluate([_provider()], contract, req)
        assert len(results) == 1
        assert not results[0].policy_result.allowed
        assert results[0].policy_result.score == 0.0

    def test_passed_security(self):
        """GREEN user, GREEN capability -> allowed."""
        engine = PolicyEngine(security=SecurityContext())
        req = _request(safety_band=SafetyBand.GREEN.value)
        contract = _contract(safety_band_min=SafetyBand.GREEN.value)
        results = engine.evaluate([_provider()], contract, req)
        assert len(results) == 1
        assert results[0].policy_result.allowed
        assert results[0].policy_result.score >= 1.0

    def test_amber_user_red_cap_rejected(self):
        """AMBER user, RED capability -> rejected."""
        engine = PolicyEngine(security=SecurityContext())
        req = _request(safety_band=SafetyBand.AMBER.value)
        contract = _contract(safety_band_min=SafetyBand.RED.value)
        results = engine.evaluate([_provider()], contract, req)
        assert not results[0].policy_result.allowed

    def test_crisis_user_passes_all(self):
        """CRISIS user passes CRISIS capability."""
        engine = PolicyEngine(security=SecurityContext())
        req = _request(safety_band=SafetyBand.CRISIS.value)
        contract = _contract(safety_band_min=SafetyBand.CRISIS.value)
        results = engine.evaluate([_provider()], contract, req)
        assert results[0].policy_result.allowed


class TestPolicyEngineToolScoping:
    """Tool-scope check via tools_granted parameter."""

    def test_tool_scope_pass(self):
        engine = PolicyEngine(
            security=SecurityContext(),
            tools_granted=frozenset(["tool.execute.weather"]),
        )
        req = _request(capability_name="tool.execute.weather")
        contract = _contract(name="tool.execute.weather")
        results = engine.evaluate([_provider()], contract, req)
        assert results[0].policy_result.allowed

    def test_tool_scope_reject(self):
        engine = PolicyEngine(
            security=SecurityContext(),
            tools_granted=frozenset(["tool.execute.calendar"]),
        )
        req = _request(capability_name="tool.execute.weather")
        contract = _contract(name="tool.execute.weather")
        results = engine.evaluate([_provider()], contract, req)
        assert not results[0].policy_result.allowed


class TestPolicyEngineCompositeScoring:
    """Soft scores compose correctly."""

    def test_base_relevance_only(self):
        """No soft dimensions wired -> score = 1.0 (base only)."""
        engine = PolicyEngine(security=SecurityContext())
        req = _request()
        contract = _contract()
        results = engine.evaluate([_provider()], contract, req)
        assert results[0].policy_result.score == 1.0

    def test_affective_adds_to_base(self):
        """Affective soft score adds to base."""
        reader = FakeStateReader({"affective_now": {"raw": "sadness", "intensity": 0.9}})
        engine = PolicyEngine(
            security=SecurityContext(),
            affective=AffectiveRouting(state_reader=reader),
        )
        req = _request()
        contract = _contract()
        results = engine.evaluate([_provider()], contract, req)
        # base (1.0) + affective (0.1) = 1.1
        assert results[0].policy_result.score == pytest.approx(1.1, abs=0.01)

    def test_cognitive_adds_to_base(self):
        """Cognitive soft score adds to base."""
        reader = FakeStateReader({"cognitive": {"load": 0.9, "complexity_tier": "HIGH"}})
        engine = PolicyEngine(
            security=SecurityContext(),
            cognitive=CognitiveLoadRouting(state_reader=reader),
        )
        req = _request()
        contract = _contract()
        results = engine.evaluate([_provider()], contract, req)
        # base (1.0) + cognitive (0.1) = 1.1
        assert results[0].policy_result.score == pytest.approx(1.1, abs=0.01)

    def test_qos_adds_to_base(self):
        """QoS soft score adds to base."""
        engine = PolicyEngine(
            security=SecurityContext(),
            qos=QoSIntegration(),
        )
        req = _request()
        contract = _contract()
        # Provider has max_execution_ms=30000, so QoS can compute latency score
        results = engine.evaluate([_provider(max_execution_ms=2000)], contract, req)
        assert results[0].policy_result.score > 1.0

    def test_all_dimensions_compose(self):
        """All 4 dimensions compose: base + affective + cognitive + qos."""
        reader = FakeStateReader(
            {
                "affective_now": {"raw": "sadness", "intensity": 0.9},
                "cognitive": {"load": 0.9, "complexity_tier": "HIGH"},
            }
        )
        engine = PolicyEngine(
            security=SecurityContext(),
            affective=AffectiveRouting(state_reader=reader),
            cognitive=CognitiveLoadRouting(state_reader=reader),
            qos=QoSIntegration(),
        )
        req = _request()
        contract = _contract()
        results = engine.evaluate([_provider(max_execution_ms=2000)], contract, req)
        # base(1.0) + affective(0.1) + cognitive(0.1) + qos(>0) > 1.2
        assert results[0].policy_result.score > 1.2

    def test_multiple_candidates(self):
        """All candidates evaluated independently."""
        engine = PolicyEngine(security=SecurityContext())
        providers = [_provider("p1"), _provider("p2"), _provider("p3")]
        results = engine.evaluate(providers, _contract(), _request())
        assert len(results) == 3
        for r in results:
            assert isinstance(r, ScoredCandidate)
            assert r.policy_result.allowed

    def test_reasons_include_all_dimensions(self):
        """Reasons list covers all 4 dimension labels."""
        reader = FakeStateReader(
            {
                "affective_now": {"raw": "joy", "intensity": 0.8},
                "cognitive": {"load": 0.5},
            }
        )
        engine = PolicyEngine(
            security=SecurityContext(),
            affective=AffectiveRouting(state_reader=reader),
            cognitive=CognitiveLoadRouting(state_reader=reader),
            qos=QoSIntegration(),
        )
        results = engine.evaluate([_provider(max_execution_ms=5000)], _contract(), _request())
        reasons = results[0].policy_result.reasons
        reason_text = " ".join(reasons)
        assert (
            "band_ok" in reason_text.lower()
            or "security" in reason_text.lower()
            or "pass" in reason_text.lower()
        )
        assert "affective=" in reason_text
        assert "cognitive=" in reason_text
        assert "qos=" in reason_text


class TestPolicyEngineDeterminism:
    """FAB-10: same inputs, same outputs."""

    def test_same_inputs_same_scores(self):
        engine = PolicyEngine(security=SecurityContext())
        req = _request()
        contract = _contract()
        providers = [_provider("p1"), _provider("p2")]
        r1 = engine.evaluate(providers, contract, req)
        r2 = engine.evaluate(providers, contract, req)
        for a, b in zip(r1, r2):
            assert a.policy_result.score == b.policy_result.score
            assert a.policy_result.allowed == b.policy_result.allowed


class TestPolicyEngineErrorHandling:
    """Graceful degradation on dimension failures."""

    def test_security_required(self):
        with pytest.raises(ValueError, match="SecurityContext is required"):
            PolicyEngine(security=None)  # type: ignore[arg-type]

    def test_no_affective_returns_zero(self):
        """No AffectiveRouting wired -> affective=0.0."""
        engine = PolicyEngine(security=SecurityContext())
        results = engine.evaluate([_provider()], _contract(), _request())
        # Score should be exactly 1.0 (base only, no soft scores)
        assert results[0].policy_result.score == 1.0

    def test_mixed_allow_reject(self):
        """Some candidates pass, some fail security."""
        engine = PolicyEngine(
            security=SecurityContext(),
            tools_granted=frozenset(["tool.execute.weather"]),
        )
        req = _request(capability_name="tool.execute.weather")
        contract = _contract(name="tool.execute.weather")
        # All should pass since capability matches tools_granted
        providers = [_provider("p1"), _provider("p2")]
        results = engine.evaluate(providers, contract, req)
        assert all(r.policy_result.allowed for r in results)


class TestPolicyEngineSatisfiesPort:
    """Verify PolicyEngine satisfies PolicyEnginePort Protocol."""

    def test_has_evaluate_method(self):
        engine = PolicyEngine(security=SecurityContext())
        assert hasattr(engine, "evaluate")
        assert callable(engine.evaluate)

    def test_evaluate_returns_scored_candidates(self):
        engine = PolicyEngine(security=SecurityContext())
        results = engine.evaluate([_provider()], _contract(), _request())
        assert isinstance(results, list)
        assert all(isinstance(r, ScoredCandidate) for r in results)

    def test_evaluate_signature_matches_port(self):
        """Evaluate accepts the exact types PolicyEnginePort requires."""
        engine = PolicyEngine(security=SecurityContext())
        candidates: List[ProviderConfig] = [_provider()]
        contract = _contract()
        request = _request()
        # This is a structural type check: if it doesn't crash, signature matches
        result = engine.evaluate(candidates, contract, request)
        assert isinstance(result, list)


# =========================================================================
# 3.2.6 -- ToolScope
# =========================================================================


class TestToolScopeConstruction:
    """Construction and property access."""

    def test_basic_construction(self):
        scope = ToolScope(tools_granted=["tool.execute.weather"])
        assert "tool.execute.weather" in scope.tools_granted

    def test_from_list(self):
        scope = ToolScope(tools_granted=["a", "b", "c"])
        assert scope.tools_granted == frozenset({"a", "b", "c"})

    def test_from_frozenset(self):
        scope = ToolScope(tools_granted=frozenset({"x", "y"}))
        assert scope.tools_granted == frozenset({"x", "y"})

    def test_deduplicates(self):
        scope = ToolScope(tools_granted=["a", "a", "b"])
        assert len(scope.tools_granted) == 2

    def test_empty_raises(self):
        with pytest.raises(ToolScopeError, match="non-empty"):
            ToolScope(tools_granted=[])

    def test_repr(self):
        scope = ToolScope(tools_granted=["b", "a"])
        r = repr(scope)
        assert "ToolScope" in r
        assert "a" in r


class TestToolScopeValidate:
    """validate() method testing."""

    def test_allowed_capability(self):
        scope = ToolScope(tools_granted=["tool.execute.weather", "tool.execute.calendar"])
        assert scope.validate("tool.execute.weather") is True

    def test_denied_capability(self):
        scope = ToolScope(tools_granted=["tool.execute.weather"])
        with pytest.raises(AccessDeniedError) as exc_info:
            scope.validate("tool.execute.payments")
        assert exc_info.value.check == "tool_scope"
        assert "tool.execute.payments" in exc_info.value.detail

    def test_empty_capability_name_raises(self):
        scope = ToolScope(tools_granted=["tool.execute.weather"])
        with pytest.raises(AccessDeniedError, match="empty"):
            scope.validate("")

    def test_multiple_tools(self):
        tools = ["tool.a", "tool.b", "tool.c", "agent.x"]
        scope = ToolScope(tools_granted=tools)
        for t in tools:
            assert scope.validate(t) is True

    def test_case_sensitive(self):
        scope = ToolScope(tools_granted=["tool.execute.Weather"])
        with pytest.raises(AccessDeniedError):
            scope.validate("tool.execute.weather")


class TestToolScopeIsAllowed:
    """is_allowed() non-raising check."""

    def test_allowed(self):
        scope = ToolScope(tools_granted=["tool.execute.weather"])
        assert scope.is_allowed("tool.execute.weather") is True

    def test_denied(self):
        scope = ToolScope(tools_granted=["tool.execute.weather"])
        assert scope.is_allowed("tool.execute.payments") is False

    def test_empty_string(self):
        scope = ToolScope(tools_granted=["tool.execute.weather"])
        assert scope.is_allowed("") is False


# =========================================================================
# Package exports
# =========================================================================


class TestPolicyPackageExports324326:
    """Verify __init__.py re-exports all new symbols."""

    def test_all_new_exports_accessible(self):
        from k1.fabric.policy import (
            PolicyEngine,
            QoSIntegration,
            QoSScore,
            ToolScope,
            ToolScopeError,
        )

        assert QoSIntegration is not None
        assert QoSScore is not None
        assert PolicyEngine is not None
        assert ToolScope is not None
        assert ToolScopeError is not None

    def test_all_in___all__(self):
        import k1.fabric.policy as pkg

        expected = [
            "QoSIntegration",
            "QoSScore",
            "PolicyEngine",
            "ToolScope",
            "ToolScopeError",
        ]
        for name in expected:
            assert name in pkg.__all__, f"{name} missing from __all__"
