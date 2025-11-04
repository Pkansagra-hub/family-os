#!/usr/bin/env python3
"""
Build ADR Index - Extract YAML frontmatter and generate searchable JSON index

This script scans all ADR files in docs/architecture/decisions/, extracts YAML frontmatter,
and generates a comprehensive JSON index for AI agent queries.

Usage:
    python scripts/build_adr_index.py                    # Build full index
    python scripts/build_adr_index.py --validate         # Validate index matches filesystem
    python scripts/build_adr_index.py --folder 01-foundation  # Build index for specific folder

Output:
    docs/architecture/decisions/00-meta/adr_index.json
"""

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional

import frontmatter
import yaml


class DateTimeEncoder(json.JSONEncoder):
    """Custom JSON encoder that converts datetime/date objects to ISO format strings."""

    def default(self, obj):
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        return super().default(obj)


class ADRIndexBuilder:
    """Build searchable JSON index from ADR YAML frontmatter."""

    def __init__(self, base_path: Path):
        self.base_path = base_path
        self.decisions_path = base_path / "docs" / "architecture" / "decisions"
        self.output_path = self.decisions_path / "00-meta" / "adr_index.json"
        self.adrs: List[Dict] = []

    def _convert_dates_to_strings(self, obj):
        """Recursively convert date/datetime objects to ISO format strings."""
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        elif isinstance(obj, dict):
            return {k: self._convert_dates_to_strings(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._convert_dates_to_strings(item) for item in obj]
        return obj

    def extract_frontmatter(self, adr_file: Path) -> Optional[Dict]:
        """Extract YAML frontmatter from ADR file."""
        try:
            with open(adr_file, "r", encoding="utf-8") as f:
                post = frontmatter.load(f)

            if not post.metadata:
                # No frontmatter found, extract basic info from filename and content
                return self._extract_basic_info(adr_file, post.content)

            # Convert frontmatter to dict and handle date objects
            metadata = dict(post.metadata)
            metadata = self._convert_dates_to_strings(metadata)

            # Add file metadata
            metadata["file_path"] = str(adr_file.relative_to(self.decisions_path))
            metadata["file_name"] = adr_file.name

            # Extract summary from content (first paragraph after title)
            metadata["summary"] = self._extract_summary(post.content)

            return metadata

        except Exception as e:
            print(f"⚠️  Error processing {adr_file.name}: {e}", file=sys.stderr)
            return None

    def _extract_basic_info(self, adr_file: Path, content: str) -> Dict:
        """Extract basic info when frontmatter is missing."""
        # Parse filename: 0004-56-module-5-layer-architecture.md
        filename = adr_file.stem
        parts = filename.split("-", 1)

        adr_number = parts[0] if parts else "unknown"
        title = parts[1].replace("-", " ").title() if len(parts) > 1 else filename

        # Extract title from first line of content
        lines = content.split("\n")
        for line in lines:
            if line.startswith("# ADR-"):
                title = line.replace("# ADR-", "").replace(adr_number + ":", "").strip()
                break

        # Extract status from content
        status = "UNKNOWN"
        for line in lines:
            if line.startswith("**Status:**") or line.startswith("Status:"):
                status = line.split(":", 1)[1].strip().replace("*", "").upper()
                break

        return {
            "adr_number": adr_number,
            "title": title,
            "status": status,
            "file_path": str(adr_file.relative_to(self.decisions_path)),
            "file_name": adr_file.name,
            "summary": self._extract_summary(content),
            "affected_layers": [],
            "affected_modules": [],
            "concerns": [],
            "related_adrs": [],
            "implementation_status": "UNKNOWN",
            "missing_frontmatter": True,
        }

    def _extract_summary(self, content: str) -> str:
        """Extract first meaningful paragraph as summary."""
        lines = content.split("\n")
        summary_lines = []
        in_summary = False

        for line in lines:
            line = line.strip()

            # Skip title and metadata lines
            if line.startswith("#") or line.startswith("**"):
                in_summary = False
                continue

            # Start collecting after first empty line
            if not line:
                if summary_lines:
                    break
                in_summary = True
                continue

            if in_summary and line:
                summary_lines.append(line)
                if len(" ".join(summary_lines)) > 200:
                    break

        summary = " ".join(summary_lines)[:200]
        return summary if summary else "No summary available"

    def scan_directory(self, folder: Optional[str] = None) -> None:
        """Scan directory for ADR files."""
        if folder:
            search_path = self.decisions_path / folder
            if not search_path.exists():
                print(f"❌ Folder not found: {folder}", file=sys.stderr)
                sys.exit(1)
        else:
            search_path = self.decisions_path

        print(f"🔍 Scanning {search_path} for ADR files...")

        # Find all .md files except meta files
        adr_files = []
        for pattern in ["**/*.md", "*/*.md"]:
            for file in search_path.glob(pattern):
                # Skip meta files
                if "00-meta" in str(file):
                    continue
                if file.name.lower() in ["readme.md", "index.md"]:
                    continue

                adr_files.append(file)

        print(f"📄 Found {len(adr_files)} ADR files")

        # Extract frontmatter
        for adr_file in sorted(adr_files):
            metadata = self.extract_frontmatter(adr_file)
            if metadata:
                self.adrs.append(metadata)
                status_icon = "✅" if not metadata.get("missing_frontmatter") else "⚠️ "
                print(
                    f"  {status_icon} {metadata.get('adr_number', '???')}: {metadata.get('title', adr_file.name)}"
                )

    def build_index(self) -> Dict:
        """Build JSON index structure."""
        # Group ADRs by category
        by_category = {}
        by_layer = {}
        by_status = {}
        by_concern = {}

        for adr in self.adrs:
            # By category (from folder name)
            folder = Path(adr["file_path"]).parts[0] if adr["file_path"] else "uncategorized"
            if folder not in by_category:
                by_category[folder] = []
            by_category[folder].append(adr["adr_number"])

            # By layer
            for layer in adr.get("affected_layers", []):
                if layer not in by_layer:
                    by_layer[layer] = []
                by_layer[layer].append(adr["adr_number"])

            # By status
            status = adr.get("status", "UNKNOWN")
            if status not in by_status:
                by_status[status] = []
            by_status[status].append(adr["adr_number"])

            # By concern
            for concern in adr.get("concerns", []):
                if concern not in by_concern:
                    by_concern[concern] = []
                by_concern[concern].append(adr["adr_number"])

        return {
            "version": "1.0.0",
            "generated_at": datetime.now().isoformat(),
            "total_adrs": len(self.adrs),
            "statistics": {
                "by_status": {k: len(v) for k, v in by_status.items()},
                "by_category": {k: len(v) for k, v in by_category.items()},
                "by_layer": {k: len(v) for k, v in by_layer.items()},
                "by_concern": {k: len(v) for k, v in by_concern.items()},
                "missing_frontmatter": sum(
                    1 for adr in self.adrs if adr.get("missing_frontmatter")
                ),
            },
            "indexes": {
                "by_category": by_category,
                "by_layer": by_layer,
                "by_status": by_status,
                "by_concern": by_concern,
            },
            "adrs": sorted(self.adrs, key=lambda x: x.get("adr_number", "")),
        }

    def save_index(self, index: Dict) -> None:
        """Save index to JSON file."""
        self.output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(self.output_path, "w", encoding="utf-8") as f:
            json.dump(index, f, indent=2, ensure_ascii=False, cls=DateTimeEncoder)

        print(f"\n✅ Index saved to {self.output_path}")

    def update_folder_indices(self) -> None:
        """Update index.yml files in category folders with ADR metadata."""
        print("\n🔄 Updating folder-level index.yml files...")

        # Group ADRs by category folder
        folders = {}
        for adr in self.adrs:
            # Get category folder from file_path (e.g., "01-foundation")
            file_path = Path(adr["file_path"])
            parts = file_path.parts

            # Skip if not in a category folder structure
            if len(parts) < 2:
                continue

            category_folder = parts[0]

            # Only process numbered category folders (01-foundation, 02-coordination, etc.)
            if not category_folder[0:2].isdigit():
                continue

            if category_folder not in folders:
                folders[category_folder] = []

            folders[category_folder].append(
                {
                    "adr_number": adr.get("adr_number", ""),
                    "title": adr.get("title", ""),
                    "status": adr.get("status", "UNKNOWN"),
                    "summary": adr.get("summary", ""),
                    "file_path": adr.get("file_path", ""),
                    "affected_layers": adr.get("affected_layers", []),
                    "affected_modules": adr.get("affected_modules", []),
                    "concerns": adr.get("concerns", []),
                }
            )

        # Update each folder's index.yml
        updated_count = 0
        for folder_name, folder_adrs in sorted(folders.items()):
            folder_path = self.decisions_path / folder_name
            index_file = folder_path / "index.yml"

            if not folder_path.exists():
                print(f"  ⚠️  Skipping {folder_name}: folder not found")
                continue

            # Sort ADRs by number
            folder_adrs.sort(key=lambda x: x["adr_number"])

            # Build YAML content
            yaml_content = f"""# ADR Category Index: {folder_name}
# Auto-generated by build_adr_index.py
# Last updated: {datetime.now().isoformat()}

category: {folder_name}
total_adrs: {len(folder_adrs)}

adrs:
"""

            for adr in folder_adrs:
                yaml_content += f"""
  - adr_number: "{adr['adr_number']}"
    title: "{adr['title']}"
    status: {adr['status']}
    file_path: "{adr['file_path']}"
    summary: "{adr['summary']}"
    affected_layers: {adr['affected_layers']}
    affected_modules: {adr['affected_modules']}
    concerns: {adr['concerns']}
"""

            # Write to file
            with open(index_file, "w", encoding="utf-8") as f:
                f.write(yaml_content)

            updated_count += 1
            print(f"  ✅ Updated {folder_name}/index.yml ({len(folder_adrs)} ADRs)")

        if updated_count == 0:
            print("  ℹ️  No category folders found to update")
        else:
            print(f"\n✅ Updated {updated_count} folder index files")

    def validate_index(self) -> bool:
        """Validate that index matches filesystem."""
        if not self.output_path.exists():
            print("❌ Index file does not exist", file=sys.stderr)
            return False

        with open(self.output_path, "r", encoding="utf-8") as f:
            index = json.load(f)

        # Count ADR files in filesystem
        adr_files = list(self.decisions_path.glob("**/*.md"))
        # Filter out meta files
        adr_files = [
            f
            for f in adr_files
            if "00-meta" not in str(f) and f.name.lower() not in ["readme.md", "index.md"]
        ]

        indexed_count = index["total_adrs"]
        filesystem_count = len(adr_files)

        print(f"\n📊 Validation Results:")
        print(f"  Index entries: {indexed_count}")
        print(f"  Filesystem ADRs: {filesystem_count}")

        if indexed_count == filesystem_count:
            print("  ✅ Index is up-to-date")
            return True
        else:
            print(f"  ❌ Mismatch: {abs(indexed_count - filesystem_count)} difference")
            print("  💡 Run: python scripts/build_adr_index.py (without --validate)")
            return False

    def print_summary(self, index: Dict) -> None:
        """Print index summary."""
        stats = index["statistics"]

        print("\n" + "=" * 60)
        print("📊 ADR Index Summary")
        print("=" * 60)

        print(f"\n📈 Total ADRs: {index['total_adrs']}")

        print("\n� By Status:")
        for status, count in sorted(stats["by_status"].items()):
            print(f"  {status}: {count}")

        print("\n🗂️  By Category:")
        for category, count in sorted(stats["by_category"].items()):
            print(f"  {category}: {count}")

        print("\n🏗️  By Layer:")
        for layer, count in sorted(stats["by_layer"].items()):
            print(f"  {layer}: {count}")

        print("\n🏷️  By Concern:")
        for concern, count in sorted(stats["by_concern"].items()):
            print(f"  {concern}: {count}")

        if stats["missing_frontmatter"] > 0:
            print(f"\n⚠️  Missing Frontmatter: {stats['missing_frontmatter']} ADRs")
            print("   💡 Run: python scripts/validate_adr_metadata.py --fix")

        print("\n" + "=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Build searchable JSON index from ADR YAML frontmatter"
    )
    parser.add_argument("--folder", help="Build index for specific folder only", default=None)
    parser.add_argument(
        "--validate", action="store_true", help="Validate index matches filesystem (no rebuild)"
    )
    parser.add_argument(
        "--base-path",
        type=Path,
        default=Path.cwd(),
        help="Base repository path (default: current directory)",
    )

    args = parser.parse_args()

    builder = ADRIndexBuilder(args.base_path)

    if args.validate:
        success = builder.validate_index()
        sys.exit(0 if success else 1)

    # Scan and build
    builder.scan_directory(args.folder)

    if not builder.adrs:
        print("⚠️  No ADRs found", file=sys.stderr)
        sys.exit(1)

    # Build index
    index = builder.build_index()

    # Save
    builder.save_index(index)

    # Update folder-level indices
    builder.update_folder_indices()

    # Print summary
    builder.print_summary(index)

    print("\n✅ Index build complete")
    print(f"📁 Output: {builder.output_path}")
    print('\n💡 Query the index with: python scripts/query_adrs.py "your query"')


if __name__ == "__main__":
    main()
