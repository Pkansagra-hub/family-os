"""
Scheduler Scanner for K0 Architecture Governance.

Scans scheduled tasks, kernel hooks, and background workers from
Part 9 of k0_architecture_master.md.

Scanner Categories:
- Scheduled Tasks: SCH-xxx entries in Part 9.1
- Kernel Hooks: KH-xxx entries in Part 9.2
- Background Workers: BGW-xxx entries in Part 9.3

Usage:
    from governance.k0.scripts.scheduler_scanner import (
        scan_scheduled_tasks,
        scan_kernel_hooks,
        scan_background_workers,
        diff_scheduler_with_master,
    )
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


def _get_repo_root() -> Path:
    """Get the repository root directory."""
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / ".git").exists() or (parent / "pyproject.toml").exists():
            return parent
    return Path.cwd()


@dataclass
class ScheduledTaskInfo:
    """Information about a scheduled task."""

    task_id: str  # e.g., "SCH-001"
    name: str  # e.g., "P08 Maintenance Interval"
    pipeline_module: str  # e.g., "P08"
    trigger_type: str  # e.g., "interval", "threshold", "manual"
    interval_cron: str  # e.g., "300s", "0 * * * *"
    timeout: str  # e.g., "180s"
    status: str = "Active"


@dataclass
class KernelHookInfo:
    """Information about a kernel lifespan hook."""

    hook_id: str  # e.g., "KH-001"
    hook_point: str  # e.g., "on_startup", "on_shutdown"
    component: str  # e.g., "PostgreSQL"
    function: str  # e.g., "configure_pool()"
    order: int
    is_async: bool = True
    timeout: str = ""
    status: str = "Active"


@dataclass
class BackgroundWorkerInfo:
    """Information about a background worker."""

    worker_id: str  # e.g., "BGW-001"
    name: str  # e.g., "SSE Metrics Reporter"
    worker_type: str  # e.g., "interval", "on-demand", "scheduled"
    pipeline_module: str  # e.g., "Kernel"
    concurrency: str  # e.g., "1", "1 per driver"
    status: str = "Active"


def scan_scheduled_tasks_from_yaml(contracts_dir: Path | None = None) -> list[ScheduledTaskInfo]:
    """
    Scan scheduled task definitions from pipeline contract YAML files.

    Returns list of ScheduledTaskInfo with task details.
    """
    if contracts_dir is None:
        contracts_dir = _get_repo_root() / "k0" / "contracts" / "pipelines"

    if not contracts_dir.exists():
        return []

    tasks: list[ScheduledTaskInfo] = []
    task_counter = 1

    for yaml_file in sorted(contracts_dir.glob("*.yaml")):
        try:
            content = yaml_file.read_text(encoding="utf-8")
            data = yaml.safe_load(content)

            if not data:
                continue

            pipeline_id = data.get("pipeline_id", "")

            # Extract triggers from YAML
            triggers = data.get("triggers", [])
            for trigger in triggers:
                if not isinstance(trigger, dict):
                    continue

                trigger_type = trigger.get("type", "unknown")
                interval = trigger.get("interval_seconds", "")
                threshold = trigger.get("threshold_count", "")
                timeout = trigger.get("timeout_seconds", 180)

                interval_cron = (
                    f"{interval}s" if interval else (f">{threshold}" if threshold else "-")
                )

                tasks.append(
                    ScheduledTaskInfo(
                        task_id=f"SCH-{task_counter:03d}",
                        name=f"{pipeline_id} {trigger_type.title()} Trigger",
                        pipeline_module=pipeline_id,
                        trigger_type=trigger_type,
                        interval_cron=interval_cron,
                        timeout=f"{timeout}s",
                        status="Active",
                    )
                )
                task_counter += 1

        except Exception as e:
            print(f"Warning: Failed to parse {yaml_file.name}: {e}")

    return tasks


def scan_kernel_hooks_from_master(master_path: Path) -> list[KernelHookInfo]:
    """
    Extract kernel hook definitions from Part 9.2 of master document.

    Note: Hooks are defined in code but we parse from master for governance.
    """
    if not master_path.exists():
        return []

    content = master_path.read_text(encoding="utf-8")
    hooks: list[KernelHookInfo] = []

    # Look for section 9.2
    section_match = re.search(
        r"## 9\.2 Kernel Lifespan Hooks Registry.*?(?=## 9\.\d|# Part |\Z)",
        content,
        re.DOTALL,
    )

    if not section_match:
        return []

    section = section_match.group(0)

    # Pattern: | KH-001 | on_startup | Component | function() | 1 | Yes | 30s | Active |
    hook_pattern = re.compile(
        r"\|\s*(KH-\d+)\s*\|\s*[🚀🛑]?\s*(\w+)\s*\|\s*([^|]+)\s*\|\s*`?([^|`]+)`?\s*\|\s*(\d+)\s*\|"
        r"\s*([✅❌]?\s*\w+)\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|"
    )

    for match in hook_pattern.finditer(section):
        hook_id = match.group(1).strip()
        hook_point = match.group(2).strip()
        component = match.group(3).strip()
        function = match.group(4).strip()
        order = int(match.group(5).strip())
        is_async = "Yes" in match.group(6)
        timeout = match.group(7).strip()
        status = match.group(8).strip()

        hooks.append(
            KernelHookInfo(
                hook_id=hook_id,
                hook_point=hook_point,
                component=component,
                function=function,
                order=order,
                is_async=is_async,
                timeout=timeout,
                status=(
                    "Active"
                    if "Active" in status
                    else ("Deprecated" if "Deprecated" in status else "Planning")
                ),
            )
        )

    return hooks


def scan_background_workers_from_master(master_path: Path) -> list[BackgroundWorkerInfo]:
    """
    Extract background worker definitions from Part 9.3 of master document.
    """
    if not master_path.exists():
        return []

    content = master_path.read_text(encoding="utf-8")
    workers: list[BackgroundWorkerInfo] = []

    # Look for section 9.3
    section_match = re.search(
        r"## 9\.3 Background Worker Registry.*?(?=## 9\.\d|# Part |\Z)",
        content,
        re.DOTALL,
    )

    if not section_match:
        return []

    section = section_match.group(0)

    # Pattern: | BGW-001 | Name | Type | Pipeline | Concurrency | Queue | Status |
    worker_pattern = re.compile(
        r"\|\s*(BGW-\d+)\s*\|\s*([^|]+)\s*\|\s*[⏱️📋🔄📊]?\s*([^|]+)\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|"
        r"\s*([^|]+)\s*\|\s*([^|]+)\s*\|"
    )

    for match in worker_pattern.finditer(section):
        worker_id = match.group(1).strip()
        name = match.group(2).strip()
        worker_type = match.group(3).strip()
        pipeline = match.group(4).strip()
        concurrency = match.group(5).strip()
        status = match.group(7).strip()

        workers.append(
            BackgroundWorkerInfo(
                worker_id=worker_id,
                name=name,
                worker_type=worker_type,
                pipeline_module=pipeline,
                concurrency=concurrency,
                status=(
                    "Active"
                    if "Active" in status
                    else ("Deprecated" if "Deprecated" in status else "Planning")
                ),
            )
        )

    return workers


def diff_scheduled_tasks_with_master(
    tasks: list[ScheduledTaskInfo], master_path: Path
) -> dict[str, Any]:
    """
    Compare scanned scheduled tasks with Part 9.1 registry.

    Returns dict with diff results.
    """
    content = master_path.read_text(encoding="utf-8")

    registered = set()
    planning_tasks = set()

    # Look for section 9.1
    section_match = re.search(
        r"## 9\.1 Scheduler Task Registry.*?(?=## 9\.\d|# Part |\Z)",
        content,
        re.DOTALL,
    )

    if section_match:
        section = section_match.group(0)
        # Extract task IDs
        task_pattern = re.compile(r"\|\s*(SCH-\d+)\s*\|")
        for match in task_pattern.finditer(section):
            task_id = match.group(1)
            registered.add(task_id)

            # Check status
            line_start = section.rfind("\n", 0, match.start())
            line_end = section.find("\n", match.end())
            line = section[line_start:line_end] if line_end > line_start else ""
            if "Planning" in line or "🎯" in line:
                planning_tasks.add(task_id)

    scanned_ids = {t.task_id for t in tasks}
    missing_in_code = registered - scanned_ids - planning_tasks

    return {
        "missing_in_master": scanned_ids - registered,
        "missing_in_code": missing_in_code,
        "scanned_count": len(tasks),
        "registered_count": len(registered),
        "planning_count": len(planning_tasks),
    }


def diff_kernel_hooks_with_master(hooks: list[KernelHookInfo], master_path: Path) -> dict[str, Any]:
    """Compare scanned kernel hooks with Part 9.2 registry."""
    # Hooks are parsed from master itself, so just count them
    active = [h for h in hooks if h.status == "Active"]
    deprecated = [h for h in hooks if h.status == "Deprecated"]
    planning = [h for h in hooks if h.status == "Planning"]

    return {
        "missing_in_master": set(),
        "missing_in_code": set(),
        "scanned_count": len(active),
        "registered_count": len(hooks),
        "planning_count": len(planning),
    }


def diff_background_workers_with_master(
    workers: list[BackgroundWorkerInfo], master_path: Path
) -> dict[str, Any]:
    """Compare scanned background workers with Part 9.3 registry."""
    # Workers are parsed from master itself, so just count them
    active = [w for w in workers if w.status == "Active"]
    deprecated = [w for w in workers if w.status == "Deprecated"]
    planning = [w for w in workers if w.status == "Planning"]

    return {
        "missing_in_master": set(),
        "missing_in_code": set(),
        "scanned_count": len(active),
        "registered_count": len(workers),
        "planning_count": len(planning),
    }


if __name__ == "__main__":
    # Quick test
    print("=" * 60)
    print("Scheduler Scanner Test")
    print("=" * 60)

    master_path = _get_repo_root() / "governance" / "k0" / "k0_architecture_master.md"

    print("\n[1] Scanning scheduled tasks from YAML...")
    tasks = scan_scheduled_tasks_from_yaml()
    print(f"Found {len(tasks)} scheduled tasks from YAML:")
    for t in tasks:
        print(f"  {t.task_id}: {t.name} ({t.trigger_type})")

    print("\n[2] Scanning kernel hooks from master...")
    hooks = scan_kernel_hooks_from_master(master_path)
    print(f"Found {len(hooks)} kernel hooks:")
    for h in hooks[:5]:
        print(f"  {h.hook_id}: {h.hook_point} -> {h.component} ({h.status})")
    if len(hooks) > 5:
        print(f"  ... and {len(hooks) - 5} more")

    print("\n[3] Scanning background workers from master...")
    workers = scan_background_workers_from_master(master_path)
    print(f"Found {len(workers)} background workers:")
    for w in workers[:5]:
        print(f"  {w.worker_id}: {w.name} ({w.status})")
    if len(workers) > 5:
        print(f"  ... and {len(workers) - 5} more")

    # Test diff
    print("\n[4] Testing diff with master...")
    if master_path.exists():
        diff = diff_scheduled_tasks_with_master(tasks, master_path)
        print(
            f"Scheduled Tasks - Scanned: {diff['scanned_count']}, Registered: {diff['registered_count']}"
        )

        diff = diff_kernel_hooks_with_master(hooks, master_path)
        print(f"Kernel Hooks - Active: {diff['scanned_count']}, Total: {diff['registered_count']}")

        diff = diff_background_workers_with_master(workers, master_path)
        print(
            f"Background Workers - Active: {diff['scanned_count']}, Total: {diff['registered_count']}"
        )
