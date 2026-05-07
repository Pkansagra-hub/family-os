"""``ConciergePolicyGate`` — step-0 hook for ``ToolDispatcher`` (M2.E2.I1).

Wires four pieces together:

* ``PolicyEvaluator``        — pure verdict computation (E6 ∧ matrix ∧ tier)
* ``SituationFrame`` snapshot — provided per call (the dispatcher knows
  the current actor + situation; the gate is told)
* ``HumanInTheLoopService``  — for ``REQUIRE_CONFIRMATION``
  → ``ApprovalRequest`` on ``TOPIC_HIL_REQUEST`` (NEVER calls
  ``concierge.protocols.hitl_pipeline.approval_pipeline`` directly —
  see implementation plan §0.1).
* ``IBus`` (optional)        — emits ``k1.selfmodel.policy.*`` events.

Public API
==========
``ConciergePolicyGate.evaluate(tool_call)`` returns:

* ``None`` when the call should pass through to the dispatcher's
  remaining steps (verdict was ``ALLOW`` — the matrix's intended
  passthrough).
* a fully-formed ``ToolResult`` with ``status="error"`` (or, for
  ``DEFER_OFFLINE``, ``status="partial"``) when the call must be
  blocked at step-0.

The gate is idempotent and re-entrant. It never mutates the
``SituationFrame`` it is given.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

from k1.bus.ports.bus import IBus
from k1.concierge.llm.types import ToolCallResult
from k1.concierge.tools.result_protocol import ToolResult
from k1.hil.service import HumanInTheLoopService
from k1.hil.types import ApprovalRequest, ApprovalResponse
from k1.selfmodel.contracts.policy import (
    FreshnessState,
    PolicyDecision,
    PolicyRequest,
    PolicyVerdict,
    ReasonCode,
    RiskClass,
)
from k1.selfmodel.contracts.risk_class_registry import get_risk_class
from k1.selfmodel.contracts.situation import SituationFrame
from k1.selfmodel.events.payloads import (
    PolicyDeferredEvent,
    PolicyEscalationEvent,
    PolicyVerdictEvent,
)
from k1.selfmodel.events.topics import (
    TOPIC_POLICY_DEFERRED,
    TOPIC_POLICY_ESCALATION,
    TOPIC_POLICY_VERDICT,
)
from k1.selfmodel.ports.risk_catalog import IRiskCatalogPort
from k1.selfmodel.service.policy_evaluator import PolicyEvaluator

__all__ = ["ConciergePolicyGate", "DeferredQueueFn", "FrameProviderFn"]

logger = logging.getLogger(__name__)

# Caller-provided hooks. Both are sync; the gate never blocks on them.
DeferredQueueFn = Callable[[PolicyRequest, SituationFrame], str]  # → queued_id
FrameProviderFn = Callable[[ToolCallResult], SituationFrame]


# M8.E1 — wrappers that ALWAYS dispatch a different effective tool
# (the inner capability name lives in the call arguments). Without
# unwrapping, the gate scores the wrapper itself which is always
# SAFETY_SENSITIVE — never the action the actor is actually attempting.
_WRAPPER_TOOLS: frozenset[str] = frozenset(
    {
        "invoke_capability",
        "batch_invoke_capabilities",
        "spawn_via_fabric",
        "execute_workflow",
    }
)
_WRAPPER_INNER_KEYS: tuple[str, ...] = (
    "capability_name",
    "capability_id",
    "tool_name",
    "name",
    "workflow_name",
)


def _resolve_effective_tool(tool_call: ToolCallResult) -> tuple[str, bool]:
    """Return ``(effective_name, was_unwrapped)``.

    For known wrapper tools, dig into ``arguments`` for the inner
    capability name. Falls back to the wrapper name (which is
    SAFETY_SENSITIVE) when the inner name cannot be resolved — this
    keeps the gate fail-closed.
    """
    name = tool_call.name
    if name not in _WRAPPER_TOOLS:
        return name, False
    args = tool_call.arguments or {}
    if not isinstance(args, dict):
        return name, False
    for key in _WRAPPER_INNER_KEYS:
        candidate = args.get(key)
        if isinstance(candidate, str) and candidate:
            return candidate, True
    return name, False


def _now_ms() -> int:
    return int(time.time() * 1000)


def _publish(bus: IBus | None, topic: str, body: dict[str, object]) -> None:
    if bus is None:
        return
    try:  # observability must never break the hot path
        bus.publish_simple(topic, body)  # type: ignore[attr-defined]
    except Exception:
        try:
            bus.publish(topic, body)  # type: ignore[arg-type]
        except Exception:
            logger.debug("policy_gate_publish_failed topic=%s", topic, exc_info=True)


class ConciergePolicyGate:
    """Step-0 dispatcher hook bridging the matrix to the runtime.

    Construction args:

    * ``actor_id``            — the session's actor (per-session gate)
    * ``frame_provider``      — callable returning the *current*
      ``SituationFrame`` for the dispatched tool call. Allows the gate
      to refresh the frame between calls without us recomposing per
      step.
    * ``hil_service``         — optional ``HumanInTheLoopService``. If
      ``None``, ``REQUIRE_CONFIRMATION`` collapses to a structured
      blocked ``ToolResult`` (no escalation possible).
    * ``deferred_queue_fn``   — optional callable invoked for
      ``DEFER_OFFLINE``; returns the queued-id string. Defaults to a
      no-op that returns ``""``.
    * ``bus``                 — optional ``IBus`` for ``k1.selfmodel.policy.*``.
    * ``current_tier_fn``     — optional callable returning the actor's
      current identity tier (defaults to ``0``). Will be the
      ``IdentitySessionManager`` lookup once M3 lands.
    * ``trace_id_fn``         — optional callable returning a trace id
      to stamp on bus events.
    * ``approval_timeout_ms`` — HIL ``ApprovalRequest`` timeout.
    """

    __slots__ = (
        "_actor_id",
        "_actor_role",
        "_frame_provider",
        "_hil",
        "_evaluator",
        "_bus",
        "_deferred_queue_fn",
        "_current_tier_fn",
        "_trace_id_fn",
        "_approval_timeout_ms",
        "_risk_catalog",
    )

    def __init__(
        self,
        *,
        actor_id: str,
        frame_provider: FrameProviderFn,
        hil_service: HumanInTheLoopService | None = None,
        evaluator: PolicyEvaluator | None = None,
        bus: IBus | None = None,
        deferred_queue_fn: DeferredQueueFn | None = None,
        current_tier_fn: Callable[[], int] | None = None,
        trace_id_fn: Callable[[], str] | None = None,
        approval_timeout_ms: int = 120_000,
        risk_catalog: IRiskCatalogPort | None = None,
        actor_role: str = "",
    ) -> None:
        if not isinstance(actor_id, str) or not actor_id:
            raise ValueError("actor_id must be a non-empty string")
        if frame_provider is None:
            raise ValueError("frame_provider is required")
        self._actor_id = actor_id
        # M13.E1.I1 -- "front" / "back" / "". Empty string preserves
        # legacy behavior (no Front whitelist enforcement) so callers
        # that haven't migrated keep working.
        self._actor_role = (actor_role or "").lower()
        self._frame_provider = frame_provider
        self._hil = hil_service
        self._evaluator = evaluator or PolicyEvaluator()
        self._bus = bus
        self._deferred_queue_fn = deferred_queue_fn
        self._current_tier_fn = current_tier_fn or (lambda: 0)
        self._trace_id_fn = trace_id_fn or (lambda: "")
        self._approval_timeout_ms = int(approval_timeout_ms)
        # M9.E1.I2 -- pluggable risk lookup. Defaults to the legacy
        # in-process registry shim so existing callers keep working.
        self._risk_catalog = risk_catalog

    # ------------------------------------------------------------------
    def _lookup_risk(self, name: str) -> RiskClass:
        """Resolve risk via the injected catalog or the legacy registry.

        M9.E1.I2 -- a ``risk_catalog`` port is preferred when supplied;
        the legacy in-process registry is the transitional fallback so
        callers that haven't migrated yet keep working.
        """
        if self._risk_catalog is not None:
            return self._risk_catalog.get_risk(name)
        return get_risk_class(name)

    # ------------------------------------------------------------------
    async def evaluate(self, tool_call: ToolCallResult) -> ToolResult | None:
        """Evaluate one tool call. ``None`` = pass-through (ALLOW)."""
        if tool_call is None:
            raise ValueError("tool_call is required")

        frame = self._frame_provider(tool_call)
        if not isinstance(frame, SituationFrame):
            raise TypeError(
                "frame_provider must return a SituationFrame, " f"got {type(frame).__name__}"
            )

        risk = self._lookup_risk(tool_call.name)
        effective_name, unwrapped = _resolve_effective_tool(tool_call)
        if unwrapped:
            risk = self._lookup_risk(effective_name)

        # M13.E1.I1 -- Front whitelist enforcement. When the wrapper was
        # ``invoke_capability`` AND the actor is the Front voice, only
        # capabilities listed in ``FRONT_READ_CAPABILITY_WHITELIST`` may
        # proceed. Everything else is hard-DENIED with a structured
        # ToolResult so the LLM gets actionable feedback.
        if unwrapped and tool_call.name == "invoke_capability" and self._actor_role == "front":
            from k1.concierge.tools.schemas_front import (
                FRONT_READ_CAPABILITY_WHITELIST,
            )

            if effective_name not in FRONT_READ_CAPABILITY_WHITELIST:
                logger.warning(
                    "policy_gate front_invoke_denied actor_id=%s capability=%s",
                    self._actor_id,
                    effective_name,
                )
                return ToolResult(
                    tool_name=tool_call.name,
                    status="error",
                    error=(
                        f"capability '{effective_name}' is not allowed for the "
                        f"Front actor; route via dispatch_task instead"
                    ),
                    data={
                        "policy_decision": "DENY",
                        "reason": "front_capability_not_whitelisted",
                        "capability_name": effective_name,
                    },
                )

        request = PolicyRequest(
            actor_id=self._actor_id,
            tool_name=effective_name,
            risk_class=risk,
            arguments=dict(tool_call.arguments or {}),
            trace_id=self._trace_id_fn(),
        )
        freshness_state = _freshness_from_frame(frame)
        verdict = self._evaluator.evaluate(
            request,
            frame,
            freshness_state=freshness_state,
            current_tier=int(self._current_tier_fn()),
        )

        # ALLOW (matrix base or emergency override) → passthrough.
        if verdict.decision == PolicyDecision.ALLOW:
            self._emit_verdict(tool_call, risk, verdict, request.trace_id)
            return None

        # M14.E1.I6 — ALLOW_WITH_CAUTION passes through but the emitted
        # verdict carries `caution: true` so UI/LLM can surface a
        # cautionary note.
        if verdict.decision == PolicyDecision.ALLOW_WITH_CAUTION:
            self._emit_verdict(tool_call, risk, verdict, request.trace_id)
            return None

        if verdict.decision == PolicyDecision.DENY:
            self._emit_verdict(tool_call, risk, verdict, request.trace_id)
            return _blocked_result(tool_call, verdict, "error")

        if verdict.decision == PolicyDecision.REQUIRE_IDENTITY:
            self._emit_verdict(tool_call, risk, verdict, request.trace_id)
            return _blocked_result(tool_call, verdict, "error")

        if verdict.decision == PolicyDecision.DEFER_OFFLINE:
            queued_id = ""
            if self._deferred_queue_fn is not None:
                try:
                    queued_id = self._deferred_queue_fn(request, frame) or ""
                except Exception:
                    logger.warning(
                        "deferred_queue_fn_failed tool=%s",
                        tool_call.name,
                        exc_info=True,
                    )
            verdict_with_id = _with_pending(verdict, queued_id)
            self._emit_verdict(tool_call, risk, verdict_with_id, request.trace_id)
            _publish(
                self._bus,
                TOPIC_POLICY_DEFERRED,
                PolicyDeferredEvent(
                    actor_id=self._actor_id,
                    tool_name=tool_call.name,
                    risk_class=risk,
                    queued_id=queued_id,
                    reason=verdict.reason,
                    trace_id=request.trace_id,
                ).to_json(),
            )
            return _blocked_result(tool_call, verdict_with_id, "partial")

        if verdict.decision == PolicyDecision.REQUIRE_CONFIRMATION:
            return await self._handle_confirmation(
                tool_call=tool_call,
                request=request,
                frame=frame,
                risk=risk,
                verdict=verdict,
            )

        # Unreachable; defensive.
        return _blocked_result(tool_call, verdict, "error")

    # ------------------------------------------------------------------
    async def _handle_confirmation(
        self,
        *,
        tool_call: ToolCallResult,
        request: PolicyRequest,
        frame: SituationFrame,
        risk: RiskClass,
        verdict: PolicyVerdict,
    ) -> ToolResult:
        # No HIL service wired → cannot escalate; return structured block.
        if self._hil is None:
            self._emit_verdict(tool_call, risk, verdict, request.trace_id)
            return _blocked_result(tool_call, verdict, "error")

        approval_req = ApprovalRequest(
            caller_key=f"selfmodel:gate:{self._actor_id}",
            trace_id=request.trace_id or "",
            summary=(
                f"Approve tool '{tool_call.name}' (risk={risk.value}) "
                f"for actor {self._actor_id} in situation "
                f"'{frame.situation_kind}'"
            ),
            options=[
                {"id": "approve", "label": "Approve"},
                {"id": "reject", "label": "Reject"},
            ],
            side_effects=[tool_call.name],
            safety_assessment=verdict.reason.value,
            timeout_ms=self._approval_timeout_ms,
        )
        try:
            response: ApprovalResponse = await self._hil.request_approval(approval_req)
        except Exception:
            logger.warning(
                "hil_ask_approval_failed tool=%s actor=%s",
                tool_call.name,
                self._actor_id,
                exc_info=True,
            )
            self._emit_verdict(tool_call, risk, verdict, request.trace_id)
            return _blocked_result(tool_call, verdict, "error")

        verdict_with_id = _with_pending(verdict, response.hil_request_id or "")
        _publish(
            self._bus,
            TOPIC_POLICY_ESCALATION,
            PolicyEscalationEvent(
                actor_id=self._actor_id,
                tool_name=tool_call.name,
                risk_class=risk,
                hil_request_id=response.hil_request_id or "",
                summary=approval_req.summary,
                side_effects=tuple(approval_req.side_effects),
                trace_id=request.trace_id,
            ).to_json(),
        )

        if response.timed_out:
            denied = PolicyVerdict(
                decision=PolicyDecision.DENY,
                reason=ReasonCode.NEEDS_CONFIRMATION,
                detail="approval timed out",
                pending_id=verdict_with_id.pending_id,
            )
            self._emit_verdict(tool_call, risk, denied, request.trace_id)
            return _blocked_result(tool_call, denied, "error")

        if response.decision == "approve":
            allowed = PolicyVerdict(
                decision=PolicyDecision.ALLOW,
                reason=ReasonCode.OK,
                detail="approved by user",
                pending_id=verdict_with_id.pending_id,
                audit_required=verdict.audit_required,
            )
            self._emit_verdict(tool_call, risk, allowed, request.trace_id)
            return None  # passthrough — dispatcher proceeds

        # reject (or anything else)
        denied = PolicyVerdict(
            decision=PolicyDecision.DENY,
            reason=ReasonCode.NEEDS_CONFIRMATION,
            detail=f"approval rejected (decision={response.decision})",
            pending_id=verdict_with_id.pending_id,
        )
        self._emit_verdict(tool_call, risk, denied, request.trace_id)
        return _blocked_result(tool_call, denied, "error")

    # ------------------------------------------------------------------
    def _emit_verdict(
        self,
        tool_call: ToolCallResult,
        risk: RiskClass,
        verdict: PolicyVerdict,
        trace_id: str,
    ) -> None:
        _publish(
            self._bus,
            TOPIC_POLICY_VERDICT,
            PolicyVerdictEvent.from_verdict(
                actor_id=self._actor_id,
                tool_name=tool_call.name,
                risk_class=risk,
                verdict=verdict,
                trace_id=trace_id,
            ).to_json(),
        )


# ---------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------
def _freshness_from_frame(frame: SituationFrame) -> FreshnessState:
    """Worst-of-three rule: any non-fresh projection downgrades the gate.

    Order: ``conflict_pending`` > ``offline_local_only`` > ``stale``
    > ``fresh`` (most-restrictive wins).
    """
    states = {str(v) for v in frame.freshness.values()}
    if FreshnessState.CONFLICT_PENDING.value in states:
        return FreshnessState.CONFLICT_PENDING
    if FreshnessState.OFFLINE_LOCAL_ONLY.value in states:
        return FreshnessState.OFFLINE_LOCAL_ONLY
    if FreshnessState.STALE.value in states:
        return FreshnessState.STALE
    return FreshnessState.FRESH


def _with_pending(verdict: PolicyVerdict, pending_id: str) -> PolicyVerdict:
    if not pending_id or verdict.pending_id == pending_id:
        return verdict
    return PolicyVerdict(
        decision=verdict.decision,
        reason=verdict.reason,
        detail=verdict.detail,
        requires_tier=verdict.requires_tier,
        pending_id=pending_id,
        audit_required=verdict.audit_required,
    )


def _blocked_result(tool_call: ToolCallResult, verdict: PolicyVerdict, status: str) -> ToolResult:
    error_msg = f"selfmodel.policy.{verdict.decision.value}: " f"{verdict.reason.value}" + (
        f" — {verdict.detail}" if verdict.detail else ""
    )
    data: dict[str, Any] = {"verdict": verdict.to_json()}
    return ToolResult(
        tool_name=tool_call.name,
        status=status,
        data=data,
        error=error_msg,
    )
