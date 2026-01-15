"""
Module Scanner - Extract module definitions from k0/modules/*/README.md.

Parses module READMEs and Python files to extract:
- Module ID (M01, M02, etc.)
- Module name
- Status (Implemented, Planning, Deprecated)
- ADR references
- Pipeline usage
- Required capabilities/syscalls

Usage:
    from governance.k0.scripts.module_scanner import scan_modules
    modules = scan_modules()
    for m in modules:
        print(f"{m['module_id']}: {m['name']} [{m['status']}]")
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ModuleInfo:
    """Extracted module information."""

    module_id: str  # M01, M02, etc.
    name: str  # pattern_separate, semantic_project
    folder: str  # hippocampus, affect, etc.
    full_path: str  # hippocampus.pattern_separate
    status: str  # Implemented, Planning, Deprecated
    version: str
    adr_ref: str | None
    readme_exists: bool
    contract_exists: bool
    python_file: str | None
    line_count: int
    test_file: str | None
    capabilities: list[str] = field(default_factory=list)


def _parse_readme_table(readme_content: str) -> list[dict[str, str]]:
    """Parse module table from README.md."""
    modules = []
    lines = readme_content.split("\n")
    in_table = False
    headers = []
    best_table: list[dict[str, str]] = []

    for line in lines:
        # Detect table header - prefer tables with ID column
        if "|" in line and ("Module" in line or "module" in line or "ID" in line):
            # Check if this table has an ID column (more valuable)
            potential_headers = [
                h.strip().lower().replace("**", "") for h in line.split("|") if h.strip()
            ]
            if "id" in potential_headers:
                # Found a table with ID column - use this one
                in_table = True
                headers = potential_headers
                modules = []  # Reset to capture this table
                continue
            elif not in_table:
                # No ID column, but no table found yet - use as fallback
                in_table = True
                headers = potential_headers
                continue

        # Skip separator line
        if in_table and re.match(r"^\|[\s\-:|]+\|$", line):
            continue

        # Parse table row
        if in_table and line.startswith("|"):
            cells = [c.strip() for c in line.split("|") if c.strip()]
            if len(cells) >= 2:
                row = dict(zip(headers, cells))
                modules.append(row)
        elif in_table and not line.startswith("|"):
            # End of table - if we found an ID column, keep this result
            if "id" in headers:
                best_table = modules.copy()
            elif not best_table:
                best_table = modules.copy()
            in_table = False
            modules = []
            headers = []

    # Handle case where table extends to end of file
    if modules:
        if "id" in headers:
            best_table = modules
        elif not best_table:
            best_table = modules

    return best_table


def _extract_module_id(row: dict[str, str]) -> str | None:
    """Extract module ID like M01, M02 from row."""
    for key in ["id", "module id", "module"]:
        if key in row:
            match = re.search(r"M\d{2}", row[key])
            if match:
                return match.group()
    return None


def _extract_status(row: dict[str, str], readme_content: str = "") -> str:
    """Extract status from row or infer from content."""
    for key in ["status"]:
        if key in row:
            val = row[key].lower()
            if "implemented" in val or "✅" in val:
                return "Production"
            if "planning" in val or "📋" in val or "adr complete" in val.lower():
                return "ADR-Complete"
            if "deprecated" in val or "❌" in val:
                return "Deprecated"
            if "experimental" in val or "🧪" in val:
                return "Experimental"
    return "Unknown"


def _extract_adr(row: dict[str, str]) -> str | None:
    """Extract ADR reference from row."""
    for key in ["adr", "adr reference"]:
        if key in row:
            match = re.search(r"K\d{3}(?:\.\d+)?", row[key])
            if match:
                return match.group()
    return None


def _find_python_file(module_dir: Path, module_name: str) -> Path | None:
    """Find Python file for module."""
    candidates = [
        module_dir / f"{module_name}.py",
        module_dir / f"{module_name}_module.py",
        module_dir / "__init__.py",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _find_contract(contracts_dir: Path, folder: str, module_name: str) -> Path | None:
    """Find contract YAML for module."""
    candidates = [
        contracts_dir / "modules" / f"{folder}.{module_name}.v1.yaml",
        contracts_dir / "modules" / f"{module_name}.v1.yaml",
        contracts_dir / "modules" / f"{folder}_{module_name}.yaml",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _count_lines(file_path: Path) -> int:
    """Count non-empty lines in file."""
    if not file_path.exists():
        return 0
    return sum(1 for line in file_path.read_text(encoding="utf-8").split("\n") if line.strip())


def _find_test_file(tests_dir: Path, folder: str, module_name: str) -> Path | None:
    """Find test file for module."""
    candidates = [
        tests_dir / "k0" / "modules" / folder / f"test_{module_name}.py",
        tests_dir / "k0" / "modules" / f"test_{folder}_{module_name}.py",
        tests_dir / "integration" / f"test_{module_name}.py",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def scan_modules(
    modules_path: Path | None = None, master_path: Path | None = None
) -> list[ModuleInfo]:
    """
    Scan k0/modules/ and extract all module definitions.

    ADR-K021: Uses contracts as primary source, master doc mapping as fallback.
    Only scans Python files that have either a contract OR are registered in master.

    Args:
        modules_path: Path to k0/modules/ (defaults to repo root)
        master_path: Path to master architecture doc for ID lookup

    Returns:
        List of ModuleInfo with module details
    """
    if modules_path is None:
        repo_root = Path(__file__).parent.parent.parent.parent
        modules_path = repo_root / "k0" / "modules"

    if master_path is None:
        master_path = Path(__file__).parent.parent / "k0_architecture_master.md"

    if not modules_path.exists():
        raise FileNotFoundError(f"Modules directory not found at {modules_path}")

    contracts_dir = modules_path.parent / "contracts"
    tests_dir = modules_path.parent.parent / "tests"

    # Build ID mapping from master document
    id_mapping = {}
    if master_path.exists():
        id_mapping = _build_module_id_mapping(master_path)

    # ADR-K021: Build set of modules with contracts (authoritative source)
    contracted_modules: set[str] = set()
    modules_contracts_dir = contracts_dir / "modules"
    if modules_contracts_dir.exists():
        for yaml_file in modules_contracts_dir.glob("*.yaml"):
            # Parse contract to extract folder.module_name pattern
            # Contract names: folder.module_name.v1.yaml or module_name.v1.yaml
            stem = yaml_file.stem  # e.g., "hippocampus.consolidate.v1"
            parts = stem.rsplit(".v", 1)[0]  # Remove version suffix
            contracted_modules.add(parts)

    modules: list[ModuleInfo] = []

    # Scan each module subdirectory - only scan modules with contracts OR in master
    for folder in sorted(modules_path.iterdir()):
        if not folder.is_dir() or folder.name.startswith("_"):
            continue

        readme_path = folder / "README.md"
        readme_exists = readme_path.exists()

        # Scan Python files - only include if contracted OR registered in master
        for py_file in folder.glob("*.py"):
            if py_file.name.startswith("_"):
                continue

            module_name = py_file.stem
            key = f"{folder.name}.{module_name}"

            # ADR-K021: Skip modules not in contracts AND not in master mapping
            has_contract = key in contracted_modules or module_name in contracted_modules
            in_master = key in id_mapping

            if not has_contract and not in_master:
                continue  # Skip unregistered helper files

            # Get ID from master mapping
            module_id = id_mapping.get(key, "Mxx")

            modules.append(
                ModuleInfo(
                    module_id=module_id,
                    name=module_name,
                    folder=folder.name,
                    full_path=key,
                    status="Unknown",
                    version="0.0.0",
                    adr_ref=None,
                    readme_exists=readme_exists,
                    contract_exists=has_contract,
                    python_file=py_file.name,
                    line_count=_count_lines(py_file),
                    test_file=None,
                )
            )

    return modules


def generate_markdown_table(modules: list[ModuleInfo]) -> str:
    """Generate markdown table for Part 3.1 Module Registry."""
    lines = [
        "| ID | Name | Folder | Status | Version | ADR | Code | Contract | Tests |",
        "|----|------|--------|--------|---------|-----|------|----------|-------|",
    ]

    for m in modules:
        adr = f"`{m.adr_ref}`" if m.adr_ref else "-"
        code = f"`{m.python_file}` ({m.line_count}L)" if m.python_file else "-"
        contract = "✅" if m.contract_exists else "❌"
        tests = f"`{m.test_file}`" if m.test_file else "-"

        lines.append(
            f"| {m.module_id} | `{m.name}` | {m.folder} | {m.status} | {m.version} | {adr} | {code} | {contract} | {tests} |"
        )

    return "\n".join(lines)


def _build_module_id_mapping(master_path: Path) -> dict[str, str]:
    """
    Build a mapping from module path to module ID using the master document.

    Parses the Module Master Table (Part 3.1) to extract:
    - Module Path column: `k0/modules/core/event_emitter.py`
    - ID column: `M17`

    Returns:
        Dict mapping "folder.module_name" -> "M17"
    """
    from governance.k0.scripts.markdown_parser import MarkdownRegistry

    registry = MarkdownRegistry(master_path)
    table = registry.get_table("3.1", "Module Master")
    if not table:
        return {}

    mapping = {}

    # Find column indices
    id_idx = None
    path_idx = None
    for i, header in enumerate(table.headers):
        if header.lower() == "id":
            id_idx = i
        if "module path" in header.lower() or "path" in header.lower():
            if "contract" not in header.lower():
                path_idx = i

    if id_idx is None or path_idx is None:
        return {}

    for row in table.rows:
        if len(row.cells) <= max(id_idx, path_idx):
            continue

        module_id_cell = row.cells[id_idx]
        path_cell = row.cells[path_idx]

        # Extract module ID (M01, M17, etc.)
        id_match = re.search(r"M\d{2}", module_id_cell)
        if not id_match:
            continue
        module_id = id_match.group()

        # Extract path: k0/modules/core/event_emitter.py -> core.event_emitter
        # Remove backticks and parse path
        path_clean = path_cell.strip("`").strip()
        path_match = re.search(r"k0/modules/([^/]+)/([^/.]+)(?:\.py)?", path_clean)
        if path_match:
            folder = path_match.group(1)
            module_name = path_match.group(2)
            key = f"{folder}.{module_name}"
            mapping[key] = module_id

    return mapping


def diff_with_master(modules: list[ModuleInfo], master_path: Path) -> dict[str, Any]:
    """
    Compare scanned modules with what's in k0_architecture_master.md.

    Uses MarkdownRegistry for reliable AST-based table parsing.
    Builds a mapping from module paths to IDs for accurate comparison.
    Only Active modules are checked for drift - Planning modules are excluded.

    Returns dict with:
        - missing_in_master: modules in code but not in doc
        - missing_in_code: modules in doc but not in code (Active only)
    """
    from governance.k0.scripts.markdown_parser import MarkdownRegistry

    registry = MarkdownRegistry(master_path)

    # Build path-to-ID mapping from master
    path_to_id = _build_module_id_mapping(master_path)

    # Get all registered module IDs from Part 3.1
    table = registry.get_table("3.1", "Module Master")
    if not table:
        table = registry.get_table_by_title("Module Master Table")

    # registered_all: all module IDs
    # registered_active: only modules with Active status
    registered_all = set()
    registered_active = set()

    if table:
        # Find status column index
        status_idx = None
        for i, header in enumerate(table.headers):
            if "status" in header.lower():
                status_idx = i
                break

        for row in table.rows:
            first_cell = row.cells[0] if row.cells else ""
            match = re.search(r"M\d{2}", first_cell)
            if match:
                module_id = match.group()
                registered_all.add(module_id)

                # Check status - only count Active for missing_in_code
                if status_idx is not None and len(row.cells) > status_idx:
                    status = row.cells[status_idx]
                    if "Active" in status:
                        registered_active.add(module_id)
                else:
                    # No status column, assume all are active
                    registered_active.add(module_id)

    # Map scanned modules to IDs using the path mapping
    scanned_ids = set()
    for m in modules:
        # Try to find ID from mapping
        key = f"{m.folder}.{m.name}"
        if key in path_to_id:
            scanned_ids.add(path_to_id[key])
        elif m.module_id.startswith("M") and m.module_id != "Mxx":
            scanned_ids.add(m.module_id)

    return {
        "missing_in_master": sorted(scanned_ids - registered_all),
        "missing_in_code": sorted(registered_active - scanned_ids),
        "scanned_count": len(modules),
        "registered_count": len(registered_all),
    }


if __name__ == "__main__":
    modules = scan_modules()
    print(f"Found {len(modules)} modules:\n")
    for m in modules:
        contract = "✅" if m.contract_exists else "❌"
        print(f"  {m.module_id}: {m.full_path} [{m.status}] Contract:{contract}")

    print("\n" + "=" * 60)
    print("Markdown Table:")
    print(generate_markdown_table(modules))
