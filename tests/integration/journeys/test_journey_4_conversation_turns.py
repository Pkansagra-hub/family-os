"""Journey 4 — Conversation across multiple turns.

Story: A user has a multi-turn conversation with the assistant. Each
turn becomes a ``memory.write`` envelope tagged with the same
``session_id`` and a monotonically increasing ``conversation_turn``.
After all turns commit, ``st_receipts`` shows one row per turn with
strictly ascending ``wal_pos`` values for that space.

This proves K0 preserves *intra-session ordering* — a foundational
guarantee for any future conversational recall.
"""

from __future__ import annotations

import uuid

import pytest

from tests.integration.harness.family_layout import (
    DeviceSpec,
    FamilyLayout,
    PersonSpec,
)
from tests.integration.harness.k0_observer import (
    count_receipts,
    list_wal_positions_for_space,
)
from tests.integration.harness.live_system import LiveSystem


def _hex(n: int = 8) -> str:
    return uuid.uuid4().hex[:n]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_journey_conversation_turns_preserve_ordering() -> None:
    fam = FamilyLayout(
        family_id=f"fam-conv-{_hex()}",
        people=(
            PersonSpec(
                person_id=f"user-{_hex()}",
                role="single",
                devices=(DeviceSpec(device_id=f"dev-{_hex()}", label="phone"),),
            ),
        ),
    )
    session_id = f"session-{_hex()}"
    turns = [
        "What's on my calendar tomorrow?",
        "Move the 10am to 11am.",
        "Also remind me to bring the demo laptop.",
        "Thanks — that's it.",
    ]
    baseline_count = count_receipts(tenant_id=fam.family_id, space_id=fam.family_id)
    baseline_wals = list_wal_positions_for_space(fam.family_id)

    async with LiveSystem(family=fam) as live:
        k1 = live.k1s[0]
        for turn_idx, utterance in enumerate(turns):
            res = await k1.publish_memory_write_v1_native(
                text=utterance,
                topics=["conversation", session_id],
                extra_body={
                    "session_id": session_id,
                    "conversation_turn": turn_idx,
                },
            )
            assert res["http_status"] == 200, (turn_idx, res)

    # All turns committed.
    assert count_receipts(tenant_id=fam.family_id, space_id=fam.family_id) - baseline_count == len(
        turns
    )

    # WAL positions for the space are strictly ascending and grew by exactly len(turns).
    after_wals = list_wal_positions_for_space(fam.family_id)
    new_wals = [w for w in after_wals if w not in baseline_wals]
    assert len(new_wals) == len(turns), (baseline_wals, after_wals, new_wals)
    assert new_wals == sorted(new_wals), new_wals
    assert len(set(new_wals)) == len(new_wals), new_wals  # unique
