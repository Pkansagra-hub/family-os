"""
Light integration tests to verify specialists use ToolCallHandler and route
to the mock MCP consistently, without requiring a live server.

We patch ToolCallHandler._post_to_mock_server to return deterministic payloads
shaped like the mock MCP response, and stub LLM responses to focus on the tool
call paths and agent context assembly.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _mock_mcp_response(tool_id: str, payload: dict):
    """Return a mock MCP-like response for a given tool_id."""
    if tool_id == "get_financial_context":
        # Provide a rich 'context' and also a 'data' path with goals for coverage
        return {
            "status": "success",
            "tool": "Get Financial Context",
            "tool_id": tool_id,
            "timestamp": "2025-11-06T00:00:00Z",
            "result": {
                "context": {
                    "budget": {
                        "total_monthly_budget": 2000.0,
                        "spent_to_date": 1200.0,
                        "categories": {
                            "groceries": {"budget": 500, "spent": 250},
                            "dining": {"budget": 300, "spent": 200},
                        },
                    },
                    "recent_transactions": [
                        {
                            "date": "2025-11-05",
                            "merchant": "Store A",
                            "amount": 25.0,
                            "category": "groceries",
                        },
                        {
                            "date": "2025-11-04",
                            "merchant": "Cafe B",
                            "amount": 15.0,
                            "category": "dining",
                        },
                    ],
                    "insights": {"overspending_categories": ["dining"]},
                },
                "data": {  # Adapter path: ensure _get_savings_goals can see this
                    "goals": [{"goal_id": "goal_emergency_fund", "current": 6500, "target": 10000}],
                },
            },
        }
    if tool_id == "get_user_preferences":
        category = (payload or {}).get("parameters", {}).get("preference_category")
        prefs = {}
        if category == "finance":
            prefs = {
                "finance": {
                    "alert_thresholds": {"budget_warning": 0.8, "large_transaction": 200},
                    "preferred_categories": ["groceries", "dining"],
                }
            }
        elif category == "health":
            prefs = {"health": {"exercise_goals": {"steps_per_day": 8000, "workouts_per_week": 3}}}
        return {
            "status": "success",
            "tool": "Get User Preferences",
            "tool_id": tool_id,
            "timestamp": "2025-11-06T00:00:00Z",
            "result": {"preferences": prefs},
        }
    if tool_id == "get_health_context":
        return {
            "status": "success",
            "tool": "Get Health Context",
            "tool_id": tool_id,
            "timestamp": "2025-11-06T00:00:00Z",
            "result": {
                # Adapter shape: list of metric nodes
                "data": [
                    {
                        "node_id": "node_health_1",
                        "node_type": "HealthMetric",
                        "person_id": "user_123",
                        "properties": {
                            "date": "2025-11-05",
                            "metric": "knee_strength",
                            "value": 70,
                        },
                    }
                ]
            },
        }
    if tool_id == "web_search":
        return {
            "status": "success",
            "tool": "Web Search",
            "tool_id": tool_id,
            "timestamp": "2025-11-06T00:00:00Z",
            "result": {
                "query": (payload or {}).get("parameters", {}).get("query", ""),
                "results": [
                    {"title": "Result 1", "snippet": "Snippet 1", "url": "https://example.com/1"},
                    {"title": "Result 2", "snippet": "Snippet 2", "url": "https://example.com/2"},
                ],
            },
        }
    # Default guard
    return {"status": "success", "tool_id": tool_id, "result": {}}


@pytest.mark.asyncio
async def test_finance_agent_tool_calls_are_routed():
    from l3_execution.agents.specialists.finance_agent import FinanceAgent

    mock_groq = MagicMock()
    agent = FinanceAgent("finance_t", "session_t", mock_groq)

    # Stub LLM to avoid external dependency
    with patch.object(agent, "call_llm", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = {"content": "Finance insights"}

        # Patch ToolCallHandler post method
        with patch(
            "l5_infrastructure.tool_call_handler.ToolCallHandler._post_to_mock_server",
            new_callable=AsyncMock,
        ) as mock_post:
            mock_post.side_effect = lambda endpoint, request_data: _mock_mcp_response(
                request_data.get("tool_id"), {"parameters": request_data.get("parameters", {})}
            )

            msg = {
                "type": "specialist_task",
                "payload": {
                    "user_query": "spending this month",
                    "user_id": "user_123",
                    "task_id": "t1",
                },
            }
            result = await agent.process_message(msg)

            # Ensure response formed and mock was hit at least once
            assert result["status"] == "success"
            assert mock_post.await_count >= 1

            # Spot-check normalized budget context
            # The agent passes context to LLM; we can verify the constructed context via call args
            called_ctx = mock_llm.call_args.kwargs["context_data"]
            assert called_ctx["budget_limits"]["monthly_budget"] == 2000.0
            assert any(c["name"] == "groceries" for c in called_ctx["budget_limits"]["categories"])


@pytest.mark.asyncio
async def test_healthcare_agent_tool_calls_are_routed():
    from l3_execution.agents.specialists.healthcare_agent import HealthcareAgent

    mock_groq = MagicMock()
    agent = HealthcareAgent("health_t", "session_t", mock_groq)

    with patch.object(agent, "call_llm", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = {"content": "Health insights"}

        with patch(
            "l5_infrastructure.tool_call_handler.ToolCallHandler._post_to_mock_server",
            new_callable=AsyncMock,
        ) as mock_post:
            mock_post.side_effect = lambda endpoint, request_data: _mock_mcp_response(
                request_data.get("tool_id"), {"parameters": request_data.get("parameters", {})}
            )

            msg = {
                "type": "specialist_task",
                "payload": {
                    "user_query": "How's my recovery?",
                    "user_id": "user_123",
                    "task_id": "t2",
                },
            }
            result = await agent.process_message(msg)

            assert result["status"] == "success"
            assert mock_post.await_count >= 1

            # Context built from adapter-style health metrics
            called_ctx = mock_llm.call_args.kwargs["context_data"]
            assert "health_context" in called_ctx
            assert isinstance(called_ctx["health_context"].get("recent_metrics", []), list)


@pytest.mark.asyncio
async def test_researcher_agent_tool_calls_are_routed():
    from l3_execution.agents.specialists.researcher_agent import ResearcherAgent

    mock_groq = MagicMock()
    agent = ResearcherAgent("research_t", "session_t", mock_groq)

    with patch.object(agent, "call_llm", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = {"content": "Research insights"}

        with patch(
            "l5_infrastructure.tool_call_handler.ToolCallHandler._post_to_mock_server",
            new_callable=AsyncMock,
        ) as mock_post:
            mock_post.side_effect = lambda endpoint, request_data: _mock_mcp_response(
                request_data.get("tool_id"), {"parameters": request_data.get("parameters", {})}
            )

            msg = {
                "type": "specialist_task",
                "payload": {
                    "user_query": "Italian restaurants nearby",
                    "user_id": "user_123",
                    "task_id": "t3",
                },
            }
            result = await agent.process_message(msg)

            assert result["status"] == "success"
            assert mock_post.await_count >= 1

            # Ensure search results were injected into context given to LLM
            called_ctx = mock_llm.call_args.kwargs["context_data"]
            assert "search_results" in called_ctx
            assert called_ctx["search_results"].get("results")
