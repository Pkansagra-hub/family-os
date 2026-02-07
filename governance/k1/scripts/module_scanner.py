"""
K1 Module Scanner - Extract module definitions from k1/*/ directories.

Scans K1 module directories and extracts:
- Module directory name (fabric, sessionstate, orchestrator, etc.)
- Contract existence and details
- Python file inventory
- README presence
- Port/adapter counts
- Test coverage

Usage:
    from governance.k1.scripts.module_scanner import scan_modules
    modules = scan_modules()
    for m in modules:
        print(f"{m.name}: [{m.status}] {m.file_count} files")
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# Directories under k1/ that are NOT modules (infrastructure/support)
NON_MODULE_DIRS: set[str] = {
    "__pycache__",
    "docs",
    "scripts",
    "config",
    "contracts",
}


@dataclass
class K1ModuleInfo:
    """Extracted K1 module information."""

    name: str  # fabric, sessionstate, orchestrator
    path: str  # k1/fabric
    status: str  # Active, Planning, Experimental, Deprecated
    has_readme: bool
    has_contract: bool
    has_init: bool
    file_count: int  # Python files
    line_count: int  # Total non-empty lines
    port_count: int  # Port interfaces (I*Port classes)
    adapter_count: int  # Adapter implementations
    test_count: int  # Test files found
    dependencies: list[str] = field(default_factory=list)  # From contract
    exports: list[str] = field(default_factory=list)  # From contract
    version: str | None = None  # From contract
    contract_path: str | None = None
    tags: list[str] = field(default_factory=list)


def _count_python_files(module_dir: Path) -> int:
    """Count Python files in module directory (excluding __pycache__)."""
    count = 0
    for py_file in module_dir.rglob("*.py"):
        if "__pycache__" not in str(py_file):
            count += 1
    return count


def _count_lines(module_dir: Path) -> int:
    """Count total non-empty lines across all Python files."""
    total = 0
    for py_file in module_dir.rglob("*.py"):
        if "__pycache__" not in str(py_file):
            try:
                text = py_file.read_text(encoding="utf-8")
                total += sum(1 for line in text.split("\n") if line.strip())
            except Exception:
                continue
    return total


def _count_ports(module_dir: Path) -> int:
    """Count port interface definitions (I*Port, I*Provider, Protocol classes in ports/)."""
    count = 0
    ports_dir = module_dir / "ports"

    # Scan ports/ directory if it exists
    search_dirs = [ports_dir] if ports_dir.exists() else [module_dir]

    for search_dir in search_dirs:
        for py_file in search_dir.rglob("*.py"):
            if "__pycache__" in str(py_file):
                continue
            try:
                content = py_file.read_text(encoding="utf-8")
                # Match ABC-based or Protocol-based port interfaces
                count += len(
                    re.findall(
                        r"class\s+I[A-Z]\w*(?:Port|Provider)\s*\(",
                        content,
                    )
                )
            except Exception:
                continue
    return count


def _count_adapters(module_dir: Path) -> int:
    """Count adapter implementations (classes implementing port interfaces)."""
    count = 0
    adapters_dir = module_dir / "adapters"

    search_dirs = [adapters_dir] if adapters_dir.exists() else []
    # Also check module root for inline adapters
    search_dirs.append(module_dir)

    seen_files: set[str] = set()

    for search_dir in search_dirs:
        for py_file in search_dir.glob("*.py"):
            if "__pycache__" in str(py_file) or str(py_file) in seen_files:
                continue
            seen_files.add(str(py_file))
            try:
                content = py_file.read_text(encoding="utf-8")
                # Match classes that inherit from I*Port
                count += len(
                    re.findall(
                        r"class\s+\w+\s*\([^)]*I[A-Z]\w*(?:Port|Provider)",
                        content,
                    )
                )
            except Exception:
                continue
    return count


def _find_test_files(tests_dir: Path, module_name: str) -> int:
    """Count test files for this module."""
    count = 0
    # Check tests/k1/<module>/
    module_test_dir = tests_dir / "k1" / module_name
    if module_test_dir.exists():
        count += sum(1 for f in module_test_dir.rglob("test_*.py"))
    # Check tests/k1/test_<module>*.py
    for f in (tests_dir / "k1").glob(f"test_{module_name}*.py"):
        count += 1
    return count


def _parse_module_contract(contracts_dir: Path, module_name: str) -> dict[str, Any]:
    """Parse module contract YAML for metadata."""
    result: dict[str, Any] = {
        "has_contract": False,
        "version": None,
        "dependencies": [],
        "exports": [],
        "tags": [],
        "contract_path": None,
    }

    # Check k1/contracts/modules/<module_name>/module.contract.yaml
    contract_path = contracts_dir / "modules" / module_name / "module.contract.yaml"
    if not contract_path.exists():
        # Try flat naming: k1/contracts/modules/<module_name>.contract.yaml
        contract_path = contracts_dir / "modules" / f"{module_name}.contract.yaml"
        if not contract_path.exists():
            return result

    try:
        content = contract_path.read_text(encoding="utf-8")
        contract = yaml.safe_load(content)

        if not contract or not isinstance(contract, dict):
            return result

        result["has_contract"] = True
        result["contract_path"] = str(contract_path.relative_to(contracts_dir.parent.parent))
        result["version"] = contract.get("impl_version")

        metadata = contract.get("metadata", {})
        result["tags"] = metadata.get("tags", [])

        # Extract dependencies
        for dep in contract.get("dependencies", []):
            if isinstance(dep, dict):
                result["dependencies"].append(dep.get("module", str(dep)))
            elif isinstance(dep, str):
                result["dependencies"].append(dep)

        # Extract exports
        for exp in contract.get("exports", []):
            if isinstance(exp, dict):
                result["exports"].append(exp.get("symbol", str(exp)))
            elif isinstance(exp, str):
                result["exports"].append(exp)

    except Exception:
        pass

    return result


def _infer_status(module_dir: Path, has_contract: bool) -> str:
    """Infer module status from directory contents."""
    if not any(module_dir.glob("*.py")):
        return "Planning"
    if has_contract:
        return "Active"

    # Check README for status hints
    readme = module_dir / "README.md"
    if readme.exists():
        try:
            content = readme.read_text(encoding="utf-8")[:500].lower()
            if "experimental" in content:
                return "Experimental"
            if "deprecated" in content:
                return "Deprecated"
            if "planning" in content:
                return "Planning"
        except Exception:
            pass

    # Has Python files but no contract
    return "Experimental"


def scan_modules(k1_path: Path | None = None) -> list[K1ModuleInfo]:
    """
    Scan k1/ directories and extract all module definitions.

    Each top-level directory under k1/ is treated as a module
    (excluding NON_MODULE_DIRS like config, contracts, docs, scripts).

    Args:
        k1_path: Path to k1/ directory

    Returns:
        Sorted list of K1ModuleInfo
    """
    if k1_path is None:
        repo_root = Path(__file__).parent.parent.parent.parent
        k1_path = repo_root / "k1"

    if not k1_path.exists():
        return []

    contracts_dir = k1_path / "contracts"
    tests_dir = k1_path.parent / "tests"

    modules: list[K1ModuleInfo] = []

    for module_dir in sorted(k1_path.iterdir()):
        if not module_dir.is_dir():
            continue
        if module_dir.name.startswith("_") or module_dir.name.startswith("."):
            continue
        if module_dir.name in NON_MODULE_DIRS:
            continue

        # Parse contract
        contract_info = _parse_module_contract(contracts_dir, module_dir.name)

        modules.append(
            K1ModuleInfo(
                name=module_dir.name,
                path=f"k1/{module_dir.name}",
                status=_infer_status(module_dir, contract_info["has_contract"]),
                has_readme=(module_dir / "README.md").exists(),
                has_contract=contract_info["has_contract"],
                has_init=(module_dir / "__init__.py").exists(),
                file_count=_count_python_files(module_dir),
                line_count=_count_lines(module_dir),
                port_count=_count_ports(module_dir),
                adapter_count=_count_adapters(module_dir),
                test_count=_find_test_files(tests_dir, module_dir.name),
                dependencies=contract_info["dependencies"],
                exports=contract_info["exports"],
                version=contract_info["version"],
                contract_path=contract_info["contract_path"],
                tags=contract_info["tags"],
            )
        )

    return modules


def generate_markdown_table(modules: list[K1ModuleInfo]) -> str:
    """Generate markdown table for module registry."""
    lines = [
        "| Module | Status | Files | Lines | Ports | Adapters | Tests | Contract | README |",
        "|--------|--------|-------|-------|-------|----------|-------|----------|--------|",
    ]

    for m in modules:
        contract = "Y" if m.has_contract else "-"
        readme = "Y" if m.has_readme else "-"
        tests = str(m.test_count) if m.test_count else "-"

        lines.append(
            f"| `{m.name}` | {m.status} | {m.file_count} | {m.line_count} | "
            f"{m.port_count} | {m.adapter_count} | {tests} | {contract} | {readme} |"
        )

    return "\n".join(lines)


def generate_summary(modules: list[K1ModuleInfo]) -> dict[str, Any]:
    """Generate summary statistics."""
    by_status: dict[str, int] = {}
    total_files = 0
    total_lines = 0
    total_ports = 0
    total_tests = 0

    for m in modules:
        by_status[m.status] = by_status.get(m.status, 0) + 1
        total_files += m.file_count
        total_lines += m.line_count
        total_ports += m.port_count
        total_tests += m.test_count

    return {
        "total_modules": len(modules),
        "by_status": by_status,
        "total_files": total_files,
        "total_lines": total_lines,
        "total_ports": total_ports,
        "total_tests": total_tests,
        "with_contract": sum(1 for m in modules if m.has_contract),
        "with_readme": sum(1 for m in modules if m.has_readme),
    }


def diff_with_registry(modules: list[K1ModuleInfo]) -> dict[str, Any]:
    """
    Validate module consistency.

    Checks:
    - Modules without contracts
    - Modules without README
    - Modules without __init__.py
    - Active modules without tests
    - Dependency references to unknown modules
    """
    issues: list[str] = []
    module_names = {m.name for m in modules}

    for m in modules:
        if m.status == "Active" and not m.has_contract:
            issues.append(f"{m.name}: Active module has no contract")
        if not m.has_readme:
            issues.append(f"{m.name}: missing README.md")
        if not m.has_init and m.file_count > 0:
            issues.append(f"{m.name}: missing __init__.py")
        if m.status == "Active" and m.test_count == 0:
            issues.append(f"{m.name}: Active module has no tests")

        # Check dependencies
        for dep in m.dependencies:
            if dep not in module_names and dep not in ("k0", "kernel", "bus"):
                issues.append(f"{m.name}: depends on unknown module '{dep}'")

    return {
        "scanned_count": len(modules),
        "issues": issues,
        "issue_count": len(issues),
    }


if __name__ == "__main__":
    modules = scan_modules()
    print("K1 Module Scanner")
    print("=" * 60)
    print(f"Found {len(modules)} modules:\n")

    for m in modules:
        contract = "Y" if m.has_contract else "-"
        print(
            f"  {m.name:<20} [{m.status:<12}] "
            f"{m.file_count:>3} files, {m.line_count:>5} lines, "
            f"{m.port_count} ports, {m.test_count} tests, contract:{contract}"
        )

    summary = generate_summary(modules)
    print(
        f"\nSummary: {summary['total_modules']} modules, "
        f"{summary['total_files']} files, {summary['total_lines']} lines, "
        f"{summary['with_contract']} contracted, {summary['total_tests']} tests"
    )

    print("\n" + "=" * 60)
    print("Markdown Table:")
    print(generate_markdown_table(modules))

    diff = diff_with_registry(modules)
    if diff["issues"]:
        print(f"\nIssues ({diff['issue_count']}):")
        for issue in diff["issues"][:15]:
            print(f"  ! {issue}")
