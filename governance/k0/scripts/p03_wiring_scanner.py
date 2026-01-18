"""
P03 Wiring Scanner - Detect orphan files and build import dependency graph.

Scans Python files in P03 pipeline and consolidation modules to:
- Build import graph from AST analysis
- Detect orphan files (created but never imported)
- Generate phase-wise dependency mapping
- Produce wiring coverage report

Part of P03 Wiring Governance Plan (Epic 1.1).

Usage:
    python -m governance.k0.scripts.p03_wiring_scanner --report
    python -m governance.k0.scripts.p03_wiring_scanner --orphans
    python -m governance.k0.scripts.p03_wiring_scanner --graph
    python -m governance.k0.scripts.p03_wiring_scanner --phase r0
"""

from __future__ import annotations

import argparse
import ast
import sys
from dataclasses import dataclass, field
from pathlib import Path

# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class FileInfo:
    """Information about a Python file."""

    path: Path
    relative_path: str
    module_path: str  # e.g., k0.pipelines.p03.phases.r0_batch_selector
    category: str  # phases, ops, qos, algorithms, etc.
    line_count: int = 0
    imports: list[str] = field(default_factory=list)
    imported_by: list[str] = field(default_factory=list)


@dataclass
class ImportInfo:
    """Information about an import statement."""

    source_file: str  # File containing the import
    target_module: str  # Module being imported
    import_type: str  # 'from' or 'import'
    names: list[str] = field(default_factory=list)  # Specific names imported


@dataclass
class FolderStats:
    """Statistics for a folder/category."""

    folder: str
    total: int
    wired: int
    orphans: int

    @property
    def coverage(self) -> float:
        if self.total == 0:
            return 100.0
        return (self.wired / self.total) * 100


@dataclass
class PhaseDependency:
    """Dependency information for a pipeline phase."""

    phase_id: str  # r0, r1, etc.
    phase_file: str
    algorithm_imports: list[str] = field(default_factory=list)
    pipeline_imports: list[str] = field(default_factory=list)
    external_imports: list[str] = field(default_factory=list)


@dataclass
class WiringReport:
    """Complete wiring analysis report."""

    total_pipeline_files: int
    total_algorithm_files: int
    wired_pipeline_files: int
    wired_algorithm_files: int
    orphan_pipeline_files: list[str] = field(default_factory=list)
    orphan_algorithm_files: list[str] = field(default_factory=list)
    phase_dependencies: dict[str, PhaseDependency] = field(default_factory=dict)
    import_graph: dict[str, list[str]] = field(default_factory=dict)

    @property
    def total_files(self) -> int:
        return self.total_pipeline_files + self.total_algorithm_files

    @property
    def wired_files(self) -> int:
        return self.wired_pipeline_files + self.wired_algorithm_files

    @property
    def orphan_files(self) -> list[str]:
        return self.orphan_pipeline_files + self.orphan_algorithm_files

    @property
    def coverage_percent(self) -> float:
        if self.total_files == 0:
            return 0.0
        return (self.wired_files / self.total_files) * 100


# =============================================================================
# Path Utilities
# =============================================================================


def _get_repo_root() -> Path:
    """Get repository root from script location."""
    return Path(__file__).parent.parent.parent.parent


def _get_p03_pipeline_dir() -> Path:
    """Get P03 pipeline directory."""
    return _get_repo_root() / "k0" / "pipelines" / "p03"


def _get_consolidation_dir() -> Path:
    """Get consolidation algorithms directory."""
    return _get_repo_root() / "k0" / "modules" / "consolidation"


def _path_to_module(path: Path, repo_root: Path) -> str:
    """Convert file path to Python module path."""
    try:
        relative = path.relative_to(repo_root)
        # Remove .py extension and convert to module path
        module_path = str(relative.with_suffix("")).replace("\\", ".").replace("/", ".")
        return module_path
    except ValueError:
        return str(path)


def _categorize_file(path: Path, base_dir: Path) -> str:
    """Categorize a file based on its directory."""
    try:
        relative = path.relative_to(base_dir)
        parts = relative.parts
        if len(parts) == 1:
            return "root"
        return parts[0]
    except ValueError:
        return "unknown"


# =============================================================================
# File Scanning (#102, #103)
# =============================================================================


def scan_p03_pipeline_files() -> list[FileInfo]:
    """
    Scan all Python files in k0/pipelines/p03/.

    Returns list of FileInfo for each .py file (excluding __pycache__).
    """
    pipeline_dir = _get_p03_pipeline_dir()
    repo_root = _get_repo_root()

    if not pipeline_dir.exists():
        return []

    files: list[FileInfo] = []

    for py_file in pipeline_dir.rglob("*.py"):
        # Skip __pycache__ and __init__.py
        if "__pycache__" in str(py_file):
            continue
        if py_file.name == "__init__.py":
            continue

        try:
            content = py_file.read_text(encoding="utf-8")
            line_count = len(content.splitlines())
        except Exception:
            line_count = 0

        relative_path = str(py_file.relative_to(pipeline_dir))
        module_path = _path_to_module(py_file, repo_root)
        category = _categorize_file(py_file, pipeline_dir)

        files.append(
            FileInfo(
                path=py_file,
                relative_path=relative_path,
                module_path=module_path,
                category=category,
                line_count=line_count,
            )
        )

    return files


def scan_consolidation_algorithm_files() -> list[FileInfo]:
    """
    Scan all Python files in k0/modules/consolidation/.

    Returns list of FileInfo for each .py file (excluding __pycache__).
    """
    consolidation_dir = _get_consolidation_dir()
    repo_root = _get_repo_root()

    if not consolidation_dir.exists():
        return []

    files: list[FileInfo] = []

    for py_file in consolidation_dir.rglob("*.py"):
        # Skip __pycache__ and __init__.py
        if "__pycache__" in str(py_file):
            continue
        if py_file.name == "__init__.py":
            continue

        try:
            content = py_file.read_text(encoding="utf-8")
            line_count = len(content.splitlines())
        except Exception:
            line_count = 0

        relative_path = str(py_file.relative_to(consolidation_dir))
        module_path = _path_to_module(py_file, repo_root)
        category = _categorize_file(py_file, consolidation_dir)

        files.append(
            FileInfo(
                path=py_file,
                relative_path=relative_path,
                module_path=module_path,
                category=category,
                line_count=line_count,
            )
        )

    return files


# =============================================================================
# AST Import Parser (#104)
# =============================================================================


def parse_imports_from_file(file_path: Path) -> list[ImportInfo]:
    """
    Parse import statements from a Python file using AST.

    Returns list of ImportInfo for each import/from statement.
    Only captures k0.* imports (internal imports).
    """
    try:
        content = file_path.read_text(encoding="utf-8")
        tree = ast.parse(content, filename=str(file_path))
    except (SyntaxError, UnicodeDecodeError) as e:
        print(f"Warning: Failed to parse {file_path}: {e}")
        return []

    imports: list[ImportInfo] = []
    source_module = _path_to_module(file_path, _get_repo_root())

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                # Only track k0.* imports
                if alias.name.startswith("k0."):
                    imports.append(
                        ImportInfo(
                            source_file=source_module,
                            target_module=alias.name,
                            import_type="import",
                            names=[alias.asname or alias.name.split(".")[-1]],
                        )
                    )

        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""

            # Handle relative imports (from .foo import bar)
            if node.level > 0:
                # Get parent package from source module
                parts = source_module.split(".")
                # Go up 'level' directories
                parent_parts = parts[: -node.level] if node.level <= len(parts) else []
                if module:
                    resolved_module = ".".join(parent_parts + [module])
                else:
                    resolved_module = ".".join(parent_parts)

                if resolved_module.startswith("k0."):
                    names = [alias.name for alias in node.names]
                    imports.append(
                        ImportInfo(
                            source_file=source_module,
                            target_module=resolved_module,
                            import_type="from",
                            names=names,
                        )
                    )

            # Handle absolute imports (from k0.foo import bar)
            elif module.startswith("k0."):
                names = [alias.name for alias in node.names]
                imports.append(
                    ImportInfo(
                        source_file=source_module,
                        target_module=module,
                        import_type="from",
                        names=names,
                    )
                )

    return imports


def parse_all_imports(files: list[FileInfo]) -> dict[str, list[ImportInfo]]:
    """
    Parse imports from all files.

    Returns dict mapping file module path to list of its imports.
    """
    result: dict[str, list[ImportInfo]] = {}

    for file_info in files:
        imports = parse_imports_from_file(file_info.path)
        result[file_info.module_path] = imports
        file_info.imports = [imp.target_module for imp in imports]

    return result


# =============================================================================
# Import Graph Builder (#105)
# =============================================================================


def build_import_graph(
    pipeline_files: list[FileInfo],
    algorithm_files: list[FileInfo],
) -> dict[str, list[str]]:
    """
    Build import graph from all files.

    Returns dict mapping each file's module path to list of modules it imports.
    Also updates imported_by field on each FileInfo.
    """
    all_files = pipeline_files + algorithm_files

    # Build module path -> FileInfo lookup
    module_to_file: dict[str, FileInfo] = {}
    for f in all_files:
        module_to_file[f.module_path] = f

    # Parse all imports
    all_imports = parse_all_imports(all_files)

    # Build graph and update imported_by
    graph: dict[str, list[str]] = {}

    for source_module, imports in all_imports.items():
        graph[source_module] = []

        for imp in imports:
            target_module = imp.target_module
            graph[source_module].append(target_module)

            # Find the target file and update its imported_by
            # Try exact match first
            if target_module in module_to_file:
                module_to_file[target_module].imported_by.append(source_module)
            else:
                # Try prefix match (import k0.modules.consolidation.algorithms.decay_engine
                # might import k0.modules.consolidation.algorithms.decay_engine.DecayEngine)
                for mod_path, file_info in module_to_file.items():
                    if mod_path.startswith(target_module) or target_module.startswith(mod_path):
                        file_info.imported_by.append(source_module)
                        break

    return graph


# =============================================================================
# Extended Import Scanners (for __init__.py and tests)
# =============================================================================


def scan_init_files() -> dict[str, list[str]]:
    """
    Scan __init__.py files for re-exports.

    Returns dict mapping module path to list of imported modules.
    """
    init_imports: dict[str, list[str]] = {}

    # Scan consolidation __init__.py files
    consolidation_dir = _get_consolidation_dir()
    for init_file in consolidation_dir.rglob("__init__.py"):
        if "__pycache__" in str(init_file):
            continue
        imports = parse_imports_from_file(init_file)
        for imp in imports:
            if imp.target_module.startswith("k0."):
                module_key = imp.target_module
                if module_key not in init_imports:
                    init_imports[module_key] = []
                init_imports[module_key].append(f"__init__:{init_file.parent.name}")

    # Scan p03 __init__.py files
    pipeline_dir = _get_p03_pipeline_dir()
    for init_file in pipeline_dir.rglob("__init__.py"):
        if "__pycache__" in str(init_file):
            continue
        imports = parse_imports_from_file(init_file)
        for imp in imports:
            if imp.target_module.startswith("k0."):
                module_key = imp.target_module
                if module_key not in init_imports:
                    init_imports[module_key] = []
                init_imports[module_key].append(f"__init__:{init_file.parent.name}")

    return init_imports


def scan_test_files() -> dict[str, list[str]]:
    """
    Scan test files for imports of P03 and consolidation modules.

    Returns dict mapping module path to list of test files importing it.
    """
    repo_root = _get_repo_root()
    test_imports: dict[str, list[str]] = {}

    # Scan test files
    test_dir = repo_root / "tests" / "k0" / "pipelines" / "p03"
    if not test_dir.exists():
        return test_imports

    for test_file in test_dir.rglob("test_*.py"):
        if "__pycache__" in str(test_file):
            continue
        imports = parse_imports_from_file(test_file)
        for imp in imports:
            if imp.target_module.startswith("k0."):
                module_key = imp.target_module
                if module_key not in test_imports:
                    test_imports[module_key] = []
                test_imports[module_key].append(f"test:{test_file.stem}")

    # Also scan consolidation tests
    consol_test_dir = repo_root / "tests" / "k0" / "modules" / "consolidation"
    if consol_test_dir.exists():
        for test_file in consol_test_dir.rglob("test_*.py"):
            if "__pycache__" in str(test_file):
                continue
            imports = parse_imports_from_file(test_file)
            for imp in imports:
                if imp.target_module.startswith("k0."):
                    module_key = imp.target_module
                    if module_key not in test_imports:
                        test_imports[module_key] = []
                    test_imports[module_key].append(f"test:{test_file.stem}")

    return test_imports


def scan_contract_modules() -> dict[str, list[str]]:
    """
    Scan pipeline contract YAML files for module references.

    Returns dict mapping module path to list of contract files referencing it.
    """
    import re

    repo_root = _get_repo_root()
    contract_modules: dict[str, list[str]] = {}

    # Scan pipeline contracts
    contracts_dir = repo_root / "k0" / "contracts" / "pipelines"
    if not contracts_dir.exists():
        return contract_modules

    for yaml_file in contracts_dir.glob("*.yaml"):
        try:
            content = yaml_file.read_text(encoding="utf-8")
            # Look for module: consolidation.xxx patterns
            module_refs = re.findall(r"module:\s*(consolidation\.[a-z_]+)", content)
            for mod_ref in module_refs:
                # Convert contract module ref to Python module path
                module_path = f"k0.modules.{mod_ref.split(':')[0]}"
                if module_path not in contract_modules:
                    contract_modules[module_path] = []
                contract_modules[module_path].append(f"contract:{yaml_file.stem}")
        except Exception:
            continue

    return contract_modules


def check_extended_imports(
    module_path: str,
    init_imports: dict[str, list[str]],
    test_imports: dict[str, list[str]],
    contract_imports: dict[str, list[str]] | None = None,
) -> list[str]:
    """
    Check if a module is imported via __init__.py, tests, or contracts.

    Returns list of import sources (e.g., ['__init__:algorithms', 'test:test_decay', 'contract:p03'])
    """
    sources: list[str] = []
    if contract_imports is None:
        contract_imports = {}

    # Check exact match
    if module_path in init_imports:
        sources.extend(init_imports[module_path])
    if module_path in test_imports:
        sources.extend(test_imports[module_path])
    if module_path in contract_imports:
        sources.extend(contract_imports[module_path])

    # Check prefix match (import k0.modules.consolidation.algorithms imports algorithms/*)
    for imp_path, imp_sources in init_imports.items():
        if module_path.startswith(imp_path + ".") or imp_path.startswith(module_path + "."):
            sources.extend(imp_sources)

    for imp_path, imp_sources in test_imports.items():
        if module_path.startswith(imp_path + ".") or imp_path.startswith(module_path + "."):
            sources.extend(imp_sources)

    for imp_path, imp_sources in contract_imports.items():
        if module_path.startswith(imp_path + ".") or imp_path.startswith(module_path + "."):
            sources.extend(imp_sources)

    return list(set(sources))


# =============================================================================
# Orphan Detection (#106)
# =============================================================================


def find_orphan_files(
    pipeline_files: list[FileInfo],
    algorithm_files: list[FileInfo],
    include_extended: bool = True,
) -> tuple[list[str], list[str]]:
    """
    Find files that are never imported by production code.

    Args:
        pipeline_files: List of pipeline FileInfo
        algorithm_files: List of algorithm FileInfo
        include_extended: If True, also check __init__.py and contract imports
                          (NOT test imports - tests don't count as wiring)

    Returns tuple of (orphan_pipeline_files, orphan_algorithm_files).
    """
    orphan_pipeline: list[str] = []
    orphan_algorithm: list[str] = []

    # Get extended imports if requested
    # NOTE: We intentionally EXCLUDE test imports - they don't prove production wiring
    init_imports: dict[str, list[str]] = {}
    contract_imports: dict[str, list[str]] = {}
    if include_extended:
        init_imports = scan_init_files()
        contract_imports = scan_contract_modules()

    # Pipeline files that don't import anything from consolidation are potential orphans
    # But phases are entry points, so we check differently
    for f in pipeline_files:
        # Phases (r0-r8) are entry points, not orphans
        if f.category == "phases":
            continue

        # Root pipeline files are also entry points
        if f.category == "root":
            continue

        # Check direct imports
        if f.imported_by:
            continue

        # Check extended imports (init + contracts only, NOT tests)
        if include_extended:
            extended = check_extended_imports(f.module_path, init_imports, {}, contract_imports)
            if extended:
                f.imported_by.extend(extended)
                continue

        orphan_pipeline.append(f.relative_path)

    # Algorithm files should be imported by pipeline phases or other algorithms
    for f in algorithm_files:
        # Check direct imports
        if f.imported_by:
            continue

        # Check extended imports (init + contracts only, NOT tests)
        if include_extended:
            extended = check_extended_imports(f.module_path, init_imports, {}, contract_imports)
            if extended:
                f.imported_by.extend(extended)
                continue

        orphan_algorithm.append(f.relative_path)

    return orphan_pipeline, orphan_algorithm


def find_phase_not_importing(pipeline_files: list[FileInfo]) -> list[str]:
    """
    Find phase files (r0-r8) that don't import any consolidation algorithms.

    These phases might be broken or incomplete.
    """
    phases_not_importing: list[str] = []

    for f in pipeline_files:
        if f.category != "phases":
            continue

        # Check if phase imports anything from consolidation
        has_consolidation_import = any("consolidation" in imp for imp in f.imports)

        if not has_consolidation_import:
            phases_not_importing.append(f.relative_path)

    return phases_not_importing


# =============================================================================
# Phase Dependency Mapping
# =============================================================================


def build_phase_dependencies(
    pipeline_files: list[FileInfo],
) -> dict[str, PhaseDependency]:
    """
    Build phase-to-algorithm dependency mapping.

    Returns dict mapping phase ID (r0, r1, etc.) to PhaseDependency.
    """
    phases: dict[str, PhaseDependency] = {}

    for f in pipeline_files:
        if f.category != "phases":
            continue

        # Extract phase ID from filename (r0_batch_selector.py -> r0)
        phase_id = f.path.stem.split("_")[0]

        algorithm_imports: list[str] = []
        pipeline_imports: list[str] = []
        external_imports: list[str] = []

        for imp in f.imports:
            if "k0.modules.consolidation" in imp:
                algorithm_imports.append(imp)
            elif "k0.pipelines.p03" in imp:
                pipeline_imports.append(imp)
            elif imp.startswith("k0."):
                external_imports.append(imp)

        phases[phase_id] = PhaseDependency(
            phase_id=phase_id,
            phase_file=f.relative_path,
            algorithm_imports=algorithm_imports,
            pipeline_imports=pipeline_imports,
            external_imports=external_imports,
        )

    return phases


# =============================================================================
# Report Generation
# =============================================================================


def generate_wiring_report() -> WiringReport:
    """
    Generate complete wiring analysis report.

    Scans all files, builds import graph, detects orphans.
    """
    # Scan files
    pipeline_files = scan_p03_pipeline_files()
    algorithm_files = scan_consolidation_algorithm_files()

    # Build import graph (also updates imported_by on each FileInfo)
    import_graph = build_import_graph(pipeline_files, algorithm_files)

    # Find orphans
    orphan_pipeline, orphan_algorithm = find_orphan_files(pipeline_files, algorithm_files)

    # Build phase dependencies
    phase_deps = build_phase_dependencies(pipeline_files)

    # Calculate wired counts
    wired_pipeline = len(
        [f for f in pipeline_files if f.imported_by or f.category in ("phases", "root")]
    )
    wired_algorithm = len([f for f in algorithm_files if f.imported_by])

    return WiringReport(
        total_pipeline_files=len(pipeline_files),
        total_algorithm_files=len(algorithm_files),
        wired_pipeline_files=wired_pipeline,
        wired_algorithm_files=wired_algorithm,
        orphan_pipeline_files=orphan_pipeline,
        orphan_algorithm_files=orphan_algorithm,
        phase_dependencies=phase_deps,
        import_graph=import_graph,
    )


def generate_folder_breakdown(
    pipeline_files: list[FileInfo] | None = None,
    algorithm_files: list[FileInfo] | None = None,
) -> tuple[list[FolderStats], list[FolderStats]]:
    """
    Generate per-folder breakdown of wiring stats.

    Returns (pipeline_stats, algorithm_stats) where each is a list of FolderStats.
    """
    if pipeline_files is None:
        pipeline_files = scan_p03_pipeline_files()
    if algorithm_files is None:
        algorithm_files = scan_consolidation_algorithm_files()

    # Build import graph to populate imported_by
    build_import_graph(pipeline_files, algorithm_files)

    # Get orphans
    orphan_pipeline, orphan_algorithm = find_orphan_files(
        pipeline_files, algorithm_files, include_extended=True
    )
    orphan_set = set(orphan_pipeline + orphan_algorithm)

    # Group pipeline files by category
    pipeline_by_cat: dict[str, list[FileInfo]] = {}
    for f in pipeline_files:
        cat = f.category or "root"
        if cat not in pipeline_by_cat:
            pipeline_by_cat[cat] = []
        pipeline_by_cat[cat].append(f)

    # Group algorithm files by category
    algo_by_cat: dict[str, list[FileInfo]] = {}
    for f in algorithm_files:
        cat = f.category or "root"
        if cat not in algo_by_cat:
            algo_by_cat[cat] = []
        algo_by_cat[cat].append(f)

    # Build pipeline stats
    pipeline_stats: list[FolderStats] = []
    for cat in sorted(pipeline_by_cat.keys()):
        files = pipeline_by_cat[cat]
        total = len(files)
        orphans = len([f for f in files if f.relative_path in orphan_set])
        wired = total - orphans
        pipeline_stats.append(FolderStats(folder=cat, total=total, wired=wired, orphans=orphans))

    # Build algorithm stats
    algo_stats: list[FolderStats] = []
    for cat in sorted(algo_by_cat.keys()):
        files = algo_by_cat[cat]
        total = len(files)
        orphans = len([f for f in files if f.relative_path in orphan_set])
        wired = total - orphans
        algo_stats.append(FolderStats(folder=cat, total=total, wired=wired, orphans=orphans))

    return pipeline_stats, algo_stats


# =============================================================================
# Output Formatters
# =============================================================================


def print_summary_report(report: WiringReport) -> None:
    """Print summary report to stdout."""
    print("=" * 60)
    print("P03 WIRING REPORT")
    print("=" * 60)
    print()
    print("SUMMARY")
    print("-" * 40)
    print(f"Pipeline Files:     {report.total_pipeline_files:>5}")
    print(f"Algorithm Files:    {report.total_algorithm_files:>5}")
    print(f"Total Files:        {report.total_files:>5}")
    print()
    print(f"Wired (Pipeline):   {report.wired_pipeline_files:>5}")
    print(f"Wired (Algorithm):  {report.wired_algorithm_files:>5}")
    print(f"Total Wired:        {report.wired_files:>5}")
    print()
    print(f"Orphan (Pipeline):  {len(report.orphan_pipeline_files):>5}")
    print(f"Orphan (Algorithm): {len(report.orphan_algorithm_files):>5}")
    print(f"Total Orphans:      {len(report.orphan_files):>5}")
    print()
    print(f"Coverage:           {report.coverage_percent:>5.1f}%")
    print()

    if report.orphan_files:
        print("ORPHAN FILES (not imported anywhere)")
        print("-" * 40)
        for f in sorted(report.orphan_files):
            print(f"  - {f}")
        print()

    print("PHASE DEPENDENCIES")
    print("-" * 40)
    for phase_id in sorted(report.phase_dependencies.keys()):
        dep = report.phase_dependencies[phase_id]
        print(f"\n{phase_id.upper()}: {dep.phase_file}")
        if dep.algorithm_imports:
            print(f"  Algorithms ({len(dep.algorithm_imports)}):")
            for imp in sorted(dep.algorithm_imports)[:5]:  # Show first 5
                short = imp.replace("k0.modules.consolidation.", "")
                print(f"    - {short}")
            if len(dep.algorithm_imports) > 5:
                print(f"    ... and {len(dep.algorithm_imports) - 5} more")


def print_orphans_only(report: WiringReport) -> None:
    """Print only orphan files."""
    if not report.orphan_files:
        print("No orphan files detected.")
        return

    print(f"Found {len(report.orphan_files)} orphan files:\n")

    if report.orphan_pipeline_files:
        print("Pipeline Orphans:")
        for f in sorted(report.orphan_pipeline_files):
            print(f"  - k0/pipelines/p03/{f}")

    if report.orphan_algorithm_files:
        print("\nAlgorithm Orphans:")
        for f in sorted(report.orphan_algorithm_files):
            print(f"  - k0/modules/consolidation/{f}")


def print_phase_graph(report: WiringReport, phase_id: str | None = None) -> None:
    """Print phase dependency graph."""
    phases = report.phase_dependencies

    if phase_id:
        if phase_id not in phases:
            print(f"Phase '{phase_id}' not found. Available: {', '.join(sorted(phases.keys()))}")
            return
        phases = {phase_id: phases[phase_id]}

    for pid in sorted(phases.keys()):
        dep = phases[pid]
        print(f"\n{'='*60}")
        print(f"PHASE: {pid.upper()}")
        print(f"File: {dep.phase_file}")
        print(f"{'='*60}")

        print("\nAlgorithm Imports:")
        if dep.algorithm_imports:
            for imp in sorted(dep.algorithm_imports):
                short = imp.replace("k0.modules.consolidation.", "")
                print(f"  from {short}")
        else:
            print("  (none)")

        print("\nPipeline Imports:")
        if dep.pipeline_imports:
            for imp in sorted(dep.pipeline_imports):
                short = imp.replace("k0.pipelines.p03.", "")
                print(f"  from {short}")
        else:
            print("  (none)")


def generate_markdown_report(report: WiringReport) -> str:
    """Generate markdown report."""
    lines = [
        "# P03 Dependency Graph",
        "",
        "> Auto-generated by `p03_wiring_scanner.py`",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Pipeline Files | {report.total_pipeline_files} |",
        f"| Algorithm Files | {report.total_algorithm_files} |",
        f"| Wired (Pipeline) | {report.wired_pipeline_files} |",
        f"| Wired (Algorithm) | {report.wired_algorithm_files} |",
        f"| Orphan Files | {len(report.orphan_files)} |",
        f"| Coverage | {report.coverage_percent:.1f}% |",
        "",
    ]

    # Phase dependencies
    lines.append("## Phase Dependencies")
    lines.append("")

    for phase_id in sorted(report.phase_dependencies.keys()):
        dep = report.phase_dependencies[phase_id]
        lines.append(f"### {phase_id.upper()}: {dep.phase_file}")
        lines.append("")

        if dep.algorithm_imports:
            lines.append("| Import | Target |")
            lines.append("|--------|--------|")
            for imp in sorted(dep.algorithm_imports):
                short = imp.replace("k0.modules.consolidation.", "")
                lines.append(f"| `{short}` | Wired |")
            lines.append("")

    # Orphans
    if report.orphan_files:
        lines.append("## Orphan Files")
        lines.append("")
        lines.append("| File | Category | Action Required |")
        lines.append("|------|----------|-----------------|")
        for f in sorted(report.orphan_algorithm_files):
            lines.append(f"| `{f}` | Algorithm | Wire or delete |")
        for f in sorted(report.orphan_pipeline_files):
            lines.append(f"| `{f}` | Pipeline | Wire or delete |")
        lines.append("")

    return "\n".join(lines)


def export_dependency_matrix(
    pipeline_files: list[FileInfo],
    algorithm_files: list[FileInfo],
    include_extended: bool = True,
) -> dict:
    """
    Export full dependency matrix for tracking.

    Args:
        pipeline_files: List of pipeline file info
        algorithm_files: List of algorithm file info
        include_extended: If True, include __init__.py and contract imports

    Returns a dict with:
    - forward_deps: file -> list of files it imports
    - reverse_deps: file -> list of files that import it
    - orphans: files with no importers (using extended checks if enabled)
    - roots: files that import others but aren't imported (entry points)
    """
    all_files = pipeline_files + algorithm_files

    # Forward dependencies (what does this file import?)
    forward_deps: dict[str, list[str]] = {}
    # Reverse dependencies (what imports this file?)
    reverse_deps: dict[str, list[str]] = {}

    for f in all_files:
        forward_deps[f.relative_path] = []
        reverse_deps[f.relative_path] = []

    # Build forward deps from imports
    for f in all_files:
        for imp in f.imports:
            # Find target file
            for target in all_files:
                if target.module_path == imp or imp.startswith(target.module_path + "."):
                    forward_deps[f.relative_path].append(target.relative_path)
                    break

    # Build reverse deps from imported_by
    for f in all_files:
        for importer_module in f.imported_by:
            # Find importer file
            for importer in all_files:
                if importer.module_path == importer_module:
                    reverse_deps[f.relative_path].append(importer.relative_path)
                    break

    # Use find_orphan_files which has extended logic
    orphan_pipeline, orphan_algorithm = find_orphan_files(
        pipeline_files, algorithm_files, include_extended=include_extended
    )
    orphans = orphan_pipeline + orphan_algorithm

    # Identify roots (import others but aren't imported)
    roots = [
        f.relative_path
        for f in all_files
        if not reverse_deps.get(f.relative_path)
        and forward_deps.get(f.relative_path)
        and f.category in ("phases", "root")
    ]

    return {
        "forward_deps": forward_deps,
        "reverse_deps": reverse_deps,
        "orphans": orphans,
        "roots": roots,
        "total_files": len(all_files),
        "pipeline_files": len(pipeline_files),
        "algorithm_files": len(algorithm_files),
    }


def print_dependency_report(
    pipeline_files: list[FileInfo],
    algorithm_files: list[FileInfo],
) -> None:
    """Print comprehensive dependency report."""
    matrix = export_dependency_matrix(pipeline_files, algorithm_files)

    print("=" * 70)
    print("P03 DEPENDENCY MATRIX")
    print("=" * 70)
    print()
    print(f"Total Files: {matrix['total_files']}")
    print(f"  Pipeline: {matrix['pipeline_files']}")
    print(f"  Algorithm: {matrix['algorithm_files']}")
    print(f"  Roots (entry points): {len(matrix['roots'])}")
    print(f"  Orphans (unused): {len(matrix['orphans'])}")
    print()

    # Show roots (entry points)
    if matrix["roots"]:
        print("-" * 70)
        print("ENTRY POINTS (phases/roots that start the chain)")
        print("-" * 70)
        for root in sorted(matrix["roots"]):
            deps = matrix["forward_deps"].get(root, [])
            print(f"\n{root}")
            if deps:
                for dep in sorted(deps):
                    print(f"  -> {dep}")

    # Show what each file imports (forward deps)
    print()
    print("-" * 70)
    print("FORWARD DEPENDENCIES (file -> imports)")
    print("-" * 70)
    for path in sorted(matrix["forward_deps"].keys()):
        deps = matrix["forward_deps"][path]
        if deps:
            print(f"\n{path}")
            for dep in sorted(deps):
                print(f"  -> {dep}")

    # Show what imports each file (reverse deps)
    print()
    print("-" * 70)
    print("REVERSE DEPENDENCIES (file <- imported by)")
    print("-" * 70)
    for path in sorted(matrix["reverse_deps"].keys()):
        importers = matrix["reverse_deps"][path]
        if importers:
            print(f"\n{path}")
            for importer in sorted(importers):
                print(f"  <- {importer}")

    # Show orphans
    if matrix["orphans"]:
        print()
        print("-" * 70)
        print("ORPHANS (not imported by anything)")
        print("-" * 70)
        for orphan in sorted(matrix["orphans"]):
            print(f"  ! {orphan}")


# =============================================================================
# CLI
# =============================================================================


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="P03 Wiring Scanner - Detect orphan files and build dependency graph",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python -m governance.k0.scripts.p03_wiring_scanner --report
    python -m governance.k0.scripts.p03_wiring_scanner --orphans
    python -m governance.k0.scripts.p03_wiring_scanner --graph
    python -m governance.k0.scripts.p03_wiring_scanner --phase r0
    python -m governance.k0.scripts.p03_wiring_scanner --deps
    python -m governance.k0.scripts.p03_wiring_scanner --deps --json > deps.json
    python -m governance.k0.scripts.p03_wiring_scanner --markdown > p03_deps.md
        """,
    )

    parser.add_argument(
        "--report",
        action="store_true",
        help="Generate full wiring report",
    )
    parser.add_argument(
        "--orphans",
        action="store_true",
        help="List orphan files only",
    )
    parser.add_argument(
        "--graph",
        action="store_true",
        help="Show phase dependency graph",
    )
    parser.add_argument(
        "--phase",
        type=str,
        help="Show dependencies for specific phase (r0, r1, etc.)",
    )
    parser.add_argument(
        "--markdown",
        action="store_true",
        help="Output markdown format",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output JSON format",
    )
    parser.add_argument(
        "--deps",
        action="store_true",
        help="Show full dependency matrix (forward + reverse deps)",
    )

    args = parser.parse_args()

    # Default to report if no action specified
    if not any([args.report, args.orphans, args.graph, args.phase, args.markdown, args.deps]):
        args.report = True

    # Handle --deps separately (doesn't need full report)
    if args.deps:
        pipeline_files = scan_p03_pipeline_files()
        algorithm_files = scan_consolidation_algorithm_files()
        build_import_graph(pipeline_files, algorithm_files)

        if args.json:
            import json

            matrix = export_dependency_matrix(pipeline_files, algorithm_files)
            print(json.dumps(matrix, indent=2))
        else:
            print_dependency_report(pipeline_files, algorithm_files)
        return 0

    # Generate report
    report = generate_wiring_report()

    # Output based on flags
    if args.json:
        import json

        data = {
            "total_pipeline_files": report.total_pipeline_files,
            "total_algorithm_files": report.total_algorithm_files,
            "wired_pipeline_files": report.wired_pipeline_files,
            "wired_algorithm_files": report.wired_algorithm_files,
            "orphan_pipeline_files": report.orphan_pipeline_files,
            "orphan_algorithm_files": report.orphan_algorithm_files,
            "coverage_percent": report.coverage_percent,
            "phase_dependencies": {
                k: {
                    "phase_id": v.phase_id,
                    "phase_file": v.phase_file,
                    "algorithm_imports": v.algorithm_imports,
                    "pipeline_imports": v.pipeline_imports,
                }
                for k, v in report.phase_dependencies.items()
            },
        }
        print(json.dumps(data, indent=2))
    elif args.markdown:
        print(generate_markdown_report(report))
    elif args.orphans:
        print_orphans_only(report)
    elif args.graph or args.phase:
        print_phase_graph(report, args.phase)
    else:
        print_summary_report(report)

    # Return non-zero if orphans found
    return 1 if report.orphan_files else 0


if __name__ == "__main__":
    sys.exit(main())
