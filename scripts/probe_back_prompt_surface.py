"""Probe the live Back prompt and tool/capability surface.

This script boots a real KernelService, creates a real session, mirrors the
pre-LLM portion of ``back_handler()``, and optionally runs manual
``discover_capabilities`` calls through the Back dispatcher.

No LLM call is made. The kernel uses the test model adapter so the probe can
boot without external model credentials while still exercising the live kernel,
session, fabric, prompt, and tool wiring.

Examples:
    python scripts/probe_back_prompt_surface.py
    python scripts/probe_back_prompt_surface.py --json
    python scripts/probe_back_prompt_surface.py --task-file data\\my_task.json
    python scripts/probe_back_prompt_surface.py --discover-intent "create a reminder for Riley"
    python scripts/probe_back_prompt_surface.py --discover-intent "create a reminder for Riley" --discover-domain reminders
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import tempfile
import uuid
from dataclasses import replace
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import k1.concierge.actors.back as back_mod
from k1.concierge.bus.builders import build_task_dispatch
from k1.concierge.config.kernel import KernelConfig
from k1.concierge.llm.types import ModelMessage, ToolCallResult, ToolSchema
from k1.kernel.service import KernelService

DEFAULT_FAMILY_TOOL_SERVICE_PATHS: tuple[str, ...] = (
    "k1.tools.family.calendar.service:CalendarToolService",
    "k1.tools.family.tasks.service:TasksToolService",
    "k1.tools.family.reminders.service:RemindersToolService",
    "k1.tools.family.chores.service:ChoresToolService",
    "k1.tools.family.shopping.service:ShoppingToolService",
    "k1.tools.family.family_settings.service:FamilySettingsService",
)

DEFAULT_TASK: dict[str, Any] = {
    "task_id": "probe-back-calendar-001",
    "tier": "LOW",
    "safety_band": "AMBER",
    "intents": [
        {
            "action": "create a calendar event for Riley soccer practice tomorrow at 5pm",
            "domain": "calendar",
            "params": {
                "title": "Riley Soccer Practice",
                "start": "2026-05-18T17:00:00",
                "duration_minutes": 60,
                "attendees": ["Riley"],
            },
        },
        {
            "action": "add a reminder 1 hour before the event",
            "domain": "reminders",
            "params": {
                "offset_minutes": -60,
                "event_ref": "Riley Soccer Practice",
            },
        },
    ],
}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    task_group = parser.add_mutually_exclusive_group()
    task_group.add_argument("--task-file", type=Path, help="Path to a JSON task payload.")
    task_group.add_argument("--task-json", help="Inline JSON task payload.")
    parser.add_argument("--session-id", default="probe-back-surface", help="Session id to create.")
    parser.add_argument(
        "--device-id", default=None, help="Optional device id for session creation."
    )
    parser.add_argument(
        "--work-dir",
        type=Path,
        default=None,
        help="Optional directory for probe SQLite files. Defaults to a temp directory.",
    )
    parser.add_argument("--json", action="store_true", help="Emit the full report as JSON.")
    parser.add_argument(
        "--discover-intent",
        action="append",
        default=[],
        help="Manual discover_capabilities intent to execute. Repeatable.",
    )
    parser.add_argument(
        "--discover-domain",
        default=None,
        help="Domain used with manual --discover-intent requests.",
    )
    parser.add_argument(
        "--skip-discover",
        action="store_true",
        help="Do not run manual discover_capabilities calls from task intents.",
    )
    parser.add_argument(
        "--disable-family-tools",
        action="store_true",
        help="Boot without the K1 family tool bundle.",
    )
    parser.add_argument(
        "--enable-self-model",
        action="store_true",
        help=(
            "Boot with the self-model bundle. Off by default because this raw kernel "
            "probe does not seed a coordinator-style actor projection."
        ),
    )
    parser.add_argument(
        "--disable-temporal",
        action="store_true",
        help="Boot without temporal wiring.",
    )
    parser.add_argument(
        "--disable-grounding",
        action="store_true",
        help="Boot without grounding wiring.",
    )
    parser.add_argument(
        "--disable-spatial",
        action="store_true",
        help="Boot without spatial wiring.",
    )
    parser.add_argument(
        "--prompt-preview-chars",
        type=int,
        default=0,
        help="When > 0, truncate the prompt in the emitted report to this many characters.",
    )
    parser.add_argument(
        "--log-level",
        default="WARNING",
        help="Python logging level for the probe runtime (default: WARNING).",
    )
    return parser.parse_args()


def _configure_logging(level: str) -> None:
    numeric_level = getattr(logging, str(level).upper(), logging.WARNING)
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        stream=sys.stdout,
    )
    logging.getLogger("asyncio").setLevel(logging.WARNING)


def _deep_copy_json(value: Any) -> Any:
    return json.loads(json.dumps(value))


def _load_task(args: argparse.Namespace) -> dict[str, Any]:
    if args.task_file is not None:
        task = json.loads(args.task_file.read_text(encoding="utf-8"))
    elif args.task_json is not None:
        task = json.loads(args.task_json)
    else:
        task = _deep_copy_json(DEFAULT_TASK)

    if not isinstance(task, dict):
        raise ValueError("task payload must be a JSON object")

    task.setdefault("task_id", f"probe-task-{uuid.uuid4().hex[:8]}")
    task.setdefault("tier", "LOW")
    task.setdefault("safety_band", "AMBER")
    return task


def _message_to_dict(message: ModelMessage) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "role": message.role,
        "content": message.content,
    }
    if message.tool_call_id:
        payload["tool_call_id"] = message.tool_call_id
    if message.name:
        payload["name"] = message.name
    if message.tool_calls:
        payload["tool_calls"] = [
            {
                "id": tool_call.id,
                "name": tool_call.name,
                "arguments": tool_call.arguments,
            }
            for tool_call in message.tool_calls
        ]
    return payload


def _tool_schema_to_dict(schema: ToolSchema) -> dict[str, Any]:
    return {
        "name": schema.name,
        "category": schema.category,
        "actor": schema.actor,
        "side_effects": schema.side_effects,
        "description": schema.description,
        "parameters": schema.parameters,
        "returns": schema.returns,
    }


def _tool_result_to_dict(result: Any) -> dict[str, Any]:
    return {
        "tool_name": getattr(result, "tool_name", ""),
        "status": getattr(result, "status", ""),
        "data": getattr(result, "data", {}),
        "error": getattr(result, "error", None),
    }


def _preview(text: str, limit: int) -> str:
    if limit <= 0 or len(text) <= limit:
        return text
    return text[:limit] + "\n...[truncated by --prompt-preview-chars]"


def _discovery_requests(
    args: argparse.Namespace, task: dict[str, Any]
) -> list[dict[str, str | None]]:
    requests: list[dict[str, str | None]] = []
    seen: set[tuple[str, str]] = set()

    def _add(intent: Any, domain: Any) -> None:
        intent_text = str(intent or "").strip()
        domain_text = "" if domain is None else str(domain).strip()
        if not intent_text:
            return
        key = (intent_text.lower(), domain_text.lower())
        if key in seen:
            return
        seen.add(key)
        requests.append(
            {
                "intent": intent_text,
                "domain": domain_text or None,
            }
        )

    for explicit_intent in args.discover_intent:
        _add(explicit_intent, args.discover_domain)

    if requests or args.skip_discover:
        return requests

    intents = task.get("intents")
    if isinstance(intents, list):
        for intent_payload in intents:
            if not isinstance(intent_payload, dict):
                continue
            _add(
                intent_payload.get("action") or intent_payload.get("intent"),
                intent_payload.get("domain"),
            )
    else:
        _add(task.get("action") or task.get("intent"), task.get("domain"))
    return requests


def _work_dir(args: argparse.Namespace) -> tuple[Path, tempfile.TemporaryDirectory[str] | None]:
    if args.work_dir is not None:
        args.work_dir.mkdir(parents=True, exist_ok=True)
        return args.work_dir.resolve(), None
    temp_dir = tempfile.TemporaryDirectory(
        prefix="back-prompt-surface-",
        ignore_cleanup_errors=True,
    )
    return Path(temp_dir.name).resolve(), temp_dir


def _build_kernel_config(args: argparse.Namespace, work_dir: Path) -> KernelConfig:
    family_tools_enabled = not args.disable_family_tools
    return KernelConfig(
        test_mode=False,
        model_mode="test",
        session_mode="standalone",
        enable_self_model=args.enable_self_model,
        enable_temporal=not args.disable_temporal,
        enable_grounding=not args.disable_grounding,
        enable_spatial=not args.disable_spatial,
        enable_family_tools=family_tools_enabled,
        family_tool_service_paths=(
            DEFAULT_FAMILY_TOOL_SERVICE_PATHS if family_tools_enabled else ()
        ),
        section_update_worker_mode="off",
        enable_section_update_worker=False,
        otel_enabled=False,
        bridge_outbox_path=str(work_dir / "bridge_outbox.db"),
        workflow_db_path=str(work_dir / "workflows.db"),
        sessionstate_db_path=str(work_dir / "sessionstate.db"),
        family_tools_db_path=str(work_dir / "family_tools.db"),
        selfmodel_projection_db_path=str(work_dir / "selfmodel.db"),
    )


async def _run_discoveries(
    dispatcher: Any,
    requests: list[dict[str, str | None]],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for index, request in enumerate(requests, start=1):
        tool_call = ToolCallResult(
            id=f"probe-discover-{index}",
            name="discover_capabilities",
            arguments={
                "intent": request["intent"],
                "domain": request["domain"],
            },
        )
        result = await dispatcher.dispatch(tool_call)
        results.append(
            {
                "request": request,
                "result": _tool_result_to_dict(result),
            }
        )
    return results


def _print_console_report(report: dict[str, Any]) -> None:
    print("=" * 80)
    print("BACK PROMPT / TOOL SURFACE PROBE")
    print("=" * 80)

    kernel = report["kernel"]
    print("\n[Kernel]")
    print(f"  work_dir: {report['work_dir']}")
    print(f"  healthy: {kernel['health']['healthy']}")
    print(f"  family_tools_enabled: {kernel['config']['enable_family_tools']}")
    print(f"  self_model_enabled: {kernel['config']['enable_self_model']}")
    print(f"  temporal_enabled: {kernel['config']['enable_temporal']}")
    print(f"  grounding_enabled: {kernel['config']['enable_grounding']}")
    print(f"  spatial_enabled: {kernel['config']['enable_spatial']}")
    family_tools = kernel["family_tools"]
    print(f"  family_capability_count: {family_tools['capability_count']}")
    if family_tools["capability_names"]:
        for name in family_tools["capability_names"]:
            print(f"    - {name}")

    task = report["task"]
    print("\n[Back Task]")
    print(f"  session_id: {report['session']['session_id']}")
    print(f"  task_id: {task['task_id']}")
    print(f"  task_tier: {report['back_runtime']['task_tier']}")
    print(f"  dispatcher_bucket: {report['back_runtime']['dispatcher_bucket']}")
    print(f"  effective_safety_band: {report['back_runtime']['effective_safety_band']}")
    print(f"  max_tool_calls: {report['back_runtime']['max_tool_calls']}")
    print(f"  trace_id: {report['back_runtime']['trace_id']}")

    print("\n[Back Tools]")
    print("  dispatcher_allowlist:")
    for tool_name in report["back_runtime"]["dispatcher_allowlist"]:
        print(f"    - {tool_name}")
    print("  model_visible_schemas:")
    for tool_schema in report["back_runtime"]["tool_schemas"]:
        properties = sorted((tool_schema.get("parameters") or {}).get("properties", {}).keys())
        print(
            f"    - {tool_schema['name']} category={tool_schema['category']} "
            f"side_effects={tool_schema['side_effects']} params={properties}"
        )

    profiles = report["back_runtime"]["execution_profiles"]
    print("\n[Execution Profiles]")
    print(f"  reason: {profiles['reason']}")
    print(f"  confidence: {report['back_runtime']['execution_profile_confidence']}")
    print(f"  profile_ids: {report['back_runtime']['execution_profile_ids']}")

    discoveries = report["discoveries"]
    if discoveries:
        print("\n[Manual discover_capabilities]")
        for entry in discoveries:
            request = entry["request"]
            result = entry["result"]
            count = 0
            if isinstance(result.get("data"), dict):
                count = int(result["data"].get("count") or 0)
            print(
                f"  - intent={request['intent']!r} domain={request['domain']!r} "
                f"status={result['status']} count={count}"
            )
            capabilities = []
            if isinstance(result.get("data"), dict):
                capabilities = result["data"].get("capabilities", []) or []
            for capability in capabilities:
                name = capability.get("name", "")
                domain = capability.get("domain", "")
                description = capability.get("description", "")
                print(f"      * {name} [{domain}] {description}")
            if result.get("error"):
                print(f"      error: {result['error']}")

    print("\n[Exact Back System Prompt]")
    print(report["back_runtime"]["prompt"])


async def _async_main(args: argparse.Namespace) -> int:
    work_dir, temp_dir = _work_dir(args)
    kernel = KernelService(config=_build_kernel_config(args, work_dir))
    task = _load_task(args)
    report: dict[str, Any]

    try:
        await kernel.startup()
        health = await kernel.health_check()
        session = await kernel.create_session(args.session_id, device_id=args.device_id)

        family_tools = kernel.family_tools
        family_capability_names = sorted(getattr(family_tools, "capability_names", []) or [])

        envelope = replace(
            build_task_dispatch(task),
            session_id=session.session_id,
            request_id=f"probe-{task.get('task_id', '')}",
            cognitive_trace_id=str(task.get("trace_id", "") or f"probe-{uuid.uuid4().hex[:12]}"),
        )
        trace_id = (
            envelope.cognitive_trace_id
            or str(task.get("trace_id", "") or "")
            or getattr(getattr(session.back_dispatcher, "ctx", None), "cognitive_trace_id", "")
            or f"back-{uuid.uuid4().hex[:12]}"
        )

        task_id = str(task.get("task_id", ""))
        task_tier = task.get("tier", "LOW")
        task_dispatcher = back_mod._maybe_rebind_back_dispatcher(
            session.back_dispatcher,
            task_tier,
            session.bus,
        )
        back_mod._bind_tool_context(
            task_dispatcher,
            trace_id=trace_id,
            session_id=session.session_id,
            task_id=task_id,
        )

        snapshot = back_mod._read_ss_snapshot(session.session_state)
        effective_safety_band = back_mod._effective_task_safety_band(task, snapshot)
        back_mod._bind_tool_context(
            task_dispatcher,
            trace_id=trace_id,
            session_id=session.session_id,
            task_id=task_id,
            safety_band=effective_safety_band,
        )

        back_cfg = back_mod.get_config().actors.back
        max_iterations = back_cfg.max_iterations.get(task_tier, back_cfg.max_iterations["LOW"])
        budget_hint = task.get("budget_hint")
        if budget_hint is not None:
            max_iterations = back_mod._budget_to_iterations(int(budget_hint))

        profile_selection = back_mod._execution_profile_selection_for_task(task)
        execution_profiles = back_mod._persist_execution_profile_selection(task, profile_selection)
        back_mod._bind_tool_context(
            task_dispatcher,
            trace_id=trace_id,
            session_id=session.session_id,
            task_id=task_id,
            safety_band=effective_safety_band,
            execution_profiles=execution_profiles,
        )

        execution_profile_block = back_mod._execution_profile_block_for_selection(profile_selection)
        execution_grounding_block = await back_mod._build_execution_grounding_block(
            task,
            session.grounding,
        )
        resolved_temporal_refs = task.get("resolved_temporal_refs")
        if not isinstance(resolved_temporal_refs, dict):
            resolved_temporal_refs = None

        prompt = back_mod.build_back_prompt(
            task=task,
            beliefs=snapshot["beliefs_prompt"],
            referents=snapshot["referents"],
            task_state=snapshot["task_state_prompt"],
            task_artifacts=snapshot["task_artifacts_prompt"],
            safety_band=effective_safety_band,
            persona_prefs=snapshot["persona_prefs"],
            max_tool_calls=max_iterations,
            execution_profile_block=execution_profile_block,
            execution_grounding_block=execution_grounding_block,
            resolved_temporal_refs=resolved_temporal_refs,
        )

        messages = back_mod.build_chat_history_for_back(
            snapshot["history_entries"],
            window=back_cfg.history_window,
        )
        messages.append(ModelMessage(role="user", content=json.dumps(task, indent=2)))
        tool_schemas = back_mod._filter_back_tools(task_tier)
        discoveries = await _run_discoveries(task_dispatcher, _discovery_requests(args, task))

        report = {
            "work_dir": str(work_dir),
            "kernel": {
                "config": {
                    "model_mode": "test",
                    "enable_family_tools": not args.disable_family_tools,
                    "enable_self_model": args.enable_self_model,
                    "enable_temporal": not args.disable_temporal,
                    "enable_grounding": not args.disable_grounding,
                    "enable_spatial": not args.disable_spatial,
                },
                "health": {
                    "healthy": health.healthy,
                    "components": health.components,
                    "details": health.details,
                },
                "family_tools": {
                    "enabled": family_tools is not None,
                    "capability_count": len(family_capability_names),
                    "capability_names": family_capability_names,
                },
            },
            "session": {
                "session_id": session.session_id,
                "device_id": args.device_id,
            },
            "task": task,
            "back_runtime": {
                "trace_id": trace_id,
                "task_tier": task_tier,
                "dispatcher_bucket": getattr(task_dispatcher, "tier", None),
                "dispatcher_allowlist": sorted(getattr(task_dispatcher, "allowlist", [])),
                "max_tool_calls": max_iterations,
                "effective_safety_band": effective_safety_band,
                "execution_profiles": profile_selection.to_dict(),
                "execution_profile_ids": list(profile_selection.profile_ids),
                "execution_profile_confidence": profile_selection.confidence,
                "execution_profile_block": execution_profile_block,
                "execution_grounding_block": execution_grounding_block,
                "snapshot": {
                    "beliefs_length": len(snapshot["beliefs_prompt"]),
                    "referents": snapshot["referents"],
                    "task_state_length": len(snapshot["task_state_prompt"]),
                    "task_artifacts_length": len(snapshot["task_artifacts_prompt"]),
                    "history_entries": len(snapshot["history_entries"]),
                    "persona_prefs": snapshot["persona_prefs"],
                },
                "messages": [_message_to_dict(message) for message in messages],
                "tool_schemas": [_tool_schema_to_dict(schema) for schema in tool_schemas],
                "prompt": _preview(prompt, args.prompt_preview_chars),
            },
            "discoveries": discoveries,
        }
    finally:
        try:
            await kernel.shutdown()
        finally:
            if temp_dir is not None:
                temp_dir.cleanup()

    if args.json:
        json.dump(report, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        _print_console_report(report)
    return 0


def main() -> int:
    args = _parse_args()
    _configure_logging(args.log_level)
    os.environ.setdefault("GOOGLE_API_KEY", os.environ.get("GOOGLE_API_KEY", ""))
    return asyncio.run(_async_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
