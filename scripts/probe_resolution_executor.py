"""Probe M12A post-resolution execution orchestration behavior."""

from __future__ import annotations

import argparse
import asyncio
import copy
import json
import sys
import uuid
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from poc.back_tool_contract.proof import ProofRecordWriter, proof_record_template
from poc.back_tool_contract.resolution_executor import (
    ResolutionExecutionRuntime,
    make_resolution_execution_request,
    validate_resolution_execution_observation,
)
from poc.back_tool_contract.resolve_situation import (
    make_resolve_situation_request,
    resolve_situation,
    validate_resolution_envelope,
)

SCENARIOS = ("jordan_clear_write", "jordan_duplicate_hil")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenarios", default=",".join(SCENARIOS))
    parser.add_argument("--json", action="store_true", help="Emit JSON report.")
    parser.add_argument("--record-proof", action="store_true", help="Write M12A proof records.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "tmp" / "back_tool_contract" / "m12a_resolution_executor",
    )
    return parser.parse_args()


def _scenario_ids(raw: str) -> list[str]:
    values = [item.strip() for item in raw.split(",") if item.strip()]
    unknown = sorted(set(values) - set(SCENARIOS))
    if unknown:
        raise SystemExit(f"Unknown scenario(s): {', '.join(unknown)}")
    return values


async def run_probe(
    scenarios: list[str], *, record_proof: bool, output_dir: Path
) -> dict[str, Any]:
    scenario_reports: dict[str, Any] = {}
    for scenario_id in scenarios:
        resolution_request = _resolution_request()
        resolution_envelope = resolve_situation(resolution_request)
        resolution_validation = validate_resolution_envelope(resolution_envelope)
        runtime = ResolutionExecutionRuntime(
            output_dir / "runtime_runs" / f"{scenario_id}-{uuid.uuid4().hex[:8]}"
        )
        try:
            setup = await _setup_scenario(runtime, scenario_id)
            execution_request = make_resolution_execution_request(
                scenario_id=scenario_id,
                task_id=f"task-m12a-{scenario_id}",
                resolution_envelope=resolution_envelope,
                proposed_write_params=_proposed_write_params(),
                actor_ref="u1",
                actor_role="guardian",
                safety_context={
                    "source_field": "safety_band",
                    "source_value": "GREEN",
                    "mapping_confidence": "direct",
                },
                prerequisite_read_context=_prerequisite_read_context(scenario_id),
            )
            observation = await runtime.execute(execution_request)
        finally:
            runtime.close()

        validation = validate_resolution_execution_observation(observation)
        scenario_reports[scenario_id] = {
            "resolution_request": resolution_request,
            "resolution_envelope": resolution_envelope,
            "resolution_validation": resolution_validation,
            "setup": setup,
            "execution_observation": observation,
            "validation": validation,
            "checks": _scenario_checks(scenario_id, resolution_envelope, observation, validation),
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
        "resolver_contract_chain_used": all(
            item["resolution_validation"]["accepted"]
            and item["resolution_envelope"]["verdict"] == "needs_prerequisite_reads"
            for item in scenario_reports.values()
        ),
    }
    report: dict[str, Any] = {
        "milestone": "M12A",
        "targeted_command": (
            "python scripts\\probe_resolution_executor.py --scenarios "
            "jordan_clear_write,jordan_duplicate_hil --json --record-proof"
        ),
        "scenarios": scenario_reports,
        "failure_drills": failure_drills,
        "checks": checks,
        "verdict": "pass" if all(checks.values()) else "fail",
    }
    if record_proof:
        report["proof_records"] = _record_proofs(report, output_dir)
    return report


def _resolution_request() -> dict[str, Any]:
    request_frame = {
        "user_goal": "Create calendar event for Jordan tomorrow at 3pm",
        "operation_hints": ["calendar", "create_event", "scheduling"],
        "resource_reference_hints": ["Jordan calendar", "Jordan tasks", "Jordan reminders"],
        "people_reference_hints": ["Jordan"],
        "temporal_reference_hints": ["tomorrow", "3pm"],
        "constraints": ["write", "duplicate_check_required", "blocker_check_required"],
        "safety_context": {
            "source_field": "safety_band",
            "source_value": "GREEN",
            "mapping_confidence": "direct",
        },
        "idempotency_key_seed": "m12a-calendar-jordan-governed",
    }
    return make_resolve_situation_request(
        scenario_id="calendar_jordan_governed",
        request_frame=request_frame,
        actor_scope={
            "actor_ref": "back",
            "household_or_space_scope": "household:demo",
            "caller_role": "guardian",
            "caller_face": "primary_user",
        },
    )


def _proposed_write_params() -> dict[str, Any]:
    return {
        "title": "Dentist appointment",
        "start": "2026-05-30T15:00:00+00:00",
        "end": "2026-05-30T15:30:00+00:00",
        "attendees": ["person:jordan"],
        "visibility": "family",
    }


async def _setup_scenario(runtime: ResolutionExecutionRuntime, scenario_id: str) -> dict[str, Any]:
    if scenario_id != "jordan_duplicate_hil":
        return {"fixture_setup": "none"}
    seeded = await runtime.seed_calendar_event(
        {
            **_proposed_write_params(),
            "title": "Dentist appointment",
            "notes": "Existing appointment seeded as system-of-record state for duplicate probe.",
        },
        idempotency_key="seed-m12a-duplicate-jordan-dentist",
    )
    return {"fixture_setup": "preexisting_calendar_event", "seeded_event": seeded}


def _prerequisite_read_context(scenario_id: str) -> dict[str, Any]:
    if scenario_id == "jordan_duplicate_hil":
        return {"tasks": [], "reminders": []}
    return {"tasks": [], "reminders": []}


def _scenario_checks(
    scenario_id: str,
    resolution_envelope: dict[str, Any],
    observation: dict[str, Any],
    validation: dict[str, Any],
) -> dict[str, bool]:
    read_phase = observation.get("read_phase") or {}
    roles = set(read_phase.get("observed_roles") or [])
    write = observation.get("write_observation") or {}
    verification = write.get("verification_observation") or {}
    submit = observation.get("submit_result") or {}
    conflict = observation.get("conflict_analysis") or {}
    if scenario_id == "jordan_clear_write":
        stats = (resolution_envelope.get("candidate_universe") or {}).get("corpus_stats") or {}
        return {
            "resolution_needs_prerequisite_reads": resolution_envelope.get("verdict")
            == "needs_prerequisite_reads",
            "execution_validation_accepted": validation["accepted"],
            "materialized_100k_registry": int(stats.get("materialized_contracts") or 0) >= 100000
            and int(stats.get("virtual_noise_records") or 0) == 0,
            "parallel_read_batch": read_phase.get("mode") == "parallel",
            "calendar_task_reminder_reads_observed": READ_ROLES_FOR_CHECK.issubset(roles),
            "task_reminder_reads_service_backed": _service_backed_reads(observation),
            "no_fixture_boundaries": observation.get("audit_fields", {}).get("fixture_boundaries")
            == [],
            "no_blockers": conflict.get("status") == "clear" and not conflict.get("blockers"),
            "write_invoked_after_reads": write.get("status") == "success"
            and observation.get("invariant_evidence", {}).get("read_before_write") is True,
            "verification_passed": verification.get("status") == "passed",
            "submit_completed": submit.get("status") == "completed"
            and submit.get("verification_status") == "verified",
        }
    return {
        "resolution_needs_prerequisite_reads": resolution_envelope.get("verdict")
        == "needs_prerequisite_reads",
        "execution_validation_accepted": validation["accepted"],
        "parallel_read_batch": read_phase.get("mode") == "parallel",
        "calendar_task_reminder_reads_observed": READ_ROLES_FOR_CHECK.issubset(roles),
        "task_reminder_reads_service_backed": _service_backed_reads(observation),
        "no_fixture_boundaries": observation.get("audit_fields", {}).get("fixture_boundaries")
        == [],
        "duplicate_detected": conflict.get("duplicate_count") == 1
        and conflict.get("status") == "blocked",
        "hil_request_created": observation.get("status") == "needs_hil"
        and bool(observation.get("hil_request")),
        "write_not_invoked": not bool(write),
        "submit_needs_hil": submit.get("status") == "needs_hil",
    }


READ_ROLES_FOR_CHECK = {"conflict_reader", "task_blocker_reader", "reminder_blocker_reader"}


def _service_backed_reads(observation: dict[str, Any]) -> bool:
    service_names = {
        str((read.get("audit_fields") or {}).get("service_backed_read") or "")
        for read in ((observation.get("read_phase") or {}).get("observations") or [])
    }
    return {"TasksToolService", "RemindersToolService"}.issubset(service_names)


def _failure_drills(scenario_reports: dict[str, Any]) -> dict[str, Any]:
    clear = copy.deepcopy(scenario_reports["jordan_clear_write"]["execution_observation"])
    duplicate = copy.deepcopy(scenario_reports["jordan_duplicate_hil"]["execution_observation"])

    f121 = copy.deepcopy(clear)
    f121["read_phase"]["completed"] = False
    f121_validation = validate_resolution_execution_observation(f121)

    f122 = copy.deepcopy(duplicate)
    f122["status"] = "completed"
    f122["write_observation"] = copy.deepcopy(clear["write_observation"])
    f122["submit_result"] = copy.deepcopy(clear["submit_result"])
    f122_validation = validate_resolution_execution_observation(f122)

    f123 = copy.deepcopy(clear)
    f123["write_observation"]["verification_observation"] = None
    f123["submit_result"]["verification_status"] = "not_applicable"
    f123_validation = validate_resolution_execution_observation(f123)

    f124 = copy.deepcopy(clear)
    f124["read_phase"]["mode"] = "serial"
    f124_validation = validate_resolution_execution_observation(f124)

    f125 = copy.deepcopy(duplicate)
    f125["status"] = "completed"
    f125["submit_result"]["status"] = "completed"
    f125["submit_result"]["verification_status"] = "verified"
    f125_validation = validate_resolution_execution_observation(f125)

    return {
        "F12A.1_write_before_prerequisite_reads": _failure_result(f121_validation),
        "F12A.2_duplicate_conflict_ignored_and_write_invoked": _failure_result(f122_validation),
        "F12A.3_completed_without_verification": _failure_result(f123_validation),
        "F12A.4_prerequisite_reads_serialized": _failure_result(f124_validation),
        "F12A.5_submit_completed_without_authority_action": _failure_result(f125_validation),
    }


def _failure_result(validation: dict[str, Any]) -> dict[str, Any]:
    return {"validation": validation, "expected_failure_observed": not validation["accepted"]}


def _record_proofs(report: dict[str, Any], output_dir: Path) -> list[dict[str, Any]]:
    writer = ProofRecordWriter(output_dir)
    observations: list[dict[str, Any]] = []
    for scenario_id, scenario_report in report["scenarios"].items():
        observation = scenario_report["execution_observation"]
        proof = proof_record_template(
            milestone_id="M12A",
            scenario_id=scenario_id,
            component="ResolutionExecutionRuntime",
            seam="ResolutionEnvelope to prerequisite reads, mutation, verification, submit_result",
            producer="Back execution orchestrator POC",
            consumer="M12 promotion gate",
            trace_id=f"trace-m12a-{scenario_id}",
            request_id=f"req-m12a-{scenario_id}",
            input_ref=f"probe_resolution_executor:{scenario_id}:resolution_envelope",
            output_ref=f"probe_resolution_executor:{scenario_id}:execution_observation",
            feature_flags=["back.use_resolution_executor_poc"],
            assertions=[key for key, value in scenario_report["checks"].items() if value],
        )
        proof["execution_id"] = observation["execution_id"]
        proof["submit_status"] = observation["submit_result"]["status"]
        observations.append(writer.write(proof).to_dict())
    failure_proof = proof_record_template(
        milestone_id="M12A",
        scenario_id="F12A_failure_drills",
        component="ResolutionExecutionRuntime",
        seam="Execution observation validation",
        producer="M12A probe",
        consumer="whiteboard promotion gate",
        trace_id="trace-m12a-failure-drills",
        request_id="req-m12a-failure-drills",
        input_ref="probe_resolution_executor:failure_drills:mutated_observations",
        output_ref="probe_resolution_executor:failure_drills:rejected_fields",
        verdict="blocked",
        feature_flags=["back.use_resolution_executor_poc"],
        assertions=[
            key
            for key, item in report["failure_drills"].items()
            if item["expected_failure_observed"]
        ],
    )
    failure_proof["first_failure_code"] = "resolution_execution_validation_rejected"
    observations.append(writer.write(failure_proof).to_dict())
    return observations


async def _amain() -> int:
    args = _parse_args()
    report = await run_probe(
        _scenario_ids(args.scenarios), record_proof=args.record_proof, output_dir=args.output_dir
    )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"M12A resolution executor verdict: {report['verdict']}")
    return 0 if report["verdict"] == "pass" else 1


def main() -> int:
    return asyncio.run(_amain())


if __name__ == "__main__":
    raise SystemExit(main())
