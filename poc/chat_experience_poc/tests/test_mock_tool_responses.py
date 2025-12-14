"""
Test Mock Tool Response Coverage

Validates that all tools in tool_registry.json have working mock response generators.
This ensures Phase 1 (Mock Response Patterns) is complete.

Run:
    pytest tests/test_mock_tool_responses.py -v
"""

import pytest
from mock_services.mock_tool_responses import (
    generate_mock_response,
    list_available_tools,
    validate_mock_response_coverage,
)


def test_all_tools_have_mock_responses():
    """Verify all tools in registry have mock response generators."""
    coverage = validate_mock_response_coverage("config/tool_registry.json")

    print(f"\n✅ Mock Response Coverage: {coverage['coverage_percentage']:.1f}%")
    print(f"   Total tools in registry: {coverage['total_tools_in_registry']}")
    print(f"   Total mock generators: {coverage['total_mock_generators']}")

    if coverage["missing_generators"]:
        print(f"\n❌ Missing generators for: {coverage['missing_generators']}")

    if coverage["extra_generators"]:
        print(f"\n⚠️ Extra generators (not in registry): {coverage['extra_generators']}")

    assert (
        coverage["coverage_percentage"] == 100.0
    ), f"Incomplete mock coverage: {coverage['missing_generators']} missing generators"


@pytest.mark.parametrize(
    "tool_id,parameters",
    [
        ("web_search", {"query": "Python tutorials", "num_results": 3}),
        ("get_health_context", {"user_id": "user_123", "query_type": "all"}),
        ("get_financial_context", {"user_id": "user_123", "time_range": "current_month"}),
        (
            "create_reminder",
            {
                "user_id": "user_123",
                "message": "PT session tomorrow",
                "fire_time": "2025-11-07T10:00:00Z",
                "recurrence": "once",
            },
        ),
        (
            "book_appointment",
            {
                "appointment_type": "pt_session",
                "date_time": "2025-11-10T15:00:00Z",
                "provider": "Dr. Johnson",
            },
        ),
        ("calculate", {"expression": "2 + 2 * 3"}),
        ("get_user_preferences", {"user_id": "user_123", "preference_category": "all"}),
        (
            "query_conversation_history",
            {
                "user_id": "user_123",
                "query": "health discussions",
                "limit": 5,
            },
        ),
    ],
)
def test_mock_response_generation(tool_id, parameters):
    """Test that each tool generates valid mock responses."""
    response = generate_mock_response(
        tool_id=tool_id,
        parameters=parameters,
        trace_id="test_trace_123",
    )

    # All responses should be dicts
    assert isinstance(response, dict), f"{tool_id} should return dict"

    # All responses should have status field
    assert "status" in response, f"{tool_id} response missing 'status' field"

    # Response should not be empty
    assert len(response) > 1, f"{tool_id} response too minimal"

    print(f"\n✅ {tool_id}: {len(response)} fields in response")


def test_web_search_response_structure():
    """Validate web_search response has correct structure."""
    response = generate_mock_response(
        "web_search",
        {"query": "test query", "num_results": 3},
    )

    assert response["status"] == "success"
    assert "results" in response
    assert isinstance(response["results"], list)
    assert len(response["results"]) == 3

    # Validate result structure
    for result in response["results"]:
        assert "title" in result
        assert "url" in result
        assert "snippet" in result
        assert "relevance_score" in result


def test_health_context_response_structure():
    """Validate get_health_context response has correct structure."""
    response = generate_mock_response(
        "get_health_context",
        {"user_id": "test_user", "query_type": "all"},
    )

    assert response["status"] == "success"
    assert "context" in response
    assert "pt_sessions" in response["context"]
    assert "medications" in response["context"]
    assert "symptoms" in response["context"]


def test_financial_context_response_structure():
    """Validate get_financial_context response has correct structure."""
    response = generate_mock_response(
        "get_financial_context",
        {"user_id": "test_user", "time_range": "current_month"},
    )

    assert response["status"] == "success"
    assert "context" in response
    assert "budget" in response["context"]
    assert "recent_transactions" in response["context"]
    assert "insights" in response["context"]


def test_reminder_creation_response():
    """Validate create_reminder response."""
    response = generate_mock_response(
        "create_reminder",
        {
            "message": "Test reminder",
            "fire_time": "2025-11-07T10:00:00Z",
            "recurrence": "once",
        },
    )

    assert response["status"] == "created"
    assert "trigger_id" in response
    assert "reminder" in response
    assert response["reminder"]["message"] == "Test reminder"


def test_appointment_booking_response():
    """Validate book_appointment response."""
    response = generate_mock_response(
        "book_appointment",
        {
            "appointment_type": "pt_session",
            "date_time": "2025-11-10T15:00:00Z",
        },
    )

    assert response["status"] == "confirmed"
    assert "appointment_id" in response
    assert "appointment" in response
    assert "confirmation_code" in response["appointment"]


def test_calculation_response():
    """Validate calculate response."""
    response = generate_mock_response(
        "calculate",
        {"expression": "10 + 5 * 2"},
    )

    assert response["status"] == "success"
    assert response["result"] == 20  # Correct order of operations


def test_user_preferences_response():
    """Validate get_user_preferences response."""
    response = generate_mock_response(
        "get_user_preferences",
        {"user_id": "test_user", "preference_category": "health"},
    )

    assert response["status"] == "success"
    assert "preferences" in response
    assert "health" in response["preferences"]


def test_conversation_history_response():
    """Validate query_conversation_history response."""
    response = generate_mock_response(
        "query_conversation_history",
        {"user_id": "test_user", "query": "health", "limit": 3},
    )

    assert response["status"] == "success"
    assert "excerpts" in response
    assert isinstance(response["excerpts"], list)
    assert len(response["excerpts"]) <= 3


def test_deterministic_responses():
    """Verify mock responses are deterministic (same input = same output)."""
    params = {"query": "test query", "num_results": 5}

    response1 = generate_mock_response("web_search", params)
    response2 = generate_mock_response("web_search", params)

    assert response1["results"][0]["title"] == response2["results"][0]["title"]
    assert response1["results"][0]["url"] == response2["results"][0]["url"]


def test_invalid_tool_id():
    """Verify appropriate error for unknown tool."""
    with pytest.raises(ValueError) as exc_info:
        generate_mock_response("nonexistent_tool", {})

    assert "No mock response generator" in str(exc_info.value)


def test_list_available_tools():
    """Verify list of available tools."""
    tools = list_available_tools()

    assert isinstance(tools, list)
    assert len(tools) == 9  # Should match number of generators (updated with query_k0_finance)
    assert "web_search" in tools
    assert "get_health_context" in tools
    assert "query_k0_finance" in tools


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
