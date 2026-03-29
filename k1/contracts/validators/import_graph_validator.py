from __future__ import annotations

import ast
from typing import Any, Dict, List, Optional, Set

import yaml

from ..loaders.wiring_loader import WiringLoader


class ImportGraphValidator:
    """
    Validates import dependency graph for cycles, orphans, and structural issues.

    - Builds dependency graph from import contracts
    - Detects circular dependencies
    - Identifies orphaned modules (no imports, not imported)
    - Validates import contract integrity
    """

    def __init__(self, wiring_loader: Optional[WiringLoader] = None):
        self.wiring_loader = wiring_loader or WiringLoader()
        self._allowlist: Set[str] = set()
        self._load_allowlist()

    def _load_allowlist(self) -> None:
        """Load import allowlist."""
        allowlist_file = (
            self.wiring_loader.contract_loader.contracts_dir / "config" / "import_allowlist.yaml"
        )
        if allowlist_file.exists():
            try:
                with open(allowlist_file, "r") as f:
                    data = yaml.safe_load(f)
                self._allowlist = set(data.get("allowed_prefixes", []))
            except Exception:
                pass

    def validate_import_graph(self) -> Dict[str, List[str]]:
        """Validate the entire import graph."""
        errors: Dict[str, List[str]] = {}

        # Load all import contracts
        import_specs = self._load_all_import_specs()

        # Build dependency graph
        graph = self._build_dependency_graph(import_specs)

        # Detect cycles
        cycles = self._detect_cycles(graph)
        if cycles:
            errors["CYCLES"] = [f"Import cycles detected: {cycles}"]

        # Find orphans
        orphans = self._find_orphans(graph)
        if orphans:
            errors["ORPHANS"] = [f"Orphaned modules (no imports, not imported): {orphans}"]

        # Validate individual imports
        for module_id, spec in import_specs.items():
            module_errors = self._validate_import_spec(module_id, spec, graph)
            if module_errors:
                errors[module_id] = module_errors

        return errors

    def _load_all_import_specs(self) -> Dict[str, Dict[str, Any]]:
        """Load all import specs from wiring contracts."""
        specs: Dict[str, Dict[str, Any]] = {}

        self.wiring_loader.index_all_modules()

        for module_id, spec in self.wiring_loader._wiring_specs.items():
            specs[module_id] = spec.get("imports", {})

        return specs

    def _build_dependency_graph(
        self, import_specs: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Set[str]]:
        """Build directed graph: module -> set of imported modules."""
        graph: Dict[str, Set[str]] = {}

        for module_id, spec in import_specs.items():
            if "error" in spec:
                continue
            deps = set()
            for imp in spec.get("imports", []):
                deps.add(imp["module"])
            graph[module_id] = deps

        return graph

    def _detect_cycles(self, graph: Dict[str, Set[str]]) -> List[List[str]]:
        """Detect cycles in the dependency graph using DFS."""
        cycles: List[List[str]] = []
        visited: Set[str] = set()
        rec_stack: Set[str] = set()

        def dfs(node: str, path: List[str]):
            visited.add(node)
            rec_stack.add(node)
            path.append(node)

            for neighbor in graph.get(node, set()):
                if neighbor not in visited:
                    dfs(neighbor, path)
                elif neighbor in rec_stack:
                    # Cycle found
                    cycle_start = path.index(neighbor)
                    cycles.append(path[cycle_start:] + [neighbor])

            path.pop()
            rec_stack.remove(node)

        for node in graph:
            if node not in visited:
                dfs(node, [])

        return cycles

    def _find_orphans(self, graph: Dict[str, Set[str]]) -> List[str]:
        """Find orphan files: all files in code.roots not reachable from imports.roots."""
        orphans: List[str] = []

        for module_id in self.wiring_loader._wiring_specs:
            spec = self.wiring_loader._wiring_specs[module_id]
            all_files = self._get_module_files(module_id)
            roots = set(spec.get("imports", {}).get("roots", []))
            reachable = self._get_reachable_files(roots, all_files)
            orphan_files = all_files - reachable
            if orphan_files:
                orphans.extend(sorted(orphan_files))

        return orphans

    def _get_reachable_files(self, roots: Set[str], all_files: Set[str]) -> Set[str]:
        """DFS to find reachable files from roots within all_files."""
        visited: Set[str] = set()
        stack = list(roots)

        while stack:
            current = stack.pop()
            if current in visited or current not in all_files:
                continue
            visited.add(current)
            imports = self._parse_imports_from_file(current)
            # For simplicity, assume imports are file paths or module names, but to resolve to files, need more logic
            # For now, just add if in all_files
            for imp in imports:
                if imp in all_files:
                    stack.append(imp)

        return visited

    def _validate_import_spec(
        self, module_id: str, spec: Dict[str, Any], graph: Dict[str, Set[str]]
    ) -> List[str]:
        """Validate a single import contract."""
        errors: List[str] = []

        if "error" in spec:
            errors.append(f"Failed to load import spec: {spec['error']}")
            return errors

        # Check for self-imports
        for imp in spec.get("imports", []):
            if imp["module"] == module_id:
                errors.append(f"Self-import detected: {module_id} imports itself")

        # Check for duplicate imports
        imported = [imp["module"] for imp in spec.get("imports", [])]
        if len(imported) != len(set(imported)):
            duplicates = [x for x in imported if imported.count(x) > 1]
            errors.append(f"Duplicate imports: {set(duplicates)}")

        # Check if imported modules exist (have contracts)
        for imp in spec.get("imports", []):
            imported_module = imp["module"]
            if imported_module not in graph:
                errors.append(f"Imported module '{imported_module}' does not exist")
            else:
                # Check for escape imports
                if not self._is_allowed_import(imported_module):
                    errors.append(f"Escape import: '{imported_module}' is not in allowed prefixes")

        return errors

    def _is_allowed_import(self, module_id: str) -> bool:
        """Check if importing this module is allowed (not escape)."""
        if module_id in self.wiring_loader._wiring_specs:
            spec = self.wiring_loader._wiring_specs[module_id]
            code = spec.get("code", {})
            roots = code.get("roots", [])
            for root in roots:
                for allowed in self._allowlist:
                    if root.startswith(allowed):
                        return True
        return False

    def _get_module_files(self, module_id: str) -> Set[str]:
        """Get all Python files in the module's code.roots."""
        files: Set[str] = set()
        spec = self.wiring_loader._wiring_specs.get(module_id, {})
        code = spec.get("code", {})
        roots = code.get("roots", [])
        base_path = self.wiring_loader.contract_loader.contracts_dir.parent.parent  # d:\familyos

        for root in roots:
            root_path = base_path / root
            if root_path.exists() and root_path.is_dir():
                for py_file in root_path.rglob("*.py"):
                    files.add(str(py_file.relative_to(base_path)))

        return files

    def _parse_imports_from_file(self, file_path: str) -> Set[str]:
        """Parse import statements from a Python file."""
        imports: Set[str] = set()
        base_path = self.wiring_loader.contract_loader.contracts_dir.parent.parent
        full_path = base_path / file_path
        if not full_path.exists():
            return imports

        try:
            with open(full_path, "r", encoding="utf-8") as f:
                tree = ast.parse(f.read(), filename=str(full_path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.add(alias.name.split(".")[0])
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imports.add(node.module.split(".")[0])
        except Exception:
            pass

        return imports

    def get_graph_report(self) -> Dict[str, Any]:
        """Generate a report on the import graph."""
        import_specs = self._load_all_import_specs()
        graph = self._build_dependency_graph(import_specs)

        total_files = 0
        for module_id in self.wiring_loader._wiring_specs:
            total_files += len(self._get_module_files(module_id))

        report = {
            "total_modules": len(graph),
            "total_files": total_files,
            "total_imports": sum(len(deps) for deps in graph.values()),
            "cycles_detected": len(self._detect_cycles(graph)),
            "orphans": self._find_orphans(graph),
            "graph_density": sum(len(deps) for deps in graph.values()) / max(1, len(graph)),
        }

        return report
