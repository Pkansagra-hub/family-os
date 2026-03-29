"""Tool Registry -- Epic 2.6 (REG-001).

Central registry that maps tool names to handler functions and carries the
metadata the LLM needs to decide **when** to use each tool and **what** to
pass.  The registry is the single source of truth for:

    1. Tool availability per tier (LOW / MEDIUM)
    2. LLM function-calling declarations (Gemini-compatible JSON schemas)
    3. Tool handler dispatch at runtime

The 14 tools are registered via ``build_default_registry()`` which wires
each handler from the signal, cognitive, read, action, and schema modules.

Architecture note
-----------------
``get_llm_declarations(tier)`` is called by the system prompt builder before
every LLM call.  The returned list is tier-filtered so the model NEVER sees
tools it is forbidden from calling at the current tier.  This is the
enforcement mechanism for the tier allowlist in the concierge spec.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    """Immutable descriptor for a registered tool.

    Attributes
    ----------
    name:
        Stable identifier used in LLM function-calling (e.g. ``"acknowledge"``).
    category:
        Logical group.  Determines cognitive-write vs read vs effectful action.
    handler:
        The callable that executes this tool.  May be a plain function or a
        bound method on ``CognitiveToolSet``.
    schema:
        Gemini-compatible JSON schema dict (``name``, ``description``,
        ``parameters``).  This is the EXACT dict sent to the model -- its
        ``description`` field is what the model reads to decide when to
        call this tool, so it must be precise and actionable.
    tiers:
        Set of tiers that MAY invoke this tool (``{"LOW", "MEDIUM"}``).
    """

    name: str
    category: Literal["signal", "cognitive", "read", "action", "meta"]
    handler: Callable[..., Any]
    schema: dict[str, Any]
    tiers: frozenset[str] = field(default_factory=lambda: frozenset({"LOW", "MEDIUM"}))


class ToolNotFoundError(KeyError):
    """Raised when a tool name is not in the registry."""

    def __init__(self, name: str, available: list[str]) -> None:
        self.name = name
        self.available = available
        super().__init__(f"Tool '{name}' not found. Available: {', '.join(sorted(available))}")


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class ToolRegistry:
    """Central 14-tool registry with category + tier filtering.

    Usage
    -----
    ::

        registry = build_default_registry(cognitive_toolset, session_manager)
        declarations = registry.get_llm_declarations("LOW")  # 9 tools
        handler = registry.get("acknowledge").handler
    """

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    # -- Mutation ----------------------------------------------------------

    def register(self, tool_def: ToolDefinition) -> None:
        """Add (or replace) a tool definition."""
        self._tools[tool_def.name] = tool_def

    # -- Lookup ------------------------------------------------------------

    def get(self, name: str) -> ToolDefinition:
        """Return the ``ToolDefinition`` for *name*, or raise ``ToolNotFoundError``."""
        try:
            return self._tools[name]
        except KeyError:
            raise ToolNotFoundError(name, list(self._tools.keys())) from None

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def __len__(self) -> int:
        return len(self._tools)

    # -- Tier-filtered queries ---------------------------------------------

    def get_for_tier(self, tier: str) -> list[ToolDefinition]:
        """Return all tools allowed at *tier*, sorted by name."""
        upper = tier.upper()
        return sorted(
            (td for td in self._tools.values() if upper in td.tiers),
            key=lambda td: td.name,
        )

    def get_llm_declarations(self, tier: str) -> list[dict[str, Any]]:
        """Return Gemini-compatible function-calling declarations for *tier*.

        Each dict has ``name``, ``description``, ``parameters`` -- exactly
        the shape Gemini ``tools=[{"function_declarations": [...]}]`` expects.
        Tier-filtered so the model never sees tools it cannot call.
        """
        return [td.schema for td in self.get_for_tier(tier)]

    def get_by_category(self, category: str) -> list[ToolDefinition]:
        """Return all tools in *category*, sorted by name."""
        return sorted(
            (td for td in self._tools.values() if td.category == category),
            key=lambda td: td.name,
        )

    @property
    def all_tool_names(self) -> list[str]:
        """Sorted list of every registered tool name."""
        return sorted(self._tools.keys())


# ---------------------------------------------------------------------------
# Factory: build the default 14-tool registry
# ---------------------------------------------------------------------------

# Tier sets used below
_LOW_MEDIUM = frozenset({"LOW", "MEDIUM"})
_MEDIUM_ONLY = frozenset({"MEDIUM"})


def build_default_registry(
    cognitive: Any,  # CognitiveToolSet
    manager: Any,  # SessionStateManager
) -> ToolRegistry:
    """Wire all 14 PoC tools into a freshly-created ``ToolRegistry``.

    Parameters
    ----------
    cognitive:
        ``CognitiveToolSet`` instance (its bound methods are the cognitive handlers).
    manager:
        ``SessionStateManager`` instance (needed by read tools that take ``manager``).

    Returns
    -------
    A fully populated ``ToolRegistry`` with 14 tools.
    """
    # Local imports to avoid circular dependency at module level
    from .action_mock import ACTION_SCHEMAS, execute_workflow, invoke_capability, spawn_via_fabric
    from .cognitive import COGNITIVE_SCHEMAS
    from .read_mock import (
        READ_SCHEMAS,
        discover_capabilities,
        read_session_state,
        recall_memory,
        summarize_context,
    )
    from .schema import SCHEMA_SCHEMAS, get_capability_schema

    registry = ToolRegistry()

    # -- Helper to find a schema by name from a list ----------------------
    def _schema(name: str, schemas: list[dict[str, Any]]) -> dict[str, Any]:
        for s in schemas:
            if s["name"] == name:
                return s
        raise ValueError(f"Schema '{name}' not found in list")  # pragma: no cover

    # =====================================================================
    # 1. SIGNAL  (0 tools -- acknowledge hidden from LLM)
    # =====================================================================
    # acknowledge() code kept in signal.py but NOT registered here.
    # This prevents the LLM from seeing or calling it, saving 1 tool
    # call per turn.  See Epic 1.1 in concierge_phase10_plan.md.

    # =====================================================================
    # 2. COGNITIVE  (6 tools) -- all LOW + MEDIUM except promote_belief
    # =====================================================================
    registry.register(
        ToolDefinition(
            name="update_scoreboard",
            category="cognitive",
            handler=cognitive.update_scoreboard,
            schema=_schema("update_scoreboard", COGNITIVE_SCHEMAS),
            tiers=_LOW_MEDIUM,
        )
    )
    registry.register(
        ToolDefinition(
            name="update_beliefs",
            category="cognitive",
            handler=cognitive.update_beliefs,
            schema=_schema("update_beliefs", COGNITIVE_SCHEMAS),
            tiers=_LOW_MEDIUM,
        )
    )
    registry.register(
        ToolDefinition(
            name="update_clarifications",
            category="cognitive",
            handler=cognitive.update_clarifications,
            schema=_schema("update_clarifications", COGNITIVE_SCHEMAS),
            tiers=_LOW_MEDIUM,
        )
    )
    registry.register(
        ToolDefinition(
            name="update_narrative",
            category="cognitive",
            handler=cognitive.update_narrative,
            schema=_schema("update_narrative", COGNITIVE_SCHEMAS),
            tiers=_LOW_MEDIUM,
        )
    )
    registry.register(
        ToolDefinition(
            name="refine_affect",
            category="cognitive",
            handler=cognitive.refine_affect,
            schema=_schema("refine_affect", COGNITIVE_SCHEMAS),
            tiers=_LOW_MEDIUM,
        )
    )
    registry.register(
        ToolDefinition(
            name="promote_belief",
            category="cognitive",
            handler=cognitive.promote_belief,
            schema=_schema("promote_belief", COGNITIVE_SCHEMAS),
            tiers=_MEDIUM_ONLY,
        )
    )

    # =====================================================================
    # 3. READ  (4 tools) -- mixed tiers
    # =====================================================================
    # recall_memory: available at both tiers (family knowledge is always needed)
    registry.register(
        ToolDefinition(
            name="recall_memory",
            category="read",
            handler=recall_memory,
            schema=_schema("recall_memory", READ_SCHEMAS),
            tiers=_LOW_MEDIUM,
        )
    )
    # discover_capabilities: MEDIUM only (LOW tasks are simple, don't need discovery)
    registry.register(
        ToolDefinition(
            name="discover_capabilities",
            category="read",
            handler=discover_capabilities,
            schema=_schema("discover_capabilities", READ_SCHEMAS),
            tiers=_MEDIUM_ONLY,
        )
    )
    # summarize_context: both tiers (always useful for context compression)
    registry.register(
        ToolDefinition(
            name="summarize_context",
            category="read",
            handler=lambda **kw: summarize_context(manager, **kw),
            schema=_schema("summarize_context", READ_SCHEMAS),
            tiers=_LOW_MEDIUM,
        )
    )
    # read_session_state: both tiers (primary read mechanism for SessionState)
    registry.register(
        ToolDefinition(
            name="read_session_state",
            category="read",
            handler=lambda **kw: read_session_state(manager, **kw),
            schema=_schema("read_session_state", READ_SCHEMAS),
            tiers=_LOW_MEDIUM,
        )
    )

    # =====================================================================
    # 4. ACTION  (3 tools) -- mixed tiers
    # =====================================================================
    # invoke_capability: both tiers (weather lookup is LOW, others are MEDIUM)
    registry.register(
        ToolDefinition(
            name="invoke_capability",
            category="action",
            handler=invoke_capability,
            schema=_schema("invoke_capability", ACTION_SCHEMAS),
            tiers=_LOW_MEDIUM,
        )
    )
    # spawn_via_fabric: MEDIUM only (agent registration is complex)
    registry.register(
        ToolDefinition(
            name="spawn_via_fabric",
            category="action",
            handler=spawn_via_fabric,
            schema=_schema("spawn_via_fabric", ACTION_SCHEMAS),
            tiers=_MEDIUM_ONLY,
        )
    )
    # execute_workflow: MEDIUM only (multi-step workflows are complex)
    registry.register(
        ToolDefinition(
            name="execute_workflow",
            category="action",
            handler=execute_workflow,
            schema=_schema("execute_workflow", ACTION_SCHEMAS),
            tiers=_MEDIUM_ONLY,
        )
    )

    # =====================================================================
    # 5. META  (1 tool) -- MEDIUM only
    # =====================================================================
    registry.register(
        ToolDefinition(
            name="get_capability_schema",
            category="meta",
            handler=get_capability_schema,
            schema=_schema("get_capability_schema", SCHEMA_SCHEMAS),
            tiers=_MEDIUM_ONLY,
        )
    )

    return registry
