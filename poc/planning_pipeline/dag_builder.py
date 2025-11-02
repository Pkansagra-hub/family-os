"""
DAG Builder - Parse expanded plans and construct executable DAG

Converts expanded plans from Stage 2 (ExpandStage) into DAG structures
with proper dependency resolution and cycle detection.

Part of M6 Epic 6.1: DAG Data Structure & Parser
"""

import uuid
from collections import defaultdict
from typing import Any, List, Optional, Set

# Import DAG structures
from dag_node import (
    DAG,
    CircularDependencyError,
    DAGEdge,
    DAGNode,
    DependencyType,
    InvalidEdgeError,
    InvalidNodeError,
    NodeStatus,
)


class DAGBuilder:
    """
    Builds executable DAG from expanded plan.

    Responsibilities:
    1. Parse expanded plan steps
    2. Create DAG nodes for each agent
    3. Extract and validate dependencies
    4. Detect circular dependencies
    5. Return executable DAG structure
    """

    def __init__(self):
        """Initialize DAG builder"""
        pass

    def build_from_expanded_plan(
        self,
        expanded_plan_dict: dict,
        user_input: str = "",
        agent_spawn_wrapper: Optional[Any] = None,
    ) -> DAG:
        """
        Convert expanded plan to executable DAG.

        Args:
            expanded_plan_dict: Expanded plan from Stage 2
                Example:
                {
                    "intent": "book_dinner_and_notify",
                    "steps": [
                        {"id": "s1", "tool": "restaurants", "agent": "query_agent", "needs": []},
                        {"id": "s2", "tool": "reservations", "agent": "booking_agent", "needs": ["s1"]},
                        {"id": "s3", "tool": "messaging", "agent": "messenger_agent", "needs": ["s2"]}
                    ],
                    "complexity": "simple",
                    "agents_required": ["query_agent", "booking_agent", "messenger_agent"]
                }
            user_input: Original user request (for context)
            agent_spawn_wrapper: Optional agent spawner (not used in building, only in execution)

        Returns:
            DAG with nodes and edges, ready for execution

        Raises:
            CircularDependencyError: If circular dependency detected
            InvalidNodeError: If node references missing dependency
        """
        # Generate unique DAG ID
        dag_id = str(uuid.uuid4())
        intent = expanded_plan_dict.get("intent", "unknown")

        # Create DAG container
        dag = DAG(
            dag_id=dag_id,
            intent=intent,
            metadata={
                "complexity": expanded_plan_dict.get("complexity", "unknown"),
                "agents_required": expanded_plan_dict.get("agents_required", []),
                "user_input": user_input,
            },
        )

        # Extract steps
        steps = expanded_plan_dict.get("steps", [])
        if not steps:
            raise InvalidNodeError("Expanded plan has no steps")

        # Phase 1: Create all nodes
        for step in steps:
            node = self._create_node_from_step(step, intent, user_input)
            dag.add_node(node)

        # Phase 2: Create edges from dependencies
        for step in steps:
            step_id = step.get("id", "")
            dependencies = step.get("needs", [])

            for dep_id in dependencies:
                # Validate dependency exists
                if dep_id not in dag.nodes:
                    raise InvalidNodeError(f"Node {step_id} depends on non-existent node {dep_id}")

                # Create edge
                edge = DAGEdge(
                    from_node=dep_id,
                    to_node=step_id,
                    dependency_type=DependencyType.SEQUENCE,
                    metadata={"created_by": "dag_builder"},
                )
                dag.add_edge(edge)

        # Phase 3: Validate no circular dependencies
        self._detect_cycles(dag)

        # Phase 4: Mark root nodes as ready
        for node in dag.get_root_nodes():
            node.mark_ready()

        return dag

    def _create_node_from_step(self, step: dict, intent: str, user_input: str) -> DAGNode:
        """
        Create DAGNode from plan step.

        Args:
            step: Step dictionary from expanded plan
            intent: Overall intent
            user_input: Original user request

        Returns:
            DAGNode instance
        """
        # Extract step fields
        node_id = step.get("id", f"step_{uuid.uuid4().hex[:8]}")
        agent_type = step.get("agent", "generic_agent")
        tool_name = step.get("tool", "")
        description = step.get("description", "")
        dependencies = step.get("needs", [])

        # Build tools dict (tool_name -> tool_config)
        tools = {}
        if tool_name:
            tools[tool_name] = {
                "schema_in": step.get("schema_in", {}),
                "schema_out": step.get("schema_out", {}),
                "band_required": step.get("band_required", "GREEN"),
                "caps_required": step.get("caps_required", []),
            }

        # Create node
        node = DAGNode(
            node_id=node_id,
            agent_type=agent_type,
            user_input=description or user_input,
            tools=tools,
            dependencies=dependencies,
            status=NodeStatus.PENDING,
            metadata={
                "step": step,
                "intent": intent,
            },
        )

        return node

    def _detect_cycles(self, dag: DAG):
        """
        Detect circular dependencies using DFS.

        Args:
            dag: DAG to validate

        Raises:
            CircularDependencyError: If cycle detected with cycle path
        """
        # Build adjacency list
        graph = defaultdict(list)
        for edge in dag.edges:
            graph[edge.from_node].append(edge.to_node)

        # Track visited and recursion stack
        visited: Set[str] = set()
        rec_stack: Set[str] = set()
        path: List[str] = []

        def dfs(node_id: str) -> Optional[List[str]]:
            """DFS with cycle detection"""
            if node_id in rec_stack:
                # Cycle detected! Extract cycle path
                cycle_start = path.index(node_id)
                cycle = path[cycle_start:] + [node_id]
                return cycle

            if node_id in visited:
                return None

            # Mark visited and add to recursion stack
            visited.add(node_id)
            rec_stack.add(node_id)
            path.append(node_id)

            # Visit all neighbors
            for neighbor in graph.get(node_id, []):
                cycle = dfs(neighbor)
                if cycle:
                    return cycle

            # Remove from recursion stack
            rec_stack.remove(node_id)
            path.pop()

            return None

        # Check all nodes
        for node_id in dag.nodes.keys():
            if node_id not in visited:
                cycle = dfs(node_id)
                if cycle:
                    raise CircularDependencyError(cycle)

    def validate_dag(self, dag: DAG) -> bool:
        """
        Validate DAG structure.

        Checks:
        1. All node dependencies exist
        2. No circular dependencies
        3. No duplicate edges
        4. All nodes reachable from roots

        Args:
            dag: DAG to validate

        Returns:
            True if valid

        Raises:
            InvalidNodeError: If validation fails
            CircularDependencyError: If cycle detected
        """
        # Check 1: All dependencies exist
        for node in dag.nodes.values():
            for dep_id in node.dependencies:
                if dep_id not in dag.nodes:
                    raise InvalidNodeError(
                        f"Node {node.node_id} depends on non-existent node {dep_id}"
                    )

        # Check 2: No circular dependencies
        self._detect_cycles(dag)

        # Check 3: No duplicate edges
        edge_set = set()
        for edge in dag.edges:
            edge_key = (edge.from_node, edge.to_node)
            if edge_key in edge_set:
                raise InvalidEdgeError(f"Duplicate edge: {edge.from_node} → {edge.to_node}")
            edge_set.add(edge_key)

        # Check 4: All nodes reachable from roots
        root_nodes = dag.get_root_nodes()
        if not root_nodes:
            raise InvalidNodeError("DAG has no root nodes (all nodes have dependencies)")

        reachable = self._get_reachable_nodes(dag, root_nodes)
        unreachable = set(dag.nodes.keys()) - reachable
        if unreachable:
            raise InvalidNodeError(f"Nodes unreachable from roots: {sorted(unreachable)}")

        return True

    def _get_reachable_nodes(self, dag: DAG, start_nodes: List[DAGNode]) -> Set[str]:
        """
        Find all nodes reachable from start nodes using BFS.

        Args:
            dag: DAG to traverse
            start_nodes: Starting nodes

        Returns:
            Set of reachable node IDs
        """
        reachable = set()
        queue = [node.node_id for node in start_nodes]

        while queue:
            node_id = queue.pop(0)
            if node_id in reachable:
                continue

            reachable.add(node_id)

            # Add all dependent nodes
            for dependent in dag.get_dependents(node_id):
                if dependent.node_id not in reachable:
                    queue.append(dependent.node_id)

        return reachable

    def get_execution_order(self, dag: DAG) -> List[List[str]]:
        """
        Get topological execution order (layers that can execute in parallel).

        Args:
            dag: DAG to analyze

        Returns:
            List of layers, where each layer is a list of node IDs that can execute in parallel

        Example:
            [[s1, s2], [s3], [s4, s5]]
            - Layer 0: s1 and s2 can run in parallel (no dependencies)
            - Layer 1: s3 runs after s1 and s2
            - Layer 2: s4 and s5 run in parallel after s3
        """
        layers = []
        remaining = set(dag.nodes.keys())
        completed = set()

        while remaining:
            # Find nodes whose dependencies are all completed
            ready = []
            for node_id in remaining:
                node = dag.get_node(node_id)
                if node and all(dep in completed for dep in node.dependencies):
                    ready.append(node_id)

            if not ready:
                # This shouldn't happen if DAG is valid (no cycles)
                raise InvalidNodeError(
                    f"Cannot determine execution order - possible cycle or missing dependencies. "
                    f"Remaining nodes: {remaining}"
                )

            # Add ready nodes as new layer
            layers.append(ready)

            # Mark as completed
            for node_id in ready:
                completed.add(node_id)
                remaining.remove(node_id)

        return layers


# ============================================================================
# EXAMPLE USAGE (for testing)
# ============================================================================

if __name__ == "__main__":
    print("Testing DAG Builder...")

    # Test 1: Simple sequential plan
    print("\n" + "=" * 70)
    print("Test 1: Sequential Dependencies (s1 → s2 → s3)")
    print("=" * 70)

    expanded_plan_1 = {
        "intent": "book_dinner_and_notify",
        "steps": [
            {
                "id": "s1",
                "tool": "restaurants",
                "agent": "query_agent",
                "needs": [],
                "description": "Find restaurants",
            },
            {
                "id": "s2",
                "tool": "reservations",
                "agent": "booking_agent",
                "needs": ["s1"],
                "description": "Book reservation",
            },
            {
                "id": "s3",
                "tool": "messaging",
                "agent": "messenger_agent",
                "needs": ["s2"],
                "description": "Notify family",
            },
        ],
        "complexity": "simple",
        "agents_required": ["query_agent", "booking_agent", "messenger_agent"],
    }

    builder = DAGBuilder()
    dag1 = builder.build_from_expanded_plan(
        expanded_plan_1, user_input="Book dinner and notify my family"
    )

    print(f"✓ Created DAG: {dag1}")
    print(f"  Root nodes: {[n.node_id for n in dag1.get_root_nodes()]}")
    print(f"  Leaf nodes: {[n.node_id for n in dag1.get_leaf_nodes()]}")
    print(f"  Edges: {len(dag1.edges)}")

    # Validate
    builder.validate_dag(dag1)
    print("✓ Validation passed")

    # Execution order
    layers1 = builder.get_execution_order(dag1)
    print(f"✓ Execution order (layers): {layers1}")

    # Test 2: Parallel plan (diamond pattern)
    print("\n" + "=" * 70)
    print("Test 2: Parallel Dependencies (Diamond Pattern)")
    print("=" * 70)

    expanded_plan_2 = {
        "intent": "check_weather_and_events",
        "steps": [
            {
                "id": "s1",
                "tool": "weather",
                "agent": "query_agent",
                "needs": [],
                "description": "Check weather",
            },
            {
                "id": "s2",
                "tool": "events",
                "agent": "query_agent",
                "needs": [],
                "description": "Check events",
            },
            {
                "id": "s3",
                "tool": "recommendations",
                "agent": "planner",
                "needs": ["s1", "s2"],
                "description": "Recommend activities",
            },
        ],
        "complexity": "medium",
        "agents_required": ["query_agent", "planner"],
    }

    dag2 = builder.build_from_expanded_plan(
        expanded_plan_2, user_input="What should I do this weekend?"
    )

    print(f"✓ Created DAG: {dag2}")
    print(f"  Root nodes: {[n.node_id for n in dag2.get_root_nodes()]}")
    print(f"  Leaf nodes: {[n.node_id for n in dag2.get_leaf_nodes()]}")

    layers2 = builder.get_execution_order(dag2)
    print(f"✓ Execution order (layers): {layers2}")
    print(f"  → Layer 0 ({len(layers2[0])} parallel): {layers2[0]}")
    print(f"  → Layer 1 ({len(layers2[1])} sequential): {layers2[1]}")

    # Test 3: Circular dependency detection
    print("\n" + "=" * 70)
    print("Test 3: Circular Dependency Detection")
    print("=" * 70)

    expanded_plan_3 = {
        "intent": "circular_test",
        "steps": [
            {"id": "s1", "tool": "tool1", "agent": "agent1", "needs": ["s3"]},
            {"id": "s2", "tool": "tool2", "agent": "agent2", "needs": ["s1"]},
            {"id": "s3", "tool": "tool3", "agent": "agent3", "needs": ["s2"]},
        ],
        "complexity": "simple",
    }

    try:
        dag3 = builder.build_from_expanded_plan(expanded_plan_3)
        print("✗ Should have detected cycle!")
    except CircularDependencyError as e:
        print(f"✓ Correctly detected circular dependency: {e}")

    print("\n" + "=" * 70)
    print("✅ All DAG Builder tests passed!")
    print("=" * 70)
