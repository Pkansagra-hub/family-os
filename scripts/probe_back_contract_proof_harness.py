"""Probe M0 proof harness behavior for the Back tool contract plan."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from poc.back_tool_contract.proof import (
    ProofRecordWriter,
    proof_record_template,
    utc_now_iso,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true", help="Run the M0 self-test drill.")
    parser.add_argument("--json", action="store_true", help="Emit JSON report.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "tmp" / "back_tool_contract" / "m0_self_test",
        help="Directory for proof artifacts.",
    )
    return parser.parse_args()


def run_self_test(output_dir: Path) -> dict[str, Any]:
    writer = ProofRecordWriter(output_dir)
    base = proof_record_template(
        milestone_id="M0",
        scenario_id="m0_self_test_success",
        component="proof_harness",
        seam="proof_record_writer",
        producer="M0 probe",
        consumer="whiteboard promotion gate",
        trace_id="trace-m0-self-test",
        request_id="req-m0-self-test",
        input_ref="self-test:success-input",
        output_ref="self-test:success-output",
        assertions=["round_trip_serialization", "schema_version_present"],
    )
    success = writer.write(base)

    failure_entry = {
        "milestone_id": "M0",
        "failure_id": "failure-m0-controlled",
        "scenario_id": "m0_self_test_failure_entry",
        "first_seen_at": utc_now_iso(),
        "failing_command": "python scripts\\probe_back_contract_proof_harness.py --self-test --json",
        "expected": "controlled failure entry is stored",
        "observed": "controlled failure entry is stored",
        "root_cause": "intentional negative-path proof",
        "contract_wrong": False,
        "implementation_wrong": False,
        "prompt_boundary_wrong": False,
        "policy_wrong": False,
        "fix_summary": "no fix required",
        "retest_command": "python scripts\\probe_back_contract_proof_harness.py --self-test --json",
        "retest_verdict": "pass",
        "remaining_risk": "none for M0 self-test",
    }
    failure = writer.write_failure_entry(failure_entry)

    validation_prompt = {
        "validation_prompt_id": "vp-m0-production-shape",
        "milestone_id": "M0",
        "scenario_id": "m0_validation_prompt_shape",
        "prompt_role": "Back",
        "provider_id": "modelhub.production_path_required_for_e2e",
        "model_id": "configured-production-model",
        "prompt_ref": "poc/back_tool_contract/prompts/m0_validation_prompt_shape.md",
        "prompt_redaction_summary": {"status": "redacted", "forbidden_material_found": []},
        "allowed_tool_calls": [],
        "allowed_next_actions": [],
        "forbidden_material": ["secrets", "raw catalogs", "raw provider stacks"],
        "expected_model_action": "not_applicable_non_llm_schema_probe",
        "expected_non_action_path": "record shape only; no LLM call is made in M0",
        "expected_evidence_fields": ["provider_id", "model_id", "prompt_ref"],
        "pass_fail_assertions": ["all required fields present", "redaction summary present"],
    }
    validation = writer.write_validation_prompt(validation_prompt)

    missing_trace_record = dict(base)
    missing_trace_record["proof_id"] = "proof-m0-missing-trace"
    missing_trace_record["trace_id"] = ""
    missing_trace = writer.write(missing_trace_record)

    secret_record = dict(base)
    secret_record["proof_id"] = "proof-m0-secret-redaction"
    secret_record["scenario_id"] = "m0_secret_redaction"
    secret_record["debug_payload"] = {"authorization": "Bearer abcdef1234567890"}
    secret = writer.write(secret_record)

    raw_catalog_record = dict(base)
    raw_catalog_record["proof_id"] = "proof-m0-raw-catalog-reject"
    raw_catalog_record["scenario_id"] = "m0_raw_catalog_reject"
    raw_catalog_record["prompt_capture_ref"] = "raw_catalog://full-capability-catalog"
    raw_catalog = writer.write(raw_catalog_record)

    mocked_e2e_record = proof_record_template(
        milestone_id="M12",
        scenario_id="m12_e2e_mock_reject",
        component="end-to-end gate",
        seam="end-to-end LLM validation",
        producer="M0 probe",
        consumer="M12 promotion gate",
        trace_id="trace-m0-mock-reject",
        request_id="req-m0-mock-reject",
        input_ref="self-test:e2e-input",
        output_ref="self-test:e2e-output",
        feature_flags=["back.e2e_contract_shadow_gate"],
    )
    mocked_e2e_record["llm_mock_used"] = True
    mocked_e2e = writer.write(mocked_e2e_record)

    checks = {
        "success_record_written": success.accepted,
        "failure_entry_written": failure.accepted,
        "validation_prompt_written": validation.accepted,
        "missing_trace_rejected": not missing_trace.accepted
        and "trace_id" in missing_trace.rejected_fields,
        "secret_like_field_redacted": secret.accepted and secret.redaction_summary["count"] > 0,
        "raw_catalog_prompt_capture_rejected": not raw_catalog.accepted
        and "prompt_capture_ref" in raw_catalog.rejected_fields,
        "mocked_e2e_rejected": not mocked_e2e.accepted
        and "llm_mock_used" in mocked_e2e.rejected_fields,
    }
    return {
        "milestone": "M0",
        "verdict": "pass" if all(checks.values()) else "fail",
        "output_dir": str(output_dir),
        "checks": checks,
        "observations": {
            "success": success.to_dict(),
            "failure": failure.to_dict(),
            "validation_prompt": validation.to_dict(),
            "missing_trace": missing_trace.to_dict(),
            "secret_redaction": secret.to_dict(),
            "raw_catalog": raw_catalog.to_dict(),
            "mocked_e2e": mocked_e2e.to_dict(),
        },
    }


def main() -> int:
    args = _parse_args()
    if not args.self_test:
        raise SystemExit("--self-test is required for this probe")
    report = run_self_test(args.output_dir)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"M0 proof harness verdict: {report['verdict']}")
        print(f"Artifacts: {report['output_dir']}")
    return 0 if report["verdict"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
