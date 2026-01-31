#!/usr/bin/env python3
"""
Code Dependency Analyzer and Orphan File Detector (Python).

Improvements vs basic version:
- Correctly handles ast.ImportFrom with relative levels (node.level)
- Treats __init__.py as the package module (pkg, not pkg.__init__)
- For "from pkg import sub", attempts pkg.sub and pkg
- Orphans are computed by reachability from roots (entrypoints + optional --roots)
- Supports --exclude patterns and common default excludes
"""

from __future__ import annotations

import argparse
import ast
import fnmatch
import json
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

DEFAULT_EXCLUDES = [
    "**/.venv/**",
    "**/venv/**",
    "**/.tox/**",
    "**/site-packages/**",
    "**/__pycache__/**",
    "**/.mypy_cache/**",
    "**/.pytest_cache/**",
    "**/build/**",
    "**/dist/**",
    "**/.git/**",
]


@dataclass(frozen=True)
class ImportRef:
    kind: str  # "import" or "from"
    module: Optional[str]  # e.g. "pkg.sub" for "from pkg.sub import x", None for "from . import x"
    level: int  # 0 for absolute, >0 for relative (number of dots)
    names: Tuple[str, ...]  # imported names for from-import; empty for direct import


class DependencyAnalyzer:
    def __init__(
        self,
        root_dir: str,
        whole_repo_dir: Optional[str] = None,
        max_depth: int = 2,
        exclude_globs: Optional[List[str]] = None,
        roots: Optional[List[str]] = None,  # file paths or module names
        include_tests: bool = False,
        slice_package: Optional[str] = None,  # e.g., "k0.pipelines.p03"
    ):
        self.root_dir = Path(root_dir).resolve()
        self.whole_repo_dir = Path(whole_repo_dir).resolve() if whole_repo_dir else self.root_dir
        self.max_depth = max_depth
        self.exclude_globs = exclude_globs or DEFAULT_EXCLUDES
        self.user_roots = roots or []
        self.include_tests = include_tests
        self.slice_package = slice_package  # if set, focus on this package for tracing

        # module name -> file path
        self.module_to_file: Dict[str, Path] = {}
        # file path -> module name
        self.file_to_module: Dict[Path, str] = {}

        # file path string -> set[file path string]
        self.dependency_graph: Dict[str, Set[str]] = defaultdict(set)
        self.reverse_graph: Dict[str, Set[str]] = defaultdict(set)

        self.repo_py_files: Set[Path] = set()  # scanned for deps
        self.all_py_files: Set[Path] = set()  # analyzed for orphan candidates (root_dir only)

        # For slice mode
        self.slice_files: Set[Path] = set()
        self.references_into_slice: Set[str] = set()  # files outside slice that reference slice

    # ----------------------------
    # Filtering / scanning
    # ----------------------------
    def _is_excluded(self, p: Path) -> bool:
        rel = p.as_posix()
        for pat in self.exclude_globs:
            if fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(str(p), pat):
                return True
        return False

    def _iter_py_files(self, base: Path) -> Iterable[Path]:
        for p in base.rglob("*.py"):
            if not self._is_excluded(p):
                yield p

    # ----------------------------
    # Module mapping
    # ----------------------------
    def _module_name_for_path(self, py_file: Path, base: Path) -> str:
        rel = py_file.relative_to(base)
        parts = list(rel.parts)

        # drop ".py"
        filename = parts[-1]
        stem = filename[:-3]

        if stem == "__init__":
            # package module = directory path
            parts = parts[:-1]  # remove __init__.py
        else:
            parts[-1] = stem

        # Treat directories as package-like (works for normal + namespace packages)
        return ".".join(parts)

    def build_module_map(self) -> None:
        # Scan whole repo for module map
        for py_file in self._iter_py_files(self.whole_repo_dir):
            self.repo_py_files.add(py_file)
            mod = self._module_name_for_path(py_file, self.whole_repo_dir)
            self.module_to_file[mod] = py_file
            self.file_to_module[py_file] = mod

        # Only analyze files in root_dir for orphan candidates
        for py_file in self._iter_py_files(self.root_dir):
            if not self.include_tests and self._looks_like_test(py_file):
                continue
            self.all_py_files.add(py_file)

        # If slice mode, identify slice files
        if self.slice_package:
            slice_prefix = self.slice_package + "."
            for mod, path in self.module_to_file.items():
                if mod == self.slice_package or mod.startswith(slice_prefix):
                    self.slice_files.add(path)

    def _looks_like_test(self, p: Path) -> bool:
        s = p.as_posix()
        name = p.name
        return "/tests/" in s or name.startswith("test_") or name.endswith("_test.py")

    # ----------------------------
    # Import extraction
    # ----------------------------
    def extract_imports(self, file_path: Path) -> List[ImportRef]:
        try:
            content = file_path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError, IOError):
            return []

        try:
            tree = ast.parse(content, filename=str(file_path))
        except SyntaxError:
            return []

        out: List[ImportRef] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    out.append(ImportRef(kind="import", module=alias.name, level=0, names=()))
            elif isinstance(node, ast.ImportFrom):
                # node.module can be None for "from . import x"
                names = tuple(a.name for a in node.names)
                out.append(
                    ImportRef(kind="from", module=node.module, level=node.level or 0, names=names)
                )
        return out

    def extract_events(self, file_path: Path) -> List[str]:
        """Extract event-related patterns like bus.publish, outbox.publish, subscribe."""
        try:
            content = file_path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError, IOError):
            return []

        try:
            tree = ast.parse(content, filename=str(file_path))
        except SyntaxError:
            return []

        events = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                # Check for bus.publish, outbox.publish, etc.
                if isinstance(node.func, ast.Attribute):
                    method = node.func.attr
                    if method in ("publish", "subscribe", "emit"):
                        obj = node.func.value
                        if isinstance(obj, ast.Name) and obj.id in ("bus", "outbox"):
                            # Extract topic or event name if possible
                            topic = "unknown"
                            if node.args:
                                arg = node.args[0]
                                if isinstance(arg, ast.Constant):
                                    topic = arg.value
                                elif isinstance(arg, ast.Str):  # deprecated
                                    if hasattr(arg, "s"):
                                        topic = arg.s
                            events.append(f"{obj.id}.{method}({topic})")
                        elif isinstance(obj, ast.Attribute):
                            # Handle ctx.bus.publish, self._bus.publish, etc.
                            if isinstance(obj.value, ast.Name):
                                prefix = obj.value.id
                                attr = obj.attr
                                if attr in ("bus", "_bus") and prefix in ("self", "ctx"):
                                    topic = "unknown"
                                    if node.args:
                                        arg = node.args[0]
                                        if isinstance(arg, ast.Constant):
                                            topic = arg.value
                                        elif isinstance(arg, ast.Str):  # deprecated
                                            if hasattr(arg, "s"):
                                                topic = arg.s
                                    events.append(f"{prefix}.{attr}.{method}({topic})")
        return events

    def extract_storage(self, file_path: Path) -> List[str]:
        """Extract storage-related patterns like st_* tables or db calls."""
        try:
            content = file_path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError, IOError):
            return []

        try:
            tree = ast.parse(content, filename=str(file_path))
        except SyntaxError:
            return []

        storage = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Str):  # deprecated
                if hasattr(node, "s") and isinstance(node.s, str) and node.s.startswith("st_"):
                    storage.append(node.s)
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                if node.value.startswith("st_"):
                    storage.append(node.value)
            # Also check for db calls like db.query, storage.get, etc.
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    if isinstance(node.func.value, ast.Name):
                        obj = node.func.value.id
                        method = node.func.attr
                        if obj in ("db", "storage", "conn") and method in (
                            "query",
                            "get",
                            "put",
                            "delete",
                            "execute",
                        ):
                            storage.append(f"{obj}.{method}")
        return storage

    def extract_dynamic_imports(self, file_path: Path) -> List[str]:
        """Extract dynamic import patterns like importlib.import_module, __import__."""
        try:
            content = file_path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError, IOError):
            return []

        try:
            tree = ast.parse(content, filename=str(file_path))
        except SyntaxError:
            return []

        dynamic = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id in ("__import__", "importlib"):
                    # __import__('module')
                    if node.args:
                        arg = node.args[0]
                        if isinstance(arg, ast.Constant):
                            dynamic.append(f"__import__({arg.value})")
                        elif isinstance(arg, ast.Str):  # deprecated
                            if hasattr(arg, "s"):
                                dynamic.append(f"__import__({arg.s})")
                elif isinstance(node.func, ast.Attribute):
                    if isinstance(node.func.value, ast.Name) and node.func.value.id == "importlib":
                        if node.func.attr == "import_module":
                            if node.args:
                                arg = node.args[0]
                                if isinstance(arg, ast.Constant):
                                    dynamic.append(f"importlib.import_module({arg.value})")
                                elif isinstance(arg, ast.Str):  # deprecated
                                    if hasattr(arg, "s"):
                                        dynamic.append(f"importlib.import_module({arg.s})")
        return dynamic

    def extract_registered_modules(self, file_path: Path) -> List[str]:
        """Extract decorator-based registrations like @register_module."""
        try:
            content = file_path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError, IOError):
            return []

        try:
            tree = ast.parse(content, filename=str(file_path))
        except SyntaxError:
            return []

        registered = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.decorator_list:
                for decorator in node.decorator_list:
                    dec_name = None
                    if isinstance(decorator, ast.Name):
                        dec_name = decorator.id
                    elif isinstance(decorator, ast.Attribute):
                        dec_name = decorator.attr
                    elif isinstance(decorator, ast.Call):
                        if isinstance(decorator.func, ast.Name):
                            dec_name = decorator.func.id
                        elif isinstance(decorator.func, ast.Attribute):
                            dec_name = decorator.func.attr
                    if dec_name and (
                        "register" in dec_name.lower() or "module" in dec_name.lower()
                    ):
                        registered.append(f"@{dec_name} on {node.name}")
        return registered

    def extract_pkgutil_scans(self, file_path: Path) -> List[str]:
        """Extract pkgutil.iter_modules calls."""
        try:
            content = file_path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError, IOError):
            return []

        try:
            tree = ast.parse(content, filename=str(file_path))
        except SyntaxError:
            return []

        scans = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    if isinstance(node.func.value, ast.Name) and node.func.value.id == "pkgutil":
                        if node.func.attr == "iter_modules":
                            if node.args:
                                arg = node.args[0]
                                if isinstance(arg, ast.Constant):
                                    scans.append(f"pkgutil.iter_modules({arg.value})")
                                elif isinstance(arg, ast.Str):  # deprecated
                                    if hasattr(arg, "s"):
                                        scans.append(f"pkgutil.iter_modules({arg.s})")
        return scans

    # ----------------------------
    # Resolution helpers
    # ----------------------------
    def _resolve_module_to_file(self, mod: str) -> Optional[Path]:
        # Exact module
        if mod in self.module_to_file:
            return self.module_to_file[mod]

        # If someone imports a package name that maps to package __init__.py,
        # our module map already uses "pkg" for pkg/__init__.py, so exact match is enough.
        return None

    def _resolve_relative_base(self, current_file: Path, level: int) -> Optional[str]:
        """
        Return the base module path after applying relative "level".
        level=1 means current package, 2 means parent, etc.
        """
        cur_mod = self.file_to_module.get(current_file)
        if not cur_mod:
            return None

        # If current file is a module like "a.b.c", its package is "a.b" (drop last)
        pkg_parts = cur_mod.split(".")[:-1]
        if level <= 0:
            return ".".join(pkg_parts)

        if level > len(pkg_parts) + 1:
            return None

        # level=1 => stay in pkg_parts
        # level=2 => go up one
        up = level - 1
        base_parts = pkg_parts[:-up] if up else pkg_parts
        return ".".join(base_parts)

    def resolve_imports_to_files(self, imp: ImportRef, current_file: Path) -> Set[Path]:
        """
        Return *possible* files this import could refer to in-repo.
        (We intentionally over-approximate slightly for from-import.)
        """
        results: Set[Path] = set()

        if imp.kind == "import":
            if not imp.module:
                return results
            # import a.b  -> module a.b (or just a)
            # We try the full name first; that’s typically what you want for file edges.
            resolved = self._resolve_module_to_file(imp.module)
            if resolved:
                results.add(resolved)
            return results

        # imp.kind == "from"
        base_prefix: Optional[str]
        if imp.level > 0:
            base_prefix = self._resolve_relative_base(current_file, imp.level)
            if base_prefix is None:
                return results
        else:
            base_prefix = ""  # absolute

        if imp.module:
            # from X import Y  => X is a module/package (edge to X)
            full_mod = f"{base_prefix}.{imp.module}".strip(".")
            m = self._resolve_module_to_file(full_mod)
            if m:
                results.add(m)

            # and try X.Y for each imported name (often modules)
            for name in imp.names:
                candidate = f"{full_mod}.{name}".strip(".")
                c = self._resolve_module_to_file(candidate)
                if c:
                    results.add(c)
        else:
            # from . import x  => base_prefix + x
            for name in imp.names:
                candidate = f"{base_prefix}.{name}".strip(".")
                c = self._resolve_module_to_file(candidate)
                if c:
                    results.add(c)

        return results

    # ----------------------------
    # Graph building
    # ----------------------------
    def build_dependency_graph(self) -> None:
        for py_file in self.repo_py_files:
            imps = self.extract_imports(py_file)
            file_str = str(py_file)

            for imp in imps:
                for dep_file in self.resolve_imports_to_files(imp, py_file):
                    if dep_file in self.repo_py_files:
                        dep_str = str(dep_file)
                        self.dependency_graph[file_str].add(dep_str)
                        self.reverse_graph[dep_str].add(file_str)

        # Second pass: dynamic imports
        self._add_dynamic_imports()

        # If slice mode, find references into slice
        if self.slice_package:
            self._find_references_into_slice()

    def _add_dynamic_imports(self) -> None:
        """Scan for dynamic imports like importlib.import_module('mod') and add edges."""
        for py_file in self.repo_py_files:
            try:
                with open(py_file, "r", encoding="utf-8") as f:
                    content = f.read()
            except (UnicodeDecodeError, IOError, OSError):
                continue

            try:
                tree = ast.parse(content, filename=str(py_file))
            except SyntaxError:
                continue

            file_str = str(py_file)
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    func = node.func
                    if isinstance(func, ast.Name) and func.id in (
                        "__import__",
                        "importlib.import_module",
                    ):
                        # Extract string args
                        for arg in node.args:
                            mod_name: str
                            if isinstance(arg, ast.Str):
                                mod_name = arg.s  # type: ignore
                            elif isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                                mod_name = arg.value  # type: ignore
                            else:
                                continue
                            dep_file = self._resolve_module_to_file(mod_name)
                            if dep_file and dep_file in self.repo_py_files:
                                dep_str = str(dep_file)
                                self.dependency_graph[file_str].add(dep_str)
                                self.reverse_graph[dep_str].add(file_str)
                    elif (
                        isinstance(func, ast.Attribute)
                        and isinstance(func.value, ast.Name)
                        and func.value.id == "importlib"
                        and func.attr == "import_module"
                    ):
                        for arg in node.args:
                            if isinstance(arg, ast.Str):
                                mod_name = arg.s  # type: ignore
                            elif isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                                mod_name = arg.value  # type: ignore
                            else:
                                continue
                            dep_file = self._resolve_module_to_file(mod_name)
                            if dep_file and dep_file in self.repo_py_files:
                                dep_str = str(dep_file)
                                self.dependency_graph[file_str].add(dep_str)
                                self.reverse_graph[dep_str].add(file_str)

    def _find_references_into_slice(self) -> None:
        """Find files outside slice that reference slice modules."""
        slice_mods = {
            self.file_to_module.get(f) for f in self.slice_files if f in self.file_to_module
        }
        slice_mods.discard(None)
        slice_prefixes = [mod + "." for mod in slice_mods if mod]

        for py_file in self.repo_py_files:
            if py_file in self.slice_files:
                continue  # skip internal
            try:
                content = py_file.read_text(encoding="utf-8")
            except (UnicodeDecodeError, IOError, OSError):
                continue

            # Check for imports
            imps = self.extract_imports(py_file)
            for imp in imps:
                if imp.module and (
                    imp.module in slice_mods
                    or any(imp.module.startswith(p) for p in slice_prefixes)
                ):
                    self.references_into_slice.add(str(py_file))
                    break

            # Check for string literals (heuristic for dynamic imports)
            if self.slice_package and self.slice_package in content:
                self.references_into_slice.add(str(py_file))

    # ----------------------------
    # Roots + reachability
    # ----------------------------
    def _is_entry_point(self, file_path: Path) -> bool:
        try:
            txt = file_path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError, IOError):
            return False
        return 'if __name__ == "__main__"' in txt or file_path.name in {
            "__main__.py",
            "main.py",
            "app.py",
            "cli.py",
        }

    def _resolve_user_root(self, s: str) -> Optional[Path]:
        p = Path(s)
        if p.exists() and p.is_file():
            return p.resolve()

        # try as module name
        return self.module_to_file.get(s)

    def compute_reachable(self) -> Set[str]:
        roots: Set[Path] = set()

        # auto roots: entry points inside the repo
        for f in self.repo_py_files:
            if self._is_entry_point(f):
                roots.add(f)

        # user roots
        for r in self.user_roots:
            p = self._resolve_user_root(r)
            if p and p in self.repo_py_files:
                roots.add(p)

        # If no roots detected, fall back to "all files in root_dir" as starting points
        # (prevents returning everything as orphan in library-style repos)
        if not roots:
            roots = set(self.all_py_files)

        reachable: Set[str] = set()
        q = deque(str(p) for p in roots)

        while q:
            cur = q.popleft()
            if cur in reachable:
                continue
            reachable.add(cur)
            for nxt in self.dependency_graph.get(cur, ()):
                if nxt not in reachable:
                    q.append(nxt)

        return reachable

    def find_orphans(self) -> Tuple[List[str], List[str]]:
        reachable = self.compute_reachable()

        orphans: List[str] = []
        orphans_init: List[str] = []
        for py_file in self.all_py_files:
            s = str(py_file)
            if s not in reachable:
                if py_file.name == "__init__.py":
                    orphans_init.append(s)
                else:
                    orphans.append(s)

        return sorted(orphans), sorted(orphans_init)

    # ----------------------------
    # Trees / output
    # ----------------------------
    def get_dependency_tree(
        self, root_file: str, depth: int = 0, seen: Optional[Set[str]] = None
    ) -> Dict:
        if depth > self.max_depth:
            return {}

        if seen is None:
            seen = set()
        if root_file in seen:
            return {"<cycle>": {}}
        seen.add(root_file)

        tree: Dict[str, Dict] = {}
        for dep in sorted(self.dependency_graph.get(root_file, ())):
            tree[dep] = self.get_dependency_tree(dep, depth + 1, seen.copy())
        return tree

    def analyze(self) -> Dict:
        self.build_module_map()
        self.build_dependency_graph()
        orphans, orphans_init = self.find_orphans()

        trees = {}
        for py_file in sorted(self.all_py_files)[:10]:
            trees[str(py_file)] = self.get_dependency_tree(str(py_file))

        events = []
        storage = []
        if self.slice_package:
            for f in self.slice_files:
                events.extend(self.extract_events(f))
                storage.extend(self.extract_storage(f))

        dynamic_imports = []
        registered_modules = []
        pkgutil_scans = []
        if self.slice_package:
            for f in self.slice_files:
                dynamic_imports.extend(self.extract_dynamic_imports(f))
                registered_modules.extend(self.extract_registered_modules(f))
                pkgutil_scans.extend(self.extract_pkgutil_scans(f))

        return {
            "total_files": len(self.all_py_files),
            "repo_files": len(self.repo_py_files),
            "orphans": orphans,
            "orphans_init": orphans_init,
            "dependency_graph": {k: sorted(v) for k, v in self.dependency_graph.items()},
            "reverse_graph": {k: sorted(v) for k, v in self.reverse_graph.items()},
            "sample_trees": trees,
            "excludes": self.exclude_globs,
            "roots": self.user_roots,
            "slice_package": self.slice_package,
            "slice_files": sorted(str(f) for f in self.slice_files),
            "references_into_slice": sorted(self.references_into_slice),
            "events": sorted(set(events)),
            "storage": sorted(set(storage)),
            "dynamic_imports": sorted(set(dynamic_imports)),
            "registered_modules": sorted(set(registered_modules)),
            "pkgutil_scans": sorted(set(pkgutil_scans)),
        }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyze Python code dependencies and find orphan files."
    )
    parser.add_argument("root_dir", help="Directory whose files you want to check for orphans")
    parser.add_argument("--whole-repo", help="Repo root to scan for imports (default: root_dir)")
    parser.add_argument(
        "--depth", type=int, default=2, help="Maximum dependency tree depth (for sample trees)"
    )
    parser.add_argument("--output", default="./analysis_output", help="Output directory")
    parser.add_argument(
        "--exclude", action="append", default=[], help="Glob pattern to exclude (repeatable)"
    )
    parser.add_argument(
        "--root",
        action="append",
        default=[],
        help="Extra root file/module for reachability (repeatable)",
    )
    parser.add_argument(
        "--slice", help="Package/module to slice and trace (e.g., k0.pipelines.p03)"
    )
    parser.add_argument(
        "--include-tests", action="store_true", help="Include tests in orphan candidates"
    )
    args = parser.parse_args()

    whole_repo = args.whole_repo or args.root_dir
    excludes = DEFAULT_EXCLUDES + args.exclude

    analyzer = DependencyAnalyzer(
        root_dir=args.root_dir,
        whole_repo_dir=whole_repo,
        max_depth=args.depth,
        exclude_globs=excludes,
        roots=args.root,
        include_tests=args.include_tests,
        slice_package=args.slice,
    )

    results = analyzer.analyze()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    (output_dir / "dependencies.json").write_text(json.dumps(results, indent=2), encoding="utf-8")

    summary_lines = [
        f"Total files in root_dir analyzed: {results['total_files']}",
        f"Total files in whole repo scanned: {results['repo_files']}",
        "",
        f"Orphan files in root_dir (NOT reachable from detected/user roots): ({len(results['orphans'])})",
        *[f"  - {o}" for o in results["orphans"]],
        "",
        f"Orphan __init__.py files (package inits, often not statically imported): ({len(results['orphans_init'])})",
        *[f"  - {o}" for o in results["orphans_init"]],
        "",
    ]

    if results.get("slice_package"):
        summary_lines.extend(
            [
                f"Slice package: {results['slice_package']}",
                f"Files in slice: {len(results['slice_files'])}",
                f"References into slice (from outside): ({len(results['references_into_slice'])})",
                *[f"  - {r}" for r in results["references_into_slice"]],
                "",
            ]
        )

    if results.get("events"):
        summary_lines.extend(
            [
                f"Events touched by slice: ({len(results['events'])})",
                *[f"  - {e}" for e in results["events"]],
                "",
            ]
        )

    if results.get("storage"):
        summary_lines.extend(
            [
                f"Storage touched by slice: ({len(results['storage'])})",
                *[f"  - {s}" for s in results["storage"]],
                "",
            ]
        )

    if results.get("dynamic_imports"):
        summary_lines.extend(
            [
                f"Dynamic imports in slice: ({len(results['dynamic_imports'])})",
                *[f"  - {d}" for d in results["dynamic_imports"]],
                "",
            ]
        )

    if results.get("registered_modules"):
        summary_lines.extend(
            [
                f"Registered modules in slice: ({len(results['registered_modules'])})",
                *[f"  - {r}" for r in results["registered_modules"]],
                "",
            ]
        )

    if results.get("pkgutil_scans"):
        summary_lines.extend(
            [
                f"Pkgutil scans in slice: ({len(results['pkgutil_scans'])})",
                *[f"  - {p}" for p in results["pkgutil_scans"]],
                "",
            ]
        )

    summary_lines.extend(
        [
            "Sample dependency trees:",
        ]
    )
    for root, tree in results["sample_trees"].items():
        summary_lines.append(f"{root}:")
        summary_lines.append(json.dumps(tree, indent=2))
        summary_lines.append("")

    (output_dir / "summary.txt").write_text("\n".join(summary_lines), encoding="utf-8")
    print(f"Analysis complete. Results saved to {output_dir}")


if __name__ == "__main__":
    main()
