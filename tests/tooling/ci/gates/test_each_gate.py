"""Tests for individual CI gates and the orchestrator.

Each gate test:

* Builds a real on-disk fixture tree under ``tmp_path`` (no mocks).
* Invokes the gate via ``subprocess.run`` so the CLI surface is exercised
  end-to-end.
* Asserts the exit code and that key offending text appears in stderr or
  stdout.

These tests deliberately avoid running gates against the live repo — the
orchestrator smoke-runs them in CI; here we want surgical control over
clean vs. violating fixtures.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _make_minimal_repo(root: Path, *, with_bridge: bool = True) -> Path:
    """Create a minimal repo skeleton: empty k0, k1, bridge trees."""
    (root / "k0").mkdir()
    (root / "k0" / "__init__.py").write_text("", encoding="utf-8")
    (root / "k1").mkdir()
    (root / "k1" / "__init__.py").write_text("", encoding="utf-8")
    if with_bridge:
        (root / "bridge").mkdir()
        (root / "bridge" / "__init__.py").write_text("", encoding="utf-8")
        (root / "bridge" / "contracts").mkdir()
        (root / "bridge" / "contracts" / "_meta").mkdir()
        # Copy the real meta-schema so manifest validation works.
        repo_root = Path(__file__).resolve().parents[4]
        real_meta = repo_root / "bridge" / "contracts" / "_meta" / "manifest.schema.json"
        shutil.copy2(real_meta, root / "bridge" / "contracts" / "_meta" / "manifest.schema.json")
        (root / "bridge" / "contracts" / "manifests").mkdir()
        (root / "bridge" / "contracts" / "schemas").mkdir()
    # Provide a bus.yaml so the bus_yaml gate has something to read.
    (root / "k1" / "config").mkdir()
    (root / "k1" / "config" / "bus.yaml").write_text(
        "default_mode: RELAXED\ntiming_rules:\n  k1.local: STRICT\n",
        encoding="utf-8",
    )
    return root


def _run(
    module: str, *, repo_root: Path, extra: list[str] | None = None
) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, "-m", module, "--repo-root", str(repo_root)]
    if extra:
        cmd.extend(extra)
    real_repo = Path(__file__).resolve().parents[4]
    return subprocess.run(
        cmd,
        cwd=str(real_repo),  # so ``tooling.ci`` resolves
        capture_output=True,
        text=True,
        check=False,
    )


# ---------------------------------------------------------------------------
# no_cross_kernel_imports
# ---------------------------------------------------------------------------


class TestNoCrossKernelImports:
    GATE = "tooling.ci.gates.no_cross_kernel_imports"

    def test_passes_on_clean_fixture(self, tmp_path: Path) -> None:
        _make_minimal_repo(tmp_path)
        # k0 imports only stdlib + sibling k0 modules
        (tmp_path / "k0" / "ok.py").write_text(
            "import os\nfrom k0 import config\n", encoding="utf-8"
        )
        (tmp_path / "k0" / "config.py").write_text("", encoding="utf-8")
        result = _run(self.GATE, repo_root=tmp_path)
        assert result.returncode == 0, result.stderr
        assert "OK (0 violations)" in result.stderr

    def test_fails_on_violating_fixture_with_path_in_stderr(self, tmp_path: Path) -> None:
        _make_minimal_repo(tmp_path)
        (tmp_path / "k0" / "leak.py").write_text("from k1 import some_module\n", encoding="utf-8")
        result = _run(self.GATE, repo_root=tmp_path)
        assert result.returncode == 1
        assert "k0/leak.py" in result.stdout
        assert "k1" in result.stdout
        assert "FAIL" in result.stderr

    def test_allowlist_marker_suppresses_violation(self, tmp_path: Path) -> None:
        _make_minimal_repo(tmp_path)
        (tmp_path / "k1" / "compat.py").write_text(
            "from k0 import legacy  # noqa: cross-kernel — MS-3 remediation\n",
            encoding="utf-8",
        )
        result = _run(self.GATE, repo_root=tmp_path)
        assert result.returncode == 0, result.stderr


# ---------------------------------------------------------------------------
# bridge_not_imported_from_kernels
# ---------------------------------------------------------------------------


class TestBridgeNotImportedFromKernels:
    GATE = "tooling.ci.gates.bridge_not_imported_from_kernels"

    def test_passes_on_clean_fixture(self, tmp_path: Path) -> None:
        _make_minimal_repo(tmp_path)
        (tmp_path / "k1" / "ok.py").write_text(
            "from bridge.client import HttpBridgeClient\n"
            "from bridge.contracts import something\n"
            "from bridge.ports import IKernelCommandPort\n",
            encoding="utf-8",
        )
        result = _run(self.GATE, repo_root=tmp_path)
        assert result.returncode == 0, result.stderr

    def test_fails_when_kernel_imports_bridge_core(self, tmp_path: Path) -> None:
        _make_minimal_repo(tmp_path)
        (tmp_path / "k1" / "leak.py").write_text(
            "from bridge.core.envelope_builder import EnvelopeBuilder\n",
            encoding="utf-8",
        )
        result = _run(self.GATE, repo_root=tmp_path)
        assert result.returncode == 1
        assert "k1/leak.py" in result.stdout
        assert "bridge.core" in result.stdout

    def test_allows_own_role_generated_subtree(self, tmp_path: Path) -> None:
        _make_minimal_repo(tmp_path)
        (tmp_path / "k1" / "client.py").write_text(
            "from bridge._generated.k1.clients.memory_write_v1 import MemoryWriteV1Client\n",
            encoding="utf-8",
        )
        result = _run(self.GATE, repo_root=tmp_path)
        assert result.returncode == 0, result.stderr

    def test_forbids_foreign_role_generated_subtree(self, tmp_path: Path) -> None:
        _make_minimal_repo(tmp_path)
        (tmp_path / "k1" / "leak.py").write_text(
            "from bridge._generated.k0.handlers.memory_write_v1 import register_handlers\n",
            encoding="utf-8",
        )
        result = _run(self.GATE, repo_root=tmp_path)
        assert result.returncode == 1
        assert "k1/leak.py" in result.stdout

    def test_allowlist_file_excludes_specific_lines(self, tmp_path: Path) -> None:
        _make_minimal_repo(tmp_path)
        (tmp_path / "k1" / "legacy.py").write_text(
            "x = 1\n" "from bridge.core.envelope_builder import CommandEnvelope\n",
            encoding="utf-8",
        )
        allow_dir = tmp_path / "tooling" / "ci" / "known_violations"
        allow_dir.mkdir(parents=True)
        (allow_dir / "bridge_imports.txt").write_text(
            "k1/legacy.py:2  # scheduled\n", encoding="utf-8"
        )
        result = _run(self.GATE, repo_root=tmp_path)
        assert result.returncode == 0, result.stderr


# ---------------------------------------------------------------------------
# manifest_implementation_bound
# ---------------------------------------------------------------------------


def _write_manifest(
    contracts_root: Path,
    *,
    topic: str,
    direction: str = "k1_to_k0",
    producer: str = "k1",
    consumer: str = "k0",
    status: str = "active",
    schema_name: str = "memory.write.v1.json",
) -> None:
    schema_path = contracts_root / "schemas" / schema_name
    schema_path.write_text(
        json.dumps({"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object"}),
        encoding="utf-8",
    )
    manifest_path = contracts_root / "manifests" / f"{topic}.yaml"
    manifest_path.write_text(
        textwrap.dedent(f"""
            topic: {topic}
            direction: {direction}
            owner_team: k0
            status: {status}
            producer:
              kernel: {producer}
            consumer:
              kernel: {consumer}
            schema: schemas/{schema_name}
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
              retention: P7D
              description: "Test manifest with at least forty characters of description text."
            sla:
              latency_p99_ms: 500
              throughput_per_sec: 100
            versioning:
              semver: 1.0.0
              compat: compatible
            checksums: {{}}
            """).strip() + "\n",
        encoding="utf-8",
    )


class TestManifestImplementationBound:
    GATE = "tooling.ci.gates.manifest_implementation_bound"

    def test_warns_when_generated_tree_is_empty(self, tmp_path: Path) -> None:
        _make_minimal_repo(tmp_path)
        _write_manifest(tmp_path / "bridge" / "contracts", topic="memory.write.v1")
        # No bridge/_generated/ tree -> day-one mode -> WARN tag.
        result = _run(self.GATE, repo_root=tmp_path, extra=["--warn-only"])
        # WARN mode: exit 0 but violations printed.
        assert result.returncode == 0, result.stderr
        assert "WARN(empty_generated)" in result.stdout
        assert "memory.write.v1" in result.stdout

    def test_passes_when_handler_exists(self, tmp_path: Path) -> None:
        _make_minimal_repo(tmp_path)
        _write_manifest(tmp_path / "bridge" / "contracts", topic="memory.write.v1")
        gen_h = tmp_path / "bridge" / "_generated" / "k0" / "handlers"
        gen_h.mkdir(parents=True)
        (gen_h / "memory_write_v1.py").write_text(
            "def register_handlers(*a, **k): ...\n", encoding="utf-8"
        )
        gen_c = tmp_path / "bridge" / "_generated" / "k1" / "clients"
        gen_c.mkdir(parents=True)
        (gen_c / "memory_write_v1.py").write_text(
            "class MemoryWriteV1Client: ...\n", encoding="utf-8"
        )
        result = _run(self.GATE, repo_root=tmp_path)
        assert result.returncode == 0, result.stderr

    def test_fails_when_handler_missing_and_tree_nonempty(self, tmp_path: Path) -> None:
        _make_minimal_repo(tmp_path)
        _write_manifest(tmp_path / "bridge" / "contracts", topic="memory.write.v1")
        # Make _generated non-empty but missing the handler.
        gen = tmp_path / "bridge" / "_generated" / "k0" / "models"
        gen.mkdir(parents=True)
        (gen / "other.py").write_text("", encoding="utf-8")
        result = _run(self.GATE, repo_root=tmp_path)
        assert result.returncode == 1
        assert "memory.write.v1" in result.stdout
        assert "[FAIL]" in result.stdout


# ---------------------------------------------------------------------------
# schema_checksum_stable
# ---------------------------------------------------------------------------


class TestSchemaChecksumStable:
    GATE = "tooling.ci.gates.schema_checksum_stable"

    def test_passes_when_checksums_block_is_empty(self, tmp_path: Path) -> None:
        _make_minimal_repo(tmp_path)
        _write_manifest(tmp_path / "bridge" / "contracts", topic="memory.write.v1")
        result = _run(self.GATE, repo_root=tmp_path)
        assert result.returncode == 0, result.stderr

    def test_update_populates_block_then_repeat_passes(self, tmp_path: Path) -> None:
        _make_minimal_repo(tmp_path)
        _write_manifest(tmp_path / "bridge" / "contracts", topic="memory.write.v1")
        upd = _run(self.GATE, repo_root=tmp_path, extra=["--update"])
        assert upd.returncode == 0
        assert "updated" in upd.stdout
        # Now a clean run must pass.
        result = _run(self.GATE, repo_root=tmp_path)
        assert result.returncode == 0, result.stderr

    def test_fails_when_embedded_checksum_lies(self, tmp_path: Path) -> None:
        _make_minimal_repo(tmp_path)
        _write_manifest(tmp_path / "bridge" / "contracts", topic="memory.write.v1")
        # Inject a bad checksum.
        manifest_path = tmp_path / "bridge" / "contracts" / "manifests" / "memory.write.v1.yaml"
        manifest_path.write_text(
            manifest_path.read_text(encoding="utf-8").replace(
                "checksums: {}",
                "checksums:\n  schema_sha256: deadbeef\n  manifest_sha256: badf00d\n",
            ),
            encoding="utf-8",
        )
        result = _run(self.GATE, repo_root=tmp_path)
        assert result.returncode == 1
        assert "schema_sha256 mismatch" in result.stdout


# ---------------------------------------------------------------------------
# bus_yaml_aligned_with_registry
# ---------------------------------------------------------------------------


class TestBusYamlAlignedWithRegistry:
    GATE = "tooling.ci.gates.bus_yaml_aligned_with_registry"

    def test_passes_when_no_cross_kernel_prefixes(self, tmp_path: Path) -> None:
        _make_minimal_repo(tmp_path)
        # Default fixture's bus.yaml only has k1.local; no cross-kernel prefix.
        result = _run(self.GATE, repo_root=tmp_path)
        assert result.returncode == 0, result.stderr

    def test_fails_when_cross_kernel_prefix_lacks_manifest(self, tmp_path: Path) -> None:
        _make_minimal_repo(tmp_path)
        (tmp_path / "k1" / "config" / "bus.yaml").write_text(
            "default_mode: RELAXED\ntiming_rules:\n  memory.write: STRICT\n",
            encoding="utf-8",
        )
        result = _run(self.GATE, repo_root=tmp_path)
        assert result.returncode == 1
        assert "memory.write" in result.stdout
        assert "FAIL" in result.stderr

    def test_passes_when_cross_kernel_prefix_has_matching_manifest(self, tmp_path: Path) -> None:
        _make_minimal_repo(tmp_path)
        (tmp_path / "k1" / "config" / "bus.yaml").write_text(
            "default_mode: RELAXED\ntiming_rules:\n  memory.write: STRICT\n",
            encoding="utf-8",
        )
        _write_manifest(
            tmp_path / "bridge" / "contracts",
            topic="memory.write.v1",
            status="proposed",
        )
        result = _run(self.GATE, repo_root=tmp_path)
        assert result.returncode == 0, result.stderr


# ---------------------------------------------------------------------------
# single_ibridge_port_definition
# ---------------------------------------------------------------------------


class TestSingleIBridgePortDefinition:
    GATE = "tooling.ci.gates.single_ibridge_port_definition"

    def test_passes_when_no_definition_exists(self, tmp_path: Path) -> None:
        _make_minimal_repo(tmp_path)
        (tmp_path / "bridge" / "ports.py").write_text(
            "class IKernelCommandPort: ...\nclass IKernelQueryPort: ...\n",
            encoding="utf-8",
        )
        result = _run(self.GATE, repo_root=tmp_path)
        assert result.returncode == 0, result.stderr

    def test_fails_when_class_definition_re_added(self, tmp_path: Path) -> None:
        _make_minimal_repo(tmp_path)
        (tmp_path / "bridge" / "umbrella.py").write_text(
            "class IBridgePort:\n    pass\n", encoding="utf-8"
        )
        result = _run(self.GATE, repo_root=tmp_path)
        assert result.returncode == 1
        assert "bridge/umbrella.py" in result.stdout
        assert "IBridgePort" in result.stdout

    def test_fails_when_subclass_uses_old_base(self, tmp_path: Path) -> None:
        _make_minimal_repo(tmp_path)
        (tmp_path / "k1" / "legacy.py").write_text(
            "class IBridgePort: ...\n" "class MyPort(IBridgePort):\n    pass\n",
            encoding="utf-8",
        )
        result = _run(self.GATE, repo_root=tmp_path)
        assert result.returncode == 1
        assert "subclasses IBridgePort" in result.stdout


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


class TestRunAllGates:
    ORCH = "tooling.ci.run_all_gates"

    def test_exits_zero_when_all_green(self, tmp_path: Path) -> None:
        _make_minimal_repo(tmp_path)
        result = _run(self.ORCH, repo_root=tmp_path, extra=["--warn-all"])
        assert result.returncode == 0, result.stderr
        # JSON summary must be the last stderr line.
        last = [line for line in result.stderr.splitlines() if line.startswith("{")][-1]
        summary = json.loads(last)
        assert summary["failed"] == []
        assert summary["crashed"] == []
        assert {g["name"] for g in summary["gates"]} == {
            "no_cross_kernel_imports",
            "bridge_not_imported_from_kernels",
            "manifest_implementation_bound",
            "schema_checksum_stable",
            "bus_yaml_aligned_with_registry",
            "single_ibridge_port_definition",
            "bridge_client_construction_via_runtime_only",
            "degraded_mode_derived_only",
            "adapter_loc_budget",
        }

    def test_aggregates_failures_when_two_gates_fail(self, tmp_path: Path) -> None:
        _make_minimal_repo(tmp_path)
        # Trigger no_cross_kernel_imports
        (tmp_path / "k0" / "leak.py").write_text("from k1 import x\n", encoding="utf-8")
        # Trigger single_ibridge_port_definition
        (tmp_path / "bridge" / "umbrella.py").write_text(
            "class IBridgePort:\n    pass\n", encoding="utf-8"
        )
        result = _run(self.ORCH, repo_root=tmp_path, extra=["--enforce-all"])
        assert result.returncode == 1
        assert "::error::" in result.stderr
        last = [line for line in result.stderr.splitlines() if line.startswith("{")][-1]
        summary = json.loads(last)
        assert "no_cross_kernel_imports" in summary["failed"]
        assert "single_ibridge_port_definition" in summary["failed"]
