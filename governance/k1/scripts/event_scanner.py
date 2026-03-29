"""
K1 Event Scanner - Extract event emissions and subscriptions from K1 codebase.

Scans code for:
- bus.emit() / bus.publish() calls
- Event topic definitions in contracts
- Event handler / subscriber registrations
- Event schema definitions

Usage:
    from governance.k1.scripts.event_scanner import scan_events
    events = scan_events()
    for e in events:
        print(f"{e.topic}: {e.producer} -> {e.consumers}")
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class K1EventInfo:
    """Extracted K1 event information."""

    topic: str  # k1.fabric.capability.resolved.v1
    version: str  # v1
    producer: str | None = None  # Module that emits
    consumers: list[str] = field(default_factory=list)
    schema_path: str | None = None
    status: str = "Active"  # Active, Deprecated, Planning
    emit_locations: list[str] = field(default_factory=list)
    subscribe_locations: list[str] = field(default_factory=list)
    source: str = "code"  # code, contract, schema


def _scan_emit_calls(k1_path: Path) -> dict[str, list[str]]:
    """
    Scan K1 Python files for event emission calls.

    Patterns detected:
    - .emit("topic.v1", ...)
    - .publish("topic.v1", ...)
    - bus.emit(topic="topic.v1")
    - emit_event("topic.v1")
    """
    events: dict[str, list[str]] = {}

    for py_file in k1_path.rglob("*.py"):
        if "__pycache__" in str(py_file):
            continue

        try:
            content = py_file.read_text(encoding="utf-8")
            lines = content.split("\n")

            for i, line in enumerate(lines, 1):
                patterns = [
                    r'\.emit\s*\(\s*["\']([a-z0-9_\.]+\.v\d+)["\']',
                    r'\.publish\s*\(\s*["\']([a-z0-9_\.]+\.v\d+)["\']',
                    r'\.emit\s*\(\s*topic\s*=\s*["\']([a-z0-9_\.]+\.v\d+)["\']',
                    r'emit_event\s*\(\s*["\']([a-z0-9_\.]+\.v\d+)["\']',
                    r'\.emit\s*\(\s*event_type\s*=\s*["\']([a-z0-9_\.]+\.v\d+)["\']',
                ]

                for pattern in patterns:
                    match = re.search(pattern, line, re.IGNORECASE)
                    if match:
                        topic = match.group(1)
                        rel_path = py_file.relative_to(k1_path.parent)
                        location = f"{rel_path}:{i}"
                        events.setdefault(topic, []).append(location)

        except Exception:
            continue

    return events


def _scan_subscribe_calls(k1_path: Path) -> dict[str, list[str]]:
    """
    Scan K1 Python files for event subscription calls.

    Patterns detected:
    - .subscribe("topic.v1", handler)
    - .on("topic.v1", handler)
    - @subscribe("topic.v1")
    - handler_for="topic.v1"
    """
    subscriptions: dict[str, list[str]] = {}

    for py_file in k1_path.rglob("*.py"):
        if "__pycache__" in str(py_file):
            continue

        try:
            content = py_file.read_text(encoding="utf-8")
            lines = content.split("\n")

            for i, line in enumerate(lines, 1):
                patterns = [
                    r'\.subscribe\s*\(\s*["\']([a-z0-9_\.]+\.v\d+)["\']',
                    r'\.on\s*\(\s*["\']([a-z0-9_\.]+\.v\d+)["\']',
                    r'@subscribe\s*\(\s*["\']([a-z0-9_\.]+\.v\d+)["\']',
                    r'handler_for\s*=\s*["\']([a-z0-9_\.]+\.v\d+)["\']',
                ]

                for pattern in patterns:
                    match = re.search(pattern, line, re.IGNORECASE)
                    if match:
                        topic = match.group(1)
                        rel_path = py_file.relative_to(k1_path.parent)
                        location = f"{rel_path}:{i}"
                        subscriptions.setdefault(topic, []).append(location)

        except Exception:
            continue

    return subscriptions


def _scan_contract_events(contracts_path: Path) -> list[K1EventInfo]:
    """
    Scan K1 contract YAML files for event definitions.

    Supports:
    - module.contract.yaml: input_event_types, output_event_types
    - wiring.contract.yaml: event subscriptions and emissions
    - Event schema files in contracts/events/ and contracts/schemas/events/
    """
    events: list[K1EventInfo] = []

    for yaml_file in contracts_path.rglob("*.yaml"):
        if "__pycache__" in str(yaml_file):
            continue

        try:
            content = yaml_file.read_text(encoding="utf-8")
            contract = yaml.safe_load(content)

            if not contract or not isinstance(contract, dict):
                continue

            # Extract module ID from metadata or filename
            metadata = contract.get("metadata", {})
            module_id = metadata.get("module_id", yaml_file.stem.split(".")[0])

            # Input event types (consumed)
            for topic in contract.get("input_event_types", []):
                if isinstance(topic, str) and ".v" in topic:
                    events.append(
                        K1EventInfo(
                            topic=topic,
                            version=topic.rsplit(".", 1)[-1] if "." in topic else "v1",
                            producer=None,
                            consumers=[module_id],
                            source="contract",
                        )
                    )

            # Output event types (produced)
            for topic in contract.get("output_event_types", []):
                if isinstance(topic, str) and ".v" in topic:
                    events.append(
                        K1EventInfo(
                            topic=topic,
                            version=topic.rsplit(".", 1)[-1] if "." in topic else "v1",
                            producer=module_id,
                            consumers=[],
                            source="contract",
                        )
                    )

            # Trigger events (legacy format)
            trigger = contract.get("trigger", {})
            if isinstance(trigger, dict) and "event" in trigger:
                topic = trigger["event"]
                events.append(
                    K1EventInfo(
                        topic=topic,
                        version=topic.rsplit(".", 1)[-1] if "." in topic else "v1",
                        producer=None,
                        consumers=[module_id],
                        source="contract",
                    )
                )

            # Outputs (legacy format)
            for output in contract.get("outputs", []):
                if isinstance(output, dict) and "event" in output:
                    topic = output["event"]
                    events.append(
                        K1EventInfo(
                            topic=topic,
                            version=topic.rsplit(".", 1)[-1] if "." in topic else "v1",
                            producer=module_id,
                            consumers=[],
                            source="contract",
                        )
                    )

        except Exception:
            continue

    return events


def _scan_event_schemas(contracts_path: Path) -> list[K1EventInfo]:
    """Scan contracts/schemas/events/ for event schema definitions."""
    events: list[K1EventInfo] = []
    events_schema_dir = contracts_path / "schemas" / "events"

    if not events_schema_dir.exists():
        return events

    for yaml_file in events_schema_dir.rglob("*.yaml"):
        try:
            content = yaml_file.read_text(encoding="utf-8")
            schema = yaml.safe_load(content)

            if not schema or not isinstance(schema, dict):
                continue

            # Extract topic from schema $id or title
            topic = schema.get("$id", "")
            if "://" in topic:
                # k1://schemas/events/capability.resolved.v1 -> capability.resolved.v1
                topic = topic.rsplit("/", 1)[-1].replace(".yaml", "")
            elif not topic:
                topic = yaml_file.stem

            if topic:
                events.append(
                    K1EventInfo(
                        topic=topic,
                        version=topic.rsplit(".", 1)[-1] if ".v" in topic else "v1",
                        schema_path=str(yaml_file.relative_to(contracts_path.parent)),
                        source="schema",
                    )
                )

        except Exception:
            continue

    return events


def _infer_module_from_path(location: str) -> str | None:
    """Infer module name from file path."""
    # k1/fabric/resolver.py -> fabric
    # k1/sessionstate/ports/events.py -> sessionstate
    match = re.match(r"k1/([^/]+)/", location)
    if match:
        return match.group(1)
    return None


def scan_events(repo_root: Path | None = None) -> list[K1EventInfo]:
    """
    Scan K1 codebase and extract all event topics.

    Merges events from:
    1. Contract YAML files (authoritative)
    2. Event schema definitions
    3. Code emit() calls (validation)
    4. Code subscribe() calls (consumer discovery)

    Args:
        repo_root: Repository root path

    Returns:
        Sorted merged list of K1EventInfo
    """
    if repo_root is None:
        repo_root = Path(__file__).parent.parent.parent.parent

    k1_path = repo_root / "k1"
    contracts_path = k1_path / "contracts"

    all_events: dict[str, K1EventInfo] = {}

    # 1. Scan contracts for declared events (authoritative source)
    for event in _scan_contract_events(contracts_path):
        if event.topic in all_events:
            existing = all_events[event.topic]
            if event.producer and not existing.producer:
                existing.producer = event.producer
            if event.consumers:
                existing.consumers = list(set(existing.consumers + event.consumers))
        else:
            all_events[event.topic] = event

    # 2. Scan event schemas
    for event in _scan_event_schemas(contracts_path):
        if event.topic in all_events:
            all_events[event.topic].schema_path = event.schema_path
        else:
            all_events[event.topic] = event

    # 3. Scan code for emit() calls
    emit_locations = _scan_emit_calls(k1_path)
    for topic, locations in emit_locations.items():
        if topic in all_events:
            all_events[topic].emit_locations = locations
            # Infer producer from first emit location
            if not all_events[topic].producer:
                all_events[topic].producer = _infer_module_from_path(locations[0])
        else:
            all_events[topic] = K1EventInfo(
                topic=topic,
                version=topic.rsplit(".", 1)[-1] if "." in topic else "v1",
                producer=_infer_module_from_path(locations[0]) if locations else None,
                emit_locations=locations,
                source="code",
            )

    # 4. Scan code for subscribe() calls
    sub_locations = _scan_subscribe_calls(k1_path)
    for topic, locations in sub_locations.items():
        if topic in all_events:
            all_events[topic].subscribe_locations = locations
            # Add inferred consumers
            for loc in locations:
                module = _infer_module_from_path(loc)
                if module and module not in all_events[topic].consumers:
                    all_events[topic].consumers.append(module)
        else:
            consumers = []
            for loc in locations:
                module = _infer_module_from_path(loc)
                if module:
                    consumers.append(module)
            all_events[topic] = K1EventInfo(
                topic=topic,
                version=topic.rsplit(".", 1)[-1] if "." in topic else "v1",
                consumers=consumers,
                subscribe_locations=locations,
                source="code",
            )

    return sorted(all_events.values(), key=lambda e: e.topic)


def generate_markdown_table(events: list[K1EventInfo]) -> str:
    """Generate markdown table for event registry."""
    lines = [
        "| Topic | Version | Producer | Consumers | Source | Status |",
        "|-------|---------|----------|-----------|--------|--------|",
    ]

    for e in events:
        producer = e.producer or "-"
        consumers = ", ".join(e.consumers[:3]) or "-"
        if len(e.consumers) > 3:
            consumers += "..."

        topic_display = f"`{e.topic}`" if len(e.topic) < 45 else f"`{e.topic[:42]}...`"

        lines.append(
            f"| {topic_display} | {e.version} | {producer} | {consumers} | {e.source} | {e.status} |"
        )

    return "\n".join(lines)


def diff_with_registry(events: list[K1EventInfo]) -> dict[str, Any]:
    """
    Validate event consistency.

    Checks:
    - Events in code but not in contracts
    - Events in contracts but no code emit/subscribe
    - Events without producers
    - Events without consumers (potential dead events)
    """
    issues: list[str] = []

    code_only: list[str] = []
    contract_only: list[str] = []
    no_producer: list[str] = []
    no_consumer: list[str] = []

    for e in events:
        if e.source == "code" and not e.schema_path:
            code_only.append(e.topic)
        if e.source == "contract" and not e.emit_locations and not e.subscribe_locations:
            contract_only.append(e.topic)
        if not e.producer and e.emit_locations:
            no_producer.append(e.topic)
        if not e.consumers and e.status == "Active":
            no_consumer.append(e.topic)

    if code_only:
        issues.append(f"{len(code_only)} events found in code but not in contracts")
    if contract_only:
        issues.append(f"{len(contract_only)} events in contracts but no code references")

    return {
        "scanned_count": len(events),
        "code_only": code_only,
        "contract_only": contract_only,
        "no_producer": no_producer,
        "no_consumer": no_consumer,
        "issues": issues,
    }


if __name__ == "__main__":
    events = scan_events()
    print("K1 Event Scanner")
    print("=" * 60)
    print(f"Found {len(events)} event topics:\n")

    for e in events[:15]:
        print(f"  {e.topic}")
        print(f"    Producer: {e.producer or 'Unknown'}")
        print(f"    Consumers: {', '.join(e.consumers) or 'None'}")
        print(f"    Source: {e.source}")
        if e.emit_locations:
            print(f"    Emit: {len(e.emit_locations)} locations")

    if len(events) > 15:
        print(f"\n  ... and {len(events) - 15} more events")

    print("\n" + "=" * 60)
    print("Markdown Table (first 10):")
    print(generate_markdown_table(events[:10]))

    diff = diff_with_registry(events)
    if diff["issues"]:
        print(f"\nIssues ({len(diff['issues'])}):")
        for issue in diff["issues"]:
            print(f"  ! {issue}")
