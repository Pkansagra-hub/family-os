"""
Contract Scanner for K0 Architecture Governance.

Scans contract YAML/JSON files in k0/contracts/ and compares with
Part 5 of k0_architecture_master.md.

Contract Categories:
- Module contracts: k0/contracts/modules/*.yaml (Part 5.1)
- Pipeline contracts: k0/contracts/pipelines/*.yaml (Part 5.2)
- Event schemas: k0/contracts/schemas/*.json (Part 5.3)

Usage:
    from governance.k0.scripts.contract_scanner import (
        scan_module_contracts,
        scan_pipeline_contracts,
        scan_event_schemas,
        diff_contracts_with_master,
    )
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
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
class ModuleContractInfo:
    """Information about a module contract."""

    contract_name: str  # e.g., "hippocampus.pattern_separate"
    module_id: str  # e.g., "M01" or full module_id from YAML
    version: str  # e.g., "v1"
    file_path: str  # relative path from repo root
    status: str = "Unknown"  # Active, Draft, Deprecated, etc.
    input_events: list[str] = field(default_factory=list)
    output_events: list[str] = field(default_factory=list)
    latency_budget_ms: int | None = None
    idempotent: bool = False
    description: str = ""


@dataclass
class PipelineContractInfo:
    """Information about a pipeline contract."""

    contract_name: str  # e.g., "p02_write"
    pipeline_id: str  # e.g., "P02_WRITE"
    version: str  # e.g., "v1"
    file_path: str  # relative path from repo root
    status: str = "Unknown"
    entry_topic: str = ""
    exit_topic: str = ""
    stages: list[str] = field(default_factory=list)
    required_capabilities: list[str] = field(default_factory=list)
    description: str = ""


@dataclass
class EventSchemaInfo:
    """Information about an event schema."""

    schema_name: str  # e.g., "cognitive.vector.stored"
    event_topic: str  # e.g., "cognitive.vector.stored.v1"
    version: str  # e.g., "v1"
    file_path: str  # relative path from repo root
    status: str = "Unknown"
    properties: list[str] = field(default_factory=list)


def scan_module_contracts(contracts_dir: Path | None = None) -> list[ModuleContractInfo]:
    """
    Scan module contract YAML files from k0/contracts/modules/.

    Returns list of ModuleContractInfo with parsed contract details.
    """
    if contracts_dir is None:
        contracts_dir = _get_repo_root() / "k0" / "contracts" / "modules"

    if not contracts_dir.exists():
        return []

    contracts: list[ModuleContractInfo] = []

    for yaml_file in sorted(contracts_dir.glob("*.yaml")):
        try:
            content = yaml_file.read_text(encoding="utf-8")
            data = yaml.safe_load(content)

            if not data:
                continue

            # Extract version from filename (e.g., "context.device_profile.v1.yaml" -> "v1")
            # Filename pattern: <module_id>.v<version>.yaml
            stem = yaml_file.stem  # e.g., "context.device_profile.v1"
            version = "v1"
            if ".v" in stem:
                parts = stem.rsplit(".v", 1)
                version = f"v{parts[1]}" if len(parts) > 1 else "v1"
                module_name = parts[0]
            else:
                module_name = stem

            # Try to get module_id from YAML, fallback to filename-derived name
            module_id = data.get("module_id", module_name)
            contract_name = module_id

            # Get relative path
            rel_path = yaml_file.relative_to(_get_repo_root())

            contract = ModuleContractInfo(
                contract_name=contract_name,
                module_id=module_id,
                version=data.get("version", version),
                file_path=str(rel_path).replace("\\", "/"),
                input_events=data.get("input_event_types", []) or [],
                output_events=data.get("output_event_types", []) or [],
                latency_budget_ms=data.get("latency_budget_ms"),
                idempotent=data.get("idempotent", False),
                description=data.get("description", "")[:100] if data.get("description") else "",
            )
            contracts.append(contract)

        except Exception as e:
            print(f"Warning: Failed to parse {yaml_file.name}: {e}")

    return contracts


def scan_pipeline_contracts(contracts_dir: Path | None = None) -> list[PipelineContractInfo]:
    """
    Scan pipeline contract YAML files from k0/contracts/pipelines/.

    Returns list of PipelineContractInfo with parsed contract details.
    """
    if contracts_dir is None:
        contracts_dir = _get_repo_root() / "k0" / "contracts" / "pipelines"

    if not contracts_dir.exists():
        return []

    contracts: list[PipelineContractInfo] = []

    for yaml_file in sorted(contracts_dir.glob("*.yaml")):
        try:
            content = yaml_file.read_text(encoding="utf-8")
            data = yaml.safe_load(content)

            if not data:
                continue

            # Extract info from filename (e.g., "p02_write.v1.yaml")
            stem = yaml_file.stem
            version = "v1"
            if ".v" in stem:
                parts = stem.rsplit(".v", 1)
                version = f"v{parts[1]}" if len(parts) > 1 else "v1"
                contract_name = parts[0]
            else:
                contract_name = stem

            # Get pipeline_id from YAML or derive from filename
            pipeline_id = data.get("pipeline_id", contract_name.upper())

            # Extract stages from DAG
            stages = []
            dag = data.get("dag", [])
            for stage in dag:
                if isinstance(stage, dict) and "id" in stage:
                    stages.append(stage["id"])

            rel_path = yaml_file.relative_to(_get_repo_root())

            contract = PipelineContractInfo(
                contract_name=contract_name,
                pipeline_id=pipeline_id,
                version=data.get("version", version),
                file_path=str(rel_path).replace("\\", "/"),
                entry_topic=data.get("entry_topic", ""),
                exit_topic=data.get("exit_topic", ""),
                stages=stages,
                required_capabilities=data.get("required_capabilities", []) or [],
                description=data.get("description", "")[:100] if data.get("description") else "",
            )
            contracts.append(contract)

        except Exception as e:
            print(f"Warning: Failed to parse {yaml_file.name}: {e}")

    return contracts


def scan_event_schemas(schemas_dir: Path | None = None) -> list[EventSchemaInfo]:
    """
    Scan event schema JSON files from k0/contracts/schemas/.

    Returns list of EventSchemaInfo with parsed schema details.
    """
    if schemas_dir is None:
        schemas_dir = _get_repo_root() / "k0" / "contracts" / "schemas"

    if not schemas_dir.exists():
        return []

    schemas: list[EventSchemaInfo] = []

    for json_file in sorted(schemas_dir.glob("*.json")):
        try:
            content = json_file.read_text(encoding="utf-8")
            data = json.loads(content)

            if not data:
                continue

            # Derive schema name from filename (e.g., "cognitive_vector_stored.json")
            # Convert underscores to dots for event topic style
            stem = json_file.stem
            schema_name = stem.replace("_", ".")

            # Try to find version in schema
            version = "v1"
            if "$id" in data:
                # Extract version from $id if present
                id_val = data["$id"]
                version_match = re.search(r"\.v(\d+)", id_val)
                if version_match:
                    version = f"v{version_match.group(1)}"

            # Derive event topic from schema name
            event_topic = f"{schema_name}.{version}"

            # Get properties if available
            properties = []
            if "properties" in data:
                properties = list(data["properties"].keys())[:10]  # First 10

            rel_path = json_file.relative_to(_get_repo_root())

            schema = EventSchemaInfo(
                schema_name=schema_name,
                event_topic=event_topic,
                version=version,
                file_path=str(rel_path).replace("\\", "/"),
                properties=properties,
            )
            schemas.append(schema)

        except Exception as e:
            print(f"Warning: Failed to parse {json_file.name}: {e}")

    return schemas


def diff_module_contracts_with_master(
    contracts: list[ModuleContractInfo], master_path: Path
) -> dict[str, Any]:
    """
    Compare scanned module contracts with Part 5.1 Module Contract Registry.

    Returns dict with:
        - missing_in_master: contracts in code but not in doc
        - missing_in_code: contracts in doc but not in code
        - scanned_count: number of contracts found in files
        - registered_count: number of contracts in master doc
    """
    content = master_path.read_text(encoding="utf-8")

    # Find Part 5.1 Module Contract Registry section
    # Look for contract names in backticks in the table rows
    # Pattern: | `contract.name` |
    registered = set()
    planning_contracts = set()

    # Look for module contract table after "## 5.1 Module Contract Registry"
    section_match = re.search(
        r"## 5\.1 Module Contract Registry.*?(?=## 5\.\d|\Z)",
        content,
        re.DOTALL,
    )

    if section_match:
        section = section_match.group(0)
        # Extract contract names from table rows
        contract_pattern = re.compile(r"\|\s*`([a-z_.]+)`\s*\|")
        for match in contract_pattern.finditer(section):
            contract_name = match.group(1)
            registered.add(contract_name)

            # Check if this is a Planning contract
            line_start = section.rfind("\n", 0, match.start())
            line_end = section.find("\n", match.end())
            line = section[line_start:line_end] if line_end > line_start else ""
            if "Planning" in line or "🎯" in line:
                planning_contracts.add(contract_name)

    scanned_names = {c.contract_name for c in contracts}

    # Planning contracts are expected to not have files yet (but many do)
    missing_in_code = registered - scanned_names - planning_contracts

    return {
        "missing_in_master": scanned_names - registered,
        "missing_in_code": missing_in_code,
        "scanned_count": len(contracts),
        "registered_count": len(registered),
        "planning_count": len(planning_contracts),
    }


def diff_pipeline_contracts_with_master(
    contracts: list[PipelineContractInfo], master_path: Path
) -> dict[str, Any]:
    """
    Compare scanned pipeline contracts with Part 5.2 Pipeline Contract Registry.

    Returns dict with same structure as diff_module_contracts_with_master.
    """
    content = master_path.read_text(encoding="utf-8")

    registered = set()
    planning_contracts = set()

    # Look for pipeline contract table after "## 5.2 Pipeline Contract Registry"
    section_match = re.search(
        r"## 5\.2 Pipeline Contract Registry.*?(?=## 5\.\d|\Z)",
        content,
        re.DOTALL,
    )

    if section_match:
        section = section_match.group(0)
        # Extract contract names from table rows
        contract_pattern = re.compile(r"\|\s*`([a-z0-9_]+)`\s*\|")
        for match in contract_pattern.finditer(section):
            contract_name = match.group(1)
            registered.add(contract_name)

            line_start = section.rfind("\n", 0, match.start())
            line_end = section.find("\n", match.end())
            line = section[line_start:line_end] if line_end > line_start else ""
            if "Planning" in line or "🎯" in line:
                planning_contracts.add(contract_name)

    scanned_names = {c.contract_name for c in contracts}
    missing_in_code = registered - scanned_names - planning_contracts

    return {
        "missing_in_master": scanned_names - registered,
        "missing_in_code": missing_in_code,
        "scanned_count": len(contracts),
        "registered_count": len(registered),
        "planning_count": len(planning_contracts),
    }


def diff_event_schemas_with_master(
    schemas: list[EventSchemaInfo], master_path: Path
) -> dict[str, Any]:
    """
    Compare scanned event schemas with Part 5.3 Event Schema Registry.

    Returns dict with same structure as diff_module_contracts_with_master.
    """
    content = master_path.read_text(encoding="utf-8")

    registered = set()
    planning_schemas = set()

    # Look for event schema table after "## 5.3 Event Schema Registry"
    section_match = re.search(
        r"## 5\.3 Event Schema Registry.*?(?=## 5\.\d|# Part |\Z)",
        content,
        re.DOTALL,
    )

    if section_match:
        section = section_match.group(0)
        # Extract schema names from table rows (first column)
        schema_pattern = re.compile(r"\|\s*`([a-z_.]+)`\s*\|")
        for match in schema_pattern.finditer(section):
            schema_name = match.group(1)
            registered.add(schema_name)

            line_start = section.rfind("\n", 0, match.start())
            line_end = section.find("\n", match.end())
            line = section[line_start:line_end] if line_end > line_start else ""
            if "Planning" in line or "🎯" in line:
                planning_schemas.add(schema_name)

    scanned_names = {s.schema_name for s in schemas}
    missing_in_code = registered - scanned_names - planning_schemas

    return {
        "missing_in_master": scanned_names - registered,
        "missing_in_code": missing_in_code,
        "scanned_count": len(schemas),
        "registered_count": len(registered),
        "planning_count": len(planning_schemas),
    }


if __name__ == "__main__":
    # Quick test
    print("=" * 60)
    print("Contract Scanner Test")
    print("=" * 60)

    print("\n[1] Scanning module contracts...")
    module_contracts = scan_module_contracts()
    print(f"Found {len(module_contracts)} module contracts:")
    for c in module_contracts[:5]:
        print(f"  {c.contract_name} ({c.version}) -> {c.file_path}")
    if len(module_contracts) > 5:
        print(f"  ... and {len(module_contracts) - 5} more")

    print("\n[2] Scanning pipeline contracts...")
    pipeline_contracts = scan_pipeline_contracts()
    print(f"Found {len(pipeline_contracts)} pipeline contracts:")
    for c in pipeline_contracts:
        print(f"  {c.contract_name} ({c.version}) -> {c.pipeline_id}")

    print("\n[3] Scanning event schemas...")
    event_schemas = scan_event_schemas()
    print(f"Found {len(event_schemas)} event schemas:")
    for s in event_schemas:
        print(f"  {s.schema_name} ({s.version}) -> {s.event_topic}")

    # Test diff
    print("\n[4] Testing diff with master...")
    master_path = _get_repo_root() / "governance" / "k0" / "k0_architecture_master.md"
    if master_path.exists():
        # Module contracts
        diff = diff_module_contracts_with_master(module_contracts, master_path)
        print(
            f"Module Contracts - Scanned: {diff['scanned_count']}, Registered: {diff['registered_count']}, Planning: {diff['planning_count']}"
        )
        if diff["missing_in_master"]:
            print(f"  Missing in master: {diff['missing_in_master']}")
        if diff["missing_in_code"]:
            print(f"  Missing in code: {diff['missing_in_code']}")

        # Pipeline contracts
        diff = diff_pipeline_contracts_with_master(pipeline_contracts, master_path)
        print(
            f"Pipeline Contracts - Scanned: {diff['scanned_count']}, Registered: {diff['registered_count']}, Planning: {diff['planning_count']}"
        )
        if diff["missing_in_master"]:
            print(f"  Missing in master: {diff['missing_in_master']}")
        if diff["missing_in_code"]:
            print(f"  Missing in code: {diff['missing_in_code']}")

        # Event schemas
        diff = diff_event_schemas_with_master(event_schemas, master_path)
        print(
            f"Event Schemas - Scanned: {diff['scanned_count']}, Registered: {diff['registered_count']}, Planning: {diff['planning_count']}"
        )
        if diff["missing_in_master"]:
            print(f"  Missing in master: {diff['missing_in_master']}")
        if diff["missing_in_code"]:
            print(f"  Missing in code: {diff['missing_in_code']}")
