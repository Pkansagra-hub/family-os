"""M4.I11 Front Iteration 2 typed grounding block renderers."""

from __future__ import annotations

import pytest

from k1.grounding.factory import GroundingFactory
from k1.grounding.kernel.handle import build_grounding_handle
from k1.grounding.service import (
    render_grounding_meta_block_v2,
    render_place_and_device_block_v2,
    render_time_block_v2,
)


@pytest.fixture
async def front_projection():
    bundle = GroundingFactory.create_standalone()
    handle = build_grounding_handle(bundle, session_id="s1", actor_id="actor-1")
    return await handle.get_projection("front")


async def test_render_grounding_meta_block_v2_emits_envelope_metadata(
    front_projection,
) -> None:
    block = render_grounding_meta_block_v2(front_projection)
    lines = block.splitlines()
    assert lines[0] == "== GROUNDING =="
    assert any(line.startswith("projection_id: ") for line in lines)
    assert any(line.startswith("envelope_id: ") for line in lines)
    assert any(line.startswith("consumer: front") for line in lines)
    assert any(line.startswith("freshness.status: ") for line in lines)
    assert any(line.startswith("freshness.generated_at_utc: ") for line in lines)
    assert any(line.startswith("freshness.age_ms: ") for line in lines)
    # Rule is the authoritative override line.
    assert "Rule:" in block


async def test_render_time_block_v2_emits_anchor_fields(front_projection) -> None:
    block = render_time_block_v2(front_projection)
    anchor = front_projection.temporal.anchor
    assert block.startswith("== TIME ==")
    assert f"now_local: {anchor.now_local}" in block
    assert f"local_date: {anchor.local_date}" in block
    assert f"local_time: {anchor.local_time}" in block
    assert f"time_of_day: {anchor.time_of_day}" in block
    assert f"timezone: {anchor.timezone}" in block
    assert f"precision: {front_projection.temporal.precision}" in block
    assert f"freshness: {front_projection.temporal.freshness}" in block


async def test_render_place_and_device_block_v2_emits_spatial_fields(
    front_projection,
) -> None:
    block = render_place_and_device_block_v2(front_projection)
    spatial = front_projection.spatial
    assert block.startswith("== PLACE AND DEVICE ==")
    expected_place = spatial.semantic_place or "unknown"
    assert f"semantic_place: {expected_place}" in block
    assert f"precision: {spatial.precision}" in block
    assert f"freshness: {spatial.freshness}" in block
    assert f"location_permission: {spatial.location_permission}" in block
