"""
DAG Node Data Structures - Foundation for parallel agent execution

Defines core data structures for representing agent execution units
and their dependencies in a Directed Acyclic Graph (DAG).

Part of M6 Epic 6.1: DAG Orchestrator Foundation
"""

# Import agent types
import sys
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent))

from agent_base import Agent, AgentResponse

# ============================================================================
# ENUMS FOR TYPE SAFETY
# ============================================================================


class NodeStatus(Enum):
    """Node execution status"""

    PENDING = "pending"  # Not yet started
    READY = "ready"  # Dependencies met, ready to run
    RUNNING = "running"  # Currently executing
    COMPLETED = "completed"  # Successfully finished
    FAILED = "failed"  # Execution failed
    BLOCKED = "blocked"  # Cannot execute due to dependency failure
    CANCELLED = "cancelled"  # Manually cancelled


class DependencyType(Enum):
    """Type of dependency between nodes"""

    DATA = "data_dependency"  # Node needs data from dependency
    SEQUENCE = "sequence_dependency"  # Node must run after dependency
    CONDITIONAL = "conditional"  # Node runs only if condition met


# ============================================================================
# CORE DATA STRUCTURES
# ============================================================================


@dataclass
class DAGNode:
    """
    Represents a single agent execution unit in the DAG.

    Each node corresponds to one agent that needs to be spawned and executed.
    Tracks execution state, dependencies, timing, and results.

    Attributes:
        node_id: Unique identifier for this node (e.g., "s1", "s2")
        agent_type: Type of agent to spawn (e.g., "travel_agent", "booking_agent")
        user_input: Original user request or derived task for this agent
        tools: Dictionary of tools available to this agent
        dependencies: List of node_ids this node depends on
        status: Current execution status (see NodeStatus enum)
        agent_instance: Reference to spawned Agent instance (set during execution)
        result: AgentResponse after execution completes
        clarification_questions: Questions asked by agent during execution
        start_time: Timestamp when execution started (seconds since epoch)
        end_time: Timestamp when execution completed (seconds since epoch)
        error: Error message if execution failed
        metadata: Additional metadata for agent context
    """

    node_id: str
    agent_type: str
    user_input: str
    tools: Dict[str, Any]
    dependencies: List[str] = field(default_factory=list)
    status: NodeStatus = NodeStatus.PENDING
    agent_instance: Optional[Agent] = None
    result: Optional[AgentResponse] = None
    clarification_questions: List[str] = field(default_factory=list)
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Convert string status to enum if needed"""
        if isinstance(self.status, str):
            self.status = NodeStatus(self.status)

    @property
    def duration_ms(self) -> Optional[float]:
        """Calculate execution duration in milliseconds"""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time) * 1000
        return None

    @property
    def is_ready(self) -> bool:
        """Check if node is ready to execute (all dependencies complete)"""
        return self.status == NodeStatus.READY

    @property
    def is_running(self) -> bool:
        """Check if node is currently executing"""
        return self.status == NodeStatus.RUNNING

    @property
    def is_complete(self) -> bool:
        """Check if node has finished execution (success or failure)"""
        return self.status in [
            NodeStatus.COMPLETED,
            NodeStatus.FAILED,
            NodeStatus.BLOCKED,
            NodeStatus.CANCELLED,
        ]

    @property
    def is_terminal(self) -> bool:
        """Check if node is in terminal state (cannot transition further)"""
        return self.is_complete

    def mark_ready(self):
        """Mark node as ready to execute"""
        if self.status == NodeStatus.PENDING:
            self.status = NodeStatus.READY

    def mark_running(self):
        """Mark node as running and record start time"""
        if self.status == NodeStatus.READY:
            self.status = NodeStatus.RUNNING
            self.start_time = time.time()

    def mark_completed(self, result: AgentResponse):
        """Mark node as completed successfully"""
        self.status = NodeStatus.COMPLETED
        self.result = result
        self.end_time = time.time()

    def mark_failed(self, error: str):
        """Mark node as failed with error message"""
        self.status = NodeStatus.FAILED
        self.error = error
        self.end_time = time.time()

    def mark_blocked(self, reason: str):
        """Mark node as blocked due to dependency failure"""
        self.status = NodeStatus.BLOCKED
        self.error = f"Blocked: {reason}"
        self.end_time = time.time()

    def mark_cancelled(self):
        """Mark node as cancelled"""
        self.status = NodeStatus.CANCELLED
        self.end_time = time.time()

    def add_clarification_question(self, question: str):
        """Record a clarification question asked by this agent"""
        self.clarification_questions.append(question)

    def to_dict(self) -> Dict[str, Any]:
        """Convert node to dictionary for serialization"""
        return {
            "node_id": self.node_id,
            "agent_type": self.agent_type,
            "user_input": self.user_input,
            "tools": list(self.tools.keys()) if self.tools else [],
            "dependencies": self.dependencies,
            "status": self.status.value,
            "clarification_questions": self.clarification_questions,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": self.duration_ms,
            "error": self.error,
            "result": (
                self.result.to_dict() if self.result and hasattr(self.result, "to_dict") else None
            ),
        }

    def __repr__(self) -> str:
        """String representation for debugging"""
        return f"DAGNode(id={self.node_id}, agent={self.agent_type}, status={self.status.value})"


@dataclass
class DAGEdge:
    """
    Represents a dependency edge between two nodes in the DAG.

    Edges define the execution order and data flow between agents.

    Attributes:
        from_node: Source node ID (dependency)
        to_node: Target node ID (dependent)
        dependency_type: Type of dependency relationship
        metadata: Additional metadata about the dependency
    """

    from_node: str
    to_node: str
    dependency_type: DependencyType = DependencyType.SEQUENCE
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Convert string dependency type to enum if needed"""
        if isinstance(self.dependency_type, str):
            self.dependency_type = DependencyType(self.dependency_type)

    def to_dict(self) -> Dict[str, Any]:
        """Convert edge to dictionary for serialization"""
        return {
            "from_node": self.from_node,
            "to_node": self.to_node,
            "dependency_type": self.dependency_type.value,
            "metadata": self.metadata,
        }

    def __repr__(self) -> str:
        """String representation for debugging"""
        return f"DAGEdge({self.from_node} → {self.to_node}, type={self.dependency_type.value})"


# ============================================================================
# DAG CONTAINER
# ============================================================================


@dataclass
class DAG:
    """
    Container for entire DAG structure.

    Manages collection of nodes and edges representing complete execution plan.
    Provides utilities for querying and manipulating the graph.

    Attributes:
        dag_id: Unique identifier for this DAG
        intent: Original user intent this DAG represents
        nodes: Dictionary of node_id → DAGNode
        edges: List of DAGEdge objects
        metadata: Additional metadata about the DAG
    """

    dag_id: str
    intent: str
    nodes: Dict[str, DAGNode] = field(default_factory=dict)
    edges: List[DAGEdge] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add_node(self, node: DAGNode):
        """Add a node to the DAG"""
        self.nodes[node.node_id] = node

    def add_edge(self, edge: DAGEdge):
        """Add an edge to the DAG"""
        self.edges.append(edge)

    def get_node(self, node_id: str) -> Optional[DAGNode]:
        """Get node by ID"""
        return self.nodes.get(node_id)

    def get_dependencies(self, node_id: str) -> List[DAGNode]:
        """Get all nodes that the given node depends on"""
        node = self.get_node(node_id)
        if not node:
            return []

        deps = []
        for dep_id in node.dependencies:
            dep_node = self.get_node(dep_id)
            if dep_node:
                deps.append(dep_node)
        return deps

    def get_dependents(self, node_id: str) -> List[DAGNode]:
        """Get all nodes that depend on the given node"""
        dependents = []
        for edge in self.edges:
            if edge.from_node == node_id:
                dependent = self.get_node(edge.to_node)
                if dependent:
                    dependents.append(dependent)
        return dependents

    def get_root_nodes(self) -> List[DAGNode]:
        """Get all nodes with no dependencies (entry points)"""
        return [node for node in self.nodes.values() if not node.dependencies]

    def get_leaf_nodes(self) -> List[DAGNode]:
        """Get all nodes with no dependents (exit points)"""
        nodes_with_dependents = {edge.from_node for edge in self.edges}
        return [node for node in self.nodes.values() if node.node_id not in nodes_with_dependents]

    def get_ready_nodes(self) -> List[DAGNode]:
        """
        Get all nodes that are ready to execute.

        A node is ready if:
        1. Status is READY
        2. All dependencies are COMPLETED (not failed or blocked)
        """
        ready = []
        for node in self.nodes.values():
            # Skip blocked nodes
            if node.status == NodeStatus.BLOCKED:
                continue

            if node.status == NodeStatus.PENDING:
                # Check if all dependencies are complete
                deps = self.get_dependencies(node.node_id)

                # If any dependency failed or blocked, this node should NOT be ready
                if any(dep.status in [NodeStatus.FAILED, NodeStatus.BLOCKED] for dep in deps):
                    continue

                # All dependencies must be completed
                if all(dep.status == NodeStatus.COMPLETED for dep in deps):
                    node.mark_ready()
                    ready.append(node)
            elif node.status == NodeStatus.READY:
                # Double-check that no dependencies have since failed
                deps = self.get_dependencies(node.node_id)
                if not any(dep.status in [NodeStatus.FAILED, NodeStatus.BLOCKED] for dep in deps):
                    ready.append(node)
        return ready

    def get_running_nodes(self) -> List[DAGNode]:
        """Get all nodes currently executing"""
        return [node for node in self.nodes.values() if node.is_running]

    def get_completed_nodes(self) -> List[DAGNode]:
        """Get all nodes that completed successfully"""
        return [node for node in self.nodes.values() if node.status == NodeStatus.COMPLETED]

    def get_failed_nodes(self) -> List[DAGNode]:
        """Get all nodes that failed"""
        return [node for node in self.nodes.values() if node.status == NodeStatus.FAILED]

    def get_blocked_nodes(self) -> List[DAGNode]:
        """Get all nodes that are blocked"""
        return [node for node in self.nodes.values() if node.status == NodeStatus.BLOCKED]

    def is_complete(self) -> bool:
        """Check if all nodes have reached terminal state"""
        return all(node.is_terminal for node in self.nodes.values())

    def block_dependents(self, node_id: str, reason: str):
        """
        Mark all dependent nodes as blocked.

        Used when a node fails - dependents cannot execute.
        """
        for dependent in self.get_dependents(node_id):
            if not dependent.is_terminal:
                dependent.mark_blocked(reason)
                # Recursively block downstream nodes
                self.block_dependents(dependent.node_id, f"Upstream dependency {node_id} failed")

    def get_execution_summary(self) -> Dict[str, Any]:
        """Get summary of DAG execution state"""
        total_nodes = len(self.nodes)
        completed = len(self.get_completed_nodes())
        failed = len(self.get_failed_nodes())
        blocked = len(self.get_blocked_nodes())
        running = len(self.get_running_nodes())
        pending = sum(
            1 for n in self.nodes.values() if n.status in [NodeStatus.PENDING, NodeStatus.READY]
        )

        return {
            "dag_id": self.dag_id,
            "intent": self.intent,
            "total_nodes": total_nodes,
            "completed": completed,
            "failed": failed,
            "blocked": blocked,
            "running": running,
            "pending": pending,
            "is_complete": self.is_complete(),
            "success_rate": f"{(completed/total_nodes)*100:.1f}%" if total_nodes > 0 else "0%",
        }

    def to_dict(self) -> Dict[str, Any]:
        """Convert DAG to dictionary for serialization"""
        return {
            "dag_id": self.dag_id,
            "intent": self.intent,
            "nodes": {nid: node.to_dict() for nid, node in self.nodes.items()},
            "edges": [edge.to_dict() for edge in self.edges],
            "summary": self.get_execution_summary(),
            "metadata": self.metadata,
        }

    def __repr__(self) -> str:
        """String representation for debugging"""
        return f"DAG(id={self.dag_id}, nodes={len(self.nodes)}, edges={len(self.edges)})"


# ============================================================================
# EXCEPTIONS
# ============================================================================


class DAGError(Exception):
    """Base exception for DAG-related errors"""

    pass


class CircularDependencyError(DAGError):
    """Raised when circular dependency detected in DAG"""

    def __init__(self, cycle: List[str]):
        self.cycle = cycle
        cycle_str = " → ".join(cycle)
        super().__init__(f"Circular dependency detected: {cycle_str}")


class InvalidNodeError(DAGError):
    """Raised when node operation is invalid"""

    pass


class InvalidEdgeError(DAGError):
    """Raised when edge operation is invalid"""

    pass


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================


def create_dag_from_steps(dag_id: str, intent: str, steps: List[Dict[str, Any]]) -> DAG:
    """
    Quick utility to create DAG from list of steps.

    Args:
        dag_id: Unique DAG identifier
        intent: User intent
        steps: List of step dicts with 'id', 'agent_type', 'tool', 'needs'

    Returns:
        DAG instance with nodes and edges
    """
    dag = DAG(dag_id=dag_id, intent=intent)

    # Create nodes
    for step in steps:
        tool_name = step.get("tool")
        node = DAGNode(
            node_id=step.get("id", f"step_{len(dag.nodes)}"),
            agent_type=step.get("agent", step.get("agent_type", "generic_agent")),
            user_input=step.get("description", intent),
            tools={tool_name: {}} if tool_name else {},
            dependencies=step.get("needs", []),
        )
        dag.add_node(node)

    # Create edges from dependencies
    for node in dag.nodes.values():
        for dep_id in node.dependencies:
            edge = DAGEdge(
                from_node=dep_id, to_node=node.node_id, dependency_type=DependencyType.SEQUENCE
            )
            dag.add_edge(edge)

    return dag


def validate_dag(dag: DAG) -> bool:
    """
    Validate DAG structure.

    Checks:
    1. All node dependencies exist
    2. No circular dependencies
    3. No duplicate edges

    Raises:
        InvalidNodeError: If node references missing dependency
        CircularDependencyError: If cycle detected
        InvalidEdgeError: If duplicate edge found

    Returns:
        True if valid
    """
    # Check all dependencies exist
    for node in dag.nodes.values():
        for dep_id in node.dependencies:
            if dep_id not in dag.nodes:
                raise InvalidNodeError(f"Node {node.node_id} depends on non-existent node {dep_id}")

    # Check for circular dependencies (will implement in dag_builder.py)
    # This is a placeholder for now

    # Check for duplicate edges
    edge_set = set()
    for edge in dag.edges:
        edge_key = (edge.from_node, edge.to_node)
        if edge_key in edge_set:
            raise InvalidEdgeError(f"Duplicate edge: {edge.from_node} → {edge.to_node}")
        edge_set.add(edge_key)

    return True


# ============================================================================
# EXAMPLE USAGE (for testing)
# ============================================================================

if __name__ == "__main__":
    # Example: Create simple DAG
    print("Creating example DAG...")

    steps = [
        {"id": "s1", "agent": "query_agent", "tool": "restaurants", "needs": []},
        {"id": "s2", "agent": "booking_agent", "tool": "reservations", "needs": ["s1"]},
        {"id": "s3", "agent": "messenger_agent", "tool": "messaging", "needs": ["s2"]},
    ]

    dag = create_dag_from_steps(dag_id="test_dag_001", intent="book_dinner_and_notify", steps=steps)

    print(f"\n{dag}")
    print(f"Root nodes: {[n.node_id for n in dag.get_root_nodes()]}")
    print(f"Leaf nodes: {[n.node_id for n in dag.get_leaf_nodes()]}")
    print(f"Ready nodes: {[n.node_id for n in dag.get_ready_nodes()]}")

    print("\nExecution summary:")
    for key, value in dag.get_execution_summary().items():
        print(f"  {key}: {value}")

    print("\n✅ DAG Node data structures created successfully!")
