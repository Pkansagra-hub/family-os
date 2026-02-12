"""
k1.orchestrator.orchestration.guards.conditional_eval -- ORCH-16.

Pre-wave guard that evaluates conditional edges on PlanStep.condition.
Steps whose conditions evaluate FALSE are marked SKIPPED and removed
from the wave dispatch list.

Guard pipeline position: G1 (pre-wave).

Design:
  - Stateless: no constructor state, no instance caching.
  - Pure evaluator: resolves ConditionExpr tree against merged_results.
  - Conservative: missing step_id in merged_results -> FALSE.
  - Empty condition (None) -> always dispatch.

Condition expression language (ConditionExpr from types.py):
  Leaf operators:   EQ, NEQ, GT, GTE, LT, LTE, CONTAINS
  Composite ops:    AND, OR, NOT
  Path format:      "step_id.status" | "step_id.data.json_path"
  Literal:          string, int, float, bool

  V1: simple comparisons only -- no function calls (ADR-1.1.11 Q10).

Path resolution from merged_results (Dict[str, CapabilityResult]):
  "sX.status"          -> "COMPLETED" if success else "FAILED"
  "sX.success"         -> bool
  "sX.data.field"      -> CapabilityResult.data["field"]
  "sX.result.data.field" -> same (explicit path)
  Missing step_id      -> UNRESOLVED -> condition evaluates FALSE

References:
  - orchestrator-implementation-plan.md Issue 3.2.2
  - Schema Whiteboard Section 8 (G1=ConditionalEdgeEvaluator)
  - M3-constraint-guards-worktickets.md WT-3.2.2

Exports:
  ConditionalEdgeEvaluator
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from k1.orchestrator.types import ConditionExpr, GuardAction, GuardDecision, ProcessingContext, Wave

from .base import DAGGuard

logger = logging.getLogger(__name__)

# Guard identity constant
_GUARD_NAME = "ConditionalEdgeEvaluator"

# Sentinel for unresolvable path references
_UNRESOLVED = object()

# Supported leaf comparison operators
_LEAF_OPS = frozenset({"EQ", "NEQ", "GT", "GTE", "GE", "LT", "LTE", "LE", "CONTAINS"})

# Supported composite operators
_COMPOSITE_OPS = frozenset({"AND", "OR", "NOT"})


# ------------------------------------------------------------------
# Path resolution helpers
# ------------------------------------------------------------------


def _drill_data(data: Optional[Dict[str, Any]], path: str) -> Any:
    """Drill into a nested dict via dotted path.

    Args:
        data: Root dict to drill into (CapabilityResult.data).
        path: Dotted path like "user.name" -> data["user"]["name"].

    Returns:
        Resolved value, or _UNRESOLVED sentinel if path cannot be resolved.
    """
    if data is None:
        return _UNRESOLVED
    parts = path.split(".")
    current: Any = data
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return _UNRESOLVED
    return current


def _resolve_path(
    path: str,
    merged_results: Dict[str, Any],
) -> Any:
    """Resolve a condition path against merged_results.

    Path format: "step_id.field" or "step_id.field.subfield..."

    Supported fields:
      status        -> "COMPLETED" or "FAILED" (derived from success)
      success       -> bool
      data.X        -> CapabilityResult.data["X"]
      result.data.X -> CapabilityResult.data["X"]

    Args:
        path: Dotted path string (e.g., "s1.status", "s2.data.count").
        merged_results: step_id -> CapabilityResult mapping.

    Returns:
        Resolved value, or _UNRESOLVED if not resolvable.
    """
    if not path:
        return _UNRESOLVED

    dot_idx = path.find(".")
    if dot_idx == -1:
        # Just a step_id with no field -> check presence
        return _UNRESOLVED if path not in merged_results else merged_results[path]

    step_id = path[:dot_idx]
    field_path = path[dot_idx + 1 :]

    if step_id not in merged_results:
        return _UNRESOLVED

    cap_result = merged_results[step_id]

    # Status: derived from CapabilityResult.success
    if field_path == "status":
        success = getattr(cap_result, "success", None)
        if success is None:
            return _UNRESOLVED
        return "COMPLETED" if success else "FAILED"

    # Direct success access
    if field_path == "success":
        return getattr(cap_result, "success", _UNRESOLVED)

    # Data access: "data.X" or "result.data.X"
    data = getattr(cap_result, "data", None)
    if field_path == "data":
        return data if data is not None else _UNRESOLVED
    if field_path.startswith("data."):
        return _drill_data(data, field_path[5:])
    if field_path == "result.data":
        return data if data is not None else _UNRESOLVED
    if field_path.startswith("result.data."):
        return _drill_data(data, field_path[12:])

    return _UNRESOLVED


# ------------------------------------------------------------------
# Comparison helpers
# ------------------------------------------------------------------


def _coerce_literal(literal: Any, target_type: type) -> Any:
    """Coerce literal to match the resolved value's type.

    Handles common cases: string "true" -> bool True, "42" -> int 42.
    Returns original literal if coercion fails.
    """
    if isinstance(literal, target_type):
        return literal
    try:
        if target_type is bool:
            if isinstance(literal, str):
                return literal.lower() in ("true", "1", "yes")
            return bool(literal)
        if target_type is int and isinstance(literal, (str, float)):
            return int(float(literal)) if isinstance(literal, str) else int(literal)
        if target_type is float and isinstance(literal, (str, int)):
            return float(literal)
        if target_type is str:
            return str(literal)
        return target_type(literal)
    except (ValueError, TypeError):
        return literal


def _compare(left_val: Any, op: str, literal: Any) -> bool:
    """Apply a comparison operator.

    Args:
        left_val: Resolved value from path (or _UNRESOLVED).
        op: Operator string (EQ, NEQ, GT, GTE, GE, LT, LTE, LE, CONTAINS).
        literal: Comparison value from ConditionExpr.literal.

    Returns:
        bool result of comparison. False if unresolvable.
    """
    if left_val is _UNRESOLVED:
        return False

    coerced = _coerce_literal(literal, type(left_val))

    try:
        if op == "EQ":
            return left_val == coerced
        if op == "NEQ":
            return left_val != coerced
        if op == "GT":
            return left_val > coerced
        if op in ("GTE", "GE"):
            return left_val >= coerced
        if op == "LT":
            return left_val < coerced
        if op in ("LTE", "LE"):
            return left_val <= coerced
        if op == "CONTAINS":
            return coerced in left_val
    except TypeError:
        # Incompatible types for comparison (e.g., str > int)
        logger.warning("[%s] Type error comparing %r %s %r", _GUARD_NAME, left_val, op, coerced)
        return False

    logger.warning("[%s] Unknown leaf operator: %s", _GUARD_NAME, op)
    return False


# ------------------------------------------------------------------
# Recursive condition evaluation
# ------------------------------------------------------------------


def evaluate_condition(
    condition: ConditionExpr,
    merged_results: Dict[str, Any],
) -> bool:
    """Recursively evaluate a ConditionExpr tree.

    Composite operators (AND, OR, NOT) combine sub-expression results.
    Leaf operators (EQ, NEQ, GT, ...) resolve path and compare to literal.

    Args:
        condition: ConditionExpr tree node.
        merged_results: step_id -> CapabilityResult mapping.

    Returns:
        True if condition is satisfied, False otherwise.
    """
    op_type = condition.type.upper()

    # Composite: AND -- all operands must be True
    if op_type == "AND":
        if not condition.operands:
            return True  # vacuous truth
        return all(evaluate_condition(sub, merged_results) for sub in condition.operands)

    # Composite: OR -- any operand must be True
    if op_type == "OR":
        if not condition.operands:
            return False  # vacuous falsity
        return any(evaluate_condition(sub, merged_results) for sub in condition.operands)

    # Composite: NOT -- negate single operand
    if op_type == "NOT":
        if not condition.operands:
            return True  # NOT(nothing) = vacuously true
        return not evaluate_condition(condition.operands[0], merged_results)

    # Leaf: resolve path and compare to literal
    if op_type in _LEAF_OPS:
        if condition.path is None:
            return False  # No path to resolve -> unresolvable
        left_val = _resolve_path(condition.path, merged_results)
        return _compare(left_val, op_type, condition.literal)

    # Unknown operator type
    logger.warning("[%s] Unknown condition type: %s", _GUARD_NAME, op_type)
    return False


# ------------------------------------------------------------------
# Guard implementation
# ------------------------------------------------------------------


class ConditionalEdgeEvaluator(DAGGuard):
    """Pre-wave guard for conditional edge evaluation (ORCH-16).

    Evaluates PlanStep.condition against merged_results from prior waves.
    Steps whose conditions evaluate FALSE are marked SKIPPED.
    Steps with no condition are always dispatched.

    Stateless -- no constructor dependencies.

    Decision flow per step:
      1. step.condition is None -> no decision (always dispatch)
      2. Evaluate condition tree against merged_results
      3. TRUE  -> CONTINUE (dispatch step)
      4. FALSE -> SKIP (remove from wave dispatch list)
    """

    async def before_wave(
        self,
        wave: Wave,
        ctx: ProcessingContext,
        merged_results: Optional[Dict[str, Any]] = None,
    ) -> List[GuardDecision]:
        """Evaluate conditions for each step in the wave.

        Args:
            wave: Wave about to be dispatched.
            ctx: ProcessingContext for trace correlation.
            merged_results: step_id -> CapabilityResult from prior waves.

        Returns:
            List of GuardDecisions. SKIP decisions for steps to remove.
            Empty list means all steps proceed.
        """
        results = merged_results if merged_results is not None else {}
        decisions: List[GuardDecision] = []

        for step in wave.steps:
            # No condition -> always dispatch (per spec: empty = dispatch)
            if step.condition is None:
                continue

            # Evaluate the condition tree
            passes = evaluate_condition(step.condition, results)

            if passes:
                logger.debug(
                    "[%s] Step '%s' condition TRUE, dispatching",
                    _GUARD_NAME,
                    step.id,
                )
            else:
                logger.info(
                    "[%s] Step '%s' condition FALSE, marking SKIPPED",
                    _GUARD_NAME,
                    step.id,
                )
                decisions.append(
                    GuardDecision(
                        guard_name=_GUARD_NAME,
                        action=GuardAction.SKIP,
                        reason=f"Condition evaluated FALSE for step '{step.id}'",
                        metadata={"step_id": step.id},
                    )
                )

        return decisions

    def __repr__(self) -> str:
        return "ConditionalEdgeEvaluator()"
