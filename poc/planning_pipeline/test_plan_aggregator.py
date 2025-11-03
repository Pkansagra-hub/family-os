"""
Test Plan Aggregator (M8 Epic 8.1)

Tests result collection and aggregation from DAG execution.
"""

import asyncio

from agent_base import Agent
from agent_spawn_wrapper import AgentSpawnWrapper
from dag_executor import DAGExecutor
from dag_node import DAG, DAGNode
from plan_aggregator import PlanAggregator, create_aggregated_plan_summary

# ============================================================================
# MOCK AGENTS
# ============================================================================


class SuccessAgent(Agent):
    """Agent that always succeeds"""

    async def execute(self, context: dict) -> dict:
        await asyncio.sleep(0.1)
        return {"status": "success", "data": f"{self.node_id}_completed"}


class FailureAgent(Agent):
    """Agent that always fails"""

    async def execute(self, context: dict) -> dict:
        raise Exception(f"{self.node_id} deliberately failed")


class SlowAgent(Agent):
    """Agent that takes time"""

    async def execute(self, context: dict) -> dict:
        await asyncio.sleep(0.5)
        return {"status": "success", "data": f"{self.node_id}_slow_result"}


class MockAgentSpawnWrapper(AgentSpawnWrapper):
    """Wrapper for spawning test agents"""

    def spawn_agent(self, agent_type: str, node_id: str, context: dict) -> Agent:
        """Spawn agent by type"""
        agents = {
            "success_agent": SuccessAgent,
            "failure_agent": FailureAgent,
            "slow_agent": SlowAgent,
        }
        agent_class = agents.get(agent_type, SuccessAgent)
        return agent_class(node_id=node_id)


# ============================================================================
# TEST CASES
# ============================================================================


async def test_full_success():
    """Test aggregation with all nodes succeeding"""
    print("\n" + "=" * 60)
    print("TEST 1: Full Success (All Nodes Complete)")
    print("=" * 60)

    # Create DAG with 3 successful nodes
    dag = DAG(
        dag_id="test_full_success",
        user_input="Test full success",
        metadata={"intent": "test_all_success"},
    )

    node1 = DAGNode(node_id="s1", agent_type="success_agent", user_input="Step 1", tools={})
    node2 = DAGNode(
        node_id="s2", agent_type="success_agent", user_input="Step 2", tools={}, dependencies=["s1"]
    )
    node3 = DAGNode(
        node_id="s3", agent_type="success_agent", user_input="Step 3", tools={}, dependencies=["s2"]
    )

    dag.add_node(node1)
    dag.add_node(node2)
    dag.add_node(node3)

    # Execute DAG
    spawn_wrapper = MockAgentSpawnWrapper()
    executor = DAGExecutor(spawn_wrapper, max_concurrent_nodes=3)

    results = await executor.execute(dag)

    # Aggregate results
    aggregator = PlanAggregator()
    aggregated = aggregator.aggregate(dag, results)

    # Print summary
    print(create_aggregated_plan_summary(aggregated))

    # Validate
    assert aggregated.status == "completed"
    assert len(aggregated.successful_steps) == 3
    assert len(aggregated.failed_steps) == 0
    assert len(aggregated.blocked_steps) == 0

    print("\n✅ Test 1 passed!")


async def test_partial_success():
    """Test aggregation with some failures"""
    print("\n" + "=" * 60)
    print("TEST 2: Partial Success (One Failure, One Blocked)")
    print("=" * 60)

    # Create DAG: s1 (success) → s2 (fail) → s3 (blocked)
    dag = DAG(
        dag_id="test_partial_success",
        user_input="Test partial success",
        metadata={"intent": "test_partial_failure"},
    )

    node1 = DAGNode(node_id="s1", agent_type="success_agent", user_input="Step 1", tools={})
    node2 = DAGNode(
        node_id="s2",
        agent_type="failure_agent",
        user_input="Step 2 (will fail)",
        tools={},
        dependencies=["s1"],
    )
    node3 = DAGNode(
        node_id="s3",
        agent_type="success_agent",
        user_input="Step 3 (will be blocked)",
        tools={},
        dependencies=["s2"],
    )

    dag.add_node(node1)
    dag.add_node(node2)
    dag.add_node(node3)

    # Execute DAG
    spawn_wrapper = MockAgentSpawnWrapper()
    executor = DAGExecutor(spawn_wrapper, max_concurrent_nodes=3)

    results = await executor.execute(dag)

    # Aggregate results
    aggregator = PlanAggregator()
    aggregated = aggregator.aggregate(dag, results)

    # Print summary
    print(create_aggregated_plan_summary(aggregated))

    # Validate
    assert aggregated.status == "partial_success"
    assert len(aggregated.successful_steps) == 1  # s1
    assert len(aggregated.failed_steps) == 1  # s2
    assert len(aggregated.blocked_steps) == 1  # s3

    print("\n✅ Test 2 passed!")


async def test_parallel_success():
    """Test aggregation with parallel execution"""
    print("\n" + "=" * 60)
    print("TEST 3: Parallel Success (Diamond Pattern)")
    print("=" * 60)

    # Create diamond DAG: s1 → [s2, s3] → s4
    dag = DAG(
        dag_id="test_parallel",
        user_input="Test parallel execution",
        metadata={"intent": "test_parallel_diamond"},
    )

    node1 = DAGNode(node_id="s1", agent_type="success_agent", user_input="Root", tools={})
    node2 = DAGNode(
        node_id="s2", agent_type="slow_agent", user_input="Branch A", tools={}, dependencies=["s1"]
    )
    node3 = DAGNode(
        node_id="s3",
        agent_type="success_agent",
        user_input="Branch B",
        tools={},
        dependencies=["s1"],
    )
    node4 = DAGNode(
        node_id="s4",
        agent_type="success_agent",
        user_input="Merge",
        tools={},
        dependencies=["s2", "s3"],
    )

    dag.add_node(node1)
    dag.add_node(node2)
    dag.add_node(node3)
    dag.add_node(node4)

    # Execute DAG
    spawn_wrapper = MockAgentSpawnWrapper()
    executor = DAGExecutor(spawn_wrapper, max_concurrent_nodes=3)

    results = await executor.execute(dag)

    # Aggregate results
    aggregator = PlanAggregator()
    aggregated = aggregator.aggregate(dag, results)

    # Print summary
    print(create_aggregated_plan_summary(aggregated))

    # Validate
    assert aggregated.status == "completed"
    assert len(aggregated.successful_steps) == 4
    assert aggregated.dag_metrics is not None
    assert aggregated.dag_metrics.max_parallelism >= 2  # s2 and s3 should run in parallel

    print("\n✅ Test 3 passed!")


async def test_collect_results():
    """Test result collection from DAG"""
    print("\n" + "=" * 60)
    print("TEST 4: Collect Results from DAG")
    print("=" * 60)

    # Create simple DAG
    dag = DAG(dag_id="test_collect", user_input="Test collection", metadata={})

    node1 = DAGNode(node_id="s1", agent_type="success_agent", user_input="Step 1", tools={})
    node2 = DAGNode(node_id="s2", agent_type="success_agent", user_input="Step 2", tools={})

    dag.add_node(node1)
    dag.add_node(node2)

    # Execute
    spawn_wrapper = MockAgentSpawnWrapper()
    executor = DAGExecutor(spawn_wrapper, max_concurrent_nodes=2)
    results = await executor.execute(dag)

    # Collect results
    aggregator = PlanAggregator()
    collected = aggregator.collect_results(dag)

    print(f"Collected {len(collected)} results:")
    for node_id, result in collected.items():
        print(f"  {node_id}: {result.status}")

    # Validate
    assert len(collected) == 2
    assert "s1" in collected
    assert "s2" in collected
    assert all(r.status == "completed" for r in collected.values())

    print("\n✅ Test 4 passed!")


async def test_failure_details():
    """Test extraction of failure details"""
    print("\n" + "=" * 60)
    print("TEST 5: Failure Details Extraction")
    print("=" * 60)

    # Create DAG with failures
    dag = DAG(dag_id="test_failures", user_input="Test failures", metadata={})

    node1 = DAGNode(node_id="s1", agent_type="failure_agent", user_input="Will fail", tools={})
    node2 = DAGNode(
        node_id="s2",
        agent_type="success_agent",
        user_input="Will be blocked",
        tools={},
        dependencies=["s1"],
    )

    dag.add_node(node1)
    dag.add_node(node2)

    # Execute
    spawn_wrapper = MockAgentSpawnWrapper()
    executor = DAGExecutor(spawn_wrapper, max_concurrent_nodes=2)
    results = await executor.execute(dag)

    # Get failure details
    aggregator = PlanAggregator()
    failed_details = aggregator.get_failed_node_details(dag)
    blocked_details = aggregator.get_blocked_node_details(dag)

    print(f"Failed nodes: {len(failed_details)}")
    for detail in failed_details:
        print(f"  {detail['node_id']}: {detail['error']}")

    print(f"Blocked nodes: {len(blocked_details)}")
    for detail in blocked_details:
        print(f"  {detail['node_id']}: {detail['error']}")

    # Validate
    assert len(failed_details) == 1
    assert failed_details[0]["node_id"] == "s1"
    assert len(blocked_details) == 1
    assert blocked_details[0]["node_id"] == "s2"

    print("\n✅ Test 5 passed!")


# ============================================================================
# MAIN
# ============================================================================


async def main():
    """Run all plan aggregator tests"""
    print("\n" + "=" * 60)
    print("PLAN AGGREGATOR TEST SUITE (M8)")
    print("=" * 60)

    await test_full_success()
    await test_partial_success()
    await test_parallel_success()
    await test_collect_results()
    await test_failure_details()

    print("\n" + "=" * 60)
    print("✅ ALL PLAN AGGREGATOR TESTS PASSED")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
