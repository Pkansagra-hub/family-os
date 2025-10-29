#!/usr/bin/env python3
"""
L5 Infrastructure Connection Diagram Generator

Generates Mermaid diagram from the connection analysis output.

Usage:
    python scripts/generate_l5_connection_diagram.py

Output:
    - l5_infrastructure_connections.mmd (Mermaid diagram)
"""

import json
import re
from pathlib import Path
from typing import Dict


def load_connections() -> Dict[str, Dict]:
    """Load connections from the JSON output file."""
    json_file = Path("scripts/output/l5_connections.json")
    if not json_file.exists():
        print(f"Error: {json_file} not found. Run analyze_l5_connections.py first.")
        return {}

    with open(json_file, "r", encoding="utf-8") as f:
        return json.load(f)


def extract_module_name(connection_str: str) -> str:
    """Extract clean module name from connection string."""
    # Remove descriptions in parentheses
    module_match = re.match(r"([^(]+)", connection_str.strip())
    if module_match:
        module = module_match.group(1).strip()
        # Clean up module name
        module = re.sub(r"\s+", "_", module)  # Replace spaces with underscores
        return module
    return connection_str.strip()


def get_component_name(module_path: str) -> str:
    """Get component name from module path."""
    parts = module_path.split(".")
    if len(parts) >= 2:
        return parts[0].upper()
    return "OTHER"


def sanitize_node_id(name: str) -> str:
    """Create a valid Mermaid node ID."""
    # Replace dots and spaces with underscores, remove special chars
    sanitized = re.sub(r"[^\w]", "_", name)
    # Ensure it starts with a letter
    if sanitized and not sanitized[0].isalpha():
        sanitized = "M_" + sanitized
    return sanitized


def generate_mermaid_diagram(connections: Dict[str, Dict]) -> str:
    """Generate Mermaid diagram from connections data."""
    diagram_lines = []
    diagram_lines.append("---")
    diagram_lines.append("title: L5 Infrastructure Module Connections")
    diagram_lines.append("---")
    diagram_lines.append("")
    diagram_lines.append("graph TD")
    diagram_lines.append("")

    # Track all nodes and edges
    nodes = set()
    edges = set()
    subgraphs = {}

    # Process each module
    for module_path, data in connections.items():
        if not data["upstream"] and not data["downstream"]:
            continue  # Skip modules with no connections

        component = get_component_name(module_path)
        if component not in subgraphs:
            subgraphs[component] = []

        # Create node
        node_id = sanitize_node_id(module_path)
        node_label = module_path.replace(".", "\\n")
        nodes.add(node_id)

        # Add to subgraph
        subgraphs[component].append(f'        {node_id}["{node_label}"]')

        # Process upstream connections (incoming edges)
        for upstream in data["upstream"]:
            upstream_module = extract_module_name(upstream)
            upstream_id = sanitize_node_id(upstream_module)

            # Only add edge if upstream module exists in our dataset
            # or if it's an external reference we want to show
            if upstream_module.startswith("k1.l5_infrastructure"):
                upstream_short = upstream_module.replace("k1.l5_infrastructure.", "")
                if upstream_short in connections:
                    upstream_id = sanitize_node_id(upstream_short)
                    edges.add(f"    {upstream_id} --> {node_id}")
            else:
                # External upstream - create a boundary node
                external_id = sanitize_node_id(f"ext_{upstream_module}")
                if external_id not in nodes:
                    nodes.add(external_id)
                    diagram_lines.append(f'    {external_id}["{upstream_module}<br/>(External)"]')
                edges.add(f"    {external_id} --> {node_id}")

        # Process downstream connections (outgoing edges)
        for downstream in data["downstream"]:
            downstream_module = extract_module_name(downstream)
            downstream_id = sanitize_node_id(downstream_module)

            if downstream_module.startswith("k1.l5_infrastructure"):
                downstream_short = downstream_module.replace("k1.l5_infrastructure.", "")
                if downstream_short in connections:
                    downstream_id = sanitize_node_id(downstream_short)
                    edges.add(f"    {node_id} --> {downstream_id}")
            else:
                # External downstream - create a boundary node
                external_id = sanitize_node_id(f"ext_{downstream_module}")
                if external_id not in nodes:
                    nodes.add(external_id)
                    diagram_lines.append(f'    {external_id}["{downstream_module}<br/>(External)"]')
                edges.add(f"    {node_id} --> {external_id}")

    # Create subgraphs
    for component, node_lines in subgraphs.items():
        if node_lines:
            diagram_lines.append(f"    subgraph {component}")
            diagram_lines.extend(node_lines)
            diagram_lines.append("    end")
            diagram_lines.append("")

    # Add edges
    if edges:
        diagram_lines.append("    %% Connections")
        for edge in sorted(edges):
            diagram_lines.append(edge)

    # Add styling
    diagram_lines.append("")
    diagram_lines.append("    %% Styling")
    diagram_lines.append(
        "    classDef l5Infrastructure fill:#e1f5fe,stroke:#01579b,stroke-width:2px"
    )
    diagram_lines.append("    classDef external fill:#fff3e0,stroke:#e65100,stroke-width:2px")
    diagram_lines.append("")
    diagram_lines.append("    %% Apply classes")

    # Apply classes to nodes
    internal_nodes = []
    external_nodes = []
    for node in nodes:
        if node.startswith("ext_"):
            external_nodes.append(node)
        else:
            internal_nodes.append(node)

    if internal_nodes:
        diagram_lines.append(f"    class {','.join(internal_nodes)} l5Infrastructure")
    if external_nodes:
        diagram_lines.append(f"    class {','.join(external_nodes)} external")

    return "\n".join(diagram_lines)


def generate_summary_stats(connections: Dict[str, Dict]) -> str:
    """Generate summary statistics for the diagram."""
    total_modules = len(connections)
    connected_modules = sum(1 for c in connections.values() if c["upstream"] or c["downstream"])
    total_connections = sum(len(c["upstream"]) + len(c["downstream"]) for c in connections.values())

    # Count components
    components = {}
    for module in connections.keys():
        component = get_component_name(module)
        components[component] = components.get(component, 0) + 1

    stats = []
    stats.append("## L5 Infrastructure Connection Diagram")
    stats.append("")
    stats.append("### Statistics")
    stats.append(f"- **Total Modules**: {total_modules}")
    stats.append(
        f"- **Connected Modules**: {connected_modules} ({connected_modules/total_modules*100:.1f}%)"
    )
    stats.append(f"- **Total Connections**: {total_connections}")
    stats.append("")
    stats.append("### Components")
    for component, count in sorted(components.items()):
        stats.append(f"- **{component}**: {count} modules")

    stats.append("")
    stats.append("### Diagram Legend")
    stats.append("- 🔷 **L5 Infrastructure Modules**: Internal components")
    stats.append("- 🔶 **External Systems**: Outside L5 infrastructure")
    stats.append("- ➡️ **Arrows**: Data flow direction (upstream → downstream)")

    return "\n".join(stats)


def main():
    """Main diagram generation function."""
    print("🔍 Generating L5 Infrastructure Connection Diagram...")
    print("=" * 60)

    connections = load_connections()
    if not connections:
        return

    # Generate Mermaid diagram
    diagram = generate_mermaid_diagram(connections)

    # Save diagram
    output_dir = Path("scripts/output")
    output_dir.mkdir(exist_ok=True)

    mmd_file = output_dir / "l5_infrastructure_connections.mmd"
    with open(mmd_file, "w", encoding="utf-8") as f:
        f.write(diagram)

    print(f"📄 Mermaid diagram saved to: {mmd_file}")

    # Generate summary
    summary = generate_summary_stats(connections)
    summary_file = output_dir / "l5_connection_diagram_readme.md"
    with open(summary_file, "w", encoding="utf-8") as f:
        f.write(summary)

    print(f"📄 Summary saved to: {summary_file}")

    print("\n✅ Diagram generation complete!")
    print(f"   Processed {len(connections)} modules")
    connected = sum(1 for c in connections.values() if c["upstream"] or c["downstream"])
    total_conn = sum(len(c["upstream"]) + len(c["downstream"]) for c in connections.values())
    print(f"   {connected} modules with connections")
    print(f"   {total_conn} total connections visualized")


if __name__ == "__main__":
    main()
