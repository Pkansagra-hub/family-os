"""Default topic registry coverage for grounding event topic families."""

from __future__ import annotations

from k1.bus.middleware.default_registry import get_default_registry
from k1.grounding.events import GROUNDING_ENVELOPE_CREATED, GROUNDING_PROJECTION_CREATED
from k1.spatial.events import SPATIAL_CONTEXT_CREATED, SPATIAL_PLACE_RESOLVED
from k1.temporal.events import TEMPORAL_ANCHOR_CREATED, TEMPORAL_EXPRESSION_RESOLVED


def test_default_registry_knows_temporal_prefix() -> None:
    registry = get_default_registry()

    assert registry.is_known(TEMPORAL_ANCHOR_CREATED)
    assert registry.is_known(TEMPORAL_EXPRESSION_RESOLVED)


def test_default_registry_knows_spatial_and_grounding_prefixes() -> None:
    registry = get_default_registry()

    assert registry.is_known(SPATIAL_CONTEXT_CREATED)
    assert registry.is_known(SPATIAL_PLACE_RESOLVED)
    assert registry.is_known(GROUNDING_ENVELOPE_CREATED)
    assert registry.is_known(GROUNDING_PROJECTION_CREATED)
