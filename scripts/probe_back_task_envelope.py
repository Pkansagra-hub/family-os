"""Probe M1 BackTaskEnvelope construction from the current task dispatch shape."""

from __future__ import annotations

import argparse
import copy
import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from k1.concierge.bus.builders import build_task_dispatch
from poc.back_tool_contract.back_task_envelope import (
    build_back_task_envelope,
    envelope_headers_from_bus_envelope,
    validate_back_task_envelope,
)
from poc.back_tool_contract.proof import ProofRecordWriter, proof_record_template


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", default="dentist_riley", choices=["dentist_riley"])
    parser.add_argument("--json", action="store_true", help="Emit JSON report.")
    parser.add_argument(
        "--record-proof", action="store_true", help="Write M1 ProofRecord artifacts."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "tmp" / "back_tool_contract" / "m1_back_task_envelope",
        help="Directory for optional proof artifacts.",
    )
    return parser.parse_args()


def dentist_riley_payload() -> dict[str, Any]:
    return {
        "task_id": "task-dentist-riley-001",
        "tier": "LOW",
        "budget_hint": 4,
        "safety_band": "AMBER",
        "intents": [
            {
                "action": "Add dentist appointment for Riley on Monday",
                "domain": "calendar",
                "urgency": "normal",
                "params": {
                    "title": "Dentist appointment",
                    "attendees": ["Riley"],
                    "date": "Monday",
                },
            }
        ],
        "reference_context": {
            "Riley": "person:riley",
            "Monday": "temporal_ref:monday-next",
            "general_context_to_add": "User asked for a calendar write but did not give a time.",
        },
        "context_snapshot": {"scoreboard_refs": {"Riley": "person:riley"}},
        "execution_profiles": [
            {
                "profile_id": "family_calendar_write_v1",
                "record_type": "guidance",
                "authority": "non_executable",
            }
        ],
        "grounding_envelope_id": "grounding-env-dentist-riley",
        "temporal_anchor_id": "temporal-anchor-monday",
        "spatial_context_id": "home-default",
        "resolved_temporal_refs": {"Monday": {"date": "2026-06-01", "status": "resolved"}},
        "resolved_spatial_refs": {"home": "space:home"},
        "narrative_thread": "family scheduling",
        "turn_state_overlay": {
            "turn_id": "session-m1:7",
            "durable": True,
            "status": "applied",
            "fields_applied": ["scoreboard.referent"],
        },
        "plan": {"steps": ["create calendar event", "ask HIL for missing time if needed"]},
        "urgency": "normal",
    }


def _bus_envelope_for_payload(payload: dict[str, Any]) -> Any:
    envelope = build_task_dispatch(copy.deepcopy(payload), parent_id=101)
    return replace(
        envelope,
        envelope_id=202,
        cognitive_trace_id="trace-m1-dentist-riley",
        session_id="session-m1",
        request_id="req-m1-dentist-riley",
    )


def run_probe(*, record_proof: bool, output_dir: Path) -> dict[str, Any]:
    raw_payload = dentist_riley_payload()
    bus_envelope = _bus_envelope_for_payload(raw_payload)
    headers = envelope_headers_from_bus_envelope(bus_envelope)
    actor_scope = {
        "actor_ref": "back",
        "household_or_space_scope": "household:demo",
        "caller_role": "guardian",
        "caller_face": "primary_user",
    }
    back_envelope = build_back_task_envelope(raw_payload, headers, actor_scope=actor_scope)
    validation = validate_back_task_envelope(back_envelope)

    missing_request_headers = dict(headers)
    missing_request_headers["request_id"] = ""
    missing_request_envelope = build_back_task_envelope(
        raw_payload, missing_request_headers, actor_scope=actor_scope
    )
    missing_request_validation = validate_back_task_envelope(missing_request_envelope)

    no_grounding_payload = copy.deepcopy(raw_payload)
    for field_name in (
        "grounding_envelope_id",
        "temporal_anchor_id",
        "spatial_context_id",
        "resolved_temporal_refs",
        "resolved_spatial_refs",
        "grounding",
    ):
        no_grounding_payload.pop(field_name, None)
    no_grounding_envelope = build_back_task_envelope(
        no_grounding_payload, headers, actor_scope=actor_scope
    )
    no_grounding_validation = validate_back_task_envelope(no_grounding_envelope)

    missing_actor_role_scope = {"actor_ref": "back", "household_or_space_scope": "household:demo"}
    missing_actor_role_envelope = build_back_task_envelope(
        raw_payload, headers, actor_scope=missing_actor_role_scope
    )
    missing_actor_role_validation = validate_back_task_envelope(missing_actor_role_envelope)

    report = {
        "milestone": "M1",
        "scenario_id": "dentist_riley",
        "targeted_command": (
            "python scripts\\probe_back_task_envelope.py --scenario dentist_riley "
            "--json --record-proof"
        ),
        "validation": validation,
        "back_task_envelope": back_envelope,
        "failure_drills": {
            "F1.1_missing_request_id": {
                "validation": missing_request_validation,
                "expected_rejected_field": "envelope_correlation.request_id",
            },
            "F1.2_top_level_plan_reported": {
                "discarded_fields": back_envelope["canonicalization_report"]["discarded_fields"],
                "discard_reasons": back_envelope["canonicalization_report"]["discard_reasons"],
            },
            "F1.3_no_grounding_handle": {
                "validation": no_grounding_validation,
                "grounding_state": no_grounding_envelope["canonicalization_report"][
                    "grounding_state"
                ],
            },
            "F1.4_actor_role_missing": {
                "validation": missing_actor_role_validation,
                "side_effect_eligible": missing_actor_role_envelope["actor_scope"][
                    "side_effect_eligible"
                ],
            },
        },
    }
    checks = {
        "success_envelope_accepted": validation["accepted"],
        "request_frame_seed_non_empty": bool(back_envelope["request_frame_seed"]["user_goal"]),
        "correlation_stable": back_envelope["envelope_correlation"]["trace_id"]
        == "trace-m1-dentist-riley",
        "canonicalization_report_truthful": "plan"
        in back_envelope["canonicalization_report"]["discarded_fields"],
        "missing_request_id_rejected": not missing_request_validation["accepted"]
        and "envelope_correlation.request_id" in missing_request_validation["rejected_fields"],
        "no_grounding_valid_degraded": no_grounding_validation["accepted"]
        and no_grounding_envelope["canonicalization_report"]["grounding_state"] == "absent",
        "missing_actor_role_allowed_not_side_effect_eligible": missing_actor_role_validation[
            "accepted"
        ]
        and not missing_actor_role_envelope["actor_scope"]["side_effect_eligible"],
    }
    report["checks"] = checks
    report["verdict"] = "pass" if all(checks.values()) else "fail"
    if record_proof:
        report["proof_records"] = _record_proofs(report, output_dir)
    return report


def _record_proofs(report: dict[str, Any], output_dir: Path) -> list[dict[str, Any]]:
    writer = ProofRecordWriter(output_dir)
    envelope = report["back_task_envelope"]
    success_record = proof_record_template(
        milestone_id="M1",
        scenario_id="dentist_riley",
        component="BackTaskEnvelope",
        seam="Front/FSM canonical task to Back ReAct intake",
        producer="Front/FSM canonical dispatch",
        consumer="Back ReAct runtime",
        trace_id=envelope["envelope_correlation"]["trace_id"],
        request_id=envelope["envelope_correlation"]["request_id"],
        task_id=envelope["task_dispatch"]["task_id"],
        input_ref="probe_back_task_envelope:dentist_riley:raw_payload",
        output_ref="probe_back_task_envelope:dentist_riley:back_task_envelope",
        feature_flags=["bus.emit_back_task_envelope"],
        assertions=[key for key, value in report["checks"].items() if value],
    )
    observations = [writer.write(success_record).to_dict()]
    failure_record = proof_record_template(
        milestone_id="M1",
        scenario_id="F1.1_missing_request_id",
        component="BackTaskEnvelope",
        seam="correlation validation",
        producer="M1 probe",
        consumer="Back ReAct runtime",
        trace_id=envelope["envelope_correlation"]["trace_id"],
        request_id="req-missing-controlled-negative",
        task_id=envelope["task_dispatch"]["task_id"],
        input_ref="probe_back_task_envelope:F1.1:missing_request_id",
        output_ref="probe_back_task_envelope:F1.1:rejected_fields",
        verdict="blocked",
        feature_flags=["bus.emit_back_task_envelope"],
        assertions=["missing request_id rejected before Back loop"],
    )
    failure_record["first_failure_code"] = "missing_required_correlation"
    observations.append(writer.write(failure_record).to_dict())
    return observations


def main() -> int:
    args = _parse_args()
    report = run_probe(record_proof=args.record_proof, output_dir=args.output_dir)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"M1 BackTaskEnvelope verdict: {report['verdict']}")
    return 0 if report["verdict"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
