"""
Integration test: Concierge → Specialist (Finance) spawn path routes via ToolCallHandler.

We patch ToolCallHandler._post_to_mock_server globally to avoid network and to
assert that finance-related tools are called by the spawned specialist.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
async def test_concierge_to_finance_tool_routing(monkeypatch):
    # Late imports to respect test discovery
    from l3_execution.agents.concierge_agent import ConciergeAgent
    from l3_execution.agents.specialists.finance_agent import FinanceAgent

    # Track tool calls
    calls = []

    async def _fake_post(self, endpoint: str, request_data: dict):
        # Record call
        calls.append(
            {
                "endpoint": endpoint,
                "tool_id": request_data.get("tool_id"),
                "parameters": request_data.get("parameters"),
            }
        )
        tool_id = request_data.get("tool_id")

        if tool_id == "query_k0_finance":
            return {
                "status": "success",
                "tool": "Query K0 Finance",
                "tool_id": tool_id,
                "timestamp": "2025-11-06T00:00:00Z",
                "result": {
                    "status": "success",
                    "user_id": request_data["parameters"].get("user_id"),
                    "query": request_data["parameters"].get("query"),
                    "transaction_count": 12,
                    "current_month_total": 1200.00,
                    "budget_utilization": 0.80,
                    "category_spending": [
                        {"category": "groceries", "amount": 400.0},
                        {"category": "dining", "amount": 300.0},
                    ],
                    "recent_transactions": [],
                },
            }
        if tool_id == "get_financial_context":
            return {
                "status": "success",
                "tool": "Get Financial Context",
                "tool_id": tool_id,
                "timestamp": "2025-11-06T00:00:00Z",
                "result": {
                    "status": "success",
                    "user_id": request_data["parameters"].get("user_id"),
                    "time_range": request_data["parameters"].get("time_range", "current_month"),
                    "context": {
                        "budget": {
                            "total_monthly_budget": 1500.0,
                            "spent_to_date": 1200.0,
                            "remaining": 300.0,
                            "categories": {
                                "groceries": {"budget": 400, "spent": 400.0, "remaining": 0.0},
                                "dining": {"budget": 300, "spent": 300.0, "remaining": 0.0},
                            },
                        },
                        "recent_transactions": [],
                        "insights": {},
                    },
                },
            }
        if tool_id == "get_user_preferences":
            return {
                "status": "success",
                "tool": "Get User Preferences",
                "tool_id": tool_id,
                "timestamp": "2025-11-06T00:00:00Z",
                "result": {
                    "status": "success",
                    "user_id": request_data["parameters"].get("user_id"),
                    "category": "finance",
                    "preferences": {
                        "finance": {
                            "currency": "USD",
                            "budget_alerts": True,
                            "spending_categories": ["groceries", "dining"],
                            "savings_goals": {"monthly_target": 500.0},
                        }
                    },
                },
            }

        # Default minimal success
        return {"status": "success", "tool_id": tool_id, "result": {}}

    # Patch the post method globally
    monkeypatch.setattr(
        "l5_infrastructure.tool_call_handler.ToolCallHandler._post_to_mock_server",
        _fake_post,
        raising=True,
    )

    # Mock Groq client with deterministic response
    mock_groq = MagicMock()
    mock_groq.complete = AsyncMock(return_value={"content": "stub", "tokens_used": 10})

    # Build Concierge with a stub AgentFactory that returns a FinanceAgent
    concierge = ConciergeAgent(
        agent_id="concierge_test",
        session_id="session_test",
        groq_client=mock_groq,
        agent_factory=None,
    )

    class StubFactory:
        async def spawn_agent(self, agent_type, task_envelope, session_id, trace_id):
            # Return a FinanceAgent and adapt the envelope to its expected input
            agent = FinanceAgent("finance_spawned", session_id, mock_groq)

            class Proxy:
                def __init__(self, inner):
                    self.agent_id = inner.agent_id
                    self._inner = inner

                async def process_message(self, message):
                    # Adapt concierge envelope to FinanceAgent message format
                    adapted = {
                        "type": "specialist_task",
                        "payload": {
                            "user_query": message.get(
                                "user_input", "What's my spending this month?"
                            ),
                            "user_id": "user_123",
                            "task_id": message.get("task_id", "task_finance"),
                        },
                    }
                    finance_result = await self._inner.process_message(adapted)
                    # Adapt FinanceAgent response to Concierge expected shape
                    return {
                        "status": finance_result.get("status", "success"),
                        "content": finance_result.get("response", ""),
                        "tokens_used": finance_result.get("tokens_used", 0),
                    }

            return Proxy(agent)

    concierge.agent_factory = StubFactory()

    # Now route to specialist via factory
    resp = await concierge._route_to_specialist("What's my spending this month?", "finance")

    # Validate response shape
    assert resp["status"] == "success"
    assert resp["specialist_type"] == "finance"

    # Ensure ToolCallHandler was used for both finance tools
    called_ids = [c["tool_id"] for c in calls]
    assert "get_financial_context" in called_ids
    assert "get_user_preferences" in called_ids
    assert "query_k0_finance" in called_ids
