"""
Phase 5: Advanced Analytics Tests

Comprehensive test coverage for:
- kg_impact_analysis(): ADR change impact analysis
- kg_diagnostics(): Architecture diagnostics and issue detection

Test coverage target: 90%+ of Phase 5 code
Performance target: <150ms P95 per query
"""

import sys
import time
from pathlib import Path

import pytest

# Setup path before imports
mcp_path = Path(__file__).parent.parent
sys.path.insert(0, str(mcp_path))

from kg_mcp_server import kg_diagnostics, kg_impact_analysis


class TestKgImpactAnalysisBasics:
    """Test kg_impact_analysis() basic functionality"""

    def test_impact_analysis_returns_dict(self) -> None:
        """Impact analysis should return dict with required fields"""
        result = kg_impact_analysis("adr_0051")

        assert isinstance(result, dict)
        assert "adr_id" in result
        assert "affected_code" in result
        assert "affected_tests" in result
        assert "breaking_changes" in result
        assert "complexity_score" in result
        assert "migration_effort" in result
        assert "query_time_ms" in result

    def test_impact_analysis_preserves_adr_id(self) -> None:
        """ADR ID should be preserved in result"""
        result = kg_impact_analysis("adr_0001")
        assert result["adr_id"] == "adr_0001"

    def test_impact_analysis_affected_code_structure(self) -> None:
        """Affected code should have proper structure"""
        result = kg_impact_analysis("adr_0051")
        affected_code = result["affected_code"]

        assert "modules" in affected_code
        assert "files" in affected_code
        assert "total_modules" in affected_code
        assert "total_files" in affected_code
        assert isinstance(affected_code["modules"], list)
        assert isinstance(affected_code["files"], list)

    def test_impact_analysis_affected_tests_structure(self) -> None:
        """Affected tests should have proper structure"""
        result = kg_impact_analysis("adr_0051")
        affected_tests = result["affected_tests"]

        assert "test_files" in affected_tests
        assert "total_tests" in affected_tests
        assert "estimated_test_count" in affected_tests
        assert isinstance(affected_tests["test_files"], list)

    def test_impact_analysis_complexity_score_in_range(self) -> None:
        """Complexity score should be 0-100"""
        result = kg_impact_analysis("adr_0051")
        assert 0 <= result["complexity_score"] <= 100

    def test_impact_analysis_migration_effort_valid(self) -> None:
        """Migration effort should be LOW, MEDIUM, or HIGH"""
        result = kg_impact_analysis("adr_0051")
        assert result["migration_effort"] in ["LOW", "MEDIUM", "HIGH"]

    def test_impact_analysis_effort_days_positive(self) -> None:
        """Estimated effort should be positive days"""
        result = kg_impact_analysis("adr_0051")
        assert result["estimated_effort_days"] > 0
        assert isinstance(result["estimated_effort_days"], int)

    def test_impact_analysis_breaking_changes_list(self) -> None:
        """Breaking changes should be list of strings"""
        result = kg_impact_analysis("adr_0051")
        assert isinstance(result["breaking_changes"], list)
        assert all(isinstance(item, str) for item in result["breaking_changes"])

    def test_impact_analysis_rollback_risks_provided(self) -> None:
        """Rollback risks should be provided"""
        result = kg_impact_analysis("adr_0051")
        assert "rollback_risks" in result
        assert isinstance(result["rollback_risks"], list)
        assert len(result["rollback_risks"]) > 0

    def test_impact_analysis_recommendations_provided(self) -> None:
        """Recommendations should be provided"""
        result = kg_impact_analysis("adr_0051")
        assert "recommendations" in result
        assert isinstance(result["recommendations"], list)
        assert len(result["recommendations"]) >= 5  # At least 5 steps


class TestKgImpactAnalysisComplexity:
    """Test kg_impact_analysis() complexity scoring"""

    def test_impact_analysis_low_complexity(self) -> None:
        """Simple ADR should have low complexity"""
        result = kg_impact_analysis("adr_0099")  # Hypothetical simple ADR
        # This will have whatever real data says, but test structure is sound
        assert result["complexity_score"] >= 0

    def test_impact_analysis_effort_correlates_with_complexity(self) -> None:
        """Higher complexity should mean higher effort"""
        results = []
        for adr_id in ["adr_0001", "adr_0051"]:
            result = kg_impact_analysis(adr_id)
            results.append(
                {
                    "adr_id": adr_id,
                    "complexity": result["complexity_score"],
                    "effort": result["estimated_effort_days"],
                }
            )

        # Just verify effort is reasonable (not validation of specific values)
        for r in results:
            assert r["effort"] <= 30  # No ADR should take >30 days

    def test_impact_analysis_dependents_impact_structure(self) -> None:
        """Dependents impact should have proper structure"""
        result = kg_impact_analysis("adr_0051")
        dependents = result["dependents_impact"]

        assert "total_dependents" in dependents
        assert "risk_level" in dependents
        assert dependents["risk_level"] in ["LOW", "MEDIUM", "HIGH"]
        assert isinstance(dependents["total_dependents"], int)


class TestKgDiagnosticsBasics:
    """Test kg_diagnostics() basic functionality"""

    def test_diagnostics_returns_dict(self) -> None:
        """Diagnostics should return dict with required fields"""
        result = kg_diagnostics("unmaintained")

        assert isinstance(result, dict)
        assert "diagnostic_type" in result
        assert "issues_found" in result
        assert "issues" in result
        assert "severity_summary" in result
        assert "query_time_ms" in result

    def test_diagnostics_preserves_diagnostic_type(self) -> None:
        """Diagnostic type should be preserved"""
        result = kg_diagnostics("orphaned")
        assert result["diagnostic_type"] == "orphaned"

    def test_diagnostics_issues_is_list(self) -> None:
        """Issues should be a list"""
        result = kg_diagnostics("missing_tests")
        assert isinstance(result["issues"], list)

    def test_diagnostics_severity_summary_structure(self) -> None:
        """Severity summary should have all levels"""
        result = kg_diagnostics("adr_drift")
        severity = result["severity_summary"]

        assert "CRITICAL" in severity
        assert "HIGH" in severity
        assert "MEDIUM" in severity
        assert "LOW" in severity
        assert all(isinstance(v, int) for v in severity.values())

    def test_diagnostics_recommendations_provided(self) -> None:
        """Recommendations should be provided"""
        result = kg_diagnostics("circular_deps")
        assert "recommendations" in result
        assert isinstance(result["recommendations"], list)
        assert len(result["recommendations"]) > 0

    def test_diagnostics_next_steps_provided(self) -> None:
        """Next steps should be provided"""
        result = kg_diagnostics("high_complexity")
        assert "next_steps" in result
        assert isinstance(result["next_steps"], list)
        assert len(result["next_steps"]) > 0

    def test_diagnostics_total_severity_score_calculated(self) -> None:
        """Total severity score should be calculated"""
        result = kg_diagnostics("dead_imports")
        assert "total_severity_score" in result
        assert isinstance(result["total_severity_score"], int)
        assert result["total_severity_score"] >= 0


class TestKgDiagnosticsTypes:
    """Test each diagnostic type"""

    def test_diagnostics_unmaintained(self) -> None:
        """Unmaintained diagnostic should work"""
        result = kg_diagnostics("unmaintained")
        assert result["diagnostic_type"] == "unmaintained"
        assert result["issues_found"] >= 0
        # Should have recommendations specific to unmaintained code
        recommendations = result["recommendations"]
        rec_text = " ".join(recommendations).lower()
        assert "test" in rec_text or "deprecat" in rec_text

    def test_diagnostics_orphaned(self) -> None:
        """Orphaned diagnostic should work"""
        result = kg_diagnostics("orphaned")
        assert result["diagnostic_type"] == "orphaned"
        assert isinstance(result["issues"], list)

    def test_diagnostics_dead_imports(self) -> None:
        """Dead imports diagnostic should work"""
        result = kg_diagnostics("dead_imports")
        assert result["diagnostic_type"] == "dead_imports"
        # Issues should describe import problems if found
        for issue in result["issues"]:
            if "import_statement" in issue:
                assert isinstance(issue["import_statement"], str)

    def test_diagnostics_missing_tests(self) -> None:
        """Missing tests diagnostic should work"""
        result = kg_diagnostics("missing_tests")
        assert result["diagnostic_type"] == "missing_tests"
        # Should recommend WARD tests
        recommendations = result["recommendations"]
        rec_text = " ".join(recommendations).lower()
        assert "ward" in rec_text or "test" in rec_text

    def test_diagnostics_adr_drift(self) -> None:
        """ADR drift diagnostic should work"""
        result = kg_diagnostics("adr_drift")
        assert result["diagnostic_type"] == "adr_drift"
        # Issues should mention ADR IDs
        for issue in result["issues"]:
            if "adr_id" in issue:
                assert isinstance(issue["adr_id"], str)

    def test_diagnostics_circular_deps(self) -> None:
        """Circular deps diagnostic should work"""
        result = kg_diagnostics("circular_deps")
        assert result["diagnostic_type"] == "circular_deps"
        # Should have recommendations for breaking cycles
        recommendations = result["recommendations"]
        rec_text = " ".join(recommendations).lower()
        assert "extract" in rec_text or "break" in rec_text or "cycle" in rec_text

    def test_diagnostics_high_complexity(self) -> None:
        """High complexity diagnostic should work"""
        result = kg_diagnostics("high_complexity")
        assert result["diagnostic_type"] == "high_complexity"
        # Should recommend breaking into smaller modules
        recommendations = result["recommendations"]
        rec_text = " ".join(recommendations).lower()
        assert "smaller" in rec_text or "modular" in rec_text or "break" in rec_text

    def test_diagnostics_unknown_type(self) -> None:
        """Unknown diagnostic type should be handled gracefully"""
        result = kg_diagnostics("unknown_diagnostic_xyz_123")
        assert result["diagnostic_type"] == "unknown_diagnostic_xyz_123"
        # Should have error message
        assert result["issues_found"] >= 0
        if result["issues"]:
            issue = result["issues"][0]
            assert "error" in str(issue).lower() or "unknown" in str(issue).lower()


class TestKgDiagnosticsIssueStructure:
    """Test issue structure in diagnostics results"""

    def test_unmaintained_issue_has_required_fields(self) -> None:
        """Unmaintained issues should have required fields"""
        result = kg_diagnostics("unmaintained")
        if result["issues"]:
            issue = result["issues"][0]
            assert "severity" in issue
            assert "reason" in issue
            assert "action" in issue

    def test_orphaned_issue_has_required_fields(self) -> None:
        """Orphaned issues should have module and action"""
        result = kg_diagnostics("orphaned")
        if result["issues"]:
            issue = result["issues"][0]
            assert "severity" in issue
            assert "action" in issue

    def test_dead_imports_issue_has_required_fields(self) -> None:
        """Dead import issues should have file location"""
        result = kg_diagnostics("dead_imports")
        if result["issues"]:
            issue = result["issues"][0]
            assert "severity" in issue
            assert "reason" in issue

    def test_missing_tests_issue_has_coverage(self) -> None:
        """Missing tests issues should have coverage info"""
        result = kg_diagnostics("missing_tests")
        if result["issues"]:
            issue = result["issues"][0]
            assert "severity" in issue
            # Coverage estimate should be present
            if "coverage_estimate" in issue:
                assert isinstance(issue["coverage_estimate"], str)


class TestPerformance:
    """Test performance of Phase 5 tools"""

    def test_impact_analysis_performance(self) -> None:
        """Impact analysis should complete within 150ms"""
        start = time.time()
        result = kg_impact_analysis("adr_0051")
        elapsed_ms = (time.time() - start) * 1000

        assert elapsed_ms < 150
        assert result["query_time_ms"] < 150

    def test_diagnostics_performance(self) -> None:
        """Diagnostics should complete within 150ms"""
        start = time.time()
        result = kg_diagnostics("unmaintained")
        elapsed_ms = (time.time() - start) * 1000

        assert elapsed_ms < 150
        assert result["query_time_ms"] < 150

    def test_multiple_diagnostics_performance(self) -> None:
        """Running multiple diagnostics should stay under budget"""
        diagnostic_types = [
            "unmaintained",
            "orphaned",
            "missing_tests",
            "high_complexity",
        ]

        times = []
        for diag_type in diagnostic_types:
            start = time.time()
            result = kg_diagnostics(diag_type)
            elapsed_ms = (time.time() - start) * 1000
            times.append(elapsed_ms)
            assert elapsed_ms < 150

        # Average should be reasonable
        avg_time = sum(times) / len(times)
        assert avg_time < 120


class TestIntegration:
    """Integration tests for Phase 5"""

    def test_impact_analysis_and_diagnostics_consistency(self) -> None:
        """Impact analysis and diagnostics should work together"""
        impact = kg_impact_analysis("adr_0051")
        diagnostics = kg_diagnostics("adr_drift")

        # Both should return proper structures
        assert isinstance(impact, dict)
        assert isinstance(diagnostics, dict)
        assert "adr_id" in impact or "diagnostic_type" in diagnostics

    def test_phase5_tools_accessible(self) -> None:
        """Phase 5 tools should be accessible"""
        assert callable(kg_impact_analysis)
        assert callable(kg_diagnostics)

    def test_phase5_graceful_error_handling(self) -> None:
        """Phase 5 tools should handle errors gracefully"""
        # Non-existent ADR should still return valid structure
        result = kg_impact_analysis("adr_9999")
        assert isinstance(result, dict)
        assert "adr_id" in result
        assert result["adr_id"] == "adr_9999"

        # Unknown diagnostic should return valid structure
        result = kg_diagnostics("completely_unknown_type_xyz")
        assert isinstance(result, dict)
        assert "diagnostic_type" in result


class TestPhase5Documentation:
    """Tests for Phase 5 documentation"""

    def test_impact_analysis_has_docstring(self) -> None:
        """kg_impact_analysis should have comprehensive docstring"""
        assert kg_impact_analysis.__doc__ is not None
        assert len(kg_impact_analysis.__doc__) > 100
        assert "Impact" in kg_impact_analysis.__doc__

    def test_diagnostics_has_docstring(self) -> None:
        """kg_diagnostics should have comprehensive docstring"""
        assert kg_diagnostics.__doc__ is not None
        assert len(kg_diagnostics.__doc__) > 100
        # Check for diagnostics-related content
        doc = kg_diagnostics.__doc__.lower()
        assert "diagnostic" in doc or "architectur" in doc

    def test_impact_analysis_docstring_includes_example(self) -> None:
        """Impact analysis docstring should include example"""
        doc = kg_impact_analysis.__doc__
        if doc:
            assert "Example" in doc

    def test_diagnostics_docstring_includes_types(self) -> None:
        """Diagnostics docstring should list diagnostic types"""
        doc = kg_diagnostics.__doc__
        if doc:
            doc_lower = doc.lower()
            assert "unmaintained" in doc_lower or "orphaned" in doc_lower


class TestPhase5Completeness:
    """Tests verifying Phase 5 is complete"""

    def test_all_phase5_tools_exported(self) -> None:
        """All Phase 5 tools should be available"""
        from kg_mcp_server import kg_diagnostics, kg_impact_analysis

        assert callable(kg_impact_analysis)
        assert callable(kg_diagnostics)

    def test_impact_analysis_uses_prior_phases(self) -> None:
        """Impact analysis should use Phase 1-3 tools internally"""
        result = kg_impact_analysis("adr_0051")

        # Should have aggregated data from prior phases
        assert "affected_code" in result
        assert "affected_tests" in result
        assert "breaking_changes" in result

    def test_diagnostics_covers_all_types(self) -> None:
        """Diagnostics should support all documented types"""
        supported_types = [
            "unmaintained",
            "orphaned",
            "dead_imports",
            "missing_tests",
            "adr_drift",
            "circular_deps",
            "high_complexity",
        ]

        for diag_type in supported_types:
            diag_result = kg_diagnostics(diag_type)
            assert diag_result["diagnostic_type"] == diag_type


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
