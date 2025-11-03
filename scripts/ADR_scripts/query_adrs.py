#!/usr/bin/env python3
"""
Query ADRs - Semantic search across indexed ADR metadata

This script provides semantic search capabilities over the ADR index built by build_adr_index.py.
Enables AI agents and developers to quickly find relevant architectural decisions.

Usage:
    python scripts/query_adrs.py "agent lifecycle management"
    python scripts/query_adrs.py --layer layer3_execution
    python scripts/query_adrs.py --status IMPLEMENTED
    python scripts/query_adrs.py --concern performance
    python scripts/query_adrs.py --module agent_fabric
    python scripts/query_adrs.py "orchestration" --layer layer2_orchestration --format json
    python scripts/query_adrs.py --related 0004  # Find ADRs related to ADR-0004
    python scripts/query_adrs.py --category 03-layer2-orchestration
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional


class ADRQuery:
    """Query ADR index with semantic search and filters."""

    def __init__(self, base_path: Path):
        self.base_path = base_path
        self.index_path = (
            base_path / "docs" / "architecture" / "decisions" / "00-meta" / "adr_index.json"
        )
        self.index_data: Optional[Dict] = None

    def load_index(self) -> None:
        """Load ADR index from JSON."""
        if not self.index_path.exists():
            print(f"❌ Index not found: {self.index_path}", file=sys.stderr)
            print("💡 Run: python scripts/build_adr_index.py", file=sys.stderr)
            sys.exit(1)

        with open(self.index_path, "r", encoding="utf-8") as f:
            self.index_data = json.load(f)

        if not self.index_data or "adrs" not in self.index_data:
            print("❌ Invalid index format", file=sys.stderr)
            sys.exit(1)

    def search_text(self, query: str, adrs: List[Dict]) -> List[Dict]:
        """Search ADRs by text query (title, description, concerns)."""
        query_lower = query.lower()
        query_terms = set(query_lower.split())

        results = []

        for adr in adrs:
            score = 0
            matched_fields = []

            # Search in title (weight: 3)
            title = adr.get("title", "").lower()
            if query_lower in title:
                score += 3
                matched_fields.append("title")
            else:
                # Check individual terms
                title_terms = set(title.split())
                common_terms = query_terms & title_terms
                if common_terms:
                    score += len(common_terms) * 2
                    matched_fields.append("title")

            # Search in concerns (weight: 2)
            concerns = [c.lower() for c in adr.get("concerns", [])]
            if any(query_lower in c for c in concerns):
                score += 2
                matched_fields.append("concerns")
            elif any(term in concerns for term in query_terms):
                score += 1
                matched_fields.append("concerns")

            # Search in affected_layers (weight: 1)
            layers = [l.lower() for l in adr.get("affected_layers", [])]
            if any(query_lower in l for l in layers):
                score += 1
                matched_fields.append("layers")

            # Search in related ADRs (weight: 1)
            related = [str(r).lower() for r in adr.get("related_adrs", [])]
            if any(query_lower in r for r in related):
                score += 1
                matched_fields.append("related")

            # Search in implementation status (weight: 0.5)
            impl_status = adr.get("implementation_status", "").lower()
            if query_lower in impl_status:
                score += 0.5
                matched_fields.append("implementation")

            if score > 0:
                adr["_score"] = score
                adr["_matched_fields"] = matched_fields
                results.append(adr)

        # Sort by score descending
        results.sort(key=lambda x: x["_score"], reverse=True)

        return results

    def filter_by_layer(self, layer: str, adrs: List[Dict]) -> List[Dict]:
        """Filter ADRs by affected layer."""
        return [adr for adr in adrs if layer in adr.get("affected_layers", [])]

    def filter_by_status(self, status: str, adrs: List[Dict]) -> List[Dict]:
        """Filter ADRs by status."""
        status_upper = status.upper()
        return [adr for adr in adrs if adr.get("status", "").upper() == status_upper]

    def filter_by_concern(self, concern: str, adrs: List[Dict]) -> List[Dict]:
        """Filter ADRs by concern tag."""
        return [adr for adr in adrs if concern in adr.get("concerns", [])]

    def filter_by_category(self, category: str, adrs: List[Dict]) -> List[Dict]:
        """Filter ADRs by category folder."""
        return [adr for adr in adrs if adr.get("category") == category]

    def find_related(self, adr_number: str, adrs: List[Dict]) -> List[Dict]:
        """Find ADRs related to a specific ADR number."""
        # Normalize ADR number (0004 or ADR-0004)
        if not adr_number.startswith("ADR-"):
            adr_number = f"ADR-{adr_number}"

        related = []

        for adr in adrs:
            # Check if adr_number is in related_adrs
            related_refs = [str(r).upper() for r in adr.get("related_adrs", [])]
            if adr_number.upper() in related_refs:
                related.append(adr)
                continue

            # Check if current ADR number matches
            current_num = adr.get("adr_number", "")
            if not current_num.startswith("ADR-"):
                current_num = f"ADR-{current_num}"

            # If this is the ADR we're looking for, get its related ADRs
            if current_num.upper() == adr_number.upper():
                for other_adr in adrs:
                    other_num = other_adr.get("adr_number", "")
                    if not other_num.startswith("ADR-"):
                        other_num = f"ADR-{other_num}"

                    if other_num.upper() in related_refs:
                        related.append(other_adr)

        return related

    def find_by_module(self, module_pattern: str, adrs: List[Dict]) -> List[Dict]:
        """Find ADRs mentioning a specific module (fuzzy match in title/concerns)."""
        pattern_lower = module_pattern.lower()

        results = []
        for adr in adrs:
            # Check title
            if pattern_lower in adr.get("title", "").lower():
                results.append(adr)
                continue

            # Check concerns
            concerns = " ".join(adr.get("concerns", [])).lower()
            if pattern_lower in concerns:
                results.append(adr)
                continue

            # Check implementation status
            if pattern_lower in adr.get("implementation_status", "").lower():
                results.append(adr)

        return results

    def query(
        self,
        text: Optional[str] = None,
        layer: Optional[str] = None,
        status: Optional[str] = None,
        concern: Optional[str] = None,
        category: Optional[str] = None,
        related: Optional[str] = None,
        module: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict]:
        """Execute query with multiple filters."""
        if not self.index_data:
            self.load_index()

        adrs = self.index_data["adrs"]

        # Apply filters
        if related:
            adrs = self.find_related(related, adrs)

        if layer:
            adrs = self.filter_by_layer(layer, adrs)

        if status:
            adrs = self.filter_by_status(status, adrs)

        if concern:
            adrs = self.filter_by_concern(concern, adrs)

        if category:
            adrs = self.filter_by_category(category, adrs)

        if module:
            adrs = self.find_by_module(module, adrs)

        # Text search (if provided)
        if text:
            adrs = self.search_text(text, adrs)

        # Apply limit
        return adrs[:limit]

    def format_results(self, results: List[Dict], format_type: str = "text") -> str:
        """Format query results for output."""
        if format_type == "json":
            return json.dumps(results, indent=2)

        if format_type == "compact":
            output = []
            for adr in results:
                adr_num = adr.get("adr_number", "UNKNOWN")
                title = adr.get("title", "No title")
                status = adr.get("status", "UNKNOWN")
                output.append(f"{adr_num}: {title} [{status}]")
            return "\n".join(output)

        # Default: detailed text format
        if not results:
            return "No ADRs found matching query"

        output = [f"🔍 Found {len(results)} ADR(s)\n"]

        for i, adr in enumerate(results, 1):
            output.append(f"{'='*60}")
            output.append(f"#{i}: ADR-{adr.get('adr_number', 'UNKNOWN')}")
            output.append(f"{'='*60}\n")

            output.append(f"📄 Title: {adr.get('title', 'No title')}")
            output.append(f"📊 Status: {adr.get('status', 'UNKNOWN')}")

            if adr.get("date_created"):
                output.append(f"📅 Created: {adr['date_created']}")

            if adr.get("authors"):
                output.append(f"👤 Authors: {', '.join(adr['authors'])}")

            if adr.get("category"):
                output.append(f"📁 Category: {adr['category']}")

            if adr.get("affected_layers"):
                layers = ", ".join(adr["affected_layers"])
                output.append(f"🏗️  Affected Layers: {layers}")

            if adr.get("concerns"):
                concerns = ", ".join(adr["concerns"])
                output.append(f"🏷️  Concerns: {concerns}")

            if adr.get("related_adrs"):
                related = ", ".join([str(r) for r in adr["related_adrs"]])
                output.append(f"🔗 Related: {related}")

            if adr.get("implementation_status"):
                output.append(f"⚙️  Implementation: {adr['implementation_status']}")

            if adr.get("file_path"):
                output.append(f"📂 Path: {adr['file_path']}")

            # Show match score if available
            if "_score" in adr:
                output.append(f"🎯 Relevance Score: {adr['_score']:.1f}")

            if "_matched_fields" in adr:
                output.append(f"✅ Matched Fields: {', '.join(adr['_matched_fields'])}")

            output.append("")  # Blank line between results

        return "\n".join(output)

    def print_statistics(self) -> None:
        """Print index statistics."""
        if not self.index_data:
            self.load_index()

        stats = self.index_data.get("statistics", {})
        meta = self.index_data.get("metadata", {})

        print("📊 ADR Index Statistics")
        print("=" * 60)
        print(f"Total ADRs: {meta.get('total_adrs', 0)}")
        print(f"Last Updated: {meta.get('generated_at', 'Unknown')}")
        print()

        # Status breakdown
        if "by_status" in stats:
            print("📈 By Status:")
            for status, count in sorted(stats["by_status"].items()):
                print(f"  {status}: {count}")
            print()

        # Layer breakdown
        if "by_layer" in stats:
            print("🏗️  By Layer:")
            for layer, count in sorted(stats["by_layer"].items()):
                print(f"  {layer}: {count}")
            print()

        # Category breakdown
        if "by_category" in stats:
            print("📁 By Category:")
            for category, count in sorted(stats["by_category"].items()):
                print(f"  {category}: {count}")
            print()

        # Concern breakdown
        if "by_concern" in stats:
            print("🏷️  By Concern (Top 10):")
            concerns = sorted(stats["by_concern"].items(), key=lambda x: x[1], reverse=True)
            for concern, count in concerns[:10]:
                print(f"  {concern}: {count}")


def main():
    parser = argparse.ArgumentParser(description="Query ADR index with semantic search and filters")
    parser.add_argument(
        "query", nargs="?", help="Text search query (searches title, concerns, layers)"
    )
    parser.add_argument("--layer", help="Filter by layer (e.g., layer3_execution)")
    parser.add_argument("--status", help="Filter by status (e.g., IMPLEMENTED)")
    parser.add_argument("--concern", help="Filter by concern tag (e.g., performance)")
    parser.add_argument(
        "--category", help="Filter by category folder (e.g., 03-layer2-orchestration)"
    )
    parser.add_argument("--related", help="Find ADRs related to specific ADR number (e.g., 0004)")
    parser.add_argument(
        "--module", help="Find ADRs mentioning specific module (e.g., agent_fabric)"
    )
    parser.add_argument(
        "--format",
        choices=["text", "json", "compact"],
        default="text",
        help="Output format (default: text)",
    )
    parser.add_argument(
        "--limit", type=int, default=20, help="Maximum number of results (default: 20)"
    )
    parser.add_argument("--stats", action="store_true", help="Show index statistics")
    parser.add_argument(
        "--base-path",
        type=Path,
        default=Path.cwd(),
        help="Base repository path (default: current directory)",
    )

    args = parser.parse_args()

    query_engine = ADRQuery(args.base_path)

    # Show statistics
    if args.stats:
        query_engine.print_statistics()
        sys.exit(0)

    # Require at least one query parameter
    if not any(
        [
            args.query,
            args.layer,
            args.status,
            args.concern,
            args.category,
            args.related,
            args.module,
        ]
    ):
        parser.print_help()
        sys.exit(1)

    # Execute query
    results = query_engine.query(
        text=args.query,
        layer=args.layer,
        status=args.status,
        concern=args.concern,
        category=args.category,
        related=args.related,
        module=args.module,
        limit=args.limit,
    )

    # Format and print results
    output = query_engine.format_results(results, args.format)
    print(output)

    # Exit with status code
    if not results:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
