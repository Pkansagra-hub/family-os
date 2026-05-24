"""
ToolDispatcher -- 6-step validation and dispatch pipeline
==========================================================

V2 Design Ref: Section 6.0 (tool split), 10.5 (output validation),
               Section 15.3 (tier-based allowlists)

Each actor (Front, Back) gets its own ToolDispatcher instance with:
  - Actor-specific allowlist (enforced at dispatch time)
  - Tier-based budget limits
  - Side-effect blocking (CRISIS tier)
  - JSON Schema argument validation

The 6-step pipeline:
  1. Allowlist check
  2. Budget check
  3. Schema validation
  4. Safety band check (CRISIS blocks side-effects)
  5. Dispatch to tool implementation
  6. Record call in history
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Optional

from k1.bus.ports.bus import IBus
from k1.concierge.config import get_config
from k1.concierge.llm.types import ToolCallResult, ToolSchema
from k1.concierge.tools.implementations import ToolContext, execute_tool
from k1.concierge.tools.result_protocol import ToolResult

# Policy gate signature: returns None to pass through (ALLOW),
# or a fully-formed ToolResult to short-circuit step-0.
# Wired by k1.selfmodel.adapters.concierge_policy_gate.ConciergePolicyGate
# at session bootstrap when ``KernelConfig.enable_self_model`` is True.
PolicyGateFn = Callable[[ToolCallResult], Awaitable[Optional[ToolResult]]]

# Optional bus import for tool lifecycle events
try:
    from k1.concierge.bus.builders import build_tool_completed, build_tool_started
except ImportError:  # pragma: no cover
    build_tool_started = None  # type: ignore[assignment]
    build_tool_completed = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# =========================================================================
# Budget limits per tier (P3.4b: collapsed to canonical {simple, plan, crisis}
# with legacy {LOW, MEDIUM, HIGH, CRISIS} aliases preserved for backward compat).
# Runtime code reads from get_config().tools.budget_limits.
# =========================================================================

_TIER_ALIAS: dict[str, str] = {
    "LOW": "simple",
    "MEDIUM": "plan",
    "HIGH": "plan",
    "CRISIS": "crisis",
    "simple": "simple",
    "plan": "plan",
    "crisis": "crisis",
}

BUDGET_LIMITS: dict[str, int] = {
    "simple": 400,
    "plan": 400,
    "crisis": 400,
    # Legacy aliases:
    "LOW": 400,
    "MEDIUM": 400,
    "HIGH": 400,
    "CRISIS": 400,
}

# =========================================================================
# Front tier allowlists (P3.4b: collapsed to {simple, plan} with legacy aliases)
# =========================================================================

_FRONT_SIMPLE: set[str] = {
    "update_beliefs",
    "update_scoreboard",
    "update_clarifications",
    "update_narrative",
    "refine_affect",
    "recall_memory",
    "summarize_context",
    "dispatch_task",
}

FRONT_TIER_ALLOWLISTS: dict[str, set[str]] = {
    "simple": _FRONT_SIMPLE,
    "plan": _FRONT_SIMPLE | {"promote_belief"},
    "crisis": set(),
    # Legacy aliases:
    "LOW": _FRONT_SIMPLE,
    "MEDIUM": _FRONT_SIMPLE | {"promote_belief"},
    "HIGH": _FRONT_SIMPLE | {"promote_belief"},
    "CRISIS": set(),
}

# P3.4b: BACK_TIER_ALLOWLISTS authoritative copy lives in schemas_back.py.
# The duplicate previously here was dead code (back actor imports from schemas_back).


# =========================================================================
# Schema validation helper
# =========================================================================


def validate_arguments(tool_name: str, arguments: dict, schema: dict) -> list[str]:
    """Validate tool call arguments against JSON Schema.

    Returns list of validation error messages. Empty list = valid.
    Uses jsonschema for Draft-7 validation.
    """
    try:
        import jsonschema

        jsonschema.validate(instance=arguments, schema=schema)
        return []
    except ImportError:
        # jsonschema not installed -- skip validation
        return []
    except Exception as e:
        # jsonschema.ValidationError or SchemaError
        return [str(e).split("\n")[0]]  # First line only


# =========================================================================
# DispatchRecord -- single call history entry
# =========================================================================


@dataclass
class DispatchRecord:
    """Record of a single tool dispatch."""

    tool_name: str
    arguments: dict[str, Any]
    result: ToolResult
    timestamp_ms: int
    iteration: int


def hash_tool_arguments(arguments: dict[str, Any] | None) -> str:
    """Return a stable short hash for tool arguments."""
    text = json.dumps(arguments or {}, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class ToolExecutionRecord:
    """Timing and retry metadata for one tool execution attempt."""

    tool_name: str
    call_id: str
    args_hash: str
    start_time_ms: int
    end_time_ms: int
    duration_ms: int
    timeout_ms: int
    result_status: str
    retryable: bool
    iteration: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "call_id": self.call_id,
            "args_hash": self.args_hash,
            "start_time_ms": self.start_time_ms,
            "end_time_ms": self.end_time_ms,
            "duration_ms": self.duration_ms,
            "timeout_ms": self.timeout_ms,
            "result_status": self.result_status,
            "retryable": self.retryable,
            "iteration": self.iteration,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ToolExecutionRecord":
        return cls(
            tool_name=str(data.get("tool_name", "")),
            call_id=str(data.get("call_id", "")),
            args_hash=str(data.get("args_hash", "")),
            start_time_ms=int(data.get("start_time_ms", 0) or 0),
            end_time_ms=int(data.get("end_time_ms", 0) or 0),
            duration_ms=int(data.get("duration_ms", 0) or 0),
            timeout_ms=int(data.get("timeout_ms", 0) or 0),
            result_status=str(data.get("result_status", "")),
            retryable=bool(data.get("retryable", False)),
            iteration=int(data.get("iteration", 0) or 0),
        )


# =========================================================================
# ToolCallSummary -- lightweight summary for persistence (Phase P)
# =========================================================================

_SENSITIVE_KEY_PATTERN = re.compile(r"password|token|secret|key|api_key", re.IGNORECASE)
_MAX_SUMMARY_CHARS = 200


@dataclass(frozen=True)
class ToolCallSummary:
    """Lightweight summary of a tool dispatch for persistence.

    Designed to survive beyond the ReAct loop lifetime into
    TypedHistoryEntry.metadata["tool_calls"] where Memory Writer
    can read it. All string fields are truncated to 200 chars max.
    Sensitive argument values (password, token, secret, key) are redacted.
    """

    tool_name: str
    arguments_summary: str  # JSON-serialized args, truncated ≤200 chars, redacted
    status: str  # "ok" | "error" | "partial"
    result_preview: str  # stringified result.data or error, truncated ≤200 chars
    timestamp_ms: int
    duration_ms: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "arguments_summary": self.arguments_summary,
            "status": self.status,
            "result_preview": self.result_preview,
            "timestamp_ms": self.timestamp_ms,
            "duration_ms": self.duration_ms,
        }


def _redact_sensitive(args: dict[str, Any]) -> dict[str, Any]:
    """Shallow-redact values whose keys match sensitive patterns."""
    redacted = {}
    for k, v in args.items():
        if _SENSITIVE_KEY_PATTERN.search(k):
            redacted[k] = "***"
        else:
            redacted[k] = v
    return redacted


def _truncate(text: str, max_len: int = _MAX_SUMMARY_CHARS) -> str:
    """Truncate text to max_len characters."""
    if len(text) <= max_len:
        return text
    return text[:max_len]


def _build_summary(record: DispatchRecord) -> ToolCallSummary:
    """Build a ToolCallSummary from a DispatchRecord."""
    # Redact + serialize arguments
    safe_args = _redact_sensitive(record.arguments) if record.arguments else {}
    try:
        args_str = json.dumps(safe_args, default=str, ensure_ascii=False)
    except (TypeError, ValueError):
        args_str = str(safe_args)
    args_summary = _truncate(args_str)

    # Build result preview
    if record.result.is_error():
        preview = record.result.error or "unknown error"
    else:
        try:
            preview = json.dumps(record.result.data, default=str, ensure_ascii=False)
        except (TypeError, ValueError):
            preview = str(record.result.data)
    result_preview = _truncate(preview)

    # Duration: next record timestamp - this record timestamp (approx)
    # We don't have end time, so use 0 as default; caller can improve
    return ToolCallSummary(
        tool_name=record.tool_name,
        arguments_summary=args_summary,
        status=record.result.status,
        result_preview=result_preview,
        timestamp_ms=record.timestamp_ms,
        duration_ms=0,
    )


# =========================================================================
# ToolDispatcher -- the 7-step pipeline
# =========================================================================


class ToolDispatcher:
    """Validates and dispatches tool calls through the 7-step pipeline.

    Each actor (Front, Back) gets its own dispatcher with its own
    allowlist and budget. The dispatcher is created once per ReAct loop
    invocation and tracks call count / history for budget enforcement.

    Args:
        actor: "front" or "back"
        allowlist: Set of allowed tool names for this actor+tier
        tool_schemas: Mapping of tool_name -> ToolSchema (for JSON Schema validation)
        ctx: ToolContext with session manager and service references
        tier: Budget tier ("LOW", "MEDIUM", "HIGH", "CRISIS")
    """

    def __init__(
        self,
        actor: str,
        allowlist: set[str],
        tool_schemas: dict[str, ToolSchema],
        ctx: ToolContext,
        tier: str = "LOW",
        bus: IBus | None = None,
        policy_gate: PolicyGateFn | None = None,
    ):
        self.actor = actor
        self.allowlist = frozenset(allowlist)
        self.tool_schemas = tool_schemas
        self.ctx = ctx
        self.tier = tier
        self._bus = bus
        # Step-0 policy gate (k1.selfmodel.ConciergePolicyGate). When
        # None the dispatcher behaves identically to its pre-M2 baseline.
        self._policy_gate: PolicyGateFn | None = policy_gate
        self.call_count: int = 0
        self.call_history: list[DispatchRecord] = []
        self.execution_history: list[ToolExecutionRecord] = []
        budget_limits = get_config().tools.budget_limits
        canonical_tier = _TIER_ALIAS.get(tier, tier)
        self._budget_limit = budget_limits.get(
            tier,
            budget_limits.get(
                canonical_tier, BUDGET_LIMITS.get(tier, BUDGET_LIMITS.get(canonical_tier, 400))
            ),
        )
        # Per-tool call count remains tracked, but the temporary cap is
        # intentionally lax while live Front/Back tool behavior is tuned.
        self._per_tool_counts: dict[str, int] = {}
        self._per_tool_limits: dict[str, int] = {
            "update_scoreboard": 400,
            "update_beliefs": 400,
            "update_clarifications": 400,
            "update_narrative": 400,
            "refine_affect": 400,
            "promote_belief": 400,
        }
        logger.info(
            "ToolDispatcher initialized (actor=%s, tier=%s, budget=%d, allowlist=%d tools)",
            actor,
            tier,
            self._budget_limit,
            len(allowlist),
        )

    # -----------------------------------------------------------------
    # M5.E3.I3: post-construction policy gate install
    # -----------------------------------------------------------------
    def set_policy_gate(self, policy_gate: PolicyGateFn | None) -> None:
        """Install (or clear) the step-0 policy gate.

        Used by ``KernelService.create_session`` at P3.5 when
        ``KernelConfig.enable_self_model=True`` to wire the
        per-session ``ConciergePolicyGate``. Passing ``None`` reverts
        to the pre-M2 baseline pipeline.
        """
        self._policy_gate = policy_gate

    @property
    def policy_gate(self) -> PolicyGateFn | None:
        """Current step-0 policy gate (``None`` when not wired)."""
        return self._policy_gate

    def _record_execution(
        self,
        *,
        name: str,
        args: dict[str, Any],
        result: ToolResult,
        call_id: str = "",
        start_ms: int | None = None,
        end_ms: int | None = None,
        timeout_ms: int = 0,
        retryable: bool = False,
        consume_budget: bool = False,
    ) -> ToolExecutionRecord:
        """Append execution metadata while preserving legacy history."""
        now_ms = int(time.time() * 1000)
        start = start_ms if start_ms is not None else now_ms
        end = end_ms if end_ms is not None else now_ms
        if consume_budget:
            self.call_count += 1
            self._per_tool_counts[name] = self._per_tool_counts.get(name, 0) + 1
            iteration = self.call_count
        else:
            iteration = len(self.execution_history) + 1
        record = ToolExecutionRecord(
            tool_name=name,
            call_id=call_id,
            args_hash=hash_tool_arguments(args),
            start_time_ms=start,
            end_time_ms=end,
            duration_ms=max(0, end - start),
            timeout_ms=max(0, timeout_ms),
            result_status=result.status,
            retryable=retryable,
            iteration=iteration,
        )
        self.execution_history.append(record)
        self.call_history.append(
            DispatchRecord(
                tool_name=name,
                arguments=args,
                result=result,
                timestamp_ms=end,
                iteration=iteration,
            )
        )
        return record

    def record_timeout(
        self,
        tool_call: ToolCallResult,
        *,
        timeout_ms: int,
    ) -> ToolExecutionRecord:
        """Record a timeout synthesized by react_loop's wait_for wrapper."""
        name = tool_call.name
        result = ToolResult(
            tool_name=name,
            status="error",
            data={"retryable": True, "timeout_ms": timeout_ms},
            error=f"tool_timeout after {timeout_ms / 1000.0:.1f}s",
        )
        now_ms = int(time.time() * 1000)
        return self._record_execution(
            name=name,
            args=tool_call.arguments,
            result=result,
            call_id=getattr(tool_call, "id", "") or "",
            start_ms=max(0, now_ms - timeout_ms),
            end_ms=now_ms,
            timeout_ms=timeout_ms,
            retryable=True,
            consume_budget=True,
        )

    @staticmethod
    def _result_retryable(result: ToolResult) -> bool:
        if not result.is_error():
            return False
        data = result.data if isinstance(result.data, dict) else {}
        if "retryable" in data:
            return bool(data.get("retryable"))
        error = (result.error or "").lower()
        terminal_markers = (
            "not allowed",
            "budget exhausted",
            "invalid arguments",
            "side-effect tools blocked",
            "submit_result(complete) rejected",
            "already called",
            "policy gate",
        )
        if any(marker in error for marker in terminal_markers):
            return False
        return bool(error)

    # -----------------------------------------------------------------
    # The 7-step dispatch pipeline
    # -----------------------------------------------------------------

    async def dispatch(self, tool_call: ToolCallResult) -> ToolResult:
        """Execute the 7-step dispatch pipeline for a single tool call.

        Steps:
          0. Policy gate (k1.selfmodel) -- only when wired; baseline
             behaviour is unchanged when ``policy_gate is None``.
          1. Allowlist check
          2. Budget check
          3. Schema validation
          4. Safety band check (CRISIS blocks side-effects)
          5. Dispatch to implementation (async -- supports async tool fns)
          6. Record in history

        Args:
            tool_call: The ToolCallResult from the LLM response.

        Returns:
            ToolResult with the tool's result or an error.
        """
        name = tool_call.name
        args = tool_call.arguments

        logger.info(
            "dispatch START  actor=%s tool=%s budget_remaining=%d/%d",
            self.actor,
            name,
            self.budget_remaining,
            self._budget_limit,
        )
        logger.debug(
            "dispatch  tool=%s args=%s",
            name,
            str(args)[:200],
        )

        # Step 0: Policy gate (selfmodel). Off by default; when wired,
        # short-circuits with a structured ToolResult on DENY /
        # REQUIRE_IDENTITY / REQUIRE_CONFIRMATION-rejected /
        # DEFER_OFFLINE. ALLOW returns None and we proceed.
        if self._policy_gate is not None:
            try:
                gated = await self._policy_gate(tool_call)
            except Exception:
                logger.exception(
                    "dispatch  policy_gate raised actor=%s tool=%s; failing closed",
                    self.actor,
                    name,
                )
                result = ToolResult(
                    tool_name=name,
                    status="error",
                    error="policy gate error (failing closed)",
                )
                self._record_execution(
                    name=name,
                    args=args,
                    result=result,
                    call_id=getattr(tool_call, "id", "") or "",
                    retryable=False,
                )
                return result
            if gated is not None:
                logger.info(
                    "dispatch BLOCKED (policy_gate)  actor=%s tool=%s status=%s",
                    self.actor,
                    name,
                    gated.status,
                )
                self._record_execution(
                    name=name,
                    args=args,
                    result=gated,
                    call_id=getattr(tool_call, "id", "") or "",
                    retryable=False,
                )
                return gated

        # Step 1: Allowlist check
        if name not in self.allowlist:
            logger.warning(
                "dispatch REJECTED (allowlist)  actor=%s tool=%s tier=%s",
                self.actor,
                name,
                self.tier,
            )
            result = ToolResult(
                tool_name=name,
                status="error",
                error=f"Tool '{name}' not allowed for actor '{self.actor}'",
            )
            self._record_execution(
                name=name,
                args=args,
                result=result,
                call_id=getattr(tool_call, "id", "") or "",
                retryable=False,
            )
            return result

        # Step 2: Budget check
        # submit_result is exempt from budget -- it's the Back actor's
        # termination signal and must always be allowed through so the
        # task can complete gracefully instead of failing with
        # BUDGET_EXHAUSTED.
        if self.call_count >= self._budget_limit and name != "submit_result":
            logger.warning(
                "dispatch REJECTED (budget)  actor=%s tool=%s count=%d limit=%d",
                self.actor,
                name,
                self.call_count,
                self._budget_limit,
            )
            result = ToolResult(
                tool_name=name,
                status="error",
                error="Tool budget exhausted",
            )
            self._record_execution(
                name=name,
                args=args,
                result=result,
                call_id=getattr(tool_call, "id", "") or "",
                retryable=False,
            )
            return result

        # Step 2b: Per-tool call limit (state-mutation tools only).
        # Prevents the model from burning the shared budget on repeated
        # bookkeeping calls (update_scoreboard x4, etc.).
        _per_limit = self._per_tool_limits.get(name)
        if _per_limit is not None:
            _tool_uses = self._per_tool_counts.get(name, 0)
            if _tool_uses >= _per_limit:
                logger.warning(
                    "dispatch REJECTED (per-tool limit)  actor=%s tool=%s uses=%d limit=%d",
                    self.actor,
                    name,
                    _tool_uses,
                    _per_limit,
                )
                result = ToolResult(
                    tool_name=name,
                    status="error",
                    error=f"{name} already called {_tool_uses} times this turn (limit={_per_limit}); stop calling it",
                )
                self._record_execution(
                    name=name,
                    args=args,
                    result=result,
                    call_id=getattr(tool_call, "id", "") or "",
                    retryable=False,
                )
                return result

        # Step 2c: Back-actor guard — reject submit_result(complete) if no
        # invoke_capability / batch_invoke_capabilities has been called yet.
        # Prevents the model from declaring success without doing any work.
        # Only applies when budget is still healthy (>= 2 remaining), so the
        # last-resort submit on a nearly-exhausted budget is still allowed.
        if (
            self.actor == "back"
            and name == "submit_result"
            and args.get("result_type") == "complete"
            and self._per_tool_counts.get("invoke_capability", 0) == 0
            and self._per_tool_counts.get("batch_invoke_capabilities", 0) == 0
            and self._per_tool_counts.get("recall_memory", 0) == 0
            and self._per_tool_counts.get("summarize_context", 0) == 0
            and self.call_count <= self._budget_limit - 2
        ):
            logger.warning(
                "dispatch REJECTED (no-work guard)  actor=back submit_result(complete) "
                "attempted before any invoke_capability call (budget_remaining=%d/%d)",
                self._budget_limit - self.call_count,
                self._budget_limit,
            )
            result = ToolResult(
                tool_name=name,
                status="error",
                error=(
                    "submit_result(complete) rejected: you have not called an authority "
                    "capability or memory/context tool yet. For live system-of-record work, "
                    "you MUST: 1) discover_capabilities(intent, domain), 2) invoke_capability "
                    "or batch_invoke_capabilities with the exact registry-owned name, "
                    "3) THEN submit_result with the actual result. If discovery returned no "
                    "viable capability, use submit_result(result_type='needs_human') instead."
                ),
            )
            self._record_execution(
                name=name,
                args=args,
                result=result,
                call_id=getattr(tool_call, "id", "") or "",
                retryable=False,
            )
            return result

        # Step 3: Schema validation
        schema_obj = self.tool_schemas.get(name)
        if schema_obj and schema_obj.parameters:
            errors = validate_arguments(name, args, schema_obj.parameters)
            if errors:
                logger.warning(
                    "dispatch REJECTED (schema)  tool=%s errors=%s",
                    name,
                    errors,
                )
                result = ToolResult(
                    tool_name=name,
                    status="error",
                    error=f"Invalid arguments: {'; '.join(errors)}",
                )
                self._record_execution(
                    name=name,
                    args=args,
                    result=result,
                    call_id=getattr(tool_call, "id", "") or "",
                    retryable=False,
                )
                return result

        # Step 4: Safety band check (CRISIS blocks side-effect tools)
        if self.tier == "CRISIS" and schema_obj and schema_obj.side_effects:
            logger.warning(
                "dispatch REJECTED (crisis-safety)  tool=%s has side_effects in CRISIS tier",
                name,
            )
            result = ToolResult(
                tool_name=name,
                status="error",
                error="Side-effect tools blocked in CRISIS tier",
            )
            self._record_execution(
                name=name,
                args=args,
                result=result,
                call_id=getattr(tool_call, "id", "") or "",
                retryable=False,
            )
            return result

        # Step 5: Dispatch to implementation (async-aware)
        # Emit tool.started event to bus (for OutputChannel tracking)
        if self._bus and build_tool_started:
            try:
                self._bus.publish(
                    build_tool_started(
                        {"tool_name": name, "actor": self.actor, "args_summary": str(args)[:200]},
                        parent_id=0,
                    )
                )
            except Exception:  # pragma: no cover
                pass  # Never let observability break execution

        start_ms = int(time.time() * 1000)
        try:
            result = await execute_tool(name, args, self.ctx)
        except Exception as exc:
            logger.exception("dispatch  implementation raised actor=%s tool=%s", self.actor, name)
            result = ToolResult(
                tool_name=name,
                status="error",
                data={"retryable": True},
                error=f"tool_exception: {exc}",
            )
        end_ms = int(time.time() * 1000)
        duration_ms = end_ms - start_ms

        # Emit tool.completed event to bus (includes result data for SS panel)
        if self._bus and build_tool_completed:
            try:
                # Include result data so OutputChannel can show what was
                # actually written to session state (beliefs, scoreboard, etc.)
                result_data = {}
                if result.data:
                    result_data = {
                        k: v
                        for k, v in result.data.items()
                        if not isinstance(v, (bytes, bytearray))
                    }
                self._bus.publish(
                    build_tool_completed(
                        {
                            "tool_name": name,
                            "actor": self.actor,
                            "success": result.is_ok(),
                            "duration_ms": duration_ms,
                            "data_keys": list(result.data.keys()) if result.data else [],
                            "result_data": result_data,
                            "args_summary": str(args)[:300],
                        },
                        parent_id=0,
                    )
                )
            except Exception:  # pragma: no cover
                pass

        # Step 6: Record
        self._record_execution(
            name=name,
            args=args,
            result=result,
            call_id=getattr(tool_call, "id", "") or "",
            start_ms=start_ms,
            end_ms=end_ms,
            retryable=self._result_retryable(result),
            consume_budget=True,
        )

        logger.info(
            "dispatch DONE  actor=%s tool=%s status=%s duration_ms=%d budget_remaining=%d",
            self.actor,
            name,
            result.status,
            duration_ms,
            self.budget_remaining,
        )
        if result.is_error():
            logger.warning(
                "dispatch  tool=%s error=%s",
                name,
                result.error,
            )
        else:
            logger.debug(
                "dispatch  tool=%s data_keys=%s",
                name,
                list(result.data.keys()) if result.data else [],
            )

        return result

    # -----------------------------------------------------------------
    # Accessors
    # -----------------------------------------------------------------

    @property
    def budget_remaining(self) -> int:
        """How many tool calls remain in the budget."""
        return max(0, self._budget_limit - self.call_count)

    @property
    def is_budget_exhausted(self) -> bool:
        """True if no budget remains."""
        return self.call_count >= self._budget_limit

    def get_call_history(self) -> list[DispatchRecord]:
        """Return a copy of the call history."""
        return list(self.call_history)

    def reset(self) -> None:
        """Reset the dispatcher for a new turn (same allowlist/tier)."""
        self.call_count = 0
        self.call_history.clear()
        self.execution_history.clear()
        self._per_tool_counts.clear()

    def get_execution_records(self) -> list[ToolExecutionRecord]:
        """Return a copy of detailed execution records."""
        return list(self.execution_history)

    def get_call_summaries(self) -> list[ToolCallSummary]:
        """Build lightweight summaries from call_history for persistence.

        Designed for Phase P (MW prerequisite): extracts tool call data
        before the dispatcher is garbage collected. Summaries are
        truncated (≤200 chars) and sensitive args are redacted.

        Returns:
            List of ToolCallSummary, one per dispatch. Duration is
            estimated from consecutive timestamps.
        """
        summaries: list[ToolCallSummary] = []
        records = self.call_history
        execution_records = getattr(self, "execution_history", [])
        for i, record in enumerate(records):
            summary = _build_summary(record)
            if i < len(execution_records):
                duration = execution_records[i].duration_ms
            elif i + 1 < len(records):
                duration = records[i + 1].timestamp_ms - record.timestamp_ms
            else:
                duration = 0
            # Replace the frozen dataclass's duration_ms
            summary = ToolCallSummary(
                tool_name=summary.tool_name,
                arguments_summary=summary.arguments_summary,
                status=summary.status,
                result_preview=summary.result_preview,
                timestamp_ms=summary.timestamp_ms,
                duration_ms=max(0, duration),
            )
            summaries.append(summary)
        return summaries


# =========================================================================
# Factory functions -- create dispatcher per actor+tier
# =========================================================================


def _build_schema_map(schemas: list[ToolSchema]) -> dict[str, ToolSchema]:
    """Build a name->schema mapping from a list of ToolSchema objects."""
    return {s.name: s for s in schemas}


def create_front_dispatcher(
    tier: str,
    ctx: ToolContext,
    schemas: list[ToolSchema] | None = None,
    bus: IBus | None = None,
) -> ToolDispatcher:
    """Create a Front ToolDispatcher with tier-based allowlist.

    Args:
        tier: "LOW", "MEDIUM", "HIGH", or "CRISIS"
        ctx: ToolContext with session manager and services
        schemas: Optional list of ToolSchema objects for validation.
            If None, imports FRONT_TOOL_SCHEMAS.
        bus: Optional IBus for emitting tool lifecycle events.

    Returns:
        ToolDispatcher configured for Front actor.
    """
    if schemas is None:
        from k1.concierge.tools.schemas_front import FRONT_TOOL_SCHEMAS

        schemas = FRONT_TOOL_SCHEMAS

    allowlist = FRONT_TIER_ALLOWLISTS.get(tier, set())
    schema_map = _build_schema_map(schemas)
    ctx.actor = "front"

    return ToolDispatcher(
        actor="front",
        allowlist=allowlist,
        tool_schemas=schema_map,
        ctx=ctx,
        tier=tier,
        bus=bus,
    )


def create_back_dispatcher(
    tier: str,
    ctx: ToolContext,
    schemas: list[ToolSchema] | None = None,
    bus: IBus | None = None,
) -> ToolDispatcher:
    """Create a Back ToolDispatcher with tier-based allowlist.

    Args:
        tier: "LOW", "MEDIUM", "HIGH"
        ctx: ToolContext with session manager and services
        schemas: Optional list of ToolSchema objects for validation.
            If None, imports BACK_TOOL_SCHEMAS.
        bus: Optional IBus for emitting tool lifecycle events.

    Returns:
        ToolDispatcher configured for Back actor.
    """
    if schemas is None:
        from k1.concierge.tools.schemas_back import BACK_TOOL_SCHEMAS

        schemas = BACK_TOOL_SCHEMAS

    from k1.concierge.tools.schemas_back import BACK_TIER_ALLOWLISTS

    allowlist = BACK_TIER_ALLOWLISTS.get(tier, [])
    schema_map = _build_schema_map(schemas)
    ctx.actor = "back"

    return ToolDispatcher(
        actor="back",
        allowlist=allowlist,
        tool_schemas=schema_map,
        ctx=ctx,
        tier=tier,
        bus=bus,
    )
