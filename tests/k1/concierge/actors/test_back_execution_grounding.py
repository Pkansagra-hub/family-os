"""M1.5-E4: Back execution grounding prompt block."""

from __future__ import annotations

from k1.concierge.actors.back import _build_execution_grounding_block
from k1.grounding.factory import GroundingFactory
from k1.grounding.serialization import projection_to_dict


async def test_back_renders_execution_grounding_from_task_projection() -> None:
    bundle = GroundingFactory.create_standalone()
    projection = await bundle.service.build_projection("s1", consumer="back", turn_id="t1")

    block = await _build_execution_grounding_block(
        {"grounding": projection_to_dict(projection)}, None
    )

    assert block.startswith("== EXECUTION GROUNDING ==")
    assert projection.envelope_id in block
