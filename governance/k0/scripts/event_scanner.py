"""
Event Scanner - Extract event emissions from codebase.

Scans code for:
- bus.emit() calls
- outbox_emit_batch() syscalls
- Event topic definitions in contracts
- Event handler registrations

Usage:
    from governance.k0.scripts.event_scanner import scan_events
    events = scan_events()
    for e in events:
        print(f"{e['topic']}: {e['producer']} -> {e['consumers']}")
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class EventInfo:
    """Extracted event information."""

    topic: str  # cognitive.memory.write.committed.v1
    version: str
    producer: str | None  # Module or pipeline that emits
    consumers: list[str] = field(default_factory=list)
    schema_path: str | None = None
    status: str = "Active"  # Active, Deprecated
    emit_locations: list[str] = field(default_factory=list)  # file:line


def _scan_emit_calls(code_path: Path) -> dict[str, list[str]]:
    """Scan Python files for emit() calls and topic string literals."""
    events: dict[str, list[str]] = {}

    for py_file in code_path.rglob("*.py"):
        if "__pycache__" in str(py_file):
            continue

        try:
            content = py_file.read_text(encoding="utf-8")
            lines = content.split("\n")

            for i, line in enumerate(lines, 1):
                # Pattern 1: .emit("topic.name.v1") calls
                patterns = [
                    r'\.emit\s*\(\s*["\']([a-z_\.]+\.v\d+)["\']',
                    r'\.emit\s*\(\s*topic\s*=\s*["\']([a-z_\.]+\.v\d+)["\']',
                    r'\.emit\s*\(\s*event_type\s*=\s*["\']([a-z_\.]+\.v\d+)["\']',
                    r'outbox_emit.*topic["\']?\s*[:=]\s*["\']([a-z_\.]+\.v\d+)["\']',
                ]

                for pattern in patterns:
                    match = re.search(pattern, line, re.IGNORECASE)
                    if match:
                        topic = match.group(1)
                        location = f"{py_file.name}:{i}"
                        events.setdefault(topic, []).append(location)

                # ADR-K021: Removed broad string literal pattern matching
                # Events are now sourced from contracts and whiteboard only
                # Emit calls above remain as secondary validation

        except Exception:
            continue

    return events


def _scan_contract_events(contracts_path: Path) -> list[EventInfo]:
    """Scan module and pipeline contracts for event definitions."""
    events: list[EventInfo] = []

    for yaml_file in contracts_path.rglob("*.yaml"):
        if "__pycache__" in str(yaml_file):
            continue

        try:
            content = yaml_file.read_text(encoding="utf-8")
            contract = yaml.safe_load(content)

            if not contract:
                continue

            module_id = contract.get("module_id", yaml_file.stem)

            # Extract input event types (list of topic strings)
            for topic in contract.get("input_event_types", []):
                if isinstance(topic, str) and ".v" in topic:
                    events.append(
                        EventInfo(
                            topic=topic,
                            version=topic.split(".")[-1] if "." in topic else "v1",
                            producer=None,
                            consumers=[module_id],
                        )
                    )

            # Extract output event types (list of topic strings)
            for topic in contract.get("output_event_types", []):
                if isinstance(topic, str) and ".v" in topic:
                    events.append(
                        EventInfo(
                            topic=topic,
                            version=topic.split(".")[-1] if "." in topic else "v1",
                            producer=module_id,
                            consumers=[],
                        )
                    )

            # Legacy: Extract trigger events (dict with event key)
            trigger = contract.get("trigger", {})
            if isinstance(trigger, dict) and "event" in trigger:
                topic = trigger["event"]
                events.append(
                    EventInfo(
                        topic=topic,
                        version=topic.split(".")[-1] if "." in topic else "v1",
                        producer=None,
                        consumers=[module_id],
                    )
                )

            # Legacy: Extract output events (list of dicts with event key)
            for output in contract.get("outputs", []):
                if isinstance(output, dict) and "event" in output:
                    topic = output["event"]
                    events.append(
                        EventInfo(
                            topic=topic,
                            version=topic.split(".")[-1] if "." in topic else "v1",
                            producer=module_id,
                            consumers=[],
                        )
                    )
        except Exception:
            continue

    return events


def _scan_whiteboard_topics(whiteboard_path: Path) -> list[EventInfo]:
    """Parse whiteboard.md for topic registry."""
    events: list[EventInfo] = []

    if not whiteboard_path.exists():
        return events

    content = whiteboard_path.read_text(encoding="utf-8")

    # Parse topic table
    in_table = False
    for line in content.split("\n"):
        if "Topic" in line and "|" in line:
            in_table = True
            continue
        if in_table and line.startswith("|---"):
            continue
        if in_table and line.startswith("|"):
            cells = [c.strip() for c in line.split("|") if c.strip()]
            if len(cells) >= 2:
                topic = cells[0].strip("`")
                if "." in topic:
                    events.append(
                        EventInfo(
                            topic=topic,
                            version=topic.split(".")[-1] if "v" in topic else "v1",
                            producer=cells[1] if len(cells) > 1 else None,
                            consumers=cells[2].split(",") if len(cells) > 2 else [],
                        )
                    )
        elif in_table and not line.startswith("|"):
            in_table = False

    return events


def scan_events(repo_root: Path | None = None) -> list[EventInfo]:
    """
    Scan codebase and extract all event topics.

    Args:
        repo_root: Repository root path

    Returns:
        List of EventInfo with event details
    """
    if repo_root is None:
        repo_root = Path(__file__).parent.parent.parent.parent

    k0_path = repo_root / "k0"
    contracts_path = k0_path / "contracts"
    whiteboard_path = k0_path / "pipelines" / "whiteboard.md"

    # Collect events from all sources
    all_events: dict[str, EventInfo] = {}

    # 1. Scan whiteboard for official topic registry
    for event in _scan_whiteboard_topics(whiteboard_path):
        all_events[event.topic] = event

    # 2. Scan contracts for declared events
    for event in _scan_contract_events(contracts_path):
        if event.topic in all_events:
            # Merge information
            existing = all_events[event.topic]
            if event.producer and not existing.producer:
                existing.producer = event.producer
            if event.consumers:
                existing.consumers = list(set(existing.consumers + event.consumers))
        else:
            all_events[event.topic] = event

    # 3. Scan code for emit() calls
    emit_locations = _scan_emit_calls(k0_path)
    for topic, locations in emit_locations.items():
        if topic in all_events:
            all_events[topic].emit_locations = locations
        else:
            all_events[topic] = EventInfo(
                topic=topic,
                version=topic.split(".")[-1] if "." in topic else "v1",
                producer=None,
                emit_locations=locations,
            )

    return sorted(all_events.values(), key=lambda e: e.topic)


def generate_markdown_table(events: list[EventInfo]) -> str:
    """Generate markdown table for Part 4.1 Event Topics Registry."""
    lines = [
        "| Topic | Version | Producer | Consumers | Emit Locations | Status |",
        "|-------|---------|----------|-----------|----------------|--------|",
    ]

    for e in events:
        producer = e.producer or "-"
        consumers = ", ".join(e.consumers[:2]) or "-"
        if len(e.consumers) > 2:
            consumers += "..."
        locations = ", ".join(e.emit_locations[:2]) or "-"
        if len(e.emit_locations) > 2:
            locations += "..."

        topic_display = f"`{e.topic}`" if len(e.topic) < 40 else f"`{e.topic[:37]}...`"

        lines.append(
            f"| {topic_display} | {e.version} | {producer} | {consumers} | {locations} | {e.status} |"
        )

    return "\n".join(lines)


def diff_with_master(events: list[EventInfo], master_path: Path) -> dict[str, Any]:
    """
    Compare scanned events with what's in k0_architecture_master.md.

    Uses MarkdownRegistry for reliable AST-based table parsing.
    Only Active events are checked for drift - Planning and Deprecated are excluded.
    """
    from governance.k0.scripts.markdown_parser import MarkdownRegistry

    registry = MarkdownRegistry(master_path)

    # Get event tables from Part 4.1 (there are multiple subtables)
    # registered_active: events marked Active that should exist in code
    # registered_all: all events for count purposes
    registered_active = set()
    registered_all = set()

    # Try different event tables in Part 4.1
    for title_fragment in [
        "Ingress",
        "Core Event Topics",
        "Vector",
        "Fanout",
        "Deprecated",
        "Future",
    ]:
        table = registry.get_table("4.1", title_fragment)
        if table:
            for row in table.rows:
                # Topic is typically in first column with backticks
                first_cell = row.cells[0] if row.cells else ""
                # Extract event topic from backticks (include digits for p02, p08, etc.)
                match = re.search(r"`([a-z0-9_\.]+\.v\d+)`", first_cell)
                if match:
                    topic = match.group(1)
                    registered_all.add(topic)

                    # Check status in last column - only count Active for drift
                    last_cell = row.cells[-1] if row.cells else ""
                    if "Active" in last_cell:
                        registered_active.add(topic)

    scanned_topics = {e.topic for e in events}

    return {
        "missing_in_master": sorted(scanned_topics - registered_all),
        "missing_in_code": sorted(registered_active - scanned_topics),
        "scanned_count": len(events),
        "registered_count": len(registered_all),
    }


if __name__ == "__main__":
    events = scan_events()
    print(f"Found {len(events)} event topics:\n")

    for e in events[:15]:
        locations = len(e.emit_locations)
        print(f"  {e.topic}")
        print(f"    Producer: {e.producer or 'Unknown'}")
        print(f"    Consumers: {', '.join(e.consumers) or 'None'}")
        print(f"    Emit locations: {locations}")

    if len(events) > 15:
        print(f"\n  ... and {len(events) - 15} more events")

    print("\n" + "=" * 60)
    print("Markdown Table (first 10):")
    print(generate_markdown_table(events[:10]))
