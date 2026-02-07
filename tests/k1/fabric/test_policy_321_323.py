"""
Integration tests for Epic 3.2.1-3.2.3:
  - 3.2.1: SecurityContext (hard gate)
  - 3.2.2: AffectiveRouting (soft score)
  - 3.2.3: CognitiveLoadRouting (soft score)

Covers:
  - Safety band access checks (FAB-06)
  - Tool-scope enforcement for sub-agents
  - Rate-limiting sliding window
  - Affective emotion-based routing scores
  - Cognitive load-based routing scores
  - Graceful degradation when SessionState unavailable
  - CapabilityRequest.safety_band field
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

import pytest

from k1.fabric.policy.affective_routing import AffectiveRouting, AffectiveScore
from k1.fabric.policy.cognitive_load_routing import CognitiveLoadRouting, CognitiveScore
from k1.fabric.policy.security_context import (
    AccessDeniedError,
    SecurityContext,
    SecurityContextError,
)
from k1.fabric.types import (
    Availability,
    CapabilityContract,
    CapabilityRequest,
    InputSpec,
    SafetyBand,
)

# =========================================================================
# Test Helpers
# =========================================================================


class FakeStateReader:
    """
    Fake ISessionStateReader that returns canned sections.

    Satisfies the ISessionStateReader Protocol via structural subtyping.
    """

    def __init__(self, sections: Optional[Dict[str, Dict[str, Any]]] = None) -> None:
        self._sections: Dict[str, Dict[str, Any]] = sections or {}

    def read_section(self, session_id: str, section: str) -> Optional[Dict[str, Any]]:
        key = f"{session_id}:{section}"
        # First try session-specific key, then fallback to section-only
        return self._sections.get(key) or self._sections.get(section)


def _request(
    capability_name: str = "tool.execute.weather",
    safety_band: str = SafetyBand.GREEN.value,
    session_id: str = "sess-1",
) -> CapabilityRequest:
    """Build a minimal CapabilityRequest."""
    return CapabilityRequest(
        capability_name=capability_name,
        caller="test",
        safety_band=safety_band,
        session_id=session_id,
    )


def _contract(
    name: str = "tool.execute.weather",
    safety_band_min: str = SafetyBand.GREEN.value,
) -> CapabilityContract:
    """Build a minimal CapabilityContract."""
    return CapabilityContract(
        name=name,
        version="1.0.0",
        domain=["WEATHER"],
        description="Weather tool",
        capabilities=["weather_lookup"],
        limitations=["none"],
        required_inputs=[InputSpec(name="loc", type="string", description="Location")],
        output={"type": "object"},
        provider_type="MCP",
        provider_id="mcp-weather",
        safety_band_min=safety_band_min,
        availability=Availability.ONLINE.value,
        avg_latency_ms=50,
    )


# =========================================================================
# 3.2.1 -- SecurityContext: Safety Band Checks
# =========================================================================


class TestSecurityContextBandAccess:
    """Safety band hard gate (FAB-06)."""

    def test_green_user_green_cap_allowed(self) -> None:
        sec = SecurityContext()
        result = sec.check_band("GREEN", "GREEN")
        assert result.allowed is True

    def test_amber_user_green_cap_allowed(self) -> None:
        sec = SecurityContext()
        result = sec.check_band("AMBER", "GREEN")
        assert result.allowed is True

    def test_crisis_user_red_cap_allowed(self) -> None:
        sec = SecurityContext()
        result = sec.check_band("CRISIS", "RED")
        assert result.allowed is True

    def test_green_user_amber_cap_denied(self) -> None:
        sec = SecurityContext()
        result = sec.check_band("GREEN", "AMBER")
        assert result.allowed is False
        assert "band_denied" in result.reasons[0]

    def test_amber_user_crisis_cap_denied(self) -> None:
        sec = SecurityContext()
        result = sec.check_band("AMBER", "CRISIS")
        assert result.allowed is False

    def test_invalid_user_band_denied(self) -> None:
        sec = SecurityContext()
        result = sec.check_band("INVALID", "GREEN")
        assert result.allowed is False
        assert "invalid user_band" in result.reasons[0]

    def test_invalid_cap_band_denied(self) -> None:
        sec = SecurityContext()
        result = sec.check_band("GREEN", "INVALID")
        assert result.allowed is False
        assert "invalid capability_band_min" in result.reasons[0]

    def test_all_bands_self_access(self) -> None:
        """Every band should be able to access capabilities at the same level."""
        sec = SecurityContext()
        for band in ("GREEN", "AMBER", "RED", "CRISIS"):
            result = sec.check_band(band, band)
            assert result.allowed is True, f"{band} should access {band}"


# =========================================================================
# 3.2.1 -- SecurityContext: Tool Scope Checks
# =========================================================================


class TestSecurityContextToolScope:
    """Sub-agent tool scoping enforcement."""

    def test_capability_in_granted_set(self) -> None:
        sec = SecurityContext()
        granted = frozenset(["tool.execute.weather", "tool.execute.news"])
        result = sec.check_tool_scope("tool.execute.weather", granted)
        assert result.allowed is True
        assert "scope_ok" in result.reasons[0]

    def test_capability_not_in_granted_set(self) -> None:
        sec = SecurityContext()
        granted = frozenset(["tool.execute.news"])
        result = sec.check_tool_scope("tool.execute.weather", granted)
        assert result.allowed is False
        assert "scope_denied" in result.reasons[0]

    def test_empty_granted_set_denies_all(self) -> None:
        sec = SecurityContext()
        result = sec.check_tool_scope("tool.execute.weather", frozenset())
        assert result.allowed is False


# =========================================================================
# 3.2.1 -- SecurityContext: Rate Limiting
# =========================================================================


class TestSecurityContextRateLimit:
    """Per-capability rate limiting with sliding window."""

    def test_no_limit_configured_passes(self) -> None:
        sec = SecurityContext()
        result = sec.check_rate_limit("tool.execute.weather")
        assert result.allowed is True
        assert "no limit" in result.reasons[0]

    def test_under_limit_passes(self) -> None:
        sec = SecurityContext(rate_limits={"tool.execute.weather": 5})
        for _ in range(4):
            result = sec.check_rate_limit("tool.execute.weather")
            assert result.allowed is True

    def test_at_limit_rejected(self) -> None:
        sec = SecurityContext(rate_limits={"tool.execute.weather": 3})
        for _ in range(3):
            sec.check_rate_limit("tool.execute.weather")
        result = sec.check_rate_limit("tool.execute.weather")
        assert result.allowed is False
        assert "rate_denied" in result.reasons[0]

    def test_different_capabilities_independent(self) -> None:
        sec = SecurityContext(rate_limits={"tool.execute.weather": 1, "tool.execute.news": 1})
        r1 = sec.check_rate_limit("tool.execute.weather")
        r2 = sec.check_rate_limit("tool.execute.news")
        assert r1.allowed is True
        assert r2.allowed is True

    def test_unconfigured_capability_passes(self) -> None:
        sec = SecurityContext(rate_limits={"tool.execute.weather": 1})
        result = sec.check_rate_limit("tool.execute.news")
        assert result.allowed is True


# =========================================================================
# 3.2.1 -- SecurityContext: Full Evaluate
# =========================================================================


class TestSecurityContextEvaluate:
    """Full evaluate() combining all checks."""

    def test_happy_path_no_scope_no_rate(self) -> None:
        sec = SecurityContext()
        req = _request(safety_band="AMBER")
        contract = _contract(safety_band_min="GREEN")
        result = sec.evaluate(req, contract)
        assert result.allowed is True
        assert len(result.reasons) >= 1

    def test_band_denied_stops_early(self) -> None:
        sec = SecurityContext()
        req = _request(safety_band="GREEN")
        contract = _contract(safety_band_min="AMBER")
        result = sec.evaluate(req, contract)
        assert result.allowed is False
        assert "band_denied" in result.reasons[0]

    def test_scope_denied_after_band_pass(self) -> None:
        sec = SecurityContext()
        req = _request(safety_band="GREEN", capability_name="tool.execute.weather")
        contract = _contract(safety_band_min="GREEN")
        result = sec.evaluate(req, contract, tools_granted=frozenset(["tool.execute.news"]))
        assert result.allowed is False
        assert any("scope_denied" in r for r in result.reasons)

    def test_scope_not_checked_when_none(self) -> None:
        """When tools_granted is None, scope check is skipped (not a sub-agent)."""
        sec = SecurityContext()
        req = _request(safety_band="GREEN")
        contract = _contract(safety_band_min="GREEN")
        result = sec.evaluate(req, contract, tools_granted=None)
        assert result.allowed is True

    def test_rate_denied_after_band_and_scope_pass(self) -> None:
        sec = SecurityContext(rate_limits={"tool.execute.weather": 1})
        req = _request(safety_band="GREEN", capability_name="tool.execute.weather")
        contract = _contract(safety_band_min="GREEN")
        granted = frozenset(["tool.execute.weather"])
        # First call passes
        r1 = sec.evaluate(req, contract, tools_granted=granted)
        assert r1.allowed is True
        # Second call hits rate limit
        r2 = sec.evaluate(req, contract, tools_granted=granted)
        assert r2.allowed is False
        assert any("rate_denied" in r for r in r2.reasons)

    def test_contract_without_safety_band_defaults_green(self) -> None:
        """PromptContract or contracts without safety_band_min default to GREEN."""
        sec = SecurityContext()
        req = _request(safety_band="GREEN")

        # Use a contract with no safety_band_min attr via mock
        @dataclass(frozen=True)
        class MinimalContract:
            name: str = "prompt.greeting"

        result = sec.evaluate(req, MinimalContract())  # type: ignore[arg-type]
        assert result.allowed is True


# =========================================================================
# 3.2.1 -- SecurityContext: Exception Hierarchy
# =========================================================================


class TestSecurityContextExceptions:

    def test_access_denied_is_security_context_error(self) -> None:
        assert issubclass(AccessDeniedError, SecurityContextError)

    def test_access_denied_attributes(self) -> None:
        err = AccessDeniedError(check="band", detail="GREEN < AMBER")
        assert err.check == "band"
        assert err.detail == "GREEN < AMBER"
        assert "band" in str(err)


# =========================================================================
# 3.2.2 -- AffectiveRouting: No State Reader
# =========================================================================


class TestAffectiveRoutingNoReader:
    """Graceful degradation when ISessionStateReader is None."""

    def test_no_reader_returns_zero(self) -> None:
        ar = AffectiveRouting(state_reader=None)
        result = ar.score(_request())
        assert result.score == 0.0
        assert result.reason == "no_state_reader"


# =========================================================================
# 3.2.2 -- AffectiveRouting: With State Reader
# =========================================================================


class TestAffectiveRoutingWithReader:
    """Emotion-based soft scoring."""

    def test_section_unavailable_returns_zero(self) -> None:
        reader = FakeStateReader(sections={})
        ar = AffectiveRouting(state_reader=reader)
        result = ar.score(_request())
        assert result.score == 0.0
        assert "unavailable" in result.reason

    def test_high_sadness_returns_0_1(self) -> None:
        reader = FakeStateReader(sections={"affective_now": {"raw": "sadness", "intensity": 0.85}})
        ar = AffectiveRouting(state_reader=reader)
        result = ar.score(_request())
        assert result.score == pytest.approx(0.10)
        assert "sad_anxious_boost" in result.reason

    def test_high_anxiety_returns_0_1(self) -> None:
        reader = FakeStateReader(sections={"affective_now": {"raw": "anxiety", "intensity": 0.9}})
        ar = AffectiveRouting(state_reader=reader)
        result = ar.score(_request())
        assert result.score == pytest.approx(0.10)

    def test_high_joy_returns_0_05(self) -> None:
        reader = FakeStateReader(sections={"affective_now": {"raw": "joy", "intensity": 0.8}})
        ar = AffectiveRouting(state_reader=reader)
        result = ar.score(_request())
        assert result.score == pytest.approx(0.05)
        assert "joy_excited_boost" in result.reason

    def test_high_excitement_returns_0_05(self) -> None:
        reader = FakeStateReader(
            sections={"affective_now": {"raw": "excitement", "intensity": 0.75}}
        )
        ar = AffectiveRouting(state_reader=reader)
        result = ar.score(_request())
        assert result.score == pytest.approx(0.05)

    def test_low_intensity_sadness_returns_zero(self) -> None:
        """Below threshold, even sad emotions produce no adjustment."""
        reader = FakeStateReader(sections={"affective_now": {"raw": "sadness", "intensity": 0.5}})
        ar = AffectiveRouting(state_reader=reader)
        result = ar.score(_request())
        assert result.score == 0.0
        assert "low_intensity" in result.reason

    def test_neutral_emotion_returns_zero(self) -> None:
        reader = FakeStateReader(sections={"affective_now": {"raw": "neutral", "intensity": 0.2}})
        ar = AffectiveRouting(state_reader=reader)
        result = ar.score(_request())
        assert result.score == 0.0

    def test_unrecognized_high_emotion_returns_zero(self) -> None:
        reader = FakeStateReader(sections={"affective_now": {"raw": "confusion", "intensity": 0.9}})
        ar = AffectiveRouting(state_reader=reader)
        result = ar.score(_request())
        assert result.score == 0.0
        assert "unrecognized" in result.reason

    def test_missing_intensity_returns_zero(self) -> None:
        reader = FakeStateReader(sections={"affective_now": {"raw": "sadness"}})
        ar = AffectiveRouting(state_reader=reader)
        result = ar.score(_request())
        assert result.score == 0.0

    def test_invalid_intensity_returns_zero(self) -> None:
        reader = FakeStateReader(
            sections={"affective_now": {"raw": "sadness", "intensity": "not_a_number"}}
        )
        ar = AffectiveRouting(state_reader=reader)
        result = ar.score(_request())
        assert result.score == 0.0

    def test_boundary_intensity_0_7_returns_zero(self) -> None:
        """Exactly at threshold (0.7) is NOT above it."""
        reader = FakeStateReader(sections={"affective_now": {"raw": "sadness", "intensity": 0.7}})
        ar = AffectiveRouting(state_reader=reader)
        result = ar.score(_request())
        assert result.score == 0.0

    def test_score_result_is_frozen(self) -> None:
        result = AffectiveScore(score=0.1, reason="test")
        with pytest.raises(AttributeError):
            result.score = 0.5  # type: ignore[misc]


# =========================================================================
# 3.2.3 -- CognitiveLoadRouting: No State Reader
# =========================================================================


class TestCognitiveLoadNoReader:
    """Graceful degradation when ISessionStateReader is None."""

    def test_no_reader_returns_zero(self) -> None:
        clr = CognitiveLoadRouting(state_reader=None)
        result = clr.score(_request())
        assert result.score == 0.0
        assert result.reason == "no_state_reader"


# =========================================================================
# 3.2.3 -- CognitiveLoadRouting: With State Reader
# =========================================================================


class TestCognitiveLoadWithReader:
    """Cognitive load-based soft scoring."""

    def test_section_unavailable_returns_zero(self) -> None:
        reader = FakeStateReader(sections={})
        clr = CognitiveLoadRouting(state_reader=reader)
        result = clr.score(_request())
        assert result.score == 0.0
        assert "unavailable" in result.reason

    def test_high_load_returns_0_1(self) -> None:
        reader = FakeStateReader(sections={"cognitive": {"load": 0.85, "complexity_tier": "HIGH"}})
        clr = CognitiveLoadRouting(state_reader=reader)
        result = clr.score(_request())
        assert result.score == pytest.approx(0.10)
        assert "high_load_boost" in result.reason

    def test_low_load_returns_0_05(self) -> None:
        reader = FakeStateReader(sections={"cognitive": {"load": 0.2, "complexity_tier": "LOW"}})
        clr = CognitiveLoadRouting(state_reader=reader)
        result = clr.score(_request())
        assert result.score == pytest.approx(0.05)
        assert "low_load_boost" in result.reason

    def test_medium_load_returns_zero(self) -> None:
        reader = FakeStateReader(sections={"cognitive": {"load": 0.5, "complexity_tier": "MEDIUM"}})
        clr = CognitiveLoadRouting(state_reader=reader)
        result = clr.score(_request())
        assert result.score == 0.0
        assert "medium_load" in result.reason

    def test_boundary_high_0_7_returns_boost(self) -> None:
        """Exactly at 0.7 is >= threshold."""
        reader = FakeStateReader(sections={"cognitive": {"load": 0.7}})
        clr = CognitiveLoadRouting(state_reader=reader)
        result = clr.score(_request())
        assert result.score == pytest.approx(0.10)

    def test_boundary_low_0_3_returns_boost(self) -> None:
        """Exactly at 0.3 is <= low threshold."""
        reader = FakeStateReader(sections={"cognitive": {"load": 0.3}})
        clr = CognitiveLoadRouting(state_reader=reader)
        result = clr.score(_request())
        assert result.score == pytest.approx(0.05)

    def test_load_clamped_above_1(self) -> None:
        reader = FakeStateReader(sections={"cognitive": {"load": 1.5}})
        clr = CognitiveLoadRouting(state_reader=reader)
        result = clr.score(_request())
        assert result.score == pytest.approx(0.10)

    def test_load_clamped_below_0(self) -> None:
        reader = FakeStateReader(sections={"cognitive": {"load": -0.5}})
        clr = CognitiveLoadRouting(state_reader=reader)
        result = clr.score(_request())
        assert result.score == pytest.approx(0.05)

    # --- Tier fallback tests ---

    def test_tier_fallback_high(self) -> None:
        """When load is absent, falls back to complexity_tier."""
        reader = FakeStateReader(sections={"cognitive": {"complexity_tier": "HIGH"}})
        clr = CognitiveLoadRouting(state_reader=reader)
        result = clr.score(_request())
        assert result.score == pytest.approx(0.10)
        assert "high_tier_boost" in result.reason

    def test_tier_fallback_low(self) -> None:
        reader = FakeStateReader(sections={"cognitive": {"complexity_tier": "LOW"}})
        clr = CognitiveLoadRouting(state_reader=reader)
        result = clr.score(_request())
        assert result.score == pytest.approx(0.05)

    def test_tier_fallback_medium(self) -> None:
        reader = FakeStateReader(sections={"cognitive": {"complexity_tier": "MEDIUM"}})
        clr = CognitiveLoadRouting(state_reader=reader)
        result = clr.score(_request())
        assert result.score == 0.0

    def test_tier_fallback_empty(self) -> None:
        reader = FakeStateReader(sections={"cognitive": {}})
        clr = CognitiveLoadRouting(state_reader=reader)
        result = clr.score(_request())
        assert result.score == 0.0
        assert "neutral_tier" in result.reason

    def test_invalid_load_falls_back_to_tier(self) -> None:
        reader = FakeStateReader(
            sections={"cognitive": {"load": "not_a_number", "complexity_tier": "HIGH"}}
        )
        clr = CognitiveLoadRouting(state_reader=reader)
        result = clr.score(_request())
        assert result.score == pytest.approx(0.10)

    def test_score_result_is_frozen(self) -> None:
        result = CognitiveScore(score=0.1, reason="test")
        with pytest.raises(AttributeError):
            result.score = 0.5  # type: ignore[misc]


# =========================================================================
# Cross-cutting: CapabilityRequest.safety_band field
# =========================================================================


class TestCapabilityRequestSafetyBand:
    """Verify safety_band field on CapabilityRequest."""

    def test_default_is_green(self) -> None:
        req = CapabilityRequest(capability_name="tool.execute.x", caller="test")
        assert req.safety_band == SafetyBand.GREEN.value

    def test_explicit_safety_band(self) -> None:
        req = CapabilityRequest(
            capability_name="tool.execute.x",
            caller="test",
            safety_band=SafetyBand.AMBER.value,
        )
        assert req.safety_band == "AMBER"

    def test_to_dict_includes_safety_band(self) -> None:
        req = CapabilityRequest(
            capability_name="tool.execute.x",
            caller="test",
            safety_band="RED",
        )
        d = req.to_dict()
        assert d["safety_band"] == "RED"

    def test_from_dict_restores_safety_band(self) -> None:
        d = {"capability_name": "tool.execute.x", "caller": "test", "safety_band": "CRISIS"}
        req = CapabilityRequest.from_dict(d)
        assert req.safety_band == "CRISIS"

    def test_from_dict_defaults_green(self) -> None:
        d = {"capability_name": "tool.execute.x", "caller": "test"}
        req = CapabilityRequest.from_dict(d)
        assert req.safety_band == "GREEN"


# =========================================================================
# Cross-cutting: Package imports
# =========================================================================


class TestPolicyPackageExports:
    """Verify k1.fabric.policy re-exports all public symbols."""

    def test_all_symbols_importable(self) -> None:
        from k1.fabric.policy import (  # noqa: F401
            AccessDeniedError,
            AffectiveRouting,
            AffectiveScore,
            CognitiveLoadRouting,
            CognitiveScore,
            ISessionStateReader,
            SecurityCheckResult,
            SecurityContext,
            SecurityContextError,
        )
