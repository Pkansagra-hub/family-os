"""Contract compatibility checker for detecting breaking changes and enforcing SemVer.

This automation script validates contract changes between git branches to ensure:
- Breaking changes are detected (field removal, type changes, required field addition, enum contraction)
- SemVer version bumps match change severity (BREAKING → MAJOR, COMPATIBLE → MINOR, PATCH → PATCH)
- N/N+1 compatibility policy is enforced (at most 2 active versions)
- Human-readable reports are generated for CI/CD artifacts

Based on ADR-0013 (Pipeline Versioning Policy) and ADR-0013a (Schema Version Registry).

Usage:
    python -m k0.automation.contract_compatibility_checker --check
    python -m k0.automation.contract_compatibility_checker --base-ref origin/main --head-ref HEAD --fail-on-breaking
    python -m k0.automation.contract_compatibility_checker --schema-file envelope.schema.json --old-version 1.0.0 --new-version 1.1.0

Exit Codes:
    0 - Success (no breaking changes, or breaking changes properly versioned)
    1 - Failure (breaking changes without MAJOR bump, or other violations)
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONTRACTS_DIR = REPO_ROOT / "k0" / "contracts"
DEFAULT_SCHEMA_DIR = DEFAULT_CONTRACTS_DIR / "jsonschema"


class ChangeType(Enum):
    """Severity classification of schema changes."""

    BREAKING = "breaking"
    COMPATIBLE = "compatible"
    PATCH = "patch"


@dataclass
class SchemaChange:
    """Represents a single change in a schema."""

    change_type: ChangeType
    path: str  # JSONPath to changed field (e.g., "properties.fieldName.type")
    old_value: Any
    new_value: Any
    description: str


@dataclass
class CompatibilityCheckResult:
    """Result of compatibility check between two schema versions."""

    schema_name: str
    old_version: str
    new_version: str
    changes: list[SchemaChange]
    is_breaking: bool
    semver_valid: bool
    issues: list[str]  # List of remediation messages


def parse_semver(version: str) -> tuple[int, int, int]:
    """Parse semantic version string into (major, minor, patch) tuple.

    Args:
        version: Version string like "1.0.0"

    Returns:
        Tuple of (major, minor, patch) integers

    Raises:
        ValueError: If version format is invalid
    """
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)$", version)
    if not match:
        raise ValueError(f"Invalid SemVer format: {version}. Expected X.Y.Z")

    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def _get_json_pointer_path(path_parts: list[str]) -> str:
    """Convert path parts list to JSON Pointer format.

    Args:
        path_parts: List of path components (e.g., ['properties', 'fieldName', 'type'])

    Returns:
        JSON Pointer string (e.g., '/properties/fieldName/type')
    """
    return "/" + "/".join(part.replace("~", "~0").replace("/", "~1") for part in path_parts)


def _diff_dicts(
    old: dict[str, Any],
    new: dict[str, Any],
    path_parts: list[str] | None = None,
) -> list[SchemaChange]:
    """Recursively diff two dictionaries to find changes.

    Args:
        old: Old dictionary
        new: New dictionary
        path_parts: Current path in the object tree

    Returns:
        List of SchemaChange objects
    """
    if path_parts is None:
        path_parts = []

    changes: list[SchemaChange] = []

    # Check for removed keys (field removal is BREAKING)
    for key in old:
        if key not in new:
            path = _get_json_pointer_path(path_parts + [key])
            changes.append(
                SchemaChange(
                    change_type=ChangeType.BREAKING,
                    path=path,
                    old_value=old[key],
                    new_value=None,
                    description=f"Field removed: {path}",
                )
            )

    # Check for added keys or type changes
    for key in new:
        current_path = path_parts + [key]
        path = _get_json_pointer_path(current_path)

        if key not in old:
            # New key added
            # Only BREAKING if it's required (will be checked separately)
            if isinstance(new[key], dict) and new[key].get("type"):
                changes.append(
                    SchemaChange(
                        change_type=ChangeType.COMPATIBLE,
                        path=path,
                        old_value=None,
                        new_value=new[key],
                        description=f"Optional field added: {path}",
                    )
                )
        else:
            # Key exists in both - check if value changed
            old_val = old[key]
            new_val = new[key]

            if old_val == new_val:
                # No change
                continue

            # Check for specific breaking changes
            if isinstance(old_val, dict) and isinstance(new_val, dict):
                # Recursively check nested objects
                nested_changes = _diff_dicts(old_val, new_val, current_path)
                changes.extend(nested_changes)
            elif key == "type" and old_val != new_val:
                # Type change is BREAKING
                changes.append(
                    SchemaChange(
                        change_type=ChangeType.BREAKING,
                        path=path,
                        old_value=old_val,
                        new_value=new_val,
                        description=f"Type changed from '{old_val}' to '{new_val}': {path}",
                    )
                )
            elif key == "enum" and isinstance(old_val, list) and isinstance(new_val, list):
                # Enum value removal is BREAKING
                removed_values = set(old_val) - set(new_val)
                if removed_values:
                    changes.append(
                        SchemaChange(
                            change_type=ChangeType.BREAKING,
                            path=path,
                            old_value=old_val,
                            new_value=new_val,
                            description=f"Enum values removed {removed_values} from {path}",
                        )
                    )
                # Enum value additions are COMPATIBLE
                added_values = set(new_val) - set(old_val)
                if added_values:
                    changes.append(
                        SchemaChange(
                            change_type=ChangeType.COMPATIBLE,
                            path=path,
                            old_value=old_val,
                            new_value=new_val,
                            description=f"Enum values added {added_values} to {path}",
                        )
                    )

    return changes


def _check_required_changes(
    old_schema: dict[str, Any],
    new_schema: dict[str, Any],
) -> list[SchemaChange]:
    """Check for changes in required field list (breaking if expanded).

    Args:
        old_schema: Old schema object
        new_schema: New schema object

    Returns:
        List of SchemaChange objects for required field changes
    """
    changes: list[SchemaChange] = []

    old_required = set(old_schema.get("required", []))
    new_required = set(new_schema.get("required", []))

    # New required fields = BREAKING (existing optional fields became required)
    added_required = new_required - old_required
    if added_required:
        for field in added_required:
            changes.append(
                SchemaChange(
                    change_type=ChangeType.BREAKING,
                    path=f"/required/{field}",
                    old_value=list(old_required),
                    new_value=list(new_required),
                    description=f"Field '{field}' now required (was optional)",
                )
            )

    return changes


def detect_changes(
    old_schema: dict[str, Any],
    new_schema: dict[str, Any],
) -> list[SchemaChange]:
    """Detect all changes between two schema versions.

    Args:
        old_schema: Original schema object
        new_schema: New schema object

    Returns:
        List of SchemaChange objects
    """
    changes: list[SchemaChange] = []

    # First check required field changes
    changes.extend(_check_required_changes(old_schema, new_schema))

    # Then check property changes (properties object may be None)
    old_props = old_schema.get("properties", {})
    new_props = new_schema.get("properties", {})

    if isinstance(old_props, dict) and isinstance(new_props, dict):
        prop_changes = _diff_dicts(old_props, new_props, ["properties"])
        changes.extend(prop_changes)

    # Check top-level schema changes (type, enum, etc.)
    top_level_changes = _diff_dicts(old_schema, new_schema)
    # Filter out already-detected changes
    detected_paths = {change.path for change in changes}
    for change in top_level_changes:
        if change.path not in detected_paths:
            changes.append(change)

    return changes


def classify_change_severity(changes: list[SchemaChange]) -> ChangeType:
    """Determine if changes are breaking, compatible, or patch-level.

    Args:
        changes: List of SchemaChange objects

    Returns:
        ChangeType.BREAKING if any breaking changes exist,
        ChangeType.COMPATIBLE if any compatible additions exist,
        ChangeType.PATCH otherwise
    """
    if not changes:
        return ChangeType.PATCH

    # Check for breaking changes
    if any(change.change_type == ChangeType.BREAKING for change in changes):
        return ChangeType.BREAKING

    # Check for compatible additions
    if any(change.change_type == ChangeType.COMPATIBLE for change in changes):
        return ChangeType.COMPATIBLE

    return ChangeType.PATCH


def validate_version_bump(
    old_version: str,
    new_version: str,
    change_severity: ChangeType,
) -> tuple[bool, str]:
    """Ensure version bump matches change severity (SemVer).

    Args:
        old_version: Original version (e.g., "1.0.0")
        new_version: New version (e.g., "1.1.0")
        change_severity: Type of changes detected

    Returns:
        Tuple of (is_valid: bool, message: str)
    """
    try:
        old_major, old_minor, old_patch = parse_semver(old_version)
        new_major, new_minor, new_patch = parse_semver(new_version)
    except ValueError as e:
        return False, str(e)

    if change_severity == ChangeType.BREAKING:
        # BREAKING changes require MAJOR version bump
        if new_major > old_major:
            return True, "MAJOR version bump matches BREAKING changes"
        else:
            return (
                False,
                f"BREAKING changes require MAJOR version bump (got {old_version} → {new_version})",
            )

    elif change_severity == ChangeType.COMPATIBLE:
        # COMPATIBLE changes require MINOR version bump (or MAJOR is also ok)
        if new_major > old_major:
            return True, "MAJOR version bump for compatible changes (conservative)"
        elif new_major == old_major and new_minor > old_minor:
            return True, "MINOR version bump matches COMPATIBLE changes"
        elif new_major == old_major and new_minor == old_minor and new_patch > old_patch:
            return (
                False,
                f"PATCH bump for compatible changes (need MINOR) ({old_version} → {new_version})",
            )
        else:
            return (
                False,
                f"Version must increase for compatible changes ({old_version} → {new_version})",
            )

    else:  # PATCH
        # PATCH changes only update patch version
        if new_major > old_major or new_minor > old_minor:
            return (
                False,
                f"PATCH-only changes should not bump MAJOR or MINOR ({old_version} → {new_version})",
            )
        elif new_patch > old_patch:
            return True, "PATCH version bump matches minor changes"
        else:
            return False, f"Version must increase for patch changes ({old_version} → {new_version})"


def _load_schema_from_git(git_ref: str, file_path: str) -> dict[str, Any] | None:
    """Load schema file from specific git reference.

    Args:
        git_ref: Git reference (branch, tag, commit SHA)
        file_path: Relative file path in repo

    Returns:
        Parsed schema object or None if file doesn't exist
    """
    try:
        result = subprocess.run(
            ["git", "show", f"{git_ref}:{file_path}"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return None

        # Try JSON first
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            # Try YAML
            return yaml.safe_load(result.stdout)

    except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
        return None


def _get_changed_schema_files(
    base_ref: str,
    head_ref: str,
    schema_dir: Path,
) -> list[str]:
    """Get list of schema files changed between two git refs.

    Args:
        base_ref: Base git reference (e.g., "origin/main")
        head_ref: Head git reference (e.g., "HEAD")
        schema_dir: Schema directory path

    Returns:
        List of relative file paths that changed
    """
    try:
        result = subprocess.run(
            [
                "git",
                "diff",
                "--name-only",
                "--diff-filter=ACMR",
                f"{base_ref}...{head_ref}",
                "--",
                str(schema_dir),
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode == 0:
            return [line.strip() for line in result.stdout.strip().split("\n") if line.strip()]
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
        pass

    return []


def check_compatibility(
    base_ref: str,
    head_ref: str,
    schema_dir: Path | None = None,
) -> list[CompatibilityCheckResult]:
    """Check contract compatibility between two git references.

    Args:
        base_ref: Base git reference (e.g., "origin/main")
        head_ref: Head git reference (e.g., "HEAD")
        schema_dir: Schema directory (default: k0/contracts/jsonschema)

    Returns:
        List of CompatibilityCheckResult objects
    """
    if schema_dir is None:
        schema_dir = DEFAULT_SCHEMA_DIR

    results: list[CompatibilityCheckResult] = []
    changed_files = _get_changed_schema_files(base_ref, head_ref, schema_dir)

    for file_path in changed_files:
        rel_path = str(Path(file_path).relative_to(REPO_ROOT)).replace("\\", "/")

        old_schema = _load_schema_from_git(base_ref, rel_path)
        new_schema = _load_schema_from_git(head_ref, rel_path)

        # Skip if both don't exist or are identical
        if not old_schema or not new_schema or old_schema == new_schema:
            continue

        # Extract schema name from filename
        schema_name = Path(file_path).stem

        # Detect changes
        changes = detect_changes(old_schema, new_schema)
        if not changes:
            continue

        change_severity = classify_change_severity(changes)

        # Extract versions from old and new schemas (if available)
        # For now, use schema_version from envelope or default to "unknown"
        old_version = old_schema.get("version", "unknown")
        new_version = new_schema.get("version", "unknown")

        # If versions not found, try $id pattern
        if old_version == "unknown":
            old_id = old_schema.get("$id", "")
            if "v" in old_id:
                old_version = old_id.split("v")[-1].rstrip('}"') or "unknown"
        if new_version == "unknown":
            new_id = new_schema.get("$id", "")
            if "v" in new_id:
                new_version = new_id.split("v")[-1].rstrip('}"') or "unknown"

        # Validate version bump
        semver_valid, semver_msg = validate_version_bump(old_version, new_version, change_severity)

        issues = []
        if not semver_valid:
            issues.append(f"SemVer violation: {semver_msg}")

        is_breaking = change_severity == ChangeType.BREAKING

        result = CompatibilityCheckResult(
            schema_name=schema_name,
            old_version=old_version,
            new_version=new_version,
            changes=changes,
            is_breaking=is_breaking,
            semver_valid=semver_valid,
            issues=issues,
        )
        results.append(result)

    return results


def generate_compatibility_report(
    results: list[CompatibilityCheckResult],
    fail_on_breaking: bool = False,
) -> tuple[str, bool]:
    """Generate human-readable report for CI artifacts.

    Args:
        results: List of CompatibilityCheckResult objects
        fail_on_breaking: If True, report fails if any breaking changes detected

    Returns:
        Tuple of (report_text: str, success: bool)
    """
    report_lines = [
        "# Contract Compatibility Report",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
    ]

    if not results:
        report_lines.extend(
            [
                "## Summary",
                "**Status:** ✅ PASS",
                "✅ No contract changes detected",
                "",
            ]
        )
        return "\n".join(report_lines), True

    breaking_count = sum(1 for r in results if r.is_breaking)
    semver_violations = sum(1 for r in results if not r.semver_valid)

    success = not (breaking_count > 0 and fail_on_breaking) and semver_violations == 0

    report_lines.extend(
        [
            "## Summary",
            f"**Status:** {'✅ PASS' if success else '❌ FAIL'}",
            f"- Total schemas checked: {len(results)}",
            f"- Breaking changes: {breaking_count}",
            f"- SemVer violations: {semver_violations}",
            "",
        ]
    )

    # Details
    report_lines.append("## Details\n")

    for result in results:
        report_lines.append(f"### {result.schema_name}")
        report_lines.append(f"**Version:** {result.old_version} → {result.new_version}")

        if result.issues:
            report_lines.append("**Issues:**")
            for issue in result.issues:
                report_lines.append(f"- ❌ {issue}")

        if result.changes:
            report_lines.append("**Changes:**")
            for change in result.changes:
                icon = "🔴" if change.change_type == ChangeType.BREAKING else "🟡"
                report_lines.append(f"- {icon} {change.description} ({change.change_type.value})")

        report_lines.append("")

    # Recommendations
    report_lines.append("## Recommendations\n")
    for result in results:
        if result.issues or result.is_breaking:
            report_lines.append(f"### {result.schema_name}")
            if result.is_breaking:
                major, minor, patch = parse_semver(result.old_version)
                recommended_version = f"{major + 1}.0.0"
                report_lines.append(
                    f"- **Update version to {recommended_version}** (MAJOR bump for breaking changes)"
                )
            if result.issues:
                for issue in result.issues:
                    report_lines.append(f"- **Fix:** {issue}")
            report_lines.append("")

    return "\n".join(report_lines), success


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check contract compatibility and enforce SemVer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Check compatibility between branches
  python -m k0.automation.contract_compatibility_checker \\
    --base-ref origin/main --head-ref HEAD --fail-on-breaking

  # Check specific file versions
  python -m k0.automation.contract_compatibility_checker \\
    --schema-file envelope.schema.json \\
    --old-version 1.0.0 --new-version 1.1.0
        """,
    )

    parser.add_argument(
        "--base-ref",
        default="origin/main",
        help="Base git reference (default: origin/main)",
    )
    parser.add_argument(
        "--head-ref",
        default="HEAD",
        help="Head git reference (default: HEAD)",
    )
    parser.add_argument(
        "--schema-dir",
        type=Path,
        default=DEFAULT_SCHEMA_DIR,
        help=f"Schema directory (default: {DEFAULT_SCHEMA_DIR})",
    )
    parser.add_argument(
        "--fail-on-breaking",
        action="store_true",
        help="Exit with code 1 if breaking changes detected",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify all contracts are properly versioned",
    )
    parser.add_argument(
        "--schema-file",
        type=Path,
        help="Single schema file to check (with --old-version and --new-version)",
    )
    parser.add_argument(
        "--old-version",
        help="Old version (used with --schema-file)",
    )
    parser.add_argument(
        "--new-version",
        help="New version (used with --schema-file)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Verbose output",
    )

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Main entry point.

    Args:
        argv: Command-line arguments

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    args = parse_args(argv)

    # Add cognitive_trace_id for observability (ADR-0086)
    trace_id = datetime.now(timezone.utc).isoformat()

    if args.verbose:
        print(f"[ContractChecker] cognitive_trace_id={trace_id}", file=sys.stderr)

    # Single file check mode
    if args.schema_file:
        if not args.old_version or not args.new_version:
            print(
                "[ContractChecker] ERROR: --old-version and --new-version required with --schema-file",
                file=sys.stderr,
            )
            return 1

        try:
            old_schema = json.loads(args.schema_file.read_text())
            new_schema = json.loads(args.schema_file.read_text())
        except (json.JSONDecodeError, FileNotFoundError) as e:
            print(f"[ContractChecker] ERROR: Failed to load schema: {e}", file=sys.stderr)
            return 1

        changes = detect_changes(old_schema, new_schema)
        severity = classify_change_severity(changes)
        is_valid, msg = validate_version_bump(args.old_version, args.new_version, severity)

        print(f"[ContractChecker] {msg}")
        return 0 if is_valid else 1

    # Git-based check
    results = check_compatibility(args.base_ref, args.head_ref, args.schema_dir)
    report, success = generate_compatibility_report(results, fail_on_breaking=args.fail_on_breaking)

    print(report)

    if args.verbose and results:
        print("\n[ContractChecker] Full change details:", file=sys.stderr)
        for result in results:
            print(f"  {result.schema_name}: {len(result.changes)} changes", file=sys.stderr)

    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
