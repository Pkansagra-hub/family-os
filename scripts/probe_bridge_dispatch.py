"""Probe M7 ConnectorDispatchRequest -> ConnectorDispatchObservation behavior."""

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
    ContractFixtureConnectorGateway,
    make_connector_dispatch_request,
    validate_connector_dispatch_observation,
)
from poc.back_tool_contract.proof import ProofRecordWriter, proof_record_template
from scripts.probe_invoke_by_binding import _binding_bundle, _params

SCENARIOS = ("calendar_contract_fixture", "rate_limit", "credential_missing")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenarios", default=",".join(SCENARIOS))
    parser.add_argument("--json", action="store_true", help="Emit JSON report.")
    parser.add_argument(
        "--record-proof", action="store_true", help="Write M7 ProofRecord artifacts."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "tmp" / "back_tool_contract" / "m7_bridge_dispatch",
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
    scenarios: list[str], *, record_proof: bool, output_dir: Path
) -> dict[str, Any]:
    bundle = _binding_bundle()
    binding = bundle["bindings"][0]
    scenario_reports: dict[str, Any] = {}
    for scenario_id in scenarios:
        request = _request_for_scenario(scenario_id, binding)
        gateway = _gateway_for_scenario(scenario_id)
        observation = await gateway.dispatch(request)
        validation = validate_connector_dispatch_observation(observation)
        scenario_reports[scenario_id] = {
            "request": request,
            "observation": observation,
            "validation": validation,
            "checks": _scenario_checks(scenario_id, observation, validation),
        }
        scenario_reports[scenario_id]["verdict"] = (
            "pass" if all(scenario_reports[scenario_id]["checks"].values()) else "fail"
        )

    semantics_probes = await _semantics_probes(binding)
    failure_drills = _failure_drills(scenario_reports)
    checks = {
        "all_scenarios_pass": all(item["verdict"] == "pass" for item in scenario_reports.values()),
        "failure_drills_pass": all(
            item["expected_failure_observed"] for item in failure_drills.values()
        ),
        "circuit_open_normalized": semantics_probes["circuit_open"]["checks"][
            "circuit_open_normalized"
        ],
        "no_secret_boundary": all(
            item["validation"]["accepted"] for item in scenario_reports.values()
        ),
    }
    report: dict[str, Any] = {
        "milestone": "M7",
        "targeted_command": (
            "python scripts\\probe_bridge_dispatch.py --scenarios "
            "calendar_contract_fixture,rate_limit,credential_missing --json --record-proof"
        ),
        "binding_bundle_ref": bundle["binding_bundle_id"],
        "scenarios": scenario_reports,
        "semantics_probes": semantics_probes,
        "failure_drills": failure_drills,
        "checks": checks,
        "verdict": "pass" if all(checks.values()) else "fail",
    }
    if record_proof:
        report["proof_records"] = _record_proofs(report, output_dir)
    return report


def _request_for_scenario(scenario_id: str, binding: dict[str, Any]) -> dict[str, Any]:
    return make_connector_dispatch_request(
        trace_id=f"trace-m7-{scenario_id}",
        request_id=f"req-m7-{scenario_id}",
        invocation_id=f"invocation-m7-{scenario_id}",
        connector_id="connector.familyos.calendar",
        adapter_id="calendar_local",
        resource_id=str(binding["resource_id"]),
        capability_name=str(binding["capability_name"]),
        operation=str(binding["effect_summary"]["operation"]),
        params=_params(include_end=True),
        actor_ref="u1",
        actor_scope={
            "actor_ref": "back",
            "caller_role": "guardian",
            "household_or_space_scope": "household:demo",
        },
        safety_context={
            "source_field": "safety_band",
            "source_value": "GREEN",
            "mapping_confidence": "direct",
        },
        policy_gate_refs=["calendar.write.actor_scope", "calendar.write.fresh_conflict_window"],
        idempotency_key=f"idem-m7-{scenario_id}",
        timeout_ms=5000,
        verifier_requested=True,
        expected_effect="write",
        queueable=False,
    )


def _gateway_for_scenario(scenario_id: str) -> ContractFixtureConnectorGateway:
    if scenario_id == "rate_limit":
        return ContractFixtureConnectorGateway(force_rate_limit=True)
    if scenario_id == "credential_missing":
        return ContractFixtureConnectorGateway(credentials_present=False)
    return ContractFixtureConnectorGateway()


async def _semantics_probes(binding: dict[str, Any]) -> dict[str, Any]:
    request = _request_for_scenario("circuit_open", binding)
    gateway = ContractFixtureConnectorGateway(circuit_open=True)
    observation = await gateway.dispatch(request)
    validation = validate_connector_dispatch_observation(observation)
    return {
        "circuit_open": {
            "request": request,
            "observation": observation,
            "validation": validation,
            "checks": {
                "validation_accepted": validation["accepted"],
                "circuit_open_normalized": observation["status"] == "unavailable"
                and observation.get("error_code") == "circuit_open"
                and not observation["audit_receipt"].get("ifl_dispatch_attempted"),
                "recovery_present": (observation.get("recovery_directive") or {}).get("action")
                == "retry_later",
            },
        }
    }


def _scenario_checks(
    scenario_id: str, observation: dict[str, Any], validation: dict[str, Any]
) -> dict[str, bool]:
    audit = observation.get("audit_receipt") or {}
    if scenario_id == "calendar_contract_fixture":
        return {
            "validation_accepted": validation["accepted"],
            "status_success": observation["status"] == "success",
            "bridge_route_owned": audit.get("route_decision_source") == "bridge",
            "projection_delta_present": bool(observation.get("projection_delta")),
            "verifier_passed": (observation.get("verifier_result") or {}).get("status") == "passed",
        }
    if scenario_id == "rate_limit":
        return {
            "validation_accepted": validation["accepted"],
            "status_retryable": observation["status"] == "retryable",
            "retry_after_present": bool(observation.get("retry_after")),
            "no_ifl_dispatch": audit.get("ifl_dispatch_attempted") is False,
            "rate_limit_normalized": observation.get("error_code") == "rate_limited",
        }
    return {
        "validation_accepted": validation["accepted"],
        "status_unavailable": observation["status"] == "unavailable",
        "credential_missing_normalized": observation.get("error_code") == "credential_missing",
        "no_ifl_dispatch": audit.get("ifl_dispatch_attempted") is False,
        "safe_summary": "secret" not in str(observation.get("error_summary") or "").lower(),
    }


def _failure_drills(scenario_reports: dict[str, Any]) -> dict[str, Any]:
    success = copy.deepcopy(scenario_reports["calendar_contract_fixture"]["observation"])
    rate_limit = copy.deepcopy(scenario_reports["rate_limit"]["observation"])

    secret_leak = copy.deepcopy(success)
    secret_leak["audit_receipt"]["refresh_token"] = "Bearer bridge-owned-refresh-token"
    secret_validation = validate_connector_dispatch_observation(secret_leak)

    raw_rate_limit = copy.deepcopy(rate_limit)
    raw_rate_limit["status"] = "failed"
    raw_rate_limit["error_code"] = "provider_error"
    raw_rate_limit["error_summary"] = "Raw provider 429 Too Many Requests"
    raw_rate_limit["audit_receipt"]["ifl_dispatch_attempted"] = True
    raw_rate_limit_validation = validate_connector_dispatch_observation(raw_rate_limit)

    queued_nonqueueable = copy.deepcopy(success)
    queued_nonqueueable["status"] = "queued"
    queued_nonqueueable["audit_receipt"]["queue"]["permitted"] = False
    queued_nonqueueable_validation = validate_connector_dispatch_observation(queued_nonqueueable)

    back_route = copy.deepcopy(success)
    back_route["audit_receipt"]["route_decision_source"] = "back"
    back_route["audit_receipt"]["adapter_route_selected_by"] = "back"
    back_route["recovery_directive"] = {"action": "ask_back_for_adapter_route"}
    back_route_validation = validate_connector_dispatch_observation(back_route)

    return {
        "F7.1_secret_material_crosses_to_fabric": _failure_result(secret_validation),
        "F7.2_rate_limit_becomes_provider_raw_error": _failure_result(raw_rate_limit_validation),
        "F7.3_queued_status_for_nonqueueable_side_effect": _failure_result(
            queued_nonqueueable_validation
        ),
        "F7.4_bridge_asks_back_for_adapter_route": _failure_result(back_route_validation),
    }


def _failure_result(validation: dict[str, Any]) -> dict[str, Any]:
    return {"validation": validation, "expected_failure_observed": not validation["accepted"]}


def _record_proofs(report: dict[str, Any], output_dir: Path) -> list[dict[str, Any]]:
    writer = ProofRecordWriter(output_dir)
    observations: list[dict[str, Any]] = []
    for scenario_id, scenario_report in report["scenarios"].items():
        observation = scenario_report["observation"]
        proof = proof_record_template(
            milestone_id="M7",
            scenario_id=scenario_id,
            component="Bridge ConnectorGateway",
            seam="ConnectorDispatchRequest to ConnectorDispatchObservation",
            producer="Fabric invocation runtime",
            consumer="Bridge ConnectorGateway POC",
            trace_id=f"trace-m7-{scenario_id}",
            request_id=f"req-m7-{scenario_id}",
            input_ref=f"probe_bridge_dispatch:{scenario_id}:connector_dispatch_request",
            output_ref=f"probe_bridge_dispatch:{scenario_id}:connector_dispatch_observation",
            feature_flags=["bridge.connector_dispatch_v1"],
            assertions=[key for key, value in scenario_report["checks"].items() if value],
        )
        proof["bridge_request_id"] = observation["bridge_request_id"]
        proof["connector_id"] = observation["connector_id"]
        observations.append(writer.write(proof).to_dict())
    failure_proof = proof_record_template(
        milestone_id="M7",
        scenario_id="F7_failure_drills",
        component="Bridge ConnectorGateway",
        seam="ConnectorDispatchObservation validation",
        producer="M7 probe",
        consumer="whiteboard promotion gate",
        trace_id="trace-m7-failure-drills",
        request_id="req-m7-failure-drills",
        input_ref="probe_bridge_dispatch:failure_drills:mutated_observations",
        output_ref="probe_bridge_dispatch:failure_drills:rejected_fields",
        verdict="blocked",
        feature_flags=["bridge.connector_dispatch_v1"],
        assertions=[
            key
            for key, item in report["failure_drills"].items()
            if item["expected_failure_observed"]
        ],
    )
    failure_proof["first_failure_code"] = "connector_dispatch_validation_rejected"
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
        print(f"M7 bridge_dispatch verdict: {report['verdict']}")
    return 0 if report["verdict"] == "pass" else 1


def main() -> int:
    import asyncio

    return asyncio.run(_amain())


if __name__ == "__main__":
    raise SystemExit(main())
