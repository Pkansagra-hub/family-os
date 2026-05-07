"""MS-2.5 Epic 2.5.3 — BridgeRuntime.from_registry tests.

No mocks: real on-disk contracts tree backed by the real meta-schema.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from bridge.runtime import BridgeRuntime, Role, Transport
from bridge.runtime_errors import (
    ManifestValidationError,
    OfflineError,
    UnboundContractError,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
REAL_META = REPO_ROOT / "bridge" / "contracts" / "_meta"

VALID_MANIFEST = """\
topic: memory.write.v1
direction: k1_to_k0
owner_team: k0
producer:
  kernel: k1
consumer:
  kernel: k0
schema: schemas/memory.write.v1.json
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
  description: Persist a memory atom into K0 episodic storage via P02.
sla:
  latency_p99_ms: 250
  throughput_per_sec: 50
versioning:
  semver: 1.0.0
  compat: compatible
status: active
"""


def _make_contracts(tmp_path: Path, *, manifest: str | None = VALID_MANIFEST) -> Path:
    root = tmp_path / "contracts"
    (root / "_meta").mkdir(parents=True)
    shutil.copyfile(
        REAL_META / "manifest.schema.json",
        root / "_meta" / "manifest.schema.json",
    )
    (root / "manifests").mkdir()
    (root / "schemas").mkdir()
    (root / "schemas" / "memory.write.v1.json").write_text(
        '{"$schema": "https://json-schema.org/draft/2020-12/schema",\n'
        ' "$id": "x", "type": "object"}\n',
        encoding="utf-8",
    )
    if manifest is not None:
        (root / "manifests" / "memory.write.v1.yaml").write_text(manifest, encoding="utf-8")
    return root


# ---------------------------------------------------------------------------
# Test 1: empty registry yields a runtime with no manifests, slots None.
# ---------------------------------------------------------------------------
def test_from_registry_empty(tmp_path: Path) -> None:
    root = _make_contracts(tmp_path, manifest=None)
    rt = BridgeRuntime.from_registry(contracts_path=root, role=Role.K0)
    assert rt.role is Role.K0
    assert rt.manifests == ()
    assert rt.command is None
    assert rt.query is None
    assert rt.sse is None
    assert rt.obs is None
    assert rt.gateway is None


# ---------------------------------------------------------------------------
# Test 2: valid manifest is loaded and surfaced for the relevant role.
# ---------------------------------------------------------------------------
def test_from_registry_loads_manifest_for_role(tmp_path: Path) -> None:
    root = _make_contracts(tmp_path)
    rt_k0 = BridgeRuntime.from_registry(contracts_path=root, role=Role.K0)
    rt_k1 = BridgeRuntime.from_registry(contracts_path=root, role=Role.K1)
    assert len(rt_k0.manifests) == 1  # consumer.kernel == k0
    assert len(rt_k1.manifests) == 1  # producer.kernel == k1
    assert rt_k0.manifests[0].topic == "memory.write.v1"


# ---------------------------------------------------------------------------
# Test 3: invalid manifest raises ManifestValidationError (runtime-side).
# ---------------------------------------------------------------------------
def test_from_registry_rejects_invalid(tmp_path: Path) -> None:
    bad = "topic: BAD\ndirection: k1_to_k0\n"
    root = _make_contracts(tmp_path, manifest=bad)
    with pytest.raises(ManifestValidationError):
        BridgeRuntime.from_registry(contracts_path=root, role=Role.K0)


# ---------------------------------------------------------------------------
# Test 4: explicit transport is preserved on the runtime.
# ---------------------------------------------------------------------------
def test_from_registry_preserves_transport(tmp_path: Path) -> None:
    root = _make_contracts(tmp_path)

    class _Marker(Transport):
        pass

    marker = _Marker()
    rt = BridgeRuntime.from_registry(contracts_path=root, role=Role.K1, transport=marker)
    assert rt.transport is marker


# ---------------------------------------------------------------------------
# Test 5: BridgeRuntime is frozen — slots cannot be reassigned.
# ---------------------------------------------------------------------------
def test_runtime_is_frozen(tmp_path: Path) -> None:
    root = _make_contracts(tmp_path, manifest=None)
    rt = BridgeRuntime.from_registry(contracts_path=root, role=Role.K0)
    with pytest.raises(Exception):  # noqa: BLE001
        rt.role = Role.K1  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Test 6: error class hierarchy is intact (importable + distinct types).
# ---------------------------------------------------------------------------
def test_runtime_error_classes() -> None:
    assert issubclass(UnboundContractError, RuntimeError)
    assert issubclass(ManifestValidationError, ValueError)
    assert issubclass(OfflineError, RuntimeError)
    assert UnboundContractError is not OfflineError
