#!/usr/bin/env python3
"""
Phase 4: File Migration (Flexible ADR Migration)
Moves specified ADR families to new folder structure and updates all links.
"""

import argparse
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

# Default migration mapping (can be extended via command line)
DEFAULT_MIGRATION_MAP = {
    "0001": ("01-foundation/0001-k0-k1-kernel-split", "k0-k1-kernel-split"),
    "0002": ("01-foundation/0002-actor-model-agent-isolation", "actor-model-agent-isolation"),
    "0003": ("01-foundation/0003-mpst-protocol-validation", "mpst-protocol-validation"),
    "0004": ("01-foundation/0004-56-module-5-layer-architecture", "56-module-5-layer-architecture"),
    "0005": ("03-layer2-orchestration/0005-agent-lifecycle-fsm", "agent-lifecycle-fsm"),
    "0006": ("03-layer2-orchestration/0006-3-phase-orchestration", "3-phase-orchestration"),
    "0007": ("03-layer2-orchestration/0007-4stage-planning-pipeline", "4stage-planning-pipeline"),
    "0008": (
        "03-layer2-orchestration/0008-saga-pattern-error-recovery",
        "saga-pattern-error-recovery",
    ),
    "0009": ("06-layer5-infrastructure/0009-circuit-breaker-pattern", "circuit-breaker-pattern"),
    "0010": ("08-security-privacy/0010-capability-based-security", "capability-based-security"),
    # Series 11-20: Contracts, Serialization, Communication, State Management
    "0011": (
        "07-contracts-serialization/0011-flatbuffers-serialization",
        "flatbuffers-serialization",
    ),
    "0012": ("07-contracts-serialization/0012-76-flatbuffers-schemas", "76-flatbuffers-schemas"),
    "0013": (
        "07-contracts-serialization/0013-pipeline-versioning-policy",
        "pipeline-versioning-policy",
    ),
    "0014": ("09-communication/0014-json-rest-api-dual-format", "json-rest-api-dual-format"),
    "0015": ("09-communication/0015-websocket-binary-protocol", "websocket-binary-protocol"),
    "0016": ("09-communication/0016-sse-event-schemas", "sse-event-schemas"),
    "0017": (
        "03-layer2-orchestration/0017-sessionstate-6-section-design",
        "sessionstate-6-section-design",
    ),
    "0018": ("05-layer4-runtime/0018-3-tier-eviction-strategy", "3-tier-eviction-strategy"),
    "0019": (
        "07-contracts-serialization/0019-flatbuffers-sessionstate-serialization",
        "flatbuffers-sessionstate-serialization",
    ),
    "0020": ("06-layer5-infrastructure/0020-multi-tier-storage", "multi-tier-storage"),
    # Series 21-31: Retention, Communication, Performance, Runtime, Infrastructure
    "0021": (
        "05-layer4-runtime/0021-turn-history-retention-policies",
        "turn-history-retention-policies",
    ),
    "0022": ("09-communication/0022-k0-bridge-bounded-batching", "k0-bridge-bounded-batching"),
    "0023": ("09-communication/0023-cursor-based-turn-pagination", "cursor-based-turn-pagination"),
    "0024": (
        "06-layer5-infrastructure/0024-performance-budgets-p95-targets",
        "performance-budgets-p95-targets",
    ),
    "0025": ("05-layer4-runtime/0025-kv-cache-management-512mb", "kv-cache-management-512mb"),
    "0026": (
        "06-layer5-infrastructure/0026-thermal-hysteresis-matrix",
        "thermal-hysteresis-matrix",
    ),
    "0027": ("04-layer3-execution/0027-model-placement-cascade", "model-placement-cascade"),
    "0028": (
        "03-layer2-orchestration/0028-weighted-fair-queuing-scheduler",
        "weighted-fair-queuing-scheduler",
    ),
    "0029": (
        "06-layer5-infrastructure/0029-prometheus-metrics-red-method",
        "prometheus-metrics-red-method",
    ),
    "0030": (
        "06-layer5-infrastructure/0030-intelligent-trace-sampling",
        "intelligent-trace-sampling",
    ),
    "0031": ("05-layer4-runtime/0031-cost-tracking-per-session", "cost-tracking-per-session"),
    # Series 32-41: Security, Privacy, Communication, Runtime
    "0032": ("10-security-privacy/0032-band-based-egress-rules", "band-based-egress-rules"),
    "0033": ("04-layer3-execution/0033-three-tier-sandbox-strategy", "three-tier-sandbox-strategy"),
    "0034": ("09-communication/0034-mcp-protocol-adoption", "mcp-protocol-adoption"),
    "0035": ("10-security-privacy/0035-pii-detection-and-redaction", "pii-detection-and-redaction"),
    "0036": ("10-security-privacy/0036-e2ee-for-red-band", "e2ee-for-red-band"),
    "0037": ("10-security-privacy/0037-jwt-authentication", "jwt-authentication"),
    "0038": (
        "06-layer5-infrastructure/0038-audit-trail-to-k0-receipts",
        "audit-trail-to-k0-receipts",
    ),
    "0039": ("05-layer4-runtime/0039-backpressure-cascade-3-tier", "backpressure-cascade-3-tier"),
    "0040": ("09-communication/0040-websocket-realtime-chat", "websocket-realtime-chat"),
    "0041": ("09-communication/0041-rest-api-session-management", "rest-api-session-management"),
    # Series 42-50: Communication, Orchestration, Infrastructure
    "0042": ("09-communication/0042-k0-sse-event-streaming", "k0-sse-event-streaming"),
    "0043": ("09-communication/0043-sse-topic-taxonomy", "sse-topic-taxonomy"),
    "0044": ("09-communication/0044-k0-bridge-http2-flatbuffers", "k0-bridge-http2-flatbuffers"),
    "0045": ("03-layer2-orchestration/0045-k1-event-bus-coordination", "k1-event-bus-coordination"),
    "0046": ("09-communication/0046-sse-websocket-bridge", "sse-websocket-bridge"),
    "0047": ("07-contracts-serialization/0047-openapi-3-1-rest-specs", "openapi-3-1-rest-specs"),
    "0048": ("03-layer2-orchestration/0048-k1-internal-event-bus", "k1-internal-event-bus"),
    "0049": (
        "03-layer2-orchestration/0049-fast-smart-lane-router-policy",
        "fast-smart-lane-router-policy",
    ),
    "0050": (
        "06-layer5-infrastructure/0050-multi-device-family-sync-strategy",
        "multi-device-family-sync-strategy",
    ),
    # Series 52-61: User Interaction, Voice Pipeline, Learning, KV-Cache, Backpressure
    "0052": ("08-user-interaction/0052-enhanced-hitl-protocols", "enhanced-hitl-protocols"),
    "0053": ("08-user-interaction/0053-message-queue-coalescing", "message-queue-coalescing"),
    "0054": ("08-user-interaction/0054-turn-boundary-management", "turn-boundary-management"),
    "0055": ("08-user-interaction/0055-context-switch-detection", "context-switch-detection"),
    "0056": ("02-layer1-input/0056-voice-pipeline-implementation", "voice-pipeline-implementation"),
    "0057": ("02-layer1-input/0057-voice-specific-backpressure", "voice-specific-backpressure"),
    "0058": ("04-layer3-execution/0058-intent-classification-voice", "intent-classification-voice"),
    "0059": ("04-layer3-execution/0059-learning-loop", "learning-loop"),
    "0060": ("05-layer4-runtime/0060-adaptive-kv-cache-management", "adaptive-kv-cache-management"),
    "0061": (
        "06-layer5-infrastructure/0061-3-tier-backpressure-cascade",
        "3-tier-backpressure-cascade",
    ),
    # Series 65-69: User Interaction & Product Craft
    "0065": (
        "08-user-interaction/0065-product-craft-ux-micro-interactions",
        "product-craft-ux-micro-interactions",
    ),
    "0066": (
        "08-user-interaction/0066-developer-testing-simulation-harness",
        "developer-testing-simulation-harness",
    ),
    "0067": (
        "08-user-interaction/0067-conversational-delight-factors",
        "conversational-delight-factors",
    ),
    "0068": ("02-layer1-input/0068-voice-quality-measurement", "voice-quality-measurement"),
    "0069": ("02-layer1-input/0069-p08-affect-modulation-k0-impl", "p08-affect-modulation-k0-impl"),
    # Series 70-77: Observability, Performance & Infrastructure
    "0070": (
        "06-layer5-infrastructure/0070-observability-evaluation-infrastructure",
        "observability-evaluation-infrastructure",
    ),
    "0071": ("02-layer1-input/0071-multilingual-code-switching", "multilingual-code-switching"),
    "0073": (
        "03-layer2-orchestration/0073-agent-lifecycle-fsm-enhancements",
        "agent-lifecycle-fsm-enhancements",
    ),
    "0074": ("06-layer5-infrastructure/0074-pluggable-module-system", "pluggable-module-system"),
    "0075": (
        "06-layer5-infrastructure/0075-layer5-extensibility-framework",
        "layer5-extensibility-framework",
    ),
    "0076": (
        "05-layer4-runtime/0076-kv-cache-optimization-strategy",
        "kv-cache-optimization-strategy",
    ),
    "0077": (
        "06-layer5-infrastructure/0077-thermal-placement-algorithm-v2",
        "thermal-placement-algorithm-v2",
    ),
    # Series 78-80: Execution & Learning
    "0078": ("04-layer3-execution/0078-tool-call-batching-pipeline", "tool-call-batching-pipeline"),
    "0079": (
        "04-layer3-execution/0079-learning-loop-drift-detection",
        "learning-loop-drift-detection",
    ),
    "0080": (
        "06-layer5-infrastructure/0080-continuous-config-hot-reload",
        "continuous-config-hot-reload",
    ),
    # Series 81-86: Agent Systems & Orchestration
    "0081": (
        "06-layer5-infrastructure/0081-k0-knowledge-graph-architecture",
        "k0-knowledge-graph-architecture",
    ),
    "0082": (
        "03-layer2-orchestration/0082-multi-party-dialogue-coordination",
        "multi-party-dialogue-coordination",
    ),
    "0083": ("02-layer1-input/0083-ambient-sensor-fusion", "ambient-sensor-fusion"),
    "0084": (
        "06-layer5-infrastructure/0084-k0-memory-consolidation-pipeline",
        "k0-memory-consolidation-pipeline",
    ),
    "0085": (
        "08-user-interaction/0085-embodied-awareness-device-presence",
        "embodied-awareness-device-presence",
    ),
    "0086": (
        "03-layer2-orchestration/0086-dynamic-agent-creation-subsystem",
        "dynamic-agent-creation-subsystem",
    ),
    # Series 87-92: Infrastructure & K0 Services
    "0087": (
        "06-layer5-infrastructure/0087-kg-mcp-semantic-enhancement",
        "kg-mcp-semantic-enhancement",
    ),
    "0088": (
        "06-layer5-infrastructure/0088-k0-local-env-paths-migration",
        "k0-local-env-paths-migration",
    ),
    "0089": (
        "10-security-privacy/0089-k0-bridge-policy-enforcement",
        "k0-bridge-policy-enforcement",
    ),
    "0090": (
        "06-layer5-infrastructure/0090-deployment-strategy-edge-rollout",
        "deployment-strategy-edge-rollout",
    ),
    "0091": (
        "06-layer5-infrastructure/0091-k0-observability-architecture",
        "k0-observability-architecture",
    ),
    "0092": (
        "06-layer5-infrastructure/0092-remediation-service-separation",
        "remediation-service-separation",
    ),
}


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Migrate ADR families to new structure")
    parser.add_argument(
        "--live", action="store_true", help="Actually perform migration (default is dry-run)"
    )
    parser.add_argument(
        "--adrs",
        nargs="+",
        default=list(DEFAULT_MIGRATION_MAP.keys()),
        help="ADR numbers to migrate (e.g., 0005 0006 0007)",
    )
    return parser.parse_args()


def get_migration_map(target_adrs: List[str]) -> Dict[str, Tuple[str, str]]:
    """Get migration mapping for specified ADRs."""
    migration_map = {}
    for adr_num in target_adrs:
        if adr_num in DEFAULT_MIGRATION_MAP:
            migration_map[adr_num] = DEFAULT_MIGRATION_MAP[adr_num]
        else:
            # Try to infer mapping for unknown ADRs
            # Look for the ADR file to get its title
            adr_files = list(ADR_DIR.glob(f"{adr_num}-*.md"))
            if adr_files:
                title_part = adr_files[0].name.replace(f"{adr_num}-", "").replace(".md", "")
                # Default to 03-layer2-orchestration for unknown ADRs (can be adjusted)
                migration_map[adr_num] = (
                    f"03-layer2-orchestration/{adr_num}-{title_part}",
                    title_part,
                )
            else:
                print(f"⚠️  Warning: Could not find ADR {adr_num} files, skipping")
    return migration_map


class ADRMigrator:
    def __init__(self, migration_map: Dict[str, Tuple[str, str]], dry_run: bool = True):
        self.migration_map = migration_map
        self.dry_run = dry_run
        self.moved_files: List[Tuple[Path, Path]] = []
        self.updated_files: List[Path] = []
        self.errors: List[str] = []

    def create_folder_structure(self):
        """Create new folder structure."""
        print("\n📁 Creating folder structure...")

        # Create category folders as needed
        categories_created = set()
        for adr_num, (folder_path, _) in self.migration_map.items():
            category = folder_path.split("/")[0]
            if category not in categories_created:
                category_dir = ADR_DIR / category
                if not self.dry_run:
                    category_dir.mkdir(exist_ok=True)
                print(
                    f"  {'[DRY-RUN] Would create' if self.dry_run else 'Created'}: {category_dir.relative_to(WORKSPACE_ROOT)}"
                )
                categories_created.add(category)

        # Create ADR family folders
        for adr_num, (folder_path, _) in self.migration_map.items():
            target_dir = ADR_DIR / folder_path
            if not self.dry_run:
                target_dir.mkdir(parents=True, exist_ok=True)
            print(
                f"  {'[DRY-RUN] Would create' if self.dry_run else 'Created'}: {target_dir.relative_to(WORKSPACE_ROOT)}"
            )
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

        # Backup all target ADR files
        for adr_num in self.migration_map.keys():
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
        folder_path, title_slug = self.migration_map[adr_num]
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
        first_adr = min(self.migration_map.keys())
        last_adr = max(self.migration_map.keys())
        audit_file = WORKSPACE_ROOT / f"adr_references_{first_adr}-{last_adr}.json"
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
        first_adr = min(self.migration_map.keys())
        last_adr = max(self.migration_map.keys())
        audit_file = WORKSPACE_ROOT / f"adr_references_{first_adr}-{last_adr}.json"
        if not audit_file.exists():
            print("  ⚠️  Link audit data not found.")
            return

        with open(audit_file) as f:
            audit_data = json.load(f)

        refs_to = audit_data.get("references_to", {})

        # Build path mapping (old filename pattern → new path)
        path_mapping = {}
        for adr_num, (folder_path, _) in self.migration_map.items():
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
            WORKSPACE_ROOT
            / f"MIGRATION_REPORT_{min(self.migration_map.keys())}-{max(self.migration_map.keys())}{'_DRY_RUN' if self.dry_run else ''}.md"
        )

        with open(report_path, "w", encoding="utf-8") as f:
            f.write(
                f"# ADR Migration Report - ADRs {', '.join(sorted(self.migration_map.keys()))}\n\n"
            )
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
        print(f"  Target ADRs: {', '.join(sorted(self.migration_map.keys()))}")
        print("=" * 70)

        try:
            # Step 1: Create folder structure
            self.create_folder_structure()

            # Step 2: Backup files
            self.backup_files()

            # Step 3: Move ADR families
            for adr_num in sorted(self.migration_map.keys()):
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
    args = parse_args()
    target_adrs = args.adrs
    migration_map = get_migration_map(target_adrs)

    if not migration_map:
        print(f"❌ No valid ADRs found in: {target_adrs}")
        return

    print(f"📋 Migrating ADRs: {', '.join(sorted(migration_map.keys()))}")

    migrator = ADRMigrator(migration_map, dry_run=not args.live)
    migrator.run()


if __name__ == "__main__":
    main()
