"""
Tests for the canned tool registry.

Validates:
  - Tool registration and lookup
  - Deterministic canned responses
  - Flaky API sequence behavior
  - Tool declaration format
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from tools.canned_registry import CannedToolRegistry


@pytest.fixture
def registry():
    r = CannedToolRegistry()
    r.reset()
    return r


class TestCannedToolRegistry:

    def test_tool_names(self, registry):
        names = registry.get_tool_names()
        assert "web_search" in names
        assert "flight_search" in names
        assert "final_answer" in names
        assert "spawn_agent" in names
        assert len(names) >= 13

    def test_declarations_format(self, registry):
        decls = registry.get_tool_declarations()
        for d in decls:
            assert "name" in d
            assert "description" in d
            assert "parameters" in d
            assert d["parameters"]["type"] == "object"

    @pytest.mark.asyncio
    async def test_web_search(self, registry):
        result = await registry.execute("web_search", {"query": "quantum computing"})
        assert result.ok
        assert "results" in result.output
        assert len(result.output["results"]) > 0

    @pytest.mark.asyncio
    async def test_weather_api(self, registry):
        result = await registry.execute("weather_api", {"city": "Paris"})
        assert result.ok
        assert result.output["city"] == "Paris"
        assert result.output["temp_c"] == 22

    @pytest.mark.asyncio
    async def test_flight_search(self, registry):
        result = await registry.execute(
            "flight_search", {"from_city": "San Francisco", "to_city": "New York"}
        )
        assert result.ok
        assert result.output["count"] >= 2

    @pytest.mark.asyncio
    async def test_hotel_search(self, registry):
        result = await registry.execute("hotel_search", {"city": "Tokyo"})
        assert result.ok
        assert result.output["count"] >= 1

    @pytest.mark.asyncio
    async def test_calculate(self, registry):
        result = await registry.execute("calculate", {"expression": "2 + 3"})
        assert result.ok
        assert result.output["result"] == 5

    @pytest.mark.asyncio
    async def test_database_query(self, registry):
        result = await registry.execute("database_query", {"query": "user_preferences"})
        assert result.ok
        assert "preferred_airline" in result.output["data"]

    @pytest.mark.asyncio
    async def test_unknown_tool(self, registry):
        result = await registry.execute("nonexistent_tool", {})
        assert not result.ok
        assert result.error_code == "TOOL_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_final_answer(self, registry):
        result = await registry.execute("final_answer", {"answer": "42", "confidence": 0.9})
        assert result.ok
        assert result.output["answer"] == "42"

    @pytest.mark.asyncio
    async def test_flaky_api_fails_then_succeeds(self, registry):
        # First call: should fail
        r1 = await registry.execute("flaky_api", {"endpoint": "premium_flight_search"})
        assert not r1.ok
        assert r1.error_code == "RATE_LIMITED"

        # Second call: should also fail
        r2 = await registry.execute("flaky_api", {"endpoint": "premium_flight_search"})
        assert not r2.ok

        # Third call: should succeed
        r3 = await registry.execute("flaky_api", {"endpoint": "premium_flight_search"})
        assert r3.ok

    @pytest.mark.asyncio
    async def test_deterministic_responses(self, registry):
        """Same inputs should always produce same outputs."""
        r1 = await registry.execute("weather_api", {"city": "Paris"})
        r2 = await registry.execute("weather_api", {"city": "Paris"})
        assert r1.output == r2.output

    @pytest.mark.asyncio
    async def test_spawn_agent_returns_placeholder(self, registry):
        result = await registry.execute("spawn_agent", {"task": "Research AI", "tool_budget": 3})
        assert result.ok
        assert result.output["action"] == "spawn_agent"
        assert result.output["status"] == "pending"


class TestLargePayloadTools:
    """Tests for the large-payload tools that return 2,000-5,000 token outputs."""

    @pytest.mark.asyncio
    async def test_search_database_large_customer_history(self, registry):
        result = await registry.execute("search_database_large", {"dataset": "customer_history"})
        assert result.ok
        assert result.output["record_count"] == 200
        assert len(result.output["customers"]) == 200
        # Verify payload is genuinely large
        import json

        raw = json.dumps(result.output)
        token_estimate = len(raw) // 4
        assert token_estimate > 2000, f"Expected >2000 tokens, got {token_estimate}"

    @pytest.mark.asyncio
    async def test_analytics_report(self, registry):
        result = await registry.execute(
            "analytics_report",
            {"report_type": "purchase_analytics", "period": "last_12_months"},
        )
        assert result.ok
        assert "segments" in result.output
        assert len(result.output["segments"]) == 10
        assert "monthly_trends" in result.output
        assert len(result.output["monthly_trends"]) == 12
        import json

        raw = json.dumps(result.output)
        token_estimate = len(raw) // 4
        assert token_estimate > 2000, f"Expected >2000 tokens, got {token_estimate}"

    @pytest.mark.asyncio
    async def test_vector_search(self, registry):
        result = await registry.execute(
            "vector_search", {"query_text": "machine learning deployment"}
        )
        assert result.ok
        assert result.output["total_results"] == 100
        assert len(result.output["results"]) == 100
        import json

        raw = json.dumps(result.output)
        token_estimate = len(raw) // 4
        assert token_estimate > 2000, f"Expected >2000 tokens, got {token_estimate}"

    @pytest.mark.asyncio
    async def test_vector_search_top_k(self, registry):
        result = await registry.execute(
            "vector_search", {"query_text": "deep learning", "top_k": 10}
        )
        assert result.ok
        assert result.output["total_results"] == 10
        assert len(result.output["results"]) == 10
