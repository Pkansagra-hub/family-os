"""Probe M5 BindingRequest -> BindingBundle behavior."""

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
    DEFAULT_CORPUS_SIZE,
    bind_capabilities,
    build_capability_corpus,
    make_binding_request,
    validate_binding_bundle,
)
from poc.back_tool_contract.policy_selector import (
    make_policy_selection_request,
    select_policy,
)
from poc.back_tool_contract.proof import ProofRecordWriter, proof_record_template
from poc.back_tool_contract.resource_projection import (
    make_resolve_resources_request,
    resolve_resources,
)

SCENARIOS = ("calendar_event", "calendar_conflict_read", "vehicle_climate", "guidance_record")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenarios", default=",".join(SCENARIOS))
    parser.add_argument("--corpus-size", type=int, default=DEFAULT_CORPUS_SIZE)
    parser.add_argument("--json", action="store_true", help="Emit JSON report.")
    parser.add_argument(
        "--record-proof", action="store_true", help="Write M5 ProofRecord artifacts."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "tmp" / "back_tool_contract" / "m5_binder",
        help="Directory for optional proof artifacts.",
    )
    return parser.parse_args()


def _scenario_ids(raw: str) -> list[str]:
    values = [item.strip() for item in raw.split(",") if item.strip()]
    unknown = sorted(set(values) - set(SCENARIOS))
    if unknown:
        raise SystemExit(f"Unknown scenario(s): {', '.join(unknown)}")
    return values


def _binding_request_for_scenario(scenario_id: str) -> dict[str, Any]:
    actor_scope = {
        "actor_ref": "back",
        "caller_role": "guardian",
        "household_or_space_scope": "household:demo",
    }
    safety_context = {
        "source_field": "safety_band",
        "source_value": "GREEN",
        "mapping_confidence": "direct",
    }
    if scenario_id == "vehicle_climate":
        universe = resolve_resources(
            make_resolve_resources_request(
                refs=["my car"],
                actor_scope=actor_scope,
                resource_kind_hints=["vehicle"],
                operation_hints=["warmup"],
            )
        )
        return make_binding_request(
            scenario_id=scenario_id,
            request_frame={"user_goal": "Warm up my car"},
            resource_candidates=universe["resources"],
            unavailable_resources=universe["unavailable_resources"],
            required_roles=["vehicle_climate_writer"],
            operation_hints=["warmup", "vehicle_climate"],
            actor_scope=actor_scope,
            safety_context=safety_context,
            policy_bundle_ref="policy_bundle:vehicle_missing:v1",
        )

    universe = resolve_resources(
        make_resolve_resources_request(
            refs=["Riley's calendar"],
            actor_scope=actor_scope,
            resource_kind_hints=["calendar"],
            operation_hints=["create_event", "list_events"],
        )
    )
    policy = select_policy(
        make_policy_selection_request(
            scenario_id="calendar_green",
            request_frame={"user_goal": "Create calendar event for Riley Monday 5pm"},
            actor_scope=actor_scope,
            candidate_resource_kinds=["calendar"],
            candidate_resource_refs=["calendar:family:riley"],
            operation_hints=["create_event"],
            effect_hints=["write", "side_effect"],
            safety_context=safety_context,
            known_freshness="fresh",
        )
    )
    role = "conflict_reader" if scenario_id == "calendar_conflict_read" else "writer"
    operation_hints = ["list_events"] if role == "conflict_reader" else ["create_event"]
    return make_binding_request(
        scenario_id=scenario_id,
        request_frame={"user_goal": "Create calendar event for Riley Monday 5pm"},
        resource_candidates=universe["resources"],
        required_roles=[role],
        operation_hints=operation_hints,
        actor_scope=actor_scope,
        safety_context=safety_context,
        policy_bundle_ref=policy["policy_bundle_id"],
        verifier_requirements=policy["verifier_requirements"] if role == "writer" else [],
        guide_selection_rules=policy["guide_selection_rules"],
    )


def run_probe(
    scenarios: list[str], *, corpus_size: int, record_proof: bool, output_dir: Path
) -> dict[str, Any]:
    corpus = build_capability_corpus(corpus_size)
    scenario_reports: dict[str, Any] = {}
    for scenario_id in scenarios:
        request = _binding_request_for_scenario(scenario_id)
        bundle = bind_capabilities(request, corpus)
        validation = validate_binding_bundle(bundle)
        repeated_bundle = bind_capabilities(request, corpus)
        scenario_reports[scenario_id] = {
            "request": request,
            "binding_bundle": bundle,
            "validation": validation,
            "checks": _scenario_checks(scenario_id, bundle, validation, repeated_bundle),
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
        "hundred_k_corpus_indexed": all(
            report["binding_bundle"]["corpus_stats"]["corpus_size"] >= 100000
            and report["binding_bundle"]["corpus_stats"].get("materialized_contracts", 0) >= 100000
            and report["binding_bundle"]["corpus_stats"].get("virtual_noise_records") == 0
            and report["binding_bundle"]["corpus_stats"]["records_examined"] <= 50
            for report in scenario_reports.values()
        ),
    }
    report: dict[str, Any] = {
        "milestone": "M5",
        "targeted_command": (
            "python scripts\\probe_binder.py --scenarios "
            "calendar_event,calendar_conflict_read,vehicle_climate,guidance_record --json --record-proof"
        ),
        "corpus_size": corpus_size,
        "scenarios": scenario_reports,
        "failure_drills": failure_drills,
        "checks": checks,
        "verdict": "pass" if all(checks.values()) else "fail",
    }
    if record_proof:
        report["proof_records"] = _record_proofs(report, output_dir)
    return report


def _scenario_checks(
    scenario_id: str,
    bundle: dict[str, Any],
    validation: dict[str, Any],
    repeated_bundle: dict[str, Any],
) -> dict[str, bool]:
    bindings = bundle.get("bindings") or []
    unbound = bundle.get("unbound_roles") or []
    if scenario_id == "calendar_event":
        binding = bindings[0] if bindings else {}
        repeated = (repeated_bundle.get("bindings") or [{}])[0]
        return {
            "validation_accepted": validation["accepted"],
            "writer_binding_present": binding.get("capability_name")
            == "tool.execute.calendar.create_event",
            "binding_id_stable": binding.get("binding_id") == repeated.get("binding_id"),
            "contract_version_present": bool(binding.get("contract_version")),
            "verifier_ref_present": bool(binding.get("verifier_ref")),
        }
    if scenario_id == "calendar_conflict_read":
        return {
            "validation_accepted": validation["accepted"],
            "reader_binding_present": any(
                item.get("capability_name") == "tool.read.calendar.list_events" for item in bindings
            ),
            "schema_refs_present": all(
                item.get("input_schema_ref") and item.get("output_schema_ref") for item in bindings
            ),
        }
    if scenario_id == "vehicle_climate":
        return {
            "validation_accepted": validation["accepted"],
            "unbound_role_present": any(
                item.get("role") == "vehicle_climate_writer"
                and item.get("reason") == "missing_capability"
                for item in unbound
            ),
            "no_vehicle_guess_binding": not bindings,
        }
    return {
        "validation_accepted": validation["accepted"],
        "guide_ref_present": "activity_profile:calendar_activity_v1"
        in bundle.get("guide_refs", []),
        "guide_not_binding": not any(
            "calendar_activity_v1" in str(item.get("capability_name")) for item in bindings
        ),
    }


def _failure_drills(scenario_reports: dict[str, Any]) -> dict[str, Any]:
    calendar = copy.deepcopy(scenario_reports["calendar_event"]["binding_bundle"])
    vehicle = copy.deepcopy(scenario_reports["vehicle_climate"]["binding_bundle"])

    f51 = copy.deepcopy(calendar)
    f51["bindings"].append(
        {
            "record_type": "capability_binding",
            "source_record_type": "activity_profile",
            "binding_id": "bad-guide-binding",
            "role": "writer",
            "capability_name": "calendar_activity_v1",
            "input_schema_ref": "schema:bad:input:v1",
            "output_schema_ref": "schema:bad:output:v1",
            "contract_version": "1.0.0",
        }
    )
    f51_validation = validate_binding_bundle(f51)

    f52 = copy.deepcopy(vehicle)
    f52["unbound_roles"] = []
    f52_validation = validate_binding_bundle(f52)

    f53 = copy.deepcopy(calendar)
    f53["bindings"][0]["input_schema_ref"] = ""
    f53_validation = validate_binding_bundle(f53)

    f54 = copy.deepcopy(calendar)
    f54["bindings"][0]["verifier_ref"] = None
    f54_validation = validate_binding_bundle(f54)

    return {
        "F5.1_activity_profile_becomes_binding": _failure_result(f51_validation),
        "F5.2_missing_vehicle_role_silently_omitted": _failure_result(f52_validation),
        "F5.3_binding_lacks_input_schema_ref": _failure_result(f53_validation),
        "F5.4_binding_lacks_required_verifier_ref": _failure_result(f54_validation),
    }


def _failure_result(validation: dict[str, Any]) -> dict[str, Any]:
    return {"validation": validation, "expected_failure_observed": not validation["accepted"]}


def _record_proofs(report: dict[str, Any], output_dir: Path) -> list[dict[str, Any]]:
    writer = ProofRecordWriter(output_dir)
    observations: list[dict[str, Any]] = []
    for scenario_id, scenario_report in report["scenarios"].items():
        bundle = scenario_report["binding_bundle"]
        proof = proof_record_template(
            milestone_id="M5",
            scenario_id=scenario_id,
            component="Capability contract binder",
            seam="BindingRequest to BindingBundle",
            producer="Fabric Situated Resolver",
            consumer="Capability contract registry POC",
            trace_id=f"trace-m5-{scenario_id}",
            request_id=f"req-m5-{scenario_id}",
            input_ref=f"probe_binder:{scenario_id}:binding_request",
            output_ref=f"probe_binder:{scenario_id}:binding_bundle",
            feature_flags=["resolver.use_binding_bundle_v1"],
            assertions=[key for key, value in scenario_report["checks"].items() if value],
        )
        proof["binding_bundle_id"] = bundle["binding_bundle_id"]
        proof["corpus_size"] = bundle["corpus_stats"]["corpus_size"]
        observations.append(writer.write(proof).to_dict())
    failure_proof = proof_record_template(
        milestone_id="M5",
        scenario_id="F5_failure_drills",
        component="Capability contract binder",
        seam="BindingBundle validation",
        producer="M5 probe",
        consumer="whiteboard promotion gate",
        trace_id="trace-m5-failure-drills",
        request_id="req-m5-failure-drills",
        input_ref="probe_binder:failure_drills:mutated_bundles",
        output_ref="probe_binder:failure_drills:rejected_fields",
        verdict="blocked",
        feature_flags=["resolver.use_binding_bundle_v1"],
        assertions=[
            key
            for key, item in report["failure_drills"].items()
            if item["expected_failure_observed"]
        ],
    )
    failure_proof["first_failure_code"] = "binding_bundle_validation_rejected"
    observations.append(writer.write(failure_proof).to_dict())
    return observations


def main() -> int:
    args = _parse_args()
    report = run_probe(
        _scenario_ids(args.scenarios),
        corpus_size=args.corpus_size,
        record_proof=args.record_proof,
        output_dir=args.output_dir,
    )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"M5 binder verdict: {report['verdict']}")
    return 0 if report["verdict"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
