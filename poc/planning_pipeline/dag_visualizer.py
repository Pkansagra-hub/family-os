"""
DAG Visualizer - ASCII and Mermaid rendering

Provides visualization tools for debugging and documentation:
- ASCII art renderer with status indicators
- Mermaid diagram export for documentation

Part of M6 Epic 6.3: DAG Visualization
"""

from typing import List, Set

from dag_node import DAG, DAGNode, NodeStatus

# ============================================================================
# ASCII RENDERER
# ============================================================================


class ASCIIRenderer:
    """
    Renders DAG as ASCII art for debugging.

    Features:
    - Visual tree structure
    - Status indicators (✓✗⏳🔄⊗)
    - Color coding (if terminal supports)
    - Compact representation
    """

    # Status symbols
    STATUS_SYMBOLS = {
        NodeStatus.PENDING: "⏳",
        NodeStatus.READY: "▶",
        NodeStatus.RUNNING: "🔄",
        NodeStatus.COMPLETED: "✓",
        NodeStatus.FAILED: "✗",
        NodeStatus.BLOCKED: "⊗",
        NodeStatus.CANCELLED: "⊘",
    }

    # ANSI color codes (if terminal supports)
    COLORS = {
        NodeStatus.PENDING: "\033[90m",  # Gray
        NodeStatus.READY: "\033[94m",  # Blue
        NodeStatus.RUNNING: "\033[93m",  # Yellow
        NodeStatus.COMPLETED: "\033[92m",  # Green
        NodeStatus.FAILED: "\033[91m",  # Red
        NodeStatus.BLOCKED: "\033[95m",  # Magenta
        NodeStatus.CANCELLED: "\033[90m",  # Gray
    }
    RESET = "\033[0m"

    def __init__(self, use_color: bool = True):
        """
        Initialize renderer.

        Args:
            use_color: Whether to use ANSI colors
        """
        self.use_color = use_color

    def render(self, dag: DAG) -> str:
        """
        Render DAG as ASCII art.

        Args:
            dag: DAG to render

        Returns:
            ASCII art string
        """
        lines = []
        lines.append(f"DAG: {dag.dag_id}")
        lines.append(f"Nodes: {len(dag.nodes)} | Edges: {len(dag.edges)}")
        lines.append("=" * 60)

        # Render nodes in execution layers
        execution_order = self._get_execution_layers(dag)

        for layer_idx, layer in enumerate(execution_order):
            lines.append(f"\nLayer {layer_idx + 1} (parallel):")
            lines.append("-" * 60)

            for node_id in layer:
                node = dag.get_node(node_id)
                if node:
                    lines.append(self._render_node(node, dag))

        # Summary
        lines.append("\n" + "=" * 60)
        lines.append(self._render_summary(dag))

        return "\n".join(lines)

    def _render_node(self, node: DAGNode, dag: DAG) -> str:
        """
        Render single node with status and dependencies.

        Args:
            node: Node to render
            dag: Parent DAG

        Returns:
            Formatted node string
        """
        # Status symbol
        symbol = self.STATUS_SYMBOLS.get(node.status, "?")

        # Color coding
        color = ""
        reset = ""
        if self.use_color:
            color = self.COLORS.get(node.status, "")
            reset = self.RESET

        # Node info
        node_str = f"{color}{symbol} {node.node_id}{reset}"
        node_str += f" ({node.agent_type})"

        # Dependencies
        deps = dag.get_dependencies(node.node_id)
        if deps:
            dep_ids = [d.node_id for d in deps]
            node_str += f" ← depends on: {', '.join(dep_ids)}"

        # Execution info
        if node.duration_ms:
            node_str += f" | {node.duration_ms:.1f}ms"

        if node.error:
            node_str += f" | Error: {node.error[:50]}"

        return "  " + node_str

    def _render_summary(self, dag: DAG) -> str:
        """
        Render execution summary.

        Args:
            dag: DAG to summarize

        Returns:
            Summary string
        """
        completed = len([n for n in dag.nodes.values() if n.status == NodeStatus.COMPLETED])
        failed = len([n for n in dag.nodes.values() if n.status == NodeStatus.FAILED])
        blocked = len([n for n in dag.nodes.values() if n.status == NodeStatus.BLOCKED])
        running = len([n for n in dag.nodes.values() if n.status == NodeStatus.RUNNING])
        pending = len([n for n in dag.nodes.values() if n.status == NodeStatus.PENDING])

        summary = "Status: "
        summary += f"✓ {completed} completed | "
        summary += f"✗ {failed} failed | "
        summary += f"⊗ {blocked} blocked | "
        summary += f"🔄 {running} running | "
        summary += f"⏳ {pending} pending"

        return summary

    def _get_execution_layers(self, dag: DAG) -> List[List[str]]:
        """
        Get execution layers (topological ordering).

        Args:
            dag: DAG to analyze

        Returns:
            List of layers, each containing parallel node IDs
        """
        layers = []
        processed: Set[str] = set()

        while len(processed) < len(dag.nodes):
            # Find nodes with all dependencies processed
            current_layer = []
            for node_id, node in dag.nodes.items():
                if node_id in processed:
                    continue

                deps = dag.get_dependencies(node_id)
                if all(d.node_id in processed for d in deps):
                    current_layer.append(node_id)

            if not current_layer:
                # Stuck - likely circular dependency
                remaining = [nid for nid in dag.nodes if nid not in processed]
                layers.append(remaining)
                break

            layers.append(current_layer)
            processed.update(current_layer)

        return layers


# ============================================================================
# MERMAID EXPORTER
# ============================================================================


class MermaidExporter:
    """
    Exports DAG to Mermaid diagram syntax.

    Features:
    - Flowchart generation
    - Status-based styling
    - Node labels with agent types
    - Dependency edges
    """

    # Mermaid node shapes by status
    NODE_SHAPES = {
        NodeStatus.PENDING: ("[", "]"),  # Rectangle
        NodeStatus.READY: ("[", "]"),  # Rectangle
        NodeStatus.RUNNING: ("[[", "]]"),  # Subroutine
        NodeStatus.COMPLETED: ("([", "])"),  # Stadium (rounded)
        NodeStatus.FAILED: ("[/", "/]"),  # Parallelogram
        NodeStatus.BLOCKED: ("[\\", "\\]"),  # Trapezoid
        NodeStatus.CANCELLED: ("[", "]"),  # Rectangle
    }

    # Mermaid CSS classes by status
    NODE_CLASSES = {
        NodeStatus.PENDING: "pending",
        NodeStatus.READY: "ready",
        NodeStatus.RUNNING: "running",
        NodeStatus.COMPLETED: "completed",
        NodeStatus.FAILED: "failed",
        NodeStatus.BLOCKED: "blocked",
        NodeStatus.CANCELLED: "cancelled",
    }

    def export(self, dag: DAG, include_styling: bool = True) -> str:
        """
        Export DAG to Mermaid flowchart syntax.

        Args:
            dag: DAG to export
            include_styling: Whether to include CSS styling

        Returns:
            Mermaid diagram string
        """
        lines = []
        lines.append("```mermaid")
        lines.append("flowchart TD")

        # Add nodes
        for node_id, node in dag.nodes.items():
            lines.append(self._export_node(node))

        # Add edges
        lines.append("")
        for edge in dag.edges:
            from_id = self._sanitize_id(edge.from_node)
            to_id = self._sanitize_id(edge.to_node)
            lines.append(f"    {from_id} --> {to_id}")

        # Add styling
        if include_styling:
            lines.append("")
            lines.append(self._export_styling())

            # Apply classes to nodes
            for node_id, node in dag.nodes.items():
                sanitized_id = self._sanitize_id(node_id)
                css_class = self.NODE_CLASSES.get(node.status, "default")
                lines.append(f"    class {sanitized_id} {css_class}")

        lines.append("```")
        return "\n".join(lines)

    def _export_node(self, node: DAGNode) -> str:
        """
        Export single node to Mermaid syntax.

        Args:
            node: Node to export

        Returns:
            Mermaid node definition
        """
        sanitized_id = self._sanitize_id(node.node_id)

        # Node label
        label = f"{node.node_id}<br/>({node.agent_type})"

        # Add status indicator
        status_symbol = ASCIIRenderer.STATUS_SYMBOLS.get(node.status, "?")
        label = f"{status_symbol} {label}"

        # Node shape based on status
        shape_start, shape_end = self.NODE_SHAPES.get(node.status, ("[", "]"))

        return f'    {sanitized_id}{shape_start}"{label}"{shape_end}'

    def _export_styling(self) -> str:
        """
        Export Mermaid CSS styling.

        Returns:
            CSS class definitions
        """
        styling = []
        styling.append("    %% Styling")
        styling.append("    classDef pending fill:#f0f0f0,stroke:#999,stroke-width:2px")
        styling.append("    classDef ready fill:#e3f2fd,stroke:#2196f3,stroke-width:2px")
        styling.append("    classDef running fill:#fff9c4,stroke:#fbc02d,stroke-width:3px")
        styling.append("    classDef completed fill:#c8e6c9,stroke:#4caf50,stroke-width:2px")
        styling.append("    classDef failed fill:#ffcdd2,stroke:#f44336,stroke-width:3px")
        styling.append("    classDef blocked fill:#e1bee7,stroke:#9c27b0,stroke-width:2px")
        styling.append(
            "    classDef cancelled fill:#f0f0f0,stroke:#999,stroke-width:1px,stroke-dasharray: 5 5"
        )
        return "\n".join(styling)

    def _sanitize_id(self, node_id: str) -> str:
        """
        Sanitize node ID for Mermaid (alphanumeric + underscore).

        Args:
            node_id: Original node ID

        Returns:
            Sanitized ID
        """
        # Replace special chars with underscore
        sanitized = "".join(c if c.isalnum() or c == "_" else "_" for c in node_id)
        # Ensure starts with letter
        if sanitized and not sanitized[0].isalpha():
            sanitized = "n" + sanitized
        return sanitized or "node"


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================


def render_dag_ascii(dag: DAG, use_color: bool = True) -> str:
    """
    Render DAG as ASCII art.

    Args:
        dag: DAG to render
        use_color: Whether to use ANSI colors

    Returns:
        ASCII art string
    """
    renderer = ASCIIRenderer(use_color=use_color)
    return renderer.render(dag)


def export_dag_mermaid(dag: DAG, include_styling: bool = True) -> str:
    """
    Export DAG to Mermaid diagram.

    Args:
        dag: DAG to export
        include_styling: Whether to include CSS styling

    Returns:
        Mermaid diagram string
    """
    exporter = MermaidExporter()
    return exporter.export(dag, include_styling=include_styling)


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

if __name__ == "__main__":
    from dag_builder import DAGBuilder

    print("=" * 60)
    print("DAG VISUALIZER - EXAMPLE")
    print("=" * 60)

    # Create sample DAG
    plan = {
        "steps": [
            {
                "id": "s1",
                "agent": "query_agent",
                "tool": "restaurants",
                "needs": [],
                "description": "Find restaurants",
            },
            {
                "id": "s2",
                "agent": "booking_agent",
                "tool": "reservations",
                "needs": ["s1"],
                "description": "Book reservation",
            },
            {
                "id": "s3",
                "agent": "messenger_agent",
                "tool": "messaging",
                "needs": ["s2"],
                "description": "Notify family",
            },
        ]
    }

    builder = DAGBuilder()
    dag = builder.build_from_expanded_plan(plan)

    # Mark some nodes as completed for demo
    dag.get_node("s1").mark_completed(None)
    dag.get_node("s2").mark_running()

    print("\n--- ASCII RENDERING ---")
    print(render_dag_ascii(dag, use_color=False))

    print("\n--- MERMAID EXPORT ---")
    print(export_dag_mermaid(dag))

    print("\n✅ Visualizer demo complete!")
