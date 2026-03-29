"""
Epic 6.3.17 -- Test AgentResponsePayload and result merging.

Tests the standard agent output envelope (4.5.8):
  - Frozen dataclass construction and field defaults
  - to_dict() / from_dict() roundtrip fidelity
  - validate() boundary conditions
  - Integration with CapabilityResult.data["payload"]
  - Multi-agent confidence aggregation / domain union / source merge
  - Concierge consumption pattern

NO MOCKS. All assertions against real dataclass instances.

References:
  - fabric-implementation-plan.md Epic 6.3, Issue 6.3.17
  - k1/fabric/types.py AgentResponsePayload (line 1718)
"""

from __future__ import annotations

from typing import Any, Dict, List

import pytest

from k1.fabric.types import AgentResponsePayload, CapabilityResult

# ===================================================================
# Helpers
# ===================================================================


def _make_payload(**overrides: Any) -> AgentResponsePayload:
    """Build a valid AgentResponsePayload with sensible defaults."""
    defaults: Dict[str, Any] = {
        "answer": "Your blood pressure is within normal range.",
        "confidence": 0.85,
        "domain": ("HEALTH",),
        "sources": ({"type": "measurement", "name": "bp_reading", "ts": "2026-02-08"},),
        "domain_data": {"vitals": {"systolic": 120, "diastolic": 80}},
        "follow_up_needed": False,
        "follow_up_suggestion": "",
        "reasoning_trace": ("retrieved vitals", "compared to baseline"),
        "tools_used": ("tool.read.check_vitals",),
        "k0_queries_made": 2,
    }
    defaults.update(overrides)
    return AgentResponsePayload(**defaults)


def _aggregate_payloads(payloads: List[AgentResponsePayload]) -> Dict[str, Any]:
    """
    Aggregate multiple AgentResponsePayload instances.

    Logic (matches Concierge aggregation spec):
      - confidence = average of all payloads
      - domain = union of all domains (preserving order, deduped)
      - sources = concatenation of all sources
      - follow_up_needed = True if ANY payload sets it
      - answer = joined answers (newline-separated)
      - domain_data = merged dict (later payloads override on key conflict)
      - tools_used = union
      - reasoning_trace = concatenation
      - k0_queries_made = sum
    """
    if len(payloads) == 0:
        return AgentResponsePayload().to_dict()
    if len(payloads) == 1:
        return payloads[0].to_dict()

    total_confidence = sum(p.confidence for p in payloads)
    avg_confidence = total_confidence / len(payloads)

    seen_domains: list[str] = []
    for p in payloads:
        for d in p.domain:
            if d not in seen_domains:
                seen_domains.append(d)

    all_sources: list[dict] = []
    for p in payloads:
        all_sources.extend(p.sources)

    merged_domain_data: Dict[str, Any] = {}
    for p in payloads:
        merged_domain_data.update(p.domain_data)

    follow_up = any(p.follow_up_needed for p in payloads)
    suggestions = [p.follow_up_suggestion for p in payloads if p.follow_up_suggestion]

    all_answers = [p.answer for p in payloads if p.answer.strip()]
    all_trace: list[str] = []
    for p in payloads:
        all_trace.extend(p.reasoning_trace)

    seen_tools: list[str] = []
    for p in payloads:
        for t in p.tools_used:
            if t not in seen_tools:
                seen_tools.append(t)

    total_k0 = sum(p.k0_queries_made for p in payloads)

    return {
        "answer": "\n".join(all_answers),
        "confidence": round(avg_confidence, 10),
        "domain": seen_domains,
        "sources": all_sources,
        "domain_data": merged_domain_data,
        "follow_up_needed": follow_up,
        "follow_up_suggestion": "; ".join(suggestions) if suggestions else "",
        "reasoning_trace": all_trace,
        "tools_used": seen_tools,
        "k0_queries_made": total_k0,
    }


# ===================================================================
# 1. Construction and immutability
# ===================================================================


class TestPayloadConstruction:
    """AgentResponsePayload frozen dataclass construction."""

    def test_default_construction(self) -> None:
        """Default payload has empty/zero fields."""
        p = AgentResponsePayload()
        assert p.answer == ""
        assert p.confidence == 0.0
        assert p.domain == ()
        assert p.sources == ()
        assert p.domain_data == {}
        assert p.follow_up_needed is False
        assert p.follow_up_suggestion == ""
        assert p.reasoning_trace == ()
        assert p.tools_used == ()
        assert p.k0_queries_made == 0

    def test_full_construction(self) -> None:
        """Payload with all fields populated."""
        p = _make_payload()
        assert p.answer == "Your blood pressure is within normal range."
        assert p.confidence == 0.85
        assert p.domain == ("HEALTH",)
        assert len(p.sources) == 1
        assert p.sources[0]["type"] == "measurement"
        assert p.domain_data["vitals"]["systolic"] == 120
        assert p.follow_up_needed is False
        assert p.tools_used == ("tool.read.check_vitals",)
        assert p.k0_queries_made == 2

    def test_frozen_immutability(self) -> None:
        """Payload fields cannot be mutated after construction."""
        p = _make_payload()
        with pytest.raises(AttributeError):
            p.answer = "mutated"  # type: ignore[misc]
        with pytest.raises(AttributeError):
            p.confidence = 0.99  # type: ignore[misc]
        with pytest.raises(AttributeError):
            p.domain = ("MUTATED",)  # type: ignore[misc]

    def test_multi_domain(self) -> None:
        """Payload with multiple domain tags."""
        p = _make_payload(domain=("HEALTH", "WELLNESS", "FITNESS"))
        assert len(p.domain) == 3
        assert "WELLNESS" in p.domain

    def test_empty_sources(self) -> None:
        """Payload with no sources is valid structurally."""
        p = _make_payload(sources=())
        assert p.sources == ()

    def test_multiple_sources(self) -> None:
        """Multiple source dicts preserved."""
        sources = (
            {"type": "api", "name": "fitbit"},
            {"type": "sensor", "name": "bp_cuff"},
            {"type": "record", "name": "ehr"},
        )
        p = _make_payload(sources=sources)
        assert len(p.sources) == 3
        assert p.sources[1]["name"] == "bp_cuff"


# ===================================================================
# 2. to_dict() serialization
# ===================================================================


class TestToDict:
    """to_dict() produces JSON-safe dict."""

    def test_to_dict_all_fields(self) -> None:
        """All fields serialized, tuples become lists."""
        p = _make_payload()
        d = p.to_dict()
        assert isinstance(d, dict)
        assert isinstance(d["domain"], list)
        assert isinstance(d["sources"], list)
        assert isinstance(d["reasoning_trace"], list)
        assert isinstance(d["tools_used"], list)
        assert d["answer"] == p.answer
        assert d["confidence"] == p.confidence
        assert d["k0_queries_made"] == 2

    def test_to_dict_default_payload(self) -> None:
        """Default payload to_dict produces empty/zero values."""
        d = AgentResponsePayload().to_dict()
        assert d["answer"] == ""
        assert d["confidence"] == 0.0
        assert d["domain"] == []
        assert d["sources"] == []
        assert d["domain_data"] == {}

    def test_to_dict_deep_copies_domain_data(self) -> None:
        """domain_data in to_dict is a copy, not a reference."""
        p = _make_payload()
        d = p.to_dict()
        d["domain_data"]["injected"] = True
        # Original must be unaffected
        assert "injected" not in p.domain_data

    def test_to_dict_deep_copies_sources(self) -> None:
        """sources in to_dict are copies."""
        p = _make_payload()
        d = p.to_dict()
        d["sources"][0]["injected"] = True
        assert "injected" not in p.sources[0]

    def test_to_dict_json_safe(self) -> None:
        """to_dict output can be serialized to JSON without error."""
        import json

        p = _make_payload()
        serialized = json.dumps(p.to_dict())
        assert isinstance(serialized, str)
        assert len(serialized) > 0


# ===================================================================
# 3. from_dict() deserialization
# ===================================================================


class TestFromDict:
    """from_dict() classmethod factory with type coercion."""

    def test_roundtrip_equality(self) -> None:
        """to_dict -> from_dict roundtrip produces equal payload."""
        p1 = _make_payload()
        d = p1.to_dict()
        p2 = AgentResponsePayload.from_dict(d)
        assert p1 == p2

    def test_roundtrip_with_complex_domain_data(self) -> None:
        """Complex nested domain_data survives roundtrip."""
        domain_data = {
            "vitals": {"heart_rate": 72, "bp": {"systolic": 120, "diastolic": 80}},
            "medications": [{"name": "aspirin", "dose_mg": 81}],
            "flags": {"critical": False, "reviewed": True},
        }
        p1 = _make_payload(domain_data=domain_data)
        d = p1.to_dict()
        p2 = AgentResponsePayload.from_dict(d)
        assert p2.domain_data["vitals"]["heart_rate"] == 72
        assert p2.domain_data["vitals"]["bp"]["systolic"] == 120
        assert p2.domain_data["medications"][0]["name"] == "aspirin"
        assert p2.domain_data["flags"]["critical"] is False

    def test_from_dict_coerces_lists_to_tuples(self) -> None:
        """Lists in dict are coerced to tuples for tuple fields."""
        raw = {
            "answer": "Test",
            "confidence": 0.5,
            "domain": ["A", "B"],
            "sources": [{"x": 1}],
            "reasoning_trace": ["step1"],
            "tools_used": ["tool.execute.a"],
        }
        p = AgentResponsePayload.from_dict(raw)
        assert isinstance(p.domain, tuple)
        assert isinstance(p.sources, tuple)
        assert isinstance(p.reasoning_trace, tuple)
        assert isinstance(p.tools_used, tuple)

    def test_from_dict_missing_fields_defaults(self) -> None:
        """Missing fields get defaults (empty/zero)."""
        p = AgentResponsePayload.from_dict({})
        assert p.answer == ""
        assert p.confidence == 0.0
        assert p.domain == ()
        assert p.sources == ()
        assert p.domain_data == {}
        assert p.follow_up_needed is False
        assert p.k0_queries_made == 0

    def test_from_dict_type_coercion(self) -> None:
        """Numeric strings are coerced to proper types."""
        raw = {"confidence": "0.75", "k0_queries_made": "3", "answer": 42}
        p = AgentResponsePayload.from_dict(raw)
        assert p.confidence == 0.75
        assert p.k0_queries_made == 3
        assert p.answer == "42"

    def test_from_dict_preserves_follow_up(self) -> None:
        """follow_up fields survive roundtrip."""
        p1 = _make_payload(
            follow_up_needed=True,
            follow_up_suggestion="Schedule a follow-up in 2 weeks",
        )
        d = p1.to_dict()
        p2 = AgentResponsePayload.from_dict(d)
        assert p2.follow_up_needed is True
        assert p2.follow_up_suggestion == "Schedule a follow-up in 2 weeks"


# ===================================================================
# 4. validate() boundary conditions
# ===================================================================


class TestValidate:
    """validate() checks confidence, domain, answer."""

    def test_valid_payload_passes(self) -> None:
        """Valid payload with all rules satisfied."""
        p = _make_payload()
        assert p.validate() is True

    def test_confidence_exactly_zero(self) -> None:
        """confidence=0.0 is valid (lower bound)."""
        p = _make_payload(confidence=0.0)
        assert p.validate() is True

    def test_confidence_exactly_one(self) -> None:
        """confidence=1.0 is valid (upper bound)."""
        p = _make_payload(confidence=1.0)
        assert p.validate() is True

    def test_confidence_above_one_fails(self) -> None:
        """confidence > 1.0 fails validation."""
        p = _make_payload(confidence=1.01)
        assert p.validate() is False

    def test_confidence_negative_fails(self) -> None:
        """confidence < 0.0 fails validation."""
        p = _make_payload(confidence=-0.1)
        assert p.validate() is False

    def test_empty_domain_fails(self) -> None:
        """Empty domain tuple fails validation."""
        p = _make_payload(domain=())
        assert p.validate() is False

    def test_empty_answer_fails(self) -> None:
        """Empty answer string fails validation."""
        p = _make_payload(answer="")
        assert p.validate() is False

    def test_whitespace_only_answer_fails(self) -> None:
        """Answer with only whitespace fails validation."""
        p = _make_payload(answer="   \n\t  ")
        assert p.validate() is False

    def test_minimal_valid_payload(self) -> None:
        """Minimal payload with just required fields passes."""
        p = AgentResponsePayload(
            answer="Yes",
            confidence=0.5,
            domain=("GENERAL",),
        )
        assert p.validate() is True

    def test_confidence_boundary_0999(self) -> None:
        """confidence=0.999 is valid."""
        p = _make_payload(confidence=0.999)
        assert p.validate() is True


# ===================================================================
# 5. domain_data freeform storage
# ===================================================================


class TestDomainDataFreeform:
    """domain_data supports arbitrary nested structures."""

    def test_complex_nested_structure(self) -> None:
        """Complex nested dict with lists and bools survives roundtrip."""
        domain_data = {
            "vitals": {"heart_rate": 72},
            "medications": [{"name": "aspirin"}],
            "flags": {"reviewed": True},
        }
        p = _make_payload(domain_data=domain_data)
        d = p.to_dict()
        reconstructed = AgentResponsePayload.from_dict(d)
        assert reconstructed.domain_data["vitals"]["heart_rate"] == 72
        assert reconstructed.domain_data["medications"][0]["name"] == "aspirin"
        assert reconstructed.domain_data["flags"]["reviewed"] is True

    def test_deeply_nested_data(self) -> None:
        """4 levels of nesting preserved."""
        domain_data = {
            "level1": {
                "level2": {
                    "level3": {
                        "level4": "deep_value",
                    }
                }
            }
        }
        p = _make_payload(domain_data=domain_data)
        rt = AgentResponsePayload.from_dict(p.to_dict())
        assert rt.domain_data["level1"]["level2"]["level3"]["level4"] == "deep_value"

    def test_empty_domain_data(self) -> None:
        """Empty domain_data roundtrips cleanly."""
        p = _make_payload(domain_data={})
        d = p.to_dict()
        rt = AgentResponsePayload.from_dict(d)
        assert rt.domain_data == {}

    def test_numeric_values_in_domain_data(self) -> None:
        """Numeric values (int, float) preserved in domain_data."""
        domain_data = {"temperature": 98.6, "steps": 10234, "sleep_hours": 7.5}
        p = _make_payload(domain_data=domain_data)
        rt = AgentResponsePayload.from_dict(p.to_dict())
        assert rt.domain_data["temperature"] == 98.6
        assert rt.domain_data["steps"] == 10234


# ===================================================================
# 6. Integration with CapabilityResult
# ===================================================================


class TestCapabilityResultIntegration:
    """Payload embedded in CapabilityResult.data["payload"]."""

    def test_wrap_in_success_result(self) -> None:
        """Payload wrappable in CapabilityResult.success via to_dict()."""
        payload = _make_payload()
        result = CapabilityResult.success_result(
            request_id="req-001",
            data={"payload": payload.to_dict()},
            provider_id="test-agent-provider",
            trace_id="trace-001",
        )
        assert result.success is True
        assert "payload" in result.data
        assert result.data["payload"]["answer"] == payload.answer

    def test_extract_and_reconstruct(self) -> None:
        """from_dict() reconstructs payload from result.data["payload"]."""
        payload = _make_payload()
        result = CapabilityResult.success_result(
            request_id="req-002",
            data={"payload": payload.to_dict()},
            provider_id="agent-001",
            trace_id="trace-002",
        )
        extracted = AgentResponsePayload.from_dict(result.data["payload"])
        assert extracted == payload
        assert extracted.confidence == 0.85
        assert extracted.domain == ("HEALTH",)

    def test_result_data_contains_both_payload_and_metadata(self) -> None:
        """result.data can contain payload alongside other metadata."""
        payload = _make_payload()
        result = CapabilityResult.success_result(
            request_id="req-003",
            data={
                "payload": payload.to_dict(),
                "agent_name": "agent.execute.health_checker",
                "execution_ms": 1500,
            },
            provider_id="agent-001",
            trace_id="trace-003",
        )
        assert result.data["agent_name"] == "agent.execute.health_checker"
        assert result.data["execution_ms"] == 1500
        extracted = AgentResponsePayload.from_dict(result.data["payload"])
        assert extracted.answer == payload.answer

    def test_failure_result_has_no_payload(self) -> None:
        """Failed results have no data (and thus no payload)."""
        result = CapabilityResult.failure_result(
            request_id="req-004",
            error_code="agent_error",
            error_message="Agent execution failed",
        )
        assert result.success is False
        assert result.data is None


# ===================================================================
# 7. Multi-agent aggregation
# ===================================================================


class TestMultiAgentAggregation:
    """Aggregation of multiple AgentResponsePayload instances."""

    def test_confidence_averaging_three_agents(self) -> None:
        """Confidence averaged across 3 payloads: (0.9+0.8+0.7)/3."""
        p1 = _make_payload(confidence=0.9, domain=("HEALTH",), answer="Health ok")
        p2 = _make_payload(confidence=0.8, domain=("FINANCE",), answer="Budget ok")
        p3 = _make_payload(confidence=0.7, domain=("SCHEDULING",), answer="Free at 3pm")
        agg = _aggregate_payloads([p1, p2, p3])
        expected = round((0.9 + 0.8 + 0.7) / 3, 10)
        assert agg["confidence"] == pytest.approx(expected, abs=1e-9)

    def test_domain_union(self) -> None:
        """Domains are unioned across all payloads, deduplicated."""
        p1 = _make_payload(domain=("HEALTH", "WELLNESS"))
        p2 = _make_payload(domain=("HEALTH", "FINANCE"))
        p3 = _make_payload(domain=("SCHEDULING",))
        agg = _aggregate_payloads([p1, p2, p3])
        assert set(agg["domain"]) == {"HEALTH", "WELLNESS", "FINANCE", "SCHEDULING"}

    def test_sources_merged(self) -> None:
        """All sources concatenated."""
        p1 = _make_payload(sources=({"name": "s1"},))
        p2 = _make_payload(sources=({"name": "s2"}, {"name": "s3"}))
        agg = _aggregate_payloads([p1, p2])
        assert len(agg["sources"]) == 3

    def test_follow_up_or_logic(self) -> None:
        """follow_up_needed=True if ANY payload sets it."""
        p1 = _make_payload(follow_up_needed=False)
        p2 = _make_payload(follow_up_needed=True, follow_up_suggestion="Check again in 1 week")
        p3 = _make_payload(follow_up_needed=False)
        agg = _aggregate_payloads([p1, p2, p3])
        assert agg["follow_up_needed"] is True
        assert "Check again in 1 week" in agg["follow_up_suggestion"]

    def test_all_follow_up_false(self) -> None:
        """follow_up_needed=False when no payload sets it."""
        p1 = _make_payload(follow_up_needed=False)
        p2 = _make_payload(follow_up_needed=False)
        agg = _aggregate_payloads([p1, p2])
        assert agg["follow_up_needed"] is False

    def test_single_agent_passthrough(self) -> None:
        """Single agent: no aggregation needed, passthrough."""
        p1 = _make_payload(confidence=0.95, domain=("HEALTH",))
        agg = _aggregate_payloads([p1])
        assert agg["confidence"] == 0.95
        assert agg["domain"] == ["HEALTH"]

    def test_domain_data_merged(self) -> None:
        """domain_data merged from all payloads (later overrides)."""
        p1 = _make_payload(domain_data={"vitals": {"hr": 72}})
        p2 = _make_payload(domain_data={"finance": {"balance": 1500}})
        agg = _aggregate_payloads([p1, p2])
        assert agg["domain_data"]["vitals"]["hr"] == 72
        assert agg["domain_data"]["finance"]["balance"] == 1500

    def test_tools_used_union(self) -> None:
        """tools_used unioned and deduplicated."""
        p1 = _make_payload(tools_used=("tool.read.a", "tool.read.b"))
        p2 = _make_payload(tools_used=("tool.read.b", "tool.read.c"))
        agg = _aggregate_payloads([p1, p2])
        assert set(agg["tools_used"]) == {"tool.read.a", "tool.read.b", "tool.read.c"}

    def test_k0_queries_summed(self) -> None:
        """k0_queries_made summed across payloads."""
        p1 = _make_payload(k0_queries_made=3)
        p2 = _make_payload(k0_queries_made=5)
        agg = _aggregate_payloads([p1, p2])
        assert agg["k0_queries_made"] == 8

    def test_answers_joined(self) -> None:
        """Answers from all payloads joined with newlines."""
        p1 = _make_payload(answer="Blood pressure normal.")
        p2 = _make_payload(answer="Budget on track.")
        agg = _aggregate_payloads([p1, p2])
        assert "Blood pressure normal." in agg["answer"]
        assert "Budget on track." in agg["answer"]


# ===================================================================
# 8. Concierge consumption pattern
# ===================================================================


class TestConciergeConsumption:
    """Simulate Concierge reading agent results."""

    def test_concierge_reads_answer(self) -> None:
        """Concierge accesses result.data['payload']['answer']."""
        payload = _make_payload(answer="Your vitals look great!")
        result = CapabilityResult.success_result(
            request_id="req-concierge-001",
            data={"payload": payload.to_dict()},
            provider_id="agent-health",
            trace_id="trace-concierge-001",
        )
        answer = result.data["payload"]["answer"]
        assert answer == "Your vitals look great!"

    def test_concierge_reads_domain_data(self) -> None:
        """Concierge accesses result.data['payload']['domain_data']."""
        domain_data = {"vitals": {"heart_rate": 72}, "medications": [{"name": "aspirin"}]}
        payload = _make_payload(domain_data=domain_data)
        result = CapabilityResult.success_result(
            request_id="req-concierge-002",
            data={"payload": payload.to_dict()},
            provider_id="agent-health",
            trace_id="trace-concierge-002",
        )
        dd = result.data["payload"]["domain_data"]
        assert dd["vitals"]["heart_rate"] == 72
        assert dd["medications"][0]["name"] == "aspirin"

    def test_concierge_reads_sources(self) -> None:
        """Concierge accesses result.data['payload']['sources']."""
        sources = (
            {"type": "api", "endpoint": "fitbit/heart"},
            {"type": "ehr", "record_id": "R-001"},
        )
        payload = _make_payload(sources=sources)
        result = CapabilityResult.success_result(
            request_id="req-concierge-003",
            data={"payload": payload.to_dict()},
            provider_id="agent-health",
            trace_id="trace-concierge-003",
        )
        s = result.data["payload"]["sources"]
        assert len(s) == 2
        assert s[0]["type"] == "api"
        assert s[1]["record_id"] == "R-001"

    def test_concierge_reads_confidence_and_follow_up(self) -> None:
        """Concierge reads confidence and follow_up fields for routing."""
        payload = _make_payload(
            confidence=0.6,
            follow_up_needed=True,
            follow_up_suggestion="Consult a doctor",
        )
        result = CapabilityResult.success_result(
            request_id="req-concierge-004",
            data={"payload": payload.to_dict()},
            provider_id="agent-health",
            trace_id="trace-concierge-004",
        )
        pd = result.data["payload"]
        assert pd["confidence"] == 0.6
        assert pd["follow_up_needed"] is True
        assert pd["follow_up_suggestion"] == "Consult a doctor"

    def test_concierge_full_access_pattern(self) -> None:
        """Full Concierge read pattern: answer + domain_data + sources + confidence."""
        payload = _make_payload(
            answer="Summary: You are healthy.",
            confidence=0.92,
            domain=("HEALTH", "WELLNESS"),
            sources=({"type": "sensor", "name": "bp_monitor"},),
            domain_data={"summary_type": "weekly", "score": 85},
        )
        result = CapabilityResult.success_result(
            request_id="req-concierge-005",
            data={"payload": payload.to_dict()},
            provider_id="agent-health",
            trace_id="trace-concierge-005",
        )
        pd = result.data["payload"]

        # Concierge DELIVERING state reads:
        answer = pd["answer"]
        domain_data = pd["domain_data"]
        sources = pd["sources"]
        confidence = pd["confidence"]
        domains = pd["domain"]

        assert answer == "Summary: You are healthy."
        assert domain_data["score"] == 85
        assert len(sources) == 1
        assert confidence == 0.92
        assert "WELLNESS" in domains
