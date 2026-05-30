"""Probe M3 ResolveResourcesRequest -> ResourceUniverse behavior."""

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

from poc.back_tool_contract.proof import ProofRecordWriter, proof_record_template
from poc.back_tool_contract.resource_projection import (
    make_resolve_resources_request,
    resolve_resources,
    validate_resource_universe,
)

DEFAULT_REFS = "Riley's calendar,my car,living room lights"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refs", default=DEFAULT_REFS, help="Comma-separated resource refs.")
    parser.add_argument("--json", action="store_true", help="Emit JSON report.")
    parser.add_argument(
        "--record-proof", action="store_true", help="Write M3 ProofRecord artifacts."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "tmp" / "back_tool_contract" / "m3_resource_projection",
        help="Directory for optional proof artifacts.",
    )
    return parser.parse_args()


def _refs(raw: str) -> list[str]:
    values = [item.strip() for item in raw.split(",") if item.strip()]
    if not values:
        raise SystemExit("At least one --refs value is required.")
    return values


def run_probe(refs: list[str], *, record_proof: bool, output_dir: Path) -> dict[str, Any]:
    request = make_resolve_resources_request(
        refs=refs,
        actor_scope={
            "actor_ref": "back",
            "caller_role": "guardian",
            "household_or_space_scope": "household:demo",
        },
        resource_kind_hints=["calendar", "vehicle", "lighting_device", "room"],
        operation_hints=["create_event", "warmup", "turn_off"],
    )
    universe = resolve_resources(request)
    validation = validate_resource_universe(universe)
    repeated_universe = resolve_resources(request)
    delta_request = copy.deepcopy(request)
    delta_request["projection_delta_rev"] = "delta-001"
    delta_universe = resolve_resources(delta_request)

    checks = {
        "validation_accepted": validation["accepted"],
        "known_native_reference_concrete": _has_resource(universe, "calendar:family:riley"),
        "scope_proof_present": bool(universe.get("scope_proof")),
        "unknown_or_unconnected_explicit": bool(universe.get("ambiguous_references"))
        or bool(universe.get("unavailable_resources")),
        "partial_projection_blocking_omission": any(
            item.get("severity") == "blocking" and item.get("resource_type") == "lighting_device"
            for item in universe.get("omissions", [])
        ),
        "projection_version_stable": universe["projection_version"]
        == repeated_universe["projection_version"],
        "projection_version_changes_after_delta": universe["projection_version"]
        != delta_universe["projection_version"],
        "display_cards_safe": not validate_resource_universe(universe)["rejected_fields"],
    }
    failure_drills = _failure_drills(universe)
    report: dict[str, Any] = {
        "milestone": "M3",
        "targeted_command": (
            "python scripts\\probe_resource_projection.py --refs "
            '"Riley\'s calendar,my car,living room lights" --json --record-proof'
        ),
        "request": request,
        "resource_universe": universe,
        "validation": validation,
        "delta_projection_version": delta_universe["projection_version"],
        "failure_drills": failure_drills,
        "checks": {
            **checks,
            "failure_drills_pass": all(
                item["expected_failure_observed"] for item in failure_drills.values()
            ),
        },
    }
    report["verdict"] = "pass" if all(report["checks"].values()) else "fail"
    if record_proof:
        report["proof_records"] = _record_proofs(report, output_dir)
    return report


def _has_resource(universe: dict[str, Any], resource_id: str) -> bool:
    return any(item.get("resource_id") == resource_id for item in universe.get("resources", []))


def _failure_drills(universe: dict[str, Any]) -> dict[str, Any]:
    resources = universe.get("resources") or []

    f31 = copy.deepcopy(universe)
    f31["resources"][0]["resource_id"] = "connector:k1_native_family"
    f31_validation = validate_resource_universe(f31)

    f32 = copy.deepcopy(universe)
    f32["resources"] = []
    f32["unavailable_resources"] = []
    f32["ambiguous_references"] = []
    f32["omissions"] = []
    f32["exclusions"] = []
    f32["completeness"] = "complete"
    f32_validation = validate_resource_universe(f32)

    f33 = copy.deepcopy(universe)
    if resources:
        f33["resources"][0].pop("freshness", None)
    f33_validation = validate_resource_universe(f33)

    f34 = copy.deepcopy(universe)
    f34["scope_proof"]["connected_unavailable_resource_refs"] = ["vehicle:family:alex_model_y"]
    f34["unavailable_resources"] = []
    f34_validation = validate_resource_universe(f34)

    return {
        "F3.1_resource_id_equals_connector_id": _failure_result(f31_validation),
        "F3.2_unknown_reference_empty_complete_universe": _failure_result(f32_validation),
        "F3.3_side_effect_freshness_omitted": _failure_result(f33_validation),
        "F3.4_unavailable_connected_resource_hidden": _failure_result(f34_validation),
    }


def _failure_result(validation: dict[str, Any]) -> dict[str, Any]:
    return {"validation": validation, "expected_failure_observed": not validation["accepted"]}


def _record_proofs(report: dict[str, Any], output_dir: Path) -> list[dict[str, Any]]:
    writer = ProofRecordWriter(output_dir)
    proof = proof_record_template(
        milestone_id="M3",
        scenario_id="resource_projection_refs",
        component="Local-world resource projection",
        seam="ResolveResourcesRequest to ResourceUniverse",
        producer="Fabric Situated Resolver",
        consumer="Resource projection POC",
        trace_id="trace-m3-resource-projection",
        request_id="req-m3-resource-projection",
        input_ref="probe_resource_projection:request",
        output_ref="probe_resource_projection:resource_universe",
        feature_flags=["resolver.use_resource_projection_v1"],
        assertions=[key for key, value in report["checks"].items() if value],
    )
    proof["resource_universe_id"] = report["resource_universe"]["universe_id"]
    proof["projection_version"] = report["resource_universe"]["projection_version"]
    failure_proof = proof_record_template(
        milestone_id="M3",
        scenario_id="F3_failure_drills",
        component="Local-world resource projection",
        seam="ResourceUniverse validation",
        producer="M3 probe",
        consumer="whiteboard promotion gate",
        trace_id="trace-m3-failure-drills",
        request_id="req-m3-failure-drills",
        input_ref="probe_resource_projection:failure_drills:mutated_universes",
        output_ref="probe_resource_projection:failure_drills:rejected_fields",
        verdict="blocked",
        feature_flags=["resolver.use_resource_projection_v1"],
        assertions=[
            key
            for key, item in report["failure_drills"].items()
            if item["expected_failure_observed"]
        ],
    )
    failure_proof["first_failure_code"] = "resource_universe_validation_rejected"
    return [writer.write(proof).to_dict(), writer.write(failure_proof).to_dict()]


def main() -> int:
    args = _parse_args()
    report = run_probe(_refs(args.refs), record_proof=args.record_proof, output_dir=args.output_dir)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"M3 resource_projection verdict: {report['verdict']}")
    return 0 if report["verdict"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
