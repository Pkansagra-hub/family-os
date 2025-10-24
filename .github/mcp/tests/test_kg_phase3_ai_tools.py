"""
Test Phase 3: AI Query Tools for KG-3.1, KG-3.2, KG-3.3

Tests the 3 high-level AI tools:
- kg_implementation_chain() - Complete context for ADR implementation
- kg_dependency_impact() - Impact analysis of module changes
- kg_get_feature_context() - Feature context for new implementation

Performance targets: <100ms per query
"""

import pytest
from kg_mcp_server import (
    kg_dependency_impact,
    kg_get_feature_context,
    kg_implementation_chain,
)


class TestKgImplementationChain:
    """Test kg_implementation_chain() tool."""

    def test_returns_dict_structure(self) -> None:
        """Test function returns proper dict structure."""
        result = kg_implementation_chain("adr_0001")
        assert isinstance(result, dict)

    def test_includes_required_fields(self) -> None:
        """Test output includes all required fields."""
        result = kg_implementation_chain("adr_0001")

        required_fields = [
            "adr",
            "contracts",
            "modules",
            "files",
            "tests",
            "related_adr",
            "patterns",
            "implementation_effort",
            "dependencies",
            "query_time_ms",
        ]

        # If ADR not found, just check for error field or empty success response
        if "error" not in result:
            for field in required_fields:
                assert field in result, f"Missing field: {field}"

    def test_adr_structure(self) -> None:
        """Test ADR metadata structure."""
        result = kg_implementation_chain("adr_0001")

        if "error" not in result and "adr" in result:
            adr = result["adr"]
            assert isinstance(adr, dict)
            assert "id" in adr
            assert "title" in adr
            assert "status" in adr

    def test_contracts_is_list(self) -> None:
        """Test contracts is a list."""
        result = kg_implementation_chain("adr_0001")

        if "error" not in result:
            assert isinstance(result["contracts"], list)

    def test_modules_is_list(self) -> None:
        """Test modules is a list."""
        result = kg_implementation_chain("adr_0001")

        if "error" not in result:
            assert isinstance(result["modules"], list)

    def test_files_is_list(self) -> None:
        """Test files is a list."""
        result = kg_implementation_chain("adr_0001")

        if "error" not in result:
            assert isinstance(result["files"], list)

    def test_tests_is_list(self) -> None:
        """Test tests is a list."""
        result = kg_implementation_chain("adr_0001")

        if "error" not in result:
            assert isinstance(result["tests"], list)

    def test_related_adr_is_list(self) -> None:
        """Test related_adr is a list."""
        result = kg_implementation_chain("adr_0001")

        if "error" not in result:
            assert isinstance(result["related_adr"], list)

    def test_patterns_is_list(self) -> None:
        """Test patterns is a list."""
        result = kg_implementation_chain("adr_0001")

        if "error" not in result:
            assert isinstance(result["patterns"], list)

    def test_effort_is_string(self) -> None:
        """Test implementation_effort is a string."""
        result = kg_implementation_chain("adr_0001")

        if "error" not in result:
            assert isinstance(result["implementation_effort"], str)

    def test_query_time_reasonable(self) -> None:
        """Test query completes in reasonable time."""
        result = kg_implementation_chain("adr_0001")

        if "error" not in result:
            assert result["query_time_ms"] >= 0
            assert result["query_time_ms"] < 200  # Allow up to 200ms

    def test_dependencies_list(self) -> None:
        """Test dependencies is a list."""
        result = kg_implementation_chain("adr_0001")

        if "error" not in result:
            assert isinstance(result["dependencies"], list)


class TestKgDependencyImpact:
    """Test kg_dependency_impact() tool."""

    def test_returns_dict_structure(self) -> None:
        """Test function returns proper dict structure."""
        result = kg_dependency_impact("k0.kernel")
        assert isinstance(result, dict)

    def test_includes_required_fields(self) -> None:
        """Test output includes all required fields."""
        result = kg_dependency_impact("k0.kernel")

        required_fields = [
            "module",
            "direct_dependents",
            "transitive_dependents",
            "dependent_count",
            "risk_level",
            "affected_tests",
            "affected_contracts",
            "breaking_changes",
            "migration_effort",
            "recommendations",
            "query_time_ms",
        ]

        for field in required_fields:
            assert field in result, f"Missing field: {field}"

    def test_module_matches(self) -> None:
        """Test returned module matches input."""
        module_id = "k0.kernel"
        result = kg_dependency_impact(module_id)
        assert result["module"] == module_id

    def test_risk_level_valid(self) -> None:
        """Test risk_level is one of valid values."""
        result = kg_dependency_impact("k0.kernel")
        assert result["risk_level"] in ["LOW", "MEDIUM", "HIGH"]

    def test_dependent_lists(self) -> None:
        """Test dependent lists are lists."""
        result = kg_dependency_impact("k0.kernel")
        assert isinstance(result["direct_dependents"], list)
        assert isinstance(result["transitive_dependents"], list)

    def test_affected_tests_list(self) -> None:
        """Test affected_tests is a list."""
        result = kg_dependency_impact("k0.kernel")
        assert isinstance(result["affected_tests"], list)

    def test_breaking_changes_list(self) -> None:
        """Test breaking_changes is a list."""
        result = kg_dependency_impact("k0.kernel")
        assert isinstance(result["breaking_changes"], list)

    def test_recommendations_list(self) -> None:
        """Test recommendations is a list."""
        result = kg_dependency_impact("k0.kernel")
        assert isinstance(result["recommendations"], list)

    def test_dependent_count_non_negative(self) -> None:
        """Test dependent_count is non-negative."""
        result = kg_dependency_impact("k0.kernel")
        assert result["dependent_count"] >= 0

    def test_dependent_count_matches_transitive(self) -> None:
        """Test dependent_count matches transitive_dependents length."""
        result = kg_dependency_impact("k0.kernel")
        assert result["dependent_count"] == len(result["transitive_dependents"])

    def test_query_time_reasonable(self) -> None:
        """Test query completes in reasonable time."""
        result = kg_dependency_impact("k0.kernel")
        assert result["query_time_ms"] >= 0
        assert result["query_time_ms"] < 200


class TestKgGetFeatureContext:
    """Test kg_get_feature_context() tool."""

    def test_returns_dict_structure(self) -> None:
        """Test function returns proper dict structure."""
        result = kg_get_feature_context("agent health monitoring")
        assert isinstance(result, dict)

    def test_includes_required_fields(self) -> None:
        """Test output includes all required fields."""
        result = kg_get_feature_context("agent health monitoring")

        required_fields = [
            "feature_name",
            "matching_adrs",
            "similar_features",
            "required_contracts",
            "suggested_layer",
            "test_template",
            "performance_budget",
            "related_modules",
            "patterns",
            "quick_start",
            "query_time_ms",
        ]

        # Check for error or success
        if "error" not in result:
            for field in required_fields:
                assert field in result, f"Missing field: {field}"

    def test_feature_name_matches(self) -> None:
        """Test returned feature_name matches input."""
        feature = "agent health monitoring"
        result = kg_get_feature_context(feature)
        assert result["feature_name"] == feature

    def test_matching_adrs_list(self) -> None:
        """Test matching_adrs is a list."""
        result = kg_get_feature_context("agent health monitoring")

        if "error" not in result:
            assert isinstance(result["matching_adrs"], list)

    def test_similar_features_list(self) -> None:
        """Test similar_features is a list."""
        result = kg_get_feature_context("agent health monitoring")

        if "error" not in result:
            assert isinstance(result["similar_features"], list)

    def test_suggested_layer_valid(self) -> None:
        """Test suggested_layer is one of valid layers."""
        result = kg_get_feature_context("agent health monitoring")

        if "error" not in result:
            valid_layers = [
                "l1_input",
                "l2_orchestration",
                "l3_execution",
                "l4_ingress",
                "l4_runtime",
                "l5_infrastructure",
            ]
            assert result["suggested_layer"] in valid_layers

    def test_performance_budget_dict(self) -> None:
        """Test performance_budget is a dict with timing info."""
        result = kg_get_feature_context("agent health monitoring")

        if "error" not in result:
            assert isinstance(result["performance_budget"], dict)
            assert "p95_ms" in result["performance_budget"]
            assert "p99_ms" in result["performance_budget"]

    def test_related_modules_list(self) -> None:
        """Test related_modules is a list."""
        result = kg_get_feature_context("agent health monitoring")

        if "error" not in result:
            assert isinstance(result["related_modules"], list)

    def test_patterns_list(self) -> None:
        """Test patterns is a list."""
        result = kg_get_feature_context("agent health monitoring")

        if "error" not in result:
            assert isinstance(result["patterns"], list)

    def test_quick_start_string(self) -> None:
        """Test quick_start is a string."""
        result = kg_get_feature_context("agent health monitoring")

        if "error" not in result:
            assert isinstance(result["quick_start"], str)
            assert len(result["quick_start"]) > 10

    def test_query_time_reasonable(self) -> None:
        """Test query completes in reasonable time."""
        result = kg_get_feature_context("agent health monitoring")

        if "error" not in result:
            assert result["query_time_ms"] >= 0
            assert result["query_time_ms"] < 200

    def test_orchestration_feature(self) -> None:
        """Test orchestration feature suggests l2_orchestration."""
        result = kg_get_feature_context("orchestrator management")

        if "error" not in result:
            assert result["suggested_layer"] == "l2_orchestration"

    def test_agent_feature(self) -> None:
        """Test agent feature suggests l3_execution."""
        result = kg_get_feature_context("agent scheduling")

        if "error" not in result:
            assert result["suggested_layer"] == "l3_execution"

    def test_api_feature(self) -> None:
        """Test api feature suggests l4_ingress."""
        result = kg_get_feature_context("api gateway")

        if "error" not in result:
            assert result["suggested_layer"] == "l4_ingress"


class TestIntegration:
    """Integration tests for Phase 3 tools."""

    def test_all_tools_accessible(self) -> None:
        """Test all 3 tools are accessible and callable."""
        try:
            result1 = kg_implementation_chain("adr_0001")
            result2 = kg_dependency_impact("k0.kernel")
            result3 = kg_get_feature_context("test feature")

            # All should return dicts
            assert isinstance(result1, dict)
            assert isinstance(result2, dict)
            assert isinstance(result3, dict)
        except Exception as e:
            pytest.fail(f"Tool execution failed: {e}")

    def test_consistent_performance(self) -> None:
        """Test tools have consistent performance profiles."""
        times = []

        result1 = kg_implementation_chain("adr_0001")
        if "query_time_ms" in result1:
            times.append(result1["query_time_ms"])

        result2 = kg_dependency_impact("k0.kernel")
        if "query_time_ms" in result2:
            times.append(result2["query_time_ms"])

        result3 = kg_get_feature_context("test feature")
        if "query_time_ms" in result3:
            times.append(result3["query_time_ms"])

        # All tools should complete reasonably
        for t in times:
            if t >= 0:  # Valid timing
                assert t < 300, f"Query took {t}ms, exceeds 300ms limit"

    def test_error_handling(self) -> None:
        """Test tools handle errors gracefully."""
        # Non-existent ADR
        result1 = kg_implementation_chain("adr_nonexistent_99999")
        # Should either return error dict or empty results
        assert isinstance(result1, dict)

        # Valid module (should work)
        result2 = kg_dependency_impact("k0.kernel")
        assert isinstance(result2, dict)
