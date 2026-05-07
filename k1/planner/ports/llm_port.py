"""ILLMPort -- Planner LLM inference protocol [F13].

The LLM port is the Planner's sole exit point for all language model calls.
Three pipeline stages (SKETCH, EXPAND, VALIDATE) and two HIL prompt
generators route through this port.

Design decisions (SS15.3)
-------------------------
- Single method: ``execute(HubRequest) -> HubResponse``.
- Routes through LLM Request Bus to Model Hub (production adapter).
- Every ``HubRequest`` carries explicit ``constraints`` (PLAN-11 enforcement).
- The Planner does NOT select models -- Model Hub's ModelSelector chooses.
- CommitService has NO access to this port (PLAN-03 enforcement).

LLM call types (SS13.1)
------------------------
- LLM-1: SKETCH main (STRUCTURED, 2000 tokens, 8000ms)
- LLM-2: EXPAND main (STRUCTURED, 1000 tokens, 5000ms)
- LLM-3: VALIDATE arbiter (STRUCTURED, 500 tokens, 3000ms)
- LLM-C1: HIL clarification (CHAT, 300 tokens, 3000ms)
- LLM-A1: HIL approval draft (CHAT, 400 tokens, 3000ms)
- Plus micro-replan variants LLM-M1/M2/M3

Callers
-------
- SketchService, ExpandService, ValidateService, HILCoordinator
- NOT CommitService (PLAN-03)

Adapters
--------
- V1: TestLLMAdapter (deterministic, per-stage canned responses)
- V2: LLMGatewayAdapter (production, via LLM Request Bus)

Import graph (Layer 1)
----------------------
k1.planner.ports.llm_port
  -> k1.planner.types  (PlannerLLMRequest, PlannerLLMResponse)
  -> typing, typing_extensions
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from k1.planner.types import PlannerLLMRequest, PlannerLLMResponse


@runtime_checkable
class ILLMPort(Protocol):
    """Planner LLM inference port -- single ``execute()`` method.

    This is a structural protocol (``typing.Protocol``).  Any object with
    a matching ``execute()`` signature satisfies it via structural subtyping.

    Budget enforcement (PLAN-11)
    ----------------------------
    Every ``PlannerLLMRequest`` carries ``constraints.max_tokens`` and
    ``constraints.timeout_ms``.  The Planner sets these; the Model Hub
    enforces them.  There is no way to issue an unbounded LLM call
    through this port.
    """

    async def execute(self, request: PlannerLLMRequest) -> PlannerLLMResponse:
        """Execute a single LLM inference call via the Model Hub.

        Args:
            request: ``PlannerLLMRequest`` envelope containing capability type,
                payload (messages + schema), constraints (budget, timeout,
                temperature), and trace_id.

        Returns:
            ``PlannerLLMResponse`` with the LLM result and response metadata
            (token usage, latency, model_id).
        """
        ...  # pragma: no cover


__all__ = ["ILLMPort"]
