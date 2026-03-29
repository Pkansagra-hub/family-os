"""
poc.k1_poc.task.bundled_executor -- Bundled intent execution plan for Back ReAct loop.

V2 Design Ref: Section 8.4 (Bundled Intents)

When a TaskDispatch contains multiple intents (bundled), Back executes
them sequentially in its ReAct loop:
    Iteration 1: invoke_capability for intent #0
    Iteration 2: invoke_capability for intent #1
    ...
    Final iteration: submit_result with combined results from all intents

The BundledExecutionPlan tracks which intents have been executed,
collects per-intent results, and produces the combined result dict
for submit_result(complete).

Design ref: Section 8.4 -- "Back executes each [intent] sequentially
in its ReAct loop, observing results between invocations."

Single-intent dispatches also use BundledExecutionPlan (it degenerates
to one step). This avoids special-casing in the Back handler.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from poc.k1_poc.task.intent import TaskIntent


@dataclass
class IntentResult:
    """Result of executing a single intent within a bundle.

    Attributes:
        intent_index:    Position of this intent in the dispatch's intents list.
        action:          The action string from the intent (for observability).
        status:          "success" or "error".
        data:            Structured result data from invoke_capability.
        error:           Error detail string (only set when status="error").
        tool_calls_used: Number of invoke_capability calls consumed.
    """

    intent_index: int
    action: str
    status: str = "success"
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    tool_calls_used: int = 0

    def __post_init__(self) -> None:
        if self.status not in ("success", "error"):
            raise ValueError(
                f"IntentResult.status must be 'success' or 'error', got '{self.status}'"
            )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for combined_result output."""
        d: dict[str, Any] = {
            "action": self.action,
            "status": self.status,
            "data": self.data,
        }
        if self.error is not None:
            d["error"] = self.error
        return d


@dataclass
class BundledExecutionPlan:
    """Execution plan for a bundled (or single) dispatch.

    The Back ReAct loop uses this to track which intents have been
    executed and collect per-intent results.  When all intents are
    done, the plan produces the combined result for submit_result.

    Usage:
        plan = BundledExecutionPlan(intents=dispatch.intents)
        while not plan.is_complete:
            intent = plan.current_intent
            # ... execute intent via invoke_capability ...
            plan.record_result(IntentResult(
                intent_index=plan.current_index,
                action=intent.action,
                data={...},
                tool_calls_used=N,
            ))
        combined = plan.combined_result()

    Attributes:
        intents:        The intents to execute (from TaskDispatch.intents).
        results:        Per-intent results collected so far.
        _current_index: Index of the next intent to execute.
    """

    intents: list[TaskIntent]
    results: list[IntentResult] = field(default_factory=list)
    _current_index: int = field(default=0, repr=False)

    @property
    def current_intent(self) -> TaskIntent | None:
        """The next intent to execute, or None if all done."""
        if self._current_index >= len(self.intents):
            return None
        return self.intents[self._current_index]

    @property
    def current_index(self) -> int:
        """Index of the next intent to execute."""
        return self._current_index

    @property
    def is_complete(self) -> bool:
        """True when all intents have been executed."""
        return self._current_index >= len(self.intents)

    @property
    def total_intents(self) -> int:
        """Total number of intents in the plan."""
        return len(self.intents)

    @property
    def completed_intents(self) -> int:
        """Number of intents that have been executed."""
        return len(self.results)

    @property
    def total_tool_calls(self) -> int:
        """Sum of tool calls across all executed intents."""
        return sum(r.tool_calls_used for r in self.results)

    @property
    def all_success(self) -> bool:
        """True if all executed intents succeeded."""
        return all(r.status == "success" for r in self.results)

    @property
    def has_errors(self) -> bool:
        """True if any executed intent failed."""
        return any(r.status == "error" for r in self.results)

    def record_result(self, result: IntentResult) -> None:
        """Record the result of the current intent and advance.

        Args:
            result: The IntentResult for the current intent.

        Raises:
            ValueError: If result.intent_index doesn't match current_index.
            RuntimeError: If plan is already complete.
        """
        if self.is_complete:
            raise RuntimeError(
                f"BundledExecutionPlan is complete ({len(self.intents)} intents), "
                f"cannot record more results"
            )
        if result.intent_index != self._current_index:
            raise ValueError(
                f"Expected result for intent {self._current_index}, " f"got {result.intent_index}"
            )
        self.results.append(result)
        self._current_index += 1

    def combined_result(self) -> dict[str, Any]:
        """Produce the combined result dict for submit_result.

        Can be called at any point (even before all intents complete)
        but typically called after is_complete is True.

        Returns:
            {
                "intent_results": [
                    {"action": "book hotel", "status": "success", "data": {...}},
                    {"action": "search restaurants", "status": "success", "data": {...}},
                ],
                "all_success": True/False,
                "total_tool_calls": N,
                "completed_intents": M,
                "total_intents": K,
            }
        """
        return {
            "intent_results": [r.to_dict() for r in self.results],
            "all_success": self.all_success,
            "total_tool_calls": self.total_tool_calls,
            "completed_intents": self.completed_intents,
            "total_intents": self.total_intents,
        }

    def results_as_list(self) -> list[dict[str, Any]]:
        """Return results as a list of dicts for TaskComplete.results.

        Each intent's data dict becomes one entry in the results list.
        This format matches TaskComplete.results for downstream
        $ref resolution in chained tasks.
        """
        return [r.data for r in self.results if r.status == "success"]
