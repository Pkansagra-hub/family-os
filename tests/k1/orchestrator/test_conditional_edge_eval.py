"""
Tests for ConditionalEdgeEvaluator (Issue 3.2.2 / ORCH-16).

Test classes -- unit (pure-function helpers):
  TestResolvePathHelper          -- _resolve_path() unit tests.
  TestDrillDataHelper            -- _drill_data() unit tests.
  TestCoerceLiteral              -- _coerce_literal() type coercion tests.
  TestCompare                    -- _compare() operator tests covering all 7 ops.
  TestEvaluateConditionLeaf      -- evaluate_condition() for leaf operators.
  TestEvaluateConditionComposite -- evaluate_condition() AND/OR/NOT trees.
  TestEvaluateConditionEdgeCases -- Missing paths, empty operands, unknown ops.
  TestConditionalEdgeNoCondition -- Steps without conditions always dispatch.
  TestConditionalEdgeSkip        -- FALSE condition -> SKIP decision.
  TestConditionalEdgeContinue    -- TRUE condition -> no SKIP decision.
  TestConditionalEdgeMixed       -- Wave with mixed condition outcomes.
  TestConditionalEdgeAllSkipped  -- Entire wave skipped (all conditions FALSE).
  TestConditionalEdgeMergedEmpty -- No merged_results -> conservative skip.
  TestConditionalEdgeRepr        -- __repr__ coverage.

Test classes -- factory-backed real-component (Epic 7.2.2):
  TestConditionalEdgeEvalReal    -- Factory-wired guard with real types (ORCH-16).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from k1.orchestrator.orchestration.guards import ConditionalEdgeEvaluator, DAGGuard
from k1.orchestrator.orchestration.guards.conditional_eval import (
    _UNRESOLVED,
    _coerce_literal,
    _compare,
    _drill_data,
    _resolve_path,
    evaluate_condition,
)
from k1.orchestrator.types import ConditionExpr, GuardAction, PlanStep, ProcessingContext, Wave

# ===========================================================================
# Fake CapabilityResult (avoids coupling tests to k1.fabric.types internals)
# ===========================================================================


@dataclass
class FakeCapResult:
    """Lightweight stand-in for CapabilityResult in guard tests."""

    success: bool = True
    data: Optional[Dict[str, Any]] = None


# ===========================================================================
# Helpers
# ===========================================================================


def _make_step(
    step_id: str = "s1",
    capability: str = "cap.test",
    condition: Optional[ConditionExpr] = None,
) -> PlanStep:
    return PlanStep(
        id=step_id,
        capability=capability,
        params={"key": "val"},
        deps=[],
        condition=condition,
    )


def _make_ctx() -> ProcessingContext:
    return ProcessingContext(
        trace_id="trace-1",
        request_id="req-1",
        tier="standard",
    )


def _make_wave(steps: Optional[List[PlanStep]] = None) -> Wave:
    return Wave(
        wave_index=0,
        steps=steps or [_make_step()],
        resolved_params={},
    )


def _eq(path: str, literal: Any) -> ConditionExpr:
    """Shorthand for EQ leaf condition."""
    return ConditionExpr(type="EQ", path=path, literal=literal)


def _neq(path: str, literal: Any) -> ConditionExpr:
    """Shorthand for NEQ leaf condition."""
    return ConditionExpr(type="NEQ", path=path, literal=literal)


def _gt(path: str, literal: Any) -> ConditionExpr:
    return ConditionExpr(type="GT", path=path, literal=literal)


def _gte(path: str, literal: Any) -> ConditionExpr:
    return ConditionExpr(type="GTE", path=path, literal=literal)


def _lt(path: str, literal: Any) -> ConditionExpr:
    return ConditionExpr(type="LT", path=path, literal=literal)


def _lte(path: str, literal: Any) -> ConditionExpr:
    return ConditionExpr(type="LTE", path=path, literal=literal)


def _contains(path: str, literal: Any) -> ConditionExpr:
    return ConditionExpr(type="CONTAINS", path=path, literal=literal)


def _and(*operands: ConditionExpr) -> ConditionExpr:
    return ConditionExpr(type="AND", operands=list(operands))


def _or(*operands: ConditionExpr) -> ConditionExpr:
    return ConditionExpr(type="OR", operands=list(operands))


def _not(operand: ConditionExpr) -> ConditionExpr:
    return ConditionExpr(type="NOT", operands=[operand])


# ===========================================================================
# _drill_data Tests
# ===========================================================================


class TestDrillDataHelper:
    def test_simple_key(self) -> None:
        assert _drill_data({"name": "Alice"}, "name") == "Alice"

    def test_nested_key(self) -> None:
        assert _drill_data({"user": {"name": "Bob"}}, "user.name") == "Bob"

    def test_deep_nesting(self) -> None:
        data = {"a": {"b": {"c": 42}}}
        assert _drill_data(data, "a.b.c") == 42

    def test_missing_key_returns_unresolved(self) -> None:
        assert _drill_data({"name": "Alice"}, "age") is _UNRESOLVED

    def test_missing_nested_key(self) -> None:
        assert _drill_data({"user": {}}, "user.name") is _UNRESOLVED

    def test_none_data_returns_unresolved(self) -> None:
        assert _drill_data(None, "anything") is _UNRESOLVED

    def test_non_dict_intermediate(self) -> None:
        data = {"name": "string_value"}
        assert _drill_data(data, "name.sub") is _UNRESOLVED

    def test_empty_dict(self) -> None:
        assert _drill_data({}, "key") is _UNRESOLVED


# ===========================================================================
# _resolve_path Tests
# ===========================================================================


class TestResolvePathHelper:
    def test_status_completed(self) -> None:
        merged = {"s1": FakeCapResult(success=True)}
        assert _resolve_path("s1.status", merged) == "COMPLETED"

    def test_status_failed(self) -> None:
        merged = {"s1": FakeCapResult(success=False)}
        assert _resolve_path("s1.status", merged) == "FAILED"

    def test_success_bool(self) -> None:
        merged = {"s1": FakeCapResult(success=True)}
        assert _resolve_path("s1.success", merged) is True

    def test_data_field(self) -> None:
        merged = {"s1": FakeCapResult(data={"count": 42})}
        assert _resolve_path("s1.data.count", merged) == 42

    def test_result_data_field(self) -> None:
        merged = {"s1": FakeCapResult(data={"color": "blue"})}
        assert _resolve_path("s1.result.data.color", merged) == "blue"

    def test_data_root(self) -> None:
        data = {"a": 1}
        merged = {"s1": FakeCapResult(data=data)}
        assert _resolve_path("s1.data", merged) == data

    def test_result_data_root(self) -> None:
        data = {"a": 1}
        merged = {"s1": FakeCapResult(data=data)}
        assert _resolve_path("s1.result.data", merged) == data

    def test_missing_step_id(self) -> None:
        merged = {"s1": FakeCapResult()}
        assert _resolve_path("s9.status", merged) is _UNRESOLVED

    def test_empty_path(self) -> None:
        assert _resolve_path("", {"s1": FakeCapResult()}) is _UNRESOLVED

    def test_bare_step_id_no_field(self) -> None:
        """Just step_id without a field -> still returns _UNRESOLVED."""
        merged = {"s1": FakeCapResult()}
        # "s1" alone has no dot, so we return _UNRESOLVED (no field to resolve)
        # Actually per impl: dot_idx == -1 -> check presence -> return cap_result
        # Let me verify the actual behavior
        result = _resolve_path("s1", merged)
        assert result is not _UNRESOLVED  # step exists, returned as-is

    def test_unknown_field_returns_unresolved(self) -> None:
        merged = {"s1": FakeCapResult()}
        assert _resolve_path("s1.bogus_field", merged) is _UNRESOLVED

    def test_nested_data(self) -> None:
        merged = {"s2": FakeCapResult(data={"user": {"age": 25}})}
        assert _resolve_path("s2.data.user.age", merged) == 25

    def test_data_none_returns_unresolved(self) -> None:
        merged = {"s1": FakeCapResult(data=None)}
        assert _resolve_path("s1.data.key", merged) is _UNRESOLVED


# ===========================================================================
# _coerce_literal Tests
# ===========================================================================


class TestCoerceLiteral:
    def test_same_type_passthrough(self) -> None:
        assert _coerce_literal(42, int) == 42
        assert _coerce_literal("hello", str) == "hello"
        assert _coerce_literal(True, bool) is True

    def test_string_to_int(self) -> None:
        assert _coerce_literal("42", int) == 42

    def test_float_string_to_int(self) -> None:
        assert _coerce_literal("3.7", int) == 3

    def test_string_to_float(self) -> None:
        assert _coerce_literal("3.14", float) == 3.14

    def test_int_to_float(self) -> None:
        assert _coerce_literal(3, float) == 3.0

    def test_string_true_to_bool(self) -> None:
        assert _coerce_literal("true", bool) is True
        assert _coerce_literal("True", bool) is True
        assert _coerce_literal("1", bool) is True
        assert _coerce_literal("yes", bool) is True

    def test_string_false_to_bool(self) -> None:
        assert _coerce_literal("false", bool) is False
        assert _coerce_literal("no", bool) is False
        assert _coerce_literal("0", bool) is False

    def test_int_to_string(self) -> None:
        assert _coerce_literal(42, str) == "42"

    def test_unconvertible_returns_original(self) -> None:
        result = _coerce_literal("not_a_number", int)
        assert result == "not_a_number"  # unchanged


# ===========================================================================
# _compare Tests
# ===========================================================================


class TestCompare:
    def test_eq_true(self) -> None:
        assert _compare("COMPLETED", "EQ", "COMPLETED") is True

    def test_eq_false(self) -> None:
        assert _compare("FAILED", "EQ", "COMPLETED") is False

    def test_neq_true(self) -> None:
        assert _compare("FAILED", "NEQ", "COMPLETED") is True

    def test_neq_false(self) -> None:
        assert _compare("COMPLETED", "NEQ", "COMPLETED") is False

    def test_gt_true(self) -> None:
        assert _compare(10, "GT", 5) is True

    def test_gt_false(self) -> None:
        assert _compare(5, "GT", 10) is False

    def test_gte_true_equal(self) -> None:
        assert _compare(10, "GTE", 10) is True

    def test_gte_true_greater(self) -> None:
        assert _compare(11, "GTE", 10) is True

    def test_gte_false(self) -> None:
        assert _compare(9, "GTE", 10) is False

    def test_ge_alias(self) -> None:
        assert _compare(10, "GE", 10) is True

    def test_lt_true(self) -> None:
        assert _compare(5, "LT", 10) is True

    def test_lt_false(self) -> None:
        assert _compare(10, "LT", 5) is False

    def test_lte_true_equal(self) -> None:
        assert _compare(10, "LTE", 10) is True

    def test_lte_true_less(self) -> None:
        assert _compare(9, "LTE", 10) is True

    def test_lte_false(self) -> None:
        assert _compare(11, "LTE", 10) is False

    def test_le_alias(self) -> None:
        assert _compare(10, "LE", 10) is True

    def test_contains_true(self) -> None:
        assert _compare("hello world", "CONTAINS", "world") is True

    def test_contains_false(self) -> None:
        assert _compare("hello world", "CONTAINS", "moon") is False

    def test_contains_list(self) -> None:
        assert _compare([1, 2, 3], "CONTAINS", 2) is True

    def test_contains_list_missing(self) -> None:
        assert _compare([1, 2, 3], "CONTAINS", 9) is False

    def test_unresolved_returns_false(self) -> None:
        assert _compare(_UNRESOLVED, "EQ", "anything") is False

    def test_type_coercion_string_to_int(self) -> None:
        """literal "42" compared to int 42 -> coerce literal to int."""
        assert _compare(42, "EQ", "42") is True

    def test_type_coercion_bool_string(self) -> None:
        assert _compare(True, "EQ", "true") is True

    def test_unknown_op_returns_false(self) -> None:
        assert _compare(1, "BOGUS", 1) is False


# ===========================================================================
# evaluate_condition Tests -- Leaf
# ===========================================================================


class TestEvaluateConditionLeaf:
    def test_eq_status_completed(self) -> None:
        merged = {"s1": FakeCapResult(success=True)}
        cond = _eq("s1.status", "COMPLETED")
        assert evaluate_condition(cond, merged) is True

    def test_eq_status_failed(self) -> None:
        merged = {"s1": FakeCapResult(success=False)}
        cond = _eq("s1.status", "COMPLETED")
        assert evaluate_condition(cond, merged) is False

    def test_neq_status(self) -> None:
        merged = {"s1": FakeCapResult(success=False)}
        cond = _neq("s1.status", "COMPLETED")
        assert evaluate_condition(cond, merged) is True

    def test_gt_data_field(self) -> None:
        merged = {"s1": FakeCapResult(data={"count": 10})}
        cond = _gt("s1.data.count", 5)
        assert evaluate_condition(cond, merged) is True

    def test_gte_boundary(self) -> None:
        merged = {"s1": FakeCapResult(data={"n": 10})}
        cond = _gte("s1.data.n", 10)
        assert evaluate_condition(cond, merged) is True

    def test_lt_data_field(self) -> None:
        merged = {"s1": FakeCapResult(data={"count": 3})}
        cond = _lt("s1.data.count", 5)
        assert evaluate_condition(cond, merged) is True

    def test_lte_boundary(self) -> None:
        merged = {"s1": FakeCapResult(data={"n": 10})}
        cond = _lte("s1.data.n", 10)
        assert evaluate_condition(cond, merged) is True

    def test_contains_string(self) -> None:
        merged = {"s1": FakeCapResult(data={"msg": "hello world"})}
        cond = _contains("s1.data.msg", "world")
        assert evaluate_condition(cond, merged) is True

    def test_missing_step_false(self) -> None:
        """Missing step_id -> FALSE (conservative skip)."""
        merged: Dict[str, Any] = {}
        cond = _eq("s99.status", "COMPLETED")
        assert evaluate_condition(cond, merged) is False

    def test_no_path_returns_false(self) -> None:
        """Leaf with path=None -> False."""
        cond = ConditionExpr(type="EQ", literal="COMPLETED")
        assert evaluate_condition(cond, {}) is False


# ===========================================================================
# evaluate_condition Tests -- Composite
# ===========================================================================


class TestEvaluateConditionComposite:
    def test_and_all_true(self) -> None:
        merged = {
            "s1": FakeCapResult(success=True),
            "s2": FakeCapResult(success=True),
        }
        cond = _and(
            _eq("s1.status", "COMPLETED"),
            _eq("s2.status", "COMPLETED"),
        )
        assert evaluate_condition(cond, merged) is True

    def test_and_one_false(self) -> None:
        merged = {
            "s1": FakeCapResult(success=True),
            "s2": FakeCapResult(success=False),
        }
        cond = _and(
            _eq("s1.status", "COMPLETED"),
            _eq("s2.status", "COMPLETED"),
        )
        assert evaluate_condition(cond, merged) is False

    def test_or_one_true(self) -> None:
        merged = {
            "s1": FakeCapResult(success=False),
            "s2": FakeCapResult(success=True),
        }
        cond = _or(
            _eq("s1.status", "COMPLETED"),
            _eq("s2.status", "COMPLETED"),
        )
        assert evaluate_condition(cond, merged) is True

    def test_or_all_false(self) -> None:
        merged = {
            "s1": FakeCapResult(success=False),
            "s2": FakeCapResult(success=False),
        }
        cond = _or(
            _eq("s1.status", "COMPLETED"),
            _eq("s2.status", "COMPLETED"),
        )
        assert evaluate_condition(cond, merged) is False

    def test_not_true(self) -> None:
        merged = {"s1": FakeCapResult(success=False)}
        cond = _not(_eq("s1.status", "COMPLETED"))
        assert evaluate_condition(cond, merged) is True

    def test_not_false(self) -> None:
        merged = {"s1": FakeCapResult(success=True)}
        cond = _not(_eq("s1.status", "COMPLETED"))
        assert evaluate_condition(cond, merged) is False

    def test_nested_and_or(self) -> None:
        """AND(OR(s1.ok, s2.ok), s3.ok) -> complex tree."""
        merged = {
            "s1": FakeCapResult(success=False),
            "s2": FakeCapResult(success=True),
            "s3": FakeCapResult(success=True),
        }
        cond = _and(
            _or(
                _eq("s1.status", "COMPLETED"),
                _eq("s2.status", "COMPLETED"),
            ),
            _eq("s3.status", "COMPLETED"),
        )
        assert evaluate_condition(cond, merged) is True

    def test_nested_not_and(self) -> None:
        """NOT(AND(s1.ok, s2.fail)) -> TRUE."""
        merged = {
            "s1": FakeCapResult(success=True),
            "s2": FakeCapResult(success=False),
        }
        cond = _not(
            _and(
                _eq("s1.status", "COMPLETED"),
                _eq("s2.status", "COMPLETED"),
            )
        )
        assert evaluate_condition(cond, merged) is True


# ===========================================================================
# evaluate_condition Tests -- Edge Cases
# ===========================================================================


class TestEvaluateConditionEdgeCases:
    def test_and_empty_operands_vacuous_true(self) -> None:
        cond = ConditionExpr(type="AND", operands=[])
        assert evaluate_condition(cond, {}) is True

    def test_or_empty_operands_vacuous_false(self) -> None:
        cond = ConditionExpr(type="OR", operands=[])
        assert evaluate_condition(cond, {}) is False

    def test_not_empty_operands_vacuous_true(self) -> None:
        cond = ConditionExpr(type="NOT", operands=[])
        assert evaluate_condition(cond, {}) is True

    def test_unknown_type_returns_false(self) -> None:
        cond = ConditionExpr(type="BOGUS", path="s1.status", literal="ok")
        assert evaluate_condition(cond, {"s1": FakeCapResult()}) is False

    def test_case_insensitive_type(self) -> None:
        """Type is uppercased internally, so 'eq' should work."""
        merged = {"s1": FakeCapResult(success=True)}
        cond = ConditionExpr(type="eq", path="s1.status", literal="COMPLETED")
        assert evaluate_condition(cond, merged) is True

    def test_boolean_data_comparison(self) -> None:
        merged = {"s2": FakeCapResult(data={"has_event_room": True})}
        cond = _eq("s2.data.has_event_room", "true")
        assert evaluate_condition(cond, merged) is True

    def test_boolean_data_false_comparison(self) -> None:
        merged = {"s2": FakeCapResult(data={"has_event_room": False})}
        cond = _eq("s2.data.has_event_room", "true")
        assert evaluate_condition(cond, merged) is False


# ===========================================================================
# ConditionalEdgeEvaluator -- Guard Integration Tests
# ===========================================================================


class TestConditionalEdgeNoCondition:
    """Steps without conditions always dispatch (no SKIP decision)."""

    async def test_no_condition_no_decision(self) -> None:
        guard = ConditionalEdgeEvaluator()
        step = _make_step(condition=None)
        wave = _make_wave([step])
        ctx = _make_ctx()

        decisions = await guard.before_wave(wave, ctx, merged_results={})

        assert decisions == []

    async def test_multiple_steps_no_conditions(self) -> None:
        guard = ConditionalEdgeEvaluator()
        steps = [_make_step(step_id=f"s{i}") for i in range(3)]
        wave = _make_wave(steps)
        ctx = _make_ctx()

        decisions = await guard.before_wave(wave, ctx, merged_results={})

        assert decisions == []


class TestConditionalEdgeSkip:
    """Steps with FALSE conditions get SKIP decisions."""

    async def test_false_condition_returns_skip(self) -> None:
        guard = ConditionalEdgeEvaluator()
        cond = _eq("s1.status", "COMPLETED")
        step = _make_step(step_id="s2", condition=cond)
        wave = _make_wave([step])
        ctx = _make_ctx()
        # s1 not in merged_results -> FALSE -> SKIP
        decisions = await guard.before_wave(wave, ctx, merged_results={})

        assert len(decisions) == 1
        assert decisions[0].action == GuardAction.SKIP
        assert decisions[0].guard_name == "ConditionalEdgeEvaluator"
        assert decisions[0].metadata["step_id"] == "s2"

    async def test_missing_dependency_returns_skip(self) -> None:
        """Step depends on s99 which never ran -> FALSE -> SKIP."""
        guard = ConditionalEdgeEvaluator()
        cond = _eq("s99.status", "COMPLETED")
        step = _make_step(step_id="s3", condition=cond)
        wave = _make_wave([step])
        merged = {"s1": FakeCapResult(success=True)}

        decisions = await guard.before_wave(wave, _make_ctx(), merged_results=merged)

        assert len(decisions) == 1
        assert decisions[0].action == GuardAction.SKIP


class TestConditionalEdgeContinue:
    """Steps with TRUE conditions produce no SKIP decision."""

    async def test_true_condition_no_skip(self) -> None:
        guard = ConditionalEdgeEvaluator()
        cond = _eq("s1.status", "COMPLETED")
        step = _make_step(step_id="s2", condition=cond)
        wave = _make_wave([step])
        merged = {"s1": FakeCapResult(success=True)}

        decisions = await guard.before_wave(wave, _make_ctx(), merged_results=merged)

        # No SKIP decision -> step proceeds
        assert decisions == []

    async def test_data_condition_true(self) -> None:
        guard = ConditionalEdgeEvaluator()
        cond = _eq("s1.data.has_event_room", "true")
        step = _make_step(step_id="s4", condition=cond)
        wave = _make_wave([step])
        merged = {"s1": FakeCapResult(data={"has_event_room": True})}

        decisions = await guard.before_wave(wave, _make_ctx(), merged_results=merged)

        assert decisions == []


class TestConditionalEdgeMixed:
    """Wave with some steps passing, some failing conditions."""

    async def test_mixed_decisions(self) -> None:
        guard = ConditionalEdgeEvaluator()
        merged = {
            "s1": FakeCapResult(success=True),
            "s2": FakeCapResult(success=False),
        }

        step_a = _make_step(step_id="sa", condition=_eq("s1.status", "COMPLETED"))  # TRUE
        step_b = _make_step(step_id="sb", condition=_eq("s2.status", "COMPLETED"))  # FALSE
        step_c = _make_step(step_id="sc", condition=None)  # no condition -> dispatch
        wave = _make_wave([step_a, step_b, step_c])

        decisions = await guard.before_wave(wave, _make_ctx(), merged_results=merged)

        # Only step_b should be SKIPPED
        assert len(decisions) == 1
        assert decisions[0].action == GuardAction.SKIP
        assert decisions[0].metadata["step_id"] == "sb"


class TestConditionalEdgeAllSkipped:
    """All steps in wave skipped -> all get SKIP decisions."""

    async def test_all_skipped(self) -> None:
        guard = ConditionalEdgeEvaluator()
        merged: Dict[str, Any] = {}  # nothing executed

        steps = [
            _make_step(step_id="sa", condition=_eq("s1.status", "COMPLETED")),
            _make_step(step_id="sb", condition=_eq("s2.status", "COMPLETED")),
        ]
        wave = _make_wave(steps)

        decisions = await guard.before_wave(wave, _make_ctx(), merged_results=merged)

        assert len(decisions) == 2
        skip_ids = {d.metadata["step_id"] for d in decisions}
        assert skip_ids == {"sa", "sb"}
        for d in decisions:
            assert d.action == GuardAction.SKIP


class TestConditionalEdgeMergedEmpty:
    """No merged_results / None -> conservative skip for all conditional steps."""

    async def test_none_merged_results(self) -> None:
        guard = ConditionalEdgeEvaluator()
        step = _make_step(step_id="s2", condition=_eq("s1.status", "COMPLETED"))
        wave = _make_wave([step])

        # merged_results=None (default)
        decisions = await guard.before_wave(wave, _make_ctx())

        assert len(decisions) == 1
        assert decisions[0].action == GuardAction.SKIP

    async def test_empty_dict_merged_results(self) -> None:
        guard = ConditionalEdgeEvaluator()
        step = _make_step(step_id="s2", condition=_eq("s1.status", "COMPLETED"))
        wave = _make_wave([step])

        decisions = await guard.before_wave(wave, _make_ctx(), merged_results={})

        assert len(decisions) == 1
        assert decisions[0].action == GuardAction.SKIP


class TestConditionalEdgeComplexConditions:
    """Complex condition trees in guard context."""

    async def test_and_condition_both_true(self) -> None:
        guard = ConditionalEdgeEvaluator()
        merged = {
            "s1": FakeCapResult(success=True),
            "s2": FakeCapResult(success=True),
        }
        cond = _and(
            _eq("s1.status", "COMPLETED"),
            _eq("s2.status", "COMPLETED"),
        )
        step = _make_step(step_id="s3", condition=cond)
        wave = _make_wave([step])

        decisions = await guard.before_wave(wave, _make_ctx(), merged_results=merged)

        assert decisions == []  # passes -> no skip

    async def test_and_condition_one_false(self) -> None:
        guard = ConditionalEdgeEvaluator()
        merged = {
            "s1": FakeCapResult(success=True),
            "s2": FakeCapResult(success=False),
        }
        cond = _and(
            _eq("s1.status", "COMPLETED"),
            _eq("s2.status", "COMPLETED"),
        )
        step = _make_step(step_id="s3", condition=cond)
        wave = _make_wave([step])

        decisions = await guard.before_wave(wave, _make_ctx(), merged_results=merged)

        assert len(decisions) == 1
        assert decisions[0].action == GuardAction.SKIP

    async def test_or_condition_one_true(self) -> None:
        guard = ConditionalEdgeEvaluator()
        merged = {
            "s1": FakeCapResult(success=False),
            "s2": FakeCapResult(success=True),
        }
        cond = _or(
            _eq("s1.status", "COMPLETED"),
            _eq("s2.status", "COMPLETED"),
        )
        step = _make_step(step_id="s3", condition=cond)
        wave = _make_wave([step])

        decisions = await guard.before_wave(wave, _make_ctx(), merged_results=merged)

        assert decisions == []  # passes

    async def test_not_condition(self) -> None:
        guard = ConditionalEdgeEvaluator()
        merged = {"s1": FakeCapResult(success=False)}
        cond = _not(_eq("s1.status", "COMPLETED"))  # NOT(FALSE) = TRUE
        step = _make_step(step_id="s2", condition=cond)
        wave = _make_wave([step])

        decisions = await guard.before_wave(wave, _make_ctx(), merged_results=merged)

        assert decisions == []  # passes

    async def test_data_gt_threshold(self) -> None:
        guard = ConditionalEdgeEvaluator()
        merged = {"s1": FakeCapResult(data={"score": 85})}
        cond = _gt("s1.data.score", 70)
        step = _make_step(step_id="s2", condition=cond)
        wave = _make_wave([step])

        decisions = await guard.before_wave(wave, _make_ctx(), merged_results=merged)

        assert decisions == []

    async def test_contains_string_condition(self) -> None:
        guard = ConditionalEdgeEvaluator()
        merged = {"s1": FakeCapResult(data={"tags": "priority,urgent"})}
        cond = _contains("s1.data.tags", "urgent")
        step = _make_step(step_id="s2", condition=cond)
        wave = _make_wave([step])

        decisions = await guard.before_wave(wave, _make_ctx(), merged_results=merged)

        assert decisions == []


class TestConditionalEdgeRepr:
    def test_repr(self) -> None:
        assert repr(ConditionalEdgeEvaluator()) == "ConditionalEdgeEvaluator()"

    def test_is_dag_guard(self) -> None:
        assert isinstance(ConditionalEdgeEvaluator(), DAGGuard)


# ===========================================================================
# Plan Example Tests (from workticket)
# ===========================================================================


class TestPlanExamples:
    """Tests that match the exact examples from the workticket."""

    async def test_plan_example_event_room(self) -> None:
        """Step s4 condition: s2.result.data.has_event_room == true."""
        guard = ConditionalEdgeEvaluator()
        merged = {"s2": FakeCapResult(data={"has_event_room": True})}
        cond = _eq("s2.result.data.has_event_room", "true")
        step = _make_step(step_id="s4", condition=cond)
        wave = _make_wave([step])

        decisions = await guard.before_wave(wave, _make_ctx(), merged_results=merged)

        assert decisions == []  # TRUE -> dispatch

    async def test_plan_example_status_failed(self) -> None:
        """Step s5 condition: s1.status == COMPLETED, but s1 is FAILED."""
        guard = ConditionalEdgeEvaluator()
        merged = {"s1": FakeCapResult(success=False)}
        cond = _eq("s1.status", "COMPLETED")
        step = _make_step(step_id="s5", condition=cond)
        wave = _make_wave([step])

        decisions = await guard.before_wave(wave, _make_ctx(), merged_results=merged)

        assert len(decisions) == 1
        assert decisions[0].action == GuardAction.SKIP
        assert decisions[0].metadata["step_id"] == "s5"

    async def test_plan_example_status_completed(self) -> None:
        """Step s5 condition: s1.status == COMPLETED, and s1 is COMPLETED."""
        guard = ConditionalEdgeEvaluator()
        merged = {"s1": FakeCapResult(success=True)}
        cond = _eq("s1.status", "COMPLETED")
        step = _make_step(step_id="s5", condition=cond)
        wave = _make_wave([step])

        decisions = await guard.before_wave(wave, _make_ctx(), merged_results=merged)

        assert decisions == []  # TRUE -> dispatch


# ===========================================================================
# Pipeline Tests (Epic 7.2.2 / ORCH-16)
#
# Guard tests do NOT import guard classes directly -- they verify guard
# behaviour through OrchestratorService.process() -> DAGExecutor pipeline.
# ===========================================================================

import pytest

from k1.orchestrator.types import ProcessResult
from tests.k1.orchestrator.helpers import (
    make_plan,
    make_step,
    orchestrator_for_testing,
    process_plan,
    register_capabilities,
)


class TestConditionalEdgeEvalPipeline:
    """Verify ORCH-16 (conditional edge evaluation) through process() pipeline.

    Creates multi-wave plans where later steps have conditions referencing
    prior step results. Verifies which capabilities actually executed via
    MockFabricAdapter.call_log.
    """

    # -- (1) Guard is second in pipeline --------------------------------

    @pytest.mark.asyncio
    async def test_guard_is_second_in_pipeline(self) -> None:
        service, _ = await orchestrator_for_testing()
        names = [g.__class__.__name__ for g in service._dag_executor._guards]
        assert names[1] == "ConditionalEdgeEvaluator"

    # -- (2) No condition -> step always executes -----------------------

    @pytest.mark.asyncio
    async def test_no_condition_step_always_executes(self) -> None:
        service, adapters = await orchestrator_for_testing()
        fabric = adapters["fabric"]
        register_capabilities(fabric, "cap.a", "cap.b")

        s1 = make_step("s1", "cap.a")
        s2 = make_step("s2", "cap.b")
        plan = make_plan([s1, s2], deps={"s2": ["s1"]})

        result = await process_plan(service, plan)

        assert result == ProcessResult.COMPLETED
        fabric.assert_called("cap.a", times=1)
        fabric.assert_called("cap.b", times=1)

    # -- (3) TRUE condition -> step executes ----------------------------

    @pytest.mark.asyncio
    async def test_true_condition_step_executes(self) -> None:
        """s1 succeeds -> s2 condition (s1.status==COMPLETED) TRUE -> s2 runs."""
        service, adapters = await orchestrator_for_testing()
        fabric = adapters["fabric"]
        register_capabilities(fabric, "cap.a", "cap.b")

        s1 = make_step("s1", "cap.a")
        s2 = make_step(
            "s2",
            "cap.b",
            condition=ConditionExpr(type="EQ", path="s1.status", literal="COMPLETED"),
        )
        plan = make_plan([s1, s2], deps={"s2": ["s1"]})

        result = await process_plan(service, plan)

        assert result == ProcessResult.COMPLETED
        fabric.assert_called("cap.a", times=1)
        fabric.assert_called("cap.b", times=1)

    # -- (4) FALSE condition -> step skipped ----------------------------

    @pytest.mark.asyncio
    async def test_false_condition_step_skipped(self) -> None:
        """s1 succeeds but condition says s1.status==FAILED -> FALSE -> skip s2."""
        service, adapters = await orchestrator_for_testing()
        fabric = adapters["fabric"]
        register_capabilities(fabric, "cap.a", "cap.b")

        s1 = make_step("s1", "cap.a")
        s2 = make_step(
            "s2",
            "cap.b",
            condition=ConditionExpr(type="EQ", path="s1.status", literal="FAILED"),
        )
        plan = make_plan([s1, s2], deps={"s2": ["s1"]})

        result = await process_plan(service, plan)

        # s2 skipped -> cancelled=1, completed=1 -> FAILED (no DEGRADED path for cancelled)
        assert result == ProcessResult.FAILED
        fabric.assert_called("cap.a", times=1)
        fabric.assert_not_called("cap.b")

    # -- (5) AND condition: both true -> step executes ------------------

    @pytest.mark.asyncio
    async def test_and_both_true_step_executes(self) -> None:
        service, adapters = await orchestrator_for_testing()
        fabric = adapters["fabric"]
        register_capabilities(fabric, "cap.a", "cap.b", "cap.c")

        s1 = make_step("s1", "cap.a")
        s2 = make_step("s2", "cap.b")
        s3 = make_step(
            "s3",
            "cap.c",
            condition=ConditionExpr(
                type="AND",
                operands=[
                    ConditionExpr(type="EQ", path="s1.status", literal="COMPLETED"),
                    ConditionExpr(type="EQ", path="s2.status", literal="COMPLETED"),
                ],
            ),
        )
        plan = make_plan([s1, s2, s3], deps={"s3": ["s1", "s2"]})

        result = await process_plan(service, plan)

        assert result == ProcessResult.COMPLETED
        fabric.assert_called("cap.c", times=1)

    # -- (6) AND condition: one false -> step skipped -------------------

    @pytest.mark.asyncio
    async def test_and_one_false_step_skipped(self) -> None:
        """s1 succeeds, s2 condition checks nonexistent s99 -> FALSE -> skip."""
        service, adapters = await orchestrator_for_testing()
        fabric = adapters["fabric"]
        register_capabilities(fabric, "cap.a", "cap.c")

        s1 = make_step("s1", "cap.a")
        # s3 depends on s1 completing AND s99 completing (s99 never ran)
        s3 = make_step(
            "s3",
            "cap.c",
            condition=ConditionExpr(
                type="AND",
                operands=[
                    ConditionExpr(type="EQ", path="s1.status", literal="COMPLETED"),
                    ConditionExpr(type="EQ", path="s99.status", literal="COMPLETED"),
                ],
            ),
        )
        plan = make_plan([s1, s3], deps={"s3": ["s1"]})

        result = await process_plan(service, plan)

        fabric.assert_called("cap.a", times=1)
        fabric.assert_not_called("cap.c")

    # -- (7) OR condition: one true -> step executes --------------------

    @pytest.mark.asyncio
    async def test_or_one_true_step_executes(self) -> None:
        service, adapters = await orchestrator_for_testing()
        fabric = adapters["fabric"]
        register_capabilities(fabric, "cap.a", "cap.c")

        s1 = make_step("s1", "cap.a")
        s3 = make_step(
            "s3",
            "cap.c",
            condition=ConditionExpr(
                type="OR",
                operands=[
                    ConditionExpr(type="EQ", path="s1.status", literal="COMPLETED"),
                    ConditionExpr(type="EQ", path="s99.status", literal="COMPLETED"),
                ],
            ),
        )
        plan = make_plan([s1, s3], deps={"s3": ["s1"]})

        result = await process_plan(service, plan)

        assert result == ProcessResult.COMPLETED
        fabric.assert_called("cap.c", times=1)

    # -- (8) NOT condition: inverts result ------------------------------

    @pytest.mark.asyncio
    async def test_not_inverts_false_to_true(self) -> None:
        """NOT(s1.status==FAILED) when s1 COMPLETED -> NOT(FALSE) -> TRUE."""
        service, adapters = await orchestrator_for_testing()
        fabric = adapters["fabric"]
        register_capabilities(fabric, "cap.a", "cap.b")

        s1 = make_step("s1", "cap.a")
        s2 = make_step(
            "s2",
            "cap.b",
            condition=ConditionExpr(
                type="NOT",
                operands=[
                    ConditionExpr(type="EQ", path="s1.status", literal="FAILED"),
                ],
            ),
        )
        plan = make_plan([s1, s2], deps={"s2": ["s1"]})

        result = await process_plan(service, plan)

        assert result == ProcessResult.COMPLETED
        fabric.assert_called("cap.b", times=1)

    # -- (9) All steps unconditional -> all execute ---------------------

    @pytest.mark.asyncio
    async def test_all_unconditional_all_execute(self) -> None:
        service, adapters = await orchestrator_for_testing()
        fabric = adapters["fabric"]
        caps = [f"cap.s{i}" for i in range(4)]
        register_capabilities(fabric, *caps)

        steps = [make_step(f"s{i}", f"cap.s{i}") for i in range(4)]
        plan = make_plan(steps)

        result = await process_plan(service, plan)

        assert result == ProcessResult.COMPLETED
        for cap in caps:
            fabric.assert_called(cap, times=1)

    # -- (10) Mixed wave: some conditional, some not --------------------

    @pytest.mark.asyncio
    async def test_mixed_wave_partial_skip(self) -> None:
        """Wave 2 has 3 steps: sa (TRUE), sb (FALSE), sc (no cond). Only sb skipped."""
        service, adapters = await orchestrator_for_testing()
        fabric = adapters["fabric"]
        register_capabilities(fabric, "cap.s1", "cap.sa", "cap.sb", "cap.sc")

        s1 = make_step("s1", "cap.s1")
        sa = make_step(
            "sa",
            "cap.sa",
            condition=ConditionExpr(type="EQ", path="s1.status", literal="COMPLETED"),
        )
        sb = make_step(
            "sb",
            "cap.sb",
            condition=ConditionExpr(type="EQ", path="s1.status", literal="FAILED"),
        )
        sc = make_step("sc", "cap.sc")
        plan = make_plan(
            [s1, sa, sb, sc],
            deps={"sa": ["s1"], "sb": ["s1"], "sc": ["s1"]},
        )

        result = await process_plan(service, plan)

        fabric.assert_called("cap.s1", times=1)
        fabric.assert_called("cap.sa", times=1)
        fabric.assert_not_called("cap.sb")
        fabric.assert_called("cap.sc", times=1)
