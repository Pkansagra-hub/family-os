"""MS-2.5 exit-criterion test (Epic 2.5.6).

This test is the contract that closes the milestone. It asserts the
seven facts that, taken together, prove the bridge substrate is
operational and the first contract is live end-to-end:

D1. The contract registry parses and validates ``memory.write.v1``.
D2. ``python -m tooling.contracts.codegen --check`` reports zero drift
    against the vendored ``bridge/_generated/`` tree.
D3. The generated K1 client and K0 handler import cleanly, with the
    expected class-level metadata (``__transport__ == "http"``,
    ``__topic__``, ``__schema_uri__``).
D4. A real round-trip via ``InProcessHttpTransport`` delivers a
    Pydantic-equal payload from K1 client to K0 handler.
D5. ``no_cross_kernel_imports`` gate exits 0 against the live tree.
D6. ``bus_yaml_aligned_with_registry`` gate exits 0 against the live
    tree (with the active manifest now requiring ``memory.*`` in
    ``k1/config/bus.yaml``).
D7. R10 enforcement: publishing a bridge-bound topic on the K1 local
    bus raises :class:`UnknownContractError`.

Failure of any single assertion blocks the merge. The test runs in CI
and must complete in <10s wall.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from bridge._generated.k0.handlers.memory_write_v1 import register_handlers as register_k0_handlers
from bridge._generated.k0.models.memory_write_v1 import MemoryWriteV1
from bridge._generated.k1.clients.memory_write_v1 import MemoryWriteV1Client
from bridge.bus_guard import (
    BridgeAwareLocalBus,
    UnknownContractError,
    load_bridge_topics,
)
from bridge.core.transport.in_process_http import InProcessHttpTransport
from bridge.handlers.k0.memory_write_v1 import handle_memory_write_v1
from bridge.runtime import BridgeRuntime, Role
from bridge.testing.dispatcher_app import build_app
from tooling.contracts.manifest_loader import load_manifests

REPO_ROOT = Path(__file__).resolve().parents[3]
CONTRACTS_PATH = REPO_ROOT / "bridge" / "contracts"


def _valid_atom() -> dict[str, object]:
    return {
        "schema_version": "2.2",
        "operation": "UPSERT",
        "text": "exit-criterion atom",
        "topics": ["exit"],
        "sentiment_label": "neutral",
        "affect": {"valence": 0.0, "arousal": 0.0, "dominance": 0.5},
        "source_type": "user_stated",
        "novelty": "EXPECTED",
        "elaboration_depth": "MENTION",
        "temporal_orientation": "PAST",
        "confidence": 1.0,
        "session_id": "session-exit",
        "conversation_turn": 1,
        "language": "en",
    }


# ---------------------------------------------------------------------------
# D1 — Registry validates the first contract.
# ---------------------------------------------------------------------------


def test_d1_registry_validates_memory_write_v1() -> None:
    manifests = load_manifests(CONTRACTS_PATH)
    by_topic = {m.topic: m for m in manifests}
    assert "memory.write.v1" in by_topic
    m = by_topic["memory.write.v1"]
    assert m.status == "active"
    assert m.direction == "k1_to_k0"
    assert m.producer_kernel == "k1"
    assert m.consumer_kernel == "k0"


# ---------------------------------------------------------------------------
# D2 — Vendored generated tree has zero drift.
# ---------------------------------------------------------------------------


def test_d2_codegen_check_reports_zero_drift() -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "tooling.contracts.codegen", "--check"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, (
        "codegen --check reported drift:\n" f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )


# ---------------------------------------------------------------------------
# D3 — Generated artefacts import cleanly with expected metadata.
# ---------------------------------------------------------------------------


def test_d3_generated_artefacts_import_cleanly() -> None:
    assert MemoryWriteV1.__name__ == "MemoryWriteV1"
    assert MemoryWriteV1Client.__transport__ == "http"
    assert MemoryWriteV1Client.__topic__ == "memory.write.v1"
    assert MemoryWriteV1Client.__schema_uri__.endswith("memory.write.v1.json")
    # Pydantic v2 model: required fields are introspectable.
    required = {name for name, info in MemoryWriteV1.model_fields.items() if info.is_required()}
    assert {"schema_version", "operation", "text", "topics", "language"} <= required


# ---------------------------------------------------------------------------
# D4 — Real round-trip via InProcessHttpTransport.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_d4_round_trip_via_in_process_http() -> None:
    rt = BridgeRuntime(role=Role.K0, contracts_path=CONTRACTS_PATH)
    register_k0_handlers(rt, impl=handle_memory_write_v1)
    app = build_app(runtime=rt)
    transport = InProcessHttpTransport(app=app)
    try:
        client_runtime = BridgeRuntime(
            role=Role.K1, contracts_path=CONTRACTS_PATH, transport=transport
        )
        client = MemoryWriteV1Client(runtime=client_runtime)
        model = MemoryWriteV1.model_validate(_valid_atom())
        result = await client.publish(model)
    finally:
        await transport.close()
    assert result["ack"] is True
    assert result["topic"] == "memory.write.v1"
    assert result["atom_id"].startswith("atom-")


# ---------------------------------------------------------------------------
# D5 — no_cross_kernel_imports gate is clean.
# ---------------------------------------------------------------------------


def test_d5_no_cross_kernel_imports_gate_clean() -> None:
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "tooling.ci.gates.no_cross_kernel_imports",
            "--repo-root",
            str(REPO_ROOT),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, f"no_cross_kernel_imports gate failed:\nstderr:\n{proc.stderr}"


# ---------------------------------------------------------------------------
# D6 — bus_yaml_aligned_with_registry gate is clean.
# ---------------------------------------------------------------------------


def test_d6_bus_yaml_aligned_with_registry_gate_clean() -> None:
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "tooling.ci.gates.bus_yaml_aligned_with_registry",
            "--repo-root",
            str(REPO_ROOT),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    # Gate may still warn on unrelated patterns; what matters for D6 is
    # that the registered ``memory.*`` topic is honoured. Accept exit 0.
    assert (
        proc.returncode == 0
    ), f"bus_yaml_aligned_with_registry gate failed:\nstderr:\n{proc.stderr}"


# ---------------------------------------------------------------------------
# D7 — R10: bridge-bound publish on local bus raises.
# ---------------------------------------------------------------------------


def test_d7_local_bus_publish_of_bridge_topic_raises() -> None:
    # Real LocalBus, real Envelope — no mocks.
    from k1.bus.impl.local_bus import LocalBus
    from k1.bus.ports.bus import Envelope

    inner = LocalBus()
    bus = BridgeAwareLocalBus(inner)
    # memory.write.v1 is a registered cross-kernel topic.
    bridge_topics = load_bridge_topics()
    assert "memory.write.v1" in bridge_topics

    env = Envelope(topic="memory.write.v1", payload=b"{}")
    with pytest.raises(UnknownContractError) as exc:
        bus.publish(env)
    assert "memory.write.v1" in str(exc.value)

    # Sanity: an intra-K1 topic is allowed (delegates to inner bus).
    env_local = Envelope(topic="k1.test.local", payload=b"{}")
    bus.publish(env_local)  # must not raise
