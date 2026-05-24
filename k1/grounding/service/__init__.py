"""Grounding service implementation."""

from __future__ import annotations

from k1.grounding.service.context_snapshot_builder import build_device_context_snapshot
from k1.grounding.service.envelope_builder import build_envelope
from k1.grounding.service.grounding_service import GroundingService
from k1.grounding.service.health import GroundingHealthStatus
from k1.grounding.service.invocation_metadata import build_invocation_metadata
from k1.grounding.service.lease_builder import build_agent_lease
from k1.grounding.service.projection_builder import build_projection
from k1.grounding.service.projection_policy import (
    assert_projection_allowed,
    default_consumer_scope,
)
from k1.grounding.service.prompt_block_renderer import (
    render_execution_grounding_block,
    render_now_block,
    render_place_block,
    render_planning_grounding_block,
)
from k1.grounding.service.propagation import (
    attach_propagation_metadata,
    build_propagation_metadata,
)
from k1.grounding.service.reference_context_builder import build_reference_context
from k1.grounding.service.stale_envelope_checker import envelope_age_ms, is_stale

__all__ = [
    "GroundingHealthStatus",
    "GroundingService",
    "assert_projection_allowed",
    "attach_propagation_metadata",
    "build_agent_lease",
    "build_device_context_snapshot",
    "build_envelope",
    "build_invocation_metadata",
    "build_projection",
    "build_propagation_metadata",
    "build_reference_context",
    "default_consumer_scope",
    "envelope_age_ms",
    "is_stale",
    "render_execution_grounding_block",
    "render_now_block",
    "render_place_block",
    "render_planning_grounding_block",
]
