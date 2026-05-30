"""Probe M11 prompt injection timing and runtime tool enforcement."""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from poc.back_tool_contract.live_provider import (
    call_live_submit_result,
    validation_prompt_record,
)
from poc.back_tool_contract.prompt_injection import (
    PromptToolDispatcherFixture,
    build_calendar_prompt_injection_sequence,
    final_prompt_payload,
    validate_dispatch_rejection,
    validate_prompt_injection_envelope,
)
from poc.back_tool_contract.proof import ProofRecordWriter, proof_record_template


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", default="calendar_riley", choices=["calendar_riley"])
    parser.add_argument("--capture-phases", default="all", choices=["all"])
    parser.add_argument("--attempt-forbidden-call", action="store_true")
    parser.add_argument("--production-provider", action="store_true")
    parser.add_argument("--model", default=os.environ.get("VERTEX_MODEL") or "gemini-2.5-flash")
    parser.add_argument("--json", action="store_true", help="Emit JSON report.")
    parser.add_argument(
        "--record-proof", action="store_true", help="Write M11 ProofRecord artifacts."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "tmp" / "back_tool_contract" / "m11_prompt_injection",
    )
    return parser.parse_args()


async def run_probe(
    *,
    production_provider: bool,
    model: str,
    attempt_forbidden_call: bool,
    record_proof: bool,
    output_dir: Path,
) -> dict[str, Any]:
    sequence = build_calendar_prompt_injection_sequence()
    envelope_reports = {}
    for envelope in sequence["envelopes"]:
        validation = validate_prompt_injection_envelope(envelope)
        envelope_reports[envelope["phase"]] = {
            "envelope": envelope,
            "validation": validation,
            "checks": {"validation_accepted": validation["accepted"]},
        }

    dispatcher = PromptToolDispatcherFixture()
    forbidden_observation = None
    forbidden_validation = {"accepted": True, "rejected_fields": []}
    if attempt_forbidden_call:
        forbidden_observation = dispatcher.enforce(
            sequence["envelopes"][-1], "discover_capabilities"
        )
        forbidden_validation = validate_dispatch_rejection(forbidden_observation)

    if production_provider:
        provider_result = await call_live_submit_result(
            prompt_payload=final_prompt_payload(sequence),
            model=model,
            trace_id="trace-m11-live-final-iteration",
            request_id="req-m11-live-final-iteration",
            session_id="session-m11",
            consumer_id="concierge.back.prompt_injection_probe",
        )
    else:
        provider_result = {
            "live_provider_called": False,
            "verdict": "blocked",
            "blocked_reason": "Pass --production-provider to satisfy M11.",
        }

    failure_drills = _failure_drills(sequence)
    checks = {
        "all_required_phases_captured": set(envelope_reports)
        == {
            "loop_start",
            "after_request_frame",
            "after_resolution",
            "after_invocation",
            "after_hil_response",
            "final_iteration",
        },
        "all_envelopes_valid": all(
            item["validation"]["accepted"] for item in envelope_reports.values()
        ),
        "after_resolution_has_allowed_next_actions": any(
            obs.get("kind") == "allowed_next_actions"
            for obs in sequence["envelopes"][2].get("observations", [])
        ),
        "after_invocation_has_recovery_directive": any(
            (obs.get("recovery_directive") or {}).get("action") == "retry_with_params"
            for obs in sequence["envelopes"][3].get("observations", [])
        ),
        "forbidden_call_rejected": forbidden_validation["accepted"]
        and bool(forbidden_observation)
        and forbidden_observation.get("status") == "rejected",
        "production_provider_passed": provider_result.get("verdict") == "pass",
        "failure_drills_pass": all(
            item["expected_failure_observed"] for item in failure_drills.values()
        ),
    }
    report: dict[str, Any] = {
        "milestone": "M11",
        "targeted_command": "python scripts\\probe_prompt_injection.py --scenario calendar_riley --capture-phases all --attempt-forbidden-call --production-provider --json --record-proof",
        "scenario_id": "calendar_riley",
        "prompt_injections": envelope_reports,
        "forbidden_call_probe": {
            "observation": forbidden_observation,
            "validation": forbidden_validation,
        },
        "provider_result": provider_result,
        "failure_drills": failure_drills,
        "checks": checks,
        "verdict": "pass" if all(checks.values()) else "fail",
    }
    if record_proof:
        report["proof_records"] = _record_proofs(report, output_dir)
        if production_provider:
            writer = ProofRecordWriter(output_dir)
            vp = validation_prompt_record(
                milestone_id="M11",
                scenario_id="calendar_riley",
                prompt_ref="probe_prompt_injection:calendar_riley:final_iteration_prompt",
                provider_result=provider_result,
            )
            report["validation_prompt_records"] = [writer.write_validation_prompt(vp).to_dict()]
    return report


def _failure_drills(sequence: dict[str, Any]) -> dict[str, Any]:
    after_resolution = copy.deepcopy(sequence["envelopes"][2])
    after_resolution["observations"] = []
    after_resolution_validation = validate_prompt_injection_envelope(after_resolution)

    raw_catalog = copy.deepcopy(sequence["envelopes"][2])
    raw_catalog["compact_cards"].append(
        {
            "card_id": "bad-raw-catalog",
            "card_version": 1,
            "card_type": "RawCatalog",
            "source_ref": "raw_catalog:all-tools",
            "summary": "raw_catalog full catalog",
        }
    )
    raw_catalog_validation = validate_prompt_injection_envelope(raw_catalog)

    final = copy.deepcopy(sequence["envelopes"][-1])
    final["allowed_tool_calls"] = ["submit_result", "discover_capabilities"]
    final_validation = validate_prompt_injection_envelope(final)

    dispatcher = PromptToolDispatcherFixture()
    bad_rejection = dispatcher.enforce(final, "discover_capabilities")
    bad_rejection["status"] = "admitted"
    bad_rejection["provider_dispatch_attempted"] = True
    bad_rejection_validation = validate_dispatch_rejection(bad_rejection)

    return {
        "F11.1_after_resolution_lacks_allowed_next_actions": _failure_result(
            after_resolution_validation
        ),
        "F11.2_raw_catalog_in_prompt_capture": _failure_result(raw_catalog_validation),
        "F11.3_forbidden_invoke_succeeds": _failure_result(bad_rejection_validation),
        "F11.4_final_iteration_allows_unrelated_discovery": _failure_result(final_validation),
    }


def _failure_result(validation: dict[str, Any]) -> dict[str, Any]:
    return {"validation": validation, "expected_failure_observed": not validation["accepted"]}


def _record_proofs(report: dict[str, Any], output_dir: Path) -> list[dict[str, Any]]:
    writer = ProofRecordWriter(output_dir)
    observations: list[dict[str, Any]] = []
    for phase, phase_report in report["prompt_injections"].items():
        envelope = phase_report["envelope"]
        proof = proof_record_template(
            milestone_id="M11",
            scenario_id=f"calendar_riley_{phase}",
            component="Back prompt injection runtime",
            seam="PromptInjectionEnvelope phase capture",
            producer="Concierge prompt assembly",
            consumer="Back ReAct loop",
            trace_id=envelope["trace_id"],
            request_id=f"req-m11-{phase}",
            input_ref=f"probe_prompt_injection:{phase}:source_refs",
            output_ref=f"probe_prompt_injection:{phase}:prompt_injection_envelope",
            feature_flags=["back.use_prompt_injection_envelope_v1"],
            assertions=[key for key, value in phase_report["checks"].items() if value],
        )
        proof["injection_id"] = envelope["injection_id"]
        observations.append(writer.write(proof).to_dict())
    failure_proof = proof_record_template(
        milestone_id="M11",
        scenario_id="F11_failure_drills",
        component="Back prompt injection runtime",
        seam="PromptInjectionEnvelope validation",
        producer="M11 probe",
        consumer="whiteboard promotion gate",
        trace_id="trace-m11-failure-drills",
        request_id="req-m11-failure-drills",
        input_ref="probe_prompt_injection:failure_drills:mutated_envelopes",
        output_ref="probe_prompt_injection:failure_drills:rejected_fields",
        verdict="blocked",
        feature_flags=["back.use_prompt_injection_envelope_v1"],
        assertions=[
            key
            for key, item in report["failure_drills"].items()
            if item["expected_failure_observed"]
        ],
    )
    failure_proof["first_failure_code"] = "prompt_injection_validation_rejected"
    observations.append(writer.write(failure_proof).to_dict())
    return observations


async def _amain() -> int:
    args = _parse_args()
    report = await run_probe(
        production_provider=args.production_provider,
        model=args.model,
        attempt_forbidden_call=args.attempt_forbidden_call,
        record_proof=args.record_proof,
        output_dir=args.output_dir,
    )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"M11 prompt_injection verdict: {report['verdict']}")
    return 0 if report["verdict"] == "pass" else 1


def main() -> int:
    import asyncio

    return asyncio.run(_amain())


if __name__ == "__main__":
    raise SystemExit(main())
