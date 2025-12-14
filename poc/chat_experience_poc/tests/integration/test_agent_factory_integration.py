"""
Test Agent Factory Integration with Concierge Agent

Verifies Epic 6.5.2.2: Dynamic Specialist Agent Spawning & Execution
"""

import logging

import pytest

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@pytest.mark.asyncio
async def test_agent_factory_spawn(mock_groq_client):
    """Test Agent Factory can spawn specialist agents"""

    logger.info("=" * 70)
    logger.info("TEST: Agent Factory Spawning")
    logger.info("=" * 70)

    from l3_execution.agents.agent_factory import AgentFactory
    from l5_infrastructure.registries.tool_registry import ToolRegistry

    # Setup (use pytest fixture)
    tool_registry = ToolRegistry()
    prompt_registry = {}

    agent_factory = AgentFactory(
        prompt_registry=prompt_registry,
        tool_registry=tool_registry,
        groq_client=mock_groq_client,  # Use fixture
    )

    logger.info("Agent Factory initialized")

    # Test 1: Spawn healthcare agent
    logger.info("\n--- Test 1: Spawn Healthcare Agent ---")
    task_envelope = {
        "task_id": "test_001",
        "user_input": "How's my recovery going?",
        "specialist_type": "healthcare",
        "session_id": "test_session",
        "trace_id": "test_trace",
    }

    agent = await agent_factory.spawn_agent(
        agent_type="healthcare",
        task_envelope=task_envelope,
        session_id="test_session",
        trace_id="test_trace",
    )

    assert agent is not None, "Agent spawn failed"
    logger.info(f"✅ Agent spawned: {agent.agent_id}")
    logger.info(f"✅ Agent type: {agent.agent_type}")
    logger.info(f"✅ Agent state: {agent.state.value}")
    logger.info(f"✅ Tools count: {len(agent.available_tools)}")

    # Test 2: Process message with agent
    logger.info("\n--- Test 2: Process Message ---")
    response = await agent.process_message(task_envelope)

    assert response["status"] == "success", "Message processing failed"
    logger.info(f"✅ Response status: {response['status']}")
    logger.info(f"✅ Response content: {response['content'][:100]}...")
    logger.info(f"✅ Tokens used: {response.get('tokens_used', 0)}")

    # Test 3: Factory stats
    logger.info("\n--- Test 3: Factory Stats ---")
    stats = agent_factory.get_stats()
    logger.info(f"✅ Spawn count: {stats['spawn_count']}")
    logger.info(f"✅ Active agents: {stats['active_agents']}")

    logger.info("\n" + "=" * 70)
    logger.info("✅ ALL TESTS PASSED")
    logger.info("=" * 70)


@pytest.mark.asyncio
async def test_concierge_with_agent_factory(mock_groq_client):
    """Test Concierge Agent using Agent Factory to route to specialists"""

    logger.info("=" * 70)
    logger.info("TEST: Concierge + Agent Factory Integration")
    logger.info("=" * 70)

    from l3_execution.agents.agent_factory import AgentFactory
    from l3_execution.agents.concierge_agent import ConciergeAgent
    from l5_infrastructure.registries.tool_registry import ToolRegistry

    # Setup (use pytest fixture)
    tool_registry = ToolRegistry()
    prompt_registry = {}

    agent_factory = AgentFactory(
        prompt_registry=prompt_registry,
        tool_registry=tool_registry,
        groq_client=mock_groq_client,  # Use fixture
    )

    concierge = ConciergeAgent(
        agent_id="concierge_test",
        session_id="test_session",
        groq_client=mock_groq_client,  # Use fixture
        agent_factory=agent_factory,
        trace_id="test_trace",
    )

    logger.info("Concierge + Agent Factory initialized")

    # Test: Route healthcare query
    logger.info("\n--- Test: Route Healthcare Query ---")
    response = await concierge._route_to_specialist(
        user_input="How's my recovery going?", specialist_type="healthcare"
    )

    assert response["status"] == "success", "Routing failed"
    assert response.get("spawned"), "Agent not spawned"

    logger.info(f"✅ Status: {response['status']}")
    logger.info(f"✅ Specialist: {response['specialist_type']}")
    logger.info(f"✅ Agent spawned: {response.get('spawned')}")
    logger.info(f"✅ Agent ID: {response.get('agent_id')}")
    logger.info(f"✅ Response: {response['content'][:100]}...")

    # Check factory stats
    stats = agent_factory.get_stats()
    logger.info(f"\n✅ Factory spawned {stats['spawn_count']} agents")
    logger.info(f"✅ Factory has {stats['active_agents']} active agents")

    logger.info("\n" + "=" * 70)
    logger.info("✅ ALL TESTS PASSED")
    logger.info("=" * 70)
