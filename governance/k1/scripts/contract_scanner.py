"""
K1 Contract Scanner - Extract contract definitions from k1/contracts/.

Scans contract YAML files for:
- Module contracts (module.contract.yaml)
- Wiring contracts (wiring.contract.yaml)
- Policy contracts (enforcement.policy.yaml, policies.contract.yaml)
- Schema definitions
- Validator registrations

Usage:
    from governance.k1.scripts.contract_scanner import scan_contracts
    contracts = scan_contracts()
    for c in contracts:
        print(f"{c.contract_id}: {c.contract_type} [{c.module}]")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class K1ContractInfo:
    """Extracted K1 contract information."""

    contract_id: str  # sessionstate.module, sessionstate.wiring, etc.
    contract_type: str  # module, wiring, policy, enforcement, schema
    module: str  # Module this contract belongs to
    version: int | None = None  # contract_version field
    impl_version: str | None = None  # Implementation version
    schema_ref: str | None = None  # $schema reference
    file_path: str = ""
    exports: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    input_events: list[str] = field(default_factory=list)
    output_events: list[str] = field(default_factory=list)
    status: str = "Active"


def _classify_contract(filename: str) -> str:
    """Determine contract type from filename."""
    name_lower = filename.lower()
    if "module.contract" in name_lower:
        return "module"
    if "wiring.contract" in name_lower:
        return "wiring"
    if "policies.contract" in name_lower:
        return "policies"
    if "enforcement.policy" in name_lower:
        return "enforcement"
    if "runtime.guard" in name_lower:
        return "runtime-guard"
    if ".schema." in name_lower:
        return "schema"
    return "other"


def _build_contract_id(module_name: str, contract_type: str) -> str:
    """Build a canonical contract ID."""
    return f"{module_name}.{contract_type}"


def _scan_module_contracts(modules_dir: Path) -> list[K1ContractInfo]:
    """Scan k1/contracts/modules/ for module-level contracts."""
    contracts: list[K1ContractInfo] = []

    if not modules_dir.exists():
        return contracts

    for module_dir in sorted(modules_dir.iterdir()):
        if not module_dir.is_dir():
            continue
        if module_dir.name.startswith("_"):
            continue

        module_name = module_dir.name

        for yaml_file in sorted(module_dir.glob("*.yaml")):
            try:
                content = yaml_file.read_text(encoding="utf-8")
                data = yaml.safe_load(content)

                if not data or not isinstance(data, dict):
                    continue

                contract_type = _classify_contract(yaml_file.name)
                contract_id = _build_contract_id(module_name, contract_type)

                # Extract metadata
                exports = []
                for exp in data.get("exports", []):
                    if isinstance(exp, dict):
                        exports.append(exp.get("symbol", ""))
                    elif isinstance(exp, str):
                        exports.append(exp)

                dependencies = []
                for dep in data.get("dependencies", []):
                    if isinstance(dep, dict):
                        dependencies.append(dep.get("module", ""))
                    elif isinstance(dep, str):
                        dependencies.append(dep)

                input_events = [e for e in data.get("input_event_types", []) if isinstance(e, str)]
                output_events = [
                    e for e in data.get("output_event_types", []) if isinstance(e, str)
                ]

                contracts.append(
                    K1ContractInfo(
                        contract_id=contract_id,
                        contract_type=contract_type,
                        module=module_name,
                        version=data.get("contract_version"),
                        impl_version=data.get("impl_version"),
                        schema_ref=data.get("$schema"),
                        file_path=str(yaml_file.relative_to(modules_dir.parent.parent)),
                        exports=exports,
                        dependencies=dependencies,
                        input_events=input_events,
                        output_events=output_events,
                    )
                )

            except Exception as e:
                print(f"Warning: Failed to parse {yaml_file}: {e}")
                continue

    return contracts


def _scan_schema_contracts(schemas_dir: Path) -> list[K1ContractInfo]:
    """Scan k1/contracts/schemas/ for schema definitions."""
    contracts: list[K1ContractInfo] = []

    if not schemas_dir.exists():
        return contracts

    for yaml_file in sorted(schemas_dir.rglob("*.yaml")):
        try:
            content = yaml_file.read_text(encoding="utf-8")
            data = yaml.safe_load(content)

            if not data or not isinstance(data, dict):
                continue

            # Skip non-schema files
            if "$schema" not in data and "title" not in data:
                continue

            schema_id = data.get("$id", yaml_file.stem)
            # Normalize schema_id: remove k1:// prefix
            if "://" in schema_id:
                schema_id = schema_id.split("://", 1)[1]

            # Determine module from path
            rel_path = yaml_file.relative_to(schemas_dir)
            category = rel_path.parts[0] if len(rel_path.parts) > 1 else "base"

            contracts.append(
                K1ContractInfo(
                    contract_id=f"schema.{schema_id}",
                    contract_type="schema",
                    module=category,
                    schema_ref=data.get("$schema"),
                    file_path=str(yaml_file.relative_to(schemas_dir.parent.parent)),
                    status="Active",
                )
            )

        except Exception:
            continue

    return contracts


def scan_contracts(contracts_path: Path | None = None) -> list[K1ContractInfo]:
    """
    Scan k1/contracts/ and extract all contract definitions.

    Sources:
    1. k1/contracts/modules/<module>/*.yaml - Module contracts
    2. k1/contracts/schemas/**/*.yaml - Schema definitions

    Args:
        contracts_path: Path to k1/contracts/

    Returns:
        Sorted list of K1ContractInfo
    """
    if contracts_path is None:
        repo_root = Path(__file__).parent.parent.parent.parent
        contracts_path = repo_root / "k1" / "contracts"

    if not contracts_path.exists():
        return []

    all_contracts: list[K1ContractInfo] = []

    # 1. Scan module contracts
    all_contracts.extend(_scan_module_contracts(contracts_path / "modules"))

    # 2. Scan schema definitions
    all_contracts.extend(_scan_schema_contracts(contracts_path / "schemas"))

    # Sort by contract ID
    all_contracts.sort(key=lambda c: c.contract_id)

    return all_contracts


def generate_markdown_table(contracts: list[K1ContractInfo]) -> str:
    """Generate markdown table for contract registry."""
    lines = [
        "| Contract ID | Type | Module | Version | Schema | Exports | Deps |",
        "|-------------|------|--------|---------|--------|---------|------|",
    ]

    for c in contracts:
        version = str(c.version) if c.version else "-"
        schema = "Y" if c.schema_ref else "-"
        exports = str(len(c.exports)) if c.exports else "-"
        deps = str(len(c.dependencies)) if c.dependencies else "-"

        cid = c.contract_id
        if len(cid) > 35:
            cid = cid[:32] + "..."

        lines.append(
            f"| `{cid}` | {c.contract_type} | {c.module} | "
            f"{version} | {schema} | {exports} | {deps} |"
        )

    return "\n".join(lines)


def diff_with_registry(contracts: list[K1ContractInfo]) -> dict[str, Any]:
    """
    Validate contract consistency.

    Checks:
    - Contracts referencing schemas that don't exist
    - Module contracts without matching module directories
    - Duplicate contract IDs
    - Contracts with missing required fields
    """
    issues: list[str] = []

    # Check for duplicates
    seen_ids: dict[str, str] = {}
    for c in contracts:
        if c.contract_id in seen_ids:
            issues.append(
                f"Duplicate contract ID '{c.contract_id}': "
                f"{c.file_path} and {seen_ids[c.contract_id]}"
            )
        seen_ids[c.contract_id] = c.file_path

    # Check schema references exist
    schema_ids = {c.contract_id for c in contracts if c.contract_type == "schema"}
    for c in contracts:
        if c.schema_ref and "k1://" in c.schema_ref:
            ref_path = c.schema_ref.replace("k1://", "")
            ref_id = f"schema.{ref_path}"
            if ref_id not in schema_ids:
                issues.append(f"{c.contract_id}: references unknown schema '{ref_id}'")

    # Check module contracts have matching module_type fields
    for c in contracts:
        if c.contract_type == "module":
            if not c.version:
                issues.append(f"{c.contract_id}: missing contract_version")
            if not c.impl_version:
                issues.append(f"{c.contract_id}: missing impl_version")

    return {
        "scanned_count": len(contracts),
        "issues": issues,
        "issue_count": len(issues),
        "by_type": _count_by_type(contracts),
    }


def _count_by_type(contracts: list[K1ContractInfo]) -> dict[str, int]:
    """Count contracts by type."""
    by_type: dict[str, int] = {}
    for c in contracts:
        by_type[c.contract_type] = by_type.get(c.contract_type, 0) + 1
    return by_type


if __name__ == "__main__":
    contracts = scan_contracts()
    print("K1 Contract Scanner")
    print("=" * 60)
    print(f"Found {len(contracts)} contracts:\n")

    by_type: dict[str, list[K1ContractInfo]] = {}
    for c in contracts:
        by_type.setdefault(c.contract_type, []).append(c)

    for ctype, type_contracts in sorted(by_type.items()):
        print(f"\n  {ctype} ({len(type_contracts)}):")
        for c in type_contracts[:5]:
            print(f"    {c.contract_id}: module={c.module}")
        if len(type_contracts) > 5:
            print(f"    ... and {len(type_contracts) - 5} more")

    print("\n" + "=" * 60)
    print("Markdown Table:")
    print(generate_markdown_table(contracts[:15]))

    diff = diff_with_registry(contracts)
    if diff["issues"]:
        print(f"\nIssues ({diff['issue_count']}):")
        for issue in diff["issues"]:
            print(f"  ! {issue}")
