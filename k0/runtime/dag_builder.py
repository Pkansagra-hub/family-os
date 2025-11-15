"""
DAG Builder - Construct Execution Graph from Pipeline Specs

Builds a topologically sorted execution plan from declarative pipeline specifications.
Validates dependencies, detects cycles, and optimizes for parallel execution.

Related:
- MIGRATION_PLAN.md: Phase 2 - DAG Builder
- k0/runtime/schemas.py: PipelineSpec, StageSpec definitions
- k0/runtime/pipeline_runner.py: Consumes DAG for execution
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Set

from .schemas import PipelineSpec, StageID, StageSpec

logger = logging.getLogger(__name__)


@dataclass
class DAGNode:
    """
    A node in the execution DAG.

    Represents a single stage with its dependencies and metadata.
    """

    stage: StageSpec
    dependencies: Set[StageID]  # Stages that must complete before this
    dependents: Set[StageID]  # Stages that depend on this
    level: int = 0  # Execution level (for parallel scheduling)


class DAGCycleError(Exception):
    """Raised when DAG contains a cycle."""

    pass


class DAGValidationError(Exception):
    """Raised when DAG structure is invalid."""

    pass


class DAG:
    """
    Directed Acyclic Graph representing pipeline execution order.

    Provides:
    - Topological ordering for sequential execution
    - Level-based grouping for parallel execution
    - Dependency tracking for validation
    """

    def __init__(self, spec: PipelineSpec) -> None:
        """
        Build DAG from pipeline specification.

        Args:
            spec: Validated PipelineSpec

        Raises:
            DAGCycleError: If cycles detected
            DAGValidationError: If dependencies invalid
        """
        self.pipeline_id = spec.pipeline_id
        self.nodes: Dict[StageID, DAGNode] = {}
        self._build_graph(spec)
        self._compute_levels()

    def _build_graph(self, spec: PipelineSpec) -> None:
        """Build dependency graph from stages."""
        # First pass: Create all nodes
        for stage in spec.dag:
            self.nodes[stage.id] = DAGNode(
                stage=stage,
                dependencies=set(stage.after),
                dependents=set(),
            )

        # Second pass: Build reverse dependencies (dependents)
        for stage_id, node in self.nodes.items():
            for dep_id in node.dependencies:
                if dep_id not in self.nodes:
                    raise DAGValidationError(
                        f"Stage '{stage_id}' depends on non-existent stage '{dep_id}'"
                    )
                self.nodes[dep_id].dependents.add(stage_id)

        logger.debug(
            f"Built DAG for {self.pipeline_id}",
            extra={
                "pipeline_id": self.pipeline_id,
                "node_count": len(self.nodes),
                "stages": list(self.nodes.keys()),
            },
        )

    def _compute_levels(self) -> None:
        """
        Compute execution levels for parallel scheduling.

        Level 0: Stages with no dependencies
        Level N: Stages whose dependencies are all in levels < N
        """
        # Find stages with no dependencies (level 0)
        ready = [node for node in self.nodes.values() if not node.dependencies]

        for node in ready:
            node.level = 0

        # BFS to assign levels
        visited = set(node.stage.id for node in ready)
        queue = ready[:]

        while queue:
            current = queue.pop(0)

            for dependent_id in current.dependents:
                dependent = self.nodes[dependent_id]

                # Check if all dependencies have been visited
                if not dependent.dependencies.issubset(visited):
                    continue

                # Compute level = max(dependency levels) + 1
                max_dep_level = max(self.nodes[dep_id].level for dep_id in dependent.dependencies)
                dependent.level = max_dep_level + 1

                visited.add(dependent_id)
                queue.append(dependent)

        # Verify all nodes were reached (no cycles)
        if len(visited) != len(self.nodes):
            unvisited = set(self.nodes.keys()) - visited
            raise DAGCycleError(
                f"Cycle detected in pipeline {self.pipeline_id}. Unreachable stages: {unvisited}"
            )

        logger.debug(
            f"Computed execution levels for {self.pipeline_id}",
            extra={
                "pipeline_id": self.pipeline_id,
                "max_level": max(node.level for node in self.nodes.values()),
                "levels": {
                    level: [node.stage.id for node in self.nodes.values() if node.level == level]
                    for level in range(max(node.level for node in self.nodes.values()) + 1)
                },
            },
        )

    def topological_order(self) -> List[StageSpec]:
        """
        Return stages in topological order (safe sequential execution).

        Returns:
            List of stages ordered so dependencies come before dependents
        """
        # Sort by level, then by stage_id for determinism
        sorted_nodes = sorted(
            self.nodes.values(),
            key=lambda n: (n.level, n.stage.id),
        )
        return [node.stage for node in sorted_nodes]

    def get_level_groups(self) -> List[List[StageSpec]]:
        """
        Return stages grouped by execution level (for parallel execution).

        Returns:
            List of stage groups, where stages in each group can run in parallel
        """
        max_level = max(node.level for node in self.nodes.values())
        groups = []

        for level in range(max_level + 1):
            level_stages = [node.stage for node in self.nodes.values() if node.level == level]
            # Sort by stage_id for determinism
            level_stages.sort(key=lambda s: s.id)
            groups.append(level_stages)

        return groups

    def get_dependencies(self, stage_id: StageID) -> Set[StageID]:
        """Get direct dependencies of a stage."""
        if stage_id not in self.nodes:
            raise KeyError(f"Stage not found: {stage_id}")
        return self.nodes[stage_id].dependencies

    def get_dependents(self, stage_id: StageID) -> Set[StageID]:
        """Get stages that depend on this stage."""
        if stage_id not in self.nodes:
            raise KeyError(f"Stage not found: {stage_id}")
        return self.nodes[stage_id].dependents

    def __len__(self) -> int:
        """Return number of stages in DAG."""
        return len(self.nodes)

    def __contains__(self, stage_id: StageID) -> bool:
        """Check if stage exists in DAG."""
        return stage_id in self.nodes


def build_dag(spec: PipelineSpec) -> DAG:
    """
    Build execution DAG from pipeline specification.

    Args:
        spec: Validated PipelineSpec

    Returns:
        DAG ready for execution

    Raises:
        DAGCycleError: If cycles detected
        DAGValidationError: If structure invalid

    Usage:
        >>> spec = PipelineSpec.load("p02_write.v1.yaml")
        >>> dag = build_dag(spec)
        >>> for stage in dag.topological_order():
        ...     await execute_stage(stage)
    """
    return DAG(spec)
