"""
Tests for Specialist Agents: Healthcare, Finance, Researcher.

Tests:
  - HealthcareAgent: Health query processing
  - FinanceAgent: Budget analysis and expense tracking
  - ResearcherAgent: Information lookup and web search

All tests use mock LLM responses and verify:
  - User KG queries are made
  - MCP tools are called correctly
  - LLM synthesis uses correct temperature
  - Response format is correct
  - SessionState updates logged

References:
  - Epic 4.3 - Specialist agents implementation
  - docs/whiteboard/chat_experience.md - Specialist patterns
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ===============================
# HealthcareAgent Tests
# ===============================


@pytest.mark.asyncio
async def test_healthcare_agent_process_message():
    """Test HealthcareAgent processes health query correctly."""
    from l3_execution.agents.specialists.healthcare_agent import HealthcareAgent

    # Mock Groq client
    mock_groq = MagicMock()

    # Create agent
    agent = HealthcareAgent(
        agent_id="healthcare_001",
        session_id="session_test",
        groq_client=mock_groq,
    )

    # Mock LLM response
    mock_llm_response = {
        "content": "Your recovery is on track! You've completed 6/8 PT sessions. Knee strength improved 40%."
    }

    with patch.object(agent, "call_llm", new_callable=AsyncMock) as mock_call_llm:
        mock_call_llm.return_value = mock_llm_response

        # Test message
        message = {
            "type": "specialist_task",
            "payload": {
                "user_query": "How's my recovery?",
                "user_id": "user_123",
                "task_id": "task_456",
            },
        }

        # Process message
        result = await agent.process_message(message)

        # Verify response structure
        assert result["status"] == "success"
        assert result["specialist"] == "healthcare"
        assert result["task_id"] == "task_456"
        assert "recovery is on track" in result["response"]

        # Verify LLM was called
        mock_call_llm.assert_called_once()
        call_args = mock_call_llm.call_args

        # Verify temperature
        assert call_args.kwargs["temperature"] == 0.7

        # Verify context includes health data
        context = call_args.kwargs["context_data"]
        assert "health_context" in context
        assert "health_goals" in context
        assert "pt_routines" in context
        assert "k0_health_data" in context

        # Verify context_used metrics
        assert "health_metrics" in result["context_used"]
        assert "goals" in result["context_used"]
        assert "pt_sessions" in result["context_used"]


@pytest.mark.asyncio
async def test_healthcare_agent_user_kg_queries():
    """Test HealthcareAgent queries User KG correctly."""
    from l3_execution.agents.specialists.healthcare_agent import HealthcareAgent

    mock_groq = MagicMock()
    agent = HealthcareAgent(
        agent_id="healthcare_002",
        session_id="session_test",
        groq_client=mock_groq,
    )

    # Test health context query
    health_context = await agent._get_health_context("user_123")
    assert "recent_metrics" in health_context
    assert len(health_context["recent_metrics"]) > 0
    assert health_context["recent_metrics"][0]["metric"] == "knee_strength"

    # Test health goals query
    health_goals = await agent._get_health_goals("user_123")
    assert len(health_goals) > 0
    assert "goal_id" in health_goals[0]
    assert "progress" in health_goals[0]

    # Test PT routines query
    pt_routines = await agent._get_pt_routines("user_123")
    assert "current_routine" in pt_routines
    assert "exercises" in pt_routines
    assert "next_session" in pt_routines


@pytest.mark.asyncio
async def test_healthcare_agent_mcp_tool():
    """Test HealthcareAgent calls query_k0_health MCP tool."""
    from l3_execution.agents.specialists.healthcare_agent import HealthcareAgent

    mock_groq = MagicMock()
    agent = HealthcareAgent(
        agent_id="healthcare_003",
        session_id="session_test",
        groq_client=mock_groq,
    )

    # Test K0 health query
    k0_data = await agent._query_k0_health("user_123", "recovery progress")
    assert "session_count" in k0_data
    assert "recent_sessions" in k0_data
    assert "improvement_metrics" in k0_data
    assert k0_data["session_count"] == 6


# ===============================
# FinanceAgent Tests
# ===============================


@pytest.mark.asyncio
async def test_finance_agent_process_message():
    """Test FinanceAgent processes budget query correctly."""
    from l3_execution.agents.specialists.finance_agent import FinanceAgent

    mock_groq = MagicMock()
    agent = FinanceAgent(
        agent_id="finance_001",
        session_id="session_test",
        groq_client=mock_groq,
    )

    # Mock LLM response
    mock_llm_response = {
        "content": "You've spent $1,200 this month (80% of budget). Groceries: $400, Dining: $300."
    }

    with patch.object(agent, "call_llm", new_callable=AsyncMock) as mock_call_llm:
        mock_call_llm.return_value = mock_llm_response

        message = {
            "type": "specialist_task",
            "payload": {
                "user_query": "What's my spending this month?",
                "user_id": "user_123",
                "task_id": "task_789",
            },
        }

        result = await agent.process_message(message)

        # Verify response
        assert result["status"] == "success"
        assert result["specialist"] == "finance"
        assert result["task_id"] == "task_789"
        assert "spent" in result["response"].lower()

        # Verify LLM called with temperature=0.3 (analytical)
        mock_call_llm.assert_called_once()
        call_args = mock_call_llm.call_args
        assert call_args.kwargs["temperature"] == 0.3

        # Verify context includes financial data
        context = call_args.kwargs["context_data"]
        assert "budget_limits" in context
        assert "savings_goals" in context
        assert "k0_finance_data" in context


@pytest.mark.asyncio
async def test_finance_agent_user_kg_queries():
    """Test FinanceAgent queries User KG correctly."""
    from l3_execution.agents.specialists.finance_agent import FinanceAgent

    mock_groq = MagicMock()
    agent = FinanceAgent(
        agent_id="finance_002",
        session_id="session_test",
        groq_client=mock_groq,
    )

    # Test budget limits query
    budget_limits = await agent._get_budget_limits("user_123")
    assert "monthly_budget" in budget_limits
    assert budget_limits["monthly_budget"] == 1500
    assert "categories" in budget_limits
    assert len(budget_limits["categories"]) > 0

    # Test savings goals query
    savings_goals = await agent._get_savings_goals("user_123")
    assert len(savings_goals) > 0
    assert "goal_id" in savings_goals[0]
    assert "current" in savings_goals[0]
    assert "target" in savings_goals[0]

    # Test financial preferences
    preferences = await agent._get_financial_preferences("user_123")
    assert "alert_thresholds" in preferences
    assert "preferred_categories" in preferences


@pytest.mark.asyncio
async def test_finance_agent_mcp_tool():
    """Test FinanceAgent calls query_k0_finance MCP tool."""
    from l3_execution.agents.specialists.finance_agent import FinanceAgent

    mock_groq = MagicMock()
    agent = FinanceAgent(
        agent_id="finance_003",
        session_id="session_test",
        groq_client=mock_groq,
    )

    # Test K0 finance query
    k0_data = await agent._query_k0_finance("user_123", "spending this month")
    assert "transaction_count" in k0_data
    assert "current_month_total" in k0_data
    assert "category_spending" in k0_data
    assert k0_data["current_month_total"] == 1200
    assert k0_data["budget_utilization"] == 0.80


# ===============================
# ResearcherAgent Tests
# ===============================


@pytest.mark.asyncio
async def test_researcher_agent_process_message():
    """Test ResearcherAgent processes research query correctly."""
    from l3_execution.agents.specialists.researcher_agent import ResearcherAgent

    mock_groq = MagicMock()
    agent = ResearcherAgent(
        agent_id="researcher_001",
        session_id="session_test",
        groq_client=mock_groq,
    )

    # Mock LLM response
    mock_llm_response = {
        "content": "I found some great Italian restaurants! Bella Italia, Luigi's Pizzeria, Trattoria Roma."
    }

    with patch.object(agent, "call_llm", new_callable=AsyncMock) as mock_call_llm:
        mock_call_llm.return_value = mock_llm_response

        message = {
            "type": "specialist_task",
            "payload": {
                "user_query": "What are Italian restaurants nearby?",
                "user_id": "user_123",
                "task_id": "task_101",
            },
        }

        result = await agent.process_message(message)

        # Verify response
        assert result["status"] == "success"
        assert result["specialist"] == "researcher"
        assert result["task_id"] == "task_101"
        assert "Italian" in result["response"]

        # Verify LLM called with temperature=0.5 (balanced)
        mock_call_llm.assert_called_once()
        call_args = mock_call_llm.call_args
        assert call_args.kwargs["temperature"] == 0.5

        # Verify context includes search results
        context = call_args.kwargs["context_data"]
        assert "search_results" in context
        assert "user_location" in context


@pytest.mark.asyncio
async def test_researcher_agent_location_based_search():
    """Test ResearcherAgent handles location-based queries."""
    from l3_execution.agents.specialists.researcher_agent import ResearcherAgent

    mock_groq = MagicMock()
    agent = ResearcherAgent(
        agent_id="researcher_002",
        session_id="session_test",
        groq_client=mock_groq,
    )

    # Get user location
    location = await agent._get_user_location("user_123")
    assert "city" in location
    assert location["city"] == "San Francisco"

    # Test location-based search
    search_results = await agent._query_web_search("Italian restaurants nearby", location)
    assert search_results["query_type"] == "location_based"
    assert len(search_results["results"]) == 3
    assert "Bella Italia" in search_results["results"][0]["name"]


@pytest.mark.asyncio
async def test_researcher_agent_factual_search():
    """Test ResearcherAgent handles factual queries."""
    from l3_execution.agents.specialists.researcher_agent import ResearcherAgent

    mock_groq = MagicMock()
    agent = ResearcherAgent(
        agent_id="researcher_003",
        session_id="session_test",
        groq_client=mock_groq,
    )

    location = {"city": "San Francisco", "state": "CA"}

    # Test factual search
    search_results = await agent._query_web_search("What is photosynthesis?", location)
    assert search_results["query_type"] == "factual"
    assert len(search_results["results"]) == 2
    assert "Wikipedia" in search_results["results"][0]["source"]


@pytest.mark.asyncio
async def test_researcher_agent_general_search():
    """Test ResearcherAgent handles general queries."""
    from l3_execution.agents.specialists.researcher_agent import ResearcherAgent

    mock_groq = MagicMock()
    agent = ResearcherAgent(
        agent_id="researcher_004",
        session_id="session_test",
        groq_client=mock_groq,
    )

    location = {"city": "San Francisco", "state": "CA"}

    # Test general search
    search_results = await agent._query_web_search("latest tech news", location)
    assert search_results["query_type"] == "general"
    assert len(search_results["results"]) == 3
    assert "snippet" in search_results["results"][0]


# ===============================
# Integration Tests
# ===============================


@pytest.mark.asyncio
async def test_all_specialists_response_format():
    """Test all specialists return consistent response format."""
    from l3_execution.agents.specialists.finance_agent import FinanceAgent
    from l3_execution.agents.specialists.healthcare_agent import HealthcareAgent
    from l3_execution.agents.specialists.researcher_agent import ResearcherAgent

    mock_groq = MagicMock()

    specialists = [
        HealthcareAgent("h1", "s1", mock_groq),
        FinanceAgent("f1", "s1", mock_groq),
        ResearcherAgent("r1", "s1", mock_groq),
    ]

    mock_llm_response = {"content": "Test response"}

    for specialist in specialists:
        with patch.object(specialist, "call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = mock_llm_response

            message = {
                "type": "specialist_task",
                "payload": {
                    "user_query": "Test query",
                    "user_id": "user_123",
                    "task_id": "task_test",
                },
            }

            result = await specialist.process_message(message)

            # Verify consistent response structure
            assert result["status"] == "success"
            assert "specialist" in result
            assert result["task_id"] == "task_test"
            assert "response" in result
            assert "context_used" in result


@pytest.mark.asyncio
async def test_specialist_temperature_settings():
    """Test each specialist uses correct temperature setting."""
    from l3_execution.agents.specialists.finance_agent import FinanceAgent
    from l3_execution.agents.specialists.healthcare_agent import HealthcareAgent
    from l3_execution.agents.specialists.researcher_agent import ResearcherAgent

    mock_groq = MagicMock()
    mock_llm_response = {"content": "Test"}

    # Test HealthcareAgent (temp=0.7)
    healthcare = HealthcareAgent("h1", "s1", mock_groq)
    with patch.object(healthcare, "call_llm", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = mock_llm_response
        await healthcare.process_message(
            {"payload": {"user_query": "test", "user_id": "u1", "task_id": "t1"}}
        )
        assert mock_llm.call_args.kwargs["temperature"] == 0.7

    # Test FinanceAgent (temp=0.3)
    finance = FinanceAgent("f1", "s1", mock_groq)
    with patch.object(finance, "call_llm", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = mock_llm_response
        await finance.process_message(
            {"payload": {"user_query": "test", "user_id": "u1", "task_id": "t1"}}
        )
        assert mock_llm.call_args.kwargs["temperature"] == 0.3

    # Test ResearcherAgent (temp=0.5)
    researcher = ResearcherAgent("r1", "s1", mock_groq)
    with patch.object(researcher, "call_llm", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = mock_llm_response
        await researcher.process_message(
            {"payload": {"user_query": "test", "user_id": "u1", "task_id": "t1"}}
        )
        assert mock_llm.call_args.kwargs["temperature"] == 0.5
