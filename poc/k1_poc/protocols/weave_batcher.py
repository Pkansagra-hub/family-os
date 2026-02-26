"""
poc.k1_poc.protocols.weave_batcher -- Batch completed-task results for woven
delivery to the user.

V2 Design Ref: Section 3 (k1.internal.weave.batch.v1 topic)
V2 Design Ref: Section 4 (WEAVING state: pending_results drained after Front)
V2 Design Ref: Section 4 (FSMTurnState: pending_results deque)

Problem:
    If 3 tasks complete within seconds, we do not want 3 separate
    messages to the user.  That is jarring UX.

Solution:
    500 ms batch window.  First result starts the timer.  Subsequent
    results within the window are collected.  Timer fires: flush all
    collected results to Front LLM via a single WEAVE invocation.

    Front receives [ASYNC RESULT ARRIVED] blocks for each result and
    generates ONE response weaving all results together.

Edge cases (V2 Section 4 WEAVING + Section 4.5 pending_results lifecycle):
    1. Single result in window:  normal weave, 1 block.
    2. Result during Front LLM:  queue, weave after current response.
    3. User input during batch:  flush immediately, include results.
    4. 0 results at expiry:      no-op (timer cancelled).
    5. Late arrival after flush:  starts new batch window.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from poc.k1_poc.config import get_config

logger = logging.getLogger(__name__)

# V2 Section 3: k1.internal.weave.batch.v1 delivery config
WEAVE_BATCH_WINDOW_MS: int = 500


@dataclass
class WeaveResult:
    """A completed task result ready for weaving into conversation.

    V2 Design Ref: Section 4 (WEAVING state -- pending_results payload)
    V2 Design Ref: Section 4 (PRESENT mode -- task_artifacts)

    Fields:
        task_id:          Unique task identifier.
        task_description: Human-readable task name.
        result_data:      Structured results from Back.
        completed_at_ns:  Monotonic timestamp of task completion.
    """

    task_id: str
    task_description: str
    result_data: dict[str, Any]
    completed_at_ns: int = field(default_factory=time.monotonic_ns)

    def to_prompt_block(self) -> str:
        """Format as [ASYNC RESULT ARRIVED] prompt injection block.

        V2 Design Ref: Section 4 (WEAVE PromptMode -- prompt assembly)

        Returns:
            Multi-line string block for injection into Front LLM context.
        """
        lines = [
            "[ASYNC RESULT ARRIVED]",
            f"Task: {self.task_description}",
            f"Task ID: {self.task_id}",
            "Result:",
        ]
        for key, value in self.result_data.items():
            lines.append(f"  {key}: {value}")
        lines.append("[END ASYNC RESULT]")
        return "\n".join(lines)

    def to_payload(self) -> dict[str, Any]:
        """Serialize for bus transport."""
        return {
            "task_id": self.task_id,
            "task_description": self.task_description,
            "result_data": self.result_data,
            "completed_at_ns": self.completed_at_ns,
        }

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> WeaveResult:
        """Deserialize from bus payload."""
        return cls(
            task_id=data["task_id"],
            task_description=data["task_description"],
            result_data=data.get("result_data", {}),
            completed_at_ns=data.get("completed_at_ns", 0),
        )


class WeaveBatcher:
    """Batches completed-task results in 500 ms windows.

    V2 Design Ref: Section 3 (k1.internal.weave.batch.v1 STRICT INTERACTIVE)
    V2 Design Ref: Section 4 (WEAVING state -- drain protocol)

    Lifecycle:
        1. task.complete arrives.
        2. If Front is busy (LLM generating), queue result.
        3. If Front idle, add to pending batch.
        4. First pending result starts the 500 ms timer.
        5. Subsequent results within window are collected.
        6. Timer fires: flush all pending -> flush_fn callback.
        7. flush_fn invokes Front LLM with WEAVE mode.

    Thread safety:
        All methods are coroutines running on a single event loop.
        No locks needed.
    """

    __slots__ = (
        "batch_window_ms",
        "_flush_fn",
        "_pending",
        "_timer",
        "_front_busy",
        "_queued",
        "_batch_count",
    )

    def __init__(
        self,
        flush_fn: Callable[[list[WeaveResult]], Awaitable[None]],
        batch_window_ms: int | None = None,
    ) -> None:
        if batch_window_ms is None:
            batch_window_ms = get_config().protocols.weave_batch_window_ms
        self.batch_window_ms = batch_window_ms
        self._flush_fn = flush_fn
        self._pending: list[WeaveResult] = []
        self._timer: asyncio.Task[None] | None = None
        self._front_busy: bool = False
        self._queued: list[WeaveResult] = []
        self._batch_count: int = 0
        logger.info(
            "WeaveBatcher initialised  batch_window_ms=%d",
            batch_window_ms,
        )

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------

    async def on_task_complete(self, result: WeaveResult) -> None:
        """Called when a task completes.

        If Front is busy (LLM generating), queue the result.
        Otherwise, collect into the current batch window.
        """
        if self._front_busy:
            self._queued.append(result)
            logger.info(
                "WeaveBatcher: Front busy, queued result for task %s",
                result.task_id,
            )
            return

        self._pending.append(result)

        if self._timer is None:
            self._timer = asyncio.create_task(self._flush_after_delay())

    async def flush(self) -> list[WeaveResult] | None:
        """Flush pending results to Front LLM.

        Cancels any active timer, collects all pending results,
        and invokes the flush callback.

        Returns:
            The flushed results, or None if nothing to flush.
        """
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

        if not self._pending:
            return None

        results = list(self._pending)
        self._pending.clear()
        self._batch_count += 1

        logger.info(
            "WeaveBatcher: flushing %d results (batch %d)",
            len(results),
            self._batch_count,
        )

        await self._flush_fn(results)
        return results

    async def flush_for_user_input(self) -> list[WeaveResult] | None:
        """Flush immediately because user sent new input.

        V2 edge case: user input during batch window.
        Include pending results in the context for the user message.
        """
        return await self.flush()

    def set_front_busy(self, busy: bool) -> None:
        """Signal whether Front LLM is currently generating.

        When Front finishes and there are queued results,
        they are moved to pending and a new batch window starts.
        """
        self._front_busy = busy
        logger.debug(
            "WeaveBatcher: front_busy=%s queued=%d",
            busy,
            len(self._queued),
        )
        if not busy and self._queued:
            self._pending.extend(self._queued)
            self._queued.clear()
            if self._timer is None and self._pending:
                self._timer = asyncio.create_task(self._flush_after_delay())

    # -----------------------------------------------------------------
    # Properties
    # -----------------------------------------------------------------

    @property
    def pending_count(self) -> int:
        """Number of results in the current batch window."""
        return len(self._pending)

    @property
    def queued_count(self) -> int:
        """Number of results queued while Front was busy."""
        return len(self._queued)

    @property
    def batch_count(self) -> int:
        """Total number of batches flushed."""
        return self._batch_count

    # -----------------------------------------------------------------
    # Internal
    # -----------------------------------------------------------------

    async def _flush_after_delay(self) -> None:
        """Wait for batch window, then flush."""
        await asyncio.sleep(self.batch_window_ms / 1000)
        await self.flush()


# ---------------------------------------------------------------------------
# Weave prompt templates (moved from fsm/weave_batcher.py, Epic 2.3)
# V2 Design Ref: Section 6.7 / 8.10
# ---------------------------------------------------------------------------

WEAVE_PROMPT_TEMPLATE = """\
[ASYNC RESULT ARRIVED]
While you were chatting with the user, a background task completed.
Task: {task_description}
Result: {task_result_summary}
The user's last message was about: {current_thread_summary}

Your job: Respond to the user's current topic first, then naturally transition
to presenting the async result. Do not ignore either context.
Example: "So about [current topic]... and by the way, I also just heard back
about [task] -- here is what I found..."
"""

WEAVE_BATCH_PROMPT_TEMPLATE = """\
[ASYNC RESULTS ARRIVED]
While you were chatting with the user, {count} background task(s) completed.

{results_block}

The user's last message was about: {current_thread_summary}

Your job: Respond to the user's current topic first, then naturally present
ALL results in a single coherent response. Group related results together.
Do not present each result separately.
"""


def _summarize_result(result: Any) -> str:
    """Produce a short summary of a task result dict."""
    if isinstance(result, dict):
        keys = list(result.keys())[:5]
        return f"{{{', '.join(keys)}}}" if keys else "{}"
    return str(result)[:200]


def format_weave_prompt(
    results: list[dict[str, Any]],
    current_thread: str = "general conversation",
) -> str:
    """Build the weave prompt text for the given results.

    Uses the single-result template when count == 1, or the batch template
    when count > 1.

    Args:
        results: List of task result dicts (each has task_id, result, etc.).
        current_thread: Summary of the user's current conversational thread.

    Returns:
        Formatted weave prompt string.
    """
    if not results:
        return ""

    if len(results) == 1:
        r = results[0]
        return WEAVE_PROMPT_TEMPLATE.format(
            task_description=r.get("task_id", "unknown task"),
            task_result_summary=_summarize_result(r.get("result", {})),
            current_thread_summary=current_thread,
        )

    # Multiple results -- batch template
    lines: list[str] = []
    for i, r in enumerate(results, 1):
        lines.append(
            f"  {i}. Task {r.get('task_id', 'unknown')}: "
            f"{_summarize_result(r.get('result', {}))}"
        )
    results_block = "\n".join(lines)
    return WEAVE_BATCH_PROMPT_TEMPLATE.format(
        count=len(results),
        results_block=results_block,
        current_thread_summary=current_thread,
    )
