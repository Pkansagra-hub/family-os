"""
Syscall Scanner - Extract syscall definitions from k0/kernel/syscalls.py.

Parses the Syscalls class and extracts:
- Method name
- Required capability (from _require_capability call)
- Parameters
- Return type
- Deprecation status (from docstring)

Usage:
    from governance.k0.scripts.syscall_scanner import scan_syscalls
    syscalls = scan_syscalls()
    for s in syscalls:
        print(f"{s['method']} requires {s['capability']}")
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class SyscallInfo:
    """Extracted syscall information."""

    method: str
    capability: str | None
    params: list[str]
    return_type: str
    status: str  # Active, Deprecated, Not-Implemented
    docstring_summary: str
    line_number: int
    tables_accessed: list[str] = field(default_factory=list)


def _extract_capability_from_body(node: ast.AsyncFunctionDef) -> str | None:
    """Extract capability from self._require_cap() call."""
    for stmt in ast.walk(node):
        if isinstance(stmt, ast.Call) and isinstance(stmt.func, ast.Attribute):
            # Look for self._require_cap("cap")
            if stmt.func.attr == "_require_cap":
                if stmt.args and isinstance(stmt.args[0], ast.Constant):
                    val = stmt.args[0].value
                    if isinstance(val, str):
                        return val
    return None


def _extract_tables_from_body(node: ast.AsyncFunctionDef) -> list[str]:
    """Extract table names from SQL or method calls."""
    tables = set()
    source = ast.unparse(node) if hasattr(ast, "unparse") else ""

    # Pattern for st_* table names
    table_pattern = re.compile(r"\bst_[a-z_]+\b")
    for match in table_pattern.findall(source):
        tables.add(match)

    return sorted(tables)


def _get_docstring_summary(node: ast.AsyncFunctionDef) -> str:
    """Extract first line of docstring."""
    docstring = ast.get_docstring(node)
    if docstring:
        first_line = docstring.split("\n")[0].strip()
        return first_line[:100]  # Truncate for table
    return ""


def _detect_status(node: ast.AsyncFunctionDef) -> str:
    """Detect status from docstring and decorators."""
    docstring = ast.get_docstring(node) or ""
    docstring_lower = docstring.lower()

    if "deprecated" in docstring_lower:
        return "Deprecated"
    if "not implemented" in docstring_lower or "notimplementederror" in docstring_lower:
        return "Not-Implemented"
    if "placeholder" in docstring_lower or "stub" in docstring_lower:
        return "Planning"

    # Check for raise NotImplementedError
    for stmt in ast.walk(node):
        if isinstance(stmt, ast.Raise):
            if isinstance(stmt.exc, ast.Call):
                if isinstance(stmt.exc.func, ast.Name):
                    if stmt.exc.func.id == "NotImplementedError":
                        return "Not-Implemented"

    return "Active"


def _extract_params(node: ast.AsyncFunctionDef) -> list[str]:
    """Extract parameter names (excluding self)."""
    params = []
    for arg in node.args.args:
        if arg.arg != "self":
            params.append(arg.arg)
    # Add **kwargs if present
    if node.args.kwarg:
        params.append(f"**{node.args.kwarg.arg}")
    return params


def _extract_return_type(node: ast.AsyncFunctionDef) -> str:
    """Extract return type annotation."""
    if node.returns:
        try:
            return ast.unparse(node.returns)
        except Exception:
            return "Any"
    return "None"


def scan_syscalls(syscalls_path: Path | None = None) -> list[SyscallInfo]:
    """
    Scan k0/kernel/syscalls.py and extract all syscall methods.

    Args:
        syscalls_path: Path to syscalls.py (defaults to k0/kernel/syscalls.py)

    Returns:
        List of SyscallInfo with method details
    """
    if syscalls_path is None:
        # Resolve relative to this script
        repo_root = Path(__file__).parent.parent.parent.parent
        syscalls_path = repo_root / "k0" / "kernel" / "syscalls.py"

    if not syscalls_path.exists():
        raise FileNotFoundError(f"syscalls.py not found at {syscalls_path}")

    source = syscalls_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(syscalls_path))

    syscalls: list[SyscallInfo] = []

    # Find the Syscalls class
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "Syscalls":
            # Extract all async methods
            for item in node.body:
                if isinstance(item, ast.AsyncFunctionDef):
                    # Skip private methods
                    if item.name.startswith("_"):
                        continue

                    syscall = SyscallInfo(
                        method=item.name,
                        capability=_extract_capability_from_body(item),
                        params=_extract_params(item),
                        return_type=_extract_return_type(item),
                        status=_detect_status(item),
                        docstring_summary=_get_docstring_summary(item),
                        line_number=item.lineno,
                        tables_accessed=_extract_tables_from_body(item),
                    )
                    syscalls.append(syscall)

    return syscalls


def generate_markdown_table(syscalls: list[SyscallInfo]) -> str:
    """Generate markdown table for Part 7.1 Syscall Methods Registry."""
    lines = [
        "| Method | Capability | Params | Return | Status | Line | Tables |",
        "|--------|------------|--------|--------|--------|------|--------|",
    ]

    for s in syscalls:
        cap = f"`{s.capability}`" if s.capability else "-"
        params = ", ".join(s.params[:3])  # First 3 params
        if len(s.params) > 3:
            params += "..."
        tables = ", ".join(s.tables_accessed[:2]) or "-"
        lines.append(
            f"| `{s.method}` | {cap} | {params} | `{s.return_type}` | {s.status} | {s.line_number} | {tables} |"
        )

    return "\n".join(lines)


def diff_with_master(syscalls: list[SyscallInfo], master_path: Path) -> dict[str, Any]:
    """
    Compare scanned syscalls with what's in k0_architecture_master.md.

    Uses MarkdownRegistry for reliable AST-based table parsing.

    Returns dict with:
        - missing_in_master: syscalls in code but not in doc
        - missing_in_code: syscalls in doc but not in code
        - status_mismatch: syscalls with different status
    """
    from governance.k0.scripts.markdown_parser import MarkdownRegistry, extract_backtick_value

    registry = MarkdownRegistry(master_path)

    # Get the syscall table from Part 7.1
    table = registry.get_table("7.1", "Syscall")
    if not table:
        # Fallback: try by title only
        table = registry.get_table_by_title("Syscall Methods Registry")

    registered = set()
    if table:
        # Extract method names from first column (Method)
        for row in table.rows:
            method_cell = row.cells[0] if row.cells else ""
            # Extract from backticks: `method()` -> method
            method_name = extract_backtick_value(method_cell)
            # Remove trailing parentheses if present
            method_name = method_name.rstrip("()")
            if method_name and not method_name.startswith("-"):
                registered.add(method_name)

    scanned_names = {s.method for s in syscalls}

    return {
        "missing_in_master": scanned_names - registered,
        "missing_in_code": registered - scanned_names,
        "scanned_count": len(syscalls),
        "registered_count": len(registered),
    }


if __name__ == "__main__":
    # Quick test
    syscalls = scan_syscalls()
    print(f"Found {len(syscalls)} syscall methods:\n")
    for s in syscalls:
        print(f"  {s.method} -> {s.capability} [{s.status}]")

    print("\n" + "=" * 60)
    print("Markdown Table:")
    print(generate_markdown_table(syscalls))
