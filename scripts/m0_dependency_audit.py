"""M0 E0.2 — Dependency Map Generator & Circular Dependency Checker.

Walks all .py files under poc/k1_poc/, extracts internal imports,
builds a folder-to-folder adjacency matrix, detects cycles, and
documents all k1.* framework imports.

Output: docs/plans/M0_DEPENDENCY_AUDIT.md
"""

import ast
import os
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(r"D:\familyos")
POC = ROOT / "poc" / "k1_poc"
SKIP = {"__pycache__", ".git", ".pytest_cache", "__pycache__"}


def get_imports(filepath: Path) -> list[str]:
    """Extract all import strings from a Python file."""
    try:
        source = filepath.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source, filename=str(filepath))
    except (SyntaxError, ValueError):
        return []

    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
    return imports


def folder_of(module: str, prefix: str = "poc.k1_poc.") -> str | None:
    """Extract the top-level folder from a poc.k1_poc.X.Y import."""
    if module.startswith(prefix):
        rest = module[len(prefix) :]
        return rest.split(".")[0] if rest else None
    return None


def k1_module(module: str) -> str | None:
    """Extract k1.* module path if this is a k1 framework import."""
    if module.startswith("k1."):
        return module
    return None


def detect_cycles(adj: dict[str, set[str]]) -> list[list[str]]:
    """Find all elementary cycles using DFS."""
    visited = set()
    in_stack = set()
    stack = []
    cycles = []

    def dfs(node):
        visited.add(node)
        in_stack.add(node)
        stack.append(node)
        for neighbor in sorted(adj.get(node, [])):
            if neighbor not in visited:
                dfs(neighbor)
            elif neighbor in in_stack:
                idx = stack.index(neighbor)
                cycle = stack[idx:] + [neighbor]
                cycles.append(cycle)
        stack.pop()
        in_stack.discard(node)

    for node in sorted(adj):
        if node not in visited:
            dfs(node)
    return cycles


def main():
    # Collect all .py files
    py_files = []
    for dirpath, dirnames, filenames in os.walk(POC):
        dirnames[:] = [d for d in dirnames if d not in SKIP]
        for fn in filenames:
            if fn.endswith(".py"):
                py_files.append(Path(dirpath) / fn)

    print(f"Scanning {len(py_files)} .py files under poc/k1_poc/...")

    # Build folder-to-folder matrix and k1 import list
    folder_adj: dict[str, set[str]] = defaultdict(set)
    k1_imports: dict[str, set[str]] = defaultdict(set)  # file -> set of k1.* modules
    all_folders = set()
    file_import_counts: dict[str, int] = defaultdict(int)

    for fp in sorted(py_files):
        rel = fp.relative_to(POC)
        parts = rel.parts
        src_folder = parts[0] if len(parts) > 1 else "(root)"
        all_folders.add(src_folder)

        imports = get_imports(fp)
        for imp in imports:
            # Internal poc.k1_poc imports
            dst = folder_of(imp)
            if dst and dst != src_folder:
                folder_adj[src_folder].add(dst)
                all_folders.add(dst)
                file_import_counts[src_folder] += 1

            # k1.* framework imports
            k1m = k1_module(imp)
            if k1m:
                rel_path = str(rel).replace("\\", "/")
                k1_imports[rel_path].add(k1m)

    # Detect cycles
    cycles = detect_cycles(folder_adj)

    # Generate report
    lines = []
    lines.append("# M0 E0.2 — Dependency Audit Report")
    lines.append("")
    lines.append(f"**Date**: 2026-03-30")
    lines.append(f"**Files scanned**: {len(py_files)}")
    lines.append(f"**Folders with imports**: {len(all_folders)}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Section 1: Folder-to-folder matrix
    lines.append("## 1. Folder-to-Folder Import Matrix")
    lines.append("")
    lines.append("| Source Folder | Imports From |")
    lines.append("|---|---|")
    for src in sorted(folder_adj):
        dsts = ", ".join(sorted(folder_adj[src]))
        lines.append(f"| `{src}` | {dsts} |")
    lines.append("")

    # Folders with no outgoing internal imports
    no_deps = all_folders - set(folder_adj.keys())
    if no_deps:
        lines.append(
            f"**Leaf folders** (no outgoing internal imports): {', '.join(f'`{f}`' for f in sorted(no_deps))}"
        )
        lines.append("")

    # Section 2: Circular dependencies
    lines.append("## 2. Circular Dependency Check")
    lines.append("")
    if not cycles:
        lines.append("✅ **ZERO circular dependencies found.** The import graph is a DAG.")
    else:
        lines.append(f"❌ **{len(cycles)} circular dependency chains found:**")
        lines.append("")
        for i, cycle in enumerate(cycles, 1):
            lines.append(f"{i}. `{'` → `'.join(cycle)}`")
    lines.append("")

    # Hub analysis
    lines.append("### Hub Analysis")
    lines.append("")
    lines.append("| Folder | Outgoing Imports | Incoming Imports |")
    lines.append("|---|---|---|")
    incoming: dict[str, int] = defaultdict(int)
    for src, dsts in folder_adj.items():
        for dst in dsts:
            incoming[dst] += 1
    for folder in sorted(all_folders):
        out = len(folder_adj.get(folder, []))
        inc = incoming.get(folder, 0)
        marker = " ⭐ HUB" if out > 10 else ""
        lines.append(f"| `{folder}` | {out} | {inc} |{marker}")
    lines.append("")

    # Section 3: k1.* framework imports
    lines.append("## 3. K1 Framework Imports (`k1.*`)")
    lines.append("")
    lines.append(
        "These imports reference `k1.*` packages (Bus, Fabric, etc.) that will NOT change path during the Big Copy (M5)."
    )
    lines.append("")

    # Deduplicate: collect unique k1 modules
    all_k1_modules = set()
    for mods in k1_imports.values():
        all_k1_modules.update(mods)

    lines.append(f"**Total unique k1.\\* modules imported**: {len(all_k1_modules)}")
    lines.append("")
    lines.append("### 3a. Unique k1.* Modules")
    lines.append("")
    for mod in sorted(all_k1_modules):
        lines.append(f"- `{mod}`")
    lines.append("")

    lines.append("### 3b. Files Importing k1.* (by folder)")
    lines.append("")
    lines.append("| File | k1.* Imports |")
    lines.append("|---|---|")
    for filepath in sorted(k1_imports):
        mods = ", ".join(f"`{m}`" for m in sorted(k1_imports[filepath]))
        lines.append(f"| `{filepath}` | {mods} |")
    lines.append("")

    # Section 4: Summary
    lines.append("## 4. Summary")
    lines.append("")
    lines.append(f"| Metric | Value |")
    lines.append(f"|---|---|")
    lines.append(f"| Python files scanned | {len(py_files)} |")
    lines.append(f"| Unique folders | {len(all_folders)} |")
    lines.append(f"| Folder-to-folder edges | {sum(len(v) for v in folder_adj.values())} |")
    lines.append(f"| Circular dependencies | {len(cycles)} |")
    lines.append(f"| Unique k1.* modules | {len(all_k1_modules)} |")
    lines.append(f"| Files importing k1.* | {len(k1_imports)} |")
    lines.append("")

    # Write output
    out_path = ROOT / "docs" / "plans" / "M0_DEPENDENCY_AUDIT.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"✅ Report written to {out_path}")
    print(
        f"   Folders: {len(all_folders)}, Edges: {sum(len(v) for v in folder_adj.values())}, Cycles: {len(cycles)}, k1 modules: {len(all_k1_modules)}"
    )


if __name__ == "__main__":
    main()
