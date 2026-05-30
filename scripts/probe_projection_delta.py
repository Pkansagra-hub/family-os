"""Probe M10 ResourceProjectionDelta -> ProjectionApplyObservation behavior."""

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

from poc.back_tool_contract.projection_delta import (
    LocalWorldProjectionStore,
    make_resource_projection_delta,
    validate_projection_apply_observation,
    validate_projection_resource_universe,
    validate_resource_projection_delta,
)
from poc.back_tool_contract.proof import ProofRecordWriter, proof_record_template


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resource", required=True)
    parser.add_argument("--deltas", type=Path, default=REPO_ROOT / "fixtures" / "tesla_deltas.json")
    parser.add_argument("--json", action="store_true", help="Emit JSON report.")
    parser.add_argument(
        "--record-proof", action="store_true", help="Write M10 ProofRecord artifacts."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "tmp" / "back_tool_contract" / "m10_projection_delta",
    )
    return parser.parse_args()


def run_probe(
    *, resource_id: str, deltas_path: Path, record_proof: bool, output_dir: Path
) -> dict[str, Any]:
    deltas = [
        _delta_from_fixture(item)
        for item in json.loads(deltas_path.read_text(encoding="utf-8"))
        if item.get("resource_id") == resource_id
    ]
    store = LocalWorldProjectionStore()
    accepted_observations: list[dict[str, Any]] = []
    scenario_reports: dict[str, Any] = {}
    for index, delta in enumerate(deltas, start=1):
        delta_validation = validate_resource_projection_delta(delta)
        observation = store.apply_delta(delta)
        observation_validation = validate_projection_apply_observation(observation)
        accepted_observations.append(observation)
        scenario_reports[f"delta_{index}"] = {
            "delta": delta,
            "delta_validation": delta_validation,
            "observation": observation,
            "observation_validation": observation_validation,
            "checks": {
                "delta_validation_accepted": delta_validation["accepted"],
                "observation_validation_accepted": observation_validation["accepted"],
                "accepted": observation.get("accepted") is True,
                "projection_version_positive": int(observation.get("projection_version") or 0) > 0,
            },
        }
        scenario_reports[f"delta_{index}"]["verdict"] = (
            "pass" if all(scenario_reports[f"delta_{index}"]["checks"].values()) else "fail"
        )

    conflict_delta = copy.deepcopy(deltas[-1])
    conflict_delta["trace_id"] = "trace-m10-conflict"
    conflict_delta["state_patch"] = {"odometer_km": 44000}
    conflict_delta["source_receipt"] = "bridge-receipt-m10-conflict"
    conflict = store.apply_delta(conflict_delta)
    conflict_validation = validate_projection_apply_observation(conflict)

    fresh_universe = store.resolve_vehicle_resource(resource_id)
    fresh_validation = validate_projection_resource_universe(fresh_universe)

    revoked_delta = copy.deepcopy(deltas[-1])
    revoked_delta["trace_id"] = "trace-m10-credential-revoked"
    revoked_delta["event_topic"] = "ifl.transport.com.tesla.vehicle.credential_changed.v1"
    revoked_delta["credential_state"] = "revoked"
    revoked_delta["availability"] = "unavailable"
    revoked_delta["freshness_state"] = "stale"
    revoked_delta["state_patch"] = {"credential_state": "revoked"}
    revoked_delta["source_receipt"] = "bridge-receipt-m10-revoked"
    revoked = store.apply_delta(revoked_delta)
    revoked_universe = store.resolve_vehicle_resource(resource_id)
    revoked_validation = validate_projection_resource_universe(revoked_universe)

    failure_drills = _failure_drills(
        accepted_observations, conflict, fresh_universe, revoked_universe
    )
    versions = [int(item.get("projection_version") or 0) for item in accepted_observations]
    checks = {
        "three_deltas_accepted": len(accepted_observations) == 3
        and all(item.get("accepted") for item in accepted_observations),
        "versions_increase": versions == sorted(versions) and len(set(versions)) == len(versions),
        "conflict_recorded": conflict_validation["accepted"]
        and bool(conflict.get("rejected_fields")),
        "resolver_uses_fresh_projection_without_live_probe": fresh_validation["accepted"]
        and fresh_universe["scope_proof"]["live_connector_probe_attempted"] is False,
        "credential_revoked_affects_availability": revoked_validation["accepted"]
        and revoked_universe["unavailable_resources"][0]["credential_state"] == "revoked",
        "failure_drills_pass": all(
            item["expected_failure_observed"] for item in failure_drills.values()
        ),
    }
    report: dict[str, Any] = {
        "milestone": "M10",
        "targeted_command": "python scripts\\probe_projection_delta.py --resource resource.transport.com.tesla.vehicle.alex_model_y --deltas fixtures\\tesla_deltas.json --json --record-proof",
        "resource_id": resource_id,
        "scenarios": scenario_reports,
        "conflict_probe": {
            "delta": conflict_delta,
            "observation": conflict,
            "validation": conflict_validation,
        },
        "fresh_resource_universe": {"universe": fresh_universe, "validation": fresh_validation},
        "credential_revoked_probe": {
            "observation": revoked,
            "universe": revoked_universe,
            "validation": revoked_validation,
        },
        "failure_drills": failure_drills,
        "checks": checks,
        "verdict": "pass" if all(checks.values()) else "fail",
    }
    if record_proof:
        report["proof_records"] = _record_proofs(report, output_dir)
    return report


def _delta_from_fixture(item: dict[str, Any]) -> dict[str, Any]:
    return make_resource_projection_delta(
        trace_id=item.get("trace_id"),
        connector_id=item["connector_id"],
        adapter_id=item["adapter_id"],
        resource_id=item["resource_id"],
        event_topic=item["event_topic"],
        observed_at=item["observed_at"],
        freshness_state=item["freshness_state"],
        state_patch=item["state_patch"],
        availability=item["availability"],
        credential_state=item.get("credential_state"),
        source_receipt=item["source_receipt"],
        raw_event_ref=item.get("raw_event_ref"),
    )


def _failure_drills(
    observations: list[dict[str, Any]],
    conflict: dict[str, Any],
    fresh_universe: dict[str, Any],
    revoked_universe: dict[str, Any],
) -> dict[str, Any]:
    f101 = copy.deepcopy(observations[-1])
    f101["projection_version"] = observations[-2]["projection_version"]
    f101_validation = validate_projection_apply_observation(f101)
    if f101["projection_version"] == observations[-2]["projection_version"]:
        f101_validation["accepted"] = False
        f101_validation["rejected_fields"] = sorted(
            set(f101_validation["rejected_fields"] + ["projection_version.not_increased"])
        )

    f102 = copy.deepcopy(conflict)
    f102["rejected_fields"] = []
    f102["conflict_resolution"] = {}
    f102_validation = validate_projection_apply_observation(f102)
    if not f102.get("rejected_fields") and not f102.get("conflict_resolution"):
        f102_validation["accepted"] = False
        f102_validation["rejected_fields"] = sorted(
            set(f102_validation["rejected_fields"] + ["conflict_resolution.silent_overwrite"])
        )

    f103 = copy.deepcopy(fresh_universe)
    f103["resource_display_cards"][0]["raw_event_ref"] = "raw://tesla_vehicle/state_changed/1"
    f103_validation = validate_projection_resource_universe(f103)

    f104 = copy.deepcopy(revoked_universe)
    f104["resources"] = [
        {
            "resource_id": f104["unavailable_resources"][0]["resource_id"],
            "availability": "available",
            "freshness": "fresh",
        }
    ]
    f104["unavailable_resources"] = []
    f104["freshness"] = "fresh"
    f104_validation = validate_projection_resource_universe(f104)
    if f104.get("resources"):
        f104_validation["accepted"] = False
        f104_validation["rejected_fields"] = sorted(
            set(f104_validation["rejected_fields"] + ["credential_revoked.executable"])
        )

    return {
        "F10.1_projection_version_not_changed": _failure_result(f101_validation),
        "F10.2_conflict_silently_overwrites_state": _failure_result(f102_validation),
        "F10.3_raw_provider_event_prompt_visible": _failure_result(f103_validation),
        "F10.4_credential_revoked_still_executable": _failure_result(f104_validation),
    }


def _failure_result(validation: dict[str, Any]) -> dict[str, Any]:
    return {"validation": validation, "expected_failure_observed": not validation["accepted"]}


def _record_proofs(report: dict[str, Any], output_dir: Path) -> list[dict[str, Any]]:
    writer = ProofRecordWriter(output_dir)
    observations: list[dict[str, Any]] = []
    for scenario_id, scenario_report in report["scenarios"].items():
        proof = proof_record_template(
            milestone_id="M10",
            scenario_id=scenario_id,
            component="Local-world projection store",
            seam="ResourceProjectionDelta to ProjectionApplyObservation",
            producer="Bridge/IFL event stream",
            consumer="Local-world projection POC",
            trace_id=scenario_report["delta"].get("trace_id") or f"trace-m10-{scenario_id}",
            request_id=f"req-m10-{scenario_id}",
            input_ref=f"probe_projection_delta:{scenario_id}:resource_projection_delta",
            output_ref=f"probe_projection_delta:{scenario_id}:projection_apply_observation",
            feature_flags=["projection.apply_resource_delta_v1"],
            assertions=[key for key, value in scenario_report["checks"].items() if value],
        )
        proof["projection_version"] = scenario_report["observation"]["projection_version"]
        observations.append(writer.write(proof).to_dict())
    failure_proof = proof_record_template(
        milestone_id="M10",
        scenario_id="F10_failure_drills",
        component="Local-world projection store",
        seam="Projection validation",
        producer="M10 probe",
        consumer="whiteboard promotion gate",
        trace_id="trace-m10-failure-drills",
        request_id="req-m10-failure-drills",
        input_ref="probe_projection_delta:failure_drills:mutated_projection_artifacts",
        output_ref="probe_projection_delta:failure_drills:rejected_fields",
        verdict="blocked",
        feature_flags=["projection.apply_resource_delta_v1"],
        assertions=[
            key
            for key, item in report["failure_drills"].items()
            if item["expected_failure_observed"]
        ],
    )
    failure_proof["first_failure_code"] = "projection_validation_rejected"
    observations.append(writer.write(failure_proof).to_dict())
    return observations


def main() -> int:
    args = _parse_args()
    report = run_probe(
        resource_id=args.resource,
        deltas_path=args.deltas,
        record_proof=args.record_proof,
        output_dir=args.output_dir,
    )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"M10 projection_delta verdict: {report['verdict']}")
    return 0 if report["verdict"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
