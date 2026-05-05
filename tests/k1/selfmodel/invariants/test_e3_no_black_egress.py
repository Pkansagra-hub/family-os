"""M4.E3.I3 — Empty-Set Invariant E3: no BLACK egress to bridge / capsule."""

from __future__ import annotations

import pytest

from k1.selfmodel.adapters.bridge_amendment_sync import BridgeAmendmentSyncAdapter
from k1.selfmodel.contracts.constitution import (
    AmendmentProposal,
    AmendmentStatus,
)
from k1.selfmodel.contracts.privacy import (
    BlackBandLeakError,
    PrivacyBand,
    privacy_band_to_bridge,
)
from k1.selfmodel.contracts.situation import (
    RelationsSubset,
    SituationFrame,
)
from k1.selfmodel.service.capsule_builder import GroundingCapsuleBuilder

pytestmark = pytest.mark.invariant


class _NullSigning:
    key_id = "k1"

    def sign(self, payload):  # pragma: no cover - never reached
        return "x"


class _NullBridge:
    async def submit_command(self, *a, **kw):  # pragma: no cover - never reached
        raise AssertionError("submit_command must NOT be invoked when band=BLACK")


def test_privacy_band_to_bridge_blocks_black() -> None:
    with pytest.raises(BlackBandLeakError):
        privacy_band_to_bridge(PrivacyBand.BLACK)


async def test_bridge_submit_delta_rejects_black_band() -> None:
    proposal = AmendmentProposal(
        amendment_id="amd",
        parent_version="v0",
        proposed_by="m",
        body={},
        status=AmendmentStatus.DRAFT,
    )
    adapter = BridgeAmendmentSyncAdapter(bridge=_NullBridge(), signing=_NullSigning())
    with pytest.raises(BlackBandLeakError):
        await adapter.submit_delta(proposal, band=PrivacyBand.BLACK)


def test_capsule_actor_block_rejects_black_band() -> None:
    frame = SituationFrame(
        actor_id="a1",
        situation_kind="caregiver_context_briefing",
        composed_at_ms=0,
        projected_self={"display_name": "Alex", "privacy_band": "BLACK"},
        relations=RelationsSubset(),
    )
    with pytest.raises(BlackBandLeakError):
        GroundingCapsuleBuilder().build(frame)
