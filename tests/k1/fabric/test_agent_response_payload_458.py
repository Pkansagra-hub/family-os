"""
Tests for Issue 4.5.8 -- AgentResponsePayload type.

Covers:
  - Construction with defaults and full arguments
  - Frozen immutability guarantee
  - to_dict() JSON-safe serialization (tuples -> lists, defensive copies)
  - from_dict() classmethod factory with type coercion
  - validate() business rules (confidence range, domain non-empty, answer non-empty)
  - Round-trip: to_dict() -> from_dict() identity
  - Integration pattern: CapabilityResult.data["payload"] embedding
"""

from __future__ import annotations

import dataclasses

import pytest

from k1.fabric.types import AgentResponsePayload, CapabilityResult

# ===================================================================
# Section 1: Construction
# ===================================================================


class TestConstruction:
    """AgentResponsePayload construction with defaults and full arguments."""

    def test_all_defaults(self) -> None:
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
        p = AgentResponsePayload(
            answer="Your blood pressure is within normal range.",
            confidence=0.92,
            domain=("health", "vitals"),
            sources=({"title": "WHO Guidelines", "url": "https://who.int"},),
            domain_data={"vitals": {"systolic": 120, "diastolic": 80}},
            follow_up_needed=True,
            follow_up_suggestion="Schedule a follow-up in 3 months.",
            reasoning_trace=("step1: retrieve vitals", "step2: compare ranges"),
            tools_used=("tool.execute.vitals_lookup",),
            k0_queries_made=3,
        )
        assert p.answer == "Your blood pressure is within normal range."
        assert p.confidence == 0.92
        assert p.domain == ("health", "vitals")
        assert len(p.sources) == 1
        assert p.sources[0]["title"] == "WHO Guidelines"
        assert p.domain_data["vitals"]["systolic"] == 120
        assert p.follow_up_needed is True
        assert p.follow_up_suggestion == "Schedule a follow-up in 3 months."
        assert p.reasoning_trace == ("step1: retrieve vitals", "step2: compare ranges")
        assert p.tools_used == ("tool.execute.vitals_lookup",)
        assert p.k0_queries_made == 3

    def test_is_dataclass(self) -> None:
        assert dataclasses.is_dataclass(AgentResponsePayload)

    def test_frozen(self) -> None:
        p = AgentResponsePayload(answer="test")
        with pytest.raises(dataclasses.FrozenInstanceError):
            p.answer = "changed"  # type: ignore[misc]

    def test_frozen_confidence(self) -> None:
        p = AgentResponsePayload(confidence=0.5)
        with pytest.raises(dataclasses.FrozenInstanceError):
            p.confidence = 0.9  # type: ignore[misc]


# ===================================================================
# Section 2: to_dict()
# ===================================================================


class TestToDict:
    """JSON-safe serialization via to_dict()."""

    def test_tuples_become_lists(self) -> None:
        p = AgentResponsePayload(
            domain=("a", "b"),
            reasoning_trace=("r1",),
            tools_used=("t1", "t2"),
        )
        d = p.to_dict()
        assert isinstance(d["domain"], list)
        assert d["domain"] == ["a", "b"]
        assert isinstance(d["reasoning_trace"], list)
        assert d["reasoning_trace"] == ["r1"]
        assert isinstance(d["tools_used"], list)
        assert d["tools_used"] == ["t1", "t2"]

    def test_sources_become_list_of_dicts(self) -> None:
        p = AgentResponsePayload(
            sources=({"k": "v"},),
        )
        d = p.to_dict()
        assert isinstance(d["sources"], list)
        assert d["sources"] == [{"k": "v"}]

    def test_domain_data_is_copy(self) -> None:
        original = {"a": 1}
        p = AgentResponsePayload(domain_data=original)
        d = p.to_dict()
        assert d["domain_data"] is not original
        assert d["domain_data"] == {"a": 1}

    def test_all_keys_present(self) -> None:
        p = AgentResponsePayload()
        d = p.to_dict()
        expected_keys = {
            "answer",
            "confidence",
            "domain",
            "sources",
            "domain_data",
            "follow_up_needed",
            "follow_up_suggestion",
            "reasoning_trace",
            "tools_used",
            "k0_queries_made",
        }
        assert set(d.keys()) == expected_keys

    def test_returns_new_dict_each_call(self) -> None:
        p = AgentResponsePayload()
        d1 = p.to_dict()
        d2 = p.to_dict()
        assert d1 is not d2


# ===================================================================
# Section 3: from_dict()
# ===================================================================


class TestFromDict:
    """Classmethod factory with type coercion."""

    def test_full_round_trip(self) -> None:
        original = AgentResponsePayload(
            answer="Answer",
            confidence=0.85,
            domain=("health",),
            sources=({"ref": "A"},),
            domain_data={"vitals": True},
            follow_up_needed=True,
            follow_up_suggestion="Check back",
            reasoning_trace=("step1",),
            tools_used=("tool1",),
            k0_queries_made=5,
        )
        d = original.to_dict()
        restored = AgentResponsePayload.from_dict(d)
        assert restored.answer == original.answer
        assert restored.confidence == original.confidence
        assert restored.domain == original.domain
        assert restored.sources == original.sources
        assert restored.domain_data == original.domain_data
        assert restored.follow_up_needed == original.follow_up_needed
        assert restored.follow_up_suggestion == original.follow_up_suggestion
        assert restored.reasoning_trace == original.reasoning_trace
        assert restored.tools_used == original.tools_used
        assert restored.k0_queries_made == original.k0_queries_made

    def test_empty_dict(self) -> None:
        p = AgentResponsePayload.from_dict({})
        assert p.answer == ""
        assert p.confidence == 0.0
        assert p.domain == ()
        assert p.sources == ()
        assert p.domain_data == {}
        assert p.k0_queries_made == 0

    def test_lists_coerced_to_tuples(self) -> None:
        p = AgentResponsePayload.from_dict(
            {
                "domain": ["a", "b"],
                "sources": [{"k": "v"}],
                "reasoning_trace": ["r1", "r2"],
                "tools_used": ["t1"],
            }
        )
        assert isinstance(p.domain, tuple)
        assert isinstance(p.sources, tuple)
        assert isinstance(p.reasoning_trace, tuple)
        assert isinstance(p.tools_used, tuple)

    def test_confidence_coerced_to_float(self) -> None:
        p = AgentResponsePayload.from_dict({"confidence": 1})
        assert isinstance(p.confidence, float)
        assert p.confidence == 1.0

    def test_k0_queries_made_coerced_to_int(self) -> None:
        p = AgentResponsePayload.from_dict({"k0_queries_made": "3"})
        assert isinstance(p.k0_queries_made, int)
        assert p.k0_queries_made == 3

    def test_non_dict_sources_coerced(self) -> None:
        """Non-dict entries in sources list become empty dicts."""
        p = AgentResponsePayload.from_dict({"sources": ["not_a_dict"]})
        assert p.sources == ({},)


# ===================================================================
# Section 4: validate()
# ===================================================================


class TestValidate:
    """Business rule validation."""

    def test_valid_payload(self) -> None:
        p = AgentResponsePayload(
            answer="Yes",
            confidence=0.8,
            domain=("health",),
        )
        assert p.validate() is True

    def test_confidence_zero_valid(self) -> None:
        p = AgentResponsePayload(answer="x", confidence=0.0, domain=("d",))
        assert p.validate() is True

    def test_confidence_one_valid(self) -> None:
        p = AgentResponsePayload(answer="x", confidence=1.0, domain=("d",))
        assert p.validate() is True

    def test_confidence_below_zero_invalid(self) -> None:
        p = AgentResponsePayload(answer="x", confidence=-0.1, domain=("d",))
        assert p.validate() is False

    def test_confidence_above_one_invalid(self) -> None:
        p = AgentResponsePayload(answer="x", confidence=1.01, domain=("d",))
        assert p.validate() is False

    def test_empty_domain_invalid(self) -> None:
        p = AgentResponsePayload(answer="x", confidence=0.5, domain=())
        assert p.validate() is False

    def test_empty_answer_invalid(self) -> None:
        p = AgentResponsePayload(answer="", confidence=0.5, domain=("d",))
        assert p.validate() is False

    def test_whitespace_only_answer_invalid(self) -> None:
        p = AgentResponsePayload(answer="   ", confidence=0.5, domain=("d",))
        assert p.validate() is False

    def test_all_defaults_invalid(self) -> None:
        """Default construction fails validation (empty answer, empty domain)."""
        p = AgentResponsePayload()
        assert p.validate() is False


# ===================================================================
# Section 5: Integration pattern (CapabilityResult embedding)
# ===================================================================


class TestIntegrationPattern:
    """Verify the CapabilityResult.data['payload'] embedding pattern."""

    def test_payload_in_capability_result(self) -> None:
        payload = AgentResponsePayload(
            answer="Blood sugar is 110 mg/dL.",
            confidence=0.95,
            domain=("health", "diabetes"),
            sources=({"ref": "Lab Report 2025-01"},),
            domain_data={"glucose_mg_dl": 110},
        )
        result = CapabilityResult.success_result(
            request_id="req-001",
            data={"payload": payload.to_dict()},
            provider_id="agent.execute.diabetes",
            trace_id="tr-001",
        )
        assert result.success is True
        assert "payload" in result.data
        assert result.data["payload"]["answer"] == "Blood sugar is 110 mg/dL."
        assert result.data["payload"]["domain_data"]["glucose_mg_dl"] == 110

    def test_concierge_consumption_pattern(self) -> None:
        """Concierge reads answer, domain_data, and sources from result."""
        payload = AgentResponsePayload(
            answer="Account balance is $5,000.",
            confidence=0.99,
            domain=("finance",),
            sources=({"institution": "BankX"},),
            domain_data={"accounts": [{"name": "Checking", "balance": 5000}]},
        )
        result_data = {"payload": payload.to_dict()}

        # Concierge consumption (DELIVERING state):
        answer = result_data["payload"]["answer"]
        domain_data = result_data["payload"]["domain_data"]
        sources = result_data["payload"]["sources"]

        assert answer == "Account balance is $5,000."
        assert domain_data["accounts"][0]["balance"] == 5000
        assert sources[0]["institution"] == "BankX"

    def test_multi_agent_merging_pattern(self) -> None:
        """Multiple payloads can be deserialized and compared."""
        p1 = AgentResponsePayload(
            answer="A1",
            confidence=0.8,
            domain=("health",),
        )
        p2 = AgentResponsePayload(
            answer="A2",
            confidence=0.9,
            domain=("health",),
        )
        payloads = [
            AgentResponsePayload.from_dict(p1.to_dict()),
            AgentResponsePayload.from_dict(p2.to_dict()),
        ]
        best = max(payloads, key=lambda p: p.confidence)
        assert best.answer == "A2"
        assert best.confidence == 0.9
