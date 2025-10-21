"""Contract checksum computation and VERSION registry management.

This automation script computes SHA256 checksums for all contract artifacts
and manages the VERSION registry file that tracks contract stability for
release governance.

Usage:
    python -m k0.automation.compute_contract_checksums
    python -m k0.automation.compute_contract_checksums --check
    python -m k0.automation.compute_contract_checksums --update

Commands:
    (default) - Display current checksums for all contract artifacts
    --check   - Verify artifacts match VERSION registry (exit 1 on mismatch)
    --update  - Recompute checksums and update VERSION file

Exit Codes:
    0 - Success (or checksums match in --check mode)
    1 - Checksum mismatch (--check) or VERSION file errors
"""

from __future__ import annotations

import argparse
import hashlib
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_DIR = REPO_ROOT / "k0" / "contracts"
VERSION_FILE = CONTRACTS_DIR / "VERSION"
SCHEMA_DIR = CONTRACTS_DIR / "jsonschema"
OPENAPI_FILE = CONTRACTS_DIR / "openapi.k0.yaml"
ASYNCAPI_FILE = CONTRACTS_DIR / "asyncapi.events.yaml"
STORAGE_SQL_FILE = CONTRACTS_DIR / "sql" / "storage.sql"


def compute_sha256(file_path: Path) -> str:
    """Compute SHA256 checksum for a file."""
    hasher = hashlib.sha256()
    with file_path.open("rb") as handle:
        while chunk := handle.read(8192):
            hasher.update(chunk)
    return hasher.hexdigest()


def collect_contract_artifacts() -> dict[str, Any]:
    """Collect all contract artifacts and compute checksums."""
    artifacts: dict[str, Any] = {}

    # OpenAPI specification
    if OPENAPI_FILE.exists():
        artifacts["openapi"] = {
            "file": "openapi.k0.yaml",
            "version": "1.0.0",
            "sha256": compute_sha256(OPENAPI_FILE),
        }

    # AsyncAPI specification
    if ASYNCAPI_FILE.exists():
        artifacts["asyncapi"] = {
            "file": "asyncapi.events.yaml",
            "version": "1.0.0",
            "sha256": compute_sha256(ASYNCAPI_FILE),
        }

    # JSON Schemas
    schemas = []
    if SCHEMA_DIR.exists():
        for schema_file in sorted(SCHEMA_DIR.glob("*.json")):
            relative_path = schema_file.relative_to(CONTRACTS_DIR)
            schemas.append(
                {
                    "file": str(relative_path).replace("\\", "/"),
                    "sha256": compute_sha256(schema_file),
                }
            )
    if schemas:
        artifacts["schemas"] = schemas

    # Storage SQL
    if STORAGE_SQL_FILE.exists():
        artifacts["storage"] = {
            "file": "sql/storage.sql",
            "sha256": compute_sha256(STORAGE_SQL_FILE),
        }

    return artifacts


def load_version_registry() -> dict[str, Any]:
    """Load the VERSION registry file."""
    if not VERSION_FILE.exists():
        raise FileNotFoundError(f"VERSION file not found: {VERSION_FILE}")

    with VERSION_FILE.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def create_version_registry() -> dict[str, Any]:
    """Create a new VERSION registry structure."""
    return {
        "version": "1.0.0",
        "release_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "status": "frozen",
        "artifacts": collect_contract_artifacts(),
        "approvals": {
            "architecture": None,
            "security": None,
            "operations": None,
        },
        "changelog": [
            {
                "version": "1.0.0",
                "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "changes": [
                    "Initial version freeze for v1.0 release",
                    "All schemas stabilized",
                    "Checksum registry established",
                ],
            }
        ],
    }


def write_version_registry(registry: dict[str, Any]) -> None:
    """Write the VERSION registry file with comments."""
    # Create YAML dump
    content_lines = [
        "# K0 Contracts Version Registry",
        "# This file tracks the canonical version and checksums for all contract artifacts.",
        "# Changes to this file require Architecture + Security + Ops approval.",
        "",
    ]

    # Manually format YAML for readability
    yaml_content = yaml.dump(
        registry,
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
    )
    content_lines.append(yaml_content)

    VERSION_FILE.write_text("\n".join(content_lines), encoding="utf-8")


def display_checksums() -> None:
    """Display current checksums for all contract artifacts."""
    artifacts = collect_contract_artifacts()

    print("[ContractChecksums] Current artifact checksums:")
    print()

    if "openapi" in artifacts:
        print(f"OpenAPI: {artifacts['openapi']['file']}")
        print(f"  SHA256: {artifacts['openapi']['sha256']}")
        print()

    if "asyncapi" in artifacts:
        print(f"AsyncAPI: {artifacts['asyncapi']['file']}")
        print(f"  SHA256: {artifacts['asyncapi']['sha256']}")
        print()

    if "schemas" in artifacts:
        print(f"JSON Schemas ({len(artifacts['schemas'])} files):")
        for schema in artifacts["schemas"]:
            print(f"  {schema['file']}: {schema['sha256']}")
        print()

    if "storage" in artifacts:
        print(f"Storage SQL: {artifacts['storage']['file']}")
        print(f"  SHA256: {artifacts['storage']['sha256']}")
        print()


def verify_checksums() -> bool:
    """Verify current checksums match VERSION registry."""
    try:
        registry = load_version_registry()
    except FileNotFoundError as exc:
        print(f"[ContractChecksums] ERROR: {exc}")
        print("[ContractChecksums] Run with --update to create VERSION file.")
        return False

    current = collect_contract_artifacts()
    registered = registry.get("artifacts", {})

    mismatches = []

    # Check OpenAPI
    if "openapi" in current and "openapi" in registered:
        if current["openapi"]["sha256"] != registered["openapi"]["sha256"]:
            mismatches.append(
                f"OpenAPI checksum mismatch:\n"
                f"  Current:    {current['openapi']['sha256']}\n"
                f"  Registered: {registered['openapi']['sha256']}"
            )

    # Check AsyncAPI
    if "asyncapi" in current and "asyncapi" in registered:
        if current["asyncapi"]["sha256"] != registered["asyncapi"]["sha256"]:
            mismatches.append(
                f"AsyncAPI checksum mismatch:\n"
                f"  Current:    {current['asyncapi']['sha256']}\n"
                f"  Registered: {registered['asyncapi']['sha256']}"
            )

    # Check schemas
    if "schemas" in current and "schemas" in registered:
        current_schemas = {s["file"]: s["sha256"] for s in current["schemas"]}
        registered_schemas = {s["file"]: s["sha256"] for s in registered["schemas"]}

        for file, checksum in current_schemas.items():
            if file not in registered_schemas:
                mismatches.append(f"New schema not registered: {file}")
            elif checksum != registered_schemas[file]:
                mismatches.append(
                    f"Schema checksum mismatch: {file}\n"
                    f"  Current:    {checksum}\n"
                    f"  Registered: {registered_schemas[file]}"
                )

        for file in registered_schemas:
            if file not in current_schemas:
                mismatches.append(f"Registered schema missing: {file}")

    # Check storage
    if "storage" in current and "storage" in registered:
        if current["storage"]["sha256"] != registered["storage"]["sha256"]:
            mismatches.append(
                f"Storage SQL checksum mismatch:\n"
                f"  Current:    {current['storage']['sha256']}\n"
                f"  Registered: {registered['storage']['sha256']}"
            )

    if mismatches:
        print("[ContractChecksums] ❌ Contract integrity check FAILED")
        print()
        for mismatch in mismatches:
            print(mismatch)
            print()
        print("[ContractChecksums] Contract artifacts have been modified without")
        print("[ContractChecksums] updating the VERSION registry.")
        print()
        print("[ContractChecksums] If this change is intentional:")
        print("[ContractChecksums]   1. Update VERSION with architecture approval")
        print(
            "[ContractChecksums]   2. Run: python -m k0.automation.compute_contract_checksums --update"
        )
        print(
            "[ContractChecksums]   3. Commit both contract changes and VERSION update"
        )
        return False

    print("[ContractChecksums] ✅ All contract checksums match VERSION registry")
    print(f"[ContractChecksums] Registry version: {registry.get('version', 'unknown')}")
    print(f"[ContractChecksums] Registry status: {registry.get('status', 'unknown')}")
    return True


def update_version_file() -> None:
    """Update VERSION file with current checksums."""
    if VERSION_FILE.exists():
        print(f"[ContractChecksums] Updating existing VERSION file: {VERSION_FILE}")
        registry = load_version_registry()
        registry["artifacts"] = collect_contract_artifacts()
    else:
        print(f"[ContractChecksums] Creating new VERSION file: {VERSION_FILE}")
        registry = create_version_registry()

    write_version_registry(registry)
    print("[ContractChecksums] ✅ VERSION file updated successfully")
    print()
    print("[ContractChecksums] Next steps:")
    print("[ContractChecksums]   1. Review changes: git diff k0/contracts/VERSION")
    print("[ContractChecksums]   2. Update approvals section if needed")
    print("[ContractChecksums]   3. Commit: git add k0/contracts/VERSION")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compute and verify contract artifact checksums"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--check",
        action="store_true",
        help="Verify checksums match VERSION registry (CI mode)",
    )
    group.add_argument(
        "--update",
        action="store_true",
        help="Update VERSION file with current checksums",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)

    if args.check:
        return 0 if verify_checksums() else 1
    elif args.update:
        update_version_file()
        return 0
    else:
        display_checksums()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
