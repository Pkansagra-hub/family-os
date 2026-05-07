"""
Tool Parallelism Rules -- Which tools can execute concurrently
==============================================================

V2 Design Ref: Section 6.4 (Parallelism)

Rules:
  1. Cognitive tools are parallel-safe among themselves (they write to
     independent SS sections).
  2. Control tools (dispatch_task, submit_result) are ALWAYS_SEQUENTIAL
     -- exactly one call, at the end of the iteration.
  3. Read tools are parallel-safe with anything (they don't mutate).
  4. Action tools (Back-only) are parallel-safe among themselves.

These rules are used by the ToolDispatcher to batch parallel calls.
"""

from __future__ import annotations

# Tools that can execute in parallel (no ordering dependency).
# Each group is a set of tool names that can be batched.
PARALLEL_SAFE_GROUPS: dict[str, frozenset[str]] = {
    "cognitive": frozenset(
        {
            "update_beliefs",
            "update_scoreboard",
            "update_clarifications",
            "update_narrative",
            "refine_affect",
            "promote_belief",
        }
    ),
    "read": frozenset(
        {
            "recall_memory",
            "summarize_context",
            "discover_capabilities",
        }
    ),
    "action": frozenset(
        {
            "invoke_capability",
            "spawn_via_fabric",
            "execute_workflow",
        }
    ),
}

# Tools that must execute alone (not batched with others).
ALWAYS_SEQUENTIAL: frozenset[str] = frozenset(
    {
        "dispatch_task",  # Must be last (Front)
        "submit_result",  # Must be last (Back)
    }
)


def can_parallelize(tool_a: str, tool_b: str) -> bool:
    """Return True if two tools can safely execute in parallel.

    Both tools must be in the same PARALLEL_SAFE_GROUP,
    and neither can be in ALWAYS_SEQUENTIAL.
    """
    if tool_a in ALWAYS_SEQUENTIAL or tool_b in ALWAYS_SEQUENTIAL:
        return False

    for group in PARALLEL_SAFE_GROUPS.values():
        if tool_a in group and tool_b in group:
            return True

    # Cross-group parallelism: read + cognitive is safe
    read_group = PARALLEL_SAFE_GROUPS["read"]
    cognitive_group = PARALLEL_SAFE_GROUPS["cognitive"]
    if (tool_a in read_group and tool_b in cognitive_group) or (
        tool_a in cognitive_group and tool_b in read_group
    ):
        return True

    # Cross-group parallelism: read + action is safe
    action_group = PARALLEL_SAFE_GROUPS["action"]
    if (tool_a in read_group and tool_b in action_group) or (
        tool_a in action_group and tool_b in read_group
    ):
        return True

    return False


def partition_calls(tool_names: list[str]) -> list[list[str]]:
    """Partition a list of tool calls into sequential batches.

    Returns a list of batches. Tools within a batch can be called in
    parallel. Batches must be executed sequentially.

    Sequential tools always get their own single-element batch.
    """
    sequential: list[str] = []
    parallelizable: list[str] = []

    for name in tool_names:
        if name in ALWAYS_SEQUENTIAL:
            sequential.append(name)
        else:
            parallelizable.append(name)

    batches: list[list[str]] = []

    # Parallelizable tools form one batch
    if parallelizable:
        batches.append(parallelizable)

    # Remaining sequential tools (dispatch_task, submit_result) go LAST
    for name in sequential:
        batches.append([name])

    return batches
