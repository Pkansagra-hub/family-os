"""
Pipeline Scanner - Extract pipeline definitions from k0/contracts/pipelines/*.yaml.

Parses pipeline contracts and extracts:
- Pipeline ID (P01, P02, etc.)
- Name and description
- Stages with module references
- Events consumed/produced
- Required capabilities

Usage:
    from governance.k0.scripts.pipeline_scanner import scan_pipelines
    pipelines = scan_pipelines()
    for p in pipelines:
        print(f"{p['pipeline_id']}: {p['name']} [{p['status']}]")
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class PipelineInfo:
    """Extracted pipeline information."""

    pipeline_id: str  # P01, P02, etc.
    name: str
    version: str
    status: str  # Production, Planning, Deprecated
    description: str
    trigger_event: str | None
    output_events: list[str] = field(default_factory=list)
    stages: list[dict] = field(default_factory=list)
    required_caps: list[str] = field(default_factory=list)
    modules_used: list[str] = field(default_factory=list)
    contract_path: str = ""
    dossier_path: str | None = None


def _extract_pipeline_id(filename: str, contract: dict) -> str:
    """Extract pipeline ID from filename or contract."""
    # Try filename first (p02_write.v1.yaml -> P02)
    match = re.search(r"p(\d{2})", filename.lower())
    if match:
        return f"P{match.group(1)}"

    # Try contract metadata
    metadata = contract.get("metadata", {})
    if "pipeline_id" in metadata:
        return metadata["pipeline_id"]

    return "Pxx"


def _extract_status(contract: dict) -> str:
    """Extract status from contract metadata."""
    metadata = contract.get("metadata", {})
    status = metadata.get("status", "").lower()

    if "production" in status or "active" in status:
        return "Production"
    if "planning" in status or "draft" in status:
        return "Planning"
    if "deprecated" in status:
        return "Deprecated"

    return "Unknown"


def _extract_modules(stages: list) -> list[str]:
    """Extract module references from stages."""
    modules = []
    for stage in stages:
        module = stage.get("module", "")
        if module:
            # Extract module name (hippocampus.pattern_separate:v1 -> hippocampus.pattern_separate)
            module_name = module.split(":")[0]
            if module_name and module_name not in modules:
                modules.append(module_name)
    return modules


def _extract_capabilities(stages: list) -> list[str]:
    """Extract required capabilities from stages."""
    caps = set()
    for stage in stages:
        for cap in stage.get("required_caps", []):
            caps.add(cap)
    return sorted(caps)


def _extract_events(contract: dict) -> tuple[str | None, list[str]]:
    """Extract trigger and output events."""
    trigger = contract.get("trigger", {}).get("event")
    outputs = []

    for output in contract.get("outputs", []):
        if isinstance(output, dict) and "event" in output:
            outputs.append(output["event"])
        elif isinstance(output, str):
            outputs.append(output)

    return trigger, outputs


def scan_pipelines(contracts_path: Path | None = None) -> list[PipelineInfo]:
    """
    Scan k0/contracts/pipelines/ and extract all pipeline definitions.

    Args:
        contracts_path: Path to k0/contracts/pipelines/ (defaults to repo root)

    Returns:
        List of PipelineInfo with pipeline details
    """
    if contracts_path is None:
        repo_root = Path(__file__).parent.parent.parent.parent
        contracts_path = repo_root / "k0" / "contracts" / "pipelines"

    if not contracts_path.exists():
        raise FileNotFoundError(f"Pipelines directory not found at {contracts_path}")

    dossiers_path = contracts_path.parent.parent.parent / "docs" / "pipelines"

    pipelines: list[PipelineInfo] = []

    for yaml_file in sorted(contracts_path.glob("*.yaml")):
        if yaml_file.name.startswith("_"):
            continue

        try:
            content = yaml_file.read_text(encoding="utf-8")
            contract = yaml.safe_load(content)

            if not contract:
                continue

            pipeline_id = _extract_pipeline_id(yaml_file.name, contract)
            metadata = contract.get("metadata", {})
            stages = contract.get("stages", [])
            trigger, outputs = _extract_events(contract)

            # Find dossier
            dossier = None
            if dossiers_path.exists():
                for dossier_file in dossiers_path.glob(f"{pipeline_id.lower()}_*.md"):
                    dossier = str(dossier_file.relative_to(dossiers_path.parent.parent))
                    break

            pipelines.append(
                PipelineInfo(
                    pipeline_id=pipeline_id,
                    name=metadata.get("name", yaml_file.stem),
                    version=metadata.get("version", "1.0.0"),
                    status=_extract_status(contract),
                    description=metadata.get("description", "")[:100],
                    trigger_event=trigger,
                    output_events=outputs,
                    stages=stages,
                    required_caps=_extract_capabilities(stages),
                    modules_used=_extract_modules(stages),
                    contract_path=str(yaml_file.relative_to(yaml_file.parent.parent.parent)),
                    dossier_path=dossier,
                )
            )
        except yaml.YAMLError as e:
            print(f"Warning: Failed to parse {yaml_file}: {e}")
            continue

    return pipelines


def generate_markdown_table(pipelines: list[PipelineInfo]) -> str:
    """Generate markdown table for Part 2.1 Pipeline Registry."""
    lines = [
        "| ID | Name | Version | Status | Trigger | Outputs | Stages | Modules |",
        "|----|------|---------|--------|---------|---------|--------|---------|",
    ]

    for p in pipelines:
        trigger = f"`{p.trigger_event}`" if p.trigger_event else "-"
        outputs = ", ".join(f"`{o}`" for o in p.output_events[:2]) or "-"
        if len(p.output_events) > 2:
            outputs += "..."
        modules = ", ".join(p.modules_used[:3]) or "-"
        if len(p.modules_used) > 3:
            modules += "..."

        lines.append(
            f"| {p.pipeline_id} | {p.name} | {p.version} | {p.status} | {trigger} | {outputs} | {len(p.stages)} | {modules} |"
        )

    return "\n".join(lines)


def diff_with_master(pipelines: list[PipelineInfo], master_path: Path) -> dict[str, Any]:
    """
    Compare scanned pipelines with what's in k0_architecture_master.md.

    Uses MarkdownRegistry for reliable AST-based table parsing.

    Note: We only report missing_in_master for pipelines that have contract YAML files.
    Planned pipelines (P01-P20) in master without contracts are expected.
    """
    from governance.k0.scripts.markdown_parser import MarkdownRegistry

    registry = MarkdownRegistry(master_path)

    # Get pipeline table from Part 2.1
    table = registry.get_table("2.1", "Pipeline Master")
    if not table:
        table = registry.get_table_by_title("Pipeline Master Table")

    registered = set()
    if table:
        # Pipeline ID is typically in the first column
        for row in table.rows:
            first_cell = row.cells[0] if row.cells else ""
            # Extract P02, P08, etc.
            match = re.search(r"P\d{2}", first_cell)
            if match:
                registered.add(match.group())

    scanned_ids = {p.pipeline_id for p in pipelines if p.pipeline_id != "Pxx"}

    # Only report contracts missing in master (not planned pipelines without contracts)
    return {
        "missing_in_master": sorted(scanned_ids - registered),
        "missing_in_code": [],  # Don't report planned pipelines without contracts
        "scanned_count": len(pipelines),
        "registered_count": len(registered),
    }


if __name__ == "__main__":
    pipelines = scan_pipelines()
    print(f"Found {len(pipelines)} pipelines:\n")
    for p in pipelines:
        print(f"  {p.pipeline_id}: {p.name} [{p.status}] - {len(p.stages)} stages")

    print("\n" + "=" * 60)
    print("Markdown Table:")
    print(generate_markdown_table(pipelines))
