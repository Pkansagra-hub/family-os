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

import logging
import time
from dataclasses import dataclass
from typing import Any

from poc.k1_poc.config import get_config
from poc.k1_poc.llm.types import ToolCallResult, ToolSchema
from poc.k1_poc.tools.implementations import ToolContext, execute_tool
from poc.k1_poc.tools.result_protocol import ToolResult

# Optional bus import for tool lifecycle events
try:
    from poc.k1_poc.bus.builders import build_tool_completed, build_tool_started
except ImportError:  # pragma: no cover
    build_tool_started = None  # type: ignore[assignment]
    build_tool_completed = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# =========================================================================
# Budget limits per tier
# Kept as module-level constant for backward compatibility.
# Runtime code reads from get_config().tools.budget_limits.
# =========================================================================

BUDGET_LIMITS: dict[str, int] = {
    "LOW": 5,
    "MEDIUM": 10,
    "HIGH": 20,
    "CRISIS": 3,
}

# =========================================================================
# Front tier allowlists (V2 Section 15.3)
# =========================================================================

FRONT_TIER_ALLOWLISTS: dict[str, set[str]] = {
    "LOW": {
        "update_beliefs",
        "update_scoreboard",
        "update_clarifications",
        "update_narrative",
        "refine_affect",
        "recall_memory",
        "summarize_context",
        "dispatch_task",
    },
    "MEDIUM": {
        "update_beliefs",
        "update_scoreboard",
        "update_clarifications",
        "update_narrative",
        "refine_affect",
        "promote_belief",
        "recall_memory",
        "summarize_context",
        "dispatch_task",
    },
    "HIGH": {
        "update_beliefs",
        "update_scoreboard",
        "update_clarifications",
        "update_narrative",
        "refine_affect",
        "promote_belief",
        "recall_memory",
        "summarize_context",
        "dispatch_task",
    },
    "CRISIS": set(),  # Front doesn't run ReAct in CRISIS
}

# Back tier allowlists (imported from schemas_back.py at factory level)
BACK_TIER_ALLOWLISTS: dict[str, set[str]] = {
    "LOW": {"recall_memory", "discover_capabilities", "invoke_capability", "submit_result"},
    "MEDIUM": {
        "recall_memory",
        "discover_capabilities",
        "invoke_capability",
        "spawn_via_fabric",
        "execute_workflow",
        "submit_result",
    },
    "HIGH": {
        "recall_memory",
        "discover_capabilities",
        "invoke_capability",
        "spawn_via_fabric",
        "execute_workflow",
        "submit_result",
    },
}


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
        bus: Any | None = None,
    ):
        self.actor = actor
        self.allowlist = frozenset(allowlist)
        self.tool_schemas = tool_schemas
        self.ctx = ctx
        self.tier = tier
        self._bus = bus
        self.call_count: int = 0
        self.call_history: list[DispatchRecord] = []
        self._budget_limit = get_config().tools.budget_limits.get(tier, 5)
        logger.info(
            "ToolDispatcher initialized (actor=%s, tier=%s, budget=%d, allowlist=%d tools)",
            actor,
            tier,
            self._budget_limit,
            len(allowlist),
        )

    # -----------------------------------------------------------------
    # The 7-step dispatch pipeline
    # -----------------------------------------------------------------

    async def dispatch(self, tool_call: ToolCallResult) -> ToolResult:
        """Execute the 7-step dispatch pipeline for a single tool call.

        Steps:
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

        # Step 1: Allowlist check
        if name not in self.allowlist:
            logger.warning(
                "dispatch REJECTED (allowlist)  actor=%s tool=%s tier=%s",
                self.actor,
                name,
                self.tier,
            )
            return ToolResult(
                tool_name=name,
                status="error",
                error=f"Tool '{name}' not allowed for actor '{self.actor}'",
            )

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
            return ToolResult(
                tool_name=name,
                status="error",
                error="Tool budget exhausted",
            )

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
                return ToolResult(
                    tool_name=name,
                    status="error",
                    error=f"Invalid arguments: {'; '.join(errors)}",
                )

        # Step 4: Safety band check (CRISIS blocks side-effect tools)
        if self.tier == "CRISIS" and schema_obj and schema_obj.side_effects:
            logger.warning(
                "dispatch REJECTED (crisis-safety)  tool=%s has side_effects in CRISIS tier",
                name,
            )
            return ToolResult(
                tool_name=name,
                status="error",
                error="Side-effect tools blocked in CRISIS tier",
            )

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
        result = await execute_tool(name, args, self.ctx)
        duration_ms = int(time.time() * 1000) - start_ms

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
        self.call_count += 1
        self.call_history.append(
            DispatchRecord(
                tool_name=name,
                arguments=args,
                result=result,
                timestamp_ms=int(time.time() * 1000),
                iteration=self.call_count,
            )
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
    bus: Any | None = None,
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
        from poc.k1_poc.tools.schemas_front import FRONT_TOOL_SCHEMAS

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
    bus: Any | None = None,
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
        from poc.k1_poc.tools.schemas_back import BACK_TOOL_SCHEMAS

        schemas = BACK_TOOL_SCHEMAS

    allowlist = BACK_TIER_ALLOWLISTS.get(tier, set())
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
