"""MS-4 exit-criterion test (Epic 4.3).

Locks the two MS-4 deliverables in a single pytest run:

1. **Codec negotiation works end-to-end**: a generated K1 client carries
   the manifest-declared codec on its class (``__codec__``,
   ``__codecs_allowed__``, ``__codec_negotiation__``); the codec
   registry resolves the same names; ``HttpTransport.publish(codec=...)``
   wraps non-JSON bodies with the canonical ``{_codec, _b64}`` shape
   inside a JSON envelope. The signing path (canonical JSON of the
   envelope) is unchanged.
2. **Adapter LOC budget gate enforces**: the
   ``tooling.ci.gates.adapter_loc_budget`` subprocess returns 0 against
   the real workspace and 1 when fed an over-budget fixture.

If either deliverable regresses, this test fails and MS-4 is not done.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import httpx
import pytest
from pydantic import BaseModel

from bridge._generated.k1.clients.memory_write_v1 import MemoryWriteV1Client
from bridge.core.codecs import (
    BODY_WRAPPER_B64_KEY,
    BODY_WRAPPER_CODEC_KEY,
    CodecRegistry,
    MsgpackCodec,
)
from bridge.core.envelope_builder import BridgeConfig, EnvelopeBuilder
from bridge.core.signing import HmacSigning
from bridge.core.transport import HttpTransport, TransportConfig

REPO_ROOT = Path(__file__).resolve().parents[3]


# ---------------------------------------------------------------------------
# Deliverable 1: codec negotiation works end-to-end
# ---------------------------------------------------------------------------


class _Body(BaseModel):
    schema_version: str = "1.0"
    text: str
    n: int = 0


def test_generated_client_carries_codec_constants() -> None:
    """Generated client constants align with what the registry can resolve."""
    reg = CodecRegistry()
    # The manifest default for memory.write.v1 today is JSON; constants
    # must mirror the manifest exactly.
    assert MemoryWriteV1Client.__codec__ == "json"
    assert MemoryWriteV1Client.__codec__ in [c.name for c in reg.codecs_allowed({"codec": "json"})]
    assert MemoryWriteV1Client.__codec_negotiation__ in {
        "fixed",
        "client_choice_in_allowed",
    }
    # __codecs_allowed__ is a tuple so it is hashable and comparable.
    assert isinstance(MemoryWriteV1Client.__codecs_allowed__, tuple)
    for name in MemoryWriteV1Client.__codecs_allowed__:
        reg.get(name)  # raises if unknown


@pytest.mark.asyncio
async def test_msgpack_publish_wraps_body_in_canonical_json_envelope() -> None:
    """The end-to-end wire shape MS-4 promises: outer JSON envelope, body wrapped."""
    captured: dict = {}

    def handle(req: httpx.Request) -> httpx.Response:
        # Outer envelope is canonical JSON for signing; we just parse it.
        captured["envelope"] = json.loads(req.content.decode("utf-8"))
        captured["content_type"] = req.headers.get("Content-Type")
        captured["accept"] = req.headers.get("Accept")
        return httpx.Response(200, json={"ok": True})

    cfg = TransportConfig(base_url="http://k0.test")
    builder = EnvelopeBuilder(
        config=BridgeConfig(tenant_id="t1", space_id="s1", device_id="d1"),
        signer=HmacSigning(secret=b"\x00" * 32, key_id="dev:test"),
    )
    transport = HttpTransport(config=cfg, envelope_builder=builder)
    transport._client = httpx.AsyncClient(  # type: ignore[attr-defined]
        transport=httpx.MockTransport(handle), base_url=cfg.base_url
    )
    try:
        await transport.publish(
            topic="memory.write.v1",
            schema_uri="bridge://contracts/schemas/memory.write.v1.json",
            payload=_Body(text="hello", n=11),
            codec="msgpack",
        )
    finally:
        await transport.close()

    env = captured["envelope"]
    # Outer envelope: still JSON, still signed (sig field present).
    assert captured["content_type"] == "application/json"
    assert "sig" in env and "sig_alg" in env and "sig_kid" in env
    # Body field is the canonical wrapped shape, NOT raw msgpack bytes.
    body = env["body"]
    assert set(body.keys()) == {BODY_WRAPPER_CODEC_KEY, BODY_WRAPPER_B64_KEY}
    assert body[BODY_WRAPPER_CODEC_KEY] == "msgpack"
    # Decoded wrapped body matches the original payload.
    import base64

    raw = base64.b64decode(body[BODY_WRAPPER_B64_KEY])
    assert MsgpackCodec().decode(raw) == {
        "schema_version": "1.0",
        "text": "hello",
        "n": 11,
    }
    # Accept header advertises both msgpack and JSON fallback.
    assert "application/msgpack" in captured["accept"]
    assert "application/json" in captured["accept"]


# ---------------------------------------------------------------------------
# Deliverable 2: adapter LOC budget gate enforces
# ---------------------------------------------------------------------------


def _run_gate(repo_root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "tooling.ci.gates.adapter_loc_budget",
            "--repo-root",
            str(repo_root),
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO_ROOT,
    )


def test_adapter_loc_budget_gate_passes_at_head() -> None:
    """The budget gate is green at HEAD — captures the MS-4 baseline."""
    result = _run_gate(REPO_ROOT)
    assert result.returncode == 0, (
        f"adapter_loc_budget regressed at HEAD\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_adapter_loc_budget_gate_fails_when_over_budget(tmp_path: Path) -> None:
    """An over-budget fixture is rejected by the gate (exit 1)."""
    from tooling.ci.gates.adapter_loc_budget import (
        PER_FILE_SLOC_CAP,
        TOTAL_SLOC_BUDGET,
    )

    repo = tmp_path / "repo"
    adapters = repo / "k1" / "guard" / "adapters"
    adapters.mkdir(parents=True)
    per = PER_FILE_SLOC_CAP - 1
    n_files = (TOTAL_SLOC_BUDGET // per) + 2
    for i in range(n_files):
        (adapters / f"bridge_{i}.py").write_text("x = 1\n" * per, encoding="utf-8")
    result = _run_gate(repo)
    assert result.returncode == 1
    assert "exceeds budget" in result.stdout
