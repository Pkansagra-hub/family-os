"""Content + bundle checksums for bridge contracts.

A *bundle SHA* is the SHA256 over the sorted ``(relative_path, sha256)``
lines for every manifest YAML and every payload schema JSON. It is what
generated artifacts stamp in their header so reviewers can spot which
manifest revision produced them.

CLI: ``python -m tooling.contracts.checksums [--update]``
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONTRACTS_ROOT = REPO_ROOT / "bridge" / "contracts"


def compute_sha256(path: Path) -> str:
    """SHA256 hex of a file's bytes."""
    hasher = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(8192):
            hasher.update(chunk)
    return hasher.hexdigest()


def collect_artifact_checksums(contracts_root: Path) -> list[tuple[str, str]]:
    """Return ``[(relative_path, sha256), ...]`` sorted by path.

    Includes every YAML in ``manifests/`` and every JSON in ``schemas/``.
    Excludes ``_meta/`` (which holds the meta-schema itself, not contracts).
    """
    items: list[tuple[str, str]] = []
    for sub in ("manifests", "schemas"):
        d = contracts_root / sub
        if not d.exists():
            continue
        for path in sorted(d.rglob("*")):
            if not path.is_file() or path.name == ".gitkeep":
                continue
            rel = path.relative_to(contracts_root).as_posix()
            items.append((rel, compute_sha256(path)))
    items.sort()
    return items


def manifest_bundle_sha(contracts_root: Path) -> str:
    """SHA256 over the canonical artifact-checksum listing."""
    items = collect_artifact_checksums(contracts_root)
    canonical = "\n".join(f"{rel} {digest}" for rel, digest in items)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bridge contract checksums")
    parser.add_argument(
        "--update",
        action="store_true",
        help="Reserved for future VERSION-file maintenance. No-op in MS-2.5.",
    )
    parser.add_argument(
        "--contracts-root",
        type=Path,
        default=DEFAULT_CONTRACTS_ROOT,
    )
    args = parser.parse_args(argv)
    items = collect_artifact_checksums(args.contracts_root)
    for rel, digest in items:
        print(f"{digest}  {rel}")
    print(f"# bundle_sha: {manifest_bundle_sha(args.contracts_root)}")
    if args.update:
        # Placeholder: VERSION-file write happens in MS-3a once the first
        # contract lands. Intentional no-op now per MS-2.5 plan.
        print("# --update: no VERSION file in MS-2.5; ignored")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(_main())
