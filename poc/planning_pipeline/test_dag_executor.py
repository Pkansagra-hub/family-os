"""
Test suite for DAG Executor

Tests parallel execution, failure handling, and metrics tracking.
Part of M6 Epic 6.2: Parallel Executor
Part of M6 Epic 6.3: DAG Visualization
"""

import asyncio
from typing import Any, Dict, Optional

# Import agent base classes
from agent_base import Agent, AgentContext, AgentResponse
from agent_spawn_wrapper import AgentSpawnWrapper
from dag_builder import DAGBuilder
from dag_executor import DAGExecutor

# Import DAG structures
from dag_node import NodeStatus
from dag_visualizer import export_dag_mermaid, render_dag_ascii

# ============================================================================
# MOCK AGENT INFRASTRUCTURE FOR TESTING
# ============================================================================


class MockAgent(Agent):
    """Mock agent for testing DAG execution"""

    def __init__(
        self,
        agent_type: str,
        latency_ms: float = 100.0,
        should_fail: bool = False,
        result_text: str = "Mock result",
    ):
        """Initialize mock agent"""
        self.agent_id = f"mock_{agent_type}"
        self.agent_type = agent_type
        self.context = AgentContext(
            agent_id=self.agent_id,
            agent_type=self.agent_type,
            user_input="Mock input",
            conversation_history=[],
            clarification_history=[],
        )
        self.latency_ms = latency_ms
        self.should_fail = should_fail
        self.result_text = result_text
        self.question_queue = None  # For M7 compatibility

    def get_required_tools(self) -> list:
        """Return empty tool list for mock agent"""
        return []

    async def execute(self, context: AgentContext) -> AgentResponse:
        """Execute mock agent"""
        # Simulate work
        await asyncio.sleep(self.latency_ms / 1000.0)

        if self.should_fail:
            return AgentResponse(
                agent_id=self.agent_id,
                agent_type=self.agent_type,
                status="error",
                error="Mock agent failed",
                latency_ms=self.latency_ms,
            )

        return AgentResponse(
            agent_id=self.agent_id,
            agent_type=self.agent_type,
            status="completed",
            result={"text": self.result_text},
            latency_ms=self.latency_ms,
        )


class MockAgentSpawnWrapper(AgentSpawnWrapper):
    """Mock agent spawn wrapper for testing"""

    def __init__(self, fail_agents: Optional[Dict[str, bool]] = None):
        """
        Initialize mock spawn wrapper.

        Args:
            fail_agents: Dict of agent_type → should_fail
        """
        self.fail_agents = fail_agents or {}
        self.spawned_agents = []

    async def spawn_agent(
        self,
        agent_type: str,
        user_input: str = "",
        tools: Optional[list] = None,
        user_id: str = "user",
        user_profile: Optional[Dict[str, Any]] = None,
        conversation_history: Optional[list] = None,
        clarification_history: Optional[list] = None,
    ) -> Agent:
        """Spawn mock agent"""
        should_fail = self.fail_agents.get(agent_type, False)
        print(
            f"DEBUG spawn_agent: type={agent_type}, should_fail={should_fail}, fail_agents={self.fail_agents}"
        )

        agent = MockAgent(
            agent_type=agent_type,
            latency_ms=100.0,
            should_fail=should_fail,
            result_text=f"Result from {agent_type}",
        )

        self.spawned_agents.append(agent)
        return agent


# ============================================================================
# TEST CASES
# ============================================================================


async def test_sequential_execution():
    """Test DAG with sequential dependencies"""
    print("\n=== Test 1: Sequential Execution ===")

    # Create sequential DAG: s1 → s2 → s3
    plan = {
        "steps": [
            {
                "id": "s1",
                "agent": "agent_a",
                "description": "Step 1",
                "needs": [],
                "tools": ["tool_a"],
            },
            {
                "id": "s2",
                "agent": "agent_b",
                "description": "Step 2",
                "needs": ["s1"],
                "tools": ["tool_b"],
            },
            {
                "id": "s3",
                "agent": "agent_c",
                "description": "Step 3",
                "needs": ["s2"],
                "tools": ["tool_c"],
            },
        ]
    }

    # Build DAG
    builder = DAGBuilder()
    dag = builder.build_from_expanded_plan(plan)

    print(f"DAG: {dag.dag_id}")
    print(f"Nodes: {len(dag.nodes)}")
    print(f"Edges: {len(dag.edges)}")

    # Execute
    spawn_wrapper = MockAgentSpawnWrapper()
    executor = DAGExecutor(spawn_wrapper, max_concurrent_nodes=5)

    results = await executor.execute(dag)

    # Validate
    assert len(results) == 3
    assert all(r.status == "completed" for r in results.values())
    assert dag.is_complete()

    # Check metrics
    metrics = dag.metadata.get("metrics")
    assert metrics is not None
    assert metrics["nodes_completed"] == 3
    assert metrics["nodes_failed"] == 0
    assert metrics["max_parallelism"] == 1  # Sequential = 1 at a time

    print("✅ Sequential execution complete")
    print(f"   Metrics: {metrics}")
    print(f"   Max parallelism: {metrics['max_parallelism']}")


async def test_parallel_execution():
    """Test DAG with parallel branches"""
    print("\n=== Test 2: Parallel Execution ===")

    # Create diamond DAG:
    #     s1   s2
    #      ↘  ↙
    #       s3
    plan = {
        "steps": [
            {
                "id": "s1",
                "agent": "agent_a",
                "description": "Step 1",
                "needs": [],
                "tools": ["tool_a"],
            },
            {
                "id": "s2",
                "agent": "agent_b",
                "description": "Step 2",
                "needs": [],
                "tools": ["tool_b"],
            },
            {
                "id": "s3",
                "agent": "agent_c",
                "description": "Step 3",
                "needs": ["s1", "s2"],
                "tools": ["tool_c"],
            },
        ]
    }

    # Build DAG
    builder = DAGBuilder()
    dag = builder.build_from_expanded_plan(plan)

    print(f"DAG: {dag.dag_id}")
    print(f"Nodes: {len(dag.nodes)}")
    print(f"Edges: {len(dag.edges)}")

    # Execute
    spawn_wrapper = MockAgentSpawnWrapper()
    executor = DAGExecutor(spawn_wrapper, max_concurrent_nodes=5)

    results = await executor.execute(dag)

    # Validate
    assert len(results) == 3
    assert all(r.status == "completed" for r in results.values())
    assert dag.is_complete()

    # Check metrics
    metrics = dag.metadata.get("metrics")
    assert metrics is not None
    assert metrics["nodes_completed"] == 3
    assert metrics["nodes_failed"] == 0
    assert metrics["max_parallelism"] == 2  # s1 and s2 run in parallel

    print("✅ Parallel execution complete")
    print(f"   Metrics: {metrics}")
    print(f"   Max parallelism: {metrics['max_parallelism']}")


async def test_failure_handling():
    """Test graceful failure handling"""
    print("\n=== Test 3: Failure Handling ===")

    # Create DAG where s2 fails:
    #     s1
    #    ↙  ↘
    #   s2   s3
    #   ↓
    #   s4 (should be blocked)
    plan = {
        "steps": [
            {
                "id": "s1",
                "agent": "agent_a",
                "description": "Step 1",
                "needs": [],
                "tools": ["tool_a"],
            },
            {
                "id": "s2",
                "agent": "agent_b_fail",
                "description": "Step 2 (will fail)",
                "needs": ["s1"],
                "tools": ["tool_b"],
            },
            {
                "id": "s3",
                "agent": "agent_c",
                "description": "Step 3",
                "needs": ["s1"],
                "tools": ["tool_c"],
            },
            {
                "id": "s4",
                "agent": "agent_d",
                "description": "Step 4 (depends on failed s2)",
                "needs": ["s2"],
                "tools": ["tool_d"],
            },
        ]
    }

    # Build DAG
    builder = DAGBuilder()
    dag = builder.build_from_expanded_plan(plan)

    print(f"DAG: {dag.dag_id}")
    print(f"Nodes: {len(dag.nodes)}")

    # Execute with s2 configured to fail
    spawn_wrapper = MockAgentSpawnWrapper(fail_agents={"agent_b_fail": True})
    executor = DAGExecutor(spawn_wrapper, max_concurrent_nodes=5)

    results = await executor.execute(dag)

    # Validate
    print(f"Results: {list(results.keys())}")
    for node_id, result in results.items():
        print(f"  {node_id}: status={result.status}, error={result.error}")
    print(f"s4 status: {dag.get_node('s4').status if dag.get_node('s4') else 'None'}")

    assert len(results) == 3  # s1, s2, s3 executed; s4 blocked
    assert results["s1"].status == "completed"
    assert results["s2"].status == "error"
    assert results["s3"].status == "completed"
    assert "s4" not in results  # s4 never executed

    # Check node statuses
    assert dag.get_node("s1").status == NodeStatus.COMPLETED
    assert dag.get_node("s2").status == NodeStatus.FAILED
    assert dag.get_node("s3").status == NodeStatus.COMPLETED
    assert dag.get_node("s4").status == NodeStatus.BLOCKED

    # Check metrics
    metrics = dag.metadata.get("metrics")
    assert metrics is not None
    assert metrics["nodes_completed"] == 2  # s1, s3
    assert metrics["nodes_failed"] == 1  # s2
    assert metrics["nodes_blocked"] == 1  # s4

    print("✅ Failure handled gracefully")
    print(f"   Metrics: {metrics}")
    print(f"   s1: {dag.get_node('s1').status.value}")
    print(f"   s2: {dag.get_node('s2').status.value} (failed as expected)")
    print(f"   s3: {dag.get_node('s3').status.value}")
    print(f"   s4: {dag.get_node('s4').status.value} (blocked by s2 failure)")


async def test_performance_metrics():
    """Test performance metrics tracking"""
    print("\n=== Test 4: Performance Metrics ===")

    # Create simple parallel DAG
    plan = {
        "steps": [
            {"id": "s1", "agent": "agent_a", "description": "S1", "needs": [], "tools": []},
            {"id": "s2", "agent": "agent_b", "description": "S2", "needs": [], "tools": []},
            {
                "id": "s3",
                "agent": "agent_c",
                "description": "S3",
                "needs": ["s1", "s2"],
                "tools": [],
            },
        ]
    }

    builder = DAGBuilder()
    dag = builder.build_from_expanded_plan(plan)

    # Execute
    spawn_wrapper = MockAgentSpawnWrapper()
    executor = DAGExecutor(spawn_wrapper, max_concurrent_nodes=5)

    results = await executor.execute(dag)

    # Check metrics structure
    metrics = dag.metadata.get("metrics")
    assert metrics is not None

    print("✅ Metrics tracked successfully")
    print(f"   DAG ID: {metrics['dag_id']}")
    print(f"   Total execution time: {metrics['total_execution_ms']:.1f}ms")
    print(f"   Nodes executed: {metrics['nodes_executed']}")
    print(f"   Success rate: {metrics['success_rate']}")
    print(f"   Max parallelism: {metrics['max_parallelism']}")
    print(f"   Node latencies: {metrics['node_latencies']}")

    # Validate metric values
    assert metrics["nodes_executed"] == 3
    assert metrics["nodes_completed"] == 3
    assert metrics["nodes_failed"] == 0
    assert metrics["max_parallelism"] == 2  # s1, s2 run in parallel
    assert len(metrics["node_latencies"]) == 3


async def test_ascii_visualization():
    """Test ASCII DAG rendering"""
    print("\n=== Test 5: ASCII Visualization ===")

    # Create simple DAG
    plan = {
        "steps": [
            {"id": "s1", "agent": "agent_a", "description": "S1", "needs": [], "tools": []},
            {"id": "s2", "agent": "agent_b", "description": "S2", "needs": ["s1"], "tools": []},
        ]
    }

    builder = DAGBuilder()
    dag = builder.build_from_expanded_plan(plan)

    # Execute DAG
    spawn_wrapper = MockAgentSpawnWrapper()
    executor = DAGExecutor(spawn_wrapper, max_concurrent_nodes=5)
    await executor.execute(dag)

    # Render ASCII
    ascii_output = render_dag_ascii(dag, use_color=False)

    print("ASCII Output:")
    print(ascii_output)

    # Validate output contains expected elements
    assert dag.dag_id in ascii_output
    assert "s1" in ascii_output
    assert "s2" in ascii_output
    assert "✓" in ascii_output  # Completed symbol
    assert "Layer" in ascii_output

    print("✅ ASCII visualization working")


async def test_mermaid_export():
    """Test Mermaid diagram export"""
    print("\n=== Test 6: Mermaid Export ===")

    # Create diamond DAG
    plan = {
        "steps": [
            {"id": "s1", "agent": "agent_a", "description": "S1", "needs": [], "tools": []},
            {"id": "s2", "agent": "agent_b", "description": "S2", "needs": [], "tools": []},
            {
                "id": "s3",
                "agent": "agent_c",
                "description": "S3",
                "needs": ["s1", "s2"],
                "tools": [],
            },
        ]
    }

    builder = DAGBuilder()
    dag = builder.build_from_expanded_plan(plan)

    # Export Mermaid
    mermaid_output = export_dag_mermaid(dag, include_styling=True)

    print("Mermaid Output:")
    print(mermaid_output)

    # Validate output
    assert "```mermaid" in mermaid_output
    assert "flowchart TD" in mermaid_output
    assert "s1" in mermaid_output
    assert "s2" in mermaid_output
    assert "s3" in mermaid_output
    assert "-->" in mermaid_output  # Edge syntax
    assert "classDef" in mermaid_output  # Styling

    print("✅ Mermaid export working")


# ============================================================================
# RUN ALL TESTS
# ============================================================================


async def run_all_tests():
    """Run all test cases"""
    print("=" * 60)
    print("DAG EXECUTOR TEST SUITE")
    print("=" * 60)

    try:
        await test_sequential_execution()
        await test_parallel_execution()
        await test_failure_handling()
        await test_performance_metrics()
        await test_ascii_visualization()
        await test_mermaid_export()

        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED")
        print("=" * 60)

    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        raise
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(run_all_tests())


# ============================================================================
# RUN ALL TESTS
# ============================================================================


async def run_all_tests():
    """Run all test cases"""
    print("=" * 60)
    print("DAG EXECUTOR TEST SUITE")
    print("=" * 60)

    try:
        await test_sequential_execution()
        await test_parallel_execution()
        await test_failure_handling()
        await test_performance_metrics()
        await test_ascii_visualization()
        await test_mermaid_export()

        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED")
        print("=" * 60)

    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        raise
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(run_all_tests())
