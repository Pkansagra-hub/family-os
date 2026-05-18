"""HumanInTheLoopService -- unified HIL coordinator (E1.M1.8).

Single service that handles:
  - clarification     (planner SKETCH)
  - approval          (planner VALIDATE)
  - needs_human       (concierge Back -> FSM, with suspension)
  - override          (orchestrator ConstraintResolver)
  - capability_gate   (fabric pre-execution gate, with safety policy)

Wire flow:
  caller -> svc.<method>(request)
         -> safety check (gate only)
         -> publish HILEnvelope on TOPIC_HIL_REQUEST
         -> await asyncio.Future keyed by hil_request_id
         -> _on_response (subscribed to TOPIC_HIL_RESPONSE) resolves Future
         -> typed response dataclass returned
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any

from k1.hil.config import HILConfig
from k1.hil.ledger import HILLedgerAdapter
from k1.hil.ports import IEventPort, ILLMPort
from k1.hil.safety import SafetyBandPolicy, SafetyDecision
from k1.hil.suspension import SuspensionManager
from k1.hil.topics import TOPIC_HIL_AUDIT, TOPIC_HIL_REQUEST, TOPIC_HIL_RESPONSE
from k1.hil.types import (
    ApprovalRequest,
    ApprovalResponse,
    CapabilityGateRequest,
    ClarificationRequest,
    ClarificationResponse,
    GateDecision,
    GateOutcome,
    HILEnvelope,
    HILKind,
    HILResponseEnvelope,
    NeedsHumanRequest,
    NeedsHumanResponse,
    OverrideRequest,
    OverrideResponse,
)

logger = logging.getLogger(__name__)


def _now_ms() -> int:
    return int(time.time() * 1000)


class HumanInTheLoopService:
    """One instance per kernel; satisfies `IHILPort` structurally."""

    __slots__ = (
        "_event_port",
        "_llm_port",
        "_safety_policy",
        "_ledger",
        "_suspension_mgr",
        "_config",
        "_pending",
        "_round_budget",
        "_response_subscription",
        "_lock",
        "_shutdown",
        "_counters",
    )

    def __init__(
        self,
        *,
        event_port: IEventPort,
        ledger: HILLedgerAdapter,
        suspension_mgr: SuspensionManager | None,
        safety_policy: SafetyBandPolicy,
        config: HILConfig,
        llm_port: ILLMPort | None = None,
    ) -> None:
        self._event_port = event_port
        self._llm_port = llm_port
        self._safety_policy = safety_policy
        self._ledger = ledger
        self._suspension_mgr = suspension_mgr
        self._config = config
        self._pending: dict[str, asyncio.Future[HILResponseEnvelope]] = {}
        self._round_budget: dict[str, int] = {}
        self._lock = asyncio.Lock()
        self._shutdown = False
        self._counters: dict[str, int] = {
            "unknown_id": 0,
            "legacy_bridge_ignored": 0,
            "resolved": 0,
            "timed_out": 0,
        }
        self._response_subscription = event_port.subscribe(TOPIC_HIL_RESPONSE, self._on_response)

    # ------------------------------------------------------------------
    # Public methods (one per HILKind)
    # ------------------------------------------------------------------

    async def ask_clarification(self, req: ClarificationRequest) -> ClarificationResponse:
        # Round budget enforcement (planner-side per caller_key).
        async with self._lock:
            used = self._round_budget.get(req.caller_key, 0)
            if used >= self._config.max_clarification_rounds:
                logger.info(
                    "hil_clarification_budget_exhausted caller_key=%s used=%d max=%d",
                    req.caller_key,
                    used,
                    self._config.max_clarification_rounds,
                )
                return ClarificationResponse(
                    hil_request_id="",
                    answer=None,
                    timed_out=False,
                    round_budget_exhausted=True,
                )
            self._round_budget[req.caller_key] = used + 1

        # Optional LLM synthesis.
        question = req.pre_formed_question
        if (
            req.synthesize_with_llm
            and self._llm_port is not None
            and self._config.enable_llm_synthesis
            and question is None
        ):
            try:
                question = await self._llm_port.synthesize_question(
                    context=req.question_context, trace_id=req.trace_id
                )
            except Exception as exc:  # noqa: BLE001 -- best-effort
                logger.warning(
                    "hil_llm_synthesis_failed trace_id=%s error=%s",
                    req.trace_id,
                    exc,
                )
                question = None

        payload = {
            "question": question or "",
            "context": dict(req.question_context),
            "synthesize_with_llm": req.synthesize_with_llm,
        }
        resp_env = await self._request(
            HILKind.CLARIFICATION,
            req.caller_key,
            req.trace_id,
            payload,
            req.timeout_ms or self._config.clarification_timeout_ms,
        )
        return ClarificationResponse(
            hil_request_id=resp_env.hil_request_id,
            answer=resp_env.payload.get("answer") if not resp_env.timed_out else None,
            timed_out=resp_env.timed_out,
            round_budget_exhausted=False,
        )

    async def request_approval(self, req: ApprovalRequest) -> ApprovalResponse:
        payload = {
            "summary": req.summary,
            "options": list(req.options),
            "side_effects": list(req.side_effects),
            "safety_assessment": req.safety_assessment,
            "estimated_duration_ms": req.estimated_duration_ms,
        }
        resp_env = await self._request(
            HILKind.APPROVAL,
            req.caller_key,
            req.trace_id,
            payload,
            req.timeout_ms or self._config.approval_timeout_ms,
        )
        if resp_env.timed_out:
            return ApprovalResponse(
                hil_request_id=resp_env.hil_request_id,
                decision="reject",
                modifications=None,
                timed_out=True,
            )
        return ApprovalResponse(
            hil_request_id=resp_env.hil_request_id,
            decision=str(resp_env.payload.get("decision", "reject")),
            modifications=resp_env.payload.get("modifications"),
            timed_out=False,
        )

    async def needs_human(self, req: NeedsHumanRequest) -> NeedsHumanResponse:
        # Suspend BEFORE publishing for crash-recovery.
        if self._suspension_mgr is not None:
            try:
                await self._suspension_mgr.suspend(
                    req.task_id,
                    reason=f"hil:{req.hil_type}",
                    question=req.question,
                    options=list(req.options),
                    context=dict(req.context),
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("hil_suspend_failed task_id=%s error=%s", req.task_id, exc)

        payload = {
            "task_id": req.task_id,
            "hil_type": req.hil_type,
            "question": req.question,
            "options": list(req.options),
            "context": dict(req.context),
            "side_effects": list(req.side_effects),
            "safety_band": req.safety_band,
            "react_history": list(req.react_history),
        }
        timeout_ms = req.timeout_ms or self._config.needs_human_timeout_ms
        resp_env = await self._request(
            HILKind.NEEDS_HUMAN, req.caller_key, req.trace_id, payload, timeout_ms
        )
        resolution = dict(resp_env.payload.get("resolution", {}))
        decision = str(resp_env.payload.get("decision", "timeout" if resp_env.timed_out else ""))
        if self._suspension_mgr is not None and not resp_env.timed_out:
            try:
                await self._suspension_mgr.resolve(req.task_id, resolution)
            except Exception as exc:  # noqa: BLE001
                logger.warning("hil_resolve_failed task_id=%s error=%s", req.task_id, exc)
        return NeedsHumanResponse(
            hil_request_id=resp_env.hil_request_id,
            decision=decision,
            resolution=resolution,
            raw_user_text=resp_env.payload.get("raw_user_text"),
            timed_out=resp_env.timed_out,
        )

    async def request_override(self, req: OverrideRequest) -> OverrideResponse:
        payload = {
            "request_id": req.request_id,
            "plan_id": req.plan_id,
            "unresolved_capabilities": list(req.unresolved_capabilities),
            "proposed_alternatives": list(req.proposed_alternatives),
        }
        resp_env = await self._request(
            HILKind.OVERRIDE,
            req.caller_key,
            req.trace_id,
            payload,
            req.timeout_ms or self._config.override_timeout_ms,
        )
        if resp_env.timed_out:
            return OverrideResponse(
                hil_request_id=resp_env.hil_request_id,
                choice="abort",
                selected_alternative=None,
                fallback_action=None,
                timed_out=True,
            )
        return OverrideResponse(
            hil_request_id=resp_env.hil_request_id,
            choice=str(resp_env.payload.get("choice", "abort")),
            selected_alternative=resp_env.payload.get("selected_alternative"),
            fallback_action=resp_env.payload.get("fallback_action"),
            timed_out=False,
        )

    async def gate_capability(self, req: CapabilityGateRequest) -> GateDecision:
        decision = self._safety_policy.decide(req.contract, req.params)

        if decision is SafetyDecision.ALLOW:
            return GateDecision(
                outcome=GateOutcome.ALLOW,
                hil_request_id=None,
                reason="safety_policy_allow",
                user_approved=None,
                audit_only=False,
            )

        if decision is SafetyDecision.DENY:
            # Reserved path; emit audit if enabled.
            hil_id = str(uuid.uuid4())
            audit_only = self._safety_policy.is_audit_only(req.contract)
            await self._maybe_audit(
                {
                    "event": "blocked",
                    "hil_request_id": hil_id,
                    "kind": HILKind.CAPABILITY_GATE.value,
                    "caller_key": req.caller_key,
                    "capability": req.capability_name,
                    "reason": "safety_policy_deny",
                    "timestamp_ms": _now_ms(),
                }
            )
            return GateDecision(
                outcome=GateOutcome.DENY,
                hil_request_id=hil_id,
                reason="safety_policy_deny",
                user_approved=False,
                audit_only=audit_only,
            )

        # decision is ASK -- publish and await.
        payload = {
            "capability_name": req.capability_name,
            "contract": {
                "name": req.contract.name,
                "safety_band_min": req.contract.safety_band_min,
                "requires_human_confirmation": req.contract.requires_human_confirmation,
                "side_effects": list(req.contract.side_effects),
                "description": req.contract.description,
            },
            "params": dict(req.params),
            "params_summary": req.params_summary,
        }
        resp_env = await self._request(
            HILKind.CAPABILITY_GATE,
            req.caller_key,
            req.trace_id,
            payload,
            req.timeout_ms or self._config.capability_gate_timeout_ms,
        )

        audit_only = self._safety_policy.is_audit_only(req.contract)
        if resp_env.timed_out:
            return GateDecision(
                outcome=GateOutcome.TIMEOUT,
                hil_request_id=resp_env.hil_request_id,
                reason="user_response_timeout",
                user_approved=None,
                audit_only=audit_only,
            )
        approved = bool(resp_env.payload.get("approved", False))
        return GateDecision(
            outcome=GateOutcome.ASK_APPROVED if approved else GateOutcome.ASK_REJECTED,
            hil_request_id=resp_env.hil_request_id,
            reason=str(resp_env.payload.get("reason", "user_decision")),
            user_approved=approved,
            audit_only=audit_only,
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def reset_round_budget(self, caller_key: str) -> None:
        """Clear clarification round counter for a single caller key."""
        # Sync method -- no await; mutate without lock is safe because
        # round_budget reads/writes happen only inside service methods
        # which serialize via `_lock`. This call should happen outside
        # any in-flight request for the same caller_key (planner LC hook).
        self._round_budget.pop(caller_key, None)

    def get_counters(self) -> dict[str, int]:
        """Return a shallow copy of the in-process HIL boundary counters.

        Keys: ``unknown_id``, ``legacy_bridge_ignored``, ``resolved``, ``timed_out``.
        Monotonic per-process. Read by tests and observability; not published.
        """
        return dict(self._counters)

    async def shutdown(self) -> None:
        """Unsubscribe and cancel all pending futures."""
        if self._shutdown:
            return
        self._shutdown = True
        try:
            unsub = getattr(self._event_port, "unsubscribe", None)
            if unsub is not None and self._response_subscription is not None:
                unsub(self._response_subscription)
        except Exception as exc:  # noqa: BLE001
            logger.warning("hil_unsubscribe_failed error=%s", exc)
        async with self._lock:
            for fut in list(self._pending.values()):
                if not fut.done():
                    fut.cancel()
            self._pending.clear()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _request(
        self,
        kind: HILKind,
        caller_key: str,
        trace_id: str,
        payload: dict[str, Any],
        timeout_ms: int,
    ) -> HILResponseEnvelope:
        hil_id = str(uuid.uuid4())
        env = HILEnvelope(
            hil_request_id=hil_id,
            kind=kind,
            caller_key=caller_key,
            trace_id=trace_id,
            created_at_ms=_now_ms(),
            timeout_ms=timeout_ms,
            payload=payload,
        )
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[HILResponseEnvelope] = loop.create_future()
        async with self._lock:
            self._pending[hil_id] = fut

        self._ledger.write_requested(env)
        await self._maybe_audit(
            {
                "event": "requested",
                "hil_request_id": hil_id,
                "kind": kind.value,
                "caller_key": caller_key,
                "trace_id": trace_id,
                "timestamp_ms": env.created_at_ms,
            }
        )
        try:
            await self._event_port.publish(TOPIC_HIL_REQUEST, env.to_dict())
        except Exception as exc:
            logger.error(
                "hil_publish_failed hil_request_id=%s kind=%s error=%s",
                hil_id,
                kind.value,
                exc,
            )
            async with self._lock:
                self._pending.pop(hil_id, None)
            raise

        logger.info(
            "hil_requested hil_request_id=%s kind=%s caller_key=%s timeout_ms=%d",
            hil_id,
            kind.value,
            caller_key,
            timeout_ms,
        )

        try:
            resp = await asyncio.wait_for(fut, timeout=timeout_ms / 1000.0)
            self._counters["resolved"] = self._counters.get("resolved", 0) + 1
            self._ledger.write_resolved(env, resp)
            await self._maybe_audit(
                {
                    "event": "resolved",
                    "hil_request_id": hil_id,
                    "kind": kind.value,
                    "duration_ms": max(0, resp.responded_at_ms - env.created_at_ms),
                    "timestamp_ms": resp.responded_at_ms,
                }
            )
            return resp
        except asyncio.TimeoutError:
            self._counters["timed_out"] = self._counters.get("timed_out", 0) + 1
            timeout_resp = HILResponseEnvelope(
                hil_request_id=hil_id,
                kind=kind,
                responded_at_ms=_now_ms(),
                payload={},
                timed_out=True,
            )
            self._ledger.write_timed_out(env)
            await self._maybe_audit(
                {
                    "event": "timed_out",
                    "hil_request_id": hil_id,
                    "kind": kind.value,
                    "caller_key": caller_key,
                    "timeout_ms": timeout_ms,
                    "timestamp_ms": timeout_resp.responded_at_ms,
                }
            )
            logger.info(
                "hil_timed_out hil_request_id=%s kind=%s caller_key=%s",
                hil_id,
                kind.value,
                caller_key,
            )
            return timeout_resp
        finally:
            async with self._lock:
                self._pending.pop(hil_id, None)

    async def _on_response(self, topic: str, data: dict[str, Any]) -> None:
        try:
            resp = HILResponseEnvelope.from_dict(data)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "hil_response_decode_failed topic=%s error=%s data_keys=%s",
                topic,
                exc,
                list(data.keys()) if isinstance(data, dict) else type(data).__name__,
            )
            return
        async with self._lock:
            fut = self._pending.get(resp.hil_request_id)
        if fut is None:
            if bool(resp.payload.get("legacy_bridge")):
                self._counters["legacy_bridge_ignored"] = (
                    self._counters.get("legacy_bridge_ignored", 0) + 1
                )
                logger.debug(
                    "hil_response_legacy_bridge_ignored hil_request_id=%s kind=%s",
                    resp.hil_request_id,
                    resp.kind.value,
                    extra={
                        "hil_request_id": resp.hil_request_id,
                        "kind": resp.kind.value,
                    },
                )
                return
            self._counters["unknown_id"] = self._counters.get("unknown_id", 0) + 1
            logger.warning(
                "hil_response_unknown_id hil_request_id=%s kind=%s",
                resp.hil_request_id,
                resp.kind.value,
                extra={
                    "hil_request_id": resp.hil_request_id,
                    "kind": resp.kind.value,
                },
            )
            return
        if not fut.done():
            fut.set_result(resp)

    async def _maybe_audit(self, event: dict[str, Any]) -> None:
        if not self._config.enable_audit_topic:
            return
        try:
            await self._event_port.publish(TOPIC_HIL_AUDIT, event)
        except Exception as exc:  # noqa: BLE001
            logger.debug("hil_audit_publish_failed error=%s", exc)
