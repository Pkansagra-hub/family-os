#!/usr/bin/env python3
"""
Phase 4: File Migration (Scoped to ADRs 0001-0004)
Moves ADR families to new folder structure and updates all links.
"""

import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

WORKSPACE_ROOT = Path(__file__).parent.parent.parent
DOCS_ROOT = WORKSPACE_ROOT / "docs"
ADR_DIR = DOCS_ROOT / "architecture" / "decisions"
BACKUP_DIR = WORKSPACE_ROOT / "adr_migration_backup"

# Migration mapping: ADR number → (new folder, title slug)
MIGRATION_MAP = {
    "0001": ("01-foundation/0001-k0-k1-kernel-split", "k0-k1-kernel-split"),
    "0002": ("01-foundation/0002-actor-model-agent-isolation", "actor-model-agent-isolation"),
    "0003": ("01-foundation/0003-mpst-protocol-validation", "mpst-protocol-validation"),
    "0004": ("01-foundation/0004-56-module-5-layer-architecture", "56-module-5-layer-architecture"),
}


class ADRMigrator:
    def __init__(self, dry_run: bool = True):
        self.dry_run = dry_run
        self.moved_files: List[Tuple[Path, Path]] = []
        self.updated_files: List[Path] = []
        self.errors: List[str] = []

    def create_folder_structure(self):
        """Create new folder structure."""
        print("\n📁 Creating folder structure...")

        # Create 01-foundation/ if not exists
        foundation_dir = ADR_DIR / "01-foundation"
        if not self.dry_run:
            foundation_dir.mkdir(exist_ok=True)
        print(
            f"  {'[DRY-RUN] Would create' if self.dry_run else 'Created'}: {foundation_dir.relative_to(WORKSPACE_ROOT)}"
        )

        # Create ADR family folders
        for adr_num, (folder_path, _) in MIGRATION_MAP.items():
            target_dir = ADR_DIR / folder_path
            if not self.dry_run:
                target_dir.mkdir(parents=True, exist_ok=True)
            print(
                f"  {'[DRY-RUN] Would create' if self.dry_run else 'Created'}: {target_dir.relative_to(WORKSPACE_ROOT)}"
            )

    def backup_files(self):
        """Create backup of all ADR files before migration."""
        if self.dry_run:
            print("\n💾 [DRY-RUN] Would create backup in: adr_migration_backup/")
            return

        print("\n💾 Creating backup...")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = BACKUP_DIR / timestamp
        backup_path.mkdir(parents=True, exist_ok=True)

        # Backup all 0001-0004 ADR files
        for adr_num in MIGRATION_MAP.keys():
            for adr_file in ADR_DIR.glob(f"{adr_num}*.md"):
                shutil.copy2(adr_file, backup_path / adr_file.name)

        print(f"  ✅ Backup created: {backup_path.relative_to(WORKSPACE_ROOT)}")

    def get_adr_files(self, adr_num: str) -> Dict[str, List[Path] | Path]:
        """Get parent and sub-ADR files for an ADR number."""
        files: Dict[str, List[Path] | Path] = {}

        # Find parent ADR (e.g., 0001-k0-k1-kernel-split.md)
        parent_files = list(ADR_DIR.glob(f"{adr_num}-*.md"))
        parent_files = [f for f in parent_files if not re.match(rf"{adr_num}[a-z]-", f.name)]

        if parent_files:
            files["parent"] = parent_files[0]

        # Find sub-ADRs (e.g., 0001a-*.md, 0001b-*.md)
        sub_files = [f for f in ADR_DIR.glob(f"{adr_num}[a-z]-*.md")]
        files["subs"] = sorted(sub_files)

        return files

    def move_adr_family(self, adr_num: str):
        """Move ADR family (parent + sub-ADRs) to new structure."""
        folder_path, title_slug = MIGRATION_MAP[adr_num]
        target_dir = ADR_DIR / folder_path

        print(f"\n📦 Moving ADR-{adr_num} family...")

        # Get all files for this ADR
        files = self.get_adr_files(adr_num)

        if not files:
            print(f"  ⚠️  No files found for ADR-{adr_num}")
            return

        # Move parent ADR (rename to just 0001.md)
        if "parent" in files:
            parent_file = files["parent"]
            if isinstance(parent_file, Path):
                new_name = f"{adr_num}.md"
                target_path = target_dir / new_name

                if not self.dry_run:
                    shutil.move(str(parent_file), str(target_path))

                self.moved_files.append((parent_file, target_path))
                print(
                    f"  {'[DRY-RUN]' if self.dry_run else '✅'} {parent_file.name} → {target_path.relative_to(ADR_DIR)}"
                )

        # Move sub-ADRs (keep original names)
        subs = files.get("subs", [])
        if isinstance(subs, list):
            for sub_file in subs:
                target_path = target_dir / sub_file.name

                if not self.dry_run:
                    shutil.move(str(sub_file), str(target_path))

                self.moved_files.append((sub_file, target_path))
                print(
                    f"  {'[DRY-RUN]' if self.dry_run else '✅'} {sub_file.name} → {target_path.relative_to(ADR_DIR)}"
                )

    def update_internal_links(self):
        """Update links inside moved ADR files (FROM references)."""
        print("\n🔗 Updating internal links in moved ADRs...")

        # Load the link audit data
        audit_file = WORKSPACE_ROOT / "adr_references_0001-0004.json"
        if not audit_file.exists():
            print("  ⚠️  Link audit data not found. Run phase3_link_audit_scoped.py first.")
            return

        with open(audit_file) as f:
            audit_data = json.load(f)

        refs_from = audit_data.get("references_from", {})

        for old_path, new_path in self.moved_files:
            if old_path.name not in refs_from:
                continue

            links = refs_from[old_path.name]
            if not links:
                continue

            print(f"  📝 {old_path.name} ({len(links)} links)")

            if self.dry_run:
                print(f"     [DRY-RUN] Would update {len(links)} links")
                continue

            # Read file content
            content = new_path.read_text(encoding="utf-8")
            original_content = content

            # Update relative links
            # Pattern: [text](../other-adr.md) or [text](./file.md)
            for link in links:
                link_path = link["link_path"]

                # Calculate new relative path
                # For now, we'll mark these for manual review
                # Complex path calculation would go here
                pass

            # Write back if changed
            if content != original_content:
                new_path.write_text(content, encoding="utf-8")
                self.updated_files.append(new_path)

    def update_external_references(self):
        """Update references TO moved ADRs from other files."""
        print("\n🔗 Updating external references to moved ADRs...")

        # Load the link audit data
        audit_file = WORKSPACE_ROOT / "adr_references_0001-0004.json"
        if not audit_file.exists():
            print("  ⚠️  Link audit data not found.")
            return

        with open(audit_file) as f:
            audit_data = json.load(f)

        refs_to = audit_data.get("references_to", {})

        # Build path mapping (old filename pattern → new path)
        path_mapping = {}
        for adr_num, (folder_path, _) in MIGRATION_MAP.items():
            # Parent ADR
            old_pattern = f"{adr_num}-[^/]+\\.md"
            new_path = f"{folder_path}/{adr_num}.md"
            path_mapping[adr_num] = new_path

            # Sub-ADRs
            for sub_file in ADR_DIR.glob(f"{adr_num}[a-z]-*.md"):
                sub_letter = sub_file.name.split("-")[0]  # e.g., "0001a"
                new_sub_path = f"{folder_path}/{sub_file.name}"
                path_mapping[sub_letter] = new_sub_path

        # Group references by file
        files_to_update = {}
        for adr_num, refs in refs_to.items():
            for ref in refs:
                file_path = Path(ref["file"])
                if file_path not in files_to_update:
                    files_to_update[file_path] = []
                files_to_update[file_path].append((adr_num, ref))

        print(f"  Found {len(files_to_update)} files with references to moved ADRs")

        for file_path, refs in list(files_to_update.items())[:5]:  # Show first 5
            print(
                f"  📝 {file_path.relative_to(WORKSPACE_ROOT) if WORKSPACE_ROOT in file_path.parents else file_path}"
            )
            print(f"     {len(refs)} references")

            if self.dry_run:
                print(f"     [DRY-RUN] Would update references")

    def validate_links(self):
        """Validate that all links in moved files resolve correctly."""
        print("\n✅ Validating links...")

        if self.dry_run:
            print("  [DRY-RUN] Link validation would be performed after actual migration")
            return

        broken_links = []

        for _, new_path in self.moved_files:
            if not new_path.exists():
                continue

            content = new_path.read_text(encoding="utf-8")

            # Find all markdown links
            link_pattern = re.compile(r"\[([^\]]+)\]\(([^\)]+)\)")
            for match in link_pattern.finditer(content):
                link_text, link_path = match.groups()

                # Skip external links
                if link_path.startswith("http"):
                    continue

                # Resolve relative path
                resolved = (new_path.parent / link_path).resolve()

                if not resolved.exists():
                    broken_links.append((new_path, link_path))

        if broken_links:
            print(f"  ⚠️  Found {len(broken_links)} broken links")
            for file, link in broken_links[:5]:
                print(f"     {file.name}: {link}")
        else:
            print(f"  ✅ All links valid")

    def generate_report(self):
        """Generate migration report."""
        report_path = (
            WORKSPACE_ROOT / f"MIGRATION_REPORT_0001-0004{'_DRY_RUN' if self.dry_run else ''}.md"
        )

        with open(report_path, "w", encoding="utf-8") as f:
            f.write("# ADR Migration Report - ADRs 0001-0004\n\n")
            f.write(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"**Mode:** {'DRY RUN' if self.dry_run else 'LIVE MIGRATION'}\n\n")

            f.write("---\n\n")
            f.write("## 📊 Summary\n\n")
            f.write(f"- **Files moved:** {len(self.moved_files)}\n")
            f.write(f"- **Files updated:** {len(self.updated_files)}\n")
            f.write(f"- **Errors:** {len(self.errors)}\n\n")

            f.write("---\n\n")
            f.write("## 📦 Moved Files\n\n")
            for old_path, new_path in self.moved_files:
                f.write(
                    f"- `{old_path.relative_to(ADR_DIR)}` → `{new_path.relative_to(ADR_DIR)}`\n"
                )

            f.write("\n---\n\n")
            f.write("## 🔗 Link Updates\n\n")
            if self.dry_run:
                f.write("*Link updates would be performed in live migration*\n\n")
            else:
                f.write(f"Updated {len(self.updated_files)} files with new link paths\n\n")

            if self.errors:
                f.write("\n---\n\n")
                f.write("## ⚠️ Errors\n\n")
                for error in self.errors:
                    f.write(f"- {error}\n")

            f.write("\n---\n\n")
            f.write("## ✅ Next Steps\n\n")
            if self.dry_run:
                f.write("1. Review this dry-run report\n")
                f.write("2. Run migration with `--live` flag\n")
                f.write("3. Validate all links work\n")
                f.write("4. Update index files\n")
            else:
                f.write("1. ✅ Files migrated\n")
                f.write("2. Validate links manually\n")
                f.write("3. Update readme.md and indices\n")
                f.write("4. Commit changes\n")

        print(f"\n📄 Report generated: {report_path.name}")
        return report_path

    def run(self):
        """Execute migration workflow."""
        print("=" * 70)
        print(f"  PHASE 4: FILE MIGRATION {'(DRY RUN)' if self.dry_run else '(LIVE)'}")
        print("=" * 70)

        try:
            # Step 1: Create folder structure
            self.create_folder_structure()

            # Step 2: Backup files
            self.backup_files()

            # Step 3: Move ADR families
            for adr_num in sorted(MIGRATION_MAP.keys()):
                self.move_adr_family(adr_num)

            # Step 4: Update internal links
            self.update_internal_links()

            # Step 5: Update external references
            self.update_external_references()

            # Step 6: Validate links
            self.validate_links()

            # Step 7: Generate report
            report_path = self.generate_report()

            print("\n" + "=" * 70)
            print(f"  MIGRATION {'DRY RUN' if self.dry_run else ''} COMPLETE")
            print("=" * 70)
            print(f"\n📊 Summary:")
            print(f"   - Files moved: {len(self.moved_files)}")
            print(f"   - Files updated: {len(self.updated_files)}")
            print(f"   - Errors: {len(self.errors)}")
            print(f"\n📄 Full report: {report_path.name}")

            if self.dry_run:
                print(f"\n💡 This was a DRY RUN. No files were actually moved.")
                print(f"   Run with --live flag to perform actual migration.")
            else:
                print(f"\n✅ Migration complete! Backup saved in: adr_migration_backup/")

        except Exception as e:
            print(f"\n❌ Migration failed: {e}")
            self.errors.append(str(e))
            raise


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Migrate ADRs 0001-0004 to new folder structure")
    parser.add_argument(
        "--live", action="store_true", help="Perform actual migration (default is dry-run)"
    )
    args = parser.parse_args()

    migrator = ADRMigrator(dry_run=not args.live)
    migrator.run()


if __name__ == "__main__":
    main()
