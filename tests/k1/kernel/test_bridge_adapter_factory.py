"""MS-3b Epic 3b.5 \u2014 ``SinkBridgeAdapter`` no longer imports LocalOutbox directly.

These tests guard the kernel/bridge wall: the adapter must reach the
outbox only through the ``bridge.client.create_sink_bridge_client``
public seam.
"""

from __future__ import annotations

import ast
from pathlib import Path

from k1.kernel.adapters.bridge_adapter import SinkBridgeAdapter


def test_sink_bridge_adapter_does_not_import_local_outbox():
    src = Path("k1/kernel/adapters/bridge_adapter.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    forbidden = "bridge.sync.local_outbox"
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            assert mod != forbidden, (
                f"SinkBridgeAdapter must not import {forbidden}; "
                "use bridge.client.create_sink_bridge_client() instead."
            )
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name != forbidden, (
                    f"SinkBridgeAdapter must not import {forbidden}; "
                    "use bridge.client.create_sink_bridge_client() instead."
                )


def test_sink_bridge_adapter_constructs_via_factory(tmp_path: Path):
    adapter = SinkBridgeAdapter(outbox_path=tmp_path / "ob.db")
    client = adapter.get_client()
    # Sanity: SinkBridgeClient is offline by definition.
    assert adapter.is_connected() is False
    assert client is not None
    # Underlying outbox is a LocalOutbox even though the adapter never
    # imported it directly \u2014 the factory wired it for us.
    assert type(adapter._outbox).__name__ == "LocalOutbox"


def test_sink_bridge_adapter_outbox_persists_enqueue(tmp_path: Path):
    """End-to-end: factory-built client enqueues into the wired outbox."""
    import asyncio

    adapter = SinkBridgeAdapter(outbox_path=tmp_path / "ob.db")
    client = adapter.get_client()

    async def _go() -> None:
        await client.submit_command(
            topic="memory.write.v1",
            body={"text": "hi"},
        )

    asyncio.run(_go())
    assert adapter._outbox.pending_count() == 1
