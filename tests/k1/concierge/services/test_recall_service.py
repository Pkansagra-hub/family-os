"""MS-3c — ``RecallService`` round-trips through the typed paired-contract surface.

Validates two layers in one place:

1. ``RecallService(query=runtime.query)`` builds a typed
   ``RecallRequestV1`` from concierge-shaped kwargs and routes it
   through the in-process bridge dispatcher.
2. The concierge call site never sees raw dicts — the response comes
   back as a typed ``RecallResponseV1`` with structured hits.

Offline-graceful fallback (``query=None``) is also covered: callers
must be able to ``response.hits`` without a try/except.
"""

from __future__ import annotations

import pathlib
from typing import Any

import pytest

from bridge._generated.k0.handlers.recall_request_v1 import (
    register_handlers as register_k0_recall_handlers,
)
from bridge._generated.k0.models.recall_request_v1 import RecallRequestV1 as K0RecallRequestV1
from bridge._generated.k1.models.recall_response_v1 import RecallResponseV1
from bridge.core.transport.in_process_http import InProcessHttpTransport
from bridge.runtime import BridgeRuntime, Role
from bridge.testing.dispatcher_app import build_app
from k1.concierge.services.recall_service import RecallService

CONTRACTS_PATH = pathlib.Path(__file__).resolve().parents[4] / "bridge" / "contracts"


pytestmark = pytest.mark.asyncio


async def test_recall_service_offline_returns_empty_response() -> None:
    """``RecallService(None)`` must yield an empty typed response."""
    svc = RecallService(query=None)
    response = await svc.recall("anything", trace_id="off-1")
    assert isinstance(response, RecallResponseV1)
    assert response.hits == []
    assert response.total == 0
    assert response.truncated is False
    assert response.trace_id == "off-1"


async def test_recall_service_routes_through_typed_paired_contract() -> None:
    """Round-trip K1 RecallService -> in-process HTTP -> K0 handler."""
    captured: dict[str, Any] = {}

    async def fake_recall(payload: K0RecallRequestV1) -> dict[str, Any]:
        captured["payload"] = payload
        return {
            "hits": [
                {
                    "atom_id": "atom-svc-1",
                    "content": {"text": "service hit"},
                    "score": 0.75,
                    "source": "test",
                    "selector_type": payload.selectors[0].type.value,
                }
            ],
            "total": 1,
            "latency_ms": 3,
            "truncated": False,
            "trace_id": payload.trace_id or "",
        }

    rt_k0 = BridgeRuntime(role=Role.K0, contracts_path=CONTRACTS_PATH)
    register_k0_recall_handlers(rt_k0, impl=fake_recall)
    app = build_app(runtime=rt_k0)
    transport = InProcessHttpTransport(app=app)

    try:
        rt_k1 = BridgeRuntime.from_registry(
            contracts_path=CONTRACTS_PATH,
            role=Role.K1,
            transport=transport,
        )
        # The runtime exposes the typed namespace bag at ``.query``.
        assert rt_k1.query is not None
        assert hasattr(rt_k1.query, "recall_request_v1")

        svc = RecallService(query=rt_k1.query)
        response = await svc.recall(
            "what did we discuss?",
            space_id="space-svc",
            memory_types=["semantic"],
            max_results=3,
            trace_id="trace-svc-1",
        )
    finally:
        await transport.close()

    assert isinstance(response, RecallResponseV1)
    assert response.total == 1
    assert response.trace_id == "trace-svc-1"
    assert len(response.hits) == 1
    hit = response.hits[0]
    assert hit.atom_id == "atom-svc-1"
    assert hit.score == pytest.approx(0.75)
    # Handler observed a real K0-side Pydantic body (each kernel owns its copy).
    assert isinstance(captured["payload"], K0RecallRequestV1)
    assert captured["payload"].space_id == "space-svc"
    assert captured["payload"].max_results == 3
    assert captured["payload"].vector_query == "what did we discuss?"
