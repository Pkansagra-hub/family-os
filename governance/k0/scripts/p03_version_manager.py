"""
P03 Version Manager - Track file versions with SHA256 checksums.

Manages VERSION.yaml files for P03 pipeline and consolidation modules.
Detects file changes, generates changelogs, and supports version bumping.

Part of P03 Wiring Governance Plan (Epic 2.1).

Usage:
    python -m governance.k0.scripts.p03_version_manager --generate
    python -m governance.k0.scripts.p03_version_manager --check
    python -m governance.k0.scripts.p03_version_manager --bump patch
    python -m governance.k0.scripts.p03_version_manager --changelog
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class FileChecksum:
    """Checksum information for a single file."""

    relative_path: str
    sha256: str
    size_bytes: int
    last_modified: str  # ISO format


@dataclass
class VersionManifest:
    """Complete version manifest for a directory."""

    version: str  # Semantic version e.g., "1.0.0"
    generated_at: str  # ISO timestamp
    generator: str  # Script name and version
    directory: str  # Relative path from repo root
    file_count: int
    total_size_bytes: int
    files: list[FileChecksum] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for YAML serialization."""
        return {
            "version": self.version,
            "generated_at": self.generated_at,
            "generator": self.generator,
            "directory": self.directory,
            "file_count": self.file_count,
            "total_size_bytes": self.total_size_bytes,
            "files": [
                {
                    "path": f.relative_path,
                    "sha256": f.sha256,
                    "size": f.size_bytes,
                    "modified": f.last_modified,
                }
                for f in self.files
            ],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VersionManifest":
        """Create from dictionary loaded from YAML."""
        files = [
            FileChecksum(
                relative_path=f["path"],
                sha256=f["sha256"],
                size_bytes=f["size"],
                last_modified=f["modified"],
            )
            for f in data.get("files", [])
        ]
        return cls(
            version=data.get("version", "0.0.0"),
            generated_at=data.get("generated_at", ""),
            generator=data.get("generator", ""),
            directory=data.get("directory", ""),
            file_count=data.get("file_count", 0),
            total_size_bytes=data.get("total_size_bytes", 0),
            files=files,
        )


@dataclass
class IntegrityResult:
    """Result of integrity check for a single file."""

    path: str
    status: str  # "ok", "modified", "added", "deleted"
    old_sha256: str | None = None
    new_sha256: str | None = None
    size_diff: int = 0


@dataclass
class IntegrityReport:
    """Complete integrity check report."""

    version: str
    checked_at: str
    total_files: int
    ok_count: int
    modified_count: int
    added_count: int
    deleted_count: int
    results: list[IntegrityResult] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        """True if no changes detected."""
        return self.modified_count == 0 and self.added_count == 0 and self.deleted_count == 0

    @property
    def changes(self) -> list[IntegrityResult]:
        """Return only changed files."""
        return [r for r in self.results if r.status != "ok"]


@dataclass
class ChangelogEntry:
    """Single changelog entry."""

    version: str
    date: str
    changes: list[str] = field(default_factory=list)


# =============================================================================
# Path Utilities
# =============================================================================


def _get_repo_root() -> Path:
    """Get repository root from script location."""
    return Path(__file__).parent.parent.parent.parent


def _get_p03_pipeline_dir() -> Path:
    """Get P03 pipeline directory."""
    return _get_repo_root() / "k0" / "pipelines" / "p03"


def _get_consolidation_dir() -> Path:
    """Get consolidation algorithms directory."""
    return _get_repo_root() / "k0" / "modules" / "consolidation"


def _get_version_file_path(target_dir: Path) -> Path:
    """Get VERSION.yaml path for a directory."""
    return target_dir / "VERSION.yaml"


# =============================================================================
# Checksum Functions
# =============================================================================


def compute_file_sha256(file_path: Path) -> str:
    """Compute SHA256 hash of a file."""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def scan_directory_files(target_dir: Path) -> list[FileChecksum]:
    """
    Scan all Python files in a directory and compute checksums.

    Excludes __pycache__, __init__.py, and VERSION.yaml.
    """
    if not target_dir.exists():
        return []

    checksums: list[FileChecksum] = []

    for py_file in sorted(target_dir.rglob("*.py")):
        # Skip excluded files
        if "__pycache__" in str(py_file):
            continue
        if py_file.name == "__init__.py":
            continue

        try:
            stat = py_file.stat()
            sha256 = compute_file_sha256(py_file)
            modified = datetime.fromtimestamp(stat.st_mtime).isoformat()

            checksums.append(
                FileChecksum(
                    relative_path=str(py_file.relative_to(target_dir)),
                    sha256=sha256,
                    size_bytes=stat.st_size,
                    last_modified=modified,
                )
            )
        except Exception as e:
            print(f"Warning: Could not process {py_file}: {e}")

    return checksums


# =============================================================================
# Version File Generation (#202)
# =============================================================================


def generate_version_file(
    target_dir: Path,
    version: str = "1.0.0",
    write: bool = True,
) -> VersionManifest:
    """
    Generate VERSION.yaml for a directory.

    Args:
        target_dir: Directory to scan
        version: Semantic version string
        write: If True, write VERSION.yaml to disk

    Returns:
        VersionManifest with all file checksums
    """
    repo_root = _get_repo_root()
    checksums = scan_directory_files(target_dir)

    total_size = sum(f.size_bytes for f in checksums)

    try:
        relative_dir = str(target_dir.relative_to(repo_root))
    except ValueError:
        relative_dir = str(target_dir)

    manifest = VersionManifest(
        version=version,
        generated_at=datetime.now().isoformat(),
        generator="p03_version_manager.py v1.0.0",
        directory=relative_dir,
        file_count=len(checksums),
        total_size_bytes=total_size,
        files=checksums,
    )

    if write:
        version_file = _get_version_file_path(target_dir)
        with open(version_file, "w", encoding="utf-8") as f:
            yaml.dump(
                manifest.to_dict(),
                f,
                default_flow_style=False,
                sort_keys=False,
                allow_unicode=True,
            )
        print(f"Generated {version_file}")

    return manifest


def load_version_file(target_dir: Path) -> VersionManifest | None:
    """Load existing VERSION.yaml from a directory."""
    version_file = _get_version_file_path(target_dir)

    if not version_file.exists():
        return None

    with open(version_file, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    return VersionManifest.from_dict(data)


# =============================================================================
# Integrity Check (#203)
# =============================================================================


def check_version_integrity(target_dir: Path) -> IntegrityReport:
    """
    Check if files have changed since VERSION.yaml was generated.

    Args:
        target_dir: Directory to check

    Returns:
        IntegrityReport with all changes detected
    """
    manifest = load_version_file(target_dir)

    if manifest is None:
        # No VERSION.yaml - treat all files as "added"
        current_files = scan_directory_files(target_dir)
        return IntegrityReport(
            version="0.0.0",
            checked_at=datetime.now().isoformat(),
            total_files=len(current_files),
            ok_count=0,
            modified_count=0,
            added_count=len(current_files),
            deleted_count=0,
            results=[
                IntegrityResult(
                    path=f.relative_path,
                    status="added",
                    new_sha256=f.sha256,
                )
                for f in current_files
            ],
        )

    # Build lookup from manifest
    manifest_lookup: dict[str, FileChecksum] = {f.relative_path: f for f in manifest.files}

    # Scan current files
    current_files = scan_directory_files(target_dir)
    current_lookup: dict[str, FileChecksum] = {f.relative_path: f for f in current_files}

    results: list[IntegrityResult] = []
    ok_count = 0
    modified_count = 0
    added_count = 0
    deleted_count = 0

    # Check each current file
    for path, current in current_lookup.items():
        if path not in manifest_lookup:
            # New file
            results.append(
                IntegrityResult(
                    path=path,
                    status="added",
                    new_sha256=current.sha256,
                )
            )
            added_count += 1
        elif current.sha256 != manifest_lookup[path].sha256:
            # Modified file
            old = manifest_lookup[path]
            results.append(
                IntegrityResult(
                    path=path,
                    status="modified",
                    old_sha256=old.sha256,
                    new_sha256=current.sha256,
                    size_diff=current.size_bytes - old.size_bytes,
                )
            )
            modified_count += 1
        else:
            # Unchanged
            results.append(
                IntegrityResult(
                    path=path,
                    status="ok",
                    old_sha256=current.sha256,
                    new_sha256=current.sha256,
                )
            )
            ok_count += 1

    # Check for deleted files
    for path in manifest_lookup:
        if path not in current_lookup:
            results.append(
                IntegrityResult(
                    path=path,
                    status="deleted",
                    old_sha256=manifest_lookup[path].sha256,
                )
            )
            deleted_count += 1

    return IntegrityReport(
        version=manifest.version,
        checked_at=datetime.now().isoformat(),
        total_files=len(current_files),
        ok_count=ok_count,
        modified_count=modified_count,
        added_count=added_count,
        deleted_count=deleted_count,
        results=results,
    )


# =============================================================================
# Version Bumping (#204)
# =============================================================================


def parse_version(version: str) -> tuple[int, int, int]:
    """Parse semantic version string to tuple."""
    parts = version.split(".")
    if len(parts) != 3:
        raise ValueError(f"Invalid version format: {version}")
    return int(parts[0]), int(parts[1]), int(parts[2])


def format_version(major: int, minor: int, patch: int) -> str:
    """Format version tuple to string."""
    return f"{major}.{minor}.{patch}"


def bump_version(
    target_dir: Path,
    bump_type: str = "patch",
    write: bool = True,
) -> tuple[str, str]:
    """
    Bump version and regenerate VERSION.yaml.

    Args:
        target_dir: Directory to bump
        bump_type: "major", "minor", or "patch"
        write: If True, write updated VERSION.yaml

    Returns:
        Tuple of (old_version, new_version)
    """
    manifest = load_version_file(target_dir)

    if manifest is None:
        old_version = "0.0.0"
    else:
        old_version = manifest.version

    major, minor, patch = parse_version(old_version)

    if bump_type == "major":
        new_version = format_version(major + 1, 0, 0)
    elif bump_type == "minor":
        new_version = format_version(major, minor + 1, 0)
    elif bump_type == "patch":
        new_version = format_version(major, minor, patch + 1)
    else:
        raise ValueError(f"Invalid bump type: {bump_type}")

    if write:
        generate_version_file(target_dir, version=new_version, write=True)

    return old_version, new_version


# =============================================================================
# Changelog Generation (#205)
# =============================================================================


def generate_changelog(target_dir: Path) -> ChangelogEntry | None:
    """
    Generate changelog entry based on current changes.

    Args:
        target_dir: Directory to check

    Returns:
        ChangelogEntry if changes found, None otherwise
    """
    report = check_version_integrity(target_dir)

    if report.is_clean:
        return None

    changes: list[str] = []

    if report.added_count > 0:
        added_files = [r.path for r in report.results if r.status == "added"]
        changes.append(f"Added {report.added_count} files: {', '.join(added_files[:5])}")
        if len(added_files) > 5:
            changes[-1] += f" (+{len(added_files) - 5} more)"

    if report.modified_count > 0:
        modified_files = [r.path for r in report.results if r.status == "modified"]
        changes.append(f"Modified {report.modified_count} files: {', '.join(modified_files[:5])}")
        if len(modified_files) > 5:
            changes[-1] += f" (+{len(modified_files) - 5} more)"

    if report.deleted_count > 0:
        deleted_files = [r.path for r in report.results if r.status == "deleted"]
        changes.append(f"Deleted {report.deleted_count} files: {', '.join(deleted_files[:5])}")
        if len(deleted_files) > 5:
            changes[-1] += f" (+{len(deleted_files) - 5} more)"

    return ChangelogEntry(
        version=report.version,
        date=datetime.now().strftime("%Y-%m-%d"),
        changes=changes,
    )


def append_to_changelog_file(
    changelog_path: Path,
    entry: ChangelogEntry,
) -> None:
    """Append changelog entry to CHANGELOG.md."""
    content = f"\n## [{entry.version}] - {entry.date}\n\n"
    for change in entry.changes:
        content += f"- {change}\n"

    if changelog_path.exists():
        existing = changelog_path.read_text(encoding="utf-8")
        # Insert after header
        if "# Changelog" in existing:
            parts = existing.split("\n## ", 1)
            if len(parts) == 2:
                new_content = parts[0] + content + "\n## " + parts[1]
            else:
                new_content = existing + content
        else:
            new_content = existing + content
    else:
        new_content = f"# Changelog\n\nAll notable changes to P03 files.\n{content}"

    changelog_path.write_text(new_content, encoding="utf-8")
    print(f"Updated {changelog_path}")


# =============================================================================
# Output Formatters
# =============================================================================


def print_integrity_report(report: IntegrityReport, target_name: str) -> None:
    """Print integrity report to stdout."""
    print(f"\n{target_name} Integrity Check (version {report.version})")
    print("=" * 60)
    print(f"Total Files:    {report.total_files}")
    print(f"Unchanged:      {report.ok_count}")
    print(f"Modified:       {report.modified_count}")
    print(f"Added:          {report.added_count}")
    print(f"Deleted:        {report.deleted_count}")
    print()

    if report.is_clean:
        print("Status: CLEAN - No changes detected")
    else:
        print("Status: CHANGES DETECTED")
        print()
        for r in report.changes:
            if r.status == "added":
                print(f"  + {r.path}")
            elif r.status == "modified":
                sign = "+" if r.size_diff >= 0 else ""
                print(f"  ~ {r.path} ({sign}{r.size_diff} bytes)")
            elif r.status == "deleted":
                print(f"  - {r.path}")


def print_combined_report(
    pipeline_report: IntegrityReport,
    algorithm_report: IntegrityReport,
) -> None:
    """Print combined report for both directories."""
    print()
    print("=" * 60)
    print("P03 VERSION INTEGRITY REPORT")
    print("=" * 60)

    print_integrity_report(pipeline_report, "Pipeline (k0/pipelines/p03)")
    print_integrity_report(algorithm_report, "Algorithms (k0/modules/consolidation)")

    total_changes = (
        pipeline_report.modified_count
        + pipeline_report.added_count
        + pipeline_report.deleted_count
        + algorithm_report.modified_count
        + algorithm_report.added_count
        + algorithm_report.deleted_count
    )

    print()
    print("=" * 60)
    if total_changes == 0:
        print("OVERALL: CLEAN - All files match VERSION.yaml")
    else:
        print(f"OVERALL: {total_changes} changes detected")
        print("Run --generate to update VERSION.yaml files")
    print()


# =============================================================================
# CLI
# =============================================================================


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="P03 Version Manager - Track file versions with SHA256 checksums",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python -m governance.k0.scripts.p03_version_manager --generate
    python -m governance.k0.scripts.p03_version_manager --check
    python -m governance.k0.scripts.p03_version_manager --bump patch
    python -m governance.k0.scripts.p03_version_manager --changelog
    python -m governance.k0.scripts.p03_version_manager --target pipeline --check
        """,
    )

    parser.add_argument(
        "--generate",
        action="store_true",
        help="Generate VERSION.yaml files",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check integrity against VERSION.yaml",
    )
    parser.add_argument(
        "--bump",
        type=str,
        choices=["major", "minor", "patch"],
        help="Bump version (major/minor/patch)",
    )
    parser.add_argument(
        "--changelog",
        action="store_true",
        help="Generate changelog from changes",
    )
    parser.add_argument(
        "--target",
        type=str,
        choices=["pipeline", "algorithms", "both"],
        default="both",
        help="Target directory (default: both)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't write files, just show what would happen",
    )

    args = parser.parse_args()

    # Default to --check if no action specified
    if not any([args.generate, args.check, args.bump, args.changelog]):
        args.check = True

    # Determine target directories
    pipeline_dir = _get_p03_pipeline_dir()
    algorithm_dir = _get_consolidation_dir()

    targets: list[tuple[str, Path]] = []
    if args.target in ("pipeline", "both"):
        targets.append(("Pipeline", pipeline_dir))
    if args.target in ("algorithms", "both"):
        targets.append(("Algorithms", algorithm_dir))

    write = not args.dry_run

    # Execute action
    if args.generate:
        print("Generating VERSION.yaml files...")
        for name, target_dir in targets:
            existing = load_version_file(target_dir)
            version = existing.version if existing else "1.0.0"
            manifest = generate_version_file(target_dir, version=version, write=write)
            print(f"  {name}: {manifest.file_count} files, {manifest.total_size_bytes:,} bytes")
        return 0

    if args.check:
        reports = []
        for name, target_dir in targets:
            report = check_version_integrity(target_dir)
            reports.append((name, report))

        if len(reports) == 2:
            print_combined_report(reports[0][1], reports[1][1])
        else:
            for name, report in reports:
                print_integrity_report(report, name)

        # Return 1 if any changes detected
        has_changes = any(not r.is_clean for _, r in reports)
        return 1 if has_changes else 0

    if args.bump:
        print(f"Bumping {args.bump} version...")
        for name, target_dir in targets:
            old_ver, new_ver = bump_version(target_dir, args.bump, write=write)
            print(f"  {name}: {old_ver} -> {new_ver}")
        return 0

    if args.changelog:
        print("Generating changelog entries...")
        for name, target_dir in targets:
            entry = generate_changelog(target_dir)
            if entry:
                print(f"\n{name}:")
                print(f"  Version: {entry.version}")
                print(f"  Date: {entry.date}")
                for change in entry.changes:
                    print(f"    - {change}")

                if write:
                    changelog_path = target_dir / "CHANGELOG.md"
                    append_to_changelog_file(changelog_path, entry)
            else:
                print(f"\n{name}: No changes to log")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
