"""
Tests for MetaOperationValidator (4.5.5) -- 5-gate meta-operation security policy.

Tests the 5 hard gates for dynamic agent creation:
  Gate 1: Capability band gate (caller >= AMBER)
  Gate 2: Safety band inheritance (no escalation)
  Gate 3: Restricted domain gate (no META, SECURITY, ADMIN)
  Gate 4: Tool grant recursion gate (no tool.write.* meta-tools)
  Gate 5: Agent depth gate (no provider_type=AGENT tools, depth=1)

Test infrastructure:
  Real adapters for RegistryLookupLike (NO MOCKS).
  TestRegistryLookup -- configurable contract returns with call tracking

References:
  - fabric-implementation-plan.md Epic 4.5, Issue 4.5.5
  - meta-agent-creation-integration-proposal.md (security gates)

Naming: test_meta_operation_validator_455.py (issue number suffix).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from k1.fabric.policy.security_context import (
    META_TOOL_PATTERN,
    RESTRICTED_DOMAINS,
    MetaOperationValidator,
    SecurityCheckResult,
)
from k1.fabric.types import CapabilityContract

# ===================================================================
# Test Adapters (real behavior, NO MOCKS)
# ===================================================================


class TestRegistryLookup:
    """
    Test adapter for RegistryLookupLike protocol.

    Returns pre-configured contracts by name. Tracks all lookup calls.
    """

    def __init__(
        self,
        *,
        contracts: Optional[Dict[str, CapabilityContract]] = None,
    ) -> None:
        self._contracts: Dict[str, CapabilityContract] = dict(contracts) if contracts else {}
        self.lookup_calls: List[str] = []

    def lookup(self, name: str) -> Optional[CapabilityContract]:
        self.lookup_calls.append(name)
        return self._contracts.get(name)


# ===================================================================
# Fixtures
# ===================================================================


def _spec(
    *,
    safety_band_min: str = "GREEN",
    domain: Optional[List[str]] = None,
    tools_granted: Optional[List[str]] = None,
    name: str = "agent.execute.test_agent",
) -> Dict[str, Any]:
    """Build a minimal agent spec dict."""
    return {
        "name": name,
        "safety_band_min": safety_band_min,
        "domain": domain if domain is not None else ["memory"],
        "tools_granted": (
            tools_granted if tools_granted is not None else ["tool.read.memory_search"]
        ),
        "description": "Test agent",
        "prompt_template": "test_template",
    }


@pytest.fixture
def registry() -> TestRegistryLookup:
    """Registry with standard test tools (all non-agent providers)."""
    return TestRegistryLookup(
        contracts={
            "tool.read.memory_search": CapabilityContract(
                name="tool.read.memory_search",
                provider_type="MCP",
                domain=["memory"],
                safety_band_min="GREEN",
            ),
            "tool.write.memory_store": CapabilityContract(
                name="tool.write.memory_store",
                provider_type="MCP",
                domain=["memory"],
                safety_band_min="AMBER",
            ),
            "tool.read.calendar": CapabilityContract(
                name="tool.read.calendar",
                provider_type="MCP",
                domain=["scheduling"],
                safety_band_min="GREEN",
            ),
            "agent.execute.existing_agent": CapabilityContract(
                name="agent.execute.existing_agent",
                provider_type="AGENT",
                domain=["memory"],
                safety_band_min="GREEN",
            ),
        }
    )


@pytest.fixture
def validator(registry: TestRegistryLookup) -> MetaOperationValidator:
    """MetaOperationValidator with standard test registry."""
    return MetaOperationValidator(registry=registry)


# ===================================================================
# TestGate1 -- Capability band gate
# ===================================================================


class TestCapabilityBandGate:
    """Gate 1: Caller SafetyBand must be >= AMBER for meta-operations."""

    def test_amber_caller_allowed(self, validator: MetaOperationValidator) -> None:
        result = validator.validate_meta_operation("AMBER", _spec())
        assert result.allowed is True

    def test_red_caller_allowed(self, validator: MetaOperationValidator) -> None:
        result = validator.validate_meta_operation("RED", _spec())
        assert result.allowed is True

    def test_crisis_caller_allowed(self, validator: MetaOperationValidator) -> None:
        result = validator.validate_meta_operation("CRISIS", _spec())
        assert result.allowed is True

    def test_green_caller_denied(self, validator: MetaOperationValidator) -> None:
        result = validator.validate_meta_operation("GREEN", _spec())
        assert result.allowed is False
        assert any("capability_band_denied" in r for r in result.reasons)

    def test_invalid_band_denied(self, validator: MetaOperationValidator) -> None:
        result = validator.validate_meta_operation("INVALID", _spec())
        assert result.allowed is False
        assert any("capability_band_denied" in r for r in result.reasons)


# ===================================================================
# TestGate2 -- Safety band inheritance
# ===================================================================


class TestBandInheritanceGate:
    """Gate 2: Agent safety_band_min cannot exceed caller band."""

    def test_green_agent_from_amber_caller(self, validator: MetaOperationValidator) -> None:
        result = validator.validate_meta_operation("AMBER", _spec(safety_band_min="GREEN"))
        assert result.allowed is True

    def test_amber_agent_from_amber_caller(self, validator: MetaOperationValidator) -> None:
        result = validator.validate_meta_operation("AMBER", _spec(safety_band_min="AMBER"))
        assert result.allowed is True

    def test_red_agent_from_amber_caller_denied(self, validator: MetaOperationValidator) -> None:
        result = validator.validate_meta_operation("AMBER", _spec(safety_band_min="RED"))
        assert result.allowed is False
        assert any("band_escalation_denied" in r for r in result.reasons)

    def test_amber_agent_from_green_caller_denied(self, validator: MetaOperationValidator) -> None:
        """Green callers fail gate 1 AND gate 2 for AMBER agent."""
        result = validator.validate_meta_operation("GREEN", _spec(safety_band_min="AMBER"))
        assert result.allowed is False
        # Should have both gate 1 and gate 2 violations
        assert any("capability_band_denied" in r for r in result.reasons)
        assert any("band_escalation_denied" in r for r in result.reasons)

    def test_red_agent_from_red_caller(self, validator: MetaOperationValidator) -> None:
        result = validator.validate_meta_operation("RED", _spec(safety_band_min="RED"))
        assert result.allowed is True

    def test_crisis_agent_from_red_caller_denied(self, validator: MetaOperationValidator) -> None:
        result = validator.validate_meta_operation("RED", _spec(safety_band_min="CRISIS"))
        assert result.allowed is False
        assert any("band_escalation_denied" in r for r in result.reasons)

    def test_missing_spec_band_defaults_green(self, validator: MetaOperationValidator) -> None:
        spec = _spec()
        del spec["safety_band_min"]
        result = validator.validate_meta_operation("AMBER", spec)
        # Default GREEN is <= AMBER caller, should pass
        assert result.allowed is True


# ===================================================================
# TestGate3 -- Restricted domain gate
# ===================================================================


class TestRestrictedDomainGate:
    """Gate 3: Agent domain cannot contain META, SECURITY, or ADMIN."""

    def test_normal_domain_allowed(self, validator: MetaOperationValidator) -> None:
        result = validator.validate_meta_operation("AMBER", _spec(domain=["memory", "recall"]))
        assert result.allowed is True

    def test_meta_domain_denied(self, validator: MetaOperationValidator) -> None:
        result = validator.validate_meta_operation("AMBER", _spec(domain=["memory", "META"]))
        assert result.allowed is False
        assert any("restricted_domain_denied" in r for r in result.reasons)

    def test_security_domain_denied(self, validator: MetaOperationValidator) -> None:
        result = validator.validate_meta_operation("AMBER", _spec(domain=["SECURITY"]))
        assert result.allowed is False
        assert any("restricted_domain_denied" in r for r in result.reasons)

    def test_admin_domain_denied(self, validator: MetaOperationValidator) -> None:
        result = validator.validate_meta_operation("AMBER", _spec(domain=["ADMIN"]))
        assert result.allowed is False
        assert any("restricted_domain_denied" in r for r in result.reasons)

    def test_case_insensitive_meta(self, validator: MetaOperationValidator) -> None:
        """Restricted domain check is case-insensitive (uppercased)."""
        result = validator.validate_meta_operation("AMBER", _spec(domain=["meta"]))
        assert result.allowed is False

    def test_case_insensitive_security(self, validator: MetaOperationValidator) -> None:
        result = validator.validate_meta_operation("AMBER", _spec(domain=["Security"]))
        assert result.allowed is False

    def test_case_insensitive_admin(self, validator: MetaOperationValidator) -> None:
        result = validator.validate_meta_operation("AMBER", _spec(domain=["admin"]))
        assert result.allowed is False

    def test_multiple_restricted_domains(self, validator: MetaOperationValidator) -> None:
        result = validator.validate_meta_operation(
            "AMBER", _spec(domain=["META", "SECURITY", "memory"])
        )
        assert result.allowed is False
        restricted_reasons = [r for r in result.reasons if "restricted_domain_denied" in r]
        assert len(restricted_reasons) == 2

    def test_restricted_domains_constant(self) -> None:
        assert RESTRICTED_DOMAINS == frozenset({"META", "SECURITY", "ADMIN"})


# ===================================================================
# TestGate4 -- Tool grant recursion gate
# ===================================================================


class TestToolGrantRecursionGate:
    """Gate 4: tools_granted cannot contain tool.write.* meta-tools."""

    def test_read_tools_allowed(self, validator: MetaOperationValidator) -> None:
        result = validator.validate_meta_operation(
            "AMBER", _spec(tools_granted=["tool.read.memory_search", "tool.read.calendar"])
        )
        assert result.allowed is True

    def test_build_agent_tool_denied(self, validator: MetaOperationValidator) -> None:
        result = validator.validate_meta_operation(
            "AMBER", _spec(tools_granted=["tool.read.memory_search", "tool.write.build_agent"])
        )
        assert result.allowed is False
        assert any("tool_recursion_denied" in r for r in result.reasons)

    def test_any_write_tool_denied(self, validator: MetaOperationValidator) -> None:
        result = validator.validate_meta_operation(
            "AMBER", _spec(tools_granted=["tool.write.some_other_meta"])
        )
        assert result.allowed is False
        assert any("tool_recursion_denied" in r for r in result.reasons)

    def test_multiple_write_tools_multiple_reasons(self, validator: MetaOperationValidator) -> None:
        result = validator.validate_meta_operation(
            "AMBER",
            _spec(tools_granted=["tool.write.build_agent", "tool.write.other"]),
        )
        assert result.allowed is False
        recursion_reasons = [r for r in result.reasons if "tool_recursion_denied" in r]
        assert len(recursion_reasons) == 2

    def test_execute_tools_allowed(self, validator: MetaOperationValidator) -> None:
        result = validator.validate_meta_operation(
            "AMBER", _spec(tools_granted=["tool.execute.weather"])
        )
        # Unknown tool in registry won't trigger gate 4 (that's gate 5)
        # Gate 4 only checks the tool.write.* pattern
        assert not any("tool_recursion_denied" in r for r in result.reasons)

    def test_meta_tool_pattern(self) -> None:
        assert META_TOOL_PATTERN.match("tool.write.build_agent")
        assert META_TOOL_PATTERN.match("tool.write.anything")
        assert not META_TOOL_PATTERN.match("tool.read.memory_search")
        assert not META_TOOL_PATTERN.match("tool.execute.weather")
        assert not META_TOOL_PATTERN.match("agent.execute.summarizer")


# ===================================================================
# TestGate5 -- Agent depth gate
# ===================================================================


class TestAgentDepthGate:
    """Gate 5: tools_granted cannot contain provider_type=AGENT tools."""

    def test_non_agent_tools_allowed(self, validator: MetaOperationValidator) -> None:
        result = validator.validate_meta_operation(
            "AMBER", _spec(tools_granted=["tool.read.memory_search"])
        )
        assert result.allowed is True

    def test_agent_tool_denied(
        self, validator: MetaOperationValidator, registry: TestRegistryLookup
    ) -> None:
        result = validator.validate_meta_operation(
            "AMBER", _spec(tools_granted=["agent.execute.existing_agent"])
        )
        assert result.allowed is False
        assert any("agent_depth_denied" in r for r in result.reasons)
        assert "agent.execute.existing_agent" in registry.lookup_calls

    def test_unknown_tool_passes_depth_check(self, validator: MetaOperationValidator) -> None:
        """Tools not in registry pass gate 5 (gate 5 only checks known tools)."""
        result = validator.validate_meta_operation(
            "AMBER", _spec(tools_granted=["tool.read.unknown_tool"])
        )
        # Gate 5 passes for unknown tools -- other gates handle unknown tool validation
        assert not any("agent_depth_denied" in r for r in result.reasons)

    def test_registry_lookup_called(
        self, validator: MetaOperationValidator, registry: TestRegistryLookup
    ) -> None:
        validator.validate_meta_operation(
            "AMBER",
            _spec(tools_granted=["tool.read.memory_search", "tool.read.calendar"]),
        )
        assert "tool.read.memory_search" in registry.lookup_calls
        assert "tool.read.calendar" in registry.lookup_calls

    def test_multiple_agent_tools_multiple_reasons(self, registry: TestRegistryLookup) -> None:
        registry._contracts["agent.execute.another_agent"] = CapabilityContract(
            name="agent.execute.another_agent",
            provider_type="AGENT",
            domain=["general"],
        )
        validator = MetaOperationValidator(registry=registry)
        result = validator.validate_meta_operation(
            "AMBER",
            _spec(
                tools_granted=[
                    "agent.execute.existing_agent",
                    "agent.execute.another_agent",
                ]
            ),
        )
        assert result.allowed is False
        depth_reasons = [r for r in result.reasons if "agent_depth_denied" in r]
        assert len(depth_reasons) == 2


# ===================================================================
# TestAllGatesCombined
# ===================================================================


class TestAllGatesCombined:
    """Tests for combined gate evaluation behavior."""

    def test_all_gates_pass(self, validator: MetaOperationValidator) -> None:
        result = validator.validate_meta_operation(
            "AMBER",
            _spec(
                safety_band_min="GREEN",
                domain=["memory", "recall"],
                tools_granted=["tool.read.memory_search"],
            ),
        )
        assert result.allowed is True
        assert result.reasons == ["meta_operation_allowed"]

    def test_all_gates_collected(self, validator: MetaOperationValidator) -> None:
        """All gate violations are collected, not just the first."""
        result = validator.validate_meta_operation(
            "GREEN",
            _spec(
                safety_band_min="RED",
                domain=["META", "ADMIN"],
                tools_granted=["tool.write.build_agent", "agent.execute.existing_agent"],
            ),
        )
        assert result.allowed is False
        # Should have violations from gates 1, 2, 3 (x2), 4, and 5
        assert len(result.reasons) >= 5

    def test_result_is_security_check_result(self, validator: MetaOperationValidator) -> None:
        result = validator.validate_meta_operation("AMBER", _spec())
        assert isinstance(result, SecurityCheckResult)

    def test_allowed_result_is_frozen(self, validator: MetaOperationValidator) -> None:
        result = validator.validate_meta_operation("AMBER", _spec())
        with pytest.raises(AttributeError):
            result.allowed = False  # type: ignore[misc]

    def test_empty_tools_granted(self, validator: MetaOperationValidator) -> None:
        """Empty tools_granted passes gates 4 and 5 (no tools to check)."""
        result = validator.validate_meta_operation("AMBER", _spec(tools_granted=[]))
        assert result.allowed is True

    def test_empty_domain(self, validator: MetaOperationValidator) -> None:
        """Empty domain passes gate 3 (no domains to check)."""
        result = validator.validate_meta_operation("AMBER", _spec(domain=[]))
        assert result.allowed is True


# ===================================================================
# TestProtocolSatisfaction
# ===================================================================


class TestProtocolSatisfaction:
    """Tests that MetaOperationValidator satisfies SecurityGateLike."""

    def test_satisfies_security_gate_like(self, validator: MetaOperationValidator) -> None:
        from k1.fabric.core.agent_builder import SecurityGateLike

        assert isinstance(validator, SecurityGateLike)

    def test_has_validate_meta_operation(self, validator: MetaOperationValidator) -> None:
        assert hasattr(validator, "validate_meta_operation")
        assert callable(validator.validate_meta_operation)


# ===================================================================
# TestRepr
# ===================================================================


class TestRepr:
    """Tests for __repr__ output."""

    def test_repr(self, validator: MetaOperationValidator) -> None:
        r = repr(validator)
        assert "MetaOperationValidator(" in r


# ===================================================================
# TestPolicyExports
# ===================================================================


class TestPolicyExports:
    """Tests that 4.5.5 exports are accessible from k1.fabric.policy."""

    def test_meta_operation_validator_importable(self) -> None:
        from k1.fabric.policy import MetaOperationValidator as MOV

        assert MOV is not None

    def test_restricted_domains_importable(self) -> None:
        from k1.fabric.policy import RESTRICTED_DOMAINS as RD

        assert RD is not None
        assert isinstance(RD, frozenset)

    def test_meta_tool_pattern_importable(self) -> None:
        from k1.fabric.policy import META_TOOL_PATTERN as MTP

        assert MTP is not None

    def test_in_all(self) -> None:
        import k1.fabric.policy as pkg

        assert "MetaOperationValidator" in pkg.__all__
        assert "RESTRICTED_DOMAINS" in pkg.__all__
        assert "META_TOOL_PATTERN" in pkg.__all__
