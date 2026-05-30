"""Probe M9 IFL manifest -> CapabilityRegistrationBatch behavior."""

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

from poc.back_tool_contract.manifest_registration import (
    load_ifl_manifest,
    register_ifl_manifest,
    validate_capability_registration_batch,
)
from poc.back_tool_contract.proof import ProofRecordWriter, proof_record_template

SCENARIOS = ("valid_manifest", "guidance_profile", "invalid_missing_identity")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest", type=Path, default=REPO_ROOT / "fixtures" / "manifest_tesla_like.json"
    )
    parser.add_argument("--scenarios", default=",".join(SCENARIOS))
    parser.add_argument("--json", action="store_true", help="Emit JSON report.")
    parser.add_argument(
        "--record-proof", action="store_true", help="Write M9 ProofRecord artifacts."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "tmp" / "back_tool_contract" / "m9_manifest_translator",
    )
    return parser.parse_args()


def _scenario_ids(raw: str) -> list[str]:
    values = [item.strip() for item in raw.split(",") if item.strip()]
    unknown = sorted(set(values) - set(SCENARIOS))
    if unknown:
        raise SystemExit(f"Unknown scenario(s): {', '.join(unknown)}")
    return values


def run_probe(
    *, manifest_path: Path, scenarios: list[str], record_proof: bool, output_dir: Path
) -> dict[str, Any]:
    base_manifest = load_ifl_manifest(manifest_path)
    scenario_reports: dict[str, Any] = {}
    for scenario_id in scenarios:
        manifest = _manifest_for_scenario(base_manifest, scenario_id)
        batch = register_ifl_manifest(manifest)
        validation = validate_capability_registration_batch(batch)
        scenario_reports[scenario_id] = {
            "manifest_ref": str(manifest_path),
            "manifest_id": manifest.get("manifest_id"),
            "registration_batch": batch,
            "validation": validation,
            "checks": _scenario_checks(scenario_id, batch, validation),
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
        "connector_identity_preserved": scenario_reports["valid_manifest"]["checks"][
            "connector_identity_preserved"
        ],
    }
    report: dict[str, Any] = {
        "milestone": "M9",
        "targeted_command": "python scripts\\probe_manifest_translator.py --manifest fixtures\\manifest_tesla_like.json --json --record-proof",
        "scenarios": scenario_reports,
        "failure_drills": failure_drills,
        "checks": checks,
        "verdict": "pass" if all(checks.values()) else "fail",
    }
    if record_proof:
        report["proof_records"] = _record_proofs(report, output_dir)
    return report


def _manifest_for_scenario(base: dict[str, Any], scenario_id: str) -> dict[str, Any]:
    manifest = copy.deepcopy(base)
    if scenario_id == "guidance_profile":
        manifest["capability_templates"] = [
            {
                "template_id": "vehicle.climate_guidance.v1",
                "record_type": "guide_card",
                "guide_ref": "guide.transport.com.tesla.climate_safety.v1",
                "summary": "Guidance only; not executable.",
            }
        ]
        manifest["guide_cards"] = [
            {
                "guide_ref": "guide.transport.com.tesla.climate_safety.v1",
                "record_type": "guide_card",
                "summary": "Confirm vehicle identity before climate actions.",
            }
        ]
    if scenario_id == "invalid_missing_identity":
        manifest["resource_models"][0]["identity_fields"] = []
    return manifest


def _scenario_checks(
    scenario_id: str, batch: dict[str, Any], validation: dict[str, Any]
) -> dict[str, bool]:
    contracts = batch.get("capability_contracts") or []
    models = batch.get("resource_model_contracts") or []
    routes = batch.get("provider_routes") or []
    connector_id = batch.get("connector_id")
    if scenario_id == "valid_manifest":
        return {
            "validation_accepted": validation["accepted"],
            "batch_accepted": batch.get("accepted") is True,
            "contracts_emitted": bool(contracts),
            "resource_models_emitted": bool(models),
            "provider_schemas_preserved": all(
                isinstance(item.get("input_schema"), dict)
                and isinstance(item.get("output_schema"), dict)
                and item.get("provider_schema_digest")
                for item in contracts
            ),
            "fabric_contract_shape_emitted": all(
                item.get("name") == item.get("capability_name")
                and item.get("provider_type") == "BRIDGE"
                and item.get("provider_id") == f"connector:{connector_id}"
                and item.get("resource_kind")
                for item in contracts
            ),
            "route_points_to_connector_adapter": all(
                route.get("connector_id") == connector_id
                and route.get("adapter_id") == batch.get("adapter_id")
                for route in routes
            ),
            "connector_identity_preserved": all(
                connector_id in item.get("capability_name", "") for item in contracts
            ),
            "verifier_preserved": any(
                item.get("verifier_ref") for item in contracts if item.get("effect_type") == "write"
            ),
        }
    if scenario_id == "guidance_profile":
        return {
            "validation_accepted": validation["accepted"],
            "guide_ref_present": "guide.transport.com.tesla.climate_safety.v1"
            in batch.get("guide_refs", []),
            "guide_not_executable": not contracts,
        }
    return {
        "validation_accepted": validation["accepted"],
        "batch_rejected": batch.get("accepted") is False,
        "blocking_diagnostic": any(
            item.get("severity") == "blocking" for item in batch.get("registration_diagnostics", [])
        ),
        "no_partial_executable_registration": not contracts,
    }


def _failure_drills(scenario_reports: dict[str, Any]) -> dict[str, Any]:
    valid = copy.deepcopy(scenario_reports["valid_manifest"]["registration_batch"])
    invalid = copy.deepcopy(scenario_reports["invalid_missing_identity"]["registration_batch"])

    f91 = copy.deepcopy(valid)
    f91["capability_contracts"][0]["capability_name"] = "tool.execute.vehicle.start_climate"
    f91_validation = validate_capability_registration_batch(f91)

    f92 = copy.deepcopy(valid)
    f92["capability_contracts"].append(
        {
            "record_type": "capability_contract",
            "source_record_type": "guide_card",
            "capability_name": "tool.execute.transport.com.tesla.climate_guidance",
            "effect_type": "write",
            "operation": "climate_guidance",
            "verifier_ref": "verifier.transport.com.tesla.climate_readback.v1",
        }
    )
    f92_validation = validate_capability_registration_batch(f92)

    f93 = copy.deepcopy(invalid)
    f93["accepted"] = False
    f93["capability_contracts"] = copy.deepcopy(valid["capability_contracts"][:1])
    f93_validation = validate_capability_registration_batch(f93)

    f94 = copy.deepcopy(valid)
    for contract in f94["capability_contracts"]:
        if contract.get("effect_type") == "write":
            contract["verifier_ref"] = None
    f94_validation = validate_capability_registration_batch(f94)

    f95 = copy.deepcopy(valid)
    f95["capability_contracts"][0].pop("input_schema", None)
    f95_validation = validate_capability_registration_batch(f95)

    return {
        "F9.1_connector_identity_lost": _failure_result(f91_validation),
        "F9.2_guide_profile_registered_executable": _failure_result(f92_validation),
        "F9.3_invalid_manifest_partially_registers_executable": _failure_result(f93_validation),
        "F9.4_verifier_affordance_dropped": _failure_result(f94_validation),
        "F9.5_provider_schema_dropped": _failure_result(f95_validation),
    }


def _failure_result(validation: dict[str, Any]) -> dict[str, Any]:
    return {"validation": validation, "expected_failure_observed": not validation["accepted"]}


def _record_proofs(report: dict[str, Any], output_dir: Path) -> list[dict[str, Any]]:
    writer = ProofRecordWriter(output_dir)
    observations: list[dict[str, Any]] = []
    for scenario_id, scenario_report in report["scenarios"].items():
        batch = scenario_report["registration_batch"]
        proof = proof_record_template(
            milestone_id="M9",
            scenario_id=scenario_id,
            component="ManifestTranslator",
            seam="IflManifest to CapabilityRegistrationBatch",
            producer="IFL manifest registry",
            consumer="Fabric capability registration POC",
            trace_id=f"trace-m9-{scenario_id}",
            request_id=f"req-m9-{scenario_id}",
            input_ref=f"probe_manifest_translator:{scenario_id}:ifl_manifest",
            output_ref=f"probe_manifest_translator:{scenario_id}:registration_batch",
            feature_flags=["fabric.register_ifl_manifest_batch_v1"],
            assertions=[key for key, value in scenario_report["checks"].items() if value],
        )
        proof["registration_batch_id"] = batch["registration_batch_id"]
        observations.append(writer.write(proof).to_dict())
    failure_proof = proof_record_template(
        milestone_id="M9",
        scenario_id="F9_failure_drills",
        component="ManifestTranslator",
        seam="CapabilityRegistrationBatch validation",
        producer="M9 probe",
        consumer="whiteboard promotion gate",
        trace_id="trace-m9-failure-drills",
        request_id="req-m9-failure-drills",
        input_ref="probe_manifest_translator:failure_drills:mutated_batches",
        output_ref="probe_manifest_translator:failure_drills:rejected_fields",
        verdict="blocked",
        feature_flags=["fabric.register_ifl_manifest_batch_v1"],
        assertions=[
            key
            for key, item in report["failure_drills"].items()
            if item["expected_failure_observed"]
        ],
    )
    failure_proof["first_failure_code"] = "registration_batch_validation_rejected"
    observations.append(writer.write(failure_proof).to_dict())
    return observations


def main() -> int:
    args = _parse_args()
    report = run_probe(
        manifest_path=args.manifest,
        scenarios=_scenario_ids(args.scenarios),
        record_proof=args.record_proof,
        output_dir=args.output_dir,
    )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"M9 manifest_translator verdict: {report['verdict']}")
    return 0 if report["verdict"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
