"""Opt-in live M2B proof: production LLM authors resolve_situation tool call.

This probe makes a real provider request when --live is supplied. It uses the
same ModelHub provider loader/env path as production web/kernel boot.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from k1.model_hub.factory import ModelHubFactory  # noqa: E402
from k1.model_hub.loader import ProviderConfig, ProviderLoader  # noqa: E402
from k1.model_hub.types import (  # noqa: E402
    CapabilityType,
    FinishReason,
    HubRequest,
    Message,
    ModelPreference,
    Priority,
    RequestConstraints,
    ToolCallPayload,
    ToolCallResultSet,
    ToolDefinition,
)
from poc.back_tool_contract.back_prompt_surface import (  # noqa: E402
    build_back_resolver_prompt_surface,
    make_resolver_tool_call,
    validate_resolver_tool_call,
)
from poc.back_tool_contract.proof import (  # noqa: E402
    ProofRecordWriter,
    proof_record_template,
)
from poc.back_tool_contract.resolve_situation import (  # noqa: E402
    resolve_situation,
    validate_resolution_envelope,
)
from scripts.probe_back_resolver_prompt_surface import _back_task_envelope  # noqa: E402


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", default="dentist_riley_5pm", choices=["dentist_riley_5pm"])
    parser.add_argument(
        "--live", action="store_true", help="Actually call the configured LLM provider."
    )
    parser.add_argument("--model", default=os.environ.get("VERTEX_MODEL") or "gemini-2.5-flash")
    parser.add_argument("--json", action="store_true", help="Emit JSON report.")
    parser.add_argument(
        "--record-proof", action="store_true", help="Write M2B ProofRecord artifacts."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "tmp" / "back_tool_contract" / "m2b_back_resolver_live_llm",
        help="Directory for optional proof artifacts.",
    )
    return parser.parse_args()


async def run_probe(
    *,
    live: bool,
    model: str,
    record_proof: bool,
    output_dir: Path,
) -> dict[str, Any]:
    surface = build_back_resolver_prompt_surface(
        _back_task_envelope(),
        scenario_id="calendar_riley",
        session_snapshot={"control.safety_band": "GREEN", "scoreboard.Riley": "person:riley"},
    )
    if not live:
        return {
            "milestone": "M2B",
            "scenario_id": "dentist_riley_5pm",
            "verdict": "skipped",
            "skip_reason": "Pass --live to make a production provider call.",
            "targeted_command": _targeted_command(model),
            "prompt_surface_ref": surface["surface_id"],
        }

    preflight = _provider_preflight()
    if not preflight["ready"]:
        return {
            "milestone": "M2B",
            "scenario_id": "dentist_riley_5pm",
            "verdict": "blocked",
            "targeted_command": _targeted_command(model),
            "provider_preflight": preflight,
            "prompt_surface_ref": surface["surface_id"],
        }

    hub = ModelHubFactory.create_standalone()
    load_result = await ProviderLoader(hub).load(ProviderConfig.from_env())  # type: ignore[arg-type]
    if "vertex" not in load_result.registered and "google" not in load_result.registered:
        await _shutdown_hub(hub)
        return {
            "milestone": "M2B",
            "scenario_id": "dentist_riley_5pm",
            "verdict": "blocked",
            "targeted_command": _targeted_command(model),
            "provider_load_result": _load_result_dict(load_result),
            "prompt_surface_ref": surface["surface_id"],
        }

    request = _hub_request(surface, model=model)
    try:
        response = await hub.execute(request)
    except Exception as exc:
        await _shutdown_hub(hub)
        return {
            "milestone": "M2B",
            "scenario_id": "dentist_riley_5pm",
            "verdict": "blocked",
            "targeted_command": _targeted_command(model),
            "provider_preflight": preflight,
            "provider_load_result": _load_result_dict(load_result),
            "prompt_surface_ref": surface["surface_id"],
            "blocked_reason": "provider_or_modelhub_error",
            "error_type": type(exc).__name__,
            "error_summary": str(exc),
        }
    finally:
        await _shutdown_hub(hub)

    provider_tool_call = _first_tool_call(response.result)
    resolver_tool_call = _provider_tool_call_to_resolver_tool_call(provider_tool_call)
    tool_validation = validate_resolver_tool_call(resolver_tool_call, surface)
    resolution_validation: dict[str, Any] = {"accepted": False, "rejected_fields": ["not_run"]}
    if tool_validation["accepted"]:
        resolution = resolve_situation(resolver_tool_call["arguments"])
        resolution_validation = validate_resolution_envelope(resolution)

    checks = {
        "provider_returned_tool_call": provider_tool_call is not None,
        "tool_name_is_resolve_situation": bool(
            provider_tool_call and provider_tool_call.get("name") == "resolve_situation"
        ),
        "tool_call_validation_accepted": tool_validation["accepted"],
        "m2_resolver_accepts_live_call": resolution_validation["accepted"],
        "finish_reason_is_tool_call": response.metadata.finish_reason == FinishReason.TOOL_CALLS,
        "provider_is_live": response.metadata.provider_id in {"vertex", "google"},
    }
    report: dict[str, Any] = {
        "milestone": "M2B",
        "scenario_id": "dentist_riley_5pm",
        "targeted_command": _targeted_command(model),
        "provider_preflight": preflight,
        "provider_load_result": _load_result_dict(load_result),
        "model_id": response.metadata.model_id,
        "provider_id": response.metadata.provider_id,
        "finish_reason": response.metadata.finish_reason.value,
        "token_usage": {
            "prompt_tokens": response.metadata.usage.prompt_tokens,
            "completion_tokens": response.metadata.usage.completion_tokens,
            "total_tokens": response.metadata.usage.total_tokens,
        },
        "prompt_surface_ref": surface["surface_id"],
        "provider_tool_call": provider_tool_call,
        "resolver_tool_call": resolver_tool_call,
        "tool_call_validation": tool_validation,
        "resolution_validation": resolution_validation,
        "checks": checks,
        "verdict": "pass" if all(checks.values()) else "fail",
    }
    if record_proof:
        report["proof_records"] = _record_proofs(report, output_dir)
    return report


def _hub_request(surface: dict[str, Any], *, model: str) -> HubRequest:
    payload = ToolCallPayload(
        system_prompt=(
            "You are the Back LLM in a production proof. Call resolve_situation exactly once. "
            "The user message contains resolver_tool_call_template.arguments. Your function "
            "arguments MUST be byte-for-byte semantically equal to that template: same "
            "contract_name, actor_scope, safety_context, request_frame, freshness_policy, "
            "prompt_budget, required_outputs, and feature_flags. Do not infer blanks from the "
            "schema. Do not supply resource_id, capability_name, binding_id, candidate_universe, "
            "policy verdicts, or resolver outputs. Do not answer in text."
        ),
        messages=[
            Message(
                role="user",
                content=json.dumps(_compact_surface_for_llm(surface), sort_keys=True),
            )
        ],
        tools=[
            ToolDefinition(
                name="resolve_situation",
                description=(
                    "Resolve the current Back task into a situated execution envelope. "
                    "Arguments must be copied exactly from resolver_tool_call_template.arguments "
                    "in the user message; locked fields must not be empty or changed."
                ),
                parameters=_resolve_situation_tool_schema(),
            )
        ],
        tool_choice="resolve_situation",
        parallel_tool_calls=False,
    )
    return HubRequest(
        capability=CapabilityType.TOOL_CALL,
        payload=payload,
        constraints=RequestConstraints(
            max_tokens=2048,
            timeout_ms=60000,
            priority=Priority.INTERACTIVE,
            temperature=0.0,
            model_preference=ModelPreference(preferred_provider="vertex", preferred_model=model),
            provider_preference="vertex",
            consumer_id="concierge.back.live_resolver_probe",
            reasoning_effort="low",
        ),
        trace_id="trace-m2b-live-back-resolver",
        request_id="req-m2b-live-back-resolver",
        session_id="session-m2b",
    )


def _compact_surface_for_llm(surface: dict[str, Any]) -> dict[str, Any]:
    template = make_resolver_tool_call(surface)
    return {
        "contract_name": surface["contract_name"],
        "schema_version": surface["schema_version"],
        "resolver_tool_name": surface["resolver_tool_name"],
        "resolver_tool_call_template": template,
        "request_frame_draft": surface["request_frame_draft"],
        "locked_fields": surface["locked_fields"],
        "allowed_llm_values": surface["allowed_llm_values"],
        "source_ledger": surface["source_ledger"],
        "llm_authoring_policy": surface["llm_authoring_policy"],
    }


def _resolve_situation_tool_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "contract_name": {
                "type": "string",
                "description": "Must be k1.fabric.resolve_situation_request.",
            },
            "schema_version": {"type": "integer"},
            "scenario_id": {"type": "string"},
            "request_frame": {
                "type": "object",
                "properties": {
                    "user_goal": {"type": "string"},
                    "semantic_refs": {"type": "array", "items": {"type": "string"}},
                    "operation_hints": {"type": "array", "items": {"type": "string"}},
                    "effect_hints": {"type": "array", "items": {"type": "string"}},
                    "resource_reference_hints": {"type": "array", "items": {"type": "string"}},
                    "people_reference_hints": {"type": "array", "items": {"type": "string"}},
                    "temporal_reference_hints": {"type": "array", "items": {"type": "string"}},
                    "constraints": {"type": "array", "items": {"type": "string"}},
                    "safety_context": {
                        "type": "object",
                        "description": (
                            "Copy exactly from locked_fields.safety_context and from "
                            "resolver_tool_call_template.arguments.request_frame.safety_context; "
                            "must match top-level safety_context."
                        ),
                        "properties": {
                            "source_field": {"type": "string"},
                            "source_value": {"type": "string"},
                            "mapping_confidence": {"type": "string"},
                        },
                        "required": ["source_field", "source_value", "mapping_confidence"],
                    },
                    "idempotency_key_seed": {"type": "string"},
                },
                "required": [
                    "user_goal",
                    "semantic_refs",
                    "operation_hints",
                    "effect_hints",
                    "safety_context",
                    "idempotency_key_seed",
                ],
            },
            "actor_scope": {
                "type": "object",
                "description": "Copy exactly from locked_fields.actor_scope; must not be empty.",
                "properties": {
                    "actor_ref": {"type": "string"},
                    "household_or_space_scope": {"type": "string"},
                    "caller_role": {"type": "string"},
                    "caller_face": {"type": "string"},
                    "side_effect_eligible": {"type": "boolean"},
                },
                "required": ["actor_ref", "household_or_space_scope", "caller_role"],
            },
            "safety_context": {
                "type": "object",
                "description": "Copy exactly from locked_fields.safety_context; must not be empty.",
                "properties": {
                    "source_field": {"type": "string"},
                    "source_value": {"type": "string"},
                    "mapping_confidence": {"type": "string"},
                },
                "required": ["source_field", "source_value", "mapping_confidence"],
            },
            "resolution_mode": {"type": "string", "description": "Use execution."},
            "freshness_policy": {
                "type": "object",
                "description": "Copy exactly from resolver_tool_call_template.arguments.freshness_policy.",
            },
            "prompt_budget": {
                "type": "object",
                "description": "Copy exactly from resolver_tool_call_template.arguments.prompt_budget.",
            },
            "previous_resolution_id": {"type": ["string", "null"]},
            "required_outputs": {"type": "array", "items": {"type": "string"}},
            "feature_flags": {"type": "array", "items": {"type": "string"}},
        },
        "required": [
            "contract_name",
            "schema_version",
            "request_frame",
            "actor_scope",
            "safety_context",
            "resolution_mode",
            "freshness_policy",
            "prompt_budget",
            "required_outputs",
            "feature_flags",
        ],
    }


def _first_tool_call(result: Any) -> dict[str, Any] | None:
    tool_calls = getattr(result, "tool_calls", None)
    if tool_calls is None and isinstance(result, ToolCallResultSet):
        tool_calls = result.tool_calls
    if not tool_calls:
        return None
    call = tool_calls[0]
    args = call.arguments
    try:
        parsed_args = json.loads(args) if isinstance(args, str) else dict(args)
    except Exception:
        parsed_args = {"_unparsed_arguments": str(args)}
    return {"id": call.id, "name": call.name, "arguments": parsed_args}


def _provider_tool_call_to_resolver_tool_call(
    provider_tool_call: dict[str, Any] | None,
) -> dict[str, Any]:
    if provider_tool_call is None:
        return {"tool_name": "", "arguments": {}}
    return {
        "tool_name": provider_tool_call.get("name") or "",
        "arguments": provider_tool_call.get("arguments") or {},
    }


def _provider_preflight() -> dict[str, Any]:
    provider = (os.environ.get("LLM_PROVIDER") or "").strip().lower()
    if not provider and os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        provider = "vertex"
    project = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GOOGLE_PROJECT_ID")
    has_api_key = bool(os.environ.get("GOOGLE_API_KEY"))
    has_adc = _has_adc_credentials()
    ready = provider in {"vertex", "vertex-ai", "vertex_ai", "google-cloud", "google_cloud"}
    ready = ready and bool(project) and (has_api_key or has_adc)
    return {
        "ready": ready,
        "provider": provider or "auto",
        "project_present": bool(project),
        "location": os.environ.get("GOOGLE_CLOUD_LOCATION")
        or os.environ.get("GOOGLE_LOCATION")
        or "global",
        "auth_mode": "api_key" if has_api_key else "adc" if has_adc else "missing",
    }


def _has_adc_credentials() -> bool:
    try:
        import google.auth

        google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        return True
    except Exception:
        return False


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


def _record_proofs(report: dict[str, Any], output_dir: Path) -> list[dict[str, Any]]:
    writer = ProofRecordWriter(output_dir)
    record = proof_record_template(
        milestone_id="M2B",
        scenario_id="dentist_riley_5pm_live_llm",
        component="Back live LLM resolver authoring",
        seam="BackResolverPromptSurface to live resolve_situation tool call",
        producer="ModelHub Vertex provider",
        consumer="Back resolver tool-call validator",
        trace_id="trace-m2b-live-back-resolver",
        request_id="req-m2b-live-back-resolver",
        task_id="task-dentist-riley-5pm-001",
        input_ref="probe_back_resolver_live_llm:prompt_surface",
        output_ref="probe_back_resolver_live_llm:provider_tool_call",
        verdict="pass" if report.get("verdict") == "pass" else "blocked",
        feature_flags=["back.use_resolver_prompt_surface_v1", "back.live_llm_resolver_probe"],
        assertions=[key for key, value in report.get("checks", {}).items() if value],
    )
    record["provider_id"] = report.get("provider_id")
    record["model_id"] = report.get("model_id")
    record["token_usage"] = report.get("token_usage")
    return [writer.write(record).to_dict()]


def _targeted_command(model: str) -> str:
    return (
        "python scripts\\probe_back_resolver_live_llm.py --scenario dentist_riley_5pm "
        f"--model {model} --live --json --record-proof"
    )


async def _amain() -> int:
    args = _parse_args()
    report = await run_probe(
        live=args.live,
        model=args.model,
        record_proof=args.record_proof,
        output_dir=args.output_dir,
    )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
    else:
        print(f"M2B live Back resolver LLM verdict: {report['verdict']}")
    return 0 if report["verdict"] in {"pass", "skipped"} else 1


def main() -> int:
    return asyncio.run(_amain())


if __name__ == "__main__":
    raise SystemExit(main())
