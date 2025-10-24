"""
Phase 4: AIContextBuilder + kg_ask() Tests

Comprehensive test coverage for:
- AIContextBuilder: 4 context-building methods
- kg_ask(): Natural language query routing
- Integration with Phase 1-3 KG tools

Test coverage target: 90%+ of Phase 4 code
Performance target: <100ms P95 per query
"""

import sys
import time
from pathlib import Path

import pytest

# Setup path before imports
mcp_path = Path(__file__).parent.parent
sys.path.insert(0, str(mcp_path))

from kg_mcp_server import AIContextBuilder, kg_ask


class TestAIContextBuilderFeatureContext:
    """Test AIContextBuilder.build_feature_context()"""

    def setup_method(self) -> None:
        """Setup before each test"""
        self.builder = AIContextBuilder()

    def test_build_feature_context_returns_dict(self) -> None:
        """Feature context should return dict with all required fields"""
        result = self.builder.build_feature_context("agent health monitoring")

        assert isinstance(result, dict)
        assert "feature_name" in result
        assert "suggested_layer" in result
        assert "matching_adrs" in result
        assert "implementations" in result
        assert "related_modules" in result
        assert "required_contracts" in result
        assert "patterns" in result
        assert "performance_budget" in result
        assert "test_template" in result
        assert "quick_start" in result
        assert "effort_estimate" in result
        assert "context_time_ms" in result

    def test_build_feature_context_layer_suggestion_orchestration(self):
        """Should suggest l2_orchestration for orchestration features"""
        result = self.builder.build_feature_context("orchestration policy")
        assert result["suggested_layer"] == "l2_orchestration"

    def test_build_feature_context_layer_suggestion_agent(self):
        """Should suggest l3_execution for agent-related features"""
        result = self.builder.build_feature_context("agent scheduling")
        assert result["suggested_layer"] == "l3_execution"

    def test_build_feature_context_layer_suggestion_api(self):
        """Should suggest l4_ingress for API/gateway features"""
        result = self.builder.build_feature_context("api gateway")
        assert result["suggested_layer"] == "l4_ingress"

    def test_build_feature_context_layer_suggestion_infra(self):
        """Should suggest l5_infrastructure for infrastructure features"""
        result = self.builder.build_feature_context("infrastructure monitoring")
        assert result["suggested_layer"] == "l5_infrastructure"

    def test_build_feature_context_performance_budget_monitoring(self):
        """Monitoring features should have budget of <100ms"""
        result = self.builder.build_feature_context("health monitoring")
        assert result["performance_budget"]["p95_ms"] <= 100

    def test_build_feature_context_performance_budget_query(self):
        """Query features should have budget of <50ms"""
        result = self.builder.build_feature_context("search functionality")
        assert result["performance_budget"]["p95_ms"] <= 50

    def test_build_feature_context_quick_start_not_empty(self):
        """Quick start should provide actionable steps"""
        result = self.builder.build_feature_context("new component")
        assert len(result["quick_start"]) > 0
        assert (
            "Review" in result["quick_start"]
            or "review" in result["quick_start"].lower()
        )

    def test_build_feature_context_effort_estimate_reasonable(self):
        """Effort estimate should be human-readable"""
        result = self.builder.build_feature_context("health monitoring")
        assert isinstance(result["effort_estimate"], str)
        assert len(result["effort_estimate"]) > 0

    def test_build_feature_context_performance_under_100ms(self):
        """Feature context should complete within 100ms"""
        start = time.time()
        result = self.builder.build_feature_context("test feature")
        elapsed_ms = (time.time() - start) * 1000

        assert elapsed_ms < 100  # Most tests should be under 100ms
        assert result["context_time_ms"] < 100


class TestAIContextBuilderErrorContext:
    """Test AIContextBuilder.build_error_context()"""

    def setup_method(self):
        """Setup before each test"""
        self.builder = AIContextBuilder()

    def test_build_error_context_returns_dict(self):
        """Error context should return dict with all required fields"""
        result = self.builder.build_error_context("circular_dependency")

        assert isinstance(result, dict)
        assert "error_type" in result
        assert "diagnosis" in result
        assert "next_steps" in result
        assert "helpful_tools" in result
        assert "context_time_ms" in result

    def test_build_error_context_circular_dependency(self):
        """Should provide guidance for circular dependencies"""
        result = self.builder.build_error_context("circular_dependency")
        assert result["error_type"] == "circular_dependency"
        assert "Circular" in result["diagnosis"]["description"]
        assert result["diagnosis"]["severity"] == "HIGH"

    def test_build_error_context_missing_contract(self):
        """Should provide guidance for missing contracts"""
        result = self.builder.build_error_context("missing_contract")
        assert result["error_type"] == "missing_contract"
        assert "contract" in result["diagnosis"]["description"].lower()
        assert result["diagnosis"]["severity"] == "MEDIUM"

    def test_build_error_context_unmaintained_module(self):
        """Should provide guidance for unmaintained modules"""
        result = self.builder.build_error_context("unmaintained_module")
        assert result["error_type"] == "unmaintained_module"
        assert "recent" in result["diagnosis"]["description"].lower()
        assert result["diagnosis"]["severity"] == "LOW"

    def test_build_error_context_adr_drift(self):
        """Should provide guidance for ADR drift"""
        result = self.builder.build_error_context("adr_drift")
        assert result["error_type"] == "adr_drift"
        assert (
            "ADR" in result["diagnosis"]["description"]
            or "drift" in result["diagnosis"]["description"].lower()
        )

    def test_build_error_context_missing_adr(self):
        """Should provide guidance for missing ADRs"""
        result = self.builder.build_error_context("missing_adr")
        assert result["error_type"] == "missing_adr"
        assert "ADR" in result["diagnosis"]["description"]

    def test_build_error_context_unknown_error(self):
        """Should handle unknown error types gracefully"""
        result = self.builder.build_error_context("unknown_error_type_xyz")
        assert "Unknown error type" in result["diagnosis"]["description"]
        assert result["diagnosis"]["severity"] == "UNKNOWN"

    def test_build_error_context_next_steps_provided(self):
        """Next steps should be list of actionable items"""
        result = self.builder.build_error_context("circular_dependency")
        assert isinstance(result["next_steps"], list)
        assert len(result["next_steps"]) > 0
        assert all(isinstance(step, str) for step in result["next_steps"])

    def test_build_error_context_helpful_tools_provided(self):
        """Helpful tools should reference KG functions"""
        result = self.builder.build_error_context("circular_dependency")
        assert isinstance(result["helpful_tools"], list)
        assert len(result["helpful_tools"]) > 0
        assert any("kg_" in tool for tool in result["helpful_tools"])


class TestAIContextBuilderModuleContext:
    """Test AIContextBuilder.build_module_context()"""

    def setup_method(self):
        """Setup before each test"""
        self.builder = AIContextBuilder()

    def test_build_module_context_returns_dict(self):
        """Module context should return dict with all required fields"""
        result = self.builder.build_module_context("k0.kernel")

        assert isinstance(result, dict)
        assert "module_name" in result
        assert "dependencies" in result
        assert "dependent_count" in result
        assert "dependents" in result
        assert "risk_level" in result
        assert "related_adrs" in result
        assert "contracts" in result
        assert "tests" in result
        assert "quick_analysis" in result
        assert "context_time_ms" in result

    def test_build_module_context_module_name_preserved(self):
        """Module name should be preserved in result"""
        result = self.builder.build_module_context("k1.l2_orchestration.scheduler")
        assert result["module_name"] == "k1.l2_orchestration.scheduler"

    def test_build_module_context_dependencies_is_list(self):
        """Dependencies should be a list"""
        result = self.builder.build_module_context("k0.kernel")
        assert isinstance(result["dependencies"], list)

    def test_build_module_context_dependents_is_list(self):
        """Dependents should be a list"""
        result = self.builder.build_module_context("k0.kernel")
        assert isinstance(result["dependents"], list)

    def test_build_module_context_quick_analysis_structure(self):
        """Quick analysis should have is_core, is_leaf, is_hub, recommendation"""
        result = self.builder.build_module_context("k0.kernel")
        quick_analysis = result["quick_analysis"]

        assert "is_core" in quick_analysis
        assert "is_leaf" in quick_analysis
        assert "is_hub" in quick_analysis
        assert "recommendation" in quick_analysis
        assert isinstance(quick_analysis["recommendation"], str)

    def test_build_module_context_risk_level_valid(self) -> None:
        """Risk level should be one of: LOW, MEDIUM, HIGH, UNKNOWN"""
        result = self.builder.build_module_context("k0.kernel")
        assert result["risk_level"] in [
            "LOW",
            "MEDIUM",
            "HIGH",
            "UNKNOWN",
            "low",
            "medium",
            "high",
            "unknown",
        ]

    def test_build_module_context_related_adrs_is_list(self):
        """Related ADRs should be a list"""
        result = self.builder.build_module_context("k0.kernel")
        assert isinstance(result["related_adrs"], list)

    def test_build_module_context_performance_under_100ms(self):
        """Module context should complete within 100ms"""
        start = time.time()
        result = self.builder.build_module_context("k0.kernel")
        elapsed_ms = (time.time() - start) * 1000

        assert elapsed_ms < 100
        assert result["context_time_ms"] < 100


class TestAIContextBuilderRefactorContext:
    """Test AIContextBuilder.build_refactor_context()"""

    def setup_method(self):
        """Setup before each test"""
        self.builder = AIContextBuilder()

    def test_build_refactor_context_returns_dict(self):
        """Refactor context should return dict with all required fields"""
        result = self.builder.build_refactor_context("k0.kernel", "k0.core")

        assert isinstance(result, dict)
        assert "old_module" in result
        assert "new_module" in result
        assert "affected_modules" in result
        assert "affected_tests" in result
        assert "breaking_changes" in result
        assert "migration_steps" in result
        assert "risk_level" in result
        assert "recommendations" in result
        assert "estimated_effort_days" in result
        assert "context_time_ms" in result

    def test_build_refactor_context_modules_preserved(self):
        """Old and new module names should be preserved"""
        result = self.builder.build_refactor_context("k0.old_module", "k0.new_module")
        assert result["old_module"] == "k0.old_module"
        assert result["new_module"] == "k0.new_module"

    def test_build_refactor_context_affected_modules_is_list(self):
        """Affected modules should be a list"""
        result = self.builder.build_refactor_context("k0.kernel", "k0.core")
        assert isinstance(result["affected_modules"], list)

    def test_build_refactor_context_migration_steps_provided(self):
        """Migration steps should be actionable"""
        result = self.builder.build_refactor_context("k0.kernel", "k0.core")
        assert isinstance(result["migration_steps"], list)
        assert len(result["migration_steps"]) >= 5  # At least 5 steps

    def test_build_refactor_context_all_steps_are_strings(self):
        """All migration steps should be strings"""
        result = self.builder.build_refactor_context("k0.kernel", "k0.core")
        assert all(isinstance(step, str) for step in result["migration_steps"])

    def test_build_refactor_context_effort_estimate_positive(self):
        """Effort estimate should be positive number of days"""
        result = self.builder.build_refactor_context("k0.kernel", "k0.core")
        assert isinstance(result["estimated_effort_days"], int)
        assert result["estimated_effort_days"] > 0

    def test_build_refactor_context_risk_level_valid(self):
        """Risk level should be valid"""
        result = self.builder.build_refactor_context("k0.kernel", "k0.core")
        assert result["risk_level"] in ["LOW", "MEDIUM", "HIGH", "UNKNOWN"]

    def test_build_refactor_context_recommendations_is_list(self):
        """Recommendations should be a list"""
        result = self.builder.build_refactor_context("k0.kernel", "k0.core")
        assert isinstance(result["recommendations"], list)

    def test_build_refactor_context_performance_under_100ms(self):
        """Refactor context should complete within 100ms"""
        start = time.time()
        result = self.builder.build_refactor_context("k0.kernel", "k0.core")
        elapsed_ms = (time.time() - start) * 1000

        assert elapsed_ms < 100
        assert result["context_time_ms"] < 100


class TestKgAskRouting:
    """Test kg_ask() natural language query routing"""

    def test_kg_ask_feature_implementation_routing(self):
        """'how do I implement X?' should route to feature_context"""
        result = kg_ask("how do I implement agent health monitoring?")

        assert isinstance(result, dict)
        assert "query" in result
        assert "query_type" in result
        assert "result" in result
        assert "response_time_ms" in result

        query_type = result["query_type"]
        assert "feature_context" in query_type.lower()

    def test_kg_ask_adr_implementation_routing(self):
        """'what implements ADR-XXXX?' should route to implementation_chain"""
        result = kg_ask("what implements ADR-0051?")

        assert isinstance(result, dict)
        assert "query_type" in result
        assert "adr_id" in result
        assert result["adr_id"] == "adr_0051"

        query_type = result["query_type"]
        assert "implementation_chain" in query_type.lower()

    def test_kg_ask_dependency_impact_routing(self):
        """'what breaks if I modify X?' should route to dependency_impact"""
        result = kg_ask("what breaks if I modify agent_scheduler?")

        assert isinstance(result, dict)
        assert "query_type" in result
        assert "module" in result

        query_type = result["query_type"]
        assert "dependency_impact" in query_type.lower()

    def test_kg_ask_module_info_routing(self):
        """'tell me about module X' should route to module_context"""
        result = kg_ask("tell me about k0.kernel")

        assert isinstance(result, dict)
        assert "query_type" in result
        assert "module" in result

        query_type = result["query_type"]
        assert "module_context" in query_type.lower()

    def test_kg_ask_refactor_routing(self):
        """'how do I refactor X to Y?' should route to refactor_context"""
        result = kg_ask("how do I refactor kernel to executor?")

        assert isinstance(result, dict)
        assert "query_type" in result
        assert "old_module" in result
        assert "new_module" in result

        query_type = result["query_type"]
        assert "refactor_context" in query_type.lower()

    def test_kg_ask_error_fix_routing(self):
        """'how do I fix error X?' should route to error_context"""
        result = kg_ask("how do I fix circular_dependency?")

        assert isinstance(result, dict)
        assert "query_type" in result
        assert "error_type" in result

        query_type = result["query_type"]
        assert "error_context" in query_type.lower()

    def test_kg_ask_generic_feature_routing(self):
        """Unknown query should default to feature_context"""
        result = kg_ask("some random text that doesn't match patterns")

        assert isinstance(result, dict)
        assert "query_type" in result
        assert "default" in result["query_type"].lower()

    def test_kg_ask_response_time_tracked(self):
        """Response time should be tracked"""
        result = kg_ask("how do I add monitoring?")
        assert "response_time_ms" in result
        assert isinstance(result["response_time_ms"], (int, float))
        assert result["response_time_ms"] >= 0

    def test_kg_ask_performance_under_150ms(self):
        """kg_ask should complete within 150ms"""
        start = time.time()
        result = kg_ask("how do I add new feature?")
        elapsed_ms = (time.time() - start) * 1000

        assert elapsed_ms < 150
        assert result["response_time_ms"] < 150

    def test_kg_ask_query_preserved_in_result(self):
        """Original query should be preserved in result"""
        query = "what implements ADR-0001?"
        result = kg_ask(query)
        assert result["query"] == query


class TestKgAskADRExtraction:
    """Test kg_ask() ADR ID extraction from natural language"""

    def test_adr_extraction_format_adr_0051(self):
        """Should extract ADR ID 'adr_0051' from 'ADR-0051'"""
        result = kg_ask("what implements ADR-0051?")
        assert result["adr_id"] == "adr_0051"

    def test_adr_extraction_format_adr_underscore(self):
        """Should extract ADR ID from 'ADR_0001' format"""
        result = kg_ask("what implements ADR_0001?")
        assert result["adr_id"] == "adr_0001"

    def test_adr_extraction_lowercase(self):
        """Should handle lowercase 'adr' in query"""
        result = kg_ask("what implements adr-0042?")
        assert result["adr_id"] == "adr_0042"

    def test_adr_extraction_uppercase(self):
        """Should handle uppercase 'ADR' in query"""
        result = kg_ask("WHAT IMPLEMENTS ADR-0050?")
        assert result["adr_id"] == "adr_0050"


class TestKgAskModuleExtraction:
    """Test kg_ask() module name extraction from natural language"""

    def test_module_extraction_from_modify(self):
        """Should extract module from 'modify X'"""
        result = kg_ask("what breaks if I modify agent_scheduler?")
        assert result["module"] == "agent_scheduler"

    def test_module_extraction_from_change(self):
        """Should extract module from 'change X'"""
        result = kg_ask("what breaks if I change k0.kernel?")
        assert result["module"] == "k0.kernel"

    def test_module_extraction_from_tell_about(self):
        """Should extract module from 'tell me about X'"""
        result = kg_ask("tell me about k1.l2_orchestration.scheduler")
        assert result["module"] == "k1.l2_orchestration.scheduler"

    def test_module_extraction_from_what_is(self):
        """Should extract module from 'what is X?'"""
        result = kg_ask("what is k0.bus?")
        assert result["module"] == "k0.bus"


class TestIntegration:
    """Integration tests for Phase 4 components"""

    def test_builder_and_kg_ask_consistency(self):
        """Both builder methods and kg_ask should return similar structures"""
        builder = AIContextBuilder()

        # Build feature context directly
        direct_result = builder.build_feature_context("agent scheduling")

        # Get through kg_ask
        ask_result = kg_ask("how do I implement agent scheduling?")
        ask_feature_result = ask_result.get("result", {})

        # Both should have similar fields
        assert "suggested_layer" in direct_result
        assert "suggested_layer" in ask_feature_result

    def test_all_tools_accessible(self):
        """All Phase 4 tools should be accessible"""
        builder = AIContextBuilder()

        # All methods should be callable
        assert callable(builder.build_feature_context)
        assert callable(builder.build_error_context)
        assert callable(builder.build_module_context)
        assert callable(builder.build_refactor_context)
        assert callable(kg_ask)

    def test_graceful_error_handling(self):
        """Phase 4 tools should handle errors gracefully"""
        builder = AIContextBuilder()

        # Should not raise on non-existent module
        result = builder.build_module_context("non.existent.module")
        assert isinstance(result, dict)
        assert result["module_name"] == "non.existent.module"

        # Should not raise on non-existent error type
        result = builder.build_error_context("completely_unknown_error_type_xyz")
        assert isinstance(result, dict)
        assert "Unknown" in result["diagnosis"]["description"]

    def test_performance_consistency(self):
        """All Phase 4 operations should have consistent performance"""
        builder = AIContextBuilder()

        times = []
        for _ in range(3):
            start = time.time()
            builder.build_feature_context("test")
            elapsed_ms = (time.time() - start) * 1000
            times.append(elapsed_ms)

        # Average should be reasonable
        avg_time = sum(times) / len(times)
        assert avg_time < 150  # Most operations under 150ms


class TestPhase4Documentation:
    """Tests for Phase 4 documentation requirements"""

    def test_kg_ask_has_docstring(self):
        """kg_ask function should have comprehensive docstring"""
        assert kg_ask.__doc__ is not None
        assert len(kg_ask.__doc__) > 100
        assert "Examples" in kg_ask.__doc__ or "example" in kg_ask.__doc__.lower()

    def test_ai_context_builder_has_docstring(self):
        """AIContextBuilder class should have comprehensive docstring"""
        assert AIContextBuilder.__doc__ is not None
        assert len(AIContextBuilder.__doc__) > 100

    def test_builder_methods_have_docstrings(self):
        """All builder methods should have docstrings"""
        builder = AIContextBuilder()

        assert builder.build_feature_context.__doc__ is not None
        assert builder.build_error_context.__doc__ is not None
        assert builder.build_module_context.__doc__ is not None
        assert builder.build_refactor_context.__doc__ is not None

    def test_builder_method_docstrings_include_returns(self):
        """Builder method docstrings should document returns"""
        builder = AIContextBuilder()

        assert "Returns" in builder.build_feature_context.__doc__
        assert "Returns" in builder.build_error_context.__doc__
        assert "Returns" in builder.build_module_context.__doc__
        assert "Returns" in builder.build_refactor_context.__doc__


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
