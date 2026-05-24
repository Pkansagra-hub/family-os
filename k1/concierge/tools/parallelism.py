"""Compatibility wrapper for live Concierge parallel-safety policy.

The ReAct loop uses :mod:`k1.concierge.task.parallel_safety` directly.
This module keeps the older tools.parallelism exports alive while
delegating every decision to that single source of truth.
"""

from __future__ import annotations

from k1.concierge.task.parallel_safety import (
    ALWAYS_SEQUENTIAL,
    PARALLEL_SAFE_GROUPS,
    classify_tool_batch,
    is_parallel_safe,
)


def can_parallelize(tool_a: str, tool_b: str) -> bool:
    """Return True when both tools are parallel-safe under live policy."""
    parallel, sequential = classify_tool_batch([tool_a, tool_b])
    return len(parallel) == 2 and not sequential


def partition_calls(tool_names: list[str]) -> list[list[str]]:
    """Partition calls into one parallel batch followed by sequential calls."""
    parallel, sequential = classify_tool_batch(tool_names)
    batches: list[list[str]] = []
    if parallel:
        batches.append(parallel)
    batches.extend([name] for name in sequential)
    return batches


__all__ = [
    "ALWAYS_SEQUENTIAL",
    "PARALLEL_SAFE_GROUPS",
    "can_parallelize",
    "is_parallel_safe",
    "partition_calls",
]
