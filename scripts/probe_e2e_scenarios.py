"""Probe M12 end-to-end Back tool contract scenarios."""

from __future__ import annotations

import argparse
import asyncio
import copy
import json
import os
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from poc.back_tool_contract.e2e_scenario_gate import (
    SCENARIOS,
    build_e2e_trace,
    prompt_payload_for_scenario,
    validate_e2e_trace,
)
from poc.back_tool_contract.live_provider import (
    call_live_submit_result,
    validation_prompt_record,
)
from poc.back_tool_contract.proof import ProofRecordWriter, proof_record_template


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenarios", default="P1,P2,P3,P4,P5,P6")
    parser.add_argument("--production-provider", action="store_true")
    parser.add_argument("--model", default=os.environ.get("VERTEX_MODEL") or "gemini-2.5-flash")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--record-proof", action="store_true")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "tmp" / "back_tool_contract" / "m12_e2e_scenarios",
    )
    return parser.parse_args()


async def run_probe(
    *,
    scenario_ids: list[str],
    production_provider: bool,
    model: str,
    record_proof: bool,
    output_dir: Path,
) -> dict[str, Any]:
    scenario_reports = {}
    validation_prompt_records: list[dict[str, Any]] = []
    proof_records: list[dict[str, Any]] = []
    writer = ProofRecordWriter(output_dir) if record_proof else None

    for scenario_id in scenario_ids:
        if production_provider:
            provider_result = await call_live_submit_result(
                prompt_payload=prompt_payload_for_scenario(scenario_id),
                model=model,
                trace_id=f"trace-m12-{scenario_id.lower()}-live-submit",
                request_id=f"req-m12-{scenario_id.lower()}-live-submit",
                session_id="session-m12",
                consumer_id="concierge.back.e2e_scenario_probe",
            )
        else:
            provider_result = {
                "live_provider_called": False,
                "verdict": "blocked",
                "blocked_reason": "Pass --production-provider to satisfy M12.",
            }
        trace = build_e2e_trace(scenario_id, provider_result)
        validation = validate_e2e_trace(trace)
        checks = {
            "trace_validation_accepted": validation["accepted"],
            "production_provider_passed": provider_result.get("verdict") == "pass",
            "mocked_llm_absent": not provider_result.get("llm_mock_used"),
        }
        scenario_reports[scenario_id] = {
            "trace": trace,
            "validation": validation,
            "checks": checks,
            "verdict": "pass" if all(checks.values()) else "fail",
        }
        if writer:
            proof_records.extend(_record_trace_proofs(writer, trace))
            vp = validation_prompt_record(
                milestone_id="M12",
                scenario_id=scenario_id,
                prompt_ref=f"probe_e2e_scenarios:{scenario_id}:final_iteration_prompt",
                provider_result=provider_result,
            )
            validation_prompt_records.append(writer.write_validation_prompt(vp).to_dict())

    failure_drills = _failure_drills(scenario_reports)
    if writer:
        proof_records.append(_record_failure_proof(writer, failure_drills))
    checks = {
        "all_requested_scenarios_present": set(scenario_reports) == set(scenario_ids),
        "all_scenario_traces_pass": all(
            item["verdict"] == "pass" for item in scenario_reports.values()
        ),
        "failure_drills_pass": all(
            item["expected_failure_observed"] for item in failure_drills.values()
        ),
        "validation_prompt_records_written": (not record_proof)
        or len(validation_prompt_records) == len(scenario_ids),
    }
    report: dict[str, Any] = {
        "milestone": "M12",
        "targeted_command": "python scripts\\probe_e2e_scenarios.py --scenarios P1,P2,P3,P4,P5,P6 --production-provider --json --record-proof",
        "scenario_ids": scenario_ids,
        "scenarios": scenario_reports,
        "failure_drills": failure_drills,
        "checks": checks,
        "verdict": "pass" if all(checks.values()) else "fail",
    }
    if record_proof:
        report["proof_records"] = proof_records
        report["validation_prompt_records"] = validation_prompt_records
    return report


def _failure_drills(scenario_reports: dict[str, Any]) -> dict[str, Any]:
    drills: dict[str, Any] = {}
    if "P1" in scenario_reports:
        p1 = copy.deepcopy(scenario_reports["P1"]["trace"])
        p1["proof_chain"] = [
            item for item in p1["proof_chain"] if item.get("contract") != "BindingBundle"
        ]
        drills["F12.1_missing_contract_chain"] = _failure_result(validate_e2e_trace(p1))

    if "P2" in scenario_reports:
        p2 = copy.deepcopy(scenario_reports["P2"]["trace"])
        p2["llm_provider_evidence"] = {
            "live_provider_called": False,
            "verdict": "pass",
            "llm_mock_used": True,
        }
        drills["F12.2_mocked_llm_in_production_provider_mode"] = _failure_result(
            validate_e2e_trace(p2)
        )

        p2_invoked = copy.deepcopy(scenario_reports["P2"]["trace"])
        p2_invoked["invocations"] = [
            {"operation": "invented_vehicle_start", "binding_id": "", "side_effect": True}
        ]
        drills["F12.3_missing_capability_invoked_anyway"] = _failure_result(
            validate_e2e_trace(p2_invoked)
        )

    if "P3" in scenario_reports:
        p3 = copy.deepcopy(scenario_reports["P3"]["trace"])
        p3["submit_result"]["authority_evidence_refs"] = []
        p3["submit_result"]["verification_evidence_refs"] = []
        drills["F12.4_completed_without_authority_or_verification"] = _failure_result(
            validate_e2e_trace(p3)
        )

    if "P4" in scenario_reports:
        p4 = copy.deepcopy(scenario_reports["P4"]["trace"])
        p4["hil_choices"][0]["source_ref"] = "manual_free_text_guess"
        drills["F12.5_hil_choice_not_from_candidate_universe"] = _failure_result(
            validate_e2e_trace(p4)
        )

    if "P5" in scenario_reports:
        p5 = copy.deepcopy(scenario_reports["P5"]["trace"])
        p5["privacy_gate"] = {"gate_before_disclosure": False, "decision": "disclosed"}
        drills["F12.6_privacy_disclosure_before_gate"] = _failure_result(validate_e2e_trace(p5))

    if "P6" in scenario_reports:
        p6 = copy.deepcopy(scenario_reports["P6"]["trace"])
        p6["partial_projection"] = {"disclosed": False, "single_provider_guess": True}
        drills["F12.7_partial_projection_guessed_single_provider"] = _failure_result(
            validate_e2e_trace(p6)
        )

    return drills


def _failure_result(validation: dict[str, Any]) -> dict[str, Any]:
    return {"validation": validation, "expected_failure_observed": not validation["accepted"]}


def _record_trace_proofs(writer: ProofRecordWriter, trace: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for item in trace["proof_chain"]:
        proof = proof_record_template(
            milestone_id="M12",
            scenario_id=trace["scenario_id"],
            component=item["contract"],
            seam=f"M12 {item['contract']} chain element",
            producer=item["producer"],
            consumer=item["consumer"],
            trace_id=trace["trace_id"],
            request_id=f"req-m12-{trace['scenario_id'].lower()}-{item['contract'].lower()}",
            input_ref=f"probe_e2e_scenarios:{trace['scenario_id']}:{item['contract']}:input",
            output_ref=item["evidence_ref"],
            feature_flags=[
                "back.use_situated_execution_kernel",
                "back.use_prompt_injection_envelope_v1",
            ],
            assertions=["trace_id_bound", "producer_consumer_bound", "contract_observed"],
        )
        proof["chain_contract"] = item["contract"]
        proof["chain_proof_id"] = item["proof_id"]
        records.append(writer.write(proof).to_dict())
    return records


def _record_failure_proof(
    writer: ProofRecordWriter, failure_drills: dict[str, Any]
) -> dict[str, Any]:
    proof = proof_record_template(
        milestone_id="M12",
        scenario_id="F12_failure_drills",
        component="End-to-end scenario gate",
        seam="M12 promotion gate failure drills",
        producer="M12 probe",
        consumer="whiteboard promotion gate",
        trace_id="trace-m12-failure-drills",
        request_id="req-m12-failure-drills",
        input_ref="probe_e2e_scenarios:failure_drills:mutated_traces",
        output_ref="probe_e2e_scenarios:failure_drills:rejected_fields",
        verdict="blocked",
        feature_flags=["back.use_situated_execution_kernel"],
        assertions=[
            key for key, item in failure_drills.items() if item["expected_failure_observed"]
        ],
    )
    proof["first_failure_code"] = "e2e_trace_validation_rejected"
    return writer.write(proof).to_dict()


async def _amain() -> int:
    args = _parse_args()
    scenario_ids = [item.strip() for item in args.scenarios.split(",") if item.strip()]
    unknown = sorted(set(scenario_ids) - set(SCENARIOS))
    if unknown:
        raise SystemExit(f"Unknown scenarios: {', '.join(unknown)}")
    report = await run_probe(
        scenario_ids=scenario_ids,
        production_provider=args.production_provider,
        model=args.model,
        record_proof=args.record_proof,
        output_dir=args.output_dir,
    )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"M12 e2e scenarios verdict: {report['verdict']}")
    return 0 if report["verdict"] == "pass" else 1


def main() -> int:
    return asyncio.run(_amain())


if __name__ == "__main__":
    raise SystemExit(main())
