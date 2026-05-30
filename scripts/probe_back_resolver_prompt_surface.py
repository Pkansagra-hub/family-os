"""Probe M2A Back prompt surface -> resolve_situation tool-call authoring."""

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

from k1.concierge.bus.builders import build_task_dispatch  # noqa: E402
from poc.back_tool_contract.back_prompt_surface import (  # noqa: E402
    build_back_resolver_prompt_surface,
    make_resolver_tool_call,
    validate_prompt_surface,
    validate_resolver_tool_call,
)
from poc.back_tool_contract.back_task_envelope import (  # noqa: E402
    build_back_task_envelope,
    envelope_headers_from_bus_envelope,
)
from poc.back_tool_contract.proof import (  # noqa: E402
    ProofRecordWriter,
    proof_record_template,
)
from poc.back_tool_contract.resolve_situation import (  # noqa: E402
    resolve_situation,
    validate_resolution_envelope,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", default="dentist_riley_5pm", choices=["dentist_riley_5pm"])
    parser.add_argument("--json", action="store_true", help="Emit JSON report.")
    parser.add_argument(
        "--record-proof", action="store_true", help="Write M2A ProofRecord artifacts."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "tmp" / "back_tool_contract" / "m2a_back_resolver_prompt_surface",
        help="Directory for optional proof artifacts.",
    )
    return parser.parse_args()


def dentist_riley_5pm_payload() -> dict[str, Any]:
    return {
        "task_id": "task-dentist-riley-5pm-001",
        "tier": "LOW",
        "budget_hint": 4,
        "safety_band": "GREEN",
        "intents": [
            {
                "action": "Put Riley's dentist appointment on Monday at 5pm",
                "domain": "calendar",
                "urgency": "normal",
                "params": {
                    "title": "Dentist appointment",
                    "attendees": ["Riley"],
                    "date": "Monday",
                    "time": "5pm",
                    "duration_minutes": 30,
                },
            }
        ],
        "reference_context": {
            "Riley": "person:riley",
            "Monday": "temporal_ref:monday-next",
        },
        "context_snapshot": {"scoreboard_refs": {"Riley": "person:riley"}},
        "execution_profiles": [
            {
                "profile_id": "family_calendar_write_v1",
                "record_type": "guidance",
                "authority": "non_executable",
            }
        ],
        "grounding_envelope_id": "grounding-env-dentist-riley-5pm",
        "temporal_anchor_id": "temporal-anchor-monday-5pm",
        "spatial_context_id": "home-default",
        "resolved_temporal_refs": {
            "Monday 5pm": {
                "normalized_label": "Monday 5pm",
                "status": "resolved",
                "window": {
                    "start_local": "2026-06-01T17:00:00",
                    "end_local": "2026-06-01T17:30:00",
                    "timezone": "America/New_York",
                },
            }
        },
        "resolved_spatial_refs": {"home": "space:home"},
    }


def _back_task_envelope() -> dict[str, Any]:
    raw_payload = dentist_riley_5pm_payload()
    bus_envelope = build_task_dispatch(copy.deepcopy(raw_payload), parent_id=151)
    bus_envelope = replace(
        bus_envelope,
        envelope_id=252,
        cognitive_trace_id="trace-m2a-dentist-riley-5pm",
        session_id="session-m2a",
        request_id="req-m2a-dentist-riley-5pm",
    )
    actor_scope = {
        "actor_ref": "back",
        "household_or_space_scope": "household:demo",
        "caller_role": "guardian",
        "caller_face": "primary_user",
    }
    return build_back_task_envelope(
        raw_payload,
        envelope_headers_from_bus_envelope(bus_envelope),
        actor_scope=actor_scope,
    )


def run_probe(*, record_proof: bool, output_dir: Path) -> dict[str, Any]:
    envelope = _back_task_envelope()
    surface = build_back_resolver_prompt_surface(
        envelope,
        scenario_id="calendar_riley",
        session_snapshot={"control.safety_band": "GREEN", "scoreboard.Riley": "person:riley"},
    )
    surface_validation = validate_prompt_surface(surface)
    tool_call = make_resolver_tool_call(surface)
    tool_call_validation = validate_resolver_tool_call(tool_call, surface)
    resolution = resolve_situation(tool_call["arguments"])
    resolution_validation = validate_resolution_envelope(resolution)
    failure_drills = _failure_drills(surface, tool_call)
    checks = {
        "surface_validation_accepted": surface_validation["accepted"],
        "tool_call_validation_accepted": tool_call_validation["accepted"],
        "actor_scope_code_supplied_locked": _ledger_field_locked(surface, "actor_scope"),
        "safety_context_code_supplied_locked": _ledger_field_locked(surface, "safety_context"),
        "semantic_refs_have_source_values": _semantic_refs_check(surface),
        "operation_hints_include_derived_create_event": "create_event"
        in surface["request_frame_draft"]["operation_hints"],
        "effect_hints_include_write_side_effect": {"write", "side_effect"}.issubset(
            set(surface["request_frame_draft"]["effect_hints"])
        ),
        "m2_resolver_accepts_tool_call": resolution_validation["accepted"],
        "live_llm_smartness_not_claimed": surface["live_llm_claim"]
        == {
            "live_llm_called": False,
            "smartness_proven": False,
            "reason": "M2A is a non-LLM prompt-surface and validation proof.",
        },
        "failure_drills_pass": all(
            item["expected_failure_observed"] for item in failure_drills.values()
        ),
    }
    report: dict[str, Any] = {
        "milestone": "M2A",
        "scenario_id": "dentist_riley_5pm",
        "targeted_command": (
            "python scripts\\probe_back_resolver_prompt_surface.py --scenario "
            "dentist_riley_5pm --json --record-proof"
        ),
        "prompt_surface": surface,
        "surface_validation": surface_validation,
        "resolver_tool_call": tool_call,
        "tool_call_validation": tool_call_validation,
        "resolution_validation": resolution_validation,
        "failure_drills": failure_drills,
        "checks": checks,
        "verdict": "pass" if all(checks.values()) else "fail",
    }
    if record_proof:
        report["proof_records"] = _record_proofs(report, output_dir)
    return report


def _failure_drills(surface: dict[str, Any], tool_call: dict[str, Any]) -> dict[str, Any]:
    f2a1 = copy.deepcopy(tool_call)
    f2a1["arguments"]["actor_scope"]["caller_role"] = "administrator"
    f2a1_validation = validate_resolver_tool_call(f2a1, surface)

    f2a2 = copy.deepcopy(tool_call)
    f2a2["arguments"]["request_frame"]["resource_id"] = "calendar:family:riley"
    f2a2["arguments"]["request_frame"]["capability_name"] = "tool.execute.calendar.create_event"
    f2a2_validation = validate_resolver_tool_call(f2a2, surface)

    f2a3 = copy.deepcopy(tool_call)
    f2a3["arguments"]["request_frame"]["operation_hints"].append("delete_event")
    f2a3_validation = validate_resolver_tool_call(f2a3, surface)

    f2a4 = copy.deepcopy(tool_call)
    f2a4["arguments"]["safety_context"]["source_value"] = "AMBER"
    f2a4["arguments"]["request_frame"]["safety_context"]["source_value"] = "AMBER"
    f2a4_validation = validate_resolver_tool_call(f2a4, surface)

    f2a5 = copy.deepcopy(surface)
    f2a5["source_ledger"] = [
        item for item in f2a5["source_ledger"] if item.get("field") != "safety_context"
    ]
    f2a5_validation = validate_prompt_surface(f2a5)

    return {
        "F2A.1_llm_changes_actor_scope": _failure_result(f2a1_validation),
        "F2A.2_llm_injects_resource_or_capability_authority": _failure_result(f2a2_validation),
        "F2A.3_llm_adds_unsupported_operation_hint": _failure_result(f2a3_validation),
        "F2A.4_llm_changes_safety_band": _failure_result(f2a4_validation),
        "F2A.5_prompt_surface_missing_safety_source": _failure_result(f2a5_validation),
    }


def _failure_result(validation: dict[str, Any]) -> dict[str, Any]:
    return {"validation": validation, "expected_failure_observed": not validation["accepted"]}


def _ledger_field_locked(surface: dict[str, Any], field_name: str) -> bool:
    for item in surface.get("source_ledger") or []:
        if item.get("field") == field_name:
            return item.get("locked") is True and item.get("llm_editable") is False
    return False


def _semantic_refs_check(surface: dict[str, Any]) -> bool:
    refs = set(surface.get("request_frame_draft", {}).get("semantic_refs") or [])
    expected = {"Riley", "Dentist appointment", "Monday 5pm"}
    return expected.issubset(refs)


def _record_proofs(report: dict[str, Any], output_dir: Path) -> list[dict[str, Any]]:
    writer = ProofRecordWriter(output_dir)
    surface = report["prompt_surface"]
    success_record = proof_record_template(
        milestone_id="M2A",
        scenario_id="dentist_riley_5pm",
        component="Back resolver prompt surface",
        seam="BackTaskEnvelope to resolve_situation tool call",
        producer="Back prompt/context builder",
        consumer="Back LLM tool-call authoring validator",
        trace_id="trace-m2a-dentist-riley-5pm",
        request_id="req-m2a-dentist-riley-5pm",
        task_id="task-dentist-riley-5pm-001",
        input_ref="probe_back_resolver_prompt_surface:dentist_riley_5pm:back_task_envelope",
        output_ref="probe_back_resolver_prompt_surface:dentist_riley_5pm:resolver_tool_call",
        feature_flags=["back.use_resolver_prompt_surface_v1"],
        assertions=[key for key, value in report["checks"].items() if value],
    )
    success_record["surface_id"] = surface["surface_id"]
    success_record["live_llm_called"] = False
    observations = [writer.write(success_record).to_dict()]
    failure_record = proof_record_template(
        milestone_id="M2A",
        scenario_id="F2A_failure_drills",
        component="Back resolver prompt surface",
        seam="resolve_situation tool-call validation",
        producer="M2A probe",
        consumer="whiteboard promotion gate",
        trace_id="trace-m2a-failure-drills",
        request_id="req-m2a-failure-drills",
        input_ref="probe_back_resolver_prompt_surface:failure_drills:mutated_calls",
        output_ref="probe_back_resolver_prompt_surface:failure_drills:rejected_fields",
        verdict="blocked",
        feature_flags=["back.use_resolver_prompt_surface_v1"],
        assertions=[
            key
            for key, item in report["failure_drills"].items()
            if item["expected_failure_observed"]
        ],
    )
    failure_record["first_failure_code"] = "resolver_tool_call_validation_rejected"
    observations.append(writer.write(failure_record).to_dict())
    return observations


def main() -> int:
    args = _parse_args()
    report = run_probe(record_proof=args.record_proof, output_dir=args.output_dir)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"M2A Back resolver prompt surface verdict: {report['verdict']}")
    return 0 if report["verdict"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
