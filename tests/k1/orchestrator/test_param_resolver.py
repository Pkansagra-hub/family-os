"""
Tests for k1.orchestrator.orchestration.param_resolver -- Issue 2.3.5.

Covers:
  - Typed resolve() API with PlanStep + Dict[str, CapabilityResult]
  - Legacy resolve_step() backward-compat alias
  - Recursive nested dict/list param walking
  - Capability resolution (static + dynamic meta-agent pattern)
  - End-to-end build_agent -> execute created agent flow
  - Edge cases and error paths
  - Immutability guarantees

Test scenarios from param_resolver_spec.md (~20 tests).
"""

from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional

import pytest

from k1.orchestrator.orchestration.param_resolver import (
    ParamResolver,
    PathResolutionError,
    StepReferenceError,
    UnresolvedCapabilityError,
)
from k1.orchestrator.types import PlanStep

# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class FakeCapabilityResult:
    """Minimal CapabilityResult stand-in for ParamResolver tests.

    Mirrors k1.fabric.types.CapabilityResult but avoids import coupling.
    ParamResolver uses duck-typing: checks hasattr(result, 'success')
    and hasattr(result, 'data').
    """

    __slots__ = ("success", "data")

    def __init__(
        self,
        success: bool = True,
        data: Optional[Dict[str, Any]] = None,
    ) -> None:
        object.__setattr__(self, "success", success)
        object.__setattr__(self, "data", data)


class FakeRegistry:
    """In-memory RegistryPort implementation for tests."""

    def __init__(self, capabilities: Optional[List[str]] = None) -> None:
        self._caps = set(capabilities or [])

    def contains(self, name: str) -> bool:
        return name in self._caps


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_step(
    id: str = "step_1",
    capability: str = "tool.read.lookup",
    params: Optional[Dict[str, Any]] = None,
    deps: Optional[List[str]] = None,
) -> PlanStep:
    """Build a PlanStep with sensible defaults."""
    return PlanStep(
        id=id,
        capability=capability,
        params=params or {},
        deps=deps or [],
    )


def _success(data: Optional[Dict[str, Any]] = None) -> FakeCapabilityResult:
    """Build a successful FakeCapabilityResult."""
    return FakeCapabilityResult(success=True, data=data)


def _failure() -> FakeCapabilityResult:
    """Build a failed FakeCapabilityResult."""
    return FakeCapabilityResult(success=False, data=None)


# ===================================================================
# 1. Param resolution -- typed API resolve()
# ===================================================================


class TestParamResolutionTyped:
    """Tests for resolve() param resolution with PlanStep input."""

    def test_static_params_pass_through(self) -> None:
        """Spec scenario 1: static params pass through unchanged."""
        resolver = ParamResolver()
        step = _make_step(params={"query": "hello", "limit": 10})

        resolved_params, resolved_cap = resolver.resolve(step, {})

        assert resolved_params == {"query": "hello", "limit": 10}
        assert resolved_cap is None

    def test_single_ref_resolves(self) -> None:
        """Spec scenario 2: $step_id.result.key resolves."""
        resolver = ParamResolver()
        step = _make_step(
            id="step_2",
            params={"agent_name": "$step_1.result.name"},
            deps=["step_1"],
        )
        prior = {"step_1": _success(data={"name": "diabetes_agent"})}

        resolved_params, _ = resolver.resolve(step, prior)

        assert resolved_params["agent_name"] == "diabetes_agent"

    def test_missing_step_raises_step_reference_error(self) -> None:
        """Spec scenario 3: missing step_id raises StepReferenceError."""
        resolver = ParamResolver()
        step = _make_step(params={"x": "$missing_step.result.val"})

        with pytest.raises(StepReferenceError, match="missing_step"):
            resolver.resolve(step, {})

    def test_missing_key_raises_path_resolution_error(self) -> None:
        """Spec scenario 4: missing key in data raises PathResolutionError."""
        resolver = ParamResolver()
        step = _make_step(params={"x": "$step_1.result.no_such_key"})
        prior = {"step_1": _success(data={"other_key": "val"})}

        with pytest.raises(PathResolutionError, match="no_such_key"):
            resolver.resolve(step, prior)

    def test_non_string_values_pass_through(self) -> None:
        """Spec scenario 5: non-string values pass through unchanged."""
        resolver = ParamResolver()
        step = _make_step(
            params={
                "count": 42,
                "active": True,
                "tags": ["a", "b"],
                "config": None,
            }
        )

        resolved_params, _ = resolver.resolve(step, {})

        assert resolved_params == {
            "count": 42,
            "active": True,
            "tags": ["a", "b"],
            "config": None,
        }

    def test_mixed_static_and_dynamic_params(self) -> None:
        """Spec scenario 6: multiple params with mixed refs."""
        resolver = ParamResolver()
        step = _make_step(
            params={
                "static_key": "hello",
                "dynamic_key": "$step_1.result.value",
                "number": 99,
            }
        )
        prior = {"step_1": _success(data={"value": "resolved_val"})}

        resolved_params, _ = resolver.resolve(step, prior)

        assert resolved_params == {
            "static_key": "hello",
            "dynamic_key": "resolved_val",
            "number": 99,
        }

    def test_empty_params_returns_empty_dict(self) -> None:
        """No params -> empty dict, no errors."""
        resolver = ParamResolver()
        step = _make_step(params={})

        resolved_params, _ = resolver.resolve(step, {})

        assert resolved_params == {}

    def test_none_params_returns_empty_dict(self) -> None:
        """Step with params=None (frozen default) -> empty dict."""
        resolver = ParamResolver()
        # PlanStep has params default_factory=dict, so empty dict is default
        step = PlanStep(id="s1", capability="cap")

        resolved_params, _ = resolver.resolve(step, {})

        assert resolved_params == {}


# ===================================================================
# 2. Recursive nested dict/list walking (2.3.5 new)
# ===================================================================


class TestRecursiveParamWalking:
    """Tests for recursive nested dict and list resolution."""

    def test_nested_dict_ref_resolved(self) -> None:
        """$-ref inside nested dict is resolved."""
        resolver = ParamResolver()
        step = _make_step(
            params={
                "outer": {
                    "inner": "$step_1.result.val",
                    "static": "keep",
                }
            }
        )
        prior = {"step_1": _success(data={"val": "deep_value"})}

        resolved_params, _ = resolver.resolve(step, prior)

        assert resolved_params["outer"]["inner"] == "deep_value"
        assert resolved_params["outer"]["static"] == "keep"

    def test_deeply_nested_dict(self) -> None:
        """Three levels of nesting with ref at bottom."""
        resolver = ParamResolver()
        step = _make_step(params={"a": {"b": {"c": "$step_1.result.x"}}})
        prior = {"step_1": _success(data={"x": 42})}

        resolved_params, _ = resolver.resolve(step, prior)

        assert resolved_params["a"]["b"]["c"] == 42

    def test_list_with_ref_resolved(self) -> None:
        """$-ref inside a list is resolved."""
        resolver = ParamResolver()
        step = _make_step(params={"items": ["static", "$step_1.result.val", 123]})
        prior = {"step_1": _success(data={"val": "list_resolved"})}

        resolved_params, _ = resolver.resolve(step, prior)

        assert resolved_params["items"] == ["static", "list_resolved", 123]

    def test_nested_dict_inside_list(self) -> None:
        """Dict inside list with $-ref is resolved."""
        resolver = ParamResolver()
        step = _make_step(params={"items": [{"key": "$step_1.result.val"}]})
        prior = {"step_1": _success(data={"val": "nested_list_val"})}

        resolved_params, _ = resolver.resolve(step, prior)

        assert resolved_params["items"][0]["key"] == "nested_list_val"

    def test_nested_list_inside_list(self) -> None:
        """List inside list with $-ref is resolved."""
        resolver = ParamResolver()
        step = _make_step(params={"matrix": [["$step_1.result.val", "b"], ["c"]]})
        prior = {"step_1": _success(data={"val": "cell_00"})}

        resolved_params, _ = resolver.resolve(step, prior)

        assert resolved_params["matrix"][0][0] == "cell_00"
        assert resolved_params["matrix"][0][1] == "b"

    def test_original_step_params_not_mutated(self) -> None:
        """resolve() never mutates the original PlanStep params."""
        resolver = ParamResolver()
        original_params = {
            "nested": {"ref": "$step_1.result.val"},
            "list_ref": ["$step_1.result.val"],
        }
        step = _make_step(params=original_params)
        prior = {"step_1": _success(data={"val": "resolved"})}

        # Deep copy original to verify no mutation
        original_snapshot = copy.deepcopy(original_params)
        resolver.resolve(step, prior)

        # PlanStep.params should still contain $-refs
        assert step.params == original_snapshot


# ===================================================================
# 3. Capability resolution (typed API)
# ===================================================================


class TestCapabilityResolutionTyped:
    """Tests for capability $-ref resolution via resolve()."""

    def test_static_capability_returns_none(self) -> None:
        """Spec scenario 7: static capability -> resolved_cap is None."""
        resolver = ParamResolver()
        step = _make_step(capability="tool.read.lookup")

        _, resolved_cap = resolver.resolve(step, {})

        assert resolved_cap is None

    def test_dynamic_capability_resolves(self) -> None:
        """Spec scenario 8: $step_id.result.agent_name resolves."""
        registry = FakeRegistry(["agent.execute.diabetes"])
        resolver = ParamResolver(registry=registry)
        step = _make_step(
            id="step_2",
            capability="$step_1.result.agent_name",
            deps=["step_1"],
        )
        prior = {"step_1": _success(data={"agent_name": "agent.execute.diabetes"})}

        _, resolved_cap = resolver.resolve(step, prior)

        assert resolved_cap == "agent.execute.diabetes"

    def test_dynamic_capability_not_in_registry_raises(self) -> None:
        """Spec scenario 9: resolved cap NOT in registry -> UnresolvedCapabilityError."""
        registry = FakeRegistry([])  # empty registry
        resolver = ParamResolver(registry=registry)
        step = _make_step(
            id="step_2",
            capability="$step_1.result.agent_name",
        )
        prior = {"step_1": _success(data={"agent_name": "unknown.agent"})}

        with pytest.raises(UnresolvedCapabilityError, match="unknown.agent"):
            resolver.resolve(step, prior)

    def test_capability_ref_step_missing_raises(self) -> None:
        """Spec scenario 10: referenced step not in results -> StepReferenceError."""
        resolver = ParamResolver()
        step = _make_step(capability="$missing.result.name")

        with pytest.raises(StepReferenceError, match="missing"):
            resolver.resolve(step, {})

    def test_capability_path_traversal_fails(self) -> None:
        """Spec scenario 11: path traversal fails -> PathResolutionError."""
        resolver = ParamResolver()
        step = _make_step(capability="$step_1.result.no_key")
        prior = {"step_1": _success(data={"other": "val"})}

        with pytest.raises(PathResolutionError, match="no_key"):
            resolver.resolve(step, prior)

    def test_capability_resolves_to_non_string_raises(self) -> None:
        """Spec scenario 12: resolved to non-string -> UnresolvedCapabilityError."""
        resolver = ParamResolver()
        step = _make_step(
            id="step_2",
            capability="$step_1.result.bad_val",
        )
        prior = {"step_1": _success(data={"bad_val": 42})}

        with pytest.raises(UnresolvedCapabilityError, match="42"):
            resolver.resolve(step, prior)

    def test_capability_resolves_to_empty_string_raises(self) -> None:
        """Spec scenario 13: resolved to empty string -> UnresolvedCapabilityError."""
        resolver = ParamResolver()
        step = _make_step(
            id="step_2",
            capability="$step_1.result.empty",
        )
        prior = {"step_1": _success(data={"empty": ""})}

        with pytest.raises(UnresolvedCapabilityError, match="step_2"):
            resolver.resolve(step, prior)

    def test_deep_path_capability_resolution(self) -> None:
        """Spec scenario 14: deep path $step_id.result.nested.key resolves."""
        registry = FakeRegistry(["deep.agent"])
        resolver = ParamResolver(registry=registry)
        step = _make_step(
            id="step_2",
            capability="$step_1.result.nested.key",
        )
        prior = {"step_1": _success(data={"nested": {"key": "deep.agent"}})}

        _, resolved_cap = resolver.resolve(step, prior)

        assert resolved_cap == "deep.agent"

    def test_no_registry_skips_existence_check(self) -> None:
        """No registry (POC mode) -> resolved cap accepted without check."""
        resolver = ParamResolver(registry=None)
        step = _make_step(
            id="step_2",
            capability="$step_1.result.agent_name",
        )
        prior = {"step_1": _success(data={"agent_name": "any.agent"})}

        _, resolved_cap = resolver.resolve(step, prior)

        assert resolved_cap == "any.agent"


# ===================================================================
# 4. End-to-end meta-agent pattern
# ===================================================================


class TestEndToEndMetaAgent:
    """Tests for the build_agent -> execute created agent full flow."""

    def test_build_then_execute_full_flow(self) -> None:
        """Spec scenario 15: complete meta-agent creation pattern."""
        # Step 1a: build_agent returns agent name
        step_1a_result = _success(
            data={
                "agent_name": "agent.execute.diabetes_companion",
                "status": "registered",
            }
        )

        # Step 2a: references step_1a dynamically
        registry = FakeRegistry(["agent.execute.diabetes_companion"])
        resolver = ParamResolver(registry=registry)

        step_2a = _make_step(
            id="step_2a",
            capability="$step_1a.result.agent_name",
            params={
                "query": "What is my latest blood sugar reading?",
                "session_id": "sess-001",
            },
            deps=["step_1a"],
        )

        prior = {"step_1a": step_1a_result}
        resolved_params, resolved_cap = resolver.resolve(step_2a, prior)

        assert resolved_cap == "agent.execute.diabetes_companion"
        assert resolved_params["query"] == "What is my latest blood sugar reading?"
        assert resolved_params["session_id"] == "sess-001"

    def test_multiple_dynamic_steps_in_sequence(self) -> None:
        """Spec scenario 16: multiple steps each referencing previous."""
        registry = FakeRegistry(["agent.intermediate", "agent.final"])
        resolver = ParamResolver(registry=registry)

        # Step 2 references step 1 result
        step_2 = _make_step(
            id="step_2",
            capability="$step_1.result.cap",
            params={"data": "$step_1.result.output"},
        )
        prior_2 = {
            "step_1": _success(data={"cap": "agent.intermediate", "output": "val1"}),
        }
        params_2, cap_2 = resolver.resolve(step_2, prior_2)
        assert cap_2 == "agent.intermediate"
        assert params_2["data"] == "val1"

        # Step 3 references step 2 result
        step_3 = _make_step(
            id="step_3",
            capability="$step_2.result.next_cap",
            params={"prev": "$step_2.result.output"},
        )
        prior_3 = {
            **prior_2,
            "step_2": _success(data={"next_cap": "agent.final", "output": "val2"}),
        }
        params_3, cap_3 = resolver.resolve(step_3, prior_3)
        assert cap_3 == "agent.final"
        assert params_3["prev"] == "val2"

    def test_step_dict_not_mutated(self) -> None:
        """Spec scenario 17: original PlanStep never mutated."""
        resolver = ParamResolver()
        step = _make_step(
            id="step_2",
            params={"ref": "$step_1.result.val"},
        )
        prior = {"step_1": _success(data={"val": "resolved"})}

        original_params = dict(step.params)
        resolver.resolve(step, prior)

        assert step.params == original_params
        assert step.params["ref"] == "$step_1.result.val"

    def test_failed_step_referenced_raises(self) -> None:
        """Spec scenario 18: failed step (success=False) raises error."""
        resolver = ParamResolver()
        step = _make_step(params={"x": "$step_1.result.val"})
        prior = {"step_1": _failure()}

        with pytest.raises(PathResolutionError, match="success=False"):
            resolver.resolve(step, prior)


# ===================================================================
# 5. Edge cases
# ===================================================================


class TestEdgeCases:
    """Edge case scenarios from spec."""

    def test_result_data_is_none_raises(self) -> None:
        """Result data is None -> PathResolutionError."""
        resolver = ParamResolver()
        step = _make_step(params={"x": "$step_1.result.val"})
        prior = {"step_1": _success(data=None)}

        with pytest.raises(PathResolutionError, match="None"):
            resolver.resolve(step, prior)

    def test_empty_results_no_refs_pass_through(self) -> None:
        """Spec scenario 20: empty results + no refs -> pass through."""
        resolver = ParamResolver()
        step = _make_step(params={"static": "value"})

        resolved_params, resolved_cap = resolver.resolve(step, {})

        assert resolved_params == {"static": "value"}
        assert resolved_cap is None

    def test_dollar_sign_in_middle_of_string_not_resolved(self) -> None:
        """Only strings starting with $ are resolved; mid-string $ ignored."""
        resolver = ParamResolver()
        step = _make_step(params={"msg": "price is $50.00"})

        resolved_params, _ = resolver.resolve(step, {})

        # Does not start with $, so not treated as reference
        assert resolved_params["msg"] == "price is $50.00"

    def test_repr(self) -> None:
        """ParamResolver has useful repr."""
        resolver = ParamResolver(registry=None)
        assert "ParamResolver" in repr(resolver)

    def test_both_capability_and_params_resolved(self) -> None:
        """Both capability and params have $-refs, both resolved."""
        registry = FakeRegistry(["resolved.cap"])
        resolver = ParamResolver(registry=registry)
        step = _make_step(
            id="s2",
            capability="$s1.result.cap",
            params={"val": "$s1.result.output"},
        )
        prior = {"s1": _success(data={"cap": "resolved.cap", "output": "data_val"})}

        resolved_params, resolved_cap = resolver.resolve(step, prior)

        assert resolved_cap == "resolved.cap"
        assert resolved_params["val"] == "data_val"


# ===================================================================
# 6. Legacy resolve_step() backward compat
# ===================================================================


class TestLegacyResolveStep:
    """Tests for resolve_step() dict-based backward compat alias."""

    def test_static_step_passes_through(self) -> None:
        """Static step dict passes through unchanged."""
        resolver = ParamResolver()
        step = {"id": "s1", "capability": "tool.read", "params": {"q": "hello"}}

        result = resolver.resolve_step(step, {})

        assert result["capability"] == "tool.read"
        assert result["params"]["q"] == "hello"

    def test_param_ref_resolved(self) -> None:
        """$-ref in params resolved in dict mode."""
        resolver = ParamResolver()
        step = {"id": "s2", "capability": "cap", "params": {"x": "$s1.result.val"}}
        results = {"s1": _success(data={"val": "resolved"})}

        result = resolver.resolve_step(step, results)

        assert result["params"]["x"] == "resolved"

    def test_capability_ref_resolved(self) -> None:
        """$-ref in capability resolved in dict mode."""
        reg = FakeRegistry(["resolved.cap"])
        resolver = ParamResolver(registry=reg)
        step = {"id": "s2", "capability": "$s1.result.cap"}
        results = {"s1": _success(data={"cap": "resolved.cap"})}

        result = resolver.resolve_step(step, results)

        assert result["capability"] == "resolved.cap"

    def test_original_dict_not_mutated(self) -> None:
        """Original step dict never mutated."""
        resolver = ParamResolver()
        step = {"id": "s2", "capability": "cap", "params": {"x": "$s1.result.val"}}
        results = {"s1": _success(data={"val": "resolved"})}
        original = copy.deepcopy(step)

        resolver.resolve_step(step, results)

        assert step == original

    def test_missing_step_raises(self) -> None:
        """Missing step_id in dict mode raises StepReferenceError."""
        resolver = ParamResolver()
        step = {"id": "s2", "capability": "cap", "params": {"x": "$missing.result.val"}}

        with pytest.raises(StepReferenceError, match="missing"):
            resolver.resolve_step(step, {})

    def test_no_params_key_passes_through(self) -> None:
        """Step dict without 'params' key passes through fine."""
        resolver = ParamResolver()
        step = {"id": "s1", "capability": "cap"}

        result = resolver.resolve_step(step, {})

        assert result["capability"] == "cap"
        assert "params" not in result


# ===================================================================
# 7. Path traversal depth
# ===================================================================


class TestPathTraversal:
    """Tests for deep path traversal in references."""

    def test_single_level_path(self) -> None:
        """$step.result.key -> one level deep."""
        resolver = ParamResolver()
        step = _make_step(params={"x": "$s1.result.key"})
        prior = {"s1": _success(data={"key": "val"})}

        params, _ = resolver.resolve(step, prior)
        assert params["x"] == "val"

    def test_two_level_path(self) -> None:
        """$step.result.a.b -> two levels deep."""
        resolver = ParamResolver()
        step = _make_step(params={"x": "$s1.result.a.b"})
        prior = {"s1": _success(data={"a": {"b": "deep"}})}

        params, _ = resolver.resolve(step, prior)
        assert params["x"] == "deep"

    def test_three_level_path(self) -> None:
        """$step.result.a.b.c -> three levels deep."""
        resolver = ParamResolver()
        step = _make_step(params={"x": "$s1.result.a.b.c"})
        prior = {"s1": _success(data={"a": {"b": {"c": 999}}})}

        params, _ = resolver.resolve(step, prior)
        assert params["x"] == 999

    def test_intermediate_none_raises(self) -> None:
        """Path traversal through None intermediate raises."""
        resolver = ParamResolver()
        step = _make_step(params={"x": "$s1.result.a.b"})
        prior = {"s1": _success(data={"a": None})}

        with pytest.raises(PathResolutionError, match="b"):
            resolver.resolve(step, prior)

    def test_resolved_value_can_be_dict(self) -> None:
        """Resolved value can be a dict if it's the leaf."""
        resolver = ParamResolver()
        step = _make_step(params={"x": "$s1.result.nested"})
        prior = {"s1": _success(data={"nested": {"a": 1, "b": 2}})}

        params, _ = resolver.resolve(step, prior)
        assert params["x"] == {"a": 1, "b": 2}

    def test_resolved_value_can_be_list(self) -> None:
        """Resolved value can be a list if it's the leaf."""
        resolver = ParamResolver()
        step = _make_step(params={"x": "$s1.result.items"})
        prior = {"s1": _success(data={"items": [1, 2, 3]})}

        params, _ = resolver.resolve(step, prior)
        assert params["x"] == [1, 2, 3]
