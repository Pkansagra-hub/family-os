#!/usr/bin/env python3
"""
Check Missing ADRs Script

Compares ADR numbers mentioned in adr_family_map.md with actual ADR files
in the decisions folder to identify missing ADRs.

Usage:
    python scripts/check_missing_adrs.py
"""

import re
from pathlib import Path
from typing import List, Set, Tuple


def extract_adr_numbers_from_family_map(family_map_path: Path) -> Set[str]:
    """
    Extract all ADR numbers mentioned in the family map.

    Looks for patterns like:
    - ADR-0001
    - ADR-0001a
    - ADR-0001b
    - [ADR-0001](../decisions/0001-...)

    Returns:
        Set of ADR numbers (e.g., {'0001', '0001a', '0002', ...})
    """
    adr_numbers = set()

    # Pattern to match ADR references
    # Matches: ADR-0001, ADR-0001a, ADR-0001b, etc.
    pattern = r"ADR-(\d{4}[a-z]?)"

    with open(family_map_path, "r", encoding="utf-8") as f:
        content = f.read()

        # Find all ADR references
        matches = re.findall(pattern, content, re.IGNORECASE)

        for match in matches:
            adr_numbers.add(match)

    return adr_numbers


def extract_adr_files_from_decisions(decisions_path: Path) -> Set[str]:
    """
    Extract all ADR files from the decisions folder.

    Looks for files matching pattern: 0001-*.md, 0001a-*.md, etc.

    Returns:
        Set of ADR numbers (e.g., {'0001', '0001a', '0002', ...})
    """
    adr_numbers = set()

    # Pattern to match ADR files
    # Matches: 0001-description.md, 0001a-description.md, etc.
    pattern = r"^(\d{4}[a-z]?)-.*\.md$"

    if not decisions_path.exists():
        print(f"Warning: Decisions folder not found at {decisions_path}")
        return adr_numbers

    for file in decisions_path.iterdir():
        if file.is_file():
            match = re.match(pattern, file.name)
            if match:
                adr_numbers.add(match.group(1))

    return adr_numbers


def find_missing_adrs(
    family_map_adrs: Set[str], decision_adrs: Set[str]
) -> Tuple[List[str], List[str]]:
    """
    Find ADRs that are missing from either the family map or decisions folder.

    Args:
        family_map_adrs: ADR numbers from family map
        decision_adrs: ADR numbers from decisions folder

    Returns:
        Tuple of (missing_from_map, missing_from_decisions)
    """
    # ADRs in family map but not in decisions folder
    missing_from_decisions = sorted(family_map_adrs - decision_adrs)

    # ADRs in decisions folder but not in family map
    missing_from_map = sorted(decision_adrs - family_map_adrs)

    return missing_from_map, missing_from_decisions


def format_adr_list(adr_numbers: List[str]) -> str:
    """
    Format ADR list for display.

    Groups ADRs by main number (e.g., 0001, 0001a, 0001b together)

    Args:
        adr_numbers: List of ADR numbers

    Returns:
        Formatted string
    """
    if not adr_numbers:
        return "    None"

    # Group ADRs by main number
    groups = {}
    for adr in adr_numbers:
        # Extract main number (e.g., '0001' from '0001a')
        main_num = adr[:4]
        if main_num not in groups:
            groups[main_num] = []
        groups[main_num].append(adr)

    # Format output
    lines = []
    for main_num in sorted(groups.keys()):
        sub_adrs = sorted(groups[main_num])
        if len(sub_adrs) == 1:
            lines.append(f"    ADR-{sub_adrs[0]}")
        else:
            # Group main + sub-ADRs on one line
            adr_list = ", ".join([f"ADR-{adr}" for adr in sub_adrs])
            lines.append(f"    {adr_list}")

    return "\n".join(lines)


def main():
    """Main function to check missing ADRs."""

    # Determine paths
    script_dir = Path(__file__).parent
    repo_root = script_dir.parent

    family_map_path = (
        repo_root / "docs" / "architecture" / "tables" / "adr_family_map.md"
    )
    decisions_path = repo_root / "docs" / "architecture" / "decisions"

    print("=" * 80)
    print("ADR COVERAGE ANALYSIS")
    print("=" * 80)
    print()

    # Check if family map exists
    if not family_map_path.exists():
        print(f"Error: Family map not found at {family_map_path}")
        return 1

    # Extract ADR numbers
    print("📖 Reading ADR family map...")
    family_map_adrs = extract_adr_numbers_from_family_map(family_map_path)
    print(f"   Found {len(family_map_adrs)} ADRs referenced in family map")
    print()

    print("📁 Scanning decisions folder...")
    decision_adrs = extract_adr_files_from_decisions(decisions_path)
    print(f"   Found {len(decision_adrs)} ADR files in decisions folder")
    print()

    # Find missing ADRs
    missing_from_map, missing_from_decisions = find_missing_adrs(
        family_map_adrs, decision_adrs
    )

    # Display results
    print("-" * 80)
    print("ANALYSIS RESULTS")
    print("-" * 80)
    print()

    # ADRs in decisions but not in family map (need to be added to map)
    print(
        f"🔍 ADRs in decisions folder but NOT in family map ({len(missing_from_map)}):"
    )
    print(format_adr_list(missing_from_map))
    print()

    if missing_from_map:
        print("   ⚠️  These ADRs should be added to the family map!")
        print()

    # ADRs in family map but not in decisions (broken references)
    print(
        f"⚠️  ADRs referenced in family map but NOT in decisions folder ({len(missing_from_decisions)}):"
    )
    print(format_adr_list(missing_from_decisions))
    print()

    if missing_from_decisions:
        print("   ❌ These are broken references - ADR files are missing!")
        print()

    # Coverage statistics
    print("-" * 80)
    print("COVERAGE STATISTICS")
    print("-" * 80)
    print()

    total_adrs = len(family_map_adrs | decision_adrs)
    mapped_adrs = len(family_map_adrs & decision_adrs)
    coverage_pct = (mapped_adrs / total_adrs * 100) if total_adrs > 0 else 0

    print(f"Total unique ADRs:          {total_adrs}")
    print(f"ADRs with files AND map:    {mapped_adrs}")
    print(f"ADRs missing from map:      {len(missing_from_map)}")
    print(f"ADRs with broken refs:      {len(missing_from_decisions)}")
    print(f"Coverage:                   {coverage_pct:.1f}%")
    print()

    # Summary
    print("=" * 80)
    if not missing_from_map and not missing_from_decisions:
        print("✅ SUCCESS: All ADRs are properly documented!")
    elif missing_from_map and not missing_from_decisions:
        print(
            f"⚠️  ACTION NEEDED: {len(missing_from_map)} ADR(s) need to be added to family map"
        )
    elif missing_from_decisions and not missing_from_map:
        print(
            f"❌ ERROR: {len(missing_from_decisions)} broken ADR reference(s) in family map"
        )
    else:
        print("⚠️  ISSUES FOUND:")
        print(f"   - {len(missing_from_map)} ADR(s) need to be added to family map")
        print(f"   - {len(missing_from_decisions)} broken ADR reference(s)")
    print("=" * 80)

    return 0 if not missing_from_decisions else 1


if __name__ == "__main__":
    exit(main())
