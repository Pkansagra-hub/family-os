"""
k1.concierge.task.parallel_safety -- Tool parallelism classification for ReAct loop.

V2 Design Ref: Section 7.8 (Parallel vs Sequential Tool Calling)

The POC react_loop() executes non-terminal tool calls in parallel via
asyncio.gather (see react/loop.py).  This module provides safety
classification so that side-effect tools are forced to run sequentially
while reads and cognitive writes can safely run concurrently.

Integration (M3 E3.4.2): react_loop calls classify_tool_batch() before
execution.  Parallel-safe tools run via asyncio.gather; sequential tools
run one at a time in order.  A config toggle (react.parallel_tools_enabled)
can force all tools to run sequentially for debugging.

Classification table (V2 Section 7.8):

    Parallel-safe reads:      recall_memory, summarize_context, discover_capabilities
    Parallel-safe cog writes: update_beliefs, update_scoreboard, update_clarifications,
                              update_narrative, refine_affect
    Always sequential:        promote_belief (dep on recall),
                              dispatch_task (dep on cognitive state),
                                  invoke_capability unless a contract/read prefix proves read-only,
                              spawn_via_fabric (side effects),
                              execute_workflow (side effects),
                              submit_result (terminal)

Production batching strategy (V2 Section 7.8):
    Phase 1: parallel reads  (asyncio.gather)
    Phase 2: parallel cognitive writes (asyncio.gather)
    Phase 3: sequential tools one at a time
"""

from __future__ import annotations

from typing import Any

# =========================================================================
# Parallel-safe tool groups (V2 Section 7.8)
# =========================================================================

PARALLEL_SAFE_GROUPS: dict[str, set[str]] = {
    "reads": {"recall_memory", "summarize_context", "discover_capabilities"},
    "cognitive_writes": {
        "update_beliefs",
        "update_scoreboard",
        "update_clarifications",
        "update_narrative",
        "refine_affect",
    },
}

# =========================================================================
# Always-sequential tools (V2 Section 7.8)
# =========================================================================

ALWAYS_SEQUENTIAL: set[str] = {
    "promote_belief",  # Depends on recall_memory observation
    "dispatch_task",  # Depends on cognitive state being up-to-date
    "invoke_capability",  # Side effects -- must observe before next call
    "batch_invoke_capabilities",  # Internally classifies/batches capability requests
    "spawn_via_fabric",  # Side effects -- creates agents
    "execute_workflow",  # Side effects -- orchestrates multi-step
    "submit_result",  # Terminal -- ends the loop
}


def is_parallel_safe(tool_name: str) -> bool:
    """Check if a tool can safely run in parallel with others.

    A tool is parallel-safe if it belongs to any group in
    PARALLEL_SAFE_GROUPS.  Unknown tools default to sequential
    (fail-safe: assume side effects until proven otherwise).

    Args:
        tool_name: Name of the tool to classify.

    Returns:
        True if the tool appears in any parallel-safe group.
    """
    for group in PARALLEL_SAFE_GROUPS.values():
        if tool_name in group:
            return True
    return False


def classify_tool_batch(
    tool_names: list[str],
) -> tuple[list[str], list[str]]:
    """Split a batch of tool calls into parallel-safe and sequential groups.

    When the LLM returns multiple tool calls in one response, this
    function classifies each tool and separates them for execution
    planning.

    Unknown tools (not in PARALLEL_SAFE_GROUPS or ALWAYS_SEQUENTIAL)
    are treated as sequential (fail-safe).

    Args:
        tool_names: List of tool names from an LLM response.

    Returns:
        Tuple of (parallel_safe, sequential) tool name lists.
        Order within each list matches input order.
    """
    parallel: list[str] = []
    sequential: list[str] = []
    for name in tool_names:
        if is_parallel_safe(name):
            parallel.append(name)
        else:
            sequential.append(name)
    return parallel, sequential


def capability_invocation_is_parallel_safe(
    args: dict[str, Any] | None,
    contract_metadata: dict[str, Any] | None = None,
) -> bool:
    """Return True when an invoke_capability call is proven read-only.

    The default for invoke_capability remains sequential.  It becomes
    parallel-safe only when the registry name or discovered contract
    metadata proves there are no side effects and no human confirmation.
    """
    call_args = args or {}
    capability_name = str(call_args.get("capability_name") or "")
    metadata = contract_metadata or {}
    if bool(metadata.get("requires_human_confirmation")):
        return False
    side_effects = metadata.get("side_effects")
    if isinstance(side_effects, list) and side_effects:
        return False
    if bool(metadata.get("has_side_effects")):
        return False
    capabilities = metadata.get("capabilities")
    if not isinstance(capabilities, list):
        schema = metadata.get("schema") if isinstance(metadata.get("schema"), dict) else {}
        capabilities = schema.get("capabilities") if isinstance(schema, dict) else []
    normalized = {str(item).lower() for item in capabilities or []}
    if normalized.intersection({"write", "mutate", "delete", "side_effect"}):
        return False
    if capability_name.startswith("tool.read."):
        return True
    return "read" in normalized and not ({"write", "mutate", "side_effect"} & normalized)


def classify_tool_calls(
    tool_calls: list[tuple[str, dict[str, Any]]],
    capability_metadata: dict[str, dict[str, Any]] | None = None,
) -> tuple[list[int], list[int]]:
    """Classify concrete tool calls by index.

    Name-only classification cannot distinguish a read-only
    invoke_capability call from a side-effecting one.  This helper keeps
    the old fail-closed policy while allowing contract-proven read calls
    to execute in parallel.
    """
    metadata_by_name = capability_metadata or {}
    parallel: list[int] = []
    sequential: list[int] = []
    for index, (name, args) in enumerate(tool_calls):
        if is_parallel_safe(name):
            parallel.append(index)
            continue
        if name == "invoke_capability":
            capability_name = str((args or {}).get("capability_name") or "")
            if capability_invocation_is_parallel_safe(
                args,
                metadata_by_name.get(capability_name),
            ):
                parallel.append(index)
                continue
        sequential.append(index)
    return parallel, sequential
