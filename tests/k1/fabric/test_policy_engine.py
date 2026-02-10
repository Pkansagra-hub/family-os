"""
Epic 6.2.6 -- Test PolicyEngine (all 4 dimensions).

Covers:
  - SecurityContext: GREEN+GREEN=PASS, GREEN+AMBER=REJECT, band ordering,
    tool scope, rate limiting.
  - AffectiveRouting: high sadness boosts (+0.1), high joy boosts (+0.05),
    low intensity neutral (0.0).
  - CognitiveLoadRouting: high load (+0.1), low load (+0.05), medium neutral.
  - QoSIntegration: tight budget prefers cheaper, tight latency prefers faster.
  - PolicyEngine composite: base_relevance(1.0) + affective + cognitive + qos.
  - ToolScope enforcement per FAB-07.

NO MOCKS -- all tests use real adapters.

References:
  - fabric-implementation-plan.md Epic 6.2.6
  - fabric_discussion.md Section 10 (Four Policy Dimensions)
  - FAB-06 (safety band access), FAB-07 (tool scoping)
"""

from __future__ import annotations

import pytest

from k1.fabric.policy.affective_routing import AffectiveRouting
from k1.fabric.policy.cognitive_load_routing import CognitiveLoadRouting
from k1.fabric.policy.policy_engine import PolicyEngine
from k1.fabric.policy.qos_integration import QoSIntegration
from k1.fabric.policy.security_context import AccessDeniedError, SecurityContext
from k1.fabric.policy.tool_scope import ToolScope, ToolScopeError
from k1.fabric.types import (
    CapabilityContract,
    CapabilityRequest,
    InputSpec,
    ProviderConfig,
    SafetyBand,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class InMemorySessionStateReader:
    """Real in-memory SessionState reader for policy dimension tests."""

    def __init__(self, sections: dict | None = None):
        self._sections = sections or {}

    def read_section(self, session_id: str, section: str):
        return self._sections.get(section)

    def set_section(self, section: str, data: dict):
        self._sections[section] = data


def _make_contract(
    name: str = "tool.execute.test_cap",
    safety_band: str = SafetyBand.GREEN.value,
) -> CapabilityContract:
    return CapabilityContract(
        name=name,
        version="1.0.0",
        domain=["TEST"],
        description="Test capability",
        capabilities=["test_action"],
        limitations=[],
        required_inputs=[
            InputSpec(name="input_a", type="STRING", description="Test"),
        ],
        output={"type": "object"},
        provider_type="MCP",
        provider_id="test-provider",
        safety_band_min=safety_band,
    )


def _make_request(
    capability_name: str = "tool.execute.test_cap",
    safety_band: str = SafetyBand.GREEN.value,
    session_id: str = "sess-001",
    params: dict | None = None,
) -> CapabilityRequest:
    return CapabilityRequest(
        capability_name=capability_name,
        safety_band=safety_band,
        session_id=session_id,
        caller="test-caller",
        params=params or {},
    )


def _make_provider_config(
    provider_id: str = "test-provider",
    max_execution_ms: int = 30000,
) -> ProviderConfig:
    return ProviderConfig(
        provider_id=provider_id,
        provider_type="MCP",
        endpoint="mcp://local/test",
        max_execution_ms=max_execution_ms,
    )


# ===========================================================================
# SecurityContext tests
# ===========================================================================


class TestSecurityContext:
    """SecurityContext: hard-gate safety band, tool scope, rate limiting."""

    def test_green_user_green_cap_allowed(self):
        sec = SecurityContext()
        result = sec.check_band("GREEN", "GREEN")
        assert result.allowed is True

    def test_green_user_amber_cap_denied(self):
        sec = SecurityContext()
        result = sec.check_band("GREEN", "AMBER")
        assert result.allowed is False
        assert any("band_denied" in r for r in result.reasons)

    def test_amber_user_green_cap_allowed(self):
        sec = SecurityContext()
        result = sec.check_band("AMBER", "GREEN")
        assert result.allowed is True

    def test_amber_user_amber_cap_allowed(self):
        sec = SecurityContext()
        result = sec.check_band("AMBER", "AMBER")
        assert result.allowed is True

    def test_crisis_user_crisis_cap_allowed(self):
        sec = SecurityContext()
        result = sec.check_band("CRISIS", "CRISIS")
        assert result.allowed is True

    def test_red_user_crisis_cap_denied(self):
        sec = SecurityContext()
        result = sec.check_band("RED", "CRISIS")
        assert result.allowed is False

    def test_band_ordering_green_lt_amber_lt_red_lt_crisis(self):
        sec = SecurityContext()
        bands = ["GREEN", "AMBER", "RED", "CRISIS"]
        for i in range(len(bands)):
            for j in range(len(bands)):
                result = sec.check_band(bands[i], bands[j])
                if i >= j:
                    assert result.allowed is True, f"{bands[i]}>={bands[j]} should pass"
                else:
                    assert result.allowed is False, f"{bands[i]}<{bands[j]} should fail"

    def test_invalid_user_band_denied(self):
        sec = SecurityContext()
        result = sec.check_band("INVALID", "GREEN")
        assert result.allowed is False

    def test_tool_scope_allowed(self):
        sec = SecurityContext()
        result = sec.check_tool_scope(
            "tool.execute.weather",
            frozenset({"tool.execute.weather", "tool.execute.calendar"}),
        )
        assert result.allowed is True

    def test_tool_scope_denied(self):
        sec = SecurityContext()
        result = sec.check_tool_scope(
            "tool.execute.payments",
            frozenset({"tool.execute.weather"}),
        )
        assert result.allowed is False

    def test_rate_limit_under_limit(self):
        sec = SecurityContext(rate_limits={"tool.execute.test": 100})
        result = sec.check_rate_limit("tool.execute.test")
        assert result.allowed is True

    def test_rate_limit_exceeded(self):
        sec = SecurityContext(rate_limits={"tool.execute.test": 3})
        for _ in range(3):
            result = sec.check_rate_limit("tool.execute.test")
            assert result.allowed is True
        # 4th call should be denied
        result = sec.check_rate_limit("tool.execute.test")
        assert result.allowed is False

    def test_rate_limit_no_limit_configured(self):
        sec = SecurityContext()
        result = sec.check_rate_limit("tool.execute.test")
        assert result.allowed is True

    def test_evaluate_full_pipeline_pass(self):
        sec = SecurityContext()
        request = _make_request(safety_band="GREEN")
        contract = _make_contract(safety_band="GREEN")
        result = sec.evaluate(request, contract)
        assert result.allowed is True

    def test_evaluate_full_pipeline_band_reject(self):
        sec = SecurityContext()
        request = _make_request(safety_band="GREEN")
        contract = _make_contract(safety_band="AMBER")
        result = sec.evaluate(request, contract)
        assert result.allowed is False

    def test_evaluate_with_tool_scope_reject(self):
        sec = SecurityContext()
        request = _make_request(
            capability_name="tool.execute.payments",
            safety_band="GREEN",
        )
        contract = _make_contract(safety_band="GREEN")
        result = sec.evaluate(
            request,
            contract,
            tools_granted=frozenset({"tool.execute.weather"}),
        )
        assert result.allowed is False


# ===========================================================================
# AffectiveRouting tests
# ===========================================================================


class TestAffectiveRouting:
    """AffectiveRouting: emotion-based soft scoring."""

    def test_no_state_reader_returns_neutral(self):
        ar = AffectiveRouting(state_reader=None)
        result = ar.score(_make_request())
        assert result.score == 0.0
        assert "no_state_reader" in result.reason

    def test_missing_section_returns_neutral(self):
        reader = InMemorySessionStateReader()
        ar = AffectiveRouting(state_reader=reader)
        result = ar.score(_make_request())
        assert result.score == 0.0

    def test_high_sadness_boost(self):
        reader = InMemorySessionStateReader(
            {
                "affective_now": {"raw": "sadness", "intensity": 0.85},
            }
        )
        ar = AffectiveRouting(state_reader=reader)
        result = ar.score(_make_request())
        assert result.score == pytest.approx(0.1)
        assert "sad_anxious_boost" in result.reason

    def test_high_anxiety_boost(self):
        reader = InMemorySessionStateReader(
            {
                "affective_now": {"raw": "anxiety", "intensity": 0.9},
            }
        )
        ar = AffectiveRouting(state_reader=reader)
        result = ar.score(_make_request())
        assert result.score == pytest.approx(0.1)

    def test_high_joy_boost(self):
        reader = InMemorySessionStateReader(
            {
                "affective_now": {"raw": "joy", "intensity": 0.8},
            }
        )
        ar = AffectiveRouting(state_reader=reader)
        result = ar.score(_make_request())
        assert result.score == pytest.approx(0.05)
        assert "joy_excited_boost" in result.reason

    def test_low_intensity_no_adjustment(self):
        reader = InMemorySessionStateReader(
            {
                "affective_now": {"raw": "sadness", "intensity": 0.3},
            }
        )
        ar = AffectiveRouting(state_reader=reader)
        result = ar.score(_make_request())
        assert result.score == 0.0
        assert "low_intensity" in result.reason

    def test_intensity_at_threshold_no_adjustment(self):
        """intensity == 0.7 is at threshold, not above -> no boost."""
        reader = InMemorySessionStateReader(
            {
                "affective_now": {"raw": "sadness", "intensity": 0.7},
            }
        )
        ar = AffectiveRouting(state_reader=reader)
        result = ar.score(_make_request())
        assert result.score == 0.0

    def test_unrecognized_emotion_no_adjustment(self):
        reader = InMemorySessionStateReader(
            {
                "affective_now": {"raw": "boredom", "intensity": 0.9},
            }
        )
        ar = AffectiveRouting(state_reader=reader)
        result = ar.score(_make_request())
        assert result.score == 0.0
        assert "unrecognized_emotion" in result.reason

    def test_score_range_0_to_02(self):
        """Max score should be <= 0.2."""
        reader = InMemorySessionStateReader(
            {
                "affective_now": {"raw": "sadness", "intensity": 1.0},
            }
        )
        ar = AffectiveRouting(state_reader=reader)
        result = ar.score(_make_request())
        assert 0.0 <= result.score <= 0.2


# ===========================================================================
# CognitiveLoadRouting tests
# ===========================================================================


class TestCognitiveLoadRouting:
    """CognitiveLoadRouting: cognitive-load-aware soft scoring."""

    def test_no_state_reader_returns_neutral(self):
        clr = CognitiveLoadRouting(state_reader=None)
        result = clr.score(_make_request())
        assert result.score == 0.0
        assert "no_state_reader" in result.reason

    def test_missing_section_returns_neutral(self):
        reader = InMemorySessionStateReader()
        clr = CognitiveLoadRouting(state_reader=reader)
        result = clr.score(_make_request())
        assert result.score == 0.0

    def test_high_load_boost(self):
        reader = InMemorySessionStateReader(
            {
                "cognitive": {"load": 0.85},
            }
        )
        clr = CognitiveLoadRouting(state_reader=reader)
        result = clr.score(_make_request())
        assert result.score == pytest.approx(0.1)
        assert "high_load_boost" in result.reason

    def test_low_load_boost(self):
        reader = InMemorySessionStateReader(
            {
                "cognitive": {"load": 0.2},
            }
        )
        clr = CognitiveLoadRouting(state_reader=reader)
        result = clr.score(_make_request())
        assert result.score == pytest.approx(0.05)
        assert "low_load_boost" in result.reason

    def test_medium_load_neutral(self):
        reader = InMemorySessionStateReader(
            {
                "cognitive": {"load": 0.5},
            }
        )
        clr = CognitiveLoadRouting(state_reader=reader)
        result = clr.score(_make_request())
        assert result.score == 0.0
        assert "medium_load" in result.reason

    def test_load_at_high_threshold_gives_boost(self):
        """load == 0.7 is at threshold -> boost."""
        reader = InMemorySessionStateReader(
            {
                "cognitive": {"load": 0.7},
            }
        )
        clr = CognitiveLoadRouting(state_reader=reader)
        result = clr.score(_make_request())
        assert result.score == pytest.approx(0.1)

    def test_load_at_low_threshold_gives_boost(self):
        """load == 0.3 is at threshold -> boost."""
        reader = InMemorySessionStateReader(
            {
                "cognitive": {"load": 0.3},
            }
        )
        clr = CognitiveLoadRouting(state_reader=reader)
        result = clr.score(_make_request())
        assert result.score == pytest.approx(0.05)

    def test_complexity_tier_fallback_high(self):
        reader = InMemorySessionStateReader(
            {
                "cognitive": {"complexity_tier": "HIGH"},
            }
        )
        clr = CognitiveLoadRouting(state_reader=reader)
        result = clr.score(_make_request())
        assert result.score == pytest.approx(0.1)

    def test_complexity_tier_fallback_low(self):
        reader = InMemorySessionStateReader(
            {
                "cognitive": {"complexity_tier": "LOW"},
            }
        )
        clr = CognitiveLoadRouting(state_reader=reader)
        result = clr.score(_make_request())
        assert result.score == pytest.approx(0.05)

    def test_score_range_0_to_015(self):
        reader = InMemorySessionStateReader(
            {
                "cognitive": {"load": 1.0},
            }
        )
        clr = CognitiveLoadRouting(state_reader=reader)
        result = clr.score(_make_request())
        assert 0.0 <= result.score <= 0.15


# ===========================================================================
# QoSIntegration tests
# ===========================================================================


class TestQoSIntegration:
    """QoSIntegration: budget/latency-aware soft scoring."""

    def test_no_metadata_returns_neutral(self):
        qos = QoSIntegration()
        result = qos.score(_make_request())
        assert result.score == 0.0
        assert "no_provider_qos_metadata" in result.reason

    def test_cost_only(self):
        qos = QoSIntegration()
        result = qos.score(_make_request(), cost_per_call=0.5)
        assert result.score > 0.0
        assert result.score <= 0.2

    def test_latency_only(self):
        qos = QoSIntegration()
        result = qos.score(_make_request(), avg_latency_ms=1000)
        assert result.score > 0.0
        assert result.score <= 0.2

    def test_tight_budget_increases_cost_weight(self):
        """Tight budget (<20% remaining) should produce higher score for cheap providers."""
        qos = QoSIntegration()
        # Tight budget
        req_tight = _make_request(params={"budget_remaining_pct": 0.1})
        result_tight = qos.score(req_tight, cost_per_call=0.01)
        # Ample budget
        req_ample = _make_request(params={"budget_remaining_pct": 0.9})
        result_ample = qos.score(req_ample, cost_per_call=0.01)
        # Tight budget should yield higher score for cheap provider
        assert result_tight.score >= result_ample.score

    def test_tight_latency_increases_latency_weight(self):
        """Tight latency (<30% remaining) should produce higher score for fast providers."""
        qos = QoSIntegration()
        req_tight = _make_request(params={"latency_remaining_pct": 0.1})
        result_tight = qos.score(req_tight, avg_latency_ms=50)
        req_ample = _make_request(params={"latency_remaining_pct": 0.9})
        result_ample = qos.score(req_ample, avg_latency_ms=50)
        assert result_tight.score >= result_ample.score

    def test_score_max_02(self):
        """QoS score should never exceed 0.2."""
        qos = QoSIntegration()
        result = qos.score(
            _make_request(params={"budget_remaining_pct": 0.01}),
            cost_per_call=0.001,
            avg_latency_ms=1,
        )
        assert result.score <= 0.2


# ===========================================================================
# ToolScope tests
# ===========================================================================


class TestToolScope:
    """ToolScope: standalone sub-agent tool-scope enforcement."""

    def test_validate_allowed(self):
        scope = ToolScope(tools_granted=["tool.execute.weather", "tool.execute.calendar"])
        assert scope.validate("tool.execute.weather") is True

    def test_validate_denied_raises(self):
        scope = ToolScope(tools_granted=["tool.execute.weather"])
        with pytest.raises(AccessDeniedError):
            scope.validate("tool.execute.payments")

    def test_validate_empty_name_raises(self):
        scope = ToolScope(tools_granted=["tool.execute.weather"])
        with pytest.raises(AccessDeniedError):
            scope.validate("")

    def test_is_allowed_returns_bool(self):
        scope = ToolScope(tools_granted=["tool.execute.weather"])
        assert scope.is_allowed("tool.execute.weather") is True
        assert scope.is_allowed("tool.execute.payments") is False
        assert scope.is_allowed("") is False

    def test_empty_tools_granted_raises(self):
        with pytest.raises(ToolScopeError):
            ToolScope(tools_granted=[])

    def test_tools_granted_frozen(self):
        scope = ToolScope(tools_granted=["a", "b"])
        assert isinstance(scope.tools_granted, frozenset)
        assert scope.tools_granted == frozenset({"a", "b"})


# ===========================================================================
# PolicyEngine composite tests
# ===========================================================================


class TestPolicyEngine:
    """PolicyEngine: composite evaluation of all 4 dimensions."""

    def _build_engine(
        self,
        session_state: dict | None = None,
        rate_limits: dict | None = None,
        tools_granted: frozenset | None = None,
    ) -> PolicyEngine:
        reader = InMemorySessionStateReader(session_state or {})
        return PolicyEngine(
            security=SecurityContext(rate_limits=rate_limits),
            affective=AffectiveRouting(state_reader=reader),
            cognitive=CognitiveLoadRouting(state_reader=reader),
            qos=QoSIntegration(),
            tools_granted=tools_granted,
        )

    def test_composite_base_relevance_1(self):
        """With neutral state, composite score = base_relevance(1.0) + soft dimensions."""
        engine = self._build_engine()
        request = _make_request(safety_band="GREEN")
        contract = _make_contract(safety_band="GREEN")
        cfg = _make_provider_config()
        scored = engine.evaluate([cfg], contract, request)
        assert len(scored) == 1
        assert scored[0].policy_result.allowed is True
        # Base is 1.0, soft dimensions near-neutral -> score >= 1.0
        assert scored[0].policy_result.score >= 1.0

    def test_composite_with_affective_boost(self):
        """High sadness adds +0.1 to composite."""
        engine = self._build_engine(
            session_state={
                "affective_now": {"raw": "sadness", "intensity": 0.85},
            }
        )
        request = _make_request(safety_band="GREEN")
        contract = _make_contract(safety_band="GREEN")
        cfg = _make_provider_config()
        scored = engine.evaluate([cfg], contract, request)
        assert scored[0].policy_result.allowed is True
        assert scored[0].policy_result.score >= 1.1

    def test_composite_with_cognitive_boost(self):
        """High cognitive load adds +0.1 to composite."""
        engine = self._build_engine(
            session_state={
                "cognitive": {"load": 0.85},
            }
        )
        request = _make_request(safety_band="GREEN")
        contract = _make_contract(safety_band="GREEN")
        cfg = _make_provider_config()
        scored = engine.evaluate([cfg], contract, request)
        assert scored[0].policy_result.allowed is True
        assert scored[0].policy_result.score >= 1.1

    def test_composite_security_rejection(self):
        """Security hard gate denial -> allowed=False, score=0.0."""
        engine = self._build_engine()
        request = _make_request(safety_band="GREEN")
        contract = _make_contract(safety_band="AMBER")
        cfg = _make_provider_config()
        scored = engine.evaluate([cfg], contract, request)
        assert scored[0].policy_result.allowed is False
        assert scored[0].policy_result.score == 0.0

    def test_composite_multiple_candidates(self):
        """Engine evaluates each candidate independently."""
        engine = self._build_engine()
        request = _make_request(safety_band="GREEN")
        contract = _make_contract(safety_band="GREEN")
        configs = [_make_provider_config(provider_id=f"p{i}") for i in range(3)]
        scored = engine.evaluate(configs, contract, request)
        assert len(scored) == 3
        for s in scored:
            assert s.policy_result.allowed is True

    def test_composite_all_dimensions_active(self):
        """When all soft dimensions are active, composite > 1.0."""
        engine = self._build_engine(
            session_state={
                "affective_now": {"raw": "sadness", "intensity": 0.9},
                "cognitive": {"load": 0.85},
            }
        )
        request = _make_request(
            safety_band="GREEN",
            params={"budget_remaining_pct": 0.1},
        )
        contract = _make_contract(safety_band="GREEN")
        cfg = _make_provider_config(max_execution_ms=5000)
        scored = engine.evaluate([cfg], contract, request)
        # 1.0 + 0.1(affective) + 0.1(cognitive) + qos > 0
        assert scored[0].policy_result.score > 1.2

    def test_security_required(self):
        """PolicyEngine raises if SecurityContext is None."""
        with pytest.raises(ValueError, match="SecurityContext is required"):
            PolicyEngine(security=None)

    def test_optional_dimensions_none_graceful(self):
        """If affective/cognitive/qos are None, engine still works (0.0 scores)."""
        engine = PolicyEngine(security=SecurityContext())
        request = _make_request(safety_band="GREEN")
        contract = _make_contract(safety_band="GREEN")
        cfg = _make_provider_config()
        scored = engine.evaluate([cfg], contract, request)
        assert scored[0].policy_result.allowed is True
        assert scored[0].policy_result.score == pytest.approx(1.0)

    def test_reasons_contain_dimension_labels(self):
        """Composite reasons include affective=, cognitive=, qos= labels."""
        engine = self._build_engine()
        request = _make_request(safety_band="GREEN")
        contract = _make_contract(safety_band="GREEN")
        cfg = _make_provider_config()
        scored = engine.evaluate([cfg], contract, request)
        reasons = scored[0].policy_result.reasons
        assert any("affective=" in r for r in reasons)
        assert any("cognitive=" in r for r in reasons)
        assert any("qos=" in r for r in reasons)
