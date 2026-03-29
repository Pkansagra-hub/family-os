"""HILCoordinator -- Human-in-the-Loop coordination service [F26].

Manages exactly 2 HIL interaction points:
  1. **Clarification** (SKETCH) -- ask user for intent clarification.
  2. **Approval** (VALIDATE) -- ask user to approve a plan with side effects.

Design decisions (SS12, SS12.5)
-------------------------------
- PLAN-10: max 2 clarification rounds per plan, then best-effort.
- Approval does NOT count against clarification round budget.
- LLM generates natural-language questions/summaries (CHAT, 300/400 tokens).
- Event pub/sub via IEventPort for HIL request/response routing.
- Response correlation by ``request_id``.
- Timeouts: 60s clarification, 120s approval.
- LLM failure -> skip HIL entirely (proceed best-effort / auto-decide).
- Micro-replan NEVER triggers HIL (PLAN-12, SS10.4).
- PLAN-01: zero SessionState writes.  PLAN-06: zero capability executions.
- No ToolCallRouter reference -- only I/O is ILLMPort + IEventPort.

Concurrency (SS12.5.2)
-----------------------
- Only ONE HIL interaction active per plan.
- Clarification (SKETCH) completes before approval (VALIDATE).
- Sequential pipeline, no overlap.

Import graph (Layer 2)
----------------------
k1.planner.services.hil_coordinator
  -> k1.planner.ports.llm_port      (ILLMPort)
  -> k1.planner.ports.event_port    (IEventPort)
  -> k1.planner.types               (HubRequest, HubResponse, RequestConstraints,
                                      HILBudgetExceededError, HILTimeoutError,
                                      PlannerConfig)
  -> k1.planner.events              (TOPIC_HIL_* constants, payload dataclasses)
  -> k1.planner.config              (PlannerConfig)
  -> k1.fabric.ports.event_port     (SubscriptionHandle)

NEVER import from stage services, PipelineController, or PlannerAgent.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from k1.planner.config import PlannerConfig
from k1.planner.events import (
    TOPIC_HIL_APPROVAL_REQ,
    TOPIC_HIL_APPROVAL_RESP,
    TOPIC_HIL_CLARIFICATION,
    TOPIC_HIL_CLARIFICATION_RESP,
    HILApprovalRequestPayload,
    HILClarificationPayload,
)
from k1.planner.ports.event_port import IEventPort
from k1.planner.ports.llm_port import ILLMPort
from k1.planner.types import HILTimeoutError, HubRequest, RequestConstraints

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Safety constants (Section 8.4.1 -- auto-approve evaluation)
# ---------------------------------------------------------------------------

_SAFETY_SAFE = "safe"
_SAFETY_GREEN = "GREEN"


class HILCoordinator:
    """Human-in-the-Loop coordinator service [F26].

    Manages clarification (SKETCH) and approval (VALIDATE) interactions
    with the user, enforcing PLAN-10 round budget and providing
    timeout-based fallback paths.

    Constructor
    -----------
    ``__init__(self, llm_port, event_port, config=None)``

    Parameters
    ----------
    llm_port : ILLMPort
        LLM inference port for question/summary generation.
    event_port : IEventPort
        Event bus port for pub/sub of HIL events.
    config : PlannerConfig, optional
        Configuration (defaults used if omitted).
    """

    __slots__ = (
        "_llm_port",
        "_event_port",
        "_config",
        "_round_count",
        "_pending_request_id",
        "_hil_type",
        "_waiting",
    )

    def __init__(
        self,
        llm_port: ILLMPort,
        event_port: IEventPort,
        config: Optional[PlannerConfig] = None,
    ) -> None:
        if llm_port is None:
            raise TypeError("llm_port must not be None")
        if event_port is None:
            raise TypeError("event_port must not be None")

        self._llm_port: ILLMPort = llm_port
        self._event_port: IEventPort = event_port
        self._config: PlannerConfig = config or PlannerConfig()

        # Mutable per-plan state (Section 12.5.1)
        self._round_count: int = 0
        self._pending_request_id: Optional[str] = None
        self._hil_type: Optional[str] = None
        self._waiting: bool = False

    # -- Properties --

    @property
    def round_count(self) -> int:
        """Current clarification round count (PLAN-10)."""
        return self._round_count

    @property
    def waiting(self) -> bool:
        """True while awaiting user response."""
        return self._waiting

    @property
    def config(self) -> PlannerConfig:
        """Configuration (read-only)."""
        return self._config

    # -- reset() (Section 12.5.1 -- LC_PLAN_START) --

    def reset(self) -> None:
        """Reset all per-plan HIL state.

        Called by PipelineController at LC_PLAN_START and micro-replan start.
        """
        self._round_count = 0
        self._pending_request_id = None
        self._hil_type = None
        self._waiting = False

    # -- Clarification flow (Section 12.2.2) --

    async def request_clarification(
        self,
        request_id: str,
        question_context: Dict[str, Any],
    ) -> Optional[str]:
        """Trigger clarification flow (7 steps, Section 12.2.2).

        Called by SketchService when ambiguity is detected.

        Returns user response text, or None on:
          - Round budget exhausted (PLAN-10)
          - LLM failure generating question
          - Timeout (60s)

        Args:
            request_id: Plan request ID for correlation.
            question_context: Dict with 'question', 'intent', and any
                additional context from SKETCH discovery.

        Returns:
            User response text, or ``None``.
        """
        # Step 1: Check round budget (PLAN-10).
        if not self._check_round_budget():
            log.info(
                "hil.clarification.budget_exhausted request_id=%s "
                "round_count=%d max=%d proceeding_best_effort",
                request_id,
                self._round_count,
                self._config.max_hil_rounds,
            )
            return None

        # Step 2: Generate question via ILLMPort.
        question = await self._generate_clarification_question(
            question_context,
            trace_id=request_id,
        )
        if question is None:
            log.warning(
                "hil.clarification.llm_failure request_id=%s "
                "skipping_hil_proceeding_best_effort",
                request_id,
            )
            return None

        # Step 3: Emit clarification event.
        payload = HILClarificationPayload(
            request_id=request_id,
            question=question,
            context=question_context,
            trace_id=request_id,
        )
        self._event_port.emit(TOPIC_HIL_CLARIFICATION, payload)

        # Step 4: Set pending state.
        self._pending_request_id = request_id
        self._hil_type = "clarification"
        self._waiting = True

        # Step 5: Wait for response.
        try:
            response = await self._wait_for_response(
                topic=TOPIC_HIL_CLARIFICATION_RESP,
                request_id=request_id,
                timeout_ms=self._config.hil_clarification_timeout_ms,
            )
        except asyncio.TimeoutError:
            log.info(
                "hil.clarification.timeout request_id=%s timeout_ms=%d",
                request_id,
                self._config.hil_clarification_timeout_ms,
            )
            self._waiting = False
            self._pending_request_id = None
            self._hil_type = None
            # Increment round -- timeout still counts as a round used.
            self._round_count += 1
            return None

        # Step 6: Process response.
        self._waiting = False
        self._pending_request_id = None
        self._hil_type = None

        # Step 7: Increment round count and return.
        self._round_count += 1

        user_response = _extract_user_response(response)
        return user_response

    # -- Approval flow (Section 12.3.2) --

    async def request_approval(
        self,
        request_id: str,
        plan_summary: str,
        side_effects: List[str],
        safety_assessment: str,
        estimated_duration_ms: int,
    ) -> str:
        """Trigger approval flow (5 steps, Section 12.3.2).

        Called by ValidateService for high-risk plans.
        Approval does NOT count against PLAN-10 round budget.

        Returns one of: ``"approve"``, ``"modify"``, ``"reject"``.

        Args:
            request_id: Plan request ID for correlation.
            plan_summary: Human-readable plan summary.
            side_effects: List of side-effect descriptions.
            safety_assessment: Arbiter safety assessment string.
            estimated_duration_ms: Estimated total plan duration.

        Returns:
            ``"approve"``, ``"modify"``, or ``"reject"``.

        Raises:
            HILTimeoutError: On timeout when plan is not safe to
                auto-approve.
        """
        # Step 1: Generate approval summary via ILLMPort.
        summary = await self._generate_approval_summary(
            plan_summary=plan_summary,
            side_effects=side_effects,
            safety_assessment=safety_assessment,
            trace_id=request_id,
        )
        if summary is None:
            # LLM failure -- auto-decide based on safety.
            log.warning(
                "hil.approval.llm_failure request_id=%s evaluating_auto_decision",
                request_id,
            )
            return self._evaluate_auto_approve_decision(safety_assessment, side_effects, request_id)

        # Step 2: Emit approval request event.
        payload = HILApprovalRequestPayload(
            request_id=request_id,
            summary=summary,
            options=["approve", "modify", "reject"],
            side_effects=side_effects,
            safety_assessment=safety_assessment,
        )
        self._event_port.emit(TOPIC_HIL_APPROVAL_REQ, payload)

        # Step 3: Set pending state.
        self._pending_request_id = request_id
        self._hil_type = "approval"
        self._waiting = True

        # Step 4: Wait for response.
        try:
            response = await self._wait_for_response(
                topic=TOPIC_HIL_APPROVAL_RESP,
                request_id=request_id,
                timeout_ms=self._config.hil_approval_timeout_ms,
            )
        except asyncio.TimeoutError:
            log.info(
                "hil.approval.timeout request_id=%s timeout_ms=%d",
                request_id,
                self._config.hil_approval_timeout_ms,
            )
            self._waiting = False
            self._pending_request_id = None
            self._hil_type = None
            return self._evaluate_auto_approve_decision(safety_assessment, side_effects, request_id)

        # Step 5: Parse response and return.
        self._waiting = False
        self._pending_request_id = None
        self._hil_type = None

        response_type = _extract_approval_response(response)
        return response_type

    # -- Private: Round budget check (PLAN-10) --

    def _check_round_budget(self) -> bool:
        """Return True if clarification rounds are available."""
        return self._round_count < self._config.max_hil_rounds

    # -- Private: Auto-approve evaluation (Section 12.5.3) --

    def _evaluate_auto_approve_decision(
        self,
        safety_assessment: str,
        side_effects: List[str],
        request_id: str,
    ) -> str:
        """Evaluate whether to auto-approve on timeout/LLM failure.

        Auto-approve when:
          - No side effects AND safe assessment, OR
          - Safety assessment is "safe"

        Otherwise raise HILTimeoutError (plan cannot proceed without
        explicit approval for unsafe/side-effecting plans).
        """
        is_safe = safety_assessment.lower() == _SAFETY_SAFE
        no_side_effects = len(side_effects) == 0

        if is_safe or no_side_effects:
            log.info(
                "hil.approval.auto_approve request_id=%s " "safety=%s side_effects_count=%d",
                request_id,
                safety_assessment,
                len(side_effects),
            )
            return "approve"

        log.warning(
            "hil.approval.auto_reject request_id=%s "
            "safety=%s side_effects_count=%d plan_requires_explicit_approval",
            request_id,
            safety_assessment,
            len(side_effects),
        )
        raise HILTimeoutError(
            f"Approval timed out: plan has {len(side_effects)} side effects "
            f"with safety_assessment='{safety_assessment}'; "
            "explicit user approval required",
            stage="VALIDATE",
            request_id=request_id,
            trace_id=request_id,
        )

    # -- Private: Wait for correlated response (Section 12.5.3) --

    async def _wait_for_response(
        self,
        topic: str,
        request_id: str,
        timeout_ms: int,
    ) -> Optional[Dict[str, Any]]:
        """Subscribe to inbound topic and wait for correlated response.

        Uses an asyncio.Event to bridge the synchronous emit-based
        IEventPort handler to an async wait.

        Args:
            topic: Inbound response topic to subscribe to.
            request_id: Expected request_id for correlation.
            timeout_ms: Max wait time in milliseconds.

        Returns:
            Response payload dict, or None if no payload.

        Raises:
            asyncio.TimeoutError: If timeout expires before response.
        """
        result: Dict[str, Any] = {}
        received = asyncio.Event()

        def _handler(_topic: str, payload: Any) -> None:
            # Correlate by request_id.
            payload_dict = _payload_to_dict(payload)
            payload_request_id = payload_dict.get("request_id", "")
            if payload_request_id == request_id:
                result.update(payload_dict)
                received.set()

        handle = self._event_port.subscribe(topic, _handler)
        try:
            await asyncio.wait_for(
                received.wait(),
                timeout=timeout_ms / 1000.0,
            )
            return result if result else None
        finally:
            self._event_port.unsubscribe(handle)

    # -- Private: LLM question generation (Section 12.2.2, LLM-5a) --

    async def _generate_clarification_question(
        self,
        question_context: Dict[str, Any],
        trace_id: str,
    ) -> Optional[str]:
        """Generate a clarification question via ILLMPort (CHAT, 300 tokens).

        Returns question text, or None on LLM failure.
        """
        intent = question_context.get("intent", "")
        ambiguity = question_context.get("question", "")
        known_context = question_context.get("known_context", "")

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a family assistant asking a clarification question. "
                    "Respond with a single natural-language question. "
                    "Keep it conversational and appropriate for a family context."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Intent: {intent}\n"
                    f"What is unclear: {ambiguity}\n"
                    f"Known context: {known_context}"
                ),
            },
        ]

        request = HubRequest(
            capability="CHAT",
            payload={"messages": messages, "temperature": 0.7},
            constraints=RequestConstraints(
                max_tokens=300,
                timeout_ms=3000,
                temperature=0.7,
            ),
            trace_id=trace_id,
        )

        try:
            response = await self._llm_port.execute(request)
            content = response.result.get("content", "")
            return content if content else None
        except Exception:
            log.exception("hil.clarification.llm_error trace_id=%s", trace_id)
            return None

    # -- Private: LLM summary generation (Section 12.3.2, LLM-5b) --

    async def _generate_approval_summary(
        self,
        plan_summary: str,
        side_effects: List[str],
        safety_assessment: str,
        trace_id: str,
    ) -> Optional[str]:
        """Generate an approval summary via ILLMPort (CHAT, 400 tokens).

        Returns summary text, or None on LLM failure.
        """
        side_effects_text = "\n".join(f"- {se}" for se in side_effects) if side_effects else "None"

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a family assistant presenting a plan for approval. "
                    "Summarize the plan in plain language. "
                    "Highlight side effects, costs, and affected external systems. "
                    "Present options: approve, modify, or reject."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Plan summary: {plan_summary}\n"
                    f"Side effects:\n{side_effects_text}\n"
                    f"Safety assessment: {safety_assessment}"
                ),
            },
        ]

        request = HubRequest(
            capability="CHAT",
            payload={"messages": messages, "temperature": 0.7},
            constraints=RequestConstraints(
                max_tokens=400,
                timeout_ms=3000,
                temperature=0.7,
            ),
            trace_id=trace_id,
        )

        try:
            response = await self._llm_port.execute(request)
            content = response.result.get("content", "")
            return content if content else None
        except Exception:
            log.exception("hil.approval.llm_error trace_id=%s", trace_id)
            return None


# ---------------------------------------------------------------------------
# Module-level helpers (no state, no I/O)
# ---------------------------------------------------------------------------


def _payload_to_dict(payload: Any) -> Dict[str, Any]:
    """Convert a payload (dataclass or dict) to a plain dict."""
    if isinstance(payload, dict):
        return payload
    if hasattr(payload, "__dataclass_fields__"):
        from dataclasses import asdict

        return asdict(payload)  # type: ignore[arg-type]
    return {}


def _extract_user_response(response: Optional[Dict[str, Any]]) -> Optional[str]:
    """Extract user response text from clarification response payload."""
    if response is None:
        return None
    # Concierge sends {"request_id": ..., "response": "user text"}
    text = response.get("response", response.get("text", ""))
    return text if text else None


def _extract_approval_response(response: Optional[Dict[str, Any]]) -> str:
    """Extract approval response type from approval response payload.

    Returns "approve", "modify", or "reject".  Defaults to "approve"
    if response_type is missing or unrecognised.
    """
    if response is None:
        return "approve"
    response_type = response.get("response_type", response.get("decision", ""))
    if response_type in ("approve", "modify", "reject"):
        return response_type
    return "approve"


__all__ = ["HILCoordinator"]
