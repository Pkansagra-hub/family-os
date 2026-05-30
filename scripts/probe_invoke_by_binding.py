"""Probe M6 InvocationRequest -> InvocationObservation behavior."""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from poc.back_tool_contract.capability_binder import (
    bind_capabilities,
    build_capability_corpus,
)
from poc.back_tool_contract.invocation_runtime import (
    NativeCalendarInvocationRuntime,
    make_invocation_request,
    validate_invocation_observation,
)
from poc.back_tool_contract.proof import ProofRecordWriter, proof_record_template
from scripts.probe_binder import _binding_request_for_scenario

SCENARIOS = ("green_ok", "duration_patch", "amber_band", "idempotent_replay")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenarios", default=",".join(SCENARIOS))
    parser.add_argument("--json", action="store_true", help="Emit JSON report.")
    parser.add_argument(
        "--record-proof", action="store_true", help="Write M6 ProofRecord artifacts."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "tmp" / "back_tool_contract" / "m6_invoke_by_binding",
        help="Directory for optional proof artifacts.",
    )
    return parser.parse_args()


def _scenario_ids(raw: str) -> list[str]:
    values = [item.strip() for item in raw.split(",") if item.strip()]
    unknown = sorted(set(values) - set(SCENARIOS))
    if unknown:
        raise SystemExit(f"Unknown scenario(s): {', '.join(unknown)}")
    return values


def _binding_bundle() -> dict[str, Any]:
    request = _binding_request_for_scenario("calendar_event")
    return bind_capabilities(request, build_capability_corpus())


def _params(*, include_end: bool = True) -> dict[str, Any]:
    params = {
        "title": "Dentist appointment",
        "start": "2026-06-01T17:00:00+00:00",
        "attendees": ["person:riley"],
        "visibility": "family",
    }
    if include_end:
        params["end"] = "2026-06-01T17:30:00+00:00"
    else:
        params["duration_minutes"] = 30
    return params


async def run_probe(
    scenarios: list[str], *, record_proof: bool, output_dir: Path
) -> dict[str, Any]:
    bundle = _binding_bundle()
    binding = bundle["bindings"][0]
    runtime = NativeCalendarInvocationRuntime(output_dir / "runtime")
    scenario_reports: dict[str, Any] = {}
    try:
        for scenario_id in scenarios:
            if scenario_id == "idempotent_replay":
                report = await _run_idempotent_replay(runtime, bundle, binding)
            else:
                request = _request_for_scenario(scenario_id, binding["binding_id"])
                observation = await runtime.invoke(request, bundle)
                validation = validate_invocation_observation(observation)
                report = {
                    "request": request,
                    "observation": observation,
                    "validation": validation,
                    "checks": _scenario_checks(scenario_id, observation, validation),
                }
            report["verdict"] = "pass" if all(report["checks"].values()) else "fail"
            scenario_reports[scenario_id] = report
    finally:
        runtime.close()

    failure_drills = _failure_drills(scenario_reports)
    checks = {
        "all_scenarios_pass": all(item["verdict"] == "pass" for item in scenario_reports.values()),
        "failure_drills_pass": all(
            item["expected_failure_observed"] for item in failure_drills.values()
        ),
        "invocation_does_not_access_corpus": all(
            not item["observation"]["audit_fields"].get("corpus_accessed")
            for item in scenario_reports.values()
        ),
    }
    report: dict[str, Any] = {
        "milestone": "M6",
        "targeted_command": (
            "python scripts\\probe_invoke_by_binding.py --scenarios "
            "green_ok,duration_patch,amber_band,idempotent_replay --json --record-proof"
        ),
        "binding_bundle_ref": bundle["binding_bundle_id"],
        "scenarios": scenario_reports,
        "failure_drills": failure_drills,
        "checks": checks,
        "verdict": "pass" if all(checks.values()) else "fail",
    }
    if record_proof:
        report["proof_records"] = _record_proofs(report, output_dir)
    return report


def _request_for_scenario(scenario_id: str, binding_id: str) -> dict[str, Any]:
    safety = "AMBER" if scenario_id == "amber_band" else "GREEN"
    return make_invocation_request(
        resolution_id=f"resolution-m6-{scenario_id}",
        binding_id=binding_id,
        params=_params(include_end=scenario_id != "duration_patch"),
        idempotency_key=f"idem-m6-{scenario_id}",
        actor_ref="u1",
        actor_role="parent",
        safety_context={
            "source_field": "safety_band",
            "source_value": safety,
            "mapping_confidence": "direct",
        },
        policy_gate_refs=["calendar.write.actor_scope", "calendar.write.fresh_conflict_window"],
        expected_effect="write",
        verifier_requested=True,
    )


async def _run_idempotent_replay(
    runtime: NativeCalendarInvocationRuntime, bundle: dict[str, Any], binding: dict[str, Any]
) -> dict[str, Any]:
    first_request = make_invocation_request(
        resolution_id="resolution-m6-idempotent-replay",
        binding_id=binding["binding_id"],
        params=_params(include_end=True),
        idempotency_key="idem-m6-replay-shared",
        actor_ref="u1",
        actor_role="parent",
        safety_context={
            "source_field": "safety_band",
            "source_value": "GREEN",
            "mapping_confidence": "direct",
        },
        policy_gate_refs=["calendar.write.actor_scope", "calendar.write.fresh_conflict_window"],
        expected_effect="write",
        verifier_requested=True,
    )
    first = await runtime.invoke(first_request, bundle)
    second_request = copy.deepcopy(first_request)
    second_request["previous_invocation_id"] = first["invocation_id"]
    second = await runtime.invoke(second_request, bundle)
    validation = validate_invocation_observation(second)
    return {
        "request": second_request,
        "first_observation": first,
        "observation": second,
        "validation": validation,
        "checks": _scenario_checks("idempotent_replay", second, validation, first),
    }


def _scenario_checks(
    scenario_id: str,
    observation: dict[str, Any],
    validation: dict[str, Any],
    first_observation: dict[str, Any] | None = None,
) -> dict[str, bool]:
    audit = observation.get("audit_fields") or {}
    if scenario_id == "green_ok":
        return {
            "validation_accepted": validation["accepted"],
            "status_success": observation["status"] == "success",
            "audit_fields_present": bool(audit.get("idempotency_key")),
            "verification_passed": (observation.get("verification_observation") or {}).get("status")
            == "passed",
            "submit_result_gate_ready": observation.get("submit_result_gate", {}).get(
                "completed_allowed"
            )
            is True,
        }
    if scenario_id == "duration_patch":
        recovery = observation.get("recovery_directive") or {}
        return {
            "validation_accepted": validation["accepted"],
            "status_retryable": observation["status"] == "retryable",
            "retry_patch_present": recovery.get("action") == "retry_with_params"
            and bool(recovery.get("suggested_params_patch")),
            "provider_not_dispatched": audit.get("provider_dispatch_attempted") is False,
        }
    if scenario_id == "amber_band":
        return {
            "validation_accepted": validation["accepted"],
            "status_denied": observation["status"] == "denied",
            "provider_not_dispatched": audit.get("provider_dispatch_attempted") is False,
            "band_mapping_consistent": observation.get("safety_mapping", {}).get("status")
            == "denied_before_provider",
        }
    return {
        "validation_accepted": validation["accepted"],
        "status_success": observation["status"] == "success",
        "idempotent_replay": audit.get("idempotent_replay") is True,
        "same_event_id": bool(first_observation)
        and observation.get("structured_result", {}).get("event_id")
        == first_observation.get("structured_result", {}).get("event_id"),
        "no_duplicate_write": audit.get("duplicate_write_detected") is False
        and audit.get("provider_write_attempted") is False,
    }


def _failure_drills(scenario_reports: dict[str, Any]) -> dict[str, Any]:
    duration = copy.deepcopy(scenario_reports["duration_patch"]["observation"])
    amber = copy.deepcopy(scenario_reports["amber_band"]["observation"])
    green = copy.deepcopy(scenario_reports["green_ok"]["observation"])
    replay = copy.deepcopy(scenario_reports["idempotent_replay"]["observation"])

    f61 = copy.deepcopy(duration)
    f61["status"] = "success"
    f61["provider_status"] = "ok"
    f61["audit_fields"]["provider_dispatch_attempted"] = True
    f61_validation = validate_invocation_observation(f61)

    f62 = copy.deepcopy(amber)
    f62["status"] = "failed"
    f62["provider_status"] = "band_denied"
    f62["safety_mapping"] = {"source_value": "AMBER", "status": "passed_fabric_failed_native"}
    f62_validation = validate_invocation_observation(f62)

    f63 = copy.deepcopy(green)
    f63["errors"] = [{"code": "provider_error", "message": 'Traceback File "provider.py", line 12'}]
    f63_validation = validate_invocation_observation(f63)

    f64 = copy.deepcopy(replay)
    f64["audit_fields"]["idempotent_replay"] = True
    f64["audit_fields"]["duplicate_write_detected"] = True
    f64_validation = validate_invocation_observation(f64)

    return {
        "F6.1_missing_end_dispatches_provider_write": _failure_result(f61_validation),
        "F6.2_contradictory_amber_band_semantics": _failure_result(f62_validation),
        "F6.3_provider_stack_visible_to_back": _failure_result(f63_validation),
        "F6.4_duplicate_idempotency_creates_duplicate_event": _failure_result(f64_validation),
    }


def _failure_result(validation: dict[str, Any]) -> dict[str, Any]:
    return {"validation": validation, "expected_failure_observed": not validation["accepted"]}


def _record_proofs(report: dict[str, Any], output_dir: Path) -> list[dict[str, Any]]:
    writer = ProofRecordWriter(output_dir)
    observations: list[dict[str, Any]] = []
    for scenario_id, scenario_report in report["scenarios"].items():
        observation = scenario_report["observation"]
        proof = proof_record_template(
            milestone_id="M6",
            scenario_id=scenario_id,
            component="Fabric invocation runtime",
            seam="InvocationRequest to InvocationObservation",
            producer="Back ReAct runtime",
            consumer="Fabric invocation POC",
            trace_id=f"trace-m6-{scenario_id}",
            request_id=f"req-m6-{scenario_id}",
            input_ref=f"probe_invoke_by_binding:{scenario_id}:invocation_request",
            output_ref=f"probe_invoke_by_binding:{scenario_id}:invocation_observation",
            feature_flags=["back.invoke_by_binding_v1"],
            assertions=[key for key, value in scenario_report["checks"].items() if value],
        )
        proof["invocation_id"] = observation["invocation_id"]
        proof["binding_id"] = observation["binding_id"]
        observations.append(writer.write(proof).to_dict())
    failure_proof = proof_record_template(
        milestone_id="M6",
        scenario_id="F6_failure_drills",
        component="Fabric invocation runtime",
        seam="InvocationObservation validation",
        producer="M6 probe",
        consumer="whiteboard promotion gate",
        trace_id="trace-m6-failure-drills",
        request_id="req-m6-failure-drills",
        input_ref="probe_invoke_by_binding:failure_drills:mutated_observations",
        output_ref="probe_invoke_by_binding:failure_drills:rejected_fields",
        verdict="blocked",
        feature_flags=["back.invoke_by_binding_v1"],
        assertions=[
            key
            for key, item in report["failure_drills"].items()
            if item["expected_failure_observed"]
        ],
    )
    failure_proof["first_failure_code"] = "invocation_observation_validation_rejected"
    observations.append(writer.write(failure_proof).to_dict())
    return observations


async def _amain() -> int:
    args = _parse_args()
    report = await run_probe(
        _scenario_ids(args.scenarios), record_proof=args.record_proof, output_dir=args.output_dir
    )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"M6 invoke_by_binding verdict: {report['verdict']}")
    return 0 if report["verdict"] == "pass" else 1


def main() -> int:
    import asyncio

    return asyncio.run(_amain())


if __name__ == "__main__":
    raise SystemExit(main())
