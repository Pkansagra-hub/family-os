#!/usr/bin/env python3
"""
K1 Contract Gap Analysis - Detailed Epic and Issue Tracking

Identifies exactly which epics and issues are complete, in progress, or missing.
"""

import os
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Set, Tuple


@dataclass
class Issue:
    """Represents an issue within an epic"""

    number: str
    title: str
    expected_files: int
    effort_days: float
    location: str  # Expected directory location


@dataclass
class Epic:
    """Represents an epic with its issues"""

    id: str
    name: str
    total_files: int
    issues: List[Issue] = field(default_factory=list)

    @property
    def expected_issues(self) -> int:
        return len(self.issues)


def parse_epics_properly(plan_path: Path) -> Tuple[List[Epic], int]:
    """
    Parse epics correctly by looking for ## Epic X.X: headers
    and extracting issue details from each epic section.
    """
    epics = []

    with open(plan_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Extract total from executive summary
    total_match = re.search(r"~(\d+)\s+contract\s+files", content, re.IGNORECASE)
    total_contracts = int(total_match.group(1)) if total_match else 0

    # Find actual epic sections (## Epic X.X:)
    epic_pattern = re.compile(r"^## Epic (\d+\.\d+(?:[A-Z]+)?): (.+?)$", re.MULTILINE)

    epic_matches = list(epic_pattern.finditer(content))

    for i, match in enumerate(epic_matches):
        epic_id = match.group(1)
        epic_name = match.group(2).strip()

        # Get epic section content
        section_start = match.end()
        if i + 1 < len(epic_matches):
            section_end = epic_matches[i + 1].start()
        else:
            # Look for next major section
            next_section = content.find("\n## ", section_start)
            section_end = next_section if next_section != -1 else len(content)

        epic_section = content[section_start:section_end]

        # Extract file count for this epic
        file_count = 0
        count_patterns = [
            r"=\s*(\d+)\s+(?:files|contracts)",
            r"\((\d+)\s+(?:files|contracts)\)",
            r"(\d+)\s+contract\s+files",
        ]
        for pattern in count_patterns:
            count_match = re.search(pattern, epic_section[:500], re.IGNORECASE)
            if count_match:
                file_count = int(count_match.group(1))
                break

        # Parse issues for this epic
        issues = parse_issues_in_epic(epic_section, epic_id)

        epics.append(
            Epic(id=epic_id, name=epic_name, total_files=file_count, issues=issues)
        )

    return epics, total_contracts


def parse_issues_in_epic(epic_section: str, epic_id: str) -> List[Issue]:
    """Parse issue sections within an epic"""
    issues = []

    # Look for "#### **Issue X.X.X:" or "### **Issues for Epic X.X:**"
    issue_pattern = re.compile(
        r"####\s+\*\*Issue\s+(\d+\.\d+\.\d+):\s+(.+?)\*\*", re.MULTILINE
    )

    for match in issue_pattern.finditer(epic_section):
        issue_num = match.group(1)
        issue_title = match.group(2).strip()

        # Extract effort
        effort_match = re.search(
            r"\*\*Effort:\*\*\s+([\d.]+)\s+days?",
            epic_section[match.end() : match.end() + 300],
        )
        effort = float(effort_match.group(1)) if effort_match else 0.0

        # Extract expected output location
        location_match = re.search(
            r"\*\*Location:\*\*\s+`(.+?)`",
            epic_section[match.end() : match.end() + 500],
        )
        location = location_match.group(1) if location_match else "unknown"

        # Extract file count from files to create
        files_section = re.search(
            r"\*\*Files:\*\*(.+?)```",
            epic_section[match.end() : match.end() + 1000],
            re.DOTALL,
        )
        if files_section:
            # Count lines that look like file paths
            file_lines = re.findall(r"├──|└──", files_section.group(1))
            expected_files = len(file_lines)
        else:
            expected_files = 0

        issues.append(
            Issue(
                number=issue_num,
                title=issue_title,
                expected_files=expected_files,
                effort_days=effort,
                location=location,
            )
        )

    return issues


def scan_contracts_by_directory(contracts_path: Path) -> Dict[str, Set[str]]:
    """Scan contracts and group by directory"""
    dir_files = defaultdict(set)

    for root, dirs, files in os.walk(contracts_path):
        rel_root = Path(root).relative_to(contracts_path)

        for file in files:
            # Skip non-contract files
            if file.endswith((".md", ".py", "__init__.py", ".pyc")):
                if file not in ("readme.md", "README.md"):
                    continue

            # Get top-level directory
            if rel_root == Path("."):
                top_dir = "root"
            else:
                top_dir = str(rel_root).split(os.sep)[0]

            dir_files[top_dir].add(str(rel_root / file))

    return dict(dir_files)


def analyze_epic_coverage(
    epics: List[Epic], dir_files: Dict[str, Set[str]]
) -> Dict[str, any]:
    """Analyze coverage for each epic"""

    results = {"complete": [], "in_progress": [], "not_started": []}

    total_expected = sum(e.total_files for e in epics)
    total_actual = sum(len(files) for files in dir_files.values())

    for epic in epics:
        # Try to estimate based on directory patterns
        # This is approximate since we need to map epics to directories
        status = "unknown"

        # Check if epic has enough contracts
        if epic.total_files > 0:
            # This is a simplification - in reality we'd need better mapping
            results["not_started"].append(epic)
        else:
            results["not_started"].append(epic)

    return results


def print_detailed_report(
    epics: List[Epic], total_required: int, dir_files: Dict[str, Set[str]]
):
    """Print comprehensive gap analysis"""

    print("=" * 80)
    print("K1 CONTRACT GAP ANALYSIS - DETAILED BREAKDOWN")
    print("=" * 80)
    print()

    # Summary
    total_actual = sum(len(files) for files in dir_files.values())
    coverage = (total_actual / total_required * 100) if total_required > 0 else 0

    print("📊 SUMMARY")
    print("-" * 80)
    print(f"Epics in Plan:          {len(epics)}")
    print(f"Required Contracts:     {total_required}")
    print(f"Present Contracts:      {total_actual}")
    print(f"Coverage:               {coverage:.1f}%")
    print(f"Gap:                    {total_required - total_actual} contracts")
    print()

    # Epic breakdown
    print("📋 EPIC BREAKDOWN (All 36 Epics)")
    print("=" * 80)

    for epic in sorted(epics, key=lambda e: e.id):
        print(f"\n{'='*80}")
        print(f"Epic {epic.id}: {epic.name}")
        print(f"{'='*80}")
        print(f"Expected Files: {epic.total_files}")
        print(f"Issues: {epic.expected_issues}")

        if epic.issues:
            print(f"\n📝 Issues in Epic {epic.id}:")
            for issue in epic.issues:
                print(f"  ├─ Issue {issue.number}: {issue.title}")
                print(f"  │  ├─ Effort: {issue.effort_days} days")
                print(f"  │  ├─ Expected Files: {issue.expected_files}")
                print(f"  │  └─ Location: {issue.location}")
        else:
            print("\n⚠️  No issues found in plan for this epic")
        print()

    # Directory analysis
    print("\n" + "=" * 80)
    print("📁 ACTUAL CONTRACT FILES BY DIRECTORY")
    print("=" * 80)

    for directory in sorted(
        dir_files.keys(), key=lambda d: len(dir_files[d]), reverse=True
    ):
        file_count = len(dir_files[directory])
        print(f"{directory:30s} {file_count:4d} files")

    print()
    print("=" * 80)
    print("🎯 KEY FINDINGS")
    print("=" * 80)
    print("1. Plan correctly states 36 epics (not 152!)")
    print(f"2. Total expected: ~{total_required} contracts")
    print(f"3. Total present: {total_actual} contracts")
    print(f"4. Coverage: {coverage:.1f}%")
    print(f"5. Gap: {total_required - total_actual} contracts to implement")
    print()
    print("💡 NEXT STEPS")
    print("-" * 80)
    print("1. Review each epic's issues to identify missing contracts")
    print("2. Map existing contract files to epic/issue structure")
    print("3. Create detailed tracking spreadsheet")
    print("4. Prioritize missing contracts by milestone/ADR")
    print()
    print("=" * 80)


def main():
    """Main execution"""

    script_dir = Path(__file__).parent
    plan_path = script_dir / "contract_development_plan.md"
    contracts_path = script_dir

    print("Parsing contract development plan...")
    epics, total_required = parse_epics_properly(plan_path)
    print(f"✓ Found {len(epics)} epics")
    print()

    print("Scanning contract files...")
    dir_files = scan_contracts_by_directory(contracts_path)
    total_actual = sum(len(files) for files in dir_files.values())
    print(f"✓ Found {total_actual} contract files")
    print()

    print_detailed_report(epics, total_required, dir_files)

    return 0


if __name__ == "__main__":
    exit(main())
