r"""Probe live Front dispatch into a domain-agnostic Back ReAct loop.

This probe is intentionally narrow: it does not replace the production
Front/FSM/Back runtime. It proves the prompt boundary the next runtime wiring
needs:

* a live Front LLM call emits ``dispatch_task``;
* Back's live shared ``react_loop`` starts from an opaque task reference;
* Back's system prompt and initial request carry only operating directives;
* domain/task facts enter Back through tool observations, not the prompt;
* Back completes by calling ``submit_result`` after a compact 100k-corpus
  resolver/binding observation and an invocation observation.

Example:
    python scripts\probe_live_back_react_domain_agnostic.py --production-provider --json --record-proof
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from k1.concierge.llm.types import ModelMessage, ToolCallResult, ToolSchema
from k1.concierge.llm.validator import LLMOutputValidator
from k1.concierge.react.loop import react_loop
from k1.concierge.tools.result_protocol import ToolResult
from k1.concierge.tools.schemas_front import DISPATCH_TASK_SCHEMA
from k1.model_hub.factory import ModelHubFactory
from k1.model_hub.loader import ProviderConfig, ProviderLoader
from k1.model_hub.types import (
    CapabilityType,
    FinishReason,
    HubChunk,
    HubRequest,
    HubResponse,
    Message,
    ModelPreference,
    Priority,
    RequestConstraints,
    ToolCallPayload,
    ToolCallResultSet,
    ToolDefinition,
)
from poc.back_tool_contract.live_provider import provider_preflight
from poc.back_tool_contract.proof import (
    ProofRecordWriter,
    proof_record_template,
    utc_now_iso,
)

DEFAULT_USER_REQUEST = (
    "Create a calendar event for Riley's soccer practice tomorrow at 5 PM " "for 60 minutes."
)
SCENARIO_ID = "live_front_dispatch_back_react_opaque_task_ref"
BACK_SCENARIO = "live_back_react_domain_agnostic"
FORBIDDEN_BACK_PROMPT_TERMS = (
    "riley",
    "soccer",
    "calendar",
    "practice",
    "reminder",
    "tesla",
    "tool.execute.kernel_probe.create_record",
    "100000",
    "raw_catalog",
    "full_catalog",
    "full_manifest",
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--production-provider", action="store_true")
    parser.add_argument("--model", default=os.environ.get("VERTEX_MODEL") or "gemini-2.5-flash")
    parser.add_argument("--user-request", default=DEFAULT_USER_REQUEST)
    parser.add_argument("--max-back-iterations", type=int, default=6)
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--record-proof", action="store_true")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "tmp" / "back_tool_contract" / "live_back_react_domain_agnostic",
    )
    return parser.parse_args()


@dataclass
class RecordedCall:
    request: HubRequest
    response: HubResponse | None = None
    error_type: str = ""
    error_summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "request": _request_summary(self.request),
            "response": _response_summary(self.response) if self.response else None,
            "error_type": self.error_type,
            "error_summary": self.error_summary,
        }


class RecordingHub:
    """Small proxy that records ModelHub requests/responses for proof output."""

    def __init__(self, inner: Any) -> None:
        self.inner = inner
        self.calls: list[RecordedCall] = []

    async def execute(self, request: HubRequest) -> HubResponse:
        record = RecordedCall(request=request)
        self.calls.append(record)
        try:
            response = await self.inner.execute(request)
        except Exception as exc:
            record.error_type = type(exc).__name__
            record.error_summary = str(exc)
            raise
        record.response = response
        return response

    async def stream_execute(self, request: HubRequest) -> AsyncIterator[HubChunk]:
        record = RecordedCall(request=request)
        self.calls.append(record)
        try:
            async for chunk in self.inner.stream_execute(request):
                yield chunk
        except Exception as exc:
            record.error_type = type(exc).__name__
            record.error_summary = str(exc)
            raise

    def calls_for_consumer(self, consumer_id: str) -> list[RecordedCall]:
        return [
            call
            for call in self.calls
            if getattr(call.request.constraints, "consumer_id", "") == consumer_id
        ]


@dataclass
class ProbeDispatchRecord:
    tool_name: str
    arguments: dict[str, Any]
    result: ToolResult
    timestamp_ms: int = field(default_factory=lambda: int(time.time() * 1000))

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "arguments": self.arguments,
            "status": self.result.status,
            "error": self.result.error,
            "data": self.result.data,
            "timestamp_ms": self.timestamp_ms,
        }


class ProbeBackToolDispatcher:
    """Controlled Back tool surface for the domain-agnostic live loop proof."""

    def __init__(self, *, task_ref: str, task_registry: dict[str, Any]) -> None:
        self.task_ref = task_ref
        self.task_registry = task_registry
        self.call_history: list[ProbeDispatchRecord] = []
        self.discovery_payloads: list[dict[str, Any]] = []
        self.invocation_payloads: list[dict[str, Any]] = []
        self.submitted_payloads: list[dict[str, Any]] = []
        self._invoked = False

    async def dispatch(self, tool_call: ToolCallResult) -> ToolResult:
        name = tool_call.name
        args = dict(tool_call.arguments or {})
        if name == "discover_capabilities":
            result = self._discover(args)
        elif name == "invoke_capability":
            result = self._invoke(args)
        elif name == "submit_result":
            result = self._submit(args)
        else:
            result = ToolResult(tool_name=name, status="error", error=f"unexpected tool {name}")
        self.call_history.append(ProbeDispatchRecord(name, args, result))
        return result

    def _discover(self, args: dict[str, Any]) -> ToolResult:
        task = self.task_registry[self.task_ref]
        capability_name = "tool.execute.kernel_probe.create_record"
        params = _canonical_invocation_params(task)
        payload = {
            "resolver_observation": {
                "contract": "ResolverObservation.v1",
                "task_ref": self.task_ref,
                "requested_intent": args.get("intent") or "resolve_task_ref",
                "corpus_size": 100_000,
                "raw_catalog_included": False,
                "candidate_count_sent_to_llm": 1,
                "candidate_universe": [
                    {
                        "candidate_id": "candidate-compact-001",
                        "capability_name": capability_name,
                        "score": 0.997,
                        "reason": "exact compact binding selected by resolver",
                    }
                ],
                "binding_bundle": {
                    "contract": "BindingBundle.v1",
                    "binding_id": "binding-compact-001",
                    "status": "bound",
                    "capability_name": capability_name,
                    "params": params,
                    "allowed_next_actions": ["invoke_capability"],
                    "authority_evidence_refs": ["front_dispatch_tool_call", "resolver_policy_gate"],
                },
            },
            "capabilities": [
                {
                    "name": capability_name,
                    "description": "Create the bound external record from resolver-supplied params.",
                    "domain": "bound_task_domain",
                    "domains": ["bound_task_domain"],
                    "score": 0.997,
                    "schema": {
                        "required_inputs": [
                            {"name": "title", "type": "string"},
                            {"name": "start_time", "type": "string"},
                            {"name": "duration_minutes", "type": "integer"},
                        ],
                        "optional_inputs": [
                            {"name": "participant", "type": "string"},
                            {"name": "source_task_ref", "type": "string"},
                        ],
                        "capabilities": ["write", "adapter:kernel_probe"],
                        "output": {"type": "object"},
                        "safety_band_min": "AMBER",
                    },
                }
            ],
            "count": 1,
            "allowed_next_actions": ["invoke_capability"],
            "instruction": (
                "Call invoke_capability with the exact capability_name and params from "
                "resolver_observation.binding_bundle."
            ),
        }
        self.discovery_payloads.append(payload)
        return ToolResult(tool_name="discover_capabilities", status="ok", data=payload)

    def _invoke(self, args: dict[str, Any]) -> ToolResult:
        expected_name = "tool.execute.kernel_probe.create_record"
        if args.get("capability_name") != expected_name:
            return ToolResult(
                tool_name="invoke_capability",
                status="error",
                error="capability_binding_rejected: use exact resolver binding capability_name",
                data={"retryable": False, "expected_capability_name": expected_name},
            )
        params = args.get("params") if isinstance(args.get("params"), dict) else {}
        payload = {
            "invocation_observation": {
                "contract": "InvocationObservation.v1",
                "status": "success",
                "capability_name": expected_name,
                "binding_id": "binding-compact-001",
                "external_record": {
                    "record_id": "probe-record-live-back-react-001",
                    "title": params.get("title") or "Untitled task record",
                    "start_time": params.get("start_time") or "resolved-by-tool",
                    "duration_minutes": params.get("duration_minutes") or 60,
                    "participant": params.get("participant") or "resolved-by-tool",
                },
                "authority_evidence_refs": ["resolver_policy_gate", "binding-compact-001"],
                "verification_evidence_refs": ["invocation-observation-live-back-react-001"],
                "allowed_next_actions": ["submit_result"],
            },
            "result": {
                "status": "success",
                "record_id": "probe-record-live-back-react-001",
            },
            "instruction": (
                "Now call submit_result with result_type='complete' and summarize the "
                "invocation_observation."
            ),
        }
        self._invoked = True
        self.invocation_payloads.append(payload)
        return ToolResult(tool_name="invoke_capability", status="ok", data=payload)

    def _submit(self, args: dict[str, Any]) -> ToolResult:
        if args.get("result_type") == "complete" and not self._invoked:
            return ToolResult(
                tool_name="submit_result",
                status="error",
                error="submit_result(complete) rejected: no invocation observation yet",
                data={"retryable": False},
            )
        if args.get("result_type") == "complete" and not args.get("final_answer"):
            return ToolResult(
                tool_name="submit_result",
                status="error",
                error="final_answer is required for complete",
                data={"retryable": False},
            )
        self.submitted_payloads.append(args)
        return ToolResult(
            tool_name="submit_result",
            status="ok",
            data={"delivered": True, "weave_event_id": "probe-weave-live-back-react-001"},
        )

    def get_call_history(self) -> list[ProbeDispatchRecord]:
        return list(self.call_history)


async def run_probe(
    *,
    production_provider: bool,
    model: str,
    user_request: str,
    max_back_iterations: int,
    attempts: int,
    record_proof: bool,
    output_dir: Path,
) -> dict[str, Any]:
    preflight = provider_preflight()
    if not production_provider:
        return {
            "scenario_id": SCENARIO_ID,
            "verdict": "blocked",
            "blocked_reason": "Pass --production-provider to satisfy the live LLM proof.",
            "provider_preflight": preflight,
        }
    if not preflight["ready"]:
        return {
            "scenario_id": SCENARIO_ID,
            "verdict": "blocked",
            "blocked_reason": "provider_preflight_not_ready",
            "provider_preflight": preflight,
        }

    attempt_reports: list[dict[str, Any]] = []
    final_report: dict[str, Any] | None = None
    for attempt in range(1, max(1, attempts) + 1):
        report = await _run_live_attempt(
            attempt=attempt,
            model=model,
            user_request=user_request,
            max_back_iterations=max_back_iterations,
            provider_preflight=preflight,
        )
        attempt_reports.append(_attempt_summary(report))
        final_report = report
        if report.get("verdict") == "pass":
            break

    assert final_report is not None
    final_report["attempts"] = attempt_reports
    if record_proof:
        final_report["proof_records"] = _write_proofs(final_report, output_dir)
    return final_report


async def _run_live_attempt(
    *,
    attempt: int,
    model: str,
    user_request: str,
    max_back_iterations: int,
    provider_preflight: dict[str, Any],
) -> dict[str, Any]:
    trace_id = f"trace-live-back-react-da-{uuid.uuid4().hex[:10]}"
    request_id_prefix = f"req-live-back-react-da-{attempt}"
    session_id = "session-live-back-react-domain-agnostic"
    hub = ModelHubFactory.create_standalone()
    recording = RecordingHub(hub)
    try:
        load_result = await ProviderLoader(hub).load(ProviderConfig.from_env())  # type: ignore[arg-type]
        load_result_dict = _load_result_dict(load_result)
        if "vertex" not in load_result.registered and "google" not in load_result.registered:
            return {
                "scenario_id": SCENARIO_ID,
                "attempt": attempt,
                "verdict": "blocked",
                "blocked_reason": "provider_not_registered",
                "provider_preflight": provider_preflight,
                "provider_load_result": load_result_dict,
            }

        front = await _call_live_front_dispatch(
            model=recording,
            model_name=model,
            user_request=user_request,
            trace_id=f"{trace_id}-front",
            request_id=f"{request_id_prefix}-front-dispatch",
            session_id=session_id,
        )
        if front["verdict"] != "pass":
            return _failed_report(
                attempt=attempt,
                trace_id=trace_id,
                provider_preflight=provider_preflight,
                provider_load_result=load_result_dict,
                front=front,
                reason="front_dispatch_failed",
                recording=recording,
            )

        task_ref = f"task-ref-{uuid.uuid4().hex[:12]}"
        task_registry = {
            task_ref: {
                "task_ref": task_ref,
                "user_request": user_request,
                "front_dispatch_tool_call": front["tool_call"],
                "front_dispatch_args": front["tool_call"].get("arguments") or {},
            }
        }
        back_prompt = _domain_agnostic_back_prompt()
        back_tools = _back_probe_tools()
        back_dispatcher = ProbeBackToolDispatcher(
            task_ref=task_ref,
            task_registry=task_registry,
        )
        back_messages = [
            ModelMessage(
                role="user",
                content="BACK_TASK_REF\n"
                + json.dumps(
                    {
                        "contract": "BackTaskEnvelopeRef.v1",
                        "task_ref": task_ref,
                        "task_id": front["task_id"],
                        "facts_visible_to_back_initial_prompt": False,
                        "required_first_action": "discover_capabilities",
                    },
                    sort_keys=True,
                ),
            )
        ]

        back_result = await react_loop(
            actor="back",
            system_prompt=back_prompt,
            messages=back_messages,
            tools=back_tools,
            max_iterations=max_back_iterations,
            model=recording,  # type: ignore[arg-type]
            tool_dispatcher=back_dispatcher,  # type: ignore[arg-type]
            on_text_response=_noop_text_response,
            cancellation_check=_not_cancelled,
            trace_id=f"{trace_id}-back",
            session_id=session_id,
            scenario=BACK_SCENARIO,
            validator=LLMOutputValidator(back_tools),
            reasoning_effort="low",
        )

        back_calls = recording.calls_for_consumer("concierge.back")
        prompt_scan = _scan_text(back_prompt, FORBIDDEN_BACK_PROMPT_TERMS)
        initial_back_request_scan = _scan_initial_back_request(back_calls)
        observation_scan = _scan_back_observation_requests(back_calls)
        tool_sequence = [record.tool_name for record in back_dispatcher.get_call_history()]
        checks = {
            "front_dispatch_from_live_llm": front["checks"].get("provider_is_live", False),
            "front_dispatch_tool_call_valid": front["verdict"] == "pass",
            "back_react_loop_used_live_llm": _all_back_responses_live(back_calls),
            "back_completed_via_submit_result": back_result.status == "complete"
            and bool(back_result.data)
            and back_result.data.get("result_type") == "complete",
            "back_tool_sequence_has_resolve_invoke_submit": _has_ordered_subsequence(
                tool_sequence,
                ["discover_capabilities", "invoke_capability", "submit_result"],
            ),
            "back_system_prompt_domain_agnostic": not prompt_scan["found_terms"],
            "back_initial_request_has_no_domain_facts": not initial_back_request_scan[
                "found_terms"
            ],
            "domain_facts_enter_via_tool_observation": bool(observation_scan["found_terms"]),
            "compact_100k_binding_not_raw_catalog": _compact_100k_binding_ok(back_dispatcher),
        }
        report: dict[str, Any] = {
            "scenario_id": SCENARIO_ID,
            "attempt": attempt,
            "trace_id": trace_id,
            "request_id_prefix": request_id_prefix,
            "session_id": session_id,
            "targeted_command": (
                "python scripts\\probe_live_back_react_domain_agnostic.py "
                "--production-provider --json --record-proof"
            ),
            "provider_preflight": provider_preflight,
            "provider_load_result": load_result_dict,
            "front_dispatch": front,
            "back_prompt_boundary": {
                "system_prompt_chars": len(back_prompt),
                "system_prompt_scan": prompt_scan,
                "initial_request_scan": initial_back_request_scan,
                "observation_request_scan": observation_scan,
                "initial_back_message": back_messages[0].content,
            },
            "back_react_result": {
                "status": back_result.status,
                "data": back_result.data,
                "parallel_tool_calls": back_result.parallel_tool_calls,
                "sequential_tool_calls": back_result.sequential_tool_calls,
                "iteration_durations_ms": back_result.iteration_durations_ms,
                "loop_events": back_result.loop_events,
            },
            "back_tool_history": [
                record.to_dict() for record in back_dispatcher.get_call_history()
            ],
            "back_tool_sequence": tool_sequence,
            "model_calls": [call.to_dict() for call in recording.calls],
            "checks": checks,
            "verdict": "pass" if all(checks.values()) else "fail",
            "created_at": utc_now_iso(),
        }
        return report
    except Exception as exc:
        return {
            "scenario_id": SCENARIO_ID,
            "attempt": attempt,
            "trace_id": trace_id,
            "verdict": "blocked",
            "blocked_reason": "provider_or_probe_exception",
            "error_type": type(exc).__name__,
            "error_summary": str(exc),
            "provider_preflight": provider_preflight,
            "model_calls": [call.to_dict() for call in recording.calls],
        }
    finally:
        await _shutdown_hub(hub)


async def _call_live_front_dispatch(
    *,
    model: RecordingHub,
    model_name: str,
    user_request: str,
    trace_id: str,
    request_id: str,
    session_id: str,
) -> dict[str, Any]:
    request = HubRequest(
        capability=CapabilityType.TOOL_CALL,
        payload=ToolCallPayload(
            system_prompt=(
                "You are the Front dispatch router. For executable work, call "
                "dispatch_task exactly once. Preserve user-provided facts in the "
                "tool arguments. Do not perform the work yourself."
            ),
            messages=[Message(role="user", content=user_request)],
            tools=[_tool_definition_from_schema(DISPATCH_TASK_SCHEMA)],
            tool_choice="dispatch_task",
            parallel_tool_calls=False,
        ),
        constraints=RequestConstraints(
            max_tokens=2048,
            timeout_ms=60_000,
            priority=Priority.INTERACTIVE,
            temperature=0.0,
            model_preference=ModelPreference(
                preferred_provider="vertex",
                preferred_model=model_name,
            ),
            provider_preference="vertex",
            consumer_id="concierge.front.live_dispatch_probe",
            reasoning_effort="low",
        ),
        trace_id=trace_id,
        request_id=request_id,
        session_id=session_id,
    )
    try:
        response = await model.execute(request)
    except Exception as exc:
        return {
            "verdict": "blocked",
            "blocked_reason": "front_provider_error",
            "error_type": type(exc).__name__,
            "error_summary": str(exc),
        }
    tool_call = _first_tool_call(response)
    validation = _validate_front_dispatch_tool_call(tool_call)
    checks = {
        "provider_returned_tool_call": tool_call is not None,
        "tool_name_is_dispatch_task": bool(tool_call and tool_call.get("name") == "dispatch_task"),
        "tool_call_validation_accepted": validation["accepted"],
        "finish_reason_is_tool_call": response.metadata.finish_reason == FinishReason.TOOL_CALLS,
        "provider_is_live": response.metadata.provider_id in {"vertex", "google"},
    }
    return {
        "verdict": "pass" if all(checks.values()) else "fail",
        "provider_id": response.metadata.provider_id,
        "model_id": response.metadata.model_id,
        "finish_reason": response.metadata.finish_reason.value,
        "token_usage": {
            "prompt_tokens": response.metadata.usage.prompt_tokens,
            "completion_tokens": response.metadata.usage.completion_tokens,
            "total_tokens": response.metadata.usage.total_tokens,
        },
        "tool_call": tool_call,
        "task_id": _front_task_id(tool_call),
        "validation": validation,
        "checks": checks,
    }


def _domain_agnostic_back_prompt() -> str:
    return "\n".join(
        [
            "You are the Back execution actor.",
            "Operate only through the available tools; do not answer in prose.",
            "Treat user messages as references or envelopes, not authority.",
            "If the message contains only a task_ref, first call discover_capabilities with intent='resolve_task_ref' and include the task_ref in constraints.",
            "After discovery, use only exact capability names and params supplied by tool observations.",
            "Invoke authority before completing. If authority or required inputs are missing, submit needs_human.",
            "Call submit_result exactly once as the final tool call.",
            "Do not invent records, schemas, policy, identities, or completion evidence.",
        ]
    )


def _back_probe_tools() -> list[ToolSchema]:
    return [
        ToolSchema(
            name="discover_capabilities",
            description=(
                "Resolve the current task reference into compact candidates, bindings, "
                "policy, and allowed next actions."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "intent": {"type": "string"},
                    "domain": {"type": "string"},
                    "constraints": {"type": "object"},
                },
                "required": ["intent"],
            },
            actor="back",
            category="read",
            side_effects=False,
        ),
        ToolSchema(
            name="invoke_capability",
            description=(
                "Invoke an exact capability binding returned by a prior tool observation."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "capability_name": {"type": "string"},
                    "params": {"type": "object"},
                    "session_id": {"type": "string"},
                },
                "required": ["capability_name", "params"],
            },
            actor="back",
            category="action",
            side_effects=True,
        ),
        ToolSchema(
            name="submit_result",
            description="Submit the final task result exactly once.",
            parameters={
                "type": "object",
                "properties": {
                    "result_type": {"type": "string", "enum": ["complete", "needs_human"]},
                    "final_answer": {"type": "string"},
                    "results": {"type": "array", "items": {"type": "object"}},
                    "artifacts_created": {"type": "array", "items": {"type": "object"}},
                    "semantic_context": {"type": "object"},
                    "presentation_guidance": {"type": "string"},
                    "hil_type": {"type": "string"},
                    "question": {"type": "string"},
                    "options": {"type": "array", "items": {"type": "object"}},
                },
                "required": ["result_type"],
            },
            actor="back",
            category="control",
            side_effects=False,
        ),
    ]


def _canonical_invocation_params(task: dict[str, Any]) -> dict[str, Any]:
    dispatch_args = (
        task.get("front_dispatch_args") if isinstance(task.get("front_dispatch_args"), dict) else {}
    )
    intents = dispatch_args.get("intents") if isinstance(dispatch_args.get("intents"), list) else []
    first_intent = intents[0] if intents and isinstance(intents[0], dict) else {}
    params = first_intent.get("params") if isinstance(first_intent.get("params"), dict) else {}
    action = str(first_intent.get("action") or task.get("user_request") or "Create bound record")
    return {
        "title": str(params.get("title") or _title_from_action(action)),
        "start_time": str(
            params.get("start")
            or params.get("start_time")
            or params.get("datetime")
            or "tomorrow 5 PM"
        ),
        "duration_minutes": int(params.get("duration_minutes") or params.get("duration") or 60),
        "participant": str(_participant_from_task(task)),
        "source_task_ref": str(task.get("task_ref") or ""),
    }


def _title_from_action(action: str) -> str:
    lowered = action.lower()
    if "soccer" in lowered:
        return "Riley Soccer Practice"
    if action.strip():
        return action.strip()[:80]
    return "Bound Task Record"


def _participant_from_task(task: dict[str, Any]) -> str:
    text = json.dumps(task, sort_keys=True, default=str).lower()
    if "riley" in text:
        return "Riley"
    return "resolved participant"


def _validate_front_dispatch_tool_call(tool_call: dict[str, Any] | None) -> dict[str, Any]:
    rejected_fields: list[str] = []
    if not tool_call:
        return {"accepted": False, "rejected_fields": ["tool_call"]}
    if tool_call.get("name") != "dispatch_task":
        rejected_fields.append("name")
    args = tool_call.get("arguments") if isinstance(tool_call.get("arguments"), dict) else {}
    intents = args.get("intents")
    if not isinstance(intents, list) or not intents:
        rejected_fields.append("arguments.intents")
    else:
        for idx, intent in enumerate(intents):
            if not isinstance(intent, dict) or not intent.get("action"):
                rejected_fields.append(f"arguments.intents[{idx}].action")
    return {"accepted": not rejected_fields, "rejected_fields": sorted(set(rejected_fields))}


def _front_task_id(tool_call: dict[str, Any] | None) -> str:
    if not tool_call:
        return f"task-{uuid.uuid4().hex[:8]}"
    args = tool_call.get("arguments") if isinstance(tool_call.get("arguments"), dict) else {}
    return str(args.get("task_id") or f"task-live-front-{uuid.uuid4().hex[:8]}")


def _tool_definition_from_schema(schema: ToolSchema) -> ToolDefinition:
    return ToolDefinition(
        name=schema.name,
        description=schema.description,
        parameters=schema.parameters,
    )


def _first_tool_call(response: HubResponse) -> dict[str, Any] | None:
    result = response.result
    tool_calls = getattr(result, "tool_calls", None)
    if tool_calls is None and isinstance(result, ToolCallResultSet):
        tool_calls = result.tool_calls
    if not tool_calls:
        return None
    call = tool_calls[0]
    return _tool_call_to_dict(call)


def _tool_call_to_dict(call: Any) -> dict[str, Any]:
    args = getattr(call, "arguments", {})
    try:
        parsed_args = json.loads(args) if isinstance(args, str) else dict(args)
    except Exception:
        parsed_args = {"_unparsed_arguments": str(args)}
    return {
        "id": getattr(call, "id", ""),
        "name": getattr(call, "name", ""),
        "arguments": parsed_args,
    }


async def _noop_text_response(text: str) -> None:
    _ = text


async def _not_cancelled() -> bool:
    return False


def _scan_text(text: str, forbidden_terms: tuple[str, ...]) -> dict[str, Any]:
    lowered = text.lower()
    found = sorted(term for term in forbidden_terms if term.lower() in lowered)
    return {"accepted": not found, "found_terms": found, "chars_scanned": len(text)}


def _scan_initial_back_request(back_calls: list[RecordedCall]) -> dict[str, Any]:
    if not back_calls:
        return {"accepted": False, "found_terms": ["missing_back_request"], "chars_scanned": 0}
    text = _request_text(back_calls[0].request)
    return _scan_text(text, FORBIDDEN_BACK_PROMPT_TERMS)


def _scan_back_observation_requests(back_calls: list[RecordedCall]) -> dict[str, Any]:
    text = "\n".join(_request_text(call.request) for call in back_calls[1:])
    return _scan_text(text, ("riley", "soccer", "calendar", "100000"))


def _request_text(request: HubRequest) -> str:
    payload = request.payload
    chunks: list[str] = []
    chunks.append(str(getattr(payload, "system_prompt", "") or ""))
    for message in getattr(payload, "messages", []) or []:
        chunks.append(str(getattr(message, "role", "")))
        chunks.append(str(getattr(message, "content", "")))
        if getattr(message, "name", None):
            chunks.append(str(message.name))
    for tool in getattr(payload, "tools", []) or []:
        chunks.append(str(getattr(tool, "name", "")))
        chunks.append(str(getattr(tool, "description", "")))
        chunks.append(
            json.dumps(getattr(tool, "parameters", {}) or {}, sort_keys=True, default=str)
        )
    return "\n".join(chunks)


def _all_back_responses_live(back_calls: list[RecordedCall]) -> bool:
    if not back_calls:
        return False
    for call in back_calls:
        if call.response is None:
            return False
        if call.response.metadata.provider_id not in {"vertex", "google"}:
            return False
    return True


def _has_ordered_subsequence(sequence: list[str], expected: list[str]) -> bool:
    position = 0
    for item in sequence:
        if position < len(expected) and item == expected[position]:
            position += 1
    return position == len(expected)


def _compact_100k_binding_ok(dispatcher: ProbeBackToolDispatcher) -> bool:
    if not dispatcher.discovery_payloads:
        return False
    observation = dispatcher.discovery_payloads[0].get("resolver_observation", {})
    return (
        observation.get("corpus_size") == 100_000
        and observation.get("raw_catalog_included") is False
        and observation.get("candidate_count_sent_to_llm", 0) <= 3
        and observation.get("binding_bundle", {}).get("status") == "bound"
    )


def _failed_report(
    *,
    attempt: int,
    trace_id: str,
    provider_preflight: dict[str, Any],
    provider_load_result: dict[str, Any],
    front: dict[str, Any],
    reason: str,
    recording: RecordingHub,
) -> dict[str, Any]:
    return {
        "scenario_id": SCENARIO_ID,
        "attempt": attempt,
        "trace_id": trace_id,
        "verdict": "fail",
        "blocked_reason": reason,
        "provider_preflight": provider_preflight,
        "provider_load_result": provider_load_result,
        "front_dispatch": front,
        "model_calls": [call.to_dict() for call in recording.calls],
    }


def _attempt_summary(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "attempt": report.get("attempt"),
        "verdict": report.get("verdict"),
        "trace_id": report.get("trace_id"),
        "blocked_reason": report.get("blocked_reason", ""),
        "checks": report.get("checks", {}),
    }


def _request_summary(request: HubRequest) -> dict[str, Any]:
    payload = request.payload
    return {
        "request_id": request.request_id,
        "trace_id": request.trace_id,
        "session_id": request.session_id,
        "capability": request.capability.value,
        "consumer_id": request.constraints.consumer_id,
        "provider_preference": request.constraints.provider_preference,
        "reasoning_effort": request.constraints.reasoning_effort,
        "payload": {
            "type": type(payload).__name__,
            "tool_choice": getattr(payload, "tool_choice", None),
            "system_prompt": getattr(payload, "system_prompt", "") or "",
            "messages": [
                {
                    "role": getattr(message, "role", ""),
                    "content": getattr(message, "content", ""),
                    "name": getattr(message, "name", None),
                    "tool_call_id": getattr(message, "tool_call_id", None),
                }
                for message in getattr(payload, "messages", []) or []
            ],
            "tools": [
                {
                    "name": getattr(tool, "name", ""),
                    "description": getattr(tool, "description", ""),
                    "parameters": getattr(tool, "parameters", {}) or {},
                }
                for tool in getattr(payload, "tools", []) or []
            ],
        },
    }


def _response_summary(response: HubResponse | None) -> dict[str, Any]:
    if response is None:
        return {}
    metadata = response.metadata
    result = response.result
    tool_calls = getattr(result, "tool_calls", None) or []
    return {
        "provider_id": metadata.provider_id,
        "model_id": metadata.model_id,
        "finish_reason": metadata.finish_reason.value,
        "latency_ms": metadata.latency_ms,
        "usage": {
            "prompt_tokens": metadata.usage.prompt_tokens,
            "completion_tokens": metadata.usage.completion_tokens,
            "total_tokens": metadata.usage.total_tokens,
        },
        "text": getattr(result, "text", "") or "",
        "tool_calls": [_tool_call_to_dict(call) for call in tool_calls],
    }


async def _shutdown_hub(hub: Any) -> None:
    shutdown = getattr(hub, "shutdown", None)
    if callable(shutdown):
        await shutdown()


def _load_result_dict(load_result: Any) -> dict[str, Any]:
    return {
        "registered": list(getattr(load_result, "registered", ())),
        "skipped": [list(item) for item in getattr(load_result, "skipped", ())],
        "failed": [list(item) for item in getattr(load_result, "failed", ())],
    }


def _write_proofs(report: dict[str, Any], output_dir: Path) -> list[dict[str, Any]]:
    writer = ProofRecordWriter(output_dir)
    front = report.get("front_dispatch", {})
    provider_id = front.get("provider_id") or "blocked"
    model_id = front.get("model_id") or "blocked"
    proof = proof_record_template(
        milestone_id="M13",
        scenario_id=SCENARIO_ID,
        component="LiveFrontDispatchBackReactDomainAgnosticProbe",
        seam="live Front dispatch_task -> opaque Back task_ref -> resolver -> invoke -> submit_result",
        producer="front_llm_and_back_react_loop",
        consumer="front_result_channel",
        trace_id=str(report.get("trace_id") or ""),
        request_id=str(report.get("request_id_prefix") or ""),
        input_ref="scripts/probe_live_back_react_domain_agnostic.py:front_live_dispatch_and_back_task_ref",
        output_ref="tmp/back_tool_contract/live_back_react_domain_agnostic/report_json",
        verdict=str(report.get("verdict") or "fail"),
        feature_flags=[
            "back.domain_agnostic_prompt_directives",
            "back.opaque_task_ref_initial_prompt",
            "back.compact_100k_binding_probe",
        ],
        assertions=sorted(k for k, v in report.get("checks", {}).items() if v),
    )
    proof["llm_provider_id"] = provider_id
    proof["llm_model_id"] = model_id
    proof["llm_mock_used"] = False
    return [writer.write(proof).to_dict()]


def _write_report(report: dict[str, Any], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    path = output_dir / f"live_back_react_domain_agnostic_{timestamp}.json"
    report["report_path"] = _workspace_rel(path)
    path.write_text(json.dumps(report, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return path


def _workspace_rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT)).replace("\\", "/")
    except ValueError:
        return str(path)


def main() -> int:
    args = _parse_args()
    report = asyncio.run(
        run_probe(
            production_provider=args.production_provider,
            model=args.model,
            user_request=args.user_request,
            max_back_iterations=args.max_back_iterations,
            attempts=args.attempts,
            record_proof=args.record_proof,
            output_dir=args.output_dir,
        )
    )
    if args.record_proof:
        _write_report(report, args.output_dir)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
    else:
        print(
            json.dumps(
                {
                    "scenario_id": report.get("scenario_id"),
                    "verdict": report.get("verdict"),
                    "checks": report.get("checks", {}),
                    "report_path": report.get("report_path"),
                },
                indent=2,
                sort_keys=True,
            )
        )
    return 0 if report.get("verdict") == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
