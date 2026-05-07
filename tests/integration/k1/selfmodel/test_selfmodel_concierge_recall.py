"""M5.E2.I4 — selfmodel <-> k1.concierge (recall) seam.

Per IMPLEMENTATION_PLAN_SELF_MODEL.md M5.E2.I4:

    Validate: recall_memory tool now returns CitationPack;
    back-compat shim keeps list[dict] behavior available for
    unmigrated callers.

The wiring is purely constructor-level: install a
``RecallCitationWrapper`` as ``ToolContext.recall_fn``. The
concierge's ``execute_recall_memory`` then sees citation-packed
output without any of its own code changing.
"""

from __future__ import annotations

import pytest

from k1.concierge.tools.implementations import (
    ToolContext,
    execute_recall_memory,
)
from k1.selfmodel.adapters.recall_citation_wrapper import RecallCitationWrapper

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------
def _fake_inner_sync(query, memory_types, max_results):
    return [
        {"id": "m1", "text": f"row for {query}", "score": 0.9},
        {"id": "m2", "text": "another row", "score": 0.7},
    ]


async def _fake_inner_async(query, memory_types, max_results):
    return [{"id": "a1", "text": f"async {query}"}]


def _ctx(recall_fn) -> ToolContext:
    return ToolContext(
        session_manager=None,
        actor="front",
        recall_fn=recall_fn,
    )


def _args(query: str = "what did I do yesterday") -> dict:
    return {"query": query, "memory_types": ["episodic"], "max_results": 5}


# =====================================================================
# Pack mode (default) — concierge sees a CitationPack envelope
# =====================================================================
async def test_pack_mode_emits_citation_pack_through_recall_tool() -> None:
    wrapper = RecallCitationWrapper(inner=_fake_inner_sync, actor_id="actor:liam")
    ctx = _ctx(wrapper)

    out = await execute_recall_memory(_args(), ctx)
    assert out.status == "ok"
    # The tool wraps recall_fn output as {"memories": result, "count": ...}.
    # When the wrapper is installed, "memories" is a single-element
    # list containing the citation_pack envelope.
    memories = out.data["memories"]
    assert isinstance(memories, list) and len(memories) == 1
    envelope = memories[0]
    assert "citation_pack" in envelope
    assert "memories" in envelope  # inner rows preserved (back-compat)

    pack = envelope["citation_pack"]
    assert pack["actor_id"] == "actor:liam"
    assert isinstance(pack["citations"], list)
    assert len(pack["citations"]) == 2
    # Inner rows preserved as-is.
    assert envelope["memories"][0]["id"] == "m1"
    assert envelope["memories"][1]["id"] == "m2"


async def test_pack_mode_supports_async_inner_recall_fn() -> None:
    wrapper = RecallCitationWrapper(inner=_fake_inner_async, actor_id="actor:liam")
    ctx = _ctx(wrapper)

    out = await execute_recall_memory(_args("from yesterday"), ctx)
    assert out.status == "ok"
    envelope = out.data["memories"][0]
    assert envelope["citation_pack"]["actor_id"] == "actor:liam"
    assert envelope["memories"] == [{"id": "a1", "text": "async from yesterday"}]


# =====================================================================
# Passthrough mode (back-compat shim) — unwrapped list[dict]
# =====================================================================
async def test_passthrough_mode_returns_raw_rows() -> None:
    wrapper = RecallCitationWrapper(
        inner=_fake_inner_sync,
        actor_id="actor:liam",
        mode="passthrough",
    )
    ctx = _ctx(wrapper)

    out = await execute_recall_memory(_args(), ctx)
    assert out.status == "ok"
    rows = out.data["memories"]
    assert isinstance(rows, list)
    assert all("citation_pack" not in r for r in rows)
    assert rows[0]["id"] == "m1"
    assert rows[1]["id"] == "m2"


# =====================================================================
# Empty inner result — no crash, citations list empty
# =====================================================================
async def test_pack_mode_handles_empty_inner_result() -> None:
    wrapper = RecallCitationWrapper(
        inner=lambda q, mt, mr: [],
        actor_id="actor:liam",
    )
    ctx = _ctx(wrapper)

    out = await execute_recall_memory(_args(), ctx)
    assert out.status == "ok"
    envelope = out.data["memories"][0]
    assert envelope["citation_pack"]["citations"] == []
    assert envelope["memories"] == []


# =====================================================================
# Without wrapper — concierge tool still works (POC behaviour)
# =====================================================================
async def test_no_wrapper_yields_raw_rows_baseline() -> None:
    ctx = _ctx(_fake_inner_sync)
    out = await execute_recall_memory(_args(), ctx)
    assert out.status == "ok"
    rows = out.data["memories"]
    assert isinstance(rows, list)
    assert "citation_pack" not in rows[0]


# =====================================================================
# Empty query short-circuits at the tool, never hits the wrapper
# =====================================================================
async def test_empty_query_short_circuits_before_wrapper() -> None:
    called: list[tuple] = []

    def spy(q, mt, mr):
        called.append((q, mt, mr))
        return []

    wrapper = RecallCitationWrapper(inner=spy, actor_id="actor:liam")
    ctx = _ctx(wrapper)

    out = await execute_recall_memory({"query": "", "memory_types": [], "max_results": 5}, ctx)
    assert out.status == "error"
    assert called == []  # tool short-circuits before invoking recall_fn
