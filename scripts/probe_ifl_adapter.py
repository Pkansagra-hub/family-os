"""Probe M8 IflCommandEnvelope -> IflResultEnvelope behavior."""

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

from poc.back_tool_contract.connector_dispatch import (
    map_ifl_result_to_connector_observation,
    validate_connector_dispatch_observation,
)
from poc.back_tool_contract.ifl_adapter_runtime import (
    LocalCalendarIflAdapterRuntime,
    make_ifl_command_envelope,
    validate_ifl_command_envelope,
    validate_ifl_result_envelope,
)
from poc.back_tool_contract.proof import ProofRecordWriter, proof_record_template

SCENARIOS = ("create_event", "timeout", "provider_error")
ADAPTERS = ("calendar_local",)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adapter", choices=ADAPTERS, default="calendar_local")
    parser.add_argument("--scenarios", default=",".join(SCENARIOS))
    parser.add_argument("--json", action="store_true", help="Emit JSON report.")
    parser.add_argument(
        "--record-proof", action="store_true", help="Write M8 ProofRecord artifacts."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "tmp" / "back_tool_contract" / "m8_ifl_adapter",
        help="Directory for optional proof artifacts.",
    )
    return parser.parse_args()


def _scenario_ids(raw: str) -> list[str]:
    values = [item.strip() for item in raw.split(",") if item.strip()]
    unknown = sorted(set(values) - set(SCENARIOS))
    if unknown:
        raise SystemExit(f"Unknown scenario(s): {', '.join(unknown)}")
    return values


async def run_probe(
    adapter: str, scenarios: list[str], *, record_proof: bool, output_dir: Path
) -> dict[str, Any]:
    runtime = LocalCalendarIflAdapterRuntime()
    scenario_reports: dict[str, Any] = {}
    for scenario_id in scenarios:
        command = _command_for_scenario(adapter, scenario_id)
        command_validation = validate_ifl_command_envelope(command)
        result = await runtime.dispatch(command)
        result_validation = validate_ifl_result_envelope(result, command)
        bridge_observation = map_ifl_result_to_connector_observation(
            _connector_request_from_command(command),
            result,
            result_validation=result_validation,
        )
        bridge_validation = validate_connector_dispatch_observation(bridge_observation)
        scenario_reports[scenario_id] = {
            "command": command,
            "command_validation": command_validation,
            "result": result,
            "result_validation": result_validation,
            "bridge_mapping": {
                "observation": bridge_observation,
                "validation": bridge_validation,
            },
            "checks": _scenario_checks(
                scenario_id, command_validation, result, result_validation, bridge_validation
            ),
        }
        scenario_reports[scenario_id]["verdict"] = (
            "pass" if all(scenario_reports[scenario_id]["checks"].values()) else "fail"
        )

    failure_drills = _failure_drills(scenario_reports)
    checks = {
        "all_scenarios_pass": all(item["verdict"] == "pass" for item in scenario_reports.values()),
        "failure_drills_pass": all(
            item["expected_failure_observed"] for item in failure_drills.values()
        ),
        "all_results_map_to_bridge_status": all(
            item["bridge_mapping"]["validation"]["accepted"] for item in scenario_reports.values()
        ),
    }
    report: dict[str, Any] = {
        "milestone": "M8",
        "targeted_command": (
            "python scripts\\probe_ifl_adapter.py --adapter calendar_local --scenarios "
            "create_event,timeout,provider_error --json --record-proof"
        ),
        "adapter": adapter,
        "scenarios": scenario_reports,
        "failure_drills": failure_drills,
        "checks": checks,
        "verdict": "pass" if all(checks.values()) else "fail",
    }
    if record_proof:
        report["proof_records"] = _record_proofs(report, output_dir)
    return report


def _command_for_scenario(adapter: str, scenario_id: str) -> dict[str, Any]:
    params = {
        "title": "Dentist appointment",
        "start": "2026-06-01T17:00:00+00:00",
        "end": "2026-06-01T17:30:00+00:00",
        "attendees": ["person:riley"],
        "visibility": "family",
    }
    if scenario_id == "timeout":
        params["force_timeout"] = True
    if scenario_id == "provider_error":
        params["force_provider_error"] = True
    return make_ifl_command_envelope(
        trace_id=f"trace-m8-{scenario_id}",
        bridge_request_id=f"bridge-request-m8-{scenario_id}",
        manifest_id="manifest:calendar_local:v1",
        connector_id="connector.familyos.calendar",
        adapter_id=adapter,
        resource_ref="calendar:family:riley",
        action="create_event",
        params=params,
        auth_context_ref="authref:bridge-owned:calendar_local:v1",
        idempotency_key=f"idem-m8-{scenario_id}",
        timeout_ms=5000,
        expected_effect="write",
        readback_requested=True,
    )


def _connector_request_from_command(command: dict[str, Any]) -> dict[str, Any]:
    return {
        "bridge_request_id": command["bridge_request_id"],
        "trace_id": command["trace_id"],
        "request_id": f"req-{command['bridge_request_id']}",
        "invocation_id": f"invocation-{command['bridge_request_id']}",
        "connector_id": command["connector_id"],
        "adapter_id": command["adapter_id"],
        "resource_id": command["resource_ref"],
        "actor_ref": "u1",
        "queue_policy": {"queueable": False},
    }


def _scenario_checks(
    scenario_id: str,
    command_validation: dict[str, Any],
    result: dict[str, Any],
    result_validation: dict[str, Any],
    bridge_validation: dict[str, Any],
) -> dict[str, bool]:
    if scenario_id == "create_event":
        return {
            "command_validation_accepted": command_validation["accepted"],
            "result_validation_accepted": result_validation["accepted"],
            "status_success": result["status"] == "success",
            "normalized_payload_present": bool(result.get("normalized_payload")),
            "readback_payload_present": bool(result.get("readback_payload")),
            "bridge_mapping_accepted": bridge_validation["accepted"],
        }
    if scenario_id == "timeout":
        return {
            "command_validation_accepted": command_validation["accepted"],
            "result_validation_accepted": result_validation["accepted"],
            "status_retryable": result["status"] == "retryable",
            "retry_after_present": bool(result.get("retry_after")),
            "bridge_mapping_accepted": bridge_validation["accepted"],
        }
    return {
        "command_validation_accepted": command_validation["accepted"],
        "result_validation_accepted": result_validation["accepted"],
        "status_failed": result["status"] == "failed",
        "typed_error_code": result.get("error_code") == "provider_validation_failed",
        "safe_summary": "traceback" not in str(result.get("error_summary") or "").lower(),
        "bridge_mapping_accepted": bridge_validation["accepted"],
    }


def _failure_drills(scenario_reports: dict[str, Any]) -> dict[str, Any]:
    create_command = scenario_reports["create_event"]["command"]
    create_result = copy.deepcopy(scenario_reports["create_event"]["result"])
    provider_error = copy.deepcopy(scenario_reports["provider_error"]["result"])

    raw_stack = copy.deepcopy(provider_error)
    raw_stack["error_summary"] = 'Traceback File "provider.py", line 12: boom'
    raw_stack_validation = validate_ifl_result_envelope(raw_stack, create_command)

    raw_payload_inline = copy.deepcopy(create_result)
    raw_payload_inline["raw_payload"] = {"provider": "inline payload should stay behind raw ref"}
    raw_payload_inline_validation = validate_ifl_result_envelope(raw_payload_inline, create_command)

    missing_readback = copy.deepcopy(create_result)
    missing_readback["readback_payload"] = None
    missing_readback_validation = validate_ifl_result_envelope(missing_readback, create_command)

    unknown_status = copy.deepcopy(create_result)
    unknown_status["status"] = "mystery"
    unknown_status_validation = validate_ifl_result_envelope(unknown_status, create_command)

    return {
        "F8.1_raw_stack_in_error_summary": _failure_result(raw_stack_validation),
        "F8.2_inline_raw_provider_payload": _failure_result(raw_payload_inline_validation),
        "F8.3_readback_requested_ignored": _failure_result(missing_readback_validation),
        "F8.4_status_outside_vocabulary": _failure_result(unknown_status_validation),
    }


def _failure_result(validation: dict[str, Any]) -> dict[str, Any]:
    return {"validation": validation, "expected_failure_observed": not validation["accepted"]}


def _record_proofs(report: dict[str, Any], output_dir: Path) -> list[dict[str, Any]]:
    writer = ProofRecordWriter(output_dir)
    observations: list[dict[str, Any]] = []
    for scenario_id, scenario_report in report["scenarios"].items():
        result = scenario_report["result"]
        proof = proof_record_template(
            milestone_id="M8",
            scenario_id=scenario_id,
            component="IFL Adapter Runtime",
            seam="IflCommandEnvelope to IflResultEnvelope",
            producer="Bridge ConnectorGateway",
            consumer="Calendar local IFL adapter POC",
            trace_id=f"trace-m8-{scenario_id}",
            request_id=f"req-m8-{scenario_id}",
            input_ref=f"probe_ifl_adapter:{scenario_id}:ifl_command_envelope",
            output_ref=f"probe_ifl_adapter:{scenario_id}:ifl_result_envelope",
            feature_flags=["bridge.ifl_adapter_runtime_v1"],
            assertions=[key for key, value in scenario_report["checks"].items() if value],
        )
        proof["bridge_request_id"] = result["bridge_request_id"]
        proof["adapter_id"] = report["adapter"]
        observations.append(writer.write(proof).to_dict())
    failure_proof = proof_record_template(
        milestone_id="M8",
        scenario_id="F8_failure_drills",
        component="IFL Adapter Runtime",
        seam="IflResultEnvelope validation",
        producer="M8 probe",
        consumer="whiteboard promotion gate",
        trace_id="trace-m8-failure-drills",
        request_id="req-m8-failure-drills",
        input_ref="probe_ifl_adapter:failure_drills:mutated_results",
        output_ref="probe_ifl_adapter:failure_drills:rejected_fields",
        verdict="blocked",
        feature_flags=["bridge.ifl_adapter_runtime_v1"],
        assertions=[
            key
            for key, item in report["failure_drills"].items()
            if item["expected_failure_observed"]
        ],
    )
    failure_proof["first_failure_code"] = "ifl_result_validation_rejected"
    observations.append(writer.write(failure_proof).to_dict())
    return observations


async def _amain() -> int:
    args = _parse_args()
    report = await run_probe(
        args.adapter,
        _scenario_ids(args.scenarios),
        record_proof=args.record_proof,
        output_dir=args.output_dir,
    )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"M8 ifl_adapter verdict: {report['verdict']}")
    return 0 if report["verdict"] == "pass" else 1


def main() -> int:
    import asyncio

    return asyncio.run(_amain())


if __name__ == "__main__":
    raise SystemExit(main())
