"""Probe M4 PolicySelectionRequest -> PolicyBundle behavior."""

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

from poc.back_tool_contract.policy_selector import (
    make_policy_selection_request,
    select_policy,
    validate_policy_bundle,
)
from poc.back_tool_contract.proof import ProofRecordWriter, proof_record_template

SCENARIOS = ("calendar_green", "calendar_amber", "health_privacy")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenarios",
        default=",".join(SCENARIOS),
        help="Comma-separated scenarios: calendar_green,calendar_amber,health_privacy.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON report.")
    parser.add_argument(
        "--record-proof", action="store_true", help="Write M4 ProofRecord artifacts."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "tmp" / "back_tool_contract" / "m4_policy_selector",
        help="Directory for optional proof artifacts.",
    )
    return parser.parse_args()


def _scenario_ids(raw: str) -> list[str]:
    values = [item.strip() for item in raw.split(",") if item.strip()]
    unknown = sorted(set(values) - set(SCENARIOS))
    if unknown:
        raise SystemExit(f"Unknown scenario(s): {', '.join(unknown)}")
    return values


def _request_for_scenario(scenario_id: str) -> dict[str, Any]:
    actor_scope = {
        "actor_ref": "back",
        "caller_role": "guardian",
        "caller_face": "primary_user",
        "household_or_space_scope": "household:demo",
    }
    if scenario_id in {"calendar_green", "calendar_amber"}:
        safety = "GREEN" if scenario_id == "calendar_green" else "AMBER"
        return make_policy_selection_request(
            scenario_id=scenario_id,
            request_frame={"user_goal": "Create calendar event for Riley Monday 5pm"},
            actor_scope=actor_scope,
            candidate_resource_kinds=["calendar"],
            candidate_resource_refs=["calendar:family:riley"],
            operation_hints=["create_event"],
            effect_hints=["write", "side_effect"],
            safety_context={
                "source_field": "safety_band",
                "source_value": safety,
                "mapping_confidence": "compatibility",
            },
            known_freshness="fresh",
        )
    return make_policy_selection_request(
        scenario_id=scenario_id,
        request_frame={"user_goal": "How did Riley sleep last night?"},
        actor_scope=actor_scope,
        candidate_resource_kinds=["health"],
        candidate_resource_refs=["health:person:riley:sleep"],
        operation_hints=["read_sleep_summary"],
        effect_hints=["protected_read", "disclosure"],
        safety_context={
            "source_field": "safety_band",
            "source_value": "GREEN",
            "mapping_confidence": "direct",
        },
        known_freshness="unknown",
    )


def run_probe(scenarios: list[str], *, record_proof: bool, output_dir: Path) -> dict[str, Any]:
    scenario_reports: dict[str, Any] = {}
    for scenario_id in scenarios:
        request = _request_for_scenario(scenario_id)
        bundle = select_policy(request)
        validation = validate_policy_bundle(bundle)
        scenario_reports[scenario_id] = {
            "request": request,
            "policy_bundle": bundle,
            "validation": validation,
            "checks": _scenario_checks(scenario_id, bundle, validation),
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
        "calendar_green_amber_explicitly_differ": _calendar_green_amber_differ(scenario_reports),
    }
    report: dict[str, Any] = {
        "milestone": "M4",
        "targeted_command": (
            "python scripts\\probe_policy_selector.py --scenarios "
            "calendar_green,calendar_amber,health_privacy --json --record-proof"
        ),
        "scenarios": scenario_reports,
        "failure_drills": failure_drills,
        "checks": checks,
        "verdict": "pass" if all(checks.values()) else "fail",
    }
    if record_proof:
        report["proof_records"] = _record_proofs(report, output_dir)
    return report


def _scenario_checks(
    scenario_id: str, bundle: dict[str, Any], validation: dict[str, Any]
) -> dict[str, bool]:
    roles = set(bundle.get("required_roles") or [])
    cards = bundle.get("policy_cards") or []
    if scenario_id == "calendar_green":
        return {
            "validation_accepted": validation["accepted"],
            "required_roles_present": {"temporal_resolver", "writer", "verifier"}.issubset(roles),
            "verifier_present": bool(bundle.get("verifier_requirements")),
            "no_confirmation_required": not bundle.get("hil_triggers"),
            "policy_cards_present": bool(cards),
        }
    if scenario_id == "calendar_amber":
        return {
            "validation_accepted": validation["accepted"],
            "required_roles_present": {
                "temporal_resolver",
                "writer",
                "confirmation_collector",
            }.issubset(roles),
            "hil_or_gate_present": bool(bundle.get("hil_triggers"))
            or any(gate.get("gate_type") == "safety" for gate in bundle.get("gates", [])),
            "amber_mapping_visible": (bundle.get("safety_mapping_evidence") or {}).get("status")
            == "requires_hil",
            "policy_cards_present": bool(cards),
        }
    return {
        "validation_accepted": validation["accepted"],
        "privacy_checker_present": "privacy_checker" in roles,
        "privacy_requirements_present": bool(bundle.get("privacy_requirements")),
        "privacy_gate_present": any(
            gate.get("gate_type") in {"privacy", "disclosure"} for gate in bundle.get("gates", [])
        ),
        "policy_cards_present": bool(cards),
    }


def _calendar_green_amber_differ(scenario_reports: dict[str, Any]) -> bool:
    green = scenario_reports.get("calendar_green", {}).get("policy_bundle", {})
    amber = scenario_reports.get("calendar_amber", {}).get("policy_bundle", {})
    return bool(green and amber and green.get("hil_triggers") != amber.get("hil_triggers"))


def _failure_drills(scenario_reports: dict[str, Any]) -> dict[str, Any]:
    green = copy.deepcopy(scenario_reports["calendar_green"]["policy_bundle"])
    amber = copy.deepcopy(scenario_reports["calendar_amber"]["policy_bundle"])
    health = copy.deepcopy(scenario_reports["health_privacy"]["policy_bundle"])

    f41 = copy.deepcopy(green)
    f41["policy_cards"][0]["summary"] = "Policy should call tool.execute.calendar.create_event."
    f41_validation = validate_policy_bundle(f41)

    f42 = copy.deepcopy(green)
    f42["default_constitution_applied"] = True
    f42["required_roles"] = []
    f42["gates"] = []
    f42["policy_cards"] = []
    f42_validation = validate_policy_bundle(f42)

    f43 = copy.deepcopy(health)
    f43["privacy_requirements"] = []
    f43["gates"] = [gate for gate in f43["gates"] if gate.get("gate_type") != "privacy"]
    f43_validation = validate_policy_bundle(f43)

    f44 = copy.deepcopy(amber)
    f44["hil_triggers"] = []
    f44["gates"] = [gate for gate in f44["gates"] if gate.get("gate_type") != "safety"]
    f44["safety_mapping_evidence"] = {"source_value": "AMBER", "status": "hidden"}
    f44_validation = validate_policy_bundle(f44)

    return {
        "F4.1_provider_command_name_in_bundle": _failure_result(f41_validation),
        "F4.2_no_policy_match_empty_bundle": _failure_result(f42_validation),
        "F4.3_health_privacy_gate_missing": _failure_result(f43_validation),
        "F4.4_amber_green_conflict_hidden": _failure_result(f44_validation),
    }


def _failure_result(validation: dict[str, Any]) -> dict[str, Any]:
    return {"validation": validation, "expected_failure_observed": not validation["accepted"]}


def _record_proofs(report: dict[str, Any], output_dir: Path) -> list[dict[str, Any]]:
    writer = ProofRecordWriter(output_dir)
    observations: list[dict[str, Any]] = []
    for scenario_id, scenario_report in report["scenarios"].items():
        bundle = scenario_report["policy_bundle"]
        proof = proof_record_template(
            milestone_id="M4",
            scenario_id=scenario_id,
            component="Policy and guide selector",
            seam="PolicySelectionRequest to PolicyBundle",
            producer="Fabric Situated Resolver",
            consumer="Plane 2 policy selector POC",
            trace_id=f"trace-m4-{scenario_id}",
            request_id=f"req-m4-{scenario_id}",
            input_ref=f"probe_policy_selector:{scenario_id}:request",
            output_ref=f"probe_policy_selector:{scenario_id}:policy_bundle",
            feature_flags=["resolver.use_policy_selector_v1"],
            assertions=[key for key, value in scenario_report["checks"].items() if value],
        )
        proof["policy_bundle_id"] = bundle["policy_bundle_id"]
        observations.append(writer.write(proof).to_dict())
    failure_proof = proof_record_template(
        milestone_id="M4",
        scenario_id="F4_failure_drills",
        component="Policy and guide selector",
        seam="PolicyBundle validation",
        producer="M4 probe",
        consumer="whiteboard promotion gate",
        trace_id="trace-m4-failure-drills",
        request_id="req-m4-failure-drills",
        input_ref="probe_policy_selector:failure_drills:mutated_bundles",
        output_ref="probe_policy_selector:failure_drills:rejected_fields",
        verdict="blocked",
        feature_flags=["resolver.use_policy_selector_v1"],
        assertions=[
            key
            for key, item in report["failure_drills"].items()
            if item["expected_failure_observed"]
        ],
    )
    failure_proof["first_failure_code"] = "policy_bundle_validation_rejected"
    observations.append(writer.write(failure_proof).to_dict())
    return observations


def main() -> int:
    args = _parse_args()
    report = run_probe(
        _scenario_ids(args.scenarios), record_proof=args.record_proof, output_dir=args.output_dir
    )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"M4 policy_selector verdict: {report['verdict']}")
    return 0 if report["verdict"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
