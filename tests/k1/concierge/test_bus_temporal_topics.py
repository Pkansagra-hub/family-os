"""Concierge bus topic registry coverage for grounding event families."""

from __future__ import annotations

from types import SimpleNamespace

from k1.bus.middleware.topic_validation import TopicValidationMiddleware
from k1.concierge.bus.setup import build_middleware_chain
from k1.grounding.events import GROUNDING_ENVELOPE_CREATED
from k1.spatial.events import SPATIAL_CONTEXT_CREATED
from k1.temporal.events import TEMPORAL_ANCHOR_CREATED


def test_concierge_bus_registry_knows_grounding_prefixes() -> None:
    chain = build_middleware_chain(
        SimpleNamespace(
            topic_validation_enabled=True,
            tracing_enabled=False,
            metrics_enabled=False,
        )
    )

    assert chain is not None
    middleware = chain._middlewares[0]  # type: ignore[attr-defined]
    assert isinstance(middleware, TopicValidationMiddleware)
    assert middleware.registry.is_known(TEMPORAL_ANCHOR_CREATED)
    assert middleware.registry.is_known(SPATIAL_CONTEXT_CREATED)
    assert middleware.registry.is_known(GROUNDING_ENVELOPE_CREATED)
