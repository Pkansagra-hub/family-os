#!/usr/bin/env python3
"""
Update ADR Links - Maintain cross-references between ADRs

This script scans ADRs for references to other ADRs and updates:
1. YAML frontmatter related_adrs field
2. Broken links to moved ADRs
3. Bidirectional relationships (if A references B, ensure B knows about A)

Usage:
    python scripts/update_adr_links.py --scan           # Scan for broken links
    python scripts/update_adr_links.py --fix            # Fix broken links
    python scripts/update_adr_links.py --bidirectional  # Add reverse references
    python scripts/update_adr_links.py --adr 0004       # Update links for specific ADR
    python scripts/update_adr_links.py --dry-run        # Show changes without applying
"""

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Set, Tuple

import frontmatter


class ADRLinkUpdater:
    """Scan and update ADR cross-references."""

    def __init__(self, base_path: Path, dry_run: bool = False):
        self.base_path = base_path
        self.decisions_path = base_path / "docs" / "architecture" / "decisions"
        self.dry_run = dry_run
        self.adr_map: Dict[str, Path] = {}  # ADR number -> file path
        self.link_graph: Dict[str, Set[str]] = defaultdict(set)  # ADR -> referenced ADRs
        self.broken_links: List[Tuple[Path, str, str]] = []  # (file, broken_link, line)

    def build_adr_map(self) -> None:
        """Build map of ADR numbers to file paths."""
        print("📂 Scanning for ADR files...")

        for pattern in ["**/*.md", "*/*.md"]:
            for file in self.decisions_path.glob(pattern):
                # Skip meta files
                if "00-meta" in str(file):
                    continue
                if file.name.lower() in ["readme.md", "index.md", "index.yml"]:
                    continue

                # Extract ADR number from filename
                match = re.search(r"(\d{4}[a-z]?)", file.name)
                if match:
                    adr_num = match.group(1)
                    self.adr_map[adr_num] = file

        print(f"✅ Found {len(self.adr_map)} ADR files\n")

    def extract_adr_references(self, content: str) -> Set[str]:
        """Extract ADR references from content."""
        references = set()

        # Pattern 1: ADR-0004 or ADR-0004a
        for match in re.finditer(r"ADR-(\d{4}[a-z]?)", content, re.IGNORECASE):
            references.add(match.group(1))

        # Pattern 2: [0004-title.md]
        for match in re.finditer(r"\[(\d{4}[a-z]?)[^]]*\.md\]", content):
            references.add(match.group(1))

        # Pattern 3: decisions/0004-title/
        for match in re.finditer(r"decisions/(\d{4}[a-z]?)-", content):
            references.add(match.group(1))

        # Pattern 4: #0004 (issue-style reference)
        for match in re.finditer(r"#(\d{4}[a-z]?)\b", content):
            references.add(match.group(1))

        return references

    def scan_adr_links(self, adr_file: Path) -> Dict:
        """Scan a single ADR for references to other ADRs."""
        result = {
            "adr_number": None,
            "file_path": adr_file,
            "references_in_content": set(),
            "references_in_frontmatter": set(),
            "broken_links": [],
            "missing_frontmatter": False,
        }

        try:
            with open(adr_file, "r", encoding="utf-8") as f:
                content = f.read()

            # Get ADR number from filename
            match = re.search(r"(\d{4}[a-z]?)", adr_file.name)
            if match:
                result["adr_number"] = match.group(1)

            # Parse frontmatter
            if content.startswith("---"):
                post = frontmatter.loads(content)
                metadata = post.metadata
                body = post.content

                # Extract frontmatter references
                if "related_adrs" in metadata and isinstance(metadata["related_adrs"], list):
                    result["references_in_frontmatter"] = {
                        str(ref).replace("ADR-", "") for ref in metadata["related_adrs"]
                    }
            else:
                result["missing_frontmatter"] = True
                body = content

            # Extract content references
            result["references_in_content"] = self.extract_adr_references(body)

            # Check for broken links
            for ref in result["references_in_content"]:
                if ref not in self.adr_map:
                    result["broken_links"].append(ref)

        except Exception as e:
            print(f"⚠️  Error scanning {adr_file}: {e}", file=sys.stderr)

        return result

    def scan_all_links(self) -> Dict[str, Dict]:
        """Scan all ADRs for links."""
        print("🔍 Scanning ADR cross-references...\n")

        results = {}

        for adr_num, adr_file in sorted(self.adr_map.items()):
            scan_result = self.scan_adr_links(adr_file)
            results[adr_num] = scan_result

            # Build link graph
            self.link_graph[adr_num] = scan_result["references_in_content"]

            # Track broken links
            for broken_ref in scan_result["broken_links"]:
                self.broken_links.append((adr_file, broken_ref, "content"))

        return results

    def sync_frontmatter_with_content(self, scan_results: Dict[str, Dict]) -> int:
        """Update frontmatter related_adrs to match content references."""
        changes_made = 0

        for adr_num, result in scan_results.items():
            adr_file = result["file_path"]
            content_refs = result["references_in_content"]
            frontmatter_refs = result["references_in_frontmatter"]

            # Skip if no content references
            if not content_refs:
                continue

            # Check if update needed
            if content_refs == frontmatter_refs:
                continue

            # Update needed
            print(f"📝 Updating ADR-{adr_num}: {adr_file.name}")
            print(f"   Content refs: {sorted(content_refs)}")
            print(f"   Frontmatter refs: {sorted(frontmatter_refs)}")

            if not self.dry_run:
                self._update_frontmatter_refs(adr_file, sorted(content_refs))
                changes_made += 1
            else:
                print("   [DRY RUN - no changes made]")
                changes_made += 1

            print()

        return changes_made

    def _update_frontmatter_refs(self, adr_file: Path, references: List[str]) -> None:
        """Update frontmatter related_adrs field."""
        try:
            with open(adr_file, "r", encoding="utf-8") as f:
                content = f.read()

            if not content.startswith("---"):
                print("   ⚠️  No frontmatter found, skipping")
                return

            post = frontmatter.loads(content)

            # Update related_adrs
            post.metadata["related_adrs"] = [f"ADR-{ref}" for ref in references]

            # Write back
            with open(adr_file, "w", encoding="utf-8") as f:
                f.write(frontmatter.dumps(post))

            print("   ✅ Updated frontmatter")

        except Exception as e:
            print(f"   ❌ Error updating {adr_file}: {e}", file=sys.stderr)

    def add_bidirectional_refs(self, scan_results: Dict[str, Dict]) -> int:
        """Add reverse references (if A references B, ensure B's frontmatter mentions A)."""
        changes_made = 0

        # Build reverse reference map
        reverse_refs: Dict[str, Set[str]] = defaultdict(set)
        for adr_num, result in scan_results.items():
            for ref in result["references_in_content"]:
                if ref in self.adr_map:  # Only add valid references
                    reverse_refs[ref].add(adr_num)

        # Update frontmatter for each ADR
        for adr_num, referrers in sorted(reverse_refs.items()):
            result = scan_results.get(adr_num)
            if not result:
                continue

            adr_file = result["file_path"]
            current_refs = result["references_in_frontmatter"] | result["references_in_content"]

            # Add referrers that aren't already mentioned
            new_refs = referrers - current_refs

            if new_refs:
                print(f"🔗 Adding bidirectional refs to ADR-{adr_num}")
                print(f"   Referenced by: {sorted(new_refs)}")

                if not self.dry_run:
                    # Merge with existing references
                    all_refs = sorted(current_refs | new_refs)
                    self._update_frontmatter_refs(adr_file, all_refs)
                    changes_made += 1
                else:
                    print("   [DRY RUN - no changes made]")
                    changes_made += 1

                print()

        return changes_made

    def report_broken_links(self) -> None:
        """Report broken ADR links."""
        if not self.broken_links:
            print("✅ No broken links found\n")
            return

        print(f"❌ Found {len(self.broken_links)} broken link(s)\n")

        by_file = defaultdict(list)
        for file, broken_ref, location in self.broken_links:
            by_file[file].append((broken_ref, location))

        for file, refs in sorted(by_file.items()):
            rel_path = file.relative_to(self.decisions_path)
            print(f"📄 {rel_path}")
            for broken_ref, location in refs:
                print(f"   • ADR-{broken_ref} (in {location})")
            print()

    def generate_link_stats(self, scan_results: Dict[str, Dict]) -> None:
        """Generate statistics about ADR linking."""
        print("📊 ADR Linking Statistics")
        print("=" * 60)

        total_adrs = len(scan_results)
        adrs_with_refs = sum(1 for r in scan_results.values() if r["references_in_content"])
        total_refs = sum(len(r["references_in_content"]) for r in scan_results.values())
        broken_refs = sum(len(r["broken_links"]) for r in scan_results.values())

        print(f"Total ADRs: {total_adrs}")
        print(f"ADRs with references: {adrs_with_refs} ({adrs_with_refs/total_adrs*100:.1f}%)")
        print(f"Total references: {total_refs}")
        print(f"Broken references: {broken_refs}")
        print(f"Average refs per ADR: {total_refs/total_adrs:.1f}")
        print()

        # Most referenced ADRs
        incoming_refs = defaultdict(int)
        for result in scan_results.values():
            for ref in result["references_in_content"]:
                incoming_refs[ref] += 1

        if incoming_refs:
            print("🔗 Most Referenced ADRs (Top 10):")
            for adr_num, count in sorted(incoming_refs.items(), key=lambda x: x[1], reverse=True)[
                :10
            ]:
                if adr_num in scan_results:
                    adr_file = scan_results[adr_num]["file_path"]
                    print(f"  ADR-{adr_num}: {count} reference(s) - {adr_file.name}")
            print()

        # ADRs with most outgoing refs
        print("📤 ADRs with Most References (Top 10):")
        by_refs = sorted(
            scan_results.items(), key=lambda x: len(x[1]["references_in_content"]), reverse=True
        )
        for adr_num, result in by_refs[:10]:
            ref_count = len(result["references_in_content"])
            if ref_count > 0:
                print(f"  ADR-{adr_num}: {ref_count} reference(s) - {result['file_path'].name}")


def main():
    parser = argparse.ArgumentParser(description="Update and maintain ADR cross-references")
    parser.add_argument(
        "--scan", action="store_true", help="Scan for broken links and inconsistencies"
    )
    parser.add_argument(
        "--fix", action="store_true", help="Fix broken links and sync frontmatter with content"
    )
    parser.add_argument(
        "--bidirectional",
        action="store_true",
        help="Add bidirectional references (if A refs B, add B refs A)",
    )
    parser.add_argument("--adr", help="Update links for specific ADR only (e.g., 0004)")
    parser.add_argument("--stats", action="store_true", help="Show link statistics")
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would be changed without making changes"
    )
    parser.add_argument(
        "--base-path",
        type=Path,
        default=Path.cwd(),
        help="Base repository path (default: current directory)",
    )

    args = parser.parse_args()

    # Require at least one action
    if not any([args.scan, args.fix, args.bidirectional, args.stats]):
        parser.print_help()
        sys.exit(1)

    updater = ADRLinkUpdater(args.base_path, dry_run=args.dry_run)

    # Build ADR map
    updater.build_adr_map()

    # Scan all links
    scan_results = updater.scan_all_links()

    # Report broken links
    if args.scan or args.fix:
        updater.report_broken_links()

    # Show statistics
    if args.stats:
        updater.generate_link_stats(scan_results)

    # Fix frontmatter
    if args.fix:
        print("🔧 Syncing frontmatter with content references...\n")
        changes = updater.sync_frontmatter_with_content(scan_results)
        print(f"✅ Updated {changes} ADR(s)\n")

    # Add bidirectional references
    if args.bidirectional:
        print("🔗 Adding bidirectional references...\n")
        changes = updater.add_bidirectional_refs(scan_results)
        print(f"✅ Updated {changes} ADR(s)\n")

    # Summary
    if args.dry_run:
        print(
            "💡 This was a dry run. Use --fix or --bidirectional without --dry-run to apply changes."
        )


if __name__ == "__main__":
    main()
    main()
