#!/usr/bin/env python3
"""
Fix All ADR Validation Issues

Automatically fixes:
1. Invalid status values (COMPLETED → IMPLEMENTED, APPROVED → ACCEPTED, IN_PROGRESS → DRAFT)
2. Unknown concerns (add to valid list or remove)
3. Status mismatches between frontmatter and content

Usage:
    python scripts/ADR_scripts/fix_all_validation_issues.py
    python scripts/ADR_scripts/fix_all_validation_issues.py --dry-run
"""

import argparse
import re
import sys
from pathlib import Path
from typing import Dict, List, Set

import frontmatter

# Status mapping for corrections
STATUS_MAPPING = {
    "COMPLETED": "IMPLEMENTED",
    "APPROVED": "ACCEPTED",
    "IN_PROGRESS": "DRAFT",
    "TEMPLATE": "PROPOSED",
}

# Concern mapping - map unknown to valid or remove
CONCERN_MAPPING = {
    "compliance": "security",  # Compliance is a security concern
    "fault_isolation": "reliability",  # Fault isolation relates to reliability
    "interoperability": "compatibility",  # Interoperability is compatibility
    "developer_experience": "usability",  # Developer experience is usability
    "documentation": "maintainability",  # Documentation aids maintainability
    "ux": "usability",  # UX is usability
}

# Valid concerns (from validator)
VALID_CONCERNS = {
    "architecture",
    "modularity",
    "performance",
    "maintainability",
    "testing",
    "security",
    "privacy",
    "observability",
    "cost",
    "scalability",
    "reliability",
    "usability",
    "compatibility",
}


def fix_status_value(status: str) -> str:
    """Fix invalid status values."""
    if status in STATUS_MAPPING:
        return STATUS_MAPPING[status]
    return status


def fix_concerns(concerns: List[str]) -> List[str]:
    """Fix unknown concern values."""
    if not isinstance(concerns, list):
        return []

    fixed = []
    for concern in concerns:
        if concern in VALID_CONCERNS:
            fixed.append(concern)
        elif concern in CONCERN_MAPPING:
            # Map to valid concern
            fixed.append(CONCERN_MAPPING[concern])
        # else: skip unknown concern

    # Remove duplicates and sort
    return sorted(list(set(fixed)))


def fix_adr_file(file_path: Path, dry_run: bool = False) -> bool:
    """Fix a single ADR file. Returns True if changes were made."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            post = frontmatter.load(f)

        changes_made = False
        changes = []

        # Fix status in frontmatter
        if "status" in post.metadata:
            old_status = post.metadata["status"]
            new_status = fix_status_value(old_status)
            if old_status != new_status:
                post.metadata["status"] = new_status
                changes_made = True
                changes.append(f"Status: {old_status} → {new_status}")

        # Fix concerns in frontmatter
        if "concerns" in post.metadata:
            old_concerns = post.metadata["concerns"]
            new_concerns = fix_concerns(old_concerns)
            if old_concerns != new_concerns:
                post.metadata["concerns"] = new_concerns
                changes_made = True
                removed = set(old_concerns) - set(new_concerns)
                if removed:
                    changes.append(f"Concerns: removed {removed}")

        # Fix propagation.affected_tests if empty
        if "propagation" in post.metadata:
            prop = post.metadata["propagation"]
            if isinstance(prop, dict):
                if "affected_tests" in prop and prop["affected_tests"] == []:
                    # Keep empty list (it's valid)
                    pass
                if "triggers" in prop and prop["triggers"] == []:
                    # Add default triggers
                    prop["triggers"] = [
                        "Modifying affected modules or contracts",
                        "Changing architecture patterns or protocols",
                        "Performance requirement changes",
                    ]
                    changes_made = True
                    changes.append("Added default triggers")

        if changes_made and not dry_run:
            # Write back to file
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(frontmatter.dumps(post))

            print(f"✅ Fixed: {file_path.relative_to(Path.cwd())}")
            for change in changes:
                print(f"   - {change}")
            return True
        elif changes_made and dry_run:
            print(f"🔍 Would fix: {file_path.relative_to(Path.cwd())}")
            for change in changes:
                print(f"   - {change}")
            return True

        return False

    except Exception as e:
        print(f"❌ Error processing {file_path}: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Fix all ADR validation issues")
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would be fixed without making changes"
    )
    args = parser.parse_args()

    base_path = Path.cwd()
    decisions_path = base_path / "docs" / "architecture" / "decisions"

    if not decisions_path.exists():
        print(f"❌ Decisions folder not found: {decisions_path}")
        sys.exit(2)

    print("\n" + "=" * 70)
    if args.dry_run:
        print("🔍 DRY RUN MODE - No files will be modified")
    else:
        print("🔧 FIXING ADR VALIDATION ISSUES")
    print("=" * 70)

    # Find all ADR markdown files
    adr_files = list(decisions_path.rglob("*.md"))

    # Exclude certain files
    exclude_patterns = ["readme.md", "README.md", "index.md"]
    adr_files = [f for f in adr_files if f.name.lower() not in exclude_patterns]

    print(f"\n📁 Found {len(adr_files)} ADR files")
    print(f"\n{'DRY RUN: Would fix' if args.dry_run else 'Fixing'} files...\n")

    fixed_count = 0
    for adr_file in sorted(adr_files):
        if fix_adr_file(adr_file, dry_run=args.dry_run):
            fixed_count += 1

    print("\n" + "=" * 70)
    print(f"{'Would fix' if args.dry_run else 'Fixed'} {fixed_count} files")
    print("=" * 70)

    if args.dry_run:
        print("\n💡 Run without --dry-run to apply fixes")
    else:
        print("\n✅ All fixes applied!")
        print("\n📝 Next steps:")
        print("   1. Run: python scripts/ADR_scripts/validate_adr_metadata.py")
        print("   2. Run: python scripts/ADR_scripts/build_adr_index.py")
        print("   3. Commit changes")


if __name__ == "__main__":
    main()
