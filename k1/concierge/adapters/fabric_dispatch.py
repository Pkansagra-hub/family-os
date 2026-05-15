"""
k1.concierge.adapters.fabric_dispatch -- Production adapter for IDispatchPort.

Unifies IFabricPort (LOW tier) + OrchestratorStub (MED/HIGH tier)
behind the single IDispatchPort Protocol.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import Any

from k1.concierge.bus.builders import build_task_complete, build_task_failed
from k1.fabric.types import CapabilityRequest, CapabilityResult, ErrorInfo

logger = logging.getLogger(__name__)

# M17.E1.I3 -- prefix used by the back-actor `execute_workflow` tool when
# routing through `IDispatchPort.dispatch_direct`. The capability_name
# convention is ``workflow.<workflow_id>``; everything after the prefix is
# the workflow_id passed to the WorkflowEngine.
_WORKFLOW_PREFIX = "workflow."

# M17.E1.I3 -- params keys used to opt into the SAVE path (rather than RUN).
# When set, the dispatch adapter forwards a ``WorkflowSaveRequest`` to the
# WorkflowEngine instead of a ``WorkflowRunRequest``.
_PARAM_PERSIST = "_persist"
_PARAM_TRIGGER_SPEC = "_trigger_spec"
_PARAM_COMMITTED_PLAN_ID = "_committed_plan_id"
_PARAM_WORKFLOW_NAME = "_workflow_name"


class FabricDispatchAdapter:
    """Production adapter for IDispatchPort — Fabric + Orchestrator.

    LOW tier: dispatch_direct → IFabricPort.execute(CapabilityRequest)
    MED/HIGH: dispatch_envelope → orchestrator.handle_task(envelope) →
              publish task.complete.v1 / task.failed.v1 onto the
              session bus.

    M17.E1.I3 — When ``capability_name`` starts with ``workflow.``,
    ``dispatch_direct`` intercepts BEFORE the fabric resolution step and
    forwards the request to the production ``WorkflowEngine``. The
    ``workflow.*`` namespace has no Fabric provider; routing through the
    engine is the production path for Flow 4 (long-running workflows /
    proactive briefings). When the engine is not wired the adapter falls
    back to the existing fabric path so existing fabric-only tests stay
    green.

    The bus bridge is required because the kernel-level
    ``OrchestratorService`` emits ``ORCH_DAG_COMPLETED`` via its own
    ``_delta_port`` wired to the kernel-global bus, while the concierge
    FSM subscribes to the per-session bus. Without this bridge the
    session-scoped FSM would never observe completion.

    Also exposes ``execute()`` and ``discover_capabilities()`` as aliases so
    that legacy code can use this adapter as a drop-in until
    P4B.5 removes these bridge methods.
    """

    def __init__(
        self,
        fabric_port: Any,
        orchestrator: Any = None,
        bus: Any = None,
        workflow_engine: Any = None,
    ) -> None:
        self._fabric = fabric_port
        self._orchestrator = orchestrator
        self._bus = bus
        # M17.E1.I3 -- WorkflowEngine for workflow.* capability routing.
        # Optional: when None, workflow.* requests fall through to the
        # fabric (which will return resolution_failed). Production wires
        # this to ``OrchestratorService._workflow_engine``.
        self._workflow_engine = workflow_engine

    async def dispatch_direct(self, request: CapabilityRequest) -> CapabilityResult:
        # M17.E1.I3 -- workflow.* interception BEFORE fabric resolution.
        if request.capability_name.startswith(_WORKFLOW_PREFIX):
            if self._workflow_engine is not None:
                return await self._dispatch_workflow(request)
            # No engine wired; surface a clear error rather than the
            # generic fabric `resolution_failed` so the caller knows the
            # routing target was workflow-specific.
            logger.warning(
                "dispatch_direct.workflow_engine_not_wired capability=%s",
                request.capability_name,
            )
            return CapabilityResult(
                request_id=request.request_id,
                trace_id=request.trace_id,
                success=False,
                error=ErrorInfo(
                    code="workflow_engine_not_wired",
                    message=(
                        "workflow.* dispatch requires WorkflowEngine; "
                        "construct FabricDispatchAdapter with workflow_engine= "
                        "or wire OrchestratorService."
                    ),
                    retriable=False,
                ),
            )
        return await self._fabric.execute(request)

    async def _dispatch_workflow(self, request: CapabilityRequest) -> CapabilityResult:
        """Route a ``workflow.<id>`` capability call to the WorkflowEngine.

        Two modes, switched on the ``_persist`` param:

        * **RUN** (default): build ``WorkflowRunRequest`` and call
          ``engine.execute_workflow(...)``. Returns success when the
          engine reports COMPLETED or DEGRADED.
        * **SAVE** (``params["_persist"] = True``): build
          ``WorkflowSaveRequest`` and call ``engine.save_workflow(...)``.
          Requires ``params["_committed_plan_id"]`` and
          ``params["_trigger_spec"]`` (a ``TriggerSpec`` instance OR a
          dict that constructs one). Returns success when the engine
          reports COMPLETED.
        """
        # Local imports keep the module import-cycle-safe; orchestrator
        # types depend on bus/state machinery that isn't required for
        # tests that only exercise the LOW tier path.
        from k1.orchestrator.types import (
            ProcessingContext,
            ProcessResult,
            TriggerSpec,
            TriggerType,
            WorkflowRunRequest,
            WorkflowSaveRequest,
        )

        params = dict(request.params or {})
        persist = bool(params.pop(_PARAM_PERSIST, False))
        trigger_spec_raw = params.pop(_PARAM_TRIGGER_SPEC, None)
        committed_plan_id = params.pop(_PARAM_COMMITTED_PLAN_ID, "")
        workflow_name_override = params.pop(_PARAM_WORKFLOW_NAME, "")
        workflow_id = request.capability_name[len(_WORKFLOW_PREFIX) :]

        ctx = ProcessingContext(
            trace_id=request.trace_id or "",
            request_id=request.request_id,
            tier=request.tier,
            session_id=request.session_id or None,
        )

        try:
            if persist:
                trigger_spec = self._coerce_trigger_spec(trigger_spec_raw, TriggerSpec, TriggerType)
                save_req = WorkflowSaveRequest(
                    committed_plan_id=str(committed_plan_id),
                    workflow_name=str(workflow_name_override or workflow_id),
                    trigger_spec=trigger_spec,
                    trace_id=request.trace_id or "",
                )
                process_result = await self._workflow_engine.save_workflow(save_req, ctx)
                return self._workflow_result_to_capability(
                    request,
                    process_result,
                    ProcessResult,
                    data={
                        "mode": "save",
                        "workflow_name": save_req.workflow_name,
                        "committed_plan_id": save_req.committed_plan_id,
                    },
                )

            run_req = WorkflowRunRequest(
                workflow_id=workflow_id,
                version=str(params.pop("_version", "")) or "",
                trigger_type=TriggerType.MANUAL,
                trace_id=request.trace_id or "",
                trigger_context={"caller": request.caller, "caller_id": request.caller_id},
                param_overrides=params,
            )
            process_result = await self._workflow_engine.execute_workflow(run_req, ctx)
            return self._workflow_result_to_capability(
                request,
                process_result,
                ProcessResult,
                data={"mode": "run", "workflow_id": workflow_id},
            )
        except ValueError as exc:
            return CapabilityResult(
                request_id=request.request_id,
                trace_id=request.trace_id,
                success=False,
                error=ErrorInfo(
                    code="workflow_request_invalid",
                    message=str(exc),
                    retriable=False,
                ),
            )
        except Exception as exc:  # pragma: no cover -- defensive
            logger.exception(
                "dispatch_direct.workflow_dispatch_failed capability=%s",
                request.capability_name,
            )
            return CapabilityResult(
                request_id=request.request_id,
                trace_id=request.trace_id,
                success=False,
                error=ErrorInfo(
                    code="workflow_dispatch_error",
                    message=str(exc),
                    retriable=False,
                ),
            )

    @staticmethod
    def _coerce_trigger_spec(raw: Any, trigger_spec_cls: Any, trigger_type_cls: Any) -> Any:
        """Accept either a real TriggerSpec or a plain dict from JSON tools."""
        if raw is None:
            # Default to a MANUAL trigger so callers that omit the spec
            # still produce a valid persisted workflow.
            return trigger_spec_cls(type=trigger_type_cls.MANUAL)
        if isinstance(raw, trigger_spec_cls):
            return raw
        if isinstance(raw, dict):
            type_str = str(raw.get("type", "MANUAL")).upper()
            try:
                ttype = trigger_type_cls(type_str)
            except ValueError as exc:
                raise ValueError(f"unknown trigger type: {type_str!r}") from exc
            return trigger_spec_cls(
                type=ttype,
                schedule=raw.get("schedule"),
                timezone=str(raw.get("timezone", "UTC")),
                event_topic=raw.get("event_topic"),
                enabled=bool(raw.get("enabled", True)),
            )
        raise ValueError(f"_trigger_spec must be TriggerSpec or dict, got {type(raw).__name__}")

    @staticmethod
    def _workflow_result_to_capability(
        request: CapabilityRequest,
        process_result: Any,
        process_result_cls: Any,
        data: dict,
    ) -> CapabilityResult:
        """Translate ``ProcessResult`` to ``CapabilityResult``.

        COMPLETED / DEGRADED → success (DEGRADED includes the outcome
        string in the data so the caller can react).
        Anything else → failure with code ``workflow_<status>``.
        """
        outcome = getattr(process_result, "value", str(process_result))
        outcome_str = str(outcome).upper()
        success = process_result in (
            process_result_cls.COMPLETED,
            process_result_cls.DEGRADED,
        )
        if success:
            return CapabilityResult(
                request_id=request.request_id,
                trace_id=request.trace_id,
                success=True,
                data={**data, "process_result": outcome_str},
                provider_id="workflow_engine",
            )
        return CapabilityResult(
            request_id=request.request_id,
            trace_id=request.trace_id,
            success=False,
            error=ErrorInfo(
                code=f"workflow_{outcome_str.lower()}",
                message=f"WorkflowEngine returned {outcome_str}",
                retriable=process_result is process_result_cls.DEFERRED,
            ),
            data={**data, "process_result": outcome_str},
            provider_id="workflow_engine",
        )

    async def dispatch_envelope(self, envelope: Any) -> Any:
        if self._orchestrator is None:
            raise RuntimeError(
                "IDispatchPort.dispatch_envelope called but no orchestrator is wired. "
                "Enable orchestrator in KernelConfig."
            )
        result = await self._orchestrator.handle_task(envelope)

        # Bridge orchestrator outcome onto the per-session bus so the
        # concierge FSM (subscribed to the session bus) observes it.
        # The orchestrator's _emit_result fires ORCH_DAG_COMPLETED on
        # the kernel-global delta_bus, which the session-scoped FSM
        # cannot see.
        if self._bus is not None:
            self._publish_task_outcome(envelope, result)
        return result

    def _publish_task_outcome(self, envelope: Any, result: Any) -> None:
        """Publish task.complete.v1 / task.failed.v1 onto the session bus.

        Uses ProcessResult.value when available (string enum), else falls
        back to str(result). Treats COMPLETED/DEGRADED as success
        (DEGRADED means partial success per orchestrator semantics).
        """
        try:
            outcome = getattr(result, "value", str(result)).upper()
            task_id = getattr(envelope, "task_id", "") or getattr(envelope, "envelope_id", "")
            trace_id = (
                getattr(envelope, "trace_id", "")
                or getattr(envelope, "cognitive_trace_id", "")
                or ""
            )
            session_id = getattr(envelope, "session_id", "") or ""
            if outcome in ("COMPLETED", "DEGRADED"):
                env = build_task_complete(
                    payload={
                        "task_id": task_id,
                        "result_type": "complete",
                        "trace_id": trace_id,
                        "session_id": session_id,
                        "source": "orchestrator",
                        "process_result": outcome,
                    },
                )
                env = replace(env, cognitive_trace_id=trace_id, session_id=session_id)
                self._bus.publish(env)
            else:
                env = build_task_failed(
                    payload={
                        "task_id": task_id,
                        "reason": "orchestrator_failed",
                        "error_code": f"ORCH_{outcome}",
                        "error_message": f"orchestrator returned {outcome}",
                        "trace_id": trace_id,
                        "session_id": session_id,
                    },
                )
                env = replace(env, cognitive_trace_id=trace_id, session_id=session_id)
                self._bus.publish(env)
        except Exception:
            logger.exception(
                "FabricDispatchAdapter._publish_task_outcome failed for task_id=%s",
                getattr(envelope, "task_id", "?"),
            )

    # -- IFabricPort compat (P4B.2 bridge, removed in P4B.5) --

    async def execute(self, request: CapabilityRequest) -> CapabilityResult:
        """IFabricPort.execute alias → dispatch_direct."""
        return await self.dispatch_direct(request)

    async def execute_batch(
        self, requests: list[CapabilityRequest], strategy: str = "PARALLEL"
    ) -> list[CapabilityResult]:
        """IFabricPort.execute_batch alias."""
        return [await self.dispatch_direct(r) for r in requests]

    async def discover_capabilities(
        self, intent: str = "", domain: str | None = None, **kwargs: Any
    ) -> Any:
        """IFabricPort.discover_capabilities passthrough.

        Fabric.discover_capabilities has ``domain`` as the FIRST positional
        parameter, so always pass ``intent`` as a keyword to avoid
        "multiple values for argument 'domain'" collisions.
        """
        if hasattr(self._fabric, "discover_capabilities"):
            return await self._fabric.discover_capabilities(intent=intent, domain=domain, **kwargs)
        return {"capabilities": [], "count": 0}
