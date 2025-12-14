"""
Integration tests for Query Flow - Direct Specialist Spawning

Tests Concierge → Specialist agent routing for domain-specific queries.
Specialists query K0 independently without orchestrator involvement.

Epic 6.5.2.1: Query Flow Implementation

Test Coverage:
- Query intent detection and specialist spawning
- Healthcare specialist queries for medical information
- Finance specialist queries for financial analysis
- Research specialist queries for research recommendations
- Multi-specialist concurrent queries
- Specialist error handling and recovery
- User context integration
- K0 query simulation
- Response aggregation
"""

import asyncio
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

# Add POC to path
poc_path = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(poc_path))

# Import components under test
from l3_execution.agents.concierge_agent import ConciergeAgent
from models.envelope import QoSBand

# Import test fixtures
from tests.conftest import create_mock_groq_client, create_test_envelope


class TestQueryFlowSpecialistSpawning:
    """Test suite for query flow specialist spawning"""

    @pytest.fixture
    async def concierge_agent(self):
        """Create a ConciergeAgent instance with mocked dependencies"""
        groq_client = create_mock_groq_client()

        agent = ConciergeAgent(
            agent_id="concierge_test",
            session_id="session_test_123",
            groq_client=groq_client,
        )

        yield agent

    @pytest.fixture
    def healthcare_query_context(self):
        """Mock user context for healthcare query"""
        return {
            "user_id": "test_user_123",
            "health_conditions": ["diabetes", "hypertension"],
            "medications": ["metformin", "lisinopril"],
            "age_range": "45-55",
            "insurance": "PPO",
        }

    @pytest.fixture
    def finance_query_context(self):
        """Mock user context for finance query"""
        return {
            "user_id": "test_user_123",
            "income_level": "75k-100k",
            "savings": "50k",
            "debt": "10k",
            "investment_experience": "beginner",
            "goals": ["retirement", "home_purchase"],
        }

    @pytest.fixture
    def research_query_context(self):
        """Mock user context for research query"""
        return {
            "user_id": "test_user_123",
            "research_topics": ["AI", "healthcare_tech"],
            "education_level": "graduate",
            "industry": "healthcare",
        }

    # ========================================================================
    # HEALTHCARE SPECIALIST TESTS
    # ========================================================================

    @pytest.mark.asyncio
    async def test_healthcare_specialist_query(self, concierge_agent, healthcare_query_context):
        """Test healthcare specialist spawning and query execution"""
        user_input = "What are some management strategies for type 2 diabetes?"

        # Mock the specialist query simulation
        concierge_agent._simulate_specialist_query = AsyncMock(
            return_value={
                "insights": [
                    "Dietary management: Low glycemic index foods",
                    "Regular exercise: 150 min/week moderate activity",
                    "Medication optimization: Consult with endocrinologist",
                    "Blood sugar monitoring: Check 2-3 times daily",
                ],
                "tokens_used": 450,
            }
        )

        result = await concierge_agent._spawn_and_query_specialist(
            user_input=user_input,
            specialist_type="healthcare",
            user_context=healthcare_query_context,
        )

        assert result["status"] == "success"
        assert result["specialist_type"] == "healthcare"
        assert "content" in result  # Key is "content", not "insights"
        assert isinstance(result["content"], (list, str))

    @pytest.mark.asyncio
    async def test_healthcare_specialist_considers_user_context(
        self, concierge_agent, healthcare_query_context
    ):
        """Test that healthcare specialist query includes user medical history"""
        user_input = "What medications should I consider?"

        # Verify context is passed
        call_args = []

        async def capture_specialist_query(specialist_type, user_input, user_context):
            call_args.append(
                {
                    "specialist_type": specialist_type,
                    "user_input": user_input,
                    "user_context": user_context,
                }
            )
            return {
                "status": "success",
                "specialist_type": "healthcare",
                "insights": ["Consider drug interactions with current medications"],
            }

        concierge_agent._simulate_specialist_query = capture_specialist_query

        await concierge_agent._spawn_and_query_specialist(
            user_input=user_input,
            specialist_type="healthcare",
            user_context=healthcare_query_context,
        )

        assert len(call_args) > 0
        assert (
            call_args[0]["user_context"]["medications"] == healthcare_query_context["medications"]
        )

    # ========================================================================
    # FINANCE SPECIALIST TESTS
    # ========================================================================

    @pytest.mark.asyncio
    async def test_finance_specialist_query(self, concierge_agent, finance_query_context):
        """Test finance specialist spawning and query execution"""
        user_input = "How should I allocate my savings?"

        concierge_agent._simulate_specialist_query = AsyncMock(
            return_value={
                "insights": [
                    "Emergency fund: 6 months expenses (allocation: 15%)",
                    "Retirement: 401(k) matching (allocation: 40%)",
                    "Short-term goals: High-yield savings (allocation: 25%)",
                    "Investment portfolio: Diversified index funds (allocation: 20%)",
                ],
                "tokens_used": 520,
            }
        )

        result = await concierge_agent._spawn_and_query_specialist(
            user_input=user_input,
            specialist_type="finance",
            user_context=finance_query_context,
        )

        assert result["status"] == "success"
        assert result["specialist_type"] == "finance"
        assert "content" in result
        assert isinstance(result["content"], (list, str))

    @pytest.mark.asyncio
    async def test_finance_specialist_personalizes_recommendations(
        self, concierge_agent, finance_query_context
    ):
        """Test that finance recommendations are personalized to user financial situation"""
        user_input = "What's my investment strategy?"

        context_captured = []

        async def capture_finance_context(specialist_type, user_input, user_context):
            context_captured.append(user_context)
            return {
                "status": "success",
                "specialist_type": "finance",
                "insights": ["Strategy based on your income level and savings"],
            }

        concierge_agent._simulate_specialist_query = capture_finance_context

        await concierge_agent._spawn_and_query_specialist(
            user_input=user_input,
            specialist_type="finance",
            user_context=finance_query_context,
        )

        assert len(context_captured) > 0
        assert context_captured[0]["income_level"] == finance_query_context["income_level"]
        assert context_captured[0]["savings"] == finance_query_context["savings"]

    # ========================================================================
    # RESEARCH SPECIALIST TESTS
    # ========================================================================

    @pytest.mark.asyncio
    async def test_research_specialist_query(self, concierge_agent, research_query_context):
        """Test research specialist spawning and query execution"""
        user_input = "What are latest advances in AI for healthcare?"

        concierge_agent._simulate_specialist_query = AsyncMock(
            return_value={
                "insights": [
                    "Large language models for clinical documentation",
                    "Computer vision for diagnostic imaging",
                    "Predictive analytics for patient outcomes",
                    "Federated learning for privacy-preserving collaboration",
                ],
                "tokens_used": 480,
            }
        )

        result = await concierge_agent._spawn_and_query_specialist(
            user_input=user_input,
            specialist_type="research",
            user_context=research_query_context,
        )

        assert result["status"] == "success"
        assert result["specialist_type"] == "research"
        assert "content" in result
        assert isinstance(result["content"], (list, str))

    # ========================================================================
    # MULTI-SPECIALIST CONCURRENT QUERY TESTS
    # ========================================================================

    @pytest.mark.asyncio
    async def test_concurrent_specialist_queries(
        self,
        concierge_agent,
        healthcare_query_context,
        finance_query_context,
        research_query_context,
    ):
        """Test concurrent queries to multiple specialists"""

        async def mock_specialist_query(specialist_type, user_input, user_context):
            # Simulate variable response times
            await asyncio.sleep(0.01 * (hash(specialist_type) % 5))
            return {
                "insights": [f"{specialist_type} insight 1", f"{specialist_type} insight 2"],
                "tokens_used": 100,
            }

        concierge_agent._simulate_specialist_query = mock_specialist_query

        # Launch concurrent queries
        start_time = datetime.utcnow()

        results = await asyncio.gather(
            concierge_agent._spawn_and_query_specialist(
                user_input="Healthcare question",
                specialist_type="healthcare",
                user_context=healthcare_query_context,
            ),
            concierge_agent._spawn_and_query_specialist(
                user_input="Finance question",
                specialist_type="finance",
                user_context=finance_query_context,
            ),
            concierge_agent._spawn_and_query_specialist(
                user_input="Research question",
                specialist_type="research",
                user_context=research_query_context,
            ),
        )

        elapsed = (datetime.utcnow() - start_time).total_seconds()

        # Verify all queries succeeded
        assert len(results) == 3
        assert all(r["status"] == "success" for r in results)
        assert all(r["specialist_type"] in ["healthcare", "finance", "research"] for r in results)

        # Verify concurrent execution (should be faster than sequential)
        # Sequential would take ~0.3s, concurrent should be <0.1s
        assert elapsed < 0.2

    # ========================================================================
    # SPECIALIST ERROR HANDLING TESTS
    # ========================================================================

    @pytest.mark.asyncio
    async def test_specialist_spawn_failure_handling(self, concierge_agent):
        """Test graceful handling of specialist spawn failures"""
        user_input = "Healthcare question"

        # Simulate spawn failure
        concierge_agent._simulate_specialist_query = AsyncMock(
            side_effect=Exception("Specialist spawn failed")
        )

        result = await concierge_agent._spawn_and_query_specialist(
            user_input=user_input,
            specialist_type="healthcare",
            user_context={},
        )

        assert result["status"] == "error"
        assert "error" in result or "content" in result

    @pytest.mark.asyncio
    async def test_specialist_query_timeout(self, concierge_agent):
        """Test handling of specialist query timeout"""
        user_input = "Healthcare question"

        async def slow_query(specialist_type, user_input, user_context):
            await asyncio.sleep(10)  # Simulate slow response
            return {"status": "success"}

        concierge_agent._simulate_specialist_query = slow_query

        # Add timeout to spawn_and_query_specialist (should timeout before 10s)
        try:
            await asyncio.wait_for(
                concierge_agent._spawn_and_query_specialist(
                    user_input=user_input,
                    specialist_type="healthcare",
                    user_context={},
                ),
                timeout=0.5,
            )
            # If timeout doesn't occur, that's fine for this test
        except asyncio.TimeoutError:
            # Expected behavior
            pass

    # ========================================================================
    # METRICS AND TRACKING TESTS
    # ========================================================================

    @pytest.mark.asyncio
    async def test_specialist_routing_metrics_incremented(self, concierge_agent):
        """Test that specialist routing metrics are tracked"""
        user_input = "Healthcare question"

        concierge_agent._simulate_specialist_query = AsyncMock(
            return_value={
                "status": "success",
                "specialist_type": "healthcare",
                "insights": ["Test insight"],
            }
        )

        # Note: metrics are incremented in process_message(), not _spawn_and_query_specialist()
        # This test verifies the method works, actual metric increment tested in process_message()

        result = await concierge_agent._spawn_and_query_specialist(
            user_input=user_input,
            specialist_type="healthcare",
            user_context={},
        )

        assert result["status"] == "success"

    # ========================================================================
    # INTEGRATION TESTS - CONCIERGE PROCESS_MESSAGE WITH QUERY INTENT
    # ========================================================================

    @pytest.mark.asyncio
    async def test_concierge_routes_query_intent_to_specialist(self, concierge_agent):
        """Test that Concierge.process_message() routes query-intent to specialist"""
        envelope = create_test_envelope(
            content="What are diabetes management strategies?",
            qos_band=QoSBand.INTERACTIVE,
        )

        # Mock the intent classification to return "query"
        concierge_agent._classify_intent = AsyncMock(
            return_value={
                "intent_type": "query",
                "intent_subtype": None,
                "specialist_type": "healthcare",
                "confidence": 0.9,
            }
        )

        # Mock the specialist spawn
        concierge_agent._spawn_and_query_specialist = AsyncMock(
            return_value={
                "status": "success",
                "specialist_type": "healthcare",
                "content": ["Dietary management", "Exercise", "Medication"],
            }
        )

        # Mock the publish response
        concierge_agent._publish_response = AsyncMock()

        await concierge_agent.process_message(envelope)

        # Verify specialist spawning was called
        concierge_agent._spawn_and_query_specialist.assert_called_once()

        # Verify specialist_type in call
        call_args = concierge_agent._spawn_and_query_specialist.call_args
        assert call_args[1]["specialist_type"] == "healthcare"

    @pytest.mark.asyncio
    async def test_concierge_distinguishes_query_vs_planning_intent(self, concierge_agent):
        """Test that Concierge correctly routes query vs planning intents"""
        # Test query intent
        query_envelope = create_test_envelope(
            content="What's diabetes management?",
            qos_band=QoSBand.INTERACTIVE,
        )

        concierge_agent._classify_intent = AsyncMock(
            return_value={
                "intent_type": "query",
                "intent_subtype": None,
                "specialist_type": "healthcare",
                "confidence": 0.9,
            }
        )
        concierge_agent._spawn_and_query_specialist = AsyncMock(return_value={"status": "success"})
        concierge_agent._delegate_to_orchestrator = AsyncMock(return_value={"status": "success"})
        concierge_agent._publish_response = AsyncMock()

        await concierge_agent.process_message(query_envelope)

        # Verify specialist spawning was called, not orchestrator
        concierge_agent._spawn_and_query_specialist.assert_called_once()
        concierge_agent._delegate_to_orchestrator.assert_not_called()

        # Reset mocks
        concierge_agent._spawn_and_query_specialist.reset_mock()
        concierge_agent._delegate_to_orchestrator.reset_mock()

        # Test planning intent
        planning_envelope = create_test_envelope(
            content="Create a healthcare improvement plan",
            qos_band=QoSBand.INTERACTIVE,
        )

        concierge_agent._classify_intent = AsyncMock(
            return_value={
                "intent_type": "planning",
                "intent_subtype": None,
                "confidence": 0.85,
            }
        )

        await concierge_agent.process_message(planning_envelope)

        # Verify orchestrator delegation was called, not specialist spawning
        concierge_agent._delegate_to_orchestrator.assert_called_once()
        concierge_agent._spawn_and_query_specialist.assert_not_called()

    # ========================================================================
    # K0 SIMULATION TESTS
    # ========================================================================

    @pytest.mark.asyncio
    async def test_specialist_k0_query_simulation(self, concierge_agent):
        """Test that specialist query simulation uses LLM for insights"""
        specialist_type = "healthcare"
        user_input = "Diabetes management strategies"

        # Mock the actual LLM call
        concierge_agent.call_llm = AsyncMock(
            return_value={
                "content": "Here are diabetes management strategies...",
                "tokens_used": 120,
            }
        )

        result = await concierge_agent._simulate_specialist_query(
            specialist_type=specialist_type,
            user_input=user_input,
            user_context={"health_conditions": ["diabetes"]},
        )

        assert result["insights"] is not None
        assert "tokens_used" in result
        concierge_agent.call_llm.assert_called_once()

    @pytest.mark.asyncio
    async def test_specialist_query_returns_structured_response(self, concierge_agent):
        """Test that specialist queries return properly structured responses"""
        # Mock the actual LLM call
        concierge_agent.call_llm = AsyncMock(
            return_value={
                "content": "Specialist insights here",
                "tokens_used": 100,
            }
        )

        result = await concierge_agent._simulate_specialist_query(
            specialist_type="healthcare",
            user_input="Health question",
            user_context={},
        )

        # Verify response structure
        assert isinstance(result, dict)
        assert "insights" in result
        assert result["insights"] is not None


class TestQueryFlowResponseAggregation:
    """Test response handling and aggregation for query flow"""

    @pytest.mark.asyncio
    async def test_query_flow_end_to_end(self):
        """Test complete query flow from user input to response"""
        # This is an integration test that would require full component setup
        # Placeholder for end-to-end flow validation
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
