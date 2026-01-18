"""
Unit tests for P03 Wiring Scanner.

Tests file scanning, import parsing, graph building, and orphan detection.
"""

from pathlib import Path

from governance.k0.scripts.p03_wiring_scanner import (
    WiringReport,
    _categorize_file,
    _path_to_module,
    build_import_graph,
    find_orphan_files,
    find_phase_not_importing,
    parse_imports_from_file,
    scan_consolidation_algorithm_files,
    scan_p03_pipeline_files,
)


class TestDataClasses:
    """Tests for data class properties."""

    def test_wiring_report_total_files(self):
        report = WiringReport(
            total_pipeline_files=78,
            total_algorithm_files=89,
            wired_pipeline_files=50,
            wired_algorithm_files=60,
        )
        assert report.total_files == 167

    def test_wiring_report_wired_files(self):
        report = WiringReport(
            total_pipeline_files=78,
            total_algorithm_files=89,
            wired_pipeline_files=50,
            wired_algorithm_files=60,
        )
        assert report.wired_files == 110

    def test_wiring_report_coverage_percent(self):
        report = WiringReport(
            total_pipeline_files=50,
            total_algorithm_files=50,
            wired_pipeline_files=25,
            wired_algorithm_files=25,
        )
        assert report.coverage_percent == 50.0

    def test_wiring_report_coverage_zero_files(self):
        report = WiringReport(
            total_pipeline_files=0,
            total_algorithm_files=0,
            wired_pipeline_files=0,
            wired_algorithm_files=0,
        )
        assert report.coverage_percent == 0.0

    def test_wiring_report_orphan_files_combined(self):
        report = WiringReport(
            total_pipeline_files=10,
            total_algorithm_files=10,
            wired_pipeline_files=5,
            wired_algorithm_files=5,
            orphan_pipeline_files=["a.py", "b.py"],
            orphan_algorithm_files=["x.py", "y.py", "z.py"],
        )
        assert len(report.orphan_files) == 5


class TestPathUtilities:
    """Tests for path utility functions."""

    def test_path_to_module_simple(self):
        repo_root = Path("D:/familyos")
        file_path = Path("D:/familyos/k0/modules/consolidation/algorithms/decay_engine.py")
        result = _path_to_module(file_path, repo_root)
        assert result == "k0.modules.consolidation.algorithms.decay_engine"

    def test_path_to_module_pipeline(self):
        repo_root = Path("D:/familyos")
        file_path = Path("D:/familyos/k0/pipelines/p03/phases/r0_batch_selector.py")
        result = _path_to_module(file_path, repo_root)
        assert result == "k0.pipelines.p03.phases.r0_batch_selector"

    def test_categorize_file_phases(self):
        base_dir = Path("D:/familyos/k0/pipelines/p03")
        file_path = Path("D:/familyos/k0/pipelines/p03/phases/r0_batch_selector.py")
        result = _categorize_file(file_path, base_dir)
        assert result == "phases"

    def test_categorize_file_ops(self):
        base_dir = Path("D:/familyos/k0/pipelines/p03")
        file_path = Path("D:/familyos/k0/pipelines/p03/ops/tracing.py")
        result = _categorize_file(file_path, base_dir)
        assert result == "ops"

    def test_categorize_file_root(self):
        base_dir = Path("D:/familyos/k0/pipelines/p03")
        file_path = Path("D:/familyos/k0/pipelines/p03/main.py")
        result = _categorize_file(file_path, base_dir)
        assert result == "root"


class TestFileScanners:
    """Tests for file scanning functions."""

    def test_scan_p03_pipeline_files_returns_list(self):
        result = scan_p03_pipeline_files()
        assert isinstance(result, list)
        # We know there are ~78 files
        assert len(result) >= 70

    def test_scan_p03_pipeline_files_has_phases(self):
        result = scan_p03_pipeline_files()
        phases = [f for f in result if f.category == "phases"]
        # There are 9 phases (r0-r8)
        assert len(phases) == 9

    def test_scan_consolidation_algorithm_files_returns_list(self):
        result = scan_consolidation_algorithm_files()
        assert isinstance(result, list)
        # We know there are ~89 files
        assert len(result) >= 80

    def test_scan_consolidation_algorithm_files_excludes_init(self):
        result = scan_consolidation_algorithm_files()
        init_files = [f for f in result if f.path.name == "__init__.py"]
        assert len(init_files) == 0


class TestImportParser:
    """Tests for AST-based import parsing."""

    def test_parse_from_import(self, tmp_path):
        """Test parsing 'from k0.x import y' statements."""
        test_file = tmp_path / "test_module.py"
        test_file.write_text(
            """
from k0.modules.consolidation.algorithms.decay_engine import DecayEngine
from k0.kernel.syscalls import emit_event

def test():
    pass
"""
        )
        # Need to mock the repo root for this test
        imports = parse_imports_from_file(test_file)
        # Since our function only captures k0.* imports
        k0_imports = [i for i in imports if i.target_module.startswith("k0.")]
        assert len(k0_imports) >= 2

    def test_parse_import_statement(self, tmp_path):
        """Test parsing 'import k0.x' statements."""
        test_file = tmp_path / "test_module.py"
        test_file.write_text(
            """
import k0.modules.consolidation.algorithms as algorithms

def test():
    pass
"""
        )
        imports = parse_imports_from_file(test_file)
        # Check import type
        assert any(i.import_type == "import" for i in imports)

    def test_parse_non_k0_import_ignored(self, tmp_path):
        """Test that non-k0 imports are ignored."""
        test_file = tmp_path / "test_module.py"
        test_file.write_text(
            """
import os
import sys
from pathlib import Path
from typing import Optional

def test():
    pass
"""
        )
        imports = parse_imports_from_file(test_file)
        assert len(imports) == 0

    def test_parse_syntax_error_handled(self, tmp_path):
        """Test that syntax errors are handled gracefully."""
        test_file = tmp_path / "bad_syntax.py"
        test_file.write_text("def broken(:\n    pass")
        imports = parse_imports_from_file(test_file)
        assert imports == []


class TestImportGraph:
    """Tests for import graph building."""

    def test_build_import_graph_returns_dict(self):
        pipeline_files = scan_p03_pipeline_files()
        algorithm_files = scan_consolidation_algorithm_files()
        graph = build_import_graph(pipeline_files, algorithm_files)
        assert isinstance(graph, dict)
        assert len(graph) > 0

    def test_build_import_graph_updates_imported_by(self):
        pipeline_files = scan_p03_pipeline_files()
        algorithm_files = scan_consolidation_algorithm_files()
        build_import_graph(pipeline_files, algorithm_files)

        # Find a file we know is imported
        decay_engine = next((f for f in algorithm_files if "decay_engine" in f.relative_path), None)
        # decay_engine should be imported by r3_dedup_decay
        if decay_engine:
            assert len(decay_engine.imported_by) >= 1


class TestOrphanDetection:
    """Tests for orphan file detection."""

    def test_find_orphan_files_returns_tuples(self):
        pipeline_files = scan_p03_pipeline_files()
        algorithm_files = scan_consolidation_algorithm_files()
        build_import_graph(pipeline_files, algorithm_files)

        orphan_pipeline, orphan_algorithm = find_orphan_files(pipeline_files, algorithm_files)

        assert isinstance(orphan_pipeline, list)
        assert isinstance(orphan_algorithm, list)

    def test_phases_not_marked_as_orphans(self):
        """Phase files are entry points and should not be marked as orphans."""
        pipeline_files = scan_p03_pipeline_files()
        algorithm_files = scan_consolidation_algorithm_files()
        build_import_graph(pipeline_files, algorithm_files)

        orphan_pipeline, _ = find_orphan_files(pipeline_files, algorithm_files)

        # Phases (r0-r8) should not be in orphans
        phase_orphans = [f for f in orphan_pipeline if "phases" in f]
        assert len(phase_orphans) == 0

    def test_find_phase_not_importing(self):
        pipeline_files = scan_p03_pipeline_files()
        algorithm_files = scan_consolidation_algorithm_files()
        build_import_graph(pipeline_files, algorithm_files)

        phases_not_importing = find_phase_not_importing(pipeline_files)
        # All phases should import from consolidation
        assert len(phases_not_importing) == 0


class TestPhaseDependencies:
    """Tests for phase dependency mapping."""

    def test_phase_dependency_has_all_phases(self):
        from governance.k0.scripts.p03_wiring_scanner import build_phase_dependencies

        pipeline_files = scan_p03_pipeline_files()
        algorithm_files = scan_consolidation_algorithm_files()
        build_import_graph(pipeline_files, algorithm_files)

        phases = build_phase_dependencies(pipeline_files)

        # Should have r0 through r8
        expected_phases = ["r0", "r1", "r2", "r3", "r4", "r5", "r6", "r7", "r8"]
        for phase in expected_phases:
            assert phase in phases, f"Missing phase {phase}"

    def test_r3_has_many_algorithm_imports(self):
        """R3 (dedup_decay) is known to have many algorithm imports."""
        from governance.k0.scripts.p03_wiring_scanner import build_phase_dependencies

        pipeline_files = scan_p03_pipeline_files()
        algorithm_files = scan_consolidation_algorithm_files()
        build_import_graph(pipeline_files, algorithm_files)

        phases = build_phase_dependencies(pipeline_files)

        r3 = phases.get("r3")
        assert r3 is not None
        # R3 should have 10+ algorithm imports
        assert len(r3.algorithm_imports) >= 10


class TestReportGeneration:
    """Tests for report generation."""

    def test_generate_wiring_report(self):
        from governance.k0.scripts.p03_wiring_scanner import generate_wiring_report

        report = generate_wiring_report()

        assert isinstance(report, WiringReport)
        assert report.total_pipeline_files > 0
        assert report.total_algorithm_files > 0
        assert 0 <= report.coverage_percent <= 100

    def test_generate_markdown_report(self):
        from governance.k0.scripts.p03_wiring_scanner import (
            generate_markdown_report,
            generate_wiring_report,
        )

        report = generate_wiring_report()
        markdown = generate_markdown_report(report)

        assert "# P03 Dependency Graph" in markdown
        assert "## Summary" in markdown
        assert "## Phase Dependencies" in markdown
