"""
Plan Aggregator - Merge results from parallel agents into unified plan

Combines individual agent results from DAG execution into a single
aggregated plan for commit to K0 WAL.

Part of M8 Epic 8.1: Result Collection
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from agent_base import AgentResponse
from dag_executor import DAGMetrics
from dag_node import DAG, NodeStatus

logger = logging.getLogger(__name__)


# ============================================================================
# AGGREGATED PLAN DATA STRUCTURE
# ============================================================================


@dataclass
class AggregatedPlan:
    """
    Unified plan combining results from all DAG agents.

    This structure represents the complete execution outcome,
    including successes, failures, and blocked nodes.

    Attributes:
        flow_id: Unique identifier for this plan execution
        intent: Original user intent
        status: Overall plan status (completed/partial_success/failed)
        successful_steps: List of agent responses that completed successfully
        failed_steps: List of agent responses that failed
        blocked_steps: List of node_ids that couldn't execute (dependency failures)
        cancelled_steps: List of node_ids that were cancelled
        total_latency_ms: Total execution time
        agents_used: List of agent types used
        dag_metrics: Execution metrics from DAG executor
        timestamp: When plan was created
        metadata: Additional context and information
    """

    flow_id: str
    intent: str
    status: str  # "completed", "partial_success", "failed"
    successful_steps: List[AgentResponse] = field(default_factory=list)
    failed_steps: List[AgentResponse] = field(default_factory=list)
    blocked_steps: List[str] = field(default_factory=list)  # node_ids
    cancelled_steps: List[str] = field(default_factory=list)  # node_ids
    total_latency_ms: float = 0.0
    agents_used: List[str] = field(default_factory=list)
    dag_metrics: Optional[DAGMetrics] = None
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "flow_id": self.flow_id,
            "intent": self.intent,
            "status": self.status,
            "successful_steps": [s.to_dict() for s in self.successful_steps],
            "failed_steps": [s.to_dict() for s in self.failed_steps],
            "blocked_steps": self.blocked_steps,
            "cancelled_steps": self.cancelled_steps,
            "total_latency_ms": self.total_latency_ms,
            "agents_used": self.agents_used,
            "dag_metrics": self.dag_metrics.to_dict() if self.dag_metrics else None,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }

    def get_summary(self) -> str:
        """Generate human-readable summary"""
        total = len(self.successful_steps) + len(self.failed_steps) + len(self.blocked_steps)
        success_count = len(self.successful_steps)

        if self.status == "completed":
            return f"✅ All {total} steps completed successfully"
        elif self.status == "partial_success":
            return (
                f"⚠️  Partial success: {success_count}/{total} steps completed, "
                f"{len(self.failed_steps)} failed, {len(self.blocked_steps)} blocked"
            )
        else:  # failed
            return (
                f"❌ Plan failed: {len(self.failed_steps)} steps failed, "
                f"{len(self.blocked_steps)} blocked"
            )


# ============================================================================
# PLAN AGGREGATOR
# ============================================================================


class PlanAggregator:
    """
    Aggregates individual agent results into unified plan.

    Takes results from DAG execution and combines them into
    a single AggregatedPlan suitable for commit to K0 WAL.

    Responsibilities:
    - Collect results from all DAG nodes
    - Categorize by success/failure/blocked
    - Calculate overall plan status
    - Extract agent types used
    - Attach DAG metrics
    - Generate summary
    """

    def __init__(self):
        """Initialize plan aggregator"""
        logger.info("PlanAggregator initialized")

    def aggregate(
        self,
        dag: DAG,
        results: Dict[str, AgentResponse],
        intent: Optional[str] = None,
        flow_id: Optional[str] = None,
    ) -> AggregatedPlan:
        """
        Aggregate results from DAG execution into unified plan.

        Args:
            dag: Executed DAG with all node states
            results: Dict of node_id → AgentResponse
            intent: Original user intent (optional, extracted from DAG if not provided)
            flow_id: Flow identifier (optional, generated if not provided)

        Returns:
            AggregatedPlan with all results aggregated
        """
        logger.info(f"Aggregating results from DAG: {dag.dag_id}")

        # Extract flow_id (use dag_id if not provided)
        flow_id = flow_id or dag.dag_id

        # Extract intent from metadata if not provided
        intent = intent or dag.metadata.get("intent", "unknown")

        # Categorize results by status
        successful_steps: List[AgentResponse] = []
        failed_steps: List[AgentResponse] = []
        blocked_steps: List[str] = []
        cancelled_steps: List[str] = []
        agents_used: List[str] = []

        for node_id, node in dag.nodes.items():
            # Track agent types
            if node.agent_type not in agents_used:
                agents_used.append(node.agent_type)

            # Categorize by status
            if node.status == NodeStatus.COMPLETED:
                result = results.get(node_id)
                if result:
                    successful_steps.append(result)
                else:
                    logger.warning(f"Node {node_id} marked completed but no result found")

            elif node.status == NodeStatus.FAILED:
                result = results.get(node_id)
                if result:
                    failed_steps.append(result)
                else:
                    # Create error response for failed node without result
                    error_response = AgentResponse(
                        status="failed",
                        data={},
                        metadata={"node_id": node_id, "agent_type": node.agent_type},
                        error=node.error or "Unknown error",
                    )
                    failed_steps.append(error_response)

            elif node.status == NodeStatus.BLOCKED:
                blocked_steps.append(node_id)

            elif node.status == NodeStatus.CANCELLED:
                cancelled_steps.append(node_id)

        # Determine overall status
        total_nodes = len(dag.nodes)
        completed = len(successful_steps)
        failed = len(failed_steps)
        blocked = len(blocked_steps)

        if completed == total_nodes:
            status = "completed"
        elif failed > 0 or blocked > 0:
            if completed > 0:
                status = "partial_success"
            else:
                status = "failed"
        else:
            # All pending/running/cancelled
            status = "incomplete"

        # Get DAG metrics from metadata
        dag_metrics = dag.metadata.get("metrics")
        total_latency = dag_metrics.total_execution_ms if dag_metrics else 0.0

        # Create aggregated plan
        aggregated = AggregatedPlan(
            flow_id=flow_id,
            intent=intent,
            status=status,
            successful_steps=successful_steps,
            failed_steps=failed_steps,
            blocked_steps=blocked_steps,
            cancelled_steps=cancelled_steps,
            total_latency_ms=total_latency,
            agents_used=agents_used,
            dag_metrics=dag_metrics,
            metadata={
                "dag_id": dag.dag_id,
                "total_nodes": total_nodes,
                "completed_nodes": completed,
                "failed_nodes": failed,
                "blocked_nodes": blocked,
                "cancelled_nodes": len(cancelled_steps),
            },
        )

        logger.info(f"Plan aggregated: {aggregated.status} - {aggregated.get_summary()}")

        return aggregated

    def collect_results(self, dag: DAG) -> Dict[str, AgentResponse]:
        """
        Collect results from all DAG nodes.

        Extracts AgentResponse from each completed or failed node.

        Args:
            dag: Executed DAG

        Returns:
            Dict of node_id → AgentResponse
        """
        results: Dict[str, AgentResponse] = {}

        for node_id, node in dag.nodes.items():
            if node.result:
                results[node_id] = node.result

        return results

    def get_failed_node_details(self, dag: DAG) -> List[Dict[str, Any]]:
        """
        Extract details about failed nodes for debugging.

        Args:
            dag: Executed DAG

        Returns:
            List of dicts with failure details
        """
        failed_details = []

        for node_id, node in dag.nodes.items():
            if node.status == NodeStatus.FAILED:
                failed_details.append(
                    {
                        "node_id": node_id,
                        "agent_type": node.agent_type,
                        "error": node.error,
                        "duration_ms": node.duration_ms,
                        "user_input": node.user_input,
                    }
                )

        return failed_details

    def get_blocked_node_details(self, dag: DAG) -> List[Dict[str, Any]]:
        """
        Extract details about blocked nodes.

        Args:
            dag: Executed DAG

        Returns:
            List of dicts with blocked node details
        """
        blocked_details = []

        for node_id, node in dag.nodes.items():
            if node.status == NodeStatus.BLOCKED:
                blocked_details.append(
                    {
                        "node_id": node_id,
                        "agent_type": node.agent_type,
                        "dependencies": node.dependencies,
                        "error": node.error or "Blocked due to dependency failure",
                    }
                )

        return blocked_details


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================


def create_aggregated_plan_summary(aggregated: AggregatedPlan) -> str:
    """
    Create detailed summary of aggregated plan for logging/display.

    Args:
        aggregated: AggregatedPlan to summarize

    Returns:
        Multi-line formatted summary
    """
    lines = []
    lines.append("=" * 60)
    lines.append(f"AGGREGATED PLAN SUMMARY: {aggregated.flow_id}")
    lines.append("=" * 60)
    lines.append(f"Intent: {aggregated.intent}")
    lines.append(f"Status: {aggregated.status}")
    lines.append(f"Total Latency: {aggregated.total_latency_ms:.0f}ms")
    lines.append("")

    # Successful steps
    if aggregated.successful_steps:
        lines.append(f"✅ Successful Steps ({len(aggregated.successful_steps)}):")
        for step in aggregated.successful_steps:
            node_id = step.metadata.get("node_id", "unknown")
            agent_type = step.metadata.get("agent_type", "unknown")
            lines.append(f"  - {node_id}: {agent_type}")

    # Failed steps
    if aggregated.failed_steps:
        lines.append(f"\n❌ Failed Steps ({len(aggregated.failed_steps)}):")
        for step in aggregated.failed_steps:
            node_id = step.metadata.get("node_id", "unknown")
            agent_type = step.metadata.get("agent_type", "unknown")
            error = step.error or "Unknown error"
            lines.append(f"  - {node_id}: {agent_type} - {error}")

    # Blocked steps
    if aggregated.blocked_steps:
        lines.append(f"\n⊗ Blocked Steps ({len(aggregated.blocked_steps)}):")
        for node_id in aggregated.blocked_steps:
            lines.append(f"  - {node_id}")

    # Agents used
    lines.append(f"\nAgents Used: {', '.join(aggregated.agents_used)}")

    # DAG metrics
    if aggregated.dag_metrics:
        lines.append("\nDAG Metrics:")
        lines.append(f"  Max Parallelism: {aggregated.dag_metrics.max_parallelism}")
        lines.append(
            f"  Success Rate: {aggregated.dag_metrics.nodes_completed}/"
            f"{aggregated.dag_metrics.nodes_executed}"
        )

    lines.append("=" * 60)

    return "\n".join(lines)


# Example usage
if __name__ == "__main__":
    print("PlanAggregator module loaded successfully")
    print("Use PlanAggregator().aggregate(dag, results) to aggregate results")
