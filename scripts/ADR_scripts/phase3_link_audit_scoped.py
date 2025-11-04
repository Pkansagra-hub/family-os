#!/usr/bin/env python3
"""
Phase 3: Link Audit (Scoped to specified ADRs)
Finds all references TO and FROM specified ADRs before file migration.
"""

import argparse
import json
import re
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional

WORKSPACE_ROOT = Path(__file__).parent.parent.parent
DOCS_ROOT = WORKSPACE_ROOT / "docs"
ADR_DIR = DOCS_ROOT / "architecture" / "decisions"

# Default scope: ADRs 0001-0004 (can be overridden via command line)
DEFAULT_TARGET_ADRS = ["0001", "0002", "0003", "0004"]


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Link audit for specified ADRs")
    parser.add_argument(
        "--adrs",
        nargs="+",
        default=DEFAULT_TARGET_ADRS,
        help="ADR numbers to audit (e.g., 0005 0006 0007)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output report filename (default: LINK_AUDIT_REPORT_<first>-<last>.md)",
    )
    return parser.parse_args()


def run_ripgrep(pattern: str, path: str, extra_args: List[str] | None = None) -> List[str]:
    """Run ripgrep and return results."""
    cmd = ["rg", pattern, path, "--type", "md"]
    if extra_args:
        cmd.extend(extra_args)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            cwd=WORKSPACE_ROOT,
        )
        return result.stdout.strip().split("\n") if result.stdout.strip() else []
    except FileNotFoundError:
        print("⚠️  ripgrep (rg) not found. Please restart your terminal to pick up the new PATH.")
        return []
    except Exception as e:
        print(f"⚠️  Error running ripgrep: {e}")
        return []


def search_files_python(pattern: str, root_path: Path, file_pattern: str = "**/*.md") -> List[Dict]:
    """Pure Python file search (fallback when ripgrep unavailable)."""
    results = []

    # Compile regex pattern
    regex = re.compile(pattern)

    # Search all markdown files
    for md_file in root_path.glob(file_pattern):
        try:
            content = md_file.read_text(encoding="utf-8")
            lines = content.split("\n")

            for line_num, line in enumerate(lines, start=1):
                if regex.search(line):
                    results.append(
                        {
                            "file": str(md_file.relative_to(WORKSPACE_ROOT)),
                            "line": line_num,
                            "text": line.strip(),
                        }
                    )
        except Exception:
            continue

    return results


def find_references_to_adrs(target_adrs: List[str]) -> Dict[str, List[Dict]]:
    """Find all references TO target ADRs from anywhere in docs/."""
    print(f"\n🔍 Finding references TO ADRs {', '.join(target_adrs)}...")

    references = defaultdict(list)

    # Pattern: ADR-0001, ADR-0002, ADR-0003, ADR-0004
    for adr_num in target_adrs:
        pattern = f"ADR-{adr_num}"
        results = run_ripgrep(pattern, str(DOCS_ROOT), ["--json"])

        for line in results:
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                if data.get("type") == "match":
                    file_path = data["data"]["path"]["text"]
                    line_num = data["data"]["line_number"]
                    match_text = data["data"]["lines"]["text"].strip()

                    references[adr_num].append(
                        {"file": file_path, "line": line_num, "text": match_text}
                    )
            except json.JSONDecodeError:
                continue

    return references


def find_references_from_adrs(target_adrs: List[str]) -> Dict[str, List[Dict]]:
    """Find all references FROM target ADRs (relative links, absolute links)."""
    print(f"\n🔍 Finding references FROM ADRs {', '.join(target_adrs)}...")

    references = defaultdict(list)

    # Find all target ADR files (including sub-ADRs)
    adr_files = []
    for adr_num in target_adrs:
        adr_files.extend(ADR_DIR.glob(f"{adr_num}*.md"))

    # Pattern: Markdown links [text](path)
    link_pattern = re.compile(r"\[([^\]]+)\]\(([^\)]+)\)")

    for adr_file in adr_files:
        if not adr_file.exists():
            continue

        content = adr_file.read_text(encoding="utf-8")
        lines = content.split("\n")

        for line_num, line in enumerate(lines, start=1):
            matches = link_pattern.findall(line)
            for link_text, link_path in matches:
                # Skip external links
                if link_path.startswith("http://") or link_path.startswith("https://"):
                    continue

                # Categorize link type
                link_type = "unknown"
                if link_path.startswith("../"):
                    link_type = "relative_parent"
                elif link_path.startswith("./"):
                    link_type = "relative_current"
                elif link_path.startswith("/"):
                    link_type = "absolute"
                elif "architecture_diagrams/" in link_path:
                    link_type = "diagram"
                else:
                    link_type = "relative_implicit"

                references[adr_file.name].append(
                    {
                        "line": line_num,
                        "link_text": link_text,
                        "link_path": link_path,
                        "link_type": link_type,
                    }
                )

    return references


def find_diagram_references(target_adrs: List[str]) -> Dict[str, List[Dict]]:
    """Find all diagram references in target ADRs."""
    print(f"\n🔍 Finding diagram references in ADRs {', '.join(target_adrs)}...")

    references = defaultdict(list)
    pattern = "architecture_diagrams/"

    for adr_num in target_adrs:
        results = run_ripgrep(pattern, str(ADR_DIR), [f"--glob", f"{adr_num}*.md"])

        for line in results:
            if ":" not in line:
                continue

            parts = line.split(":", 2)
            if len(parts) >= 3:
                file_path = parts[0]
                line_num = parts[1]
                match_text = parts[2].strip()

                file_name = Path(file_path).name
                references[file_name].append({"line": line_num, "text": match_text})

    return references


def generate_report(
    target_adrs: List[str],
    refs_to: Dict[str, List[Dict]],
    refs_from: Dict[str, List[Dict]],
    diagram_refs: Dict[str, List[Dict]],
    output_filename: Optional[str] = None,
):
    """Generate comprehensive link audit report."""

    if output_filename is None:
        first_adr = min(target_adrs)
        last_adr = max(target_adrs)
        output_filename = f"LINK_AUDIT_REPORT_{first_adr}-{last_adr}.md"

    report_path = WORKSPACE_ROOT / output_filename

    # Count totals
    total_refs_to = sum(len(refs) for refs in refs_to.values())
    total_refs_from = sum(len(refs) for refs in refs_from.values())
    total_diagram_refs = sum(len(refs) for refs in diagram_refs.values())
    unique_files_referencing = len(set(ref["file"] for refs in refs_to.values() for ref in refs))

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(f"# Link Audit Report - ADRs {', '.join(target_adrs)}\n\n")
        f.write("**Date:** November 3, 2025\n")
        f.write(f"**Scope:** ADRs {', '.join(target_adrs)} (including sub-ADRs)\n")
        f.write("**Purpose:** Identify all links before Phase 4 file migration\n\n")

        f.write("---\n\n")
        f.write("## 📊 Summary Statistics\n\n")
        f.write(f"- **References TO target ADRs:** {total_refs_to}\n")
        f.write(f"- **References FROM target ADRs:** {total_refs_from}\n")
        f.write(f"- **Diagram references:** {total_diagram_refs}\n")
        f.write(f"- **Unique files referencing these ADRs:** {unique_files_referencing}\n\n")

        f.write("---\n\n")
        f.write("## 🔗 References TO Target ADRs (Incoming Links)\n\n")
        f.write(f"These are all places in `docs/` that reference ADRs {', '.join(target_adrs)}.\n")
        f.write("**Action needed:** Update these after moving ADR files.\n\n")

        for adr_num in sorted(refs_to.keys()):
            refs = refs_to[adr_num]
            f.write(f"### ADR-{adr_num} ({len(refs)} references)\n\n")

            # Group by file
            by_file = defaultdict(list)
            for ref in refs:
                by_file[ref["file"]].append(ref)

            for file_path in sorted(by_file.keys()):
                file_refs = by_file[file_path]
                f.write(f"**`{file_path}`** ({len(file_refs)} references)\n\n")
                for ref in file_refs[:5]:  # Show first 5
                    f.write(f"- Line {ref['line']}: `{ref['text'][:80]}...`\n")
                if len(file_refs) > 5:
                    f.write(f"- ... and {len(file_refs) - 5} more\n")
                f.write("\n")

        f.write("---\n\n")
        f.write("## 🔗 References FROM Target ADRs (Outgoing Links)\n\n")
        f.write(f"These are all links inside ADRs {', '.join(target_adrs)} pointing elsewhere.\n")
        f.write("**Action needed:** Update relative paths after moving files.\n\n")

        for adr_file in sorted(refs_from.keys()):
            refs = refs_from[adr_file]
            if not refs:
                continue

            f.write(f"### {adr_file} ({len(refs)} links)\n\n")

            # Group by link type
            by_type = defaultdict(list)
            for ref in refs:
                by_type[ref["link_type"]].append(ref)

            for link_type in sorted(by_type.keys()):
                type_refs = by_type[link_type]
                f.write(f"**{link_type.replace('_', ' ').title()}** ({len(type_refs)} links)\n\n")
                for ref in type_refs[:5]:
                    f.write(f"- Line {ref['line']}: [{ref['link_text']}]({ref['link_path']})\n")
                if len(type_refs) > 5:
                    f.write(f"- ... and {len(type_refs) - 5} more\n")
                f.write("\n")

        f.write("---\n\n")
        f.write("## 📐 Diagram References\n\n")
        f.write("Architecture diagram references in target ADRs.\n\n")

        if not diagram_refs:
            f.write("*No diagram references found*\n\n")
        else:
            for adr_file in sorted(diagram_refs.keys()):
                refs = diagram_refs[adr_file]
                f.write(f"### {adr_file} ({len(refs)} references)\n\n")
                for ref in refs:
                    f.write(f"- Line {ref['line']}: `{ref['text'][:80]}...`\n")
                f.write("\n")

        f.write("---\n\n")
        f.write("## ✅ Next Steps (Phase 4 Preparation)\n\n")
        f.write("1. **Create link update script:**\n")
        f.write("   - Update all incoming references (TO ADRs)\n")
        f.write("   - Update all outgoing references (FROM ADRs)\n\n")
        f.write("2. **Test on pilot ADR family:**\n")
        f.write(f"   - Move {target_adrs[0]}*.md files to new structure\n")
        f.write("   - Run link update script\n")
        f.write("   - Validate all links resolve\n\n")
        f.write("3. **Generate dry-run report:**\n")
        f.write("   - Show what would change without modifying files\n\n")
        f.write("4. **Proceed with migration:**\n")
        f.write(f"   - Apply to remaining ADR families\n\n")

    print(f"\n✅ Report generated: {report_path}")
    return report_path


def main():
    args = parse_args()
    target_adrs = args.adrs

    print("=" * 70)
    print(f"  PHASE 3: LINK AUDIT (Scoped to ADRs {', '.join(target_adrs)})")
    print("=" * 70)

    # Step 1: Find references TO target ADRs
    refs_to = find_references_to_adrs(target_adrs)
    total_to = sum(len(refs) for refs in refs_to.values())
    print(f"✅ Found {total_to} references TO target ADRs")

    # Step 2: Find references FROM target ADRs
    refs_from = find_references_from_adrs(target_adrs)
    total_from = sum(len(refs) for refs in refs_from.values())
    print(f"✅ Found {total_from} references FROM target ADRs")

    # Step 3: Find diagram references
    diagram_refs = find_diagram_references(target_adrs)
    total_diagrams = sum(len(refs) for refs in diagram_refs.values())
    print(f"✅ Found {total_diagrams} diagram references")

    # Step 4: Generate report
    report_path = generate_report(target_adrs, refs_to, refs_from, diagram_refs, args.output)

    # Step 5: Save JSON data for automation
    first_adr = min(target_adrs)
    last_adr = max(target_adrs)
    json_path = WORKSPACE_ROOT / f"adr_references_{first_adr}-{last_adr}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "target_adrs": target_adrs,
                "references_to": refs_to,
                "references_from": refs_from,
                "diagram_references": diagram_refs,
            },
            f,
            indent=2,
        )
    print(f"✅ JSON data saved: {json_path}")

    print("\n" + "=" * 70)
    print("  LINK AUDIT COMPLETE")
    print("=" * 70)
    print(f"\n📊 Summary:")
    print(f"   - References TO ADRs: {total_to}")
    print(f"   - References FROM ADRs: {total_from}")
    print(f"   - Diagram references: {total_diagrams}")
    print(f"\n📄 Full report: {report_path.name}")
    print(f"📄 JSON data: {report_path.name.replace('.md', '.json')}")
    print("\n🚀 Ready for Phase 4: File Migration")


if __name__ == "__main__":
    main()
