"""
DAG Executor - Parallel agent execution engine

Executes DAG nodes in parallel while respecting dependencies.
Handles agent failures gracefully and tracks execution metrics.

Part of M6 Epic 6.2: Parallel Executor
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from agent_base import Agent, AgentResponse
from agent_spawn_wrapper import AgentSpawnWrapper

# Import DAG structures
from dag_node import DAG, DAGError, DAGNode, NodeStatus

logger = logging.getLogger(__name__)


# ============================================================================
# EXECUTION METRICS
# ============================================================================


@dataclass
class DAGMetrics:
    """
    Execution metrics for DAG run.

    Tracks performance, parallelism, and success rates.
    """

    dag_id: str
    total_execution_ms: float
    nodes_executed: int
    nodes_completed: int
    nodes_failed: int
    nodes_blocked: int
    nodes_cancelled: int
    max_parallelism: int  # Max concurrent nodes at any point
    node_latencies: Dict[str, float] = field(default_factory=dict)  # node_id → latency_ms
    start_time: Optional[float] = None
    end_time: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary"""
        return {
            "dag_id": self.dag_id,
            "total_execution_ms": self.total_execution_ms,
            "nodes_executed": self.nodes_executed,
            "nodes_completed": self.nodes_completed,
            "nodes_failed": self.nodes_failed,
            "nodes_blocked": self.nodes_blocked,
            "nodes_cancelled": self.nodes_cancelled,
            "max_parallelism": self.max_parallelism,
            "success_rate": (
                f"{(self.nodes_completed/self.nodes_executed)*100:.1f}%"
                if self.nodes_executed > 0
                else "0%"
            ),
            "node_latencies": self.node_latencies,
        }


# ============================================================================
# DAG EXECUTOR
# ============================================================================


class DAGExecutor:
    """
    Executes DAG nodes in parallel with dependency respect.

    Features:
    - Parallel execution of independent nodes
    - Dependency-aware scheduling
    - Graceful failure handling (isolated failures)
    - Performance metrics tracking
    - Question queue support (for M7)

    Algorithm:
    1. Find root nodes (no dependencies)
    2. Spawn agents for roots in parallel
    3. On completion, mark node as done
    4. Find newly unblocked nodes
    5. Spawn unblocked nodes
    6. Repeat until DAG complete
    """

    def __init__(
        self,
        agent_spawn_wrapper: AgentSpawnWrapper,
        question_queue: Optional[Any] = None,
        max_concurrent_nodes: int = 10,
    ):
        """
        Initialize DAG executor.

        Args:
            agent_spawn_wrapper: Factory for spawning agents
            question_queue: Optional queue for agent clarifications (M7)
            max_concurrent_nodes: Max nodes to run in parallel
        """
        self.agent_spawn_wrapper = agent_spawn_wrapper
        self.question_queue = question_queue
        self.max_concurrent_nodes = max_concurrent_nodes

        # Execution state
        self.running_tasks: Dict[str, asyncio.Task] = {}
        self.task_to_node: Dict[asyncio.Task, str] = {}
        self.current_parallelism = 0
        self.max_parallelism_seen = 0

    async def execute(
        self, dag: DAG, user_id: str = "user", user_profile: Optional[Dict[str, Any]] = None
    ) -> Dict[str, AgentResponse]:
        """
        Execute DAG nodes in parallel with dependency respect.

        Args:
            dag: DAG to execute
            user_id: User identifier
            user_profile: User preferences/history

        Returns:
            Dictionary of node_id → AgentResponse

        Raises:
            DAGError: If execution fails critically
        """
        logger.info(f"Starting DAG execution: {dag.dag_id}")
        start_time = time.time()

        results: Dict[str, AgentResponse] = {}

        try:
            # Main execution loop
            while not dag.is_complete():
                # Find nodes ready to run
                ready_nodes = dag.get_ready_nodes()

                # Respect max concurrency limit
                available_slots = self.max_concurrent_nodes - len(self.running_tasks)
                nodes_to_spawn = ready_nodes[:available_slots]

                # Spawn agents for ready nodes
                for node in nodes_to_spawn:
                    await self._spawn_node(node, dag, user_id, user_profile)

                # If no running tasks and no ready nodes, we're stuck
                if not self.running_tasks:
                    if not dag.is_complete():
                        # This shouldn't happen with valid DAG
                        blocked_nodes = [n.node_id for n in dag.nodes.values() if not n.is_complete]
                        raise DAGError(
                            f"DAG execution stuck. No running tasks but DAG not complete. "
                            f"Blocked nodes: {blocked_nodes}"
                        )
                    break

                # Wait for at least one task to complete
                done, pending = await asyncio.wait(
                    self.running_tasks.values(), return_when=asyncio.FIRST_COMPLETED
                )

                # Process completed tasks
                for task in done:
                    node_id = self.task_to_node[task]
                    node = dag.get_node(node_id)

                    if node:
                        try:
                            result = await task
                            results[node_id] = result

                            # Mark node as completed or failed based on result
                            if result.status == "completed":
                                node.mark_completed(result)
                                logger.info(f"Node {node_id} completed successfully")
                            elif result.status == "error" or result.status == "failed":
                                node.mark_failed(result.error or "Unknown error")
                                logger.error(f"Node {node_id} failed: {result.error}")
                                # Block dependent nodes
                                print(f"DEBUG: Blocking dependents of {node_id}")
                                blocked_count = len(dag.get_dependents(node_id))
                                print(f"DEBUG: Found {blocked_count} dependents to block")
                                dag.block_dependents(node_id, f"Dependency {node_id} failed")
                            else:
                                # Other statuses (needs_clarification) - treat as partial completion
                                node.mark_completed(result)
                                logger.info(
                                    f"Node {node_id} completed with status: {result.status}"
                                )

                        except Exception as e:
                            logger.error(f"Task for node {node_id} raised exception: {e}")
                            node.mark_failed(str(e))
                            dag.block_dependents(
                                node_id, f"Dependency {node_id} failed with exception"
                            )

                            # Create error response
                            results[node_id] = AgentResponse(
                                agent_id=(
                                    node.agent_instance.agent_id if node.agent_instance else node_id
                                ),
                                agent_type=node.agent_type,
                                status="error",
                                error=str(e),
                            )

                    # Cleanup task tracking
                    del self.running_tasks[node_id]
                    del self.task_to_node[task]
                    self.current_parallelism = len(self.running_tasks)

            # Execution complete
            end_time = time.time()
            execution_ms = (end_time - start_time) * 1000

            # Build metrics
            metrics = self._build_metrics(dag, start_time, end_time)

            logger.info(
                f"DAG execution complete: {dag.dag_id} "
                f"({metrics.nodes_completed}/{metrics.nodes_executed} succeeded, "
                f"{execution_ms:.1f}ms, max_parallelism={metrics.max_parallelism})"
            )

            # Attach metrics to DAG
            dag.metadata["metrics"] = metrics.to_dict()

            return results

        except Exception as e:
            logger.error(f"DAG execution failed: {e}")
            raise

    async def _spawn_node(
        self, node: DAGNode, dag: DAG, user_id: str, user_profile: Optional[Dict[str, Any]]
    ):
        """
        Spawn agent for node and start execution task.

        Args:
            node: Node to execute
            dag: Parent DAG
            user_id: User identifier
            user_profile: User preferences
        """
        logger.info(f"Spawning agent for node: {node.node_id} (type={node.agent_type})")

        # Mark node as running
        node.mark_running()

        # Spawn agent
        agent = await self.agent_spawn_wrapper.spawn_agent(
            agent_type=node.agent_type,
            user_input=node.user_input,
            tools=node.tools,
            user_id=user_id,
            user_profile=user_profile or {},
            conversation_history=[],
            clarification_history=[],
        )

        # Store agent reference
        node.agent_instance = agent

        # Attach question queue if available
        if self.question_queue:
            agent.question_queue = self.question_queue

        # Create execution task
        task = asyncio.create_task(self._execute_node(node, agent))

        # Track task
        self.running_tasks[node.node_id] = task
        self.task_to_node[task] = node.node_id

        # Update parallelism tracking
        self.current_parallelism = len(self.running_tasks)
        self.max_parallelism_seen = max(self.max_parallelism_seen, self.current_parallelism)

    async def _execute_node(self, node: DAGNode, agent: Agent) -> AgentResponse:
        """
        Execute single node (agent).

        Args:
            node: Node being executed
            agent: Spawned agent instance

        Returns:
            AgentResponse from agent execution
        """
        try:
            logger.info(f"Executing node: {node.node_id}")

            # Execute agent
            result = await agent.execute(agent.context)

            # Track clarification questions
            if result.clarification_question:
                node.add_clarification_question(result.clarification_question)

            logger.info(
                f"Node {node.node_id} execution complete: "
                f"status={result.status}, latency={result.latency_ms:.1f}ms"
            )

            return result

        except Exception as e:
            logger.error(f"Node {node.node_id} execution failed: {e}")

            # Return error response
            return AgentResponse(
                agent_id=agent.agent_id,
                agent_type=agent.agent_type,
                status="error",
                error=str(e),
                latency_ms=0.0,
            )

    def _build_metrics(self, dag: DAG, start_time: float, end_time: float) -> DAGMetrics:
        """
        Build execution metrics from completed DAG.

        Args:
            dag: Completed DAG
            start_time: Execution start time
            end_time: Execution end time

        Returns:
            DAGMetrics with full execution summary
        """
        node_latencies = {}
        for node in dag.nodes.values():
            if node.duration_ms:
                node_latencies[node.node_id] = node.duration_ms

        metrics = DAGMetrics(
            dag_id=dag.dag_id,
            total_execution_ms=(end_time - start_time) * 1000,
            nodes_executed=len(dag.nodes),
            nodes_completed=len(dag.get_completed_nodes()),
            nodes_failed=len(dag.get_failed_nodes()),
            nodes_blocked=len(dag.get_blocked_nodes()),
            nodes_cancelled=sum(1 for n in dag.nodes.values() if n.status == NodeStatus.CANCELLED),
            max_parallelism=self.max_parallelism_seen,
            node_latencies=node_latencies,
            start_time=start_time,
            end_time=end_time,
        )

        return metrics


# ============================================================================
# EXAMPLE USAGE (for testing with mock agents)
# ============================================================================

if __name__ == "__main__":
    print("DAG Executor requires agent infrastructure to test.")
    print("Run full integration tests in test_dag_executor.py")
    print("\n✅ DAG Executor implementation complete!")
