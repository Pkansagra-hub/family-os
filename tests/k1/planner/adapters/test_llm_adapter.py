"""TestLLMAdapter -- in-memory ILLMPort implementation (SS16.2.2).

Implements the ILLMPort Protocol (SS15.3) with:
- Per-stage configurable HubResponse mappings
- Error injection for specific stages
- Optional simulated latency (asyncio.sleep)
- Capture-mode recording of all execute() calls
- Deterministic: same input always produces same output
- Protocol-structural compliance with ILLMPort

File location: tests/k1/planner/adapters/ (SS30.3)
Never importable from production code.
"""

from __future__ import annotations

import asyncio
from typing import Dict, List, Optional, Set

from k1.planner.types import HubRequest, HubResponse, PlannerError

# ---------------------------------------------------------------------------
# LLMTimeoutError -- referenced in spec but not yet in planner types.
# Defined here for test adapter usage; will migrate to k1.planner.types
# when production LLMGatewayAdapter is implemented.
# ---------------------------------------------------------------------------


class LLMTimeoutError(PlannerError):
    """LLM inference timed out (SS15.3, SS13.1)."""


# ---------------------------------------------------------------------------
# Stage name detection
# ---------------------------------------------------------------------------

# Canonical stage names used as keys in stage_responses.
STAGE_NAMES = frozenset(
    {
        "SKETCH",
        "EXPAND",
        "VALIDATE",
        "HIL_CLARIFY",
        "HIL_APPROVE",
        # Micro-replan variants
        "MICRO_SKETCH",
        "MICRO_EXPAND",
        "MICRO_VALIDATE",
    }
)


def _detect_stage(request: HubRequest) -> str:
    """Detect stage name from HubRequest using consumer_id or payload heuristic.

    Resolution order:
    1. constraints.consumer_id if it matches a known stage name (case-insensitive)
    2. Payload content heuristic: scan messages for stage keywords
    3. Fallback: "UNKNOWN"
    """
    # 1. consumer_id match
    consumer = getattr(request.constraints, "consumer_id", "")
    upper = consumer.upper().replace("-", "_").replace(" ", "_")
    # Check direct match or suffix match (e.g. "planner_sketch" -> "SKETCH")
    for stage in STAGE_NAMES:
        if upper == stage or upper.endswith(f"_{stage}"):
            return stage

    # 2. Payload heuristic: search messages for stage keywords
    messages = request.payload.get("messages", [])
    content_blob = " ".join(
        str(m.get("content", "")) for m in messages if isinstance(m, dict)
    ).upper()

    # Check micro stages first (more specific)
    for micro in ("MICRO_SKETCH", "MICRO_EXPAND", "MICRO_VALIDATE"):
        if micro.replace("_", " ") in content_blob or micro in content_blob:
            return micro

    for stage in ("SKETCH", "EXPAND", "VALIDATE", "HIL_CLARIFY", "HIL_APPROVE"):
        if stage in content_blob:
            return stage

    return "UNKNOWN"


class TestLLMAdapter:
    """In-memory ILLMPort for deterministic testing (SS16.2.2).

    Constructor
    -----------
    stage_responses : Dict[str, HubResponse]
        Keyed by stage name (SKETCH, EXPAND, VALIDATE, HIL_CLARIFY,
        HIL_APPROVE, MICRO_SKETCH, MICRO_EXPAND, MICRO_VALIDATE).
        Each value is a pre-built HubResponse with valid JSON matching
        the stage's OUTPUT_SCHEMA.
    error_stages : Set[str]
        Stage names configured to raise LLMTimeoutError.
    latency_ms : int
        Optional asyncio.sleep for timing tests (0 = no sleep).
    default_response : Optional[HubResponse]
        Fallback response if stage not in stage_responses.

    Internal state
    --------------
    _call_log : List[HubRequest]
        Capture list of all execute() calls for post-test assertion.
    """

    def __init__(
        self,
        stage_responses: Optional[Dict[str, HubResponse]] = None,
        error_stages: Optional[Set[str]] = None,
        latency_ms: int = 0,
        default_response: Optional[HubResponse] = None,
    ) -> None:
        self._stage_responses: Dict[str, HubResponse] = dict(stage_responses or {})
        self._error_stages: Set[str] = set(error_stages or set())
        self._latency_ms: int = latency_ms
        self._default_response: Optional[HubResponse] = default_response
        self._call_log: List[HubRequest] = []

    # ------------------------------------------------------------------
    # Configuration helpers (test-only)
    # ------------------------------------------------------------------

    def set_stage_response(self, stage: str, response: HubResponse) -> None:
        """Set or override the response for a specific stage."""
        self._stage_responses[stage] = response

    def set_error_stage(self, stage: str) -> None:
        """Configure a stage to raise LLMTimeoutError."""
        self._error_stages.add(stage)

    def clear_error_stage(self, stage: str) -> None:
        """Remove error configuration for a stage."""
        self._error_stages.discard(stage)

    # ------------------------------------------------------------------
    # ILLMPort Protocol method
    # ------------------------------------------------------------------

    async def execute(self, request: HubRequest) -> HubResponse:
        """Execute a deterministic LLM call.

        1. Records request in _call_log.
        2. Detects stage from request.
        3. If latency_ms > 0, sleeps.
        4. If stage in error_stages, raises LLMTimeoutError.
        5. Returns stage_responses[stage] or default_response.
        """
        self._call_log.append(request)

        stage = _detect_stage(request)

        if self._latency_ms > 0:
            await asyncio.sleep(self._latency_ms / 1000.0)

        if stage in self._error_stages:
            raise LLMTimeoutError(
                f"TestLLMAdapter: stage {stage} configured to fail",
                stage=stage,
                trace_id=request.trace_id,
            )

        response = self._stage_responses.get(stage)
        if response is not None:
            return response

        if self._default_response is not None:
            return self._default_response

        # Synthesize a minimal valid response
        return HubResponse(
            result={"content": f'{{"stage": "{stage}", "status": "ok"}}'},
            metadata={
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 50,
                    "total_tokens": 150,
                },
                "latency_ms": self._latency_ms,
                "model_id": "test-model",
            },
        )

    # ------------------------------------------------------------------
    # Assertion / introspection helpers (test-only)
    # ------------------------------------------------------------------

    @property
    def call_log(self) -> List[HubRequest]:
        """Read-only access to the call log."""
        return list(self._call_log)

    @property
    def call_count(self) -> int:
        """Number of execute() calls recorded."""
        return len(self._call_log)

    def get_calls_for_stage(self, stage: str) -> List[HubRequest]:
        """Return all calls that were detected as the given stage."""
        return [r for r in self._call_log if _detect_stage(r) == stage]

    def assert_call_count(self, n: int) -> None:
        """Assert that execute() was called exactly n times."""
        assert self.call_count == n, f"Expected {n} LLM calls, got {self.call_count}"

    def assert_stage_called(self, stage: str) -> None:
        """Assert that at least one call was made for the given stage."""
        calls = self.get_calls_for_stage(stage)
        assert len(calls) > 0, f"No LLM calls detected for stage {stage}"

    def assert_max_tokens(self, stage: str, expected: int) -> None:
        """Assert constraints.max_tokens for calls to the given stage."""
        calls = self.get_calls_for_stage(stage)
        for call in calls:
            actual = call.constraints.max_tokens
            assert (
                actual == expected
            ), f"Stage {stage}: expected max_tokens={expected}, got {actual}"

    def assert_capability_type(self, stage: str, expected: str) -> None:
        """Assert HubRequest.capability for calls to the given stage."""
        calls = self.get_calls_for_stage(stage)
        for call in calls:
            assert call.capability == expected, (
                f"Stage {stage}: expected capability={expected}, " f"got {call.capability}"
            )
