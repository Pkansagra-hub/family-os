"""M3-E6 consumer spatial precision policy tests."""

from __future__ import annotations

from k1.grounding.adapters.selfmodel_policy_adapter import SelfModelPolicyAdapter
from k1.grounding.config import GroundingConfig
from k1.grounding.service.projection_policy import default_consumer_scope


def test_default_consumer_scope_uses_spatial_precision_table() -> None:
    assert default_consumer_scope("front").spatial_precision == "address"
    assert default_consumer_scope("tool").spatial_precision == "place_id"
    assert default_consumer_scope("agent").spatial_precision == "semantic"


def test_default_consumer_scope_raw_gate_still_allows_raw_override() -> None:
    config = GroundingConfig(raw_spatial_allowed_by_default=True)

    assert default_consumer_scope("front", config=config).spatial_precision == "raw"


async def test_selfmodel_policy_adapter_accepts_handle_scope_override() -> None:
    class _Handle:
        async def get_grounding_consumer_scope(self, consumer: str, **kwargs):  # type: ignore[no-untyped-def]
            return {"consumer": consumer, "spatial_precision": "hidden", "privacy_scope": "tight"}

    scope = await SelfModelPolicyAdapter(_Handle()).get_consumer_scope("agent")

    assert scope.spatial_precision == "hidden"
    assert scope.privacy_scope == "tight"
