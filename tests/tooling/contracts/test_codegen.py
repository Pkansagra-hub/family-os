"""MS-2.5 Epic 2.5.2 — codegen substrate tests.

No-mock policy: tests use a real on-disk fixture contracts tree. We copy
``bridge/contracts/_meta/`` to a temp dir so the meta-schema is real, then
write fixture manifests and schemas. No network, no time, no randomness.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from tooling.contracts.checksums import (
    collect_artifact_checksums,
    manifest_bundle_sha,
)
from tooling.contracts.codegen import (
    DATAMODEL_CODEGEN_FLAGS,
    diff_against_target,
    generate_outputs,
    write_outputs,
)
from tooling.contracts.compatibility import (
    ChangeType,
    check_compatibility,
    parse_semver,
)
from tooling.contracts.manifest_loader import (
    ManifestValidationError,
    load_manifests,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
REAL_META = REPO_ROOT / "bridge" / "contracts" / "_meta"


def _make_contracts_root(tmp_path: Path) -> Path:
    """Build a fresh contracts/ tree backed by the real meta-schema."""
    root = tmp_path / "contracts"
    (root / "_meta").mkdir(parents=True)
    shutil.copyfile(
        REAL_META / "manifest.schema.json",
        root / "_meta" / "manifest.schema.json",
    )
    (root / "manifests").mkdir()
    (root / "schemas").mkdir()
    return root


def _write_manifest(root: Path, name: str, *, topic: str, schema_file: str) -> Path:
    body = f"""\
topic: {topic}
direction: k1_to_k0
owner_team: k0
producer:
  kernel: k1
consumer:
  kernel: k0
schema: schemas/{schema_file}
delivery:
  transport: http
  ordering: best_effort
  ack_required: true
  online_required: false
  endpoint_class: cloud_k0
  partition_mode: k0_primary
semantics:
  idempotent: true
  duplicate_strategy: dedupe_by_envelope_id
  retention: P30D
  description: Test fixture manifest for the codegen substrate exit criterion.
sla:
  latency_p99_ms: 250
  throughput_per_sec: 50
versioning:
  semver: 1.0.0
  compat: compatible
status: active
"""
    p = root / "manifests" / name
    p.write_text(body, encoding="utf-8")
    return p


def _write_schema(root: Path, name: str) -> Path:
    p = root / "schemas" / name
    p.write_text(
        json.dumps(
            {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "$id": f"bridge://contracts/schemas/{name}",
                "title": name,
                "type": "object",
                "additionalProperties": False,
                "properties": {"id": {"type": "string"}},
                "required": ["id"],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return p


# ---------------------------------------------------------------------------
# Test 1: manifest_loader rejects manifests that violate the meta-schema.
# ---------------------------------------------------------------------------
def test_manifest_loader_rejects_invalid(tmp_path: Path) -> None:
    root = _make_contracts_root(tmp_path)
    bad = root / "manifests" / "bad.yaml"
    bad.write_text("topic: BAD-CASE\ndirection: k1_to_k0\n", encoding="utf-8")
    with pytest.raises(ManifestValidationError) as excinfo:
        load_manifests(root)
    assert "bad.yaml" in str(excinfo.value)


# ---------------------------------------------------------------------------
# Test 2: codegen is deterministic across two runs (byte-for-byte).
# ---------------------------------------------------------------------------
def test_codegen_is_deterministic(tmp_path: Path) -> None:
    root = _make_contracts_root(tmp_path)
    _write_schema(root, "memory.write.v1.json")
    _write_manifest(
        root, "memory.write.v1.yaml", topic="memory.write.v1", schema_file="memory.write.v1.json"
    )

    a = generate_outputs(contracts_root=root)
    b = generate_outputs(contracts_root=root)
    assert a == b
    # And the rendered text is byte-identical too.
    for k in a:
        assert a[k] == b[k]


# ---------------------------------------------------------------------------
# Test 3: --check mode detects drift when vendored output is mutated.
# ---------------------------------------------------------------------------
def test_codegen_check_detects_drift(tmp_path: Path) -> None:
    root = _make_contracts_root(tmp_path)
    _write_schema(root, "memory.write.v1.json")
    _write_manifest(
        root, "memory.write.v1.yaml", topic="memory.write.v1", schema_file="memory.write.v1.json"
    )
    target = tmp_path / "_generated"
    files = generate_outputs(contracts_root=root)
    write_outputs(files, target_root=target)

    # Clean run: no diff.
    assert diff_against_target(files, target_root=target) == []

    # Tamper.
    tampered = target / "k0" / "package_index.py"
    tampered.write_text(
        tampered.read_text(encoding="utf-8") + "\n# hand edit\n",
        encoding="utf-8",
    )
    diffs = diff_against_target(files, target_root=target)
    assert diffs, "drift must be detected"


# ---------------------------------------------------------------------------
# Test 4: K0 / K1 trees are disjoint — a k1_to_k0 contract emits k0 topics
# only on the k0 side, never on the k1 side.
# ---------------------------------------------------------------------------
def test_k0_k1_trees_are_disjoint(tmp_path: Path) -> None:
    root = _make_contracts_root(tmp_path)
    _write_schema(root, "memory.write.v1.json")
    _write_manifest(
        root, "memory.write.v1.yaml", topic="memory.write.v1", schema_file="memory.write.v1.json"
    )
    files = generate_outputs(contracts_root=root)
    k0_idx = files[Path("k0/package_index.py")]
    k1_idx = files[Path("k1/package_index.py")]
    assert "memory.write.v1" in k0_idx
    assert "memory.write.v1" not in k1_idx


# ---------------------------------------------------------------------------
# Test 5: every generated file carries the autogenerated header with the
# manifest_bundle_sha.
# ---------------------------------------------------------------------------
def test_autogenerated_header_present(tmp_path: Path) -> None:
    root = _make_contracts_root(tmp_path)
    _write_schema(root, "memory.write.v1.json")
    _write_manifest(
        root, "memory.write.v1.yaml", topic="memory.write.v1", schema_file="memory.write.v1.json"
    )
    files = generate_outputs(contracts_root=root)
    bundle = manifest_bundle_sha(root)
    for rel, text in files.items():
        # Package __init__.py is a docstring stub — exempt; everything else
        # must carry the canonical header.
        if rel.name == "__init__.py":
            continue
        assert "# AUTOGENERATED" in text, f"missing AUTOGENERATED in {rel}"
        assert f"# manifest_bundle_sha: {bundle}" in text, f"bundle SHA missing in {rel}"


# ---------------------------------------------------------------------------
# Test 6: BREAKING change classification — direction swap is breaking,
# requires major bump per ADR-0013.
# ---------------------------------------------------------------------------
def test_breaking_change_classification() -> None:
    old = {
        "topic": "memory.write.v1",
        "direction": "k1_to_k0",
        "schema": "schemas/memory.write.v1.json",
        "delivery": {
            "transport": "http",
            "ordering": "best_effort",
            "online_required": False,
            "endpoint_class": "cloud_k0",
        },
        "sla": {"latency_p99_ms": 250},
        "versioning": {"semver": "1.0.0"},
        "status": "active",
    }
    new = dict(old)
    new["direction"] = "k0_to_k1"  # breaking
    new["versioning"] = {"semver": "1.1.0"}  # only minor — wrong

    result = check_compatibility(old, new)
    assert result.is_breaking is True
    assert any(c.change_type == ChangeType.BREAKING for c in result.changes)
    assert result.semver_valid is False  # major bump required, got minor

    # Now bump major — should be valid.
    new["versioning"] = {"semver": "2.0.0"}
    ok = check_compatibility(old, new)
    assert ok.is_breaking is True
    assert ok.semver_valid is True


# ---------------------------------------------------------------------------
# Test 7: bundle SHA is stable for identical content and changes when a
# manifest is edited.
# ---------------------------------------------------------------------------
def test_checksum_round_trip(tmp_path: Path) -> None:
    root = _make_contracts_root(tmp_path)
    _write_schema(root, "memory.write.v1.json")
    p = _write_manifest(
        root, "memory.write.v1.yaml", topic="memory.write.v1", schema_file="memory.write.v1.json"
    )
    sha1 = manifest_bundle_sha(root)
    sha2 = manifest_bundle_sha(root)
    assert sha1 == sha2

    items = collect_artifact_checksums(root)
    paths = [rel for rel, _ in items]
    assert "manifests/memory.write.v1.yaml" in paths
    assert "schemas/memory.write.v1.json" in paths

    # Edit and confirm bundle SHA shifts.
    p.write_text(
        p.read_text(encoding="utf-8") + "\n# trailing comment\n",
        encoding="utf-8",
    )
    sha3 = manifest_bundle_sha(root)
    assert sha3 != sha1


# ---------------------------------------------------------------------------
# Test 8: codegen flags are committed verbatim — guards against accidental
# mutation of the deterministic-output contract.
# ---------------------------------------------------------------------------
def test_datamodel_codegen_flags_verbatim() -> None:
    flags = DATAMODEL_CODEGEN_FLAGS
    # The exact pinned set per design doc Decision 2.
    assert "--input-file-type" in flags
    assert "jsonschema" in flags
    assert "--target-python-version" in flags
    assert "3.13" in flags
    assert "--output-model-type" in flags
    assert "pydantic_v2.BaseModel" in flags
    assert "--use-schema-description" in flags
    assert "--use-field-description" in flags
    assert "--use-default" in flags
    assert "--strict-nullable" in flags
    assert "--disable-timestamp" in flags  # critical for no-diff CI gate

    # Sanity: parse_semver companion.
    assert parse_semver("1.2.3") == (1, 2, 3)
