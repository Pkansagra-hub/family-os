#!/usr/bin/env python3
"""
L5 Infrastructure Connection Analyzer

Analyzes all stub files in k1/l5_infrastructure/ to extract upstream and downstream connections.

Usage:
    python scripts/analyze_l5_connections.py

Output:
    - JSON file with all connections: l5_connections.json
    - Text summary: l5_connections_summary.txt
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Tuple


def find_l5_stub_files() -> List[Path]:
    """Find all Python stub files in L5 infrastructure."""
    l5_path = Path("k1/l5_infrastructure")
    if not l5_path.exists():
        print(f"Error: {l5_path} directory not found")
        return []

    stub_files = []
    for py_file in l5_path.rglob("*.py"):
        if py_file.name == "__init__.py":
            continue
        stub_files.append(py_file)

    return sorted(stub_files)


def extract_connections_from_file(file_path: Path) -> Tuple[List[str], List[str]]:
    """
    Extract upstream and downstream connections from a stub file.

    Returns:
        Tuple of (upstream_connections, downstream_connections)
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return [], []

    # Find the "Connects To:" section
    connects_match = re.search(r"Connects To:\s*\n(.*?)(?:\n\n|\n[A-Z]|$)", content, re.DOTALL)
    if not connects_match:
        return [], []

    connects_section = connects_match.group(1)

    # Extract upstream connections
    upstream_match = re.search(
        r"Upstream:\s*\n(.*?)(?:\n\s*Downstream:|\n\n|\n[A-Z]|$)", connects_section, re.DOTALL
    )
    upstream = []
    if upstream_match:
        upstream_text = upstream_match.group(1)
        # Extract bullet points
        upstream = re.findall(r"\s*-\s*(.+?)(?:\n|$)", upstream_text)

    # Extract downstream connections
    downstream_match = re.search(
        r"Downstream:\s*\n(.*?)(?:\n\n|\n[A-Z]|$)", connects_section, re.DOTALL
    )
    downstream = []
    if downstream_match:
        downstream_text = downstream_match.group(1)
        # Extract bullet points
        downstream = re.findall(r"\s*-\s*(.+?)(?:\n|$)", downstream_text)

    return upstream, downstream


def analyze_all_connections() -> Dict[str, Dict]:
    """Analyze connections for all L5 stub files."""
    stub_files = find_l5_stub_files()
    connections = {}

    print(f"Found {len(stub_files)} stub files in L5 infrastructure")

    for file_path in stub_files:
        # Convert to module path for easier reference
        module_path = str(file_path).replace("\\", ".").replace("/", ".")
        module_path = module_path.replace("k1.l5_infrastructure.", "").replace(".py", "")

        upstream, downstream = extract_connections_from_file(file_path)

        connections[module_path] = {
            "file_path": str(file_path),
            "upstream": upstream,
            "downstream": downstream,
        }

        if upstream or downstream:
            print(f"✓ {module_path}: {len(upstream)} upstream, {len(downstream)} downstream")
        else:
            print(f"✗ {module_path}: No connections found")

    return connections


def generate_summary_report(connections: Dict[str, Dict]) -> str:
    """Generate a text summary of all connections."""
    report = []
    report.append("=" * 80)
    report.append("L5 INFRASTRUCTURE CONNECTIONS SUMMARY")
    report.append("=" * 80)
    report.append("")

    total_files = len(connections)
    files_with_connections = sum(
        1 for c in connections.values() if c["upstream"] or c["downstream"]
    )
    total_upstream = sum(len(c["upstream"]) for c in connections.values())
    total_downstream = sum(len(c["downstream"]) for c in connections.values())

    report.append(f"Total stub files analyzed: {total_files}")
    report.append(f"Files with connections: {files_with_connections}")
    report.append(f"Total upstream connections: {total_upstream}")
    report.append(f"Total downstream connections: {total_downstream}")
    report.append("")

    # Group by component
    components = {}
    for module, data in connections.items():
        component = module.split(".")[0]
        if component not in components:
            components[component] = {"upstream": set(), "downstream": set(), "files": []}
        components[component]["files"].append(module)
        components[component]["upstream"].update(data["upstream"])
        components[component]["downstream"].update(data["downstream"])

    report.append("CONNECTIONS BY COMPONENT:")
    report.append("-" * 40)

    for component in sorted(components.keys()):
        data = components[component]
        report.append(f"\n{component.upper()}:")
        report.append(f"  Files: {len(data['files'])}")
        report.append(f"  Upstream connections: {len(data['upstream'])}")
        report.append(f"  Downstream connections: {len(data['downstream'])}")

        if data["upstream"]:
            report.append("  Upstream:")
            for conn in sorted(data["upstream"]):
                report.append(f"    - {conn}")

        if data["downstream"]:
            report.append("  Downstream:")
            for conn in sorted(data["downstream"]):
                report.append(f"    - {conn}")

    report.append("")
    report.append("=" * 80)

    return "\n".join(report)


def find_connection_patterns(connections: Dict[str, Dict]) -> Dict[str, List[str]]:
    """Find common connection patterns and potential issues."""
    patterns = {
        "orphaned_upstream": [],
        "orphaned_downstream": [],
        "circular_dependencies": [],
        "most_connected": [],
    }

    # Collect all known modules
    all_modules = set(connections.keys())

    # Check for orphaned connections
    for module, data in connections.items():
        for upstream in data["upstream"]:
            # Extract module name from connection string
            module_match = re.search(r"k1\.[^(\s]+", upstream)
            if module_match:
                upstream_module = module_match.group(0).replace("k1.l5_infrastructure.", "")
                if upstream_module not in all_modules:
                    patterns["orphaned_upstream"].append(f"{module} -> {upstream_module}")

        for downstream in data["downstream"]:
            # Extract module name from connection string
            module_match = re.search(r"k1\.[^(\s]+", downstream)
            if module_match:
                downstream_module = module_match.group(0).replace("k1.l5_infrastructure.", "")
                if downstream_module not in all_modules:
                    patterns["orphaned_downstream"].append(f"{module} -> {downstream_module}")

    # Find most connected modules
    connection_counts = {}
    for module, data in connections.items():
        connection_counts[module] = len(data["upstream"]) + len(data["downstream"])

    most_connected = sorted(connection_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    patterns["most_connected"] = [
        f"{module}: {count} connections" for module, count in most_connected
    ]

    return patterns


def main():
    """Main analysis function."""
    print("🔍 Analyzing L5 Infrastructure Connections...")
    print("=" * 50)

    connections = analyze_all_connections()

    if not connections:
        print("No stub files found or no connections extracted.")
        return

    # Generate JSON output
    output_dir = Path("scripts/output")
    output_dir.mkdir(exist_ok=True)

    json_file = output_dir / "l5_connections.json"
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(connections, f, indent=2, ensure_ascii=False)

    print(f"\n📄 JSON output saved to: {json_file}")

    # Generate text summary
    summary = generate_summary_report(connections)
    summary_file = output_dir / "l5_connections_summary.txt"
    with open(summary_file, "w", encoding="utf-8") as f:
        f.write(summary)

    print(f"📄 Summary saved to: {summary_file}")

    # Generate patterns analysis
    patterns = find_connection_patterns(connections)
    patterns_file = output_dir / "l5_connection_patterns.txt"
    with open(patterns_file, "w", encoding="utf-8") as f:
        f.write("CONNECTION PATTERNS ANALYSIS\n")
        f.write("=" * 40)
        f.write("\n\n")

        f.write("ORPHANED UPSTREAM CONNECTIONS (referenced but not found):\n")
        if patterns["orphaned_upstream"]:
            for conn in patterns["orphaned_upstream"]:
                f.write(f"  - {conn}\n")
        else:
            f.write("  None found\n")

        f.write("\nORPHANED DOWNSTREAM CONNECTIONS (referenced but not found):\n")
        if patterns["orphaned_downstream"]:
            for conn in patterns["orphaned_downstream"]:
                f.write(f"  - {conn}\n")
        else:
            f.write("  None found\n")

        f.write("\nMOST CONNECTED MODULES:\n")
        for conn in patterns["most_connected"]:
            f.write(f"  - {conn}\n")

    print(f"📄 Patterns analysis saved to: {patterns_file}")

    print("\n✅ Analysis complete!")
    print(f"   Processed {len(connections)} files")
    print(
        f"   Found {sum(len(c['upstream']) + len(c['downstream']) for c in connections.values())} total connections"
    )


if __name__ == "__main__":
    main()
