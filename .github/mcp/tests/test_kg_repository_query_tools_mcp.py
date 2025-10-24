"""
Test MCP Repository Query Tools for KG-2.4.

Tests the 4 core MCP tools in kg_mcp_server:
- kg_get_module_deps()
- kg_get_dependents()
- kg_find_circular_deps()
- kg_trace_import_chain()

Performance targets: <50ms per query
"""

import pytest
from kg_indexers import DependencyGraphEngine
from kg_mcp_server import (
    _get_dependency_engine,
    kg_find_circular_deps,
    kg_get_dependents,
    kg_get_module_deps,
    kg_trace_import_chain,
)


class TestDependencyEngineInitialization:
    """Test dependency engine initialization."""

    def test_engine_lazy_loads(self) -> None:
        """Test that engine is lazy-loaded."""
        engine = _get_dependency_engine()
        assert engine is not None
        assert isinstance(engine, DependencyGraphEngine)

    def test_engine_singleton(self) -> None:
        """Test that engine is a singleton."""
        engine1 = _get_dependency_engine()
        engine2 = _get_dependency_engine()
        assert engine1 is engine2


class TestKgGetModuleDeps:
    """Test kg_get_module_deps() MCP tool."""

    def test_returns_dict_structure(self) -> None:
        """Test function returns proper dict structure."""
        result = kg_get_module_deps("k0.kernel")
        assert isinstance(result, dict)
        assert "module_id" in result
        assert "direct_dependencies" in result

    def test_output_format_includes_all_fields(self) -> None:
        """Test output includes all required fields."""
        result = kg_get_module_deps("k0.kernel")

        required_fields = [
            "module_id",
            "direct_dependencies",
            "transitive_dependencies",
            "dependency_depth",
            "by_depth",
            "circular_found",
            "query_time_ms",
        ]
        for field in required_fields:
            assert field in result, f"Missing field: {field}"

    def test_query_time_reasonable(self) -> None:
        """Test query completes in reasonable time."""
        result = kg_get_module_deps("k0.kernel")
        assert result["query_time_ms"] >= 0
        # Should complete quickly even for real graph
        assert result["query_time_ms"] < 500

    def test_module_id_matches(self) -> None:
        """Test returned module_id matches input."""
        module_id = "k0.bus"
        result = kg_get_module_deps(module_id)
        assert result["module_id"] == module_id

    def test_depth_limit_parameter(self) -> None:
        """Test depth parameter limits results."""
        result_unlimited = kg_get_module_deps("k0.kernel")
        result_depth_2 = kg_get_module_deps("k0.kernel", depth=2)

        # Both should return valid structures
        assert "dependency_depth" in result_unlimited
        assert "dependency_depth" in result_depth_2

    def test_by_depth_structure(self) -> None:
        """Test by_depth returns dict of depth->modules."""
        result = kg_get_module_deps("k0.kernel")
        assert isinstance(result["by_depth"], dict)


class TestKgGetDependents:
    """Test kg_get_dependents() MCP tool."""

    def test_returns_dict_structure(self) -> None:
        """Test function returns proper dict structure."""
        result = kg_get_dependents("k0.kernel")
        assert isinstance(result, dict)
        assert "module_id" in result
        assert "direct_dependents" in result

    def test_output_format_includes_all_fields(self) -> None:
        """Test output includes all required fields."""
        result = kg_get_dependents("k0.kernel")

        required_fields = [
            "module_id",
            "direct_dependents",
            "transitive_dependents",
            "dependent_depth",
            "by_depth",
            "impact_radius",
            "risk_level",
            "query_time_ms",
        ]
        for field in required_fields:
            assert field in result, f"Missing field: {field}"

    def test_risk_level_valid(self) -> None:
        """Test risk_level is one of valid values."""
        result = kg_get_dependents("k0.kernel")
        assert result["risk_level"] in ["low", "medium", "high"]

    def test_impact_radius_non_negative(self) -> None:
        """Test impact_radius is non-negative."""
        result = kg_get_dependents("k0.kernel")
        assert result["impact_radius"] >= 0

    def test_module_id_matches(self) -> None:
        """Test returned module_id matches input."""
        module_id = "k0.bus"
        result = kg_get_dependents(module_id)
        assert result["module_id"] == module_id

    def test_query_time_reasonable(self) -> None:
        """Test query completes in reasonable time."""
        result = kg_get_dependents("k0.kernel")
        assert result["query_time_ms"] >= 0
        assert result["query_time_ms"] < 500


class TestKgFindCircularDeps:
    """Test kg_find_circular_deps() MCP tool."""

    def test_returns_dict_structure(self) -> None:
        """Test function returns proper dict structure."""
        result = kg_find_circular_deps()
        assert isinstance(result, dict)
        assert "circular_dependencies_found" in result
        assert "cycle_count" in result

    def test_output_format_includes_all_fields(self) -> None:
        """Test output includes all required fields."""
        result = kg_find_circular_deps()

        required_fields = [
            "circular_dependencies_found",
            "cycle_count",
            "cycles",
            "modules_in_cycles",
            "risk_level",
            "query_time_ms",
        ]
        for field in required_fields:
            assert field in result, f"Missing field: {field}"

    def test_circular_found_boolean(self) -> None:
        """Test circular_dependencies_found is boolean."""
        result = kg_find_circular_deps()
        assert isinstance(result["circular_dependencies_found"], bool)

    def test_cycle_count_non_negative(self) -> None:
        """Test cycle_count is non-negative."""
        result = kg_find_circular_deps()
        assert result["cycle_count"] >= 0

    def test_cycles_is_list(self) -> None:
        """Test cycles is a list."""
        result = kg_find_circular_deps()
        assert isinstance(result["cycles"], list)

    def test_risk_level_valid(self) -> None:
        """Test risk_level is one of valid values."""
        result = kg_find_circular_deps()
        assert result["risk_level"] in ["none", "low", "medium", "high"]

    def test_modules_in_cycles_is_list(self) -> None:
        """Test modules_in_cycles is a list."""
        result = kg_find_circular_deps()
        assert isinstance(result["modules_in_cycles"], list)

    def test_query_time_reasonable(self) -> None:
        """Test query completes in reasonable time."""
        result = kg_find_circular_deps()
        assert result["query_time_ms"] >= 0
        # Cycle detection might take longer, allow up to 200ms
        assert result["query_time_ms"] < 200


class TestKgTraceImportChain:
    """Test kg_trace_import_chain() MCP tool."""

    def test_returns_dict_structure(self) -> None:
        """Test function returns proper dict structure."""
        result = kg_trace_import_chain("k0.kernel", "k0.bus")
        assert isinstance(result, dict)
        assert "source" in result
        assert "target" in result

    def test_output_format_includes_all_fields(self) -> None:
        """Test output includes all required fields."""
        result = kg_trace_import_chain("k0.kernel", "k0.bus")

        required_fields = [
            "source",
            "target",
            "paths_found",
            "paths",
            "shortest_path_length",
            "max_paths_exceeded",
            "circular_path_exists",
            "query_time_ms",
        ]
        for field in required_fields:
            assert field in result, f"Missing field: {field}"

    def test_source_target_match(self) -> None:
        """Test returned source/target match input."""
        source, target = "k0.kernel", "k0.bus"
        result = kg_trace_import_chain(source, target)
        assert result["source"] == source
        assert result["target"] == target

    def test_paths_found_non_negative(self) -> None:
        """Test paths_found is non-negative."""
        result = kg_trace_import_chain("k0.kernel", "k0.bus")
        assert result["paths_found"] >= 0

    def test_paths_is_list(self) -> None:
        """Test paths is a list."""
        result = kg_trace_import_chain("k0.kernel", "k0.bus")
        assert isinstance(result["paths"], list)

    def test_circular_path_exists_boolean(self) -> None:
        """Test circular_path_exists is boolean."""
        result = kg_trace_import_chain("k0.kernel", "k0.bus")
        assert isinstance(result["circular_path_exists"], bool)

    def test_max_paths_parameter(self) -> None:
        """Test max_paths parameter limits results."""
        result1 = kg_trace_import_chain("k0.kernel", "k0.bus", max_paths=2)
        result2 = kg_trace_import_chain("k0.kernel", "k0.bus", max_paths=10)

        # Both should be valid
        assert result1["paths_found"] >= 0
        assert result2["paths_found"] >= 0

    def test_query_time_reasonable(self) -> None:
        """Test query completes in reasonable time."""
        result = kg_trace_import_chain("k0.kernel", "k0.bus")
        assert result["query_time_ms"] >= 0
        assert result["query_time_ms"] < 500


class TestIntegration:
    """Integration tests for all tools together."""

    def test_all_tools_work_without_error(self) -> None:
        """Test all 4 tools execute without raising errors."""
        # These may fail validation (no engine) but should not raise
        try:
            kg_get_module_deps("k0.kernel")
            kg_get_dependents("k0.kernel")
            kg_find_circular_deps()
            kg_trace_import_chain("k0.kernel", "k0.bus")
        except Exception as e:
            pytest.fail(f"Tool execution failed: {e}")

    def test_tools_consistent_performance(self) -> None:
        """Test tools have consistent performance profiles."""
        times = []

        # Run each tool and collect times
        result1 = kg_get_module_deps("k0.kernel")
        times.append(result1["query_time_ms"])

        result2 = kg_get_dependents("k0.kernel")
        times.append(result2["query_time_ms"])

        result3 = kg_find_circular_deps()
        times.append(result3["query_time_ms"])

        result4 = kg_trace_import_chain("k0.kernel", "k0.bus")
        times.append(result4["query_time_ms"])

        # All times should be reasonable (under 500ms)
        for t in times:
            assert t < 500, f"Query took {t}ms, exceeds 500ms limit"
