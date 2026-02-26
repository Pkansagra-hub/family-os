"""
poc.k1_poc.task.parallel_safety -- Tool parallelism classification for ReAct loop.

V2 Design Ref: Section 7.8 (Parallel vs Sequential Tool Calling)

The POC react_loop() executes non-terminal tools in parallel via
asyncio.gather (see react/loop.py:508).  This module defines the safety
classification constants for production-grade parallel batching where
side-effect tools must be sequenced while reads and cognitive writes
can run concurrently.

Classification table (V2 Section 7.8):

    Parallel-safe reads:      recall_memory, summarize_context, discover_capabilities
    Parallel-safe cog writes: update_beliefs, update_scoreboard, update_clarifications,
                              update_narrative, refine_affect
    Always sequential:        promote_belief (dep on recall),
                              dispatch_task (dep on cognitive state),
                              invoke_capability (side effects),
                              spawn_via_fabric (side effects),
                              execute_workflow (side effects),
                              submit_result (terminal)

Production batching strategy (V2 Section 7.8):
    Phase 1: parallel reads  (asyncio.gather)
    Phase 2: parallel cognitive writes (asyncio.gather)
    Phase 3: sequential tools one at a time
"""

from __future__ import annotations

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
