"""CI gate: schema checksums embedded in manifests match their files on disk.

Each manifest may carry a ``checksums:`` block populated by tooling:

.. code-block:: yaml

    checksums:
      schema_sha256: <hex>
      manifest_sha256: <hex>

The gate recomputes both digests and fails if any embedded value
disagrees with the on-disk file. If the block is absent or empty
(``{}``), the gate is silent — the value is filled by ``--update``
in a follow-up PR or by CI tooling.

``manifest_sha256`` is computed over the YAML bytes with the
``checksums`` block stripped (so it is stable under self-update).
``schema_sha256`` is the SHA256 of the referenced JSON schema file.

Auto-fix: ``python -m tooling.ci.gates.schema_checksum_stable --update``
rewrites every manifest's ``checksums`` block in place.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path
from typing import Any

import yaml

from tooling.contracts.manifest_loader import discover_manifest_files

GATE_NAME = "schema_checksum_stable"


def _repo_root(args: argparse.Namespace) -> Path:
    if args.repo_root:
        return Path(args.repo_root).resolve()
    return Path(__file__).resolve().parents[3]


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _manifest_self_sha(raw: dict[str, Any]) -> str:
    """Compute manifest SHA over a copy with ``checksums`` stripped.

    Uses canonical YAML dump so output is byte-stable across runs.
    """
    copy = {k: v for k, v in raw.items() if k != "checksums"}
    canonical = yaml.safe_dump(copy, sort_keys=True, default_flow_style=False, allow_unicode=True)
    return _sha256_bytes(canonical.encode("utf-8"))


def _schema_path(contracts_root: Path, raw: dict[str, Any]) -> Path:
    return (contracts_root / raw["schema"]).resolve()


def _check(contracts_root: Path, *, update: bool) -> tuple[list[str], list[Path]]:
    """Return (violations, updated_files)."""
    violations: list[str] = []
    updated: list[Path] = []
    for path in discover_manifest_files(contracts_root):
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            violations.append(f"{path.name}: not a YAML mapping")
            continue
        schema_p = _schema_path(contracts_root, raw)
        if not schema_p.exists():
            violations.append(f"{path.name}: referenced schema not found: {raw.get('schema')}")
            continue

        embedded = raw.get("checksums") or {}
        actual_schema = _sha256_file(schema_p)
        actual_manifest = _manifest_self_sha(raw)

        if update:
            new_block = {
                "schema_sha256": actual_schema,
                "manifest_sha256": actual_manifest,
            }
            if embedded != new_block:
                raw["checksums"] = new_block
                path.write_text(
                    yaml.safe_dump(
                        raw,
                        sort_keys=False,
                        default_flow_style=False,
                        allow_unicode=True,
                    ),
                    encoding="utf-8",
                )
                updated.append(path)
            continue

        # If embedded is empty, the block is unfilled — silent (PR#1 mode).
        if not embedded:
            continue

        emb_schema = embedded.get("schema_sha256")
        emb_manifest = embedded.get("manifest_sha256")
        if emb_schema and emb_schema != actual_schema:
            violations.append(
                f"{path.name}: schema_sha256 mismatch: "
                f"embedded={emb_schema} actual={actual_schema}"
            )
        if emb_manifest and emb_manifest != actual_manifest:
            violations.append(
                f"{path.name}: manifest_sha256 mismatch: "
                f"embedded={emb_manifest} actual={actual_manifest}"
            )
    return violations, updated


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog=f"tooling.ci.gates.{GATE_NAME}")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--fail-on-violation", dest="fail", action="store_true", default=True)
    mode.add_argument("--warn-only", dest="fail", action="store_false")
    parser.add_argument(
        "--update", action="store_true", help="Rewrite manifests' checksums blocks in place."
    )
    parser.add_argument("--repo-root", type=str, default=None)
    args = parser.parse_args(argv)

    repo_root = _repo_root(args)
    contracts_root = repo_root / "bridge" / "contracts"
    if not contracts_root.exists():
        print(f"[{GATE_NAME}] CRASH: contracts root missing", file=sys.stderr)
        return 2

    import time

    started = time.perf_counter()
    violations, updated = _check(contracts_root, update=args.update)
    elapsed_ms = int((time.perf_counter() - started) * 1000)

    if args.update:
        for p in updated:
            print(f"updated: {p.relative_to(repo_root).as_posix()}")
        print(
            f"[{GATE_NAME}] UPDATED ({len(updated)} file(s)) in {elapsed_ms} ms",
            file=sys.stderr,
        )
        return 0

    if not violations:
        print(f"[{GATE_NAME}] OK (0 violations) in {elapsed_ms} ms", file=sys.stderr)
        return 0

    for line in violations:
        print(line)
    if args.fail:
        print(
            f"[{GATE_NAME}] FAIL ({len(violations)} violation(s)) in {elapsed_ms} ms",
            file=sys.stderr,
        )
        return 1
    print(
        f"[{GATE_NAME}] WARN ({len(violations)} violation(s)) in {elapsed_ms} ms",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
