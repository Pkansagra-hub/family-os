"""
Capability Scanner for K0 Architecture Governance.

Scans capability checks (_require_cap() calls) from syscalls.py and
capability grants/providers from Part 7.2 and Part 8 of k0_architecture_master.md.

Capability Categories:
- Capability Checks: _require_cap() calls in k0/kernel/syscalls.py (Part 7)
- Capability Grants: Per-component grants in Part 7.2
- Fabric Providers: FAB-xxx entries in Part 8.1

Usage:
    from governance.k0.scripts.capability_scanner import (
        scan_capability_checks,
        scan_capability_grants,
        scan_fabric_providers,
        diff_capabilities_with_master,
    )
"""

from __future__ import annotations

import ast
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
class CapabilityCheckInfo:
    """Information about a capability check in syscalls.py."""

    capability_name: str  # e.g., "st_hipp_events.write"
    syscall_method: str  # e.g., "hipp_events_upsert"
    line_number: int
    file_path: str


@dataclass
class CapabilityGrantInfo:
    """Information about a capability grant to a component."""

    component: str  # e.g., "P02", "M16"
    component_type: str  # "Pipeline", "Module", "Kernel"
    capabilities: list[str] = field(default_factory=list)
    notes: str = ""


@dataclass
class FabricProviderInfo:
    """Information about a fabric capability provider."""

    provider_id: str  # e.g., "FAB-001"
    capability_name: str  # e.g., "score_salience"
    handler_function: str  # e.g., "salience.score.run()"
    module_pipeline: str  # e.g., "M06"
    resolution: str  # e.g., "PRIORITY"
    priority: int
    status: str  # "Active", "Planning", "Experimental"
    timeout_ms: int | None = None


def scan_capability_checks(syscalls_path: Path | None = None) -> list[CapabilityCheckInfo]:
    """
    Scan _require_cap() calls from syscalls.py.

    Returns list of CapabilityCheckInfo with capability names and locations.
    """
    if syscalls_path is None:
        syscalls_path = _get_repo_root() / "k0" / "kernel" / "syscalls.py"

    if not syscalls_path.exists():
        return []

    checks: list[CapabilityCheckInfo] = []
    source = syscalls_path.read_text(encoding="utf-8")

    # Parse AST to find _require_cap() calls
    tree = ast.parse(source, filename=str(syscalls_path))

    # Track current method context
    current_method = None

    class CapabilityVisitor(ast.NodeVisitor):
        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            nonlocal current_method
            current_method = node.name
            self.generic_visit(node)
            current_method = None

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            nonlocal current_method
            current_method = node.name
            self.generic_visit(node)
            current_method = None

        def visit_Call(self, node: ast.Call) -> None:
            # Look for self._require_cap("capability_name")
            if (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "_require_cap"
                and node.args
            ):
                arg = node.args[0]
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    checks.append(
                        CapabilityCheckInfo(
                            capability_name=arg.value,
                            syscall_method=current_method or "unknown",
                            line_number=node.lineno,
                            file_path=str(syscalls_path.relative_to(_get_repo_root())).replace(
                                "\\", "/"
                            ),
                        )
                    )
                elif isinstance(arg, ast.Name):
                    # Variable reference (dynamic capability check)
                    checks.append(
                        CapabilityCheckInfo(
                            capability_name=f"<dynamic:{arg.id}>",
                            syscall_method=current_method or "unknown",
                            line_number=node.lineno,
                            file_path=str(syscalls_path.relative_to(_get_repo_root())).replace(
                                "\\", "/"
                            ),
                        )
                    )
            self.generic_visit(node)

    visitor = CapabilityVisitor()
    visitor.visit(tree)

    return checks


def scan_fabric_providers_from_yaml(
    capabilities_path: Path | None = None,
) -> list[FabricProviderInfo]:
    """
    Scan fabric provider definitions from core.v1.yaml.

    Returns list of FabricProviderInfo with capability details.
    """
    if capabilities_path is None:
        capabilities_path = _get_repo_root() / "k0" / "contracts" / "capabilities" / "core.v1.yaml"

    if not capabilities_path.exists():
        return []

    providers: list[FabricProviderInfo] = []

    content = capabilities_path.read_text(encoding="utf-8")
    data = yaml.safe_load(content)

    if not data or "capabilities" not in data:
        return []

    capabilities = data["capabilities"]
    provider_id_counter = 1

    for cap_name, cap_def in capabilities.items():
        if not isinstance(cap_def, dict):
            continue

        cap_providers = cap_def.get("providers", [])
        default_timeout = cap_def.get("default_timeout_ms", 0)

        for prov in cap_providers:
            if not isinstance(prov, dict):
                continue

            module_id = prov.get("module_id", "unknown")
            handler = f"{module_id}.run()"

            providers.append(
                FabricProviderInfo(
                    provider_id=f"FAB-{provider_id_counter:03d}",
                    capability_name=cap_name,
                    handler_function=handler,
                    module_pipeline=module_id,
                    resolution="PRIORITY",
                    priority=prov.get("priority", 1),
                    status="Active",  # YAML doesn't have status, assume active
                    timeout_ms=default_timeout,
                )
            )
            provider_id_counter += 1

    return providers


def diff_capability_checks_with_master(
    checks: list[CapabilityCheckInfo], master_path: Path
) -> dict[str, Any]:
    """
    Compare scanned capability checks with Part 7.2 Capability Grants.

    Returns dict with:
        - missing_in_master: capabilities checked but not granted anywhere
        - missing_in_code: capabilities granted but never checked
        - scanned_count: unique capabilities found in checks
        - registered_count: unique capabilities in grants
    """
    content = master_path.read_text(encoding="utf-8")

    # Extract all unique capabilities from Part 7.2 "All Unique Capabilities" table
    registered = set()
    planning_caps = set()
    deprecated_caps = set()

    # Look for the unique capabilities table
    section_match = re.search(
        r"### All Unique Capabilities.*?(?=### |## |# Part |\Z)",
        content,
        re.DOTALL,
    )

    if section_match:
        section = section_match.group(0)
        # Pattern: | `capability.name` | Type | Status |
        cap_pattern = re.compile(r"\|\s*`([a-z_0-9.]+)`\s*\|")
        for match in cap_pattern.finditer(section):
            cap_name = match.group(1)
            registered.add(cap_name)

            # Check status
            line_start = section.rfind("\n", 0, match.start())
            line_end = section.find("\n", match.end())
            line = section[line_start:line_end] if line_end > line_start else ""
            if "Planned" in line or "🎯" in line:
                planning_caps.add(cap_name)
            elif "Deprecated" in line or "❌" in line:
                deprecated_caps.add(cap_name)

    # Get unique capabilities from checks (excluding dynamic)
    scanned_caps = {c.capability_name for c in checks if not c.capability_name.startswith("<")}

    # Capabilities that are checked but not in master (excluding planning ones)
    missing_in_master = scanned_caps - registered

    # Capabilities granted but never checked (only Active ones)
    active_caps = registered - planning_caps - deprecated_caps
    missing_in_code = active_caps - scanned_caps

    return {
        "missing_in_master": missing_in_master,
        "missing_in_code": missing_in_code,
        "scanned_count": len(scanned_caps),
        "registered_count": len(registered),
        "planning_count": len(planning_caps),
    }


def diff_fabric_providers_with_master(
    providers: list[FabricProviderInfo], master_path: Path
) -> dict[str, Any]:
    """
    Compare scanned fabric providers with Part 8.1 Provider Registry.

    Returns dict with:
        - missing_in_master: providers in YAML but not in doc
        - missing_in_code: providers in doc but not in YAML
        - scanned_count: providers from YAML
        - registered_count: providers in master doc
    """
    content = master_path.read_text(encoding="utf-8")

    # Extract fabric providers from Part 8.1
    registered = set()
    planning_providers = set()

    section_match = re.search(
        r"## 8\.1 Capability Provider Registry.*?(?=## 8\.\d|# Part |\Z)",
        content,
        re.DOTALL,
    )

    if section_match:
        section = section_match.group(0)
        # Pattern: | FAB-001 | `capability_name` |
        provider_pattern = re.compile(r"\|\s*(FAB-\d+)\s*\|\s*`([a-z_]+)`\s*\|")
        for match in provider_pattern.finditer(section):
            provider_id = match.group(1)
            cap_name = match.group(2)
            registered.add(cap_name)

            # Check status
            line_start = section.rfind("\n", 0, match.start())
            line_end = section.find("\n", match.end())
            line = section[line_start:line_end] if line_end > line_start else ""
            if "Planning" in line or "🎯" in line:
                planning_providers.add(cap_name)

    scanned_caps = {p.capability_name for p in providers}
    missing_in_code = registered - scanned_caps - planning_providers

    return {
        "missing_in_master": scanned_caps - registered,
        "missing_in_code": missing_in_code,
        "scanned_count": len(providers),
        "registered_count": len(registered),
        "planning_count": len(planning_providers),
    }


if __name__ == "__main__":
    # Quick test
    print("=" * 60)
    print("Capability Scanner Test")
    print("=" * 60)

    print("\n[1] Scanning capability checks from syscalls.py...")
    checks = scan_capability_checks()
    print(f"Found {len(checks)} capability checks:")
    unique_caps = set(c.capability_name for c in checks)
    print(f"  Unique capabilities: {len(unique_caps)}")
    for cap in sorted(unique_caps)[:10]:
        count = sum(1 for c in checks if c.capability_name == cap)
        print(f"    {cap} ({count} checks)")
    if len(unique_caps) > 10:
        print(f"    ... and {len(unique_caps) - 10} more")

    print("\n[2] Scanning fabric providers from YAML...")
    providers = scan_fabric_providers_from_yaml()
    print(f"Found {len(providers)} fabric providers:")
    for p in providers[:5]:
        print(f"  {p.provider_id}: {p.capability_name} -> {p.module_pipeline}")
    if len(providers) > 5:
        print(f"  ... and {len(providers) - 5} more")

    # Test diff
    print("\n[3] Testing diff with master...")
    master_path = _get_repo_root() / "governance" / "k0" / "k0_architecture_master.md"
    if master_path.exists():
        # Capability checks
        diff = diff_capability_checks_with_master(checks, master_path)
        print(
            f"Capability Checks - Scanned: {diff['scanned_count']}, "
            f"Registered: {diff['registered_count']}, Planning: {diff['planning_count']}"
        )
        if diff["missing_in_master"]:
            print(f"  Missing in master: {diff['missing_in_master']}")
        if diff["missing_in_code"]:
            print(f"  Missing in code: {diff['missing_in_code']}")

        # Fabric providers
        diff = diff_fabric_providers_with_master(providers, master_path)
        print(
            f"Fabric Providers - Scanned: {diff['scanned_count']}, "
            f"Registered: {diff['registered_count']}, Planning: {diff['planning_count']}"
        )
        if diff["missing_in_master"]:
            print(f"  Missing in master: {diff['missing_in_master']}")
        if diff["missing_in_code"]:
            print(f"  Missing in code: {diff['missing_in_code']}")
