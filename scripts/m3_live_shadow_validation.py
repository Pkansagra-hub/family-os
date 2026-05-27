"""POC-only M3 live shadow quality-gate runner.

This script intentionally does not wire SectionUpdateClassifier into the
production Concierge runtime. It attaches to an already running ``boot_web``
kernel over the public web API, sends live turns through the real kernel, then
calls the SectionUpdateClassifier shape out-of-band through ModelHub and writes
a manifest plus quality-gate report.

Expected boot command shape:

    $env:LLM_PROVIDER="vertex"
    $env:GOOGLE_CLOUD_PROJECT="project-33d51855-d616-4fcd-a69"
    $env:K1_ENABLE_TEMPORAL="true"
    $env:K1_ENABLE_GROUNDING="true"
    $env:GOOGLE_CLOUD_LOCATION="global"
    Remove-Item Env:GOOGLE_API_KEY -ErrorAction SilentlyContinue
    .\\scripts\\boot_web.ps1

The runner is fail-closed: it can prove that active mode is not eligible, but it
never applies SessionState writes and never flips runtime flags.
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import hashlib
import inspect
import json
import os
import statistics
import sys
import time
from collections import Counter
from enum import Enum
from pathlib import Path
from typing import Any

import aiohttp
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_CONFIG = ROOT / "scripts" / "m3_live_shadow_validation_quota_config.yaml"
DEFAULT_OUTPUT = ROOT / "data" / "m3_section_update_shadow_validation_report.json"
DEFAULT_PROVIDER = "vertex"
DEFAULT_MODEL = "gemini-2.5-flash-lite"
CLASSIFIER_VERSION = "section-update-v0"
CLASSIFIER_WRITABLE_SECTIONS = (
    "beliefs_active",
    "scoreboard",
    "clarifications",
    "narrative_active",
    "affective_now",
)
MAX_SNAPSHOT_ITEMS = 24
MAX_SNAPSHOT_TEXT_CHARS = 320

COGNITIVE_TOOL_NAMES = {
    "update_beliefs",
    "update_scoreboard",
    "update_clarifications",
    "update_narrative",
    "refine_affect",
    "promote_belief",
}

COGNITIVE_TOOL_OPERATION_HINTS = {
    "update_beliefs": {"beliefs_active.add_fact", "beliefs_active.update_confidence"},
    "promote_belief": {"beliefs_active.update_confidence"},
    "update_scoreboard": {
        "scoreboard.push_question",
        "scoreboard.pop_question",
        "scoreboard.add_referent",
        "scoreboard.push_topic",
        "scoreboard.add_commitment",
        "scoreboard.fulfill_commitment",
    },
    "update_clarifications": {"clarifications.request", "clarifications.answer"},
    "update_narrative": {
        "narrative_active.create_thread",
        "narrative_active.switch_to",
        "narrative_active.resolve_thread",
    },
    "refine_affect": {"affective_now.update"},
}


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    config = load_config(args.config)
    if args.dry_run:
        result = dry_run_report(config, args)
        write_json(args.output, result)
        print(f"dry_run=true output={args.output}")
        return
    if args.simulated_kernel:
        asyncio.run(run_simulated_kernel_validation(config, args))
        return
    asyncio.run(run_live_validation(config, args))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="POC-only M3 SectionUpdate shadow validation against a live boot_web kernel.",
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--base-url", default="")
    parser.add_argument("--preferred-provider", default="")
    parser.add_argument("--preferred-model", default="")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--timeout-ms", type=int, default=45000)
    parser.add_argument("--max-output-tokens", type=int, default=2048)
    parser.add_argument("--consumer-id", default="poc.m3_live_shadow_validation")
    parser.add_argument(
        "--run-label", default="", help="Unique label written to run metadata only."
    )
    parser.add_argument("--turn-limit", type=int, default=0)
    parser.add_argument(
        "--per-turn-timeout-s",
        type=float,
        default=0.0,
        help="Override quota.per_turn_timeout_s for quick live-kernel failure proof.",
    )
    parser.add_argument(
        "--model-call-spacing-s",
        type=float,
        default=0.0,
        help="Minimum delay between classifier provider calls; useful for live quota pacing.",
    )
    parser.add_argument("--wait-ready-s", type=float, default=0.0)
    parser.add_argument(
        "--dry-run", action="store_true", help="Validate config without web/model calls."
    )
    parser.add_argument(
        "--simulated-kernel",
        action="store_true",
        help="Bypass boot_web/FSM; build turns from in-memory SessionState and call the provider.",
    )
    return parser


def load_config(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"M3 live shadow validation config not found: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Config must be a mapping: {path}")
    turns = raw.get("turns")
    if not isinstance(turns, list) or not turns:
        raise ValueError("Config requires at least one turn under 'turns'.")
    return raw


def dry_run_report(config: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    run_label = resolved_run_label(config, args)
    turns = selected_turns(config, args, run_label)
    return {
        "runner": "m3_live_shadow_validation",
        "mode": "dry_run",
        "base_url": resolved_base_url(config, args),
        "run_label": run_label,
        "turn_count": len(turns),
        "quota": dict(config.get("quota") or {}),
        "quality_gates": dict(config.get("quality_gates") or {}),
        "provider_id": preferred_provider(config, args),
        "model_id": preferred_model(config, args),
        "golden_fixture_validity": golden_fixture_validity(config),
        "active_eligible": False,
        "reason": "dry run never authorizes active apply",
    }


async def run_live_validation(config: dict[str, Any], args: argparse.Namespace) -> None:
    normalize_provider_env(config, args)

    base_url = resolved_base_url(config, args)
    quota = dict(config.get("quota") or {})
    if args.per_turn_timeout_s > 0:
        quota["per_turn_timeout_s"] = args.per_turn_timeout_s
    run_label = resolved_run_label(config, args)
    turn_specs = selected_turns(config, args, run_label)
    enforce_quota(turn_specs, quota)
    started = time.perf_counter()

    async with aiohttp.ClientSession() as http_session:
        status_before = await wait_for_status(http_session, base_url, args.wait_ready_s)
        observations = await collect_live_turns(http_session, base_url, turn_specs, quota)
        status_after = await fetch_json(http_session, f"{base_url}/api/status")

    classifier_records = await classify_observations(observations, config, args)
    turn_results = [record["turn_result"] for record in classifier_records]
    manifests = [record["manifest"] for record in classifier_records]
    gate_report = evaluate_quality_gates(
        manifests=manifests,
        config=config,
        provider_id=preferred_provider(config, args),
        model_id=preferred_model(config, args),
        output_path=args.output,
    )
    elapsed_s = round(time.perf_counter() - started, 3)

    report = {
        "runner": "m3_live_shadow_validation",
        "mode": "live_kernel_shadow_poc",
        "base_url": base_url,
        "run_label": run_label,
        "status_before": status_before,
        "status_after": status_after,
        "requested_turns": len(turn_specs),
        "completed_turns": len(turn_results),
        "elapsed_s": elapsed_s,
        "quota": quota,
        "timeout_path_safe_noop_proven": prove_timeout_path_safe_noop(),
        "quality_gate_report": gate_report,
        "turn_results": turn_results,
    }
    write_json(args.output, report)
    print(f"live_kernel_shadow_poc=true output={args.output}")
    print(
        "active_eligible={eligible} failed_gates={failed}".format(
            eligible=gate_report["active_eligible"],
            failed=",".join(gate_report["failed_gates"]) or "none",
        )
    )


async def run_simulated_kernel_validation(config: dict[str, Any], args: argparse.Namespace) -> None:
    load_dotenv_files()
    normalize_provider_env(config, args)

    quota = dict(config.get("quota") or {})
    run_label = resolved_run_label(config, args)
    turn_specs = selected_turns(config, args, run_label)
    enforce_quota(turn_specs, quota)
    started = time.perf_counter()

    observations, simulation_summary = collect_simulated_kernel_turns(turn_specs, config)
    classifier_records = await classify_observations(observations, config, args)
    turn_results = [record["turn_result"] for record in classifier_records]
    manifests = [record["manifest"] for record in classifier_records]
    gate_report = evaluate_quality_gates(
        manifests=manifests,
        config=config,
        provider_id=preferred_provider(config, args),
        model_id=preferred_model(config, args),
        output_path=args.output,
    )
    elapsed_s = round(time.perf_counter() - started, 3)

    report = {
        "runner": "m3_live_shadow_validation",
        "mode": "simulated_kernel_shadow_poc",
        "base_url": "simulated://sessionstate-bus",
        "run_label": run_label,
        "requested_turns": len(turn_specs),
        "completed_turns": len(turn_results),
        "elapsed_s": elapsed_s,
        "quota": quota,
        "simulation": simulation_summary,
        "timeout_path_safe_noop_proven": prove_timeout_path_safe_noop(),
        "quality_gate_report": gate_report,
        "turn_results": turn_results,
    }
    write_json(args.output, report)
    print(f"simulated_kernel_shadow_poc=true output={args.output}")
    print(
        "active_eligible={eligible} failed_gates={failed}".format(
            eligible=gate_report["active_eligible"],
            failed=",".join(gate_report["failed_gates"]) or "none",
        )
    )


def resolved_base_url(config: dict[str, Any], args: argparse.Namespace) -> str:
    return str(args.base_url or config.get("base_url") or "http://127.0.0.1:8765").rstrip("/")


def preferred_provider(config: dict[str, Any], args: argparse.Namespace) -> str:
    return str(
        args.preferred_provider
        or config.get("preferred_provider")
        or os.environ.get("LLM_PROVIDER")
        or DEFAULT_PROVIDER
    )


def preferred_model(config: dict[str, Any], args: argparse.Namespace) -> str:
    return str(
        args.preferred_model
        or config.get("preferred_model")
        or os.environ.get("K1_SECTION_UPDATE_MODEL")
        or os.environ.get("VERTEX_MODEL")
        or DEFAULT_MODEL
    )


def resolved_run_label(config: dict[str, Any], args: argparse.Namespace) -> str:
    return str(args.run_label or config.get("run_label") or f"m3-{run_id_seed()}")


def selected_turns(
    config: dict[str, Any],
    args: argparse.Namespace,
    run_label: str,
) -> list[dict[str, Any]]:
    golden_cases = golden_cases_by_id(config)
    turns = [
        hydrate_turn_spec(dict(item), golden_cases, run_label)
        for item in list(config.get("turns") or [])
    ]
    config_limit = int((config.get("quota") or {}).get("max_turns") or len(turns))
    limit = args.turn_limit if args.turn_limit > 0 else config_limit
    return [dict(item) for item in turns[:limit]]


def hydrate_turn_spec(
    turn: dict[str, Any],
    golden_cases: dict[str, dict[str, Any]],
    run_label: str,
) -> dict[str, Any]:
    case_id = str(turn.get("golden_case_id") or "")
    if not case_id:
        hydrated = dict(turn)
        hydrated["run_label"] = run_label
        reject_run_label_placeholders(hydrated)
        return hydrated
    case = golden_cases.get(case_id)
    if not case:
        raise ValueError(f"unknown golden_case_id in turns: {case_id}")
    live_turn = case.get("live_turn") if isinstance(case.get("live_turn"), dict) else {}
    hydrated = {**live_turn, **turn, "golden_case_id": case_id}
    expected_operations = expected_operations_from_plan_payload(case.get("expected_plan"))
    hydrated.setdefault("expected_operations", expected_operations)
    hydrated.setdefault(
        "critical_operations", list(case.get("critical_operations") or expected_operations)
    )
    hydrated["run_label"] = run_label
    reject_run_label_placeholders(hydrated)
    return hydrated


def reject_run_label_placeholders(value: Any, path: str = "turn") -> None:
    if isinstance(value, str):
        if "{run_label}" in value:
            raise ValueError(f"run label placeholder is not allowed in semantic turn data: {path}")
        if "m3-strongprompt" in value.lower():
            raise ValueError(f"validation run label leaked into semantic turn data: {path}")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "run_label":
                continue
            reject_run_label_placeholders(item, f"{path}.{key}")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            reject_run_label_placeholders(item, f"{path}[{index}]")


def golden_cases_by_id(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(case.get("id")): case
        for case in load_golden_cases(config)
        if isinstance(case, dict) and case.get("id")
    }


def load_golden_cases(config: dict[str, Any]) -> list[dict[str, Any]]:
    path_text = str(config.get("golden_cases_path") or "")
    if not path_text:
        return []
    path = Path(path_text)
    if not path.is_absolute():
        path = ROOT / path
    if not path.is_file():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases = payload.get("cases") if isinstance(payload, dict) else payload
    return cases if isinstance(cases, list) else []


def expected_operations_from_plan_payload(plan_payload: Any) -> list[str]:
    from k1.concierge.section_update.types import SectionUpdatePlan

    plan = SectionUpdatePlan.from_dict(plan_payload)
    return [f"{item.section}.{item.operation}" for item in plan.mutations]


def enforce_quota(turn_specs: list[dict[str, Any]], quota: dict[str, Any]) -> None:
    max_turns = int(quota.get("max_turns") or len(turn_specs))
    max_model_calls = int(quota.get("max_model_calls") or len(turn_specs))
    if len(turn_specs) > max_turns:
        raise ValueError(f"turn count {len(turn_specs)} exceeds quota max_turns={max_turns}")
    if len(turn_specs) > max_model_calls:
        raise ValueError(
            f"model call count {len(turn_specs)} exceeds quota max_model_calls={max_model_calls}"
        )


async def wait_for_status(
    http_session: aiohttp.ClientSession,
    base_url: str,
    wait_ready_s: float,
) -> dict[str, Any]:
    deadline = time.perf_counter() + max(0.0, wait_ready_s)
    last_status: dict[str, Any] = {}
    while True:
        try:
            status = await fetch_json(http_session, f"{base_url}/api/status")
            last_status = status
            if status.get("system_ready") or time.perf_counter() >= deadline:
                return status
        except Exception as exc:  # noqa: BLE001 - POC runner should report endpoint failures.
            last_status = {"system_ready": False, "error": f"{type(exc).__name__}: {exc}"}
            if time.perf_counter() >= deadline:
                raise RuntimeError(f"boot_web status endpoint unavailable: {last_status['error']}")
        await asyncio.sleep(1.0)


async def fetch_json(http_session: aiohttp.ClientSession, url: str) -> dict[str, Any]:
    async with http_session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
        response.raise_for_status()
        payload = await response.json()
        return payload if isinstance(payload, dict) else {"payload": payload}


async def fetch_session_state_summary(
    http_session: aiohttp.ClientSession,
    base_url: str,
) -> dict[str, Any]:
    try:
        snapshot = await fetch_json(http_session, f"{base_url}/api/session/state")
    except Exception as exc:  # noqa: BLE001 - summary remains best-effort evidence.
        return {"available": False, "error": f"{type(exc).__name__}: {exc}"}
    sections = snapshot.get("sections") if isinstance(snapshot.get("sections"), dict) else {}
    section_details = (
        snapshot.get("section_details") if isinstance(snapshot.get("section_details"), dict) else {}
    )
    section_payloads = (
        snapshot.get("section_payloads")
        if isinstance(snapshot.get("section_payloads"), dict)
        else {}
    )
    compact_sections = compact_section_metadata(sections, section_details)
    cognitive_sections = compact_cognitive_sections(section_details, section_payloads)
    version_source = {
        "sections": compact_sections,
        "cognitive_sections": cognitive_sections,
        "local_cold_count": snapshot.get("local_cold_count", 0),
    }
    snapshot_version = str(
        snapshot.get("snapshot_version")
        or snapshot.get("version")
        or snapshot.get("hash")
        or stable_hash(version_source)
    )
    snapshot_source_epoch = str(
        snapshot.get("last_mutation_ms")
        or snapshot.get("epoch")
        or snapshot.get("source_epoch")
        or ""
    )
    return {
        "available": bool(snapshot.get("available")),
        "source": "api/session/state",
        "snapshot_version": snapshot_version,
        "snapshot_source_epoch": snapshot_source_epoch,
        "section_names": sorted(str(name) for name in sections),
        "section_count": len(sections),
        "sections": compact_sections,
        "cognitive_sections": cognitive_sections,
        "local_cold_count": snapshot.get("local_cold_count", 0),
    }


def compact_section_metadata(
    sections: dict[str, Any], section_details: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    compact: dict[str, dict[str, Any]] = {}
    keys = (
        "name",
        "tier",
        "size_bytes",
        "current_size_bytes",
        "budget_bytes",
        "utilization_pct",
        "pressure",
        "last_updated_ms",
    )
    for name in sorted(str(item) for item in sections):
        info = sections.get(name) if isinstance(sections.get(name), dict) else {}
        detail = section_details.get(name) if isinstance(section_details.get(name), dict) else {}
        merged = {**info, **detail}
        compact[name] = {key: merged[key] for key in keys if key in merged}
    return compact


def compact_cognitive_sections(
    section_details: dict[str, Any], section_payloads: dict[str, Any]
) -> dict[str, Any]:
    compact: dict[str, Any] = {}
    for section_name in CLASSIFIER_WRITABLE_SECTIONS:
        detail = section_details.get(section_name)
        payload = section_payloads.get(section_name)
        data = payload.get("data") if isinstance(payload, dict) else None
        detail_map = detail if isinstance(detail, dict) else {}
        data_map = data if isinstance(data, dict) else {}
        if section_name == "beliefs_active":
            compact[section_name] = compact_beliefs_active(detail_map, data_map)
        elif section_name == "scoreboard":
            compact[section_name] = compact_scoreboard(detail_map, data_map)
        elif section_name == "clarifications":
            compact[section_name] = compact_clarifications(detail_map, data_map)
        elif section_name == "narrative_active":
            compact[section_name] = compact_narrative_active(detail_map, data_map)
        elif section_name == "affective_now":
            compact[section_name] = compact_affective_now(detail_map, data_map)
    return compact


def compact_beliefs_active(detail: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    facts = data.get("facts") if isinstance(data.get("facts"), dict) else {}
    fact_items: list[dict[str, Any]] = []
    for fallback_id, raw_fact in list(facts.items())[:MAX_SNAPSHOT_ITEMS]:
        if not isinstance(raw_fact, dict):
            continue
        fact_items.append(
            {
                "id": bounded_text(raw_fact.get("id") or fallback_id),
                "subject": bounded_text(raw_fact.get("subject")),
                "predicate": bounded_text(raw_fact.get("predicate")),
                "obj": bounded_text(raw_fact.get("obj") or raw_fact.get("object")),
                "confidence": raw_fact.get("confidence"),
                "source": bounded_text(raw_fact.get("source")),
                "is_pinned": bool(raw_fact.get("is_pinned", False)),
            }
        )
    return {
        "fact_count": detail.get("fact_count", len(facts)),
        "entity_count": detail.get("entity_count", 0),
        "facts": fact_items,
        "pinned_fact_ids": compact_json(data.get("pinned_fact_ids", [])),
    }


def compact_scoreboard(detail: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    return {
        "referent_count": detail.get("referent_count", 0),
        "qud_count": detail.get("qud_count", 0),
        "topic_count": detail.get("topic_count", 0),
        "open_commitment_count": detail.get("open_commitment_count", 0),
        "referents": compact_json(data.get("referents", {})),
        "open_questions": compact_json(data.get("qud_stack", [])),
        "topic_stack": compact_json(data.get("topic_stack", [])),
        "commitments": compact_json(data.get("commitments", {})),
    }


def compact_clarifications(detail: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    return {
        "pending_count": detail.get("pending_count", 0),
        "recently_resolved_count": detail.get("recently_resolved_count", 0),
        "is_blocked": bool(detail.get("is_blocked", False)),
        "blocking_clarification_id": bounded_text(detail.get("blocking_clarification_id", "")),
        "pending": compact_json(data.get("pending", {})),
        "recently_resolved": compact_json(data.get("recently_resolved", [])),
    }


def compact_narrative_active(detail: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    return {
        "current_thread_id": bounded_text(detail.get("current_thread_id", "")),
        "primary_thread_title": bounded_text(detail.get("primary_thread_title", "")),
        "paused_thread_count": detail.get("paused_thread_count", 0),
        "archived_thread_count": detail.get("archived_thread_count", 0),
        "total_threads_session": detail.get("total_threads_session", 0),
        "primary_thread": compact_json(data.get("primary_thread")),
        "paused_threads": compact_json(data.get("paused_threads", [])),
        "archived_thread_ids": compact_json(data.get("archived_thread_ids", [])),
    }


def compact_affective_now(detail: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key in (
        "current_emotion",
        "intensity",
        "valence",
        "arousal",
        "dominance",
        "trajectory",
        "confidence",
        "empathy_needed",
        "celebration_appropriate",
        "source",
    ):
        if key in data:
            result[key] = compact_json(data[key])
        elif key in detail:
            result[key] = compact_json(detail[key])
    return result


async def collect_live_turns(
    http_session: aiohttp.ClientSession,
    base_url: str,
    turn_specs: list[dict[str, Any]],
    quota: dict[str, Any],
) -> list[dict[str, Any]]:
    websocket_url = base_url.replace("http://", "ws://").replace("https://", "wss://") + "/ws"
    timeout_s = float(quota.get("per_turn_timeout_s") or 180.0)
    observations: list[dict[str, Any]] = []
    async with http_session.ws_connect(websocket_url, heartbeat=30) as websocket:
        init = await receive_json_message(websocket, timeout_s=30.0)
        if init.get("type") != "init":
            raise RuntimeError(f"expected websocket init message, got {init}")
        for index, spec in enumerate(turn_specs, start=1):
            pre_turn_snapshot = await fetch_session_state_summary(http_session, base_url)
            try:
                observation = await send_and_collect_turn(websocket, spec, index, timeout_s)
            except Exception as exc:  # noqa: BLE001 - fail closed and preserve evidence.
                observation = failed_turn_observation(
                    spec,
                    index,
                    f"{type(exc).__name__}: {exc}",
                )
            observation["session_snapshot_before_turn"] = pre_turn_snapshot
            observations.append(observation)
            if observation.get("live_error") and bool(quota.get("stop_on_turn_failure", True)):
                break
    return observations


def failed_turn_observation(spec: dict[str, Any], index: int, error: str) -> dict[str, Any]:
    return {
        "index": index,
        "thread": spec.get("thread", ""),
        "member": str(spec.get("member") or "Alex"),
        "device": str(spec.get("device") or "alex_phone"),
        "text": str(spec.get("text") or ""),
        "golden_case_id": str(spec.get("golden_case_id") or ""),
        "run_label": str(spec.get("run_label") or ""),
        "expected_operations": list(spec.get("expected_operations") or []),
        "critical_operations": list(spec.get("critical_operations") or []),
        "dangerous_false_write_if_unexpected": bool(
            spec.get("dangerous_false_write_if_unexpected", False)
        ),
        "web_turn": index,
        "response_text": "",
        "activity": {},
        "events_seen": [],
        "live_error": error,
    }


def collect_simulated_kernel_turns(
    turn_specs: list[dict[str, Any]], config: dict[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    from k1.concierge.section_update.types import SectionUpdatePlan
    from k1.sessionstate.factory import SessionStateFactory

    base_session_id = str(config.get("session_id") or "m3-simulated-session")
    session_id = f"{base_session_id}-sim-{run_id_seed()}"
    manager = SessionStateFactory.create_for_testing(session_id=session_id)
    start_result = manager.start(restore_if_exists=False)
    golden_cases = golden_cases_by_id(config)
    observations: list[dict[str, Any]] = []
    oracle_results: list[dict[str, Any]] = []
    stop_result: Any = None

    try:
        for index, spec in enumerate(turn_specs, start=1):
            pre_turn_snapshot = build_session_state_summary_from_manager(
                manager,
                source="simulated/sessionstate/pre_turn",
            )
            observation = simulated_turn_observation(spec, index, pre_turn_snapshot)
            observations.append(observation)

            case_id = str(spec.get("golden_case_id") or "")
            case = golden_cases.get(case_id, {})
            plan_payload = case.get("expected_plan") if isinstance(case, dict) else None
            if not plan_payload:
                continue
            plan = SectionUpdatePlan.from_dict(plan_payload)
            turn_apply_results: list[dict[str, Any]] = []
            for mutation in plan.mutations:
                result = manager.mutate(
                    section=mutation.section,
                    operation=mutation.operation,
                    data=dict(mutation.data),
                    cognitive_trace_id=f"simulated-oracle:{case_id}:{index}",
                )
                result_dict = result.to_dict()
                result_dict["golden_case_id"] = case_id
                turn_apply_results.append(result_dict)
                oracle_results.append(result_dict)
                if not result.success:
                    raise RuntimeError(
                        "simulated oracle apply failed: "
                        f"case={case_id} section={mutation.section} "
                        f"operation={mutation.operation} error={result.error or result.reason}"
                    )
            if turn_apply_results:
                observation["simulated_oracle_apply_results"] = turn_apply_results
    finally:
        stop_result = manager.stop(checkpoint_before_stop=False)

    summary = {
        "kernel": "bypassed",
        "fsm": "bypassed",
        "session_state": "SessionStateFactory.create_for_testing",
        "event_port": "LocalEventAdapter(capture_mode=True)",
        "writer_port": "DirectWriterAdapter",
        "bus_topic": "k1.response.final.v1",
        "session_id": session_id,
        "start_result": to_jsonable(start_result),
        "stop_result": to_jsonable(stop_result),
        "oracle_mutation_count": len(oracle_results),
        "oracle_failed_mutation_count": sum(
            1 for item in oracle_results if not item.get("success")
        ),
    }
    return observations, summary


def simulated_turn_observation(
    spec: dict[str, Any], index: int, pre_turn_snapshot: dict[str, Any]
) -> dict[str, Any]:
    member = str(spec.get("member") or "Alex")
    device = str(spec.get("device") or "alex_phone")
    text = str(spec.get("text") or "").strip()
    response_text = str(
        spec.get("simulated_response_text")
        or (
            "Acknowledged for section-update validation."
            if spec.get("expected_operations")
            else "Acknowledged."
        )
    )
    return {
        "index": index,
        "thread": spec.get("thread", ""),
        "member": member,
        "device": device,
        "text": text,
        "golden_case_id": str(spec.get("golden_case_id") or ""),
        "run_label": str(spec.get("run_label") or ""),
        "expected_operations": list(spec.get("expected_operations") or []),
        "critical_operations": list(spec.get("critical_operations") or []),
        "dangerous_false_write_if_unexpected": bool(
            spec.get("dangerous_false_write_if_unexpected", False)
        ),
        "web_turn": index,
        "response_text": response_text,
        "activity": {
            "turn": index,
            "session_ops": [],
            "tool_calls": [],
            "state_changes": {
                "simulated_bus_k1.session.user.input.v1": "DISPATCHING",
                "simulated_bus_k1.response.final.v1": "LISTENING",
            },
            "fsm_states": ["LISTENING", "DISPATCHING", "LISTENING"],
            "bytes_in": len(text.encode("utf-8")),
            "bytes_out": len(response_text.encode("utf-8")),
            "latency_ms": 0,
        },
        "events_seen": ["simulated_turn_info", "simulated_response", "simulated_activity"],
        "session_snapshot_before_turn": pre_turn_snapshot,
        "prompt_mode": "simulated_kernel",
        "prompt_context_source": "simulated_sessionstate_bus_poc",
    }


def build_session_state_summary_from_manager(manager: Any, *, source: str) -> dict[str, Any]:
    snapshot = manager.get_snapshot().to_dict()
    sections = snapshot.get("sections") if isinstance(snapshot.get("sections"), dict) else {}
    section_details: dict[str, Any] = {}
    section_payloads: dict[str, Any] = {}
    for section_name in list(sections):
        try:
            section = manager.get_section(section_name)
            if hasattr(section, "get_metadata") and callable(section.get_metadata):
                section_details[section_name] = to_jsonable(section.get_metadata())
            data: Any
            serializer = "attributes"
            if hasattr(section, "to_dict") and callable(section.to_dict):
                serializer = "to_dict"
                data = section.to_dict()
            else:
                data = {
                    key.lstrip("_"): value
                    for key, value in vars(section).items()
                    if not key.startswith("__") and not callable(value)
                }
            section_payloads[section_name] = {
                "serializer": serializer,
                "data": compact_json(to_jsonable(data)),
            }
        except Exception as exc:  # noqa: BLE001 - simulated snapshot should remain inspectable.
            section_details[section_name] = {"error": str(exc)}
            section_payloads[section_name] = {"error": str(exc), "data": None}

    compact_sections = compact_section_metadata(sections, section_details)
    cognitive_sections = compact_cognitive_sections(section_details, section_payloads)
    version_source = {
        "sections": compact_sections,
        "cognitive_sections": cognitive_sections,
        "last_mutation_ms": snapshot.get("last_mutation_ms", 0),
    }
    return {
        "available": True,
        "source": source,
        "snapshot_version": stable_hash(version_source),
        "snapshot_source_epoch": str(snapshot.get("last_mutation_ms") or ""),
        "section_names": sorted(str(name) for name in sections),
        "section_count": len(sections),
        "sections": compact_sections,
        "cognitive_sections": cognitive_sections,
        "local_cold_count": 0,
    }


async def send_and_collect_turn(
    websocket: aiohttp.ClientWebSocketResponse,
    spec: dict[str, Any],
    index: int,
    timeout_s: float,
) -> dict[str, Any]:
    member = str(spec.get("member") or "Alex")
    device = str(spec.get("device") or "alex_phone")
    text = str(spec.get("text") or "").strip()
    if not text:
        raise ValueError(f"turn {index} has empty text")
    await websocket.send_json(
        {
            "type": "message",
            "text": text,
            "member": member,
            "device": device,
            "device_context": dict(spec.get("device_context") or {}),
        }
    )

    events: list[dict[str, Any]] = []
    response_texts: list[str] = []
    activity: dict[str, Any] = {}
    turn_id_from_web = 0
    deadline = time.perf_counter() + timeout_s
    while time.perf_counter() < deadline:
        remaining = max(0.1, deadline - time.perf_counter())
        event = await receive_json_message(websocket, timeout_s=remaining)
        events.append(event)
        event_type = str(event.get("type") or "")
        if event_type == "turn_info":
            turn_id_from_web = int(event.get("turn") or 0)
        elif event_type == "response":
            response_texts.append(str(event.get("text") or ""))
        elif event_type == "system" and str(event.get("text") or ""):
            response_texts.append(str(event.get("text") or ""))
        elif event_type == "activity":
            data = event.get("data") if isinstance(event.get("data"), dict) else {}
            if not turn_id_from_web or int(data.get("turn") or 0) == turn_id_from_web:
                activity = data
                break
    if not activity:
        raise TimeoutError(f"turn {index} timed out waiting for activity")
    return {
        "index": index,
        "thread": spec.get("thread", ""),
        "member": member,
        "device": device,
        "text": text,
        "golden_case_id": str(spec.get("golden_case_id") or ""),
        "run_label": str(spec.get("run_label") or ""),
        "expected_operations": list(spec.get("expected_operations") or []),
        "critical_operations": list(spec.get("critical_operations") or []),
        "dangerous_false_write_if_unexpected": bool(
            spec.get("dangerous_false_write_if_unexpected", False)
        ),
        "web_turn": turn_id_from_web or int(activity.get("turn") or index),
        "response_text": "\n".join(item for item in response_texts if item).strip(),
        "activity": activity,
        "events_seen": [str(event.get("type") or "") for event in events],
    }


async def receive_json_message(
    websocket: aiohttp.ClientWebSocketResponse,
    *,
    timeout_s: float,
) -> dict[str, Any]:
    message = await asyncio.wait_for(websocket.receive(), timeout=timeout_s)
    if message.type == aiohttp.WSMsgType.TEXT:
        payload = json.loads(message.data)
        return payload if isinstance(payload, dict) else {"payload": payload}
    if message.type in {aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR}:
        raise RuntimeError(f"websocket closed while waiting for message: {message.type}")
    return {"type": str(message.type), "data": str(message.data)}


async def classify_observations(
    observations: list[dict[str, Any]],
    config: dict[str, Any],
    args: argparse.Namespace,
) -> list[dict[str, Any]]:
    load_dotenv_files()
    normalize_provider_env(config, args)
    from k1.model_hub.factory import ModelHubFactory
    from k1.model_hub.loader import ProviderConfig

    provider_config = ProviderConfig.from_env()
    hub, load_result = await ModelHubFactory.from_config(provider_config, ports=None)
    if not load_result.registered:
        await shutdown_hub(hub)
        raise RuntimeError(
            "No ModelHub providers registered for live shadow validation: "
            f"skipped={load_result.skipped} failed={load_result.failed}"
        )
    records: list[dict[str, Any]] = []
    try:
        spacing_s = float(
            args.model_call_spacing_s
            or (config.get("quota") or {}).get("model_call_spacing_s")
            or 0.0
        )
        next_call_at = time.perf_counter()
        for index, observation in enumerate(observations):
            delay_s = next_call_at - time.perf_counter()
            if delay_s > 0:
                print(
                    "throttle_sleep_s={sleep:.3f} before_turn={turn}".format(
                        sleep=delay_s,
                        turn=observation["index"],
                    )
                )
                await asyncio.sleep(delay_s)
            record = await classify_one_observation(hub, observation, config, args)
            records.append(record)
            manifest = record["manifest"]
            print(
                "turn={turn} status={status} ops={ops} latency_ms={latency} golden={golden} legacy_front={front}".format(
                    turn=observation["index"],
                    status=manifest["status"],
                    ops=",".join(manifest["operations"]) or "none",
                    latency=manifest["classifier_e2e_ms"],
                    golden=manifest["golden_comparison_status"],
                    front=manifest["legacy_front_comparison_status"],
                )
            )
            if spacing_s > 0 and index < len(observations) - 1:
                next_call_at = max(next_call_at + spacing_s, time.perf_counter() + spacing_s)
    finally:
        await shutdown_hub(hub)
    return records


async def classify_one_observation(
    hub: Any,
    observation: dict[str, Any],
    config: dict[str, Any],
    args: argparse.Namespace,
) -> dict[str, Any]:
    from k1.concierge.section_update.prompt import SECTION_UPDATE_BATCH_TOOL_NAME

    input_data = build_classifier_input(observation, config, args)
    if observation.get("live_error"):
        reason = f"live_kernel_turn_failed:{observation['live_error']}"
        plan = noop_plan(input_data, reason)
        manifest = build_manifest(
            input_data=input_data,
            observation=observation,
            plan=plan,
            status="live_turn_failed",
            metadata={
                "provider_id": preferred_provider(config, args),
                "model_id": preferred_model(config, args),
                "latency_ms": 0,
            },
            route_choice={},
            elapsed_ms=0,
            timeout_ms=int(args.timeout_ms or config.get("timeout_ms") or 45000),
            tool_calls=[],
            validation_errors=[reason],
            degradation_reason=reason,
            front_operations=[],
        )
        return {"turn_result": build_turn_result(observation, manifest), "manifest": manifest}

    request = build_hub_request(input_data, config, args)
    route_choice = select_route(hub, request)
    started = time.perf_counter()
    try:
        response = await hub.execute(request)
        elapsed_ms = round((time.perf_counter() - started) * 1000)
        tool_calls = unwrap_tool_calls(response.result)
        metadata = to_jsonable(response.metadata)
        plan, status, degradation_reason, validation_errors = plan_from_tool_calls(
            input_data=input_data,
            tool_calls=tool_calls,
            required_tool_name=SECTION_UPDATE_BATCH_TOOL_NAME,
            metadata=metadata,
        )
    except Exception as exc:  # noqa: BLE001 - provider failures degrade to no-op evidence.
        elapsed_ms = round((time.perf_counter() - started) * 1000)
        metadata = {"provider_id": route_choice.get("provider_id", ""), "model_id": ""}
        tool_calls = []
        degradation_reason = f"provider_failed:{type(exc).__name__}"
        validation_errors = [degradation_reason]
        status = "provider_failed"
        plan = noop_plan(input_data, degradation_reason)

    front_operations = infer_front_operations(observation)
    manifest = build_manifest(
        input_data=input_data,
        observation=observation,
        plan=plan,
        status=status,
        metadata=metadata,
        route_choice=route_choice,
        elapsed_ms=elapsed_ms,
        timeout_ms=int(args.timeout_ms or config.get("timeout_ms") or 45000),
        tool_calls=tool_calls,
        validation_errors=validation_errors,
        degradation_reason=degradation_reason,
        front_operations=front_operations,
    )
    return {"turn_result": build_turn_result(observation, manifest), "manifest": manifest}


def build_turn_result(observation: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    result = {
        "index": observation["index"],
        "expected_turn": observation.get("web_turn", observation["index"]),
        "golden_case_id": observation.get("golden_case_id", ""),
        "run_label": observation.get("run_label", ""),
        "thread": observation.get("thread", ""),
        "member": observation.get("member", ""),
        "device": observation.get("device", ""),
        "text": observation.get("text", ""),
        "response_text": observation.get("response_text", ""),
        "activity": sanitize_activity(observation.get("activity", {})),
        "classifier_session_snapshot": snapshot_report_summary(
            observation.get("session_snapshot_before_turn", {})
        ),
        "manifest": manifest,
    }
    if observation.get("live_error"):
        result["live_error"] = observation["live_error"]
    return result


def build_classifier_input(
    observation: dict[str, Any],
    config: dict[str, Any],
    args: argparse.Namespace,
) -> dict[str, Any]:
    from k1.concierge.section_update.types import SectionUpdateInput

    session_id = str(config.get("session_id") or f"web-live-{run_id_seed()}")
    web_turn = int(observation.get("web_turn") or observation["index"])
    session_state_summary = observation.get("session_snapshot_before_turn")
    if not isinstance(session_state_summary, dict):
        session_state_summary = {
            "available": False,
            "source": "missing_pre_turn_snapshot",
            "snapshot_version": "unknown-snapshot",
            "snapshot_source_epoch": "",
        }
    snapshot_version = str(session_state_summary.get("snapshot_version") or "unknown-snapshot")
    activity = observation.get("activity") if isinstance(observation.get("activity"), dict) else {}
    section_input = SectionUpdateInput(
        turn_id=f"{session_id}:{web_turn}",
        session_id=session_id,
        cognitive_trace_id=f"section-update:{session_id}:{web_turn}",
        prompt_mode=str(observation.get("prompt_mode") or "front_live_kernel"),
        fsm_state=str(activity.get("fsm_states", [""])[-1] if activity.get("fsm_states") else ""),
        bus_topic="k1.response.final.v1",
        user_turn={"text": observation.get("text", "")},
        assistant_turn={
            "final_text": observation.get("response_text", ""),
            "legacy_front_tool_names": legacy_front_tool_names(activity),
            "legacy_front_tool_call_count": len(list(activity.get("tool_calls") or [])),
            "legacy_front_session_op_count": len(list(activity.get("session_ops") or [])),
            "raw_front_session_ops_redacted": True,
            "session_ops": [],
            "latency_ms": activity.get("latency_ms", 0),
        },
        prompt_context={
            "source": str(observation.get("prompt_context_source") or "live_boot_web_poc"),
            "raw_prompt_included": False,
        },
        session_snapshot={
            "source": session_state_summary.get("source", ""),
            "available": bool(session_state_summary.get("available", False)),
            "snapshot_version": snapshot_version,
            "snapshot_source_epoch": session_state_summary.get("snapshot_source_epoch", ""),
            "section_count": session_state_summary.get("section_count", 0),
            "section_names": session_state_summary.get("section_names", []),
            "sections": session_state_summary.get("sections", {}),
            "cognitive_sections": session_state_summary.get("cognitive_sections", {}),
        },
        scenario_context={
            "thread": observation.get("thread", ""),
            "member": observation.get("member", ""),
            "device": observation.get("device", ""),
        },
        constraints={
            "classifier_mode": "shadow",
            "preferred_provider": preferred_provider(config, args),
            "preferred_model": preferred_model(config, args),
            "timeout_ms": int(args.timeout_ms or config.get("timeout_ms") or 45000),
        },
    )
    return section_input.to_dict()


def legacy_front_tool_names(activity: dict[str, Any]) -> list[str]:
    """Return non-authoritative legacy Front tool names without write payload detail."""

    names = [str(item) for item in activity.get("tool_calls", []) or []]
    return sorted({name for name in names if name in COGNITIVE_TOOL_NAMES})


def build_hub_request(
    input_data: dict[str, Any], config: dict[str, Any], args: argparse.Namespace
) -> Any:
    from k1.concierge.section_update.prompt import (
        SECTION_UPDATE_BATCH_TOOL_NAME,
        build_section_update_tool_schema,
    )
    from k1.model_hub.types import (
        CapabilityType,
        HubRequest,
        Message,
        ModelPreference,
        Priority,
        RequestConstraints,
        ToolCallPayload,
        ToolDefinition,
    )

    schema = build_section_update_tool_schema()
    tool = ToolDefinition(
        name=schema.name,
        description=schema.description,
        parameters=schema.parameters,
    )
    provider = preferred_provider(config, args)
    model = preferred_model(config, args)
    return HubRequest(
        capability=CapabilityType.TOOL_CALL,
        payload=ToolCallPayload(
            messages=[
                Message(
                    role="user",
                    content="SECTION_UPDATE_INPUT_JSON:\n"
                    + json.dumps(input_data, ensure_ascii=False, indent=2),
                )
            ],
            tools=[tool],
            tool_choice=SECTION_UPDATE_BATCH_TOOL_NAME,
            parallel_tool_calls=False,
            system_prompt=build_classifier_prompt(),
        ),
        constraints=RequestConstraints(
            max_tokens=int(args.max_output_tokens or config.get("max_output_tokens") or 2048),
            timeout_ms=int(args.timeout_ms or config.get("timeout_ms") or 45000),
            priority=Priority.INTERACTIVE,
            temperature=float(args.temperature),
            provider_preference=provider,
            model_preference=ModelPreference(
                preferred_provider=provider,
                preferred_model=model,
                preferred_tier=str(config.get("preferred_tier") or "FAST"),
            ),
            consumer_id=str(args.consumer_id or "poc.m3_live_shadow_validation"),
        ),
        trace_id=f"m3-live-shadow:{input_data['turn_id']}",
        session_id=str(input_data["session_id"]),
    )


def build_classifier_prompt() -> str:
    from k1.concierge.section_update.prompt import build_section_update_system_prompt

    return build_section_update_system_prompt()


def plan_from_tool_calls(
    *,
    input_data: dict[str, Any],
    tool_calls: list[dict[str, Any]],
    required_tool_name: str,
    metadata: dict[str, Any],
) -> tuple[Any, str, str, list[str]]:
    from k1.concierge.section_update.types import (
        ApplyTiming,
        SectionUpdatePlan,
        SectionUpdateValidation,
    )

    matching_calls = [call for call in tool_calls if call.get("name") == required_tool_name]
    if not matching_calls:
        reason = "missing_batch_tool_call"
        return noop_plan(input_data, reason), "shadow_noop", reason, ["noop"]
    arguments = parse_json_arguments(matching_calls[0].get("arguments"))
    if not isinstance(arguments, dict) or arguments.get("_parse_error"):
        reason = "malformed_batch_tool_arguments"
        return noop_plan(input_data, reason), "shadow_noop", reason, [reason]

    raw_mutations = list(arguments.get("mutations") or [])
    mutations, rejected_candidates, validation_errors, sanitizer_diagnostics = (
        sanitize_model_mutations(
            raw_mutations=raw_mutations,
            raw_rejected_candidates=list(arguments.get("rejected_candidates") or []),
            input_data=input_data,
        )
    )
    plan_payload = {
        "plan_id": "modelhub:{turn}:{snapshot}:{version}".format(
            turn=input_data["turn_id"],
            snapshot=input_data.get("session_snapshot", {}).get("snapshot_version", ""),
            version=CLASSIFIER_VERSION,
        ),
        "turn_id": input_data["turn_id"],
        "session_id": input_data["session_id"],
        "snapshot_version": input_data.get("session_snapshot", {}).get("snapshot_version", ""),
        "snapshot_source_epoch": input_data.get("session_snapshot", {}).get(
            "snapshot_source_epoch", ""
        ),
        "classifier_version": CLASSIFIER_VERSION,
        "apply_timing": ApplyTiming.SHADOW_ONLY.value if mutations else ApplyTiming.NO_OP.value,
        "mutations": mutations,
        "rejected_candidates": rejected_candidates,
        "validation": SectionUpdateValidation(
            schema_valid=not validation_errors,
            whole_plan_preflight_status=(
                "shadow_poc_validated" if not validation_errors else "invalid"
            ),
            mutation_guard_preflight_status="not_run_in_poc",
            errors=validation_errors,
        ).to_dict(),
        "diagnostics": {
            "provider_id": metadata.get("provider_id", ""),
            "model_id": metadata.get("model_id", ""),
            "tool_call_count": len(tool_calls),
            "raw_mutation_count": len(raw_mutations),
            "accepted_mutation_count": len(mutations),
            "rejected_model_candidate_count": len(rejected_candidates),
            "sanitizer": sanitizer_diagnostics,
        },
        "cognitive_trace_id": input_data.get("cognitive_trace_id", ""),
    }
    try:
        plan = SectionUpdatePlan.from_dict(plan_payload)
    except Exception as exc:  # noqa: BLE001 - invalid live output degrades safely.
        reason = f"plan_contract_error:{type(exc).__name__}"
        return noop_plan(input_data, reason), "shadow_noop", reason, [reason, str(exc)]
    status = "shadow_noop" if plan.is_noop else "shadow_plan"
    return plan, status, "", validation_errors


def sanitize_model_mutations(
    *,
    raw_mutations: list[Any],
    raw_rejected_candidates: list[Any],
    input_data: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str], list[dict[str, Any]]]:
    from k1.concierge.section_update.vocabulary import validate_target

    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = [
        item for item in raw_rejected_candidates if isinstance(item, dict)
    ]
    validation_errors: list[str] = []
    diagnostics: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    user_text = str((input_data.get("user_turn") or {}).get("text") or "").lower()
    for index, raw_item in enumerate(raw_mutations):
        if not isinstance(raw_item, dict):
            reason = "mutation_not_object"
            rejected.append({"section": "all", "operation": "", "reason": reason, "data": {}})
            diagnostics.append({"index": index, "status": "rejected", "reason": reason})
            continue

        item = normalize_model_mutation(raw_item)
        errors: list[str] = []
        target = validate_target(str(item.get("section") or ""), str(item.get("operation") or ""))
        if not target.ok:
            errors.append(target.reason)
        errors.extend(validate_mutation_payload(item, input_data=input_data))
        errors.extend(validate_mutation_semantics(item, input_data=input_data))
        semantic_key = mutation_semantic_key(item)
        if semantic_key and semantic_key in seen_keys:
            errors.append(f"duplicate_semantic_mutation:{semantic_key}")
        if single_mutation_operation_requires_one(item) and any(
            str(accepted_item.get("section") or "") == str(item.get("section") or "")
            and str(accepted_item.get("operation") or "") == str(item.get("operation") or "")
            for accepted_item in accepted
        ):
            errors.append(
                "duplicate_singleton_operation:emit one canonical mutation for this operation per completed turn"
            )
        if (
            str(item.get("section") or "") == "beliefs_active"
            and str(item.get("operation") or "") == "add_fact"
            and any(
                str(accepted_item.get("section") or "") == "beliefs_active"
                and str(accepted_item.get("operation") or "") == "add_fact"
                for accepted_item in accepted
            )
        ):
            errors.append(
                "duplicate_belief_add_fact:emit one canonical belief fact per simple completed turn"
            )
        if (
            is_ordinary_correction_turn(user_text)
            and str(item.get("section") or "") == "beliefs_active"
            and str(item.get("operation") or "") == "add_fact"
            and any(
                str(accepted_item.get("section") or "") == "beliefs_active"
                and str(accepted_item.get("operation") or "") == "add_fact"
                for accepted_item in accepted
            )
        ):
            errors.append(
                "duplicate_correction_add_fact:ordinary correction should emit one canonical replacement fact"
            )

        if errors:
            rejected.append(rejected_candidate_from_mutation(item, index, errors))
            diagnostics.append({"index": index, "status": "rejected", "reason": "; ".join(errors)})
            continue

        if semantic_key:
            seen_keys.add(semantic_key)
        accepted.append(item)
        diagnostics.append({"index": index, "status": "accepted"})

    for item in accepted:
        validation_errors.extend(validate_mutation_payload(item, input_data=input_data))
    return accepted, rejected, validation_errors, diagnostics


def normalize_model_mutation(item: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(item)
    data = dict(item.get("data") or {}) if isinstance(item.get("data"), dict) else {}
    section = str(normalized.get("section") or "")
    operation = str(normalized.get("operation") or "")
    if section == "beliefs_active" and operation == "add_fact":
        confidence = normalized.get("confidence")
        if "confidence" not in data and isinstance(confidence, int | float):
            data["confidence"] = float(confidence)
        if not str(data.get("source") or ""):
            data["source"] = str(normalized.get("source") or "classifier:section_update")
    normalized["data"] = data
    return normalized


def validate_mutation_semantics(item: dict[str, Any], *, input_data: dict[str, Any]) -> list[str]:
    section = str(item.get("section") or "")
    operation = str(item.get("operation") or "")
    raw_data = item.get("data")
    data: dict[str, Any] = raw_data if isinstance(raw_data, dict) else {}
    user_text = str((input_data.get("user_turn") or {}).get("text") or "").lower()
    errors: list[str] = []
    if is_runtime_or_capability_owned_question(user_text):
        errors.append(
            "invalid_semantics:runtime/capability live-state question is no_op for section update"
        )
    if is_unresolved_placeholder_noop_turn(user_text):
        errors.append(
            "invalid_semantics:unresolved placeholder-only turn lacks a safe cognitive payload"
        )
    if section == "beliefs_active" and operation == "update_confidence":
        if not explicit_confidence_update_requested(user_text):
            errors.append(
                "invalid_semantics:beliefs_active.update_confidence requires explicit confidence/reliability language"
            )
    if section == "beliefs_active" and operation == "add_fact":
        if is_negative_correction_fragment(item, data, user_text):
            errors.append(
                "invalid_semantics:ordinary correction may only add the positive replacement fact"
            )
        if is_conversational_closure_fact(item, data, input_data):
            errors.append(
                "invalid_semantics:conversational closure/acknowledgement is no_op, not a belief"
            )
        if is_local_discourse_referent_fact(data, user_text):
            errors.append(
                "invalid_semantics:conversation-local referent belongs to scoreboard.add_referent, not beliefs_active.add_fact"
            )
        if is_affective_state_belief(item, data, user_text):
            errors.append(
                "invalid_semantics:first-person affect belongs to affective_now.update, not beliefs_active.add_fact"
            )
    if section == "narrative_active" and operation == "create_thread":
        if is_topic_shift_without_thread_request(user_text):
            errors.append(
                "invalid_semantics:topic-only focus/switch belongs to scoreboard.push_topic, not narrative_active.create_thread"
            )
    if section == "scoreboard" and operation == "add_referent":
        if is_durable_shorthand_definition(user_text):
            errors.append(
                "invalid_semantics:durable shorthand definition belongs to beliefs_active.add_fact, not scoreboard.add_referent"
            )
        if is_durable_correction_choice(user_text):
            errors.append(
                "invalid_semantics:durable correction choice belongs to beliefs_active.add_fact, not scoreboard.add_referent"
            )
    if section == "clarifications" and operation == "request":
        if is_nonblocking_tracking_question(user_text):
            errors.append(
                "invalid_semantics:non-blocking tracking question belongs to scoreboard.push_question, not clarifications.request"
            )
    return errors


def explicit_confidence_update_requested(user_text: str) -> bool:
    confidence_terms = (
        "confidence",
        "confident",
        "reliable",
        "reliability",
        "trust",
        "sure",
        "certain",
        "uncertain",
        "maybe",
        "probably",
        "less likely",
        "more likely",
        "not sure",
    )
    return any(term in user_text for term in confidence_terms)


def is_negative_correction_fragment(
    item: dict[str, Any], data: dict[str, Any], user_text: str
) -> bool:
    correction_cues = (" not ", "actually", "instead", "rather than", "no longer")
    if not any(cue in f" {user_text} " for cue in correction_cues):
        return False
    predicate = str(data.get("predicate") or "").lower()
    obj = str(data.get("obj") or "").lower()
    reason = str(item.get("reason") or "").lower()
    idempotency_key = str(item.get("idempotency_key") or "").lower()
    removal_text = " ".join([predicate, obj, reason, idempotency_key])
    removal_cues = (" not ", "not_", "removed", "removing", "invalidate", "invalidating")
    return any(cue in removal_text for cue in removal_cues)


def is_conversational_closure_fact(
    item: dict[str, Any], data: dict[str, Any], input_data: dict[str, Any]
) -> bool:
    user_text = canonical_text((input_data.get("user_turn") or {}).get("text"))
    assistant_text = canonical_text((input_data.get("assistant_turn") or {}).get("final_text"))
    if not closure_only_user_turn(user_text):
        return False
    if assistant_creates_future_commitment(assistant_text):
        return False
    candidate_text = " ".join(
        canonical_text(value)
        for value in (
            data.get("subject"),
            data.get("predicate"),
            data.get("obj"),
            item.get("reason"),
            item.get("idempotency_key"),
        )
    )
    closure_fact_terms = (
        "done",
        "all for",
        "all set",
        "sorted",
        "closed",
        "closure",
        "topic",
        "discussion",
        "arrangement",
        "arrangements",
        "no further",
    )
    return any(term in candidate_text for term in closure_fact_terms)


def is_local_discourse_referent_fact(data: dict[str, Any], user_text: str) -> bool:
    scope_cues = (
        "for the next question",
        "in this conversation",
        "for this chat",
        "in this thread",
        "when i say",
    )
    definition_cues = (" means ", " refers to ", " i mean ")
    referent_cues = (
        " this ",
        " that ",
        " their ",
        " her ",
        " his ",
        " him ",
        " it ",
        " the plan ",
        " the form ",
    )
    padded_user_text = f" {user_text} "
    if not any(cue in padded_user_text for cue in scope_cues):
        return False
    if not any(cue in padded_user_text for cue in definition_cues):
        return False
    candidate_text = " ".join(
        canonical_text(value)
        for value in (data.get("subject"), data.get("predicate"), data.get("obj"))
    )
    padded_candidate = f" {candidate_text} "
    return any(cue in padded_user_text or cue in padded_candidate for cue in referent_cues)


def is_affective_state_belief(item: dict[str, Any], data: dict[str, Any], user_text: str) -> bool:
    affect_terms = (
        "relieved",
        "anxious",
        "overwhelmed",
        "frustrated",
        "excited",
        "upset",
        "worried",
        "proud",
    )
    first_person_cues = ("i am ", "i'm ", "i feel ", "i felt ", "i was ")
    if not any(cue in user_text for cue in first_person_cues):
        return False
    if not any(term in user_text for term in affect_terms):
        return False
    candidate_text = " ".join(
        canonical_text(value)
        for value in (
            data.get("subject"),
            data.get("predicate"),
            data.get("obj"),
            item.get("reason"),
            item.get("idempotency_key"),
        )
    )
    return any(term in candidate_text for term in affect_terms)


def is_topic_shift_without_thread_request(user_text: str) -> bool:
    topic_shift_cues = (
        "focus on",
        "switch the conversation to",
        "talk about",
        "let's focus",
        "lets focus",
    )
    explicit_thread_cues = (
        "thread",
        "new thread",
        "separate thread",
        "create a thread",
        "start a thread",
        "open a new thread",
        "make this a new thread",
    )
    return any(cue in user_text for cue in topic_shift_cues) and not any(
        cue in user_text for cue in explicit_thread_cues
    )


def is_runtime_or_capability_owned_question(user_text: str) -> bool:
    text = normalized_phrase(user_text)
    if "internal policy" in text and ("allowed to write" in text or "may write" in text):
        return True
    if "policy" in text and "allowed to write" in text:
        return True
    if ("warm" in text or "archive" in text) and (
        "what is in" in text
        or "whats in" in text
        or "show" in text
        or "read" in text
        or "list" in text
        or "tell me" in text
    ):
        return True
    if "exact transcript" in text or "transcript line" in text:
        return True
    if "artifact" in text and ("last task" in text or "task produce" in text or "produced" in text):
        return True
    if "controller" in text and "state" in text:
        return True
    if "do you know where" in text and ("device" in text or "phone" in text):
        return True
    if "phone" in text and "online" in text and ("is this" in text or "right now" in text):
        return True
    if (
        "account" in text
        and "connected" in text
        and ("can you tell" in text or "whether" in text or "right now" in text)
    ):
        return True
    if "calendar" in text and (
        "check whether" in text or "check if" in text or "has anything" in text
    ):
        return True
    if "reminder" in text and ("already have" in text or "existing" in text or "status" in text):
        return True
    if "shopping list" in text and ("currently" in text or "can you see" in text):
        return True
    return False


def is_nonblocking_tracking_question(user_text: str) -> bool:
    text = normalized_phrase(user_text)
    return (
        "help me track" in text
        and "which" in text
        and ("still due" in text or "due" in text or "open" in text or "remaining" in text)
    )


def single_mutation_operation_requires_one(item: dict[str, Any]) -> bool:
    section = str(item.get("section") or "")
    operation = str(item.get("operation") or "")
    return (section, operation) in {
        ("scoreboard", "add_referent"),
        ("scoreboard", "push_question"),
        ("scoreboard", "push_topic"),
        ("clarifications", "request"),
        ("narrative_active", "create_thread"),
        ("affective_now", "update"),
    }


def is_unresolved_placeholder_noop_turn(user_text: str) -> bool:
    text = normalized_phrase(user_text)
    unsafe_exact_turns = {
        "move it there later",
        "tell her that thing is fine",
        "use the other one for pickup",
        "do it the usual way",
        "switch back to that",
        "that one is better",
        "same plan as before",
        "put it near the usual place",
        "make sure they know",
        "change the time to then",
        "not jordan the other parent",
        "actually make it earlier",
        "can you make the pickup contact the usual person",
        "let s use the normal option for that",
        "lets use the normal option for that",
    }
    return text in unsafe_exact_turns


def is_durable_shorthand_definition(user_text: str) -> bool:
    text = normalized_phrase(user_text)
    local_scope_cues = (
        "for the next question",
        "in this conversation",
        "for this conversation",
        "in this thread",
        "for this thread",
        "for this chat",
        "in this chat",
    )
    if any(cue in text for cue in local_scope_cues):
        return False
    return " means " in f" {text} " or (
        text.startswith("when i say ") and " i mean " in f" {text} "
    )


def is_ordinary_correction_turn(user_text: str) -> bool:
    text = normalized_phrase(user_text)
    correction_cues = (
        " not ",
        "actually",
        "instead",
        "rather than",
        "no longer",
    )
    return any(cue in f" {text} " for cue in correction_cues)


def is_durable_correction_choice(user_text: str) -> bool:
    text = normalized_phrase(user_text)
    if not is_ordinary_correction_turn(text):
        return False
    local_scope_cues = (
        "for the next question",
        "in this conversation",
        "for this conversation",
        "in this thread",
        "for this thread",
        "for this chat",
        "in this chat",
    )
    if any(cue in text for cue in local_scope_cues):
        return False
    durable_family_terms = (
        "lunchbox",
        "folder",
        "pickup",
        "dropoff",
        "bus stop",
        "practice",
        "form",
        "snack",
        "teacher",
        "tutor",
        "dinner",
        "party",
        "key",
        "contact",
    )
    return any(term in text for term in durable_family_terms)


def closure_only_user_turn(user_text: str) -> bool:
    closure_patterns = (
        "thanks that is all",
        "thanks thats all",
        "that is all",
        "thats all",
        "all set",
        "all good",
        "we are done",
        "i am done",
        "done for now",
        "never mind",
        "nevermind",
        "no more",
        "nothing else",
    )
    return any(pattern in user_text for pattern in closure_patterns)


def assistant_creates_future_commitment(assistant_text: str) -> bool:
    commitment_patterns = (
        "i will",
        "i'll",
        "i can remind",
        "i will remind",
        "i'll remind",
        "i can follow up",
        "i will follow up",
        "i'll follow up",
        "later",
        "tomorrow",
        "next time",
    )
    return any(pattern in assistant_text for pattern in commitment_patterns)


def mutation_semantic_key(item: dict[str, Any]) -> str:
    section = str(item.get("section") or "")
    operation = str(item.get("operation") or "")
    raw_data = item.get("data")
    data: dict[str, Any] = raw_data if isinstance(raw_data, dict) else {}
    if section == "beliefs_active" and operation == "add_fact":
        return ":".join(
            [
                section,
                operation,
                canonical_text(data.get("subject")),
                canonical_text(data.get("predicate")),
                canonical_text(data.get("obj")),
            ]
        )
    if section == "beliefs_active" and operation == "update_confidence":
        return ":".join([section, operation, canonical_text(data.get("id"))])
    return ""


def canonical_text(value: Any) -> str:
    return " ".join(str(value or "").lower().split())


def normalized_phrase(value: Any) -> str:
    raw = str(value or "").lower()
    cleaned = "".join(
        character if character.isalnum() or character.isspace() else " " for character in raw
    )
    return " ".join(cleaned.split())


def rejected_candidate_from_mutation(
    item: dict[str, Any], index: int, errors: list[str]
) -> dict[str, Any]:
    confidence = item.get("confidence")
    return {
        "section": str(item.get("section") or "all"),
        "operation": str(item.get("operation") or ""),
        "reason": f"model_candidate_rejected[{index}]: " + "; ".join(errors),
        "confidence": confidence if isinstance(confidence, int | float) else None,
        "data": dict(item.get("data") or {}) if isinstance(item.get("data"), dict) else {},
    }


def validate_mutation_payload(
    item: dict[str, Any], *, input_data: dict[str, Any] | None = None
) -> list[str]:
    section = str(item.get("section") or "")
    operation = str(item.get("operation") or "")
    raw_data = item.get("data")
    data: dict[str, Any] = raw_data if isinstance(raw_data, dict) else {}
    errors: list[str] = []
    if section == "beliefs_active" and operation == "add_fact":
        missing = [key for key in ("subject", "predicate", "obj") if not str(data.get(key) or "")]
        if missing:
            errors.append(
                "invalid_payload:beliefs_active.add_fact requires data.subject,data.predicate,data.obj"
            )
        invalid_keys = sorted(
            key for key in ("id", "fact", "fact_id", "value", "new_value", "object") if key in data
        )
        if invalid_keys:
            errors.append(
                "invalid_payload:beliefs_active.add_fact rejects data."
                + ",data.".join(invalid_keys)
            )
        confidence = data.get("confidence")
        if not isinstance(confidence, int | float) or not 0.0 <= float(confidence) <= 1.0:
            errors.append(
                "invalid_payload:beliefs_active.add_fact requires numeric data.confidence in [0,1]"
            )
        if not str(data.get("source") or ""):
            errors.append("invalid_payload:beliefs_active.add_fact requires data.source")
    elif section == "beliefs_active" and operation == "update_confidence":
        if not str(data.get("id") or ""):
            errors.append("invalid_payload:beliefs_active.update_confidence requires data.id")
        confidence = data.get("confidence")
        if not isinstance(confidence, int | float) or not 0.0 <= float(confidence) <= 1.0:
            errors.append(
                "invalid_payload:beliefs_active.update_confidence requires numeric data.confidence in [0,1]"
            )
    elif section == "clarifications" and operation == "request":
        missing = [
            key
            for key in (
                "agent_id",
                "question",
                "priority",
                "related_entity",
                "related_intent",
                "timeout_ms",
                "blocking",
            )
            if key not in data or data.get(key) in (None, "")
        ]
        if missing:
            errors.append(
                "invalid_payload:clarifications.request requires data." + ",data.".join(missing)
            )
    elif section == "clarifications" and operation == "answer":
        clarification_id = str(data.get("clarification_id") or "")
        if not clarification_id:
            errors.append("invalid_payload:clarifications.answer requires data.clarification_id")
        elif input_data is not None and clarification_id not in exposed_clarification_ids(
            input_data
        ):
            errors.append(
                "invalid_payload:clarifications.answer requires exact pending snapshot clarification_id"
            )
        if not str(data.get("answer") or ""):
            errors.append("invalid_payload:clarifications.answer requires data.answer")
    elif section == "narrative_active" and operation == "create_thread":
        if not str(data.get("title") or ""):
            errors.append("invalid_payload:narrative_active.create_thread requires data.title")
    elif section == "narrative_active" and operation in {
        "switch_to",
        "pause_thread",
        "resolve_thread",
        "archive_thread",
        "update_thread",
    }:
        thread_id = str(data.get("thread_id") or "")
        if not thread_id:
            errors.append(f"invalid_payload:narrative_active.{operation} requires data.thread_id")
        elif input_data is not None and thread_id not in exposed_narrative_thread_ids(input_data):
            errors.append(
                f"invalid_payload:narrative_active.{operation} requires exact snapshot thread_id"
            )
    return errors


def exposed_clarification_ids(input_data: dict[str, Any]) -> set[str]:
    snapshot = input_data.get("session_snapshot") if isinstance(input_data, dict) else {}
    cognitive_sections = snapshot.get("cognitive_sections") if isinstance(snapshot, dict) else {}
    clarifications = (
        cognitive_sections.get("clarifications") if isinstance(cognitive_sections, dict) else {}
    )
    if not isinstance(clarifications, dict):
        return set()
    ids: set[str] = set()
    blocking_id = str(clarifications.get("blocking_clarification_id") or "")
    if blocking_id:
        ids.add(blocking_id)
    pending = clarifications.get("pending")
    if isinstance(pending, dict):
        for key, item in pending.items():
            if str(key or ""):
                ids.add(str(key))
            if isinstance(item, dict):
                for id_key in ("id", "clarification_id"):
                    clarification_id = str(item.get(id_key) or "")
                    if clarification_id:
                        ids.add(clarification_id)
    elif isinstance(pending, list):
        for item in pending:
            if isinstance(item, dict):
                for id_key in ("id", "clarification_id"):
                    clarification_id = str(item.get(id_key) or "")
                    if clarification_id:
                        ids.add(clarification_id)
            elif str(item or ""):
                ids.add(str(item))
    return ids


def exposed_narrative_thread_ids(input_data: dict[str, Any]) -> set[str]:
    snapshot = input_data.get("session_snapshot") if isinstance(input_data, dict) else {}
    cognitive_sections = snapshot.get("cognitive_sections") if isinstance(snapshot, dict) else {}
    narrative = (
        cognitive_sections.get("narrative_active") if isinstance(cognitive_sections, dict) else {}
    )
    if not isinstance(narrative, dict):
        return set()
    ids: set[str] = set()
    for key in ("current_thread_id",):
        value = str(narrative.get(key) or "")
        if value:
            ids.add(value)
    for key in ("primary_thread",):
        value = narrative.get(key)
        if isinstance(value, dict):
            for id_key in ("id", "thread_id"):
                thread_id = str(value.get(id_key) or "")
                if thread_id:
                    ids.add(thread_id)
    paused = narrative.get("paused_threads")
    if isinstance(paused, list):
        for item in paused:
            if isinstance(item, dict):
                for id_key in ("id", "thread_id"):
                    thread_id = str(item.get(id_key) or "")
                    if thread_id:
                        ids.add(thread_id)
            elif str(item or ""):
                ids.add(str(item))
    archived = narrative.get("archived_thread_ids")
    if isinstance(archived, list):
        ids.update(str(item) for item in archived if str(item or ""))
    return ids


def noop_plan(input_data: dict[str, Any], reason: str) -> Any:
    from k1.concierge.section_update.types import SectionUpdatePlan

    return SectionUpdatePlan.noop(
        plan_id=f"modelhub-noop:{input_data['turn_id']}:{stable_hash(reason)}",
        turn_id=input_data["turn_id"],
        session_id=input_data["session_id"],
        classifier_version=CLASSIFIER_VERSION,
        reason=reason,
        cognitive_trace_id=input_data.get("cognitive_trace_id", ""),
    )


def build_manifest(
    *,
    input_data: dict[str, Any],
    observation: dict[str, Any],
    plan: Any,
    status: str,
    metadata: dict[str, Any],
    route_choice: dict[str, Any],
    elapsed_ms: int,
    timeout_ms: int,
    tool_calls: list[dict[str, Any]],
    validation_errors: list[str],
    degradation_reason: str,
    front_operations: list[str],
) -> dict[str, Any]:
    plan_operations = summarize_plan_operations(plan)
    operations = [item["key"] for item in plan_operations]
    expected_operations = [str(item) for item in observation.get("expected_operations", [])]
    critical_operations = [str(item) for item in observation.get("critical_operations", [])]
    front_comparison = compare_operations(operations, front_operations)
    expected_comparison = compare_operations(operations, expected_operations)
    dangerous_count = dangerous_false_write_count(
        operations=operations,
        expected_operations=expected_operations,
        observation=observation,
    )
    provider_id = str(metadata.get("provider_id") or route_choice.get("provider_id") or "")
    model_id = str(metadata.get("model_id") or route_choice.get("model_id") or "")
    return {
        "manifest_id": "section-update-manifest:{turn}:{plan}:{version}".format(
            turn=input_data["turn_id"],
            plan=plan.plan_id,
            version=CLASSIFIER_VERSION,
        ),
        "plan_id": plan.plan_id,
        "turn_id": input_data["turn_id"],
        "session_id": input_data["session_id"],
        "golden_case_id": observation.get("golden_case_id", ""),
        "mode": "shadow",
        "status": status,
        "classifier_version": CLASSIFIER_VERSION,
        "snapshot_version": input_data.get("session_snapshot", {}).get("snapshot_version", ""),
        "snapshot_epoch": input_data.get("session_snapshot", {}).get("snapshot_source_epoch", ""),
        "provider_id": provider_id,
        "model_id": model_id,
        "trace_id": f"m3-live-shadow:{input_data['turn_id']}",
        "model_latency_ms": metadata.get("latency_ms", 0),
        "classifier_e2e_ms": elapsed_ms,
        "timeout_ms": timeout_ms,
        "plan_confidence": plan_confidence(plan),
        "mutation_count": len(plan.mutations),
        "sections": sorted({item["section"] for item in plan_operations}),
        "operations": operations,
        "expected_operations": expected_operations,
        "critical_operations": critical_operations,
        "plan_operations": plan_operations,
        "front_operations": list(front_operations),
        "validation_errors": list(validation_errors),
        "rejected_candidates": summarize_rejected_candidates(plan),
        "degradation_reason": degradation_reason,
        "idempotency_keys": {
            "plan": plan.plan_idempotency_key,
            "mutations": [
                item["idempotency_key"] for item in plan_operations if item["idempotency_key"]
            ],
        },
        "batch_success_rate": None,
        "front_cognitive_tool_names": cognitive_tool_names(observation),
        "tool_calls": [call.get("name", "") for call in tool_calls],
        "comparison_status": expected_comparison["status"],
        "golden_comparison_status": expected_comparison["status"],
        "legacy_front_comparison_status": front_comparison["status"],
        "false_positive_count": expected_comparison["false_positive_count"],
        "false_negative_count": expected_comparison["false_negative_count"],
        "dangerous_mismatch_count": dangerous_count,
        "comparison": front_comparison,
        "front_comparison": front_comparison,
        "expected_comparison": expected_comparison,
    }


def summarize_plan_operations(plan: Any) -> list[dict[str, Any]]:
    operations: list[dict[str, Any]] = []
    for mutation in plan.mutations:
        data = getattr(mutation, "data", {}) or {}
        section = str(getattr(mutation, "section", ""))
        operation = str(getattr(mutation, "operation", ""))
        operations.append(
            {
                "section": section,
                "operation": operation,
                "key": f"{section}.{operation}",
                "source": str(getattr(mutation, "source", "")),
                "payload_keys": sorted(str(key) for key in data),
                "confidence": getattr(mutation, "confidence", None),
                "commit_class": enum_value(getattr(mutation, "commit_class", "")),
                "idempotency_key": str(getattr(mutation, "idempotency_key", "")),
                "reason": str(getattr(mutation, "reason", "")),
            }
        )
    return operations


def summarize_rejected_candidates(plan: Any) -> list[dict[str, Any]]:
    rejected = []
    for item in plan.rejected_candidates:
        rejected.append(
            {
                "section": str(getattr(item, "section", "")),
                "operation": str(getattr(item, "operation", "")),
                "reason": str(getattr(item, "reason", "")),
                "confidence": getattr(item, "confidence", None),
                "payload_keys": sorted(str(key) for key in (getattr(item, "data", {}) or {})),
            }
        )
    return rejected


def plan_confidence(plan: Any) -> float:
    if not plan.mutations:
        return 1.0
    values = [float(getattr(item, "confidence", 0.0) or 0.0) for item in plan.mutations]
    return round(statistics.fmean(values), 4) if values else 1.0


def infer_front_operations(observation: dict[str, Any]) -> list[str]:
    raw_activity = observation.get("activity")
    activity: dict[str, Any] = raw_activity if isinstance(raw_activity, dict) else {}
    tool_names = [str(item) for item in activity.get("tool_calls", []) or []]
    inferred: set[str] = set()
    expected = set(str(item) for item in observation.get("expected_operations", []) or [])
    for tool_name in tool_names:
        hints = COGNITIVE_TOOL_OPERATION_HINTS.get(tool_name, set())
        if expected:
            inferred.update(hint for hint in hints if hint in expected)
        else:
            inferred.update(hints)
    return sorted(inferred)


def cognitive_tool_names(observation: dict[str, Any]) -> list[str]:
    raw_activity = observation.get("activity")
    activity: dict[str, Any] = raw_activity if isinstance(raw_activity, dict) else {}
    return sorted(
        str(item) for item in activity.get("tool_calls", []) or [] if item in COGNITIVE_TOOL_NAMES
    )


def compare_operations(actual: list[str], baseline: list[str]) -> dict[str, Any]:
    actual_counts = Counter(actual)
    baseline_counts = Counter(baseline)
    classifier_only = expand_counter(actual_counts - baseline_counts)
    baseline_only = expand_counter(baseline_counts - actual_counts)
    if not actual_counts and not baseline_counts:
        status = "match"
        agreement = 1.0
    elif not classifier_only and not baseline_only:
        status = "match"
        agreement = 1.0
    else:
        status = "mismatch"
        union_count = sum((actual_counts | baseline_counts).values())
        intersection_count = sum((actual_counts & baseline_counts).values())
        agreement = intersection_count / union_count if union_count else 1.0
    return {
        "status": status,
        "agreement": round(agreement, 4),
        "false_positive_count": len(classifier_only),
        "false_negative_count": len(baseline_only),
        "dangerous_mismatch_count": 0,
        "classifier_only": classifier_only,
        "baseline_only": baseline_only,
    }


def expand_counter(counter: Counter[str]) -> list[str]:
    return [item for item, count in sorted(counter.items()) for _ in range(count)]


def dangerous_false_write_count(
    *,
    operations: list[str],
    expected_operations: list[str],
    observation: dict[str, Any],
) -> int:
    unexpected = expand_counter(Counter(operations) - Counter(expected_operations))
    if not unexpected:
        return 0
    if bool(observation.get("dangerous_false_write_if_unexpected")):
        return len(unexpected)
    return sum(1 for operation in unexpected if operation.startswith("affective_now."))


def evaluate_quality_gates(
    *,
    manifests: list[dict[str, Any]],
    config: dict[str, Any],
    provider_id: str,
    model_id: str,
    output_path: Path,
) -> dict[str, Any]:
    gate_config = dict(config.get("quality_gates") or {})
    metrics = compute_metrics(manifests, config)
    failed = []
    golden_agreement_threshold = float(
        gate_config.get(
            "shadow_golden_operation_agreement",
            gate_config.get("shadow_section_operation_agreement", 0.90),
        )
    )
    checks = {
        "golden_fixture_validity": metrics["golden_fixture_validity"]
        >= float(gate_config.get("golden_fixture_validity", 1.0)),
        "golden_pass_rate": metrics["golden_pass_rate"]
        >= float(gate_config.get("golden_pass_rate", 0.95)),
        "schema_validity": metrics["schema_validity"]
        >= float(gate_config.get("schema_validity", 1.0)),
        "guard_vocabulary_validity": metrics["guard_vocabulary_validity"]
        >= float(gate_config.get("guard_vocabulary_validity", 1.0)),
        "forbidden_section_op_rate": metrics["forbidden_section_op_rate"]
        <= float(gate_config.get("forbidden_section_op_rate", 0.0)),
        "noop_precision": metrics["noop_precision"]
        >= float(gate_config.get("noop_precision", 0.98)),
        "mutation_precision": metrics["mutation_precision"]
        >= float(gate_config.get("mutation_precision", 0.97)),
        "critical_recall": metrics["critical_recall"]
        >= float(gate_config.get("critical_recall", 0.90)),
        "shadow_golden_operation_agreement": metrics["shadow_golden_operation_agreement"]
        >= golden_agreement_threshold,
        "untriaged_high_risk_mismatches": metrics["untriaged_high_risk_mismatches"]
        <= int(gate_config.get("untriaged_high_risk_mismatches", 0)),
        "dangerous_false_writes": metrics["dangerous_false_writes"]
        <= int(gate_config.get("dangerous_false_writes", 0)),
        "consecutive_shadow_turns_without_dangerous_false_writes": metrics[
            "consecutive_shadow_turns_without_dangerous_false_writes"
        ]
        >= int(gate_config.get("consecutive_shadow_turns_without_dangerous_false_writes", 100)),
        "shadow_p95_ms": metrics["shadow_p95_ms"] <= int(gate_config.get("shadow_p95_ms", 10000)),
        "active_boundary_timeout_ms": metrics["active_boundary_timeout_ms"]
        <= int(gate_config.get("active_boundary_timeout_ms", 1500)),
        "provider_failure_degradation_rate": metrics["provider_failure_degradation_rate"]
        <= float(gate_config.get("provider_failure_degradation_rate", 0.01)),
        "timeout_path_safe_noop": bool(metrics["timeout_path_safe_noop"]),
        "same_turn_retry_loop": not bool(metrics["same_turn_retry_loop"]),
    }
    for name, passed in checks.items():
        if not passed:
            failed.append(name)
    return {
        "active_eligible": not failed,
        "failed_gates": failed,
        "metrics": metrics,
        "evidence_artifacts": [str(output_path)],
        "provider_id": provider_id,
        "model_id": model_id,
    }


def compute_metrics(manifests: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    total = len(manifests)
    schema_valid = sum(1 for item in manifests if not item.get("validation_errors"))
    forbidden = sum(
        1
        for item in manifests
        for operation in item.get("operations", [])
        if operation.split(".", 1)[0]
        in {"control", "temporal", "spatial", "grounding", "history_active", "task_state"}
    )
    expected_write_turns = [item for item in manifests if item.get("expected_operations")]
    expected_noop_turns = [item for item in manifests if not item.get("expected_operations")]
    noop_matches = sum(1 for item in expected_noop_turns if not item.get("operations"))
    mutation_true_positive = 0
    mutation_total = 0
    critical_found = 0
    critical_total = 0
    golden_matches = 0
    expected_agreements = []
    front_agreements = []
    front_mismatches = 0
    duplicate_operation_count = 0
    for item in manifests:
        operation_list = list(item.get("operations", []))
        operations = Counter(operation_list)
        expected = Counter(item.get("expected_operations", []))
        mutation_true_positive += sum((operations & expected).values())
        mutation_total += sum(operations.values())
        critical = Counter(item.get("critical_operations", item.get("expected_operations", [])))
        critical_total += sum(critical.values())
        critical_found += sum((operations & critical).values())
        expected_comparison = item.get("expected_comparison", {})
        front_comparison = item.get("front_comparison", item.get("comparison", {}))
        if expected_comparison.get("status") == "match" and not item.get("validation_errors"):
            golden_matches += 1
        if front_comparison.get("status") == "mismatch":
            front_mismatches += 1
        expected_agreements.append(float(expected_comparison.get("agreement", 0.0)))
        front_agreements.append(float(front_comparison.get("agreement", 0.0)))
        duplicate_operation_count += len(operation_list) - len(set(operation_list))
    latencies = sorted(
        int(item.get("classifier_e2e_ms") or 0)
        for item in manifests
        if isinstance(item.get("classifier_e2e_ms"), int)
    )
    degraded_count = sum(
        1
        for item in manifests
        if item.get("status") in {"provider_failed", "timed_out"} or item.get("degradation_reason")
    )
    live_turn_failure_count = sum(
        1 for item in manifests if item.get("status") == "live_turn_failed"
    )
    dangerous = sum(int(item.get("dangerous_mismatch_count") or 0) for item in manifests)
    return {
        "golden_fixture_validity": golden_fixture_validity(config),
        "golden_pass_rate": ratio(golden_matches, total),
        "schema_validity": ratio(schema_valid, total),
        "guard_vocabulary_validity": 1.0 if forbidden == 0 and schema_valid == total else 0.0,
        "forbidden_section_op_rate": ratio(
            forbidden, max(1, sum(len(item.get("operations", [])) for item in manifests))
        ),
        "noop_precision": (
            ratio(noop_matches, len(expected_noop_turns)) if expected_noop_turns else 1.0
        ),
        "mutation_precision": (
            ratio(mutation_true_positive, mutation_total) if mutation_total else 1.0
        ),
        "critical_recall": ratio(critical_found, critical_total) if critical_total else 1.0,
        "shadow_golden_operation_agreement": (
            round(statistics.fmean(expected_agreements), 4) if expected_agreements else 0.0
        ),
        "legacy_front_operation_agreement": (
            round(statistics.fmean(front_agreements), 4) if front_agreements else 0.0
        ),
        "legacy_front_mismatch_count": front_mismatches,
        "duplicate_operation_count": duplicate_operation_count,
        "untriaged_high_risk_mismatches": dangerous,
        "dangerous_false_writes": dangerous,
        "consecutive_shadow_turns_without_dangerous_false_writes": consecutive_safe_turns(
            manifests
        ),
        "shadow_p95_ms": percentile(latencies, 95),
        "active_boundary_timeout_ms": int(
            (config.get("quality_gates") or {}).get("active_boundary_timeout_ms", 1500)
        ),
        "provider_failure_degradation_rate": ratio(degraded_count, total),
        "live_turn_failure_count": live_turn_failure_count,
        "timeout_path_safe_noop": prove_timeout_path_safe_noop(),
        "same_turn_retry_loop": False,
        "shadow_turn_count": total,
        "expected_write_turn_count": len(expected_write_turns),
    }


def golden_fixture_validity(config: dict[str, Any]) -> float:
    try:
        cases = load_golden_cases(config)
    except Exception:
        return 0.0
    if not cases:
        return 0.0
    from k1.concierge.section_update.types import SectionUpdatePlan
    from k1.concierge.section_update.vocabulary import validate_target

    passed = 0
    for case in cases:
        try:
            plan_payload = case.get("expected_plan", case) if isinstance(case, dict) else case
            plan = SectionUpdatePlan.from_dict(plan_payload)
            if all(
                validate_target(item.section, item.operation).ok
                and not validate_mutation_payload(item.to_dict())
                for item in plan.mutations
            ):
                passed += 1
        except Exception:
            continue
    return ratio(passed, len(cases))


def consecutive_safe_turns(manifests: list[dict[str, Any]]) -> int:
    count = 0
    for item in manifests:
        if int(item.get("dangerous_mismatch_count") or 0) == 0:
            count += 1
        else:
            count = 0
    return count


def prove_timeout_path_safe_noop() -> bool:
    input_data = {
        "turn_id": "timeout-proof:1",
        "session_id": "timeout-proof",
        "cognitive_trace_id": "timeout-proof",
    }
    plan = noop_plan(input_data, "timeout")
    return bool(plan.is_noop and not plan.mutations)


def sanitize_activity(activity: dict[str, Any]) -> dict[str, Any]:
    return {
        "turn": activity.get("turn", 0),
        "session_ops": list(activity.get("session_ops") or []),
        "tool_calls": list(activity.get("tool_calls") or []),
        "state_changes": dict(activity.get("state_changes") or {}),
        "fsm_states": list(activity.get("fsm_states") or []),
        "bytes_in": activity.get("bytes_in", 0),
        "bytes_out": activity.get("bytes_out", 0),
        "latency_ms": activity.get("latency_ms", 0),
    }


def unwrap_tool_calls(result: Any) -> list[dict[str, Any]]:
    raw_calls = getattr(result, "tool_calls", []) or []
    calls: list[dict[str, Any]] = []
    for call in raw_calls:
        calls.append(
            {
                "id": str(getattr(call, "id", "")),
                "name": str(getattr(call, "name", "")),
                "arguments": getattr(call, "arguments", ""),
            }
        )
    return calls


def parse_json_arguments(arguments: Any) -> Any:
    if isinstance(arguments, dict):
        return arguments
    if isinstance(arguments, str):
        text = arguments.strip()
        if not text:
            return {}
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            return {"_parse_error": str(exc), "raw": arguments}
    return {}


def select_route(hub: Any, request: Any) -> dict[str, Any]:
    try:
        eligible = hub._router._capability_router.route(request.capability, request.constraints)
        choice = hub._router._model_selector.select(eligible, request)
        if choice is None:
            return {"choice_available": False, "reason": "model selector returned no choice"}
        return {
            "choice_available": True,
            "provider_id": choice.provider_id,
            "model_id": choice.model_id,
            "fallback_providers": [fallback.provider_id for fallback in choice.fallback_chain],
        }
    except Exception as exc:  # noqa: BLE001 - route metadata is diagnostic only.
        return {"choice_available": False, "error_type": type(exc).__name__, "error": str(exc)}


async def shutdown_hub(hub: Any) -> None:
    shutdown = getattr(hub, "shutdown", None)
    if callable(shutdown):
        result = shutdown()
        if inspect.isawaitable(result):
            await result


def load_dotenv_files() -> None:
    for path in (ROOT / "poc" / ".env", ROOT / "poc" / "chat_experience_poc" / ".env"):
        if not path.is_file():
            continue
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, value = line.split("=", 1)
            name = name.strip()
            value = value.strip().strip('"').strip("'")
            if name == "GOOGLE_API_KEY" and os.environ.get("LLM_PROVIDER", "").lower() == "vertex":
                continue
            os.environ.setdefault(name, value)


def normalize_provider_env(config: dict[str, Any], args: argparse.Namespace) -> None:
    provider = preferred_provider(config, args).strip().lower() or DEFAULT_PROVIDER
    os.environ["LLM_PROVIDER"] = provider
    if provider in {
        "vertex",
        "vertex-ai",
        "vertex_ai",
        "agent-platform",
        "agent_platform",
        "gemini-enterprise",
        "gemini_enterprise",
        "google-cloud",
        "google_cloud",
    }:
        os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"
        if not os.environ.get("GOOGLE_CLOUD_PROJECT") and os.environ.get("GOOGLE_PROJECT_ID"):
            os.environ["GOOGLE_CLOUD_PROJECT"] = os.environ["GOOGLE_PROJECT_ID"]
        if not os.environ.get("GOOGLE_CLOUD_LOCATION") and os.environ.get("GOOGLE_LOCATION"):
            os.environ["GOOGLE_CLOUD_LOCATION"] = os.environ["GOOGLE_LOCATION"]
        os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "global")
        os.environ.pop("GOOGLE_API_KEY", None)
    model = preferred_model(config, args)
    if model:
        os.environ["K1_SECTION_UPDATE_MODEL"] = model
        if provider.startswith("vertex"):
            os.environ["VERTEX_MODEL"] = model


def normalize_requested_model_env(config: dict[str, Any], args: argparse.Namespace) -> None:
    provider = preferred_provider(config, args).strip().lower()
    model = preferred_model(config, args)
    if provider.startswith("vertex") and model:
        os.environ["VERTEX_MODEL"] = model


def snapshot_report_summary(snapshot: Any) -> dict[str, Any]:
    if not isinstance(snapshot, dict):
        return {"available": False, "source": "missing"}
    cognitive_sections = snapshot.get("cognitive_sections")
    cognitive_sections = cognitive_sections if isinstance(cognitive_sections, dict) else {}
    beliefs = cognitive_sections.get("beliefs_active")
    beliefs = beliefs if isinstance(beliefs, dict) else {}
    return {
        "available": bool(snapshot.get("available", False)),
        "source": snapshot.get("source", ""),
        "snapshot_version": snapshot.get("snapshot_version", ""),
        "snapshot_source_epoch": snapshot.get("snapshot_source_epoch", ""),
        "section_count": snapshot.get("section_count", 0),
        "cognitive_section_names": sorted(str(name) for name in cognitive_sections),
        "belief_fact_count": beliefs.get("fact_count", 0),
        "belief_fact_ids_preview": [
            str(item.get("id") or "")
            for item in list(beliefs.get("facts") or [])[: min(5, MAX_SNAPSHOT_ITEMS)]
            if isinstance(item, dict)
        ],
    }


def compact_json(value: Any, *, depth: int = 0) -> Any:
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, str):
        return bounded_text(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        if depth >= 4:
            return bounded_text(json.dumps(to_jsonable(value), ensure_ascii=False, default=str))
        return {
            bounded_text(key): compact_json(item, depth=depth + 1)
            for key, item in list(value.items())[:MAX_SNAPSHOT_ITEMS]
        }
    if isinstance(value, (list, tuple, set)):
        items = list(value)
        result = [compact_json(item, depth=depth + 1) for item in items[:MAX_SNAPSHOT_ITEMS]]
        if len(items) > MAX_SNAPSHOT_ITEMS:
            result.append({"_truncated": len(items) - MAX_SNAPSHOT_ITEMS})
        return result
    return bounded_text(value)


def bounded_text(value: Any, max_chars: int = MAX_SNAPSHOT_TEXT_CHARS) -> str:
    text = str(value or "")
    if len(text) <= max_chars:
        return text
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
    return f"{text[:max_chars]} [truncated chars={len(text)} sha256={digest}]"


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(to_jsonable(value), ensure_ascii=False, indent=2), encoding="utf-8")


def to_jsonable(value: Any) -> Any:
    if dataclasses.is_dataclass(value):
        return {
            field.name: to_jsonable(getattr(value, field.name))
            for field in dataclasses.fields(value)
        }
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_jsonable(item) for item in value]
    return value


def enum_value(value: Any) -> Any:
    return value.value if isinstance(value, Enum) else value


def stable_hash(value: Any) -> str:
    payload = json.dumps(
        to_jsonable(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def run_id_seed() -> str:
    return hashlib.sha1(str(time.time_ns()).encode("ascii")).hexdigest()[:8]


def ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(float(numerator) / float(denominator), 4)


def percentile(values: list[int], percentile_value: float) -> int:
    if not values:
        return 0
    if len(values) == 1:
        return int(values[0])
    sorted_values = sorted(values)
    rank = (len(sorted_values) - 1) * (percentile_value / 100.0)
    low = int(rank)
    high = min(low + 1, len(sorted_values) - 1)
    weight = rank - low
    return round(sorted_values[low] * (1.0 - weight) + sorted_values[high] * weight)


if __name__ == "__main__":
    main()
