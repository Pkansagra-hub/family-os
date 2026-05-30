"""M4-E1 provider metadata propagation for grounding invocation."""

from __future__ import annotations

from k1.fabric.providers.base_provider import (
    attach_provider_metadata,
    build_provider_metadata,
)
from k1.fabric.types import CapabilityRequest, ExecutionContext


def test_provider_metadata_preserves_grounding_invocation() -> None:
    grounding_invocation = {
        "invoked_at_utc": "2026-05-24T21:20:00+00:00",
        "grounding_envelope_id": "env-1",
        "grounding_projection_id": "proj-1",
        "temporal_anchor_id": "anchor-1",
        "spatial_context_id": "spatial-1",
    }
    request = CapabilityRequest(
        capability_name="tool.test.grounding",
        caller="test",
        prompt_template="tool_prompt",
        trace_id="trace-1",
    )
    context = ExecutionContext(
        session_sections={"context_override": {"grounding_invocation": grounding_invocation}},
        params={"value": 1},
        trace_id="trace-1",
    )

    metadata = build_provider_metadata(request, context)
    params = attach_provider_metadata(context.params, metadata)

    assert metadata["__grounding_invocation__"] == grounding_invocation
    assert params["__metadata__"]["__grounding_invocation__"] == grounding_invocation
