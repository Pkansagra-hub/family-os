#!/usr/bin/env python3
"""
Check Propagation - Find affected ADRs when architectural layers or modules change

This script analyzes the ADR index and propagation maps to identify which ADRs
need review when making changes to specific layers, modules, or components.

Usage:
    python scripts/check_propagation.py --layer layer3_execution
    python scripts/check_propagation.py --module agent_fabric
    python scripts/check_propagation.py --concern performance
    python scripts/check_propagation.py --adr 0004  # What's affected by ADR-0004?
    python scripts/check_propagation.py --layer layer2_orchestration --format json
    python scripts/check_propagation.py --impact-analysis  # Full dependency graph
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Set


class PropagationChecker:
    """Analyze ADR dependencies and propagation impacts."""

    def __init__(self, base_path: Path):
        self.base_path = base_path
        self.decisions_path = base_path / "docs" / "architecture" / "decisions"
        self.index_path = self.decisions_path / "00-meta" / "adr_index.json"
        self.propagation_path = self.decisions_path / "00-meta" / "propagation_maps"
        self.index_data: Optional[Dict] = None

    def load_index(self) -> None:
        """Load ADR index from JSON."""
        if not self.index_path.exists():
            print(f"❌ Index not found: {self.index_path}", file=sys.stderr)
            print("💡 Run: python scripts/build_adr_index.py", file=sys.stderr)
            sys.exit(1)

        with open(self.index_path, "r", encoding="utf-8") as f:
            self.index_data = json.load(f)

    def find_by_layer(self, layer: str) -> List[Dict]:
        """Find all ADRs affecting a specific layer."""
        if not self.index_data:
            self.load_index()

        return [adr for adr in self.index_data["adrs"] if layer in adr.get("affected_layers", [])]

    def find_by_concern(self, concern: str) -> List[Dict]:
        """Find all ADRs with a specific concern."""
        if not self.index_data:
            self.load_index()

        return [adr for adr in self.index_data["adrs"] if concern in adr.get("concerns", [])]

    def find_by_module(self, module_pattern: str) -> List[Dict]:
        """Find ADRs mentioning a specific module."""
        if not self.index_data:
            self.load_index()

        pattern_lower = module_pattern.lower()
        results = []

        for adr in self.index_data["adrs"]:
            # Check title
            if pattern_lower in adr.get("title", "").lower():
                results.append(adr)
                continue

            # Check concerns
            concerns = " ".join(adr.get("concerns", [])).lower()
            if pattern_lower in concerns:
                results.append(adr)

        return results

    def build_dependency_graph(self) -> Dict[str, Set[str]]:
        """Build directed graph of ADR dependencies from related_adrs."""
        if not self.index_data:
            self.load_index()

        graph = defaultdict(set)

        for adr in self.index_data["adrs"]:
            adr_num = adr.get("adr_number", "")
            if not adr_num:
                continue

            # Normalize ADR number
            if not adr_num.startswith("ADR-"):
                adr_num = f"ADR-{adr_num}"

            # Add edges to related ADRs
            for related in adr.get("related_adrs", []):
                related_str = str(related)
                if not related_str.startswith("ADR-"):
                    related_str = f"ADR-{related_str}"

                # Edge: current ADR depends on related ADR
                graph[adr_num].add(related_str)

        return graph

    def find_transitive_dependencies(self, adr_number: str, max_depth: int = 5) -> Dict[str, int]:
        """Find all ADRs that depend on this ADR (transitive closure)."""
        if not self.index_data:
            self.load_index()

        # Normalize ADR number
        if not adr_number.startswith("ADR-"):
            adr_number = f"ADR-{adr_number}"

        graph = self.build_dependency_graph()

        # BFS to find all ADRs that reference this one
        dependencies = {adr_number: 0}  # {adr_num: depth}
        queue = [(adr_number, 0)]
        visited = {adr_number}

        while queue:
            current, depth = queue.pop(0)

            if depth >= max_depth:
                continue

            # Find ADRs that depend on current
            for other_adr, related_set in graph.items():
                if current in related_set and other_adr not in visited:
                    dependencies[other_adr] = depth + 1
                    visited.add(other_adr)
                    queue.append((other_adr, depth + 1))

        return dependencies

    def find_affected_by_layer(self, layer: str) -> Dict[str, List[Dict]]:
        """Find all ADRs affected by changes to a layer (grouped by impact type)."""
        if not self.index_data:
            self.load_index()

        affected = {
            "direct": [],  # ADRs directly affecting this layer
            "cross_layer": [],  # ADRs affecting multiple layers including this one
            "related": [],  # ADRs related to direct ADRs
        }

        # Find direct ADRs
        direct_adrs = self.find_by_layer(layer)
        affected["direct"] = direct_adrs

        # Find cross-layer ADRs (affect this layer + others)
        for adr in direct_adrs:
            layers = adr.get("affected_layers", [])
            if len(layers) > 1:
                affected["cross_layer"].append(adr)

        # Find related ADRs through dependency graph
        graph = self.build_dependency_graph()
        related_set = set()

        for adr in direct_adrs:
            adr_num = adr.get("adr_number", "")
            if not adr_num.startswith("ADR-"):
                adr_num = f"ADR-{adr_num}"

            # Get dependencies
            deps = self.find_transitive_dependencies(adr_num, max_depth=2)
            related_set.update(deps.keys())

        # Convert related ADR numbers to full ADR objects
        adr_map = {f"ADR-{adr.get('adr_number', '')}": adr for adr in self.index_data["adrs"]}

        for adr_num in related_set:
            if adr_num in adr_map:
                adr_obj = adr_map[adr_num]
                # Only add if not already in direct/cross_layer
                if adr_obj not in affected["direct"] and adr_obj not in affected["cross_layer"]:
                    affected["related"].append(adr_obj)

        return affected

    def analyze_impact(self, adr_number: str) -> Dict:
        """Analyze full impact of changing a specific ADR."""
        if not self.index_data:
            self.load_index()

        # Normalize ADR number
        if not adr_number.startswith("ADR-"):
            adr_number = f"ADR-{adr_number}"

        # Find the ADR
        adr_obj = None
        for adr in self.index_data["adrs"]:
            num = adr.get("adr_number", "")
            if not num.startswith("ADR-"):
                num = f"ADR-{num}"
            if num == adr_number:
                adr_obj = adr
                break

        if not adr_obj:
            return {"error": f"ADR {adr_number} not found"}

        # Get transitive dependencies
        deps = self.find_transitive_dependencies(adr_number, max_depth=5)

        # Build impact report
        impact = {
            "adr": adr_obj,
            "affected_adrs": [],
            "affected_layers": set(),
            "affected_concerns": set(),
            "dependency_depth": {},
        }

        # Get ADR objects for dependencies
        adr_map = {f"ADR-{adr.get('adr_number', '')}": adr for adr in self.index_data["adrs"]}

        for dep_num, depth in deps.items():
            if dep_num == adr_number:
                continue  # Skip self

            if dep_num in adr_map:
                dep_adr = adr_map[dep_num]
                impact["affected_adrs"].append(dep_adr)
                impact["affected_layers"].update(dep_adr.get("affected_layers", []))
                impact["affected_concerns"].update(dep_adr.get("concerns", []))
                impact["dependency_depth"][dep_num] = depth

        # Convert sets to lists for JSON serialization
        impact["affected_layers"] = sorted(list(impact["affected_layers"]))
        impact["affected_concerns"] = sorted(list(impact["affected_concerns"]))

        return impact

    def format_layer_impact(self, layer: str, affected: Dict, format_type: str = "text") -> str:
        """Format layer impact analysis."""
        if format_type == "json":
            return json.dumps(affected, indent=2)

        output = []
        output.append(f"🏗️  Impact Analysis: {layer}")
        output.append("=" * 60)
        output.append("")

        # Direct impact
        direct = affected["direct"]
        output.append(f"📍 Direct Impact: {len(direct)} ADR(s)")
        if direct:
            for adr in direct[:10]:  # Show first 10
                num = adr.get("adr_number", "UNKNOWN")
                title = adr.get("title", "No title")
                status = adr.get("status", "UNKNOWN")
                output.append(f"  • ADR-{num}: {title} [{status}]")
            if len(direct) > 10:
                output.append(f"  ... and {len(direct) - 10} more")
        output.append("")

        # Cross-layer impact
        cross = affected["cross_layer"]
        output.append(f"🔀 Cross-Layer Impact: {len(cross)} ADR(s)")
        if cross:
            for adr in cross[:5]:
                num = adr.get("adr_number", "UNKNOWN")
                title = adr.get("title", "No title")
                layers = ", ".join(adr.get("affected_layers", []))
                output.append(f"  • ADR-{num}: {title}")
                output.append(f"    Layers: {layers}")
            if len(cross) > 5:
                output.append(f"  ... and {len(cross) - 5} more")
        output.append("")

        # Related ADRs
        related = affected["related"]
        output.append(f"🔗 Related ADRs (Transitive): {len(related)} ADR(s)")
        if related:
            for adr in related[:5]:
                num = adr.get("adr_number", "UNKNOWN")
                title = adr.get("title", "No title")
                output.append(f"  • ADR-{num}: {title}")
            if len(related) > 5:
                output.append(f"  ... and {len(related) - 5} more")

        return "\n".join(output)

    def format_adr_impact(self, impact: Dict, format_type: str = "text") -> str:
        """Format ADR impact analysis."""
        if format_type == "json":
            return json.dumps(impact, indent=2)

        if "error" in impact:
            return f"❌ {impact['error']}"

        output = []
        adr = impact["adr"]
        num = adr.get("adr_number", "UNKNOWN")
        title = adr.get("title", "No title")

        output.append(f"🎯 Impact Analysis: ADR-{num}")
        output.append("=" * 60)
        output.append(f"Title: {title}")
        output.append(f"Status: {adr.get('status', 'UNKNOWN')}")
        output.append("")

        # Affected ADRs
        affected_count = len(impact["affected_adrs"])
        output.append(f"📊 Affected ADRs: {affected_count}")
        if affected_count > 0:
            output.append("")
            # Group by depth
            by_depth = defaultdict(list)
            for dep_num, depth in impact["dependency_depth"].items():
                by_depth[depth].append(dep_num)

            for depth in sorted(by_depth.keys()):
                adrs_at_depth = by_depth[depth]
                output.append(f"  Depth {depth}: {len(adrs_at_depth)} ADR(s)")
                for dep_num in sorted(adrs_at_depth)[:5]:
                    # Find ADR object
                    dep_adr = next(
                        (
                            a
                            for a in impact["affected_adrs"]
                            if f"ADR-{a.get('adr_number', '')}" == dep_num
                        ),
                        None,
                    )
                    if dep_adr:
                        dep_title = dep_adr.get("title", "No title")
                        output.append(f"    • {dep_num}: {dep_title}")
                if len(adrs_at_depth) > 5:
                    output.append(f"    ... and {len(adrs_at_depth) - 5} more")
        output.append("")

        # Affected layers
        layers = impact["affected_layers"]
        output.append(f"🏗️  Affected Layers: {len(layers)}")
        if layers:
            for layer in layers:
                output.append(f"  • {layer}")
        output.append("")

        # Affected concerns
        concerns = impact["affected_concerns"]
        output.append(f"🏷️  Affected Concerns: {len(concerns)}")
        if concerns:
            for concern in concerns:
                output.append(f"  • {concern}")

        return "\n".join(output)


def main():
    parser = argparse.ArgumentParser(description="Analyze ADR propagation and dependency impact")
    parser.add_argument(
        "--layer", help="Find ADRs affected by layer changes (e.g., layer3_execution)"
    )
    parser.add_argument(
        "--module", help="Find ADRs affected by module changes (e.g., agent_fabric)"
    )
    parser.add_argument("--concern", help="Find ADRs with specific concern (e.g., performance)")
    parser.add_argument("--adr", help="Analyze impact of changing specific ADR (e.g., 0004)")
    parser.add_argument(
        "--format", choices=["text", "json"], default="text", help="Output format (default: text)"
    )
    parser.add_argument(
        "--impact-analysis", action="store_true", help="Show full dependency graph statistics"
    )
    parser.add_argument(
        "--base-path",
        type=Path,
        default=Path.cwd(),
        help="Base repository path (default: current directory)",
    )

    args = parser.parse_args()

    checker = PropagationChecker(args.base_path)

    # Impact analysis
    if args.impact_analysis:
        checker.load_index()
        graph = checker.build_dependency_graph()

        print("📊 Dependency Graph Statistics")
        print("=" * 60)
        print(f"Total ADRs: {checker.index_data['metadata']['total_adrs']}")
        print(f"ADRs with dependencies: {len(graph)}")
        print(f"Total dependency edges: {sum(len(deps) for deps in graph.values())}")
        print()

        # Find most connected ADRs
        by_deps = sorted(graph.items(), key=lambda x: len(x[1]), reverse=True)
        print("🔗 Most Connected ADRs (Top 10):")
        for adr_num, deps in by_deps[:10]:
            print(f"  {adr_num}: {len(deps)} dependencies")

        sys.exit(0)

    # Require at least one parameter
    if not any([args.layer, args.module, args.concern, args.adr]):
        parser.print_help()
        sys.exit(1)

    # Layer impact
    if args.layer:
        affected = checker.find_affected_by_layer(args.layer)
        output = checker.format_layer_impact(args.layer, affected, args.format)
        print(output)

    # Module impact
    elif args.module:
        adrs = checker.find_by_module(args.module)
        print(f"🔧 Module Impact: {args.module}")
        print("=" * 60)
        print(f"Found {len(adrs)} ADR(s) mentioning this module:\n")
        for adr in adrs:
            num = adr.get("adr_number", "UNKNOWN")
            title = adr.get("title", "No title")
            status = adr.get("status", "UNKNOWN")
            print(f"• ADR-{num}: {title} [{status}]")

    # Concern impact
    elif args.concern:
        adrs = checker.find_by_concern(args.concern)
        print(f"🏷️  Concern Impact: {args.concern}")
        print("=" * 60)
        print(f"Found {len(adrs)} ADR(s) with this concern:\n")
        for adr in adrs:
            num = adr.get("adr_number", "UNKNOWN")
            title = adr.get("title", "No title")
            layers = ", ".join(adr.get("affected_layers", []))
            print(f"• ADR-{num}: {title}")
            if layers:
                print(f"  Layers: {layers}")

    # ADR impact
    elif args.adr:
        impact = checker.analyze_impact(args.adr)
        output = checker.format_adr_impact(impact, args.format)
        print(output)


if __name__ == "__main__":
    main()
