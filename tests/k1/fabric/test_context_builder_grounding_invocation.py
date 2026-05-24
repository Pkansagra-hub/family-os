"""M4-E1 grounding invocation coverage for Fabric ContextBuilder."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from k1.fabric.core.context_builder import ContextBuilder
from k1.fabric.types import CapabilityContract
from k1.grounding.factory import GroundingFactory
from k1.grounding.kernel.handle import build_grounding_handle


def _contract() -> CapabilityContract:
    return CapabilityContract(
        name="tool.test.grounding",
        version="1.0.0",
        domain=["test"],
        provider_type="LOCAL",
        provider_id="test_provider",
    )


async def test_build_async_attaches_grounding_invocation_metadata() -> None:
    bundle = GroundingFactory.create_standalone()
    handle = build_grounding_handle(bundle, session_id="session-1", actor_id="actor-1")
    builder = ContextBuilder(grounding_port=handle)

    result = await builder.build_async(
        contract=_contract(),
        params={"value": 1},
        session_id="session-1",
        trace_id="trace-1",
    )

    override = result.context.session_sections["context_override"]
    grounding_invocation = override["grounding_invocation"]

    assert datetime.fromisoformat(grounding_invocation["invoked_at_utc"])
    assert grounding_invocation["grounding_envelope_id"]
    assert grounding_invocation["grounding_projection_id"]
    assert grounding_invocation["temporal_anchor_id"]
    assert grounding_invocation["spatial_context_id"]
    assert grounding_invocation["resolved_temporal_refs"] == []
    assert grounding_invocation["resolved_spatial_refs"] == []


class _CountingGroundingPort:
    def __init__(self) -> None:
        self.create_calls = 0

    async def create_envelope(self, *args: Any, **kwargs: Any) -> Any:
        self.create_calls += 1
        raise RuntimeError("should not be called when invocation is already supplied")


async def test_build_async_preserves_existing_grounding_invocation() -> None:
    port = _CountingGroundingPort()
    builder = ContextBuilder(grounding_port=port)
    supplied_invocation = {
        "invoked_at_utc": "2026-05-24T21:20:00+00:00",
        "grounding_envelope_id": "env-1",
        "grounding_projection_id": "proj-1",
    }

    result = await builder.build_async(
        contract=_contract(),
        session_id="session-1",
        trace_id="trace-1",
        context_override={"grounding_invocation": supplied_invocation},
    )

    override = result.context.session_sections["context_override"]
    assert override["grounding_invocation"] == supplied_invocation
    assert port.create_calls == 0


def test_context_builder_drops_deprecated_ad_hoc_grounding_override_keys() -> None:
    result = ContextBuilder().build(
        contract=_contract(),
        session_id="session-1",
        trace_id="trace-1",
        context_override={
            "temporal": {"now": "bad"},
            "spatial": {"place": "bad"},
            "time": "bad",
            "place": "bad",
            "grounding": {"ad_hoc": True},
            "grounding_invocation": {"grounding_envelope_id": "env-1"},
        },
    )

    override = result.context.session_sections["context_override"]
    assert "temporal" not in override
    assert "spatial" not in override
    assert "time" not in override
    assert "place" not in override
    assert "grounding" not in override
    assert override["grounding_invocation"] == {"grounding_envelope_id": "env-1"}
