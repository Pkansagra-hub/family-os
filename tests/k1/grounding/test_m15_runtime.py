"""M1.5 grounding runtime tests for E1-E3."""

from __future__ import annotations

import dataclasses
import inspect
from types import SimpleNamespace

from k1.grounding.adapters import SpatialHandleAdapter, build_unknown_spatial_projection
from k1.grounding.constants import (
    PROPAGATION_FIELD_ENVELOPE_ID,
    PROPAGATION_FIELD_RESOLVED_SPATIAL_REFS,
    PROPAGATION_FIELD_RESOLVED_TEMPORAL_REFS,
    PROPAGATION_FIELD_SPATIAL_CONTEXT_ID,
    PROPAGATION_FIELD_TEMPORAL_ANCHOR_ID,
)
from k1.grounding.events import GroundingEnvelopeCreatedPayload
from k1.grounding.factory import GroundingFactory
from k1.grounding.kernel.handle import build_grounding_handle
from k1.grounding.ports import (
    IGroundingIdPort,
    IGroundingSpatialPort,
    IGroundingStatePort,
)
from k1.grounding.serialization import dict_to_projection, projection_to_dict
from k1.grounding.service import (
    build_propagation_metadata,
    render_execution_grounding_block,
    render_now_block,
    render_place_block,
    render_planning_grounding_block,
)
from k1.grounding.types import DeviceContextSnapshot
from k1.kernel.ports.device_context_port import (
    DeviceContextSnapshot as KernelDeviceContextSnapshot,
)
from k1.spatial.types import SpatialProjection


def test_m15_e1_device_context_snapshot_is_single_canonical_type() -> None:
    assert KernelDeviceContextSnapshot is DeviceContextSnapshot
    assert dataclasses.is_dataclass(DeviceContextSnapshot)
    assert DeviceContextSnapshot.__dataclass_params__.frozen is True
    assert inspect.getmodule(DeviceContextSnapshot).__name__ == "k1.grounding.types"


def test_m15_e1_events_are_typed_payloads() -> None:
    payload = GroundingEnvelopeCreatedPayload(
        envelope_id="e1",
        session_id="s1",
        created_at_utc="2026-05-21T00:00:00+00:00",
        temporal_anchor_id="ta1",
        spatial_context_id="unknown",
    )
    assert dataclasses.asdict(payload)["temporal_anchor_id"] == "ta1"


async def test_m15_e2_ports_and_unknown_spatial_adapter() -> None:
    bundle, adapters = GroundingFactory.create_for_testing()
    assert isinstance(adapters["spatial_port"], IGroundingSpatialPort)
    assert isinstance(adapters["id_port"], IGroundingIdPort)
    assert isinstance(adapters["state_port"], IGroundingStatePort)

    projection = await SpatialHandleAdapter().build_projection("s1", "front")
    assert projection.context_id == "unknown"
    assert projection.precision == "hidden"
    assert projection.freshness == "unavailable"

    fallback = build_unknown_spatial_projection(session_id="s1", consumer="front")
    assert fallback.active_device_surface == "unknown"
    assert bundle.health().ready is True


async def test_m15_e3_service_builds_projection_lease_and_propagation_metadata() -> None:
    bundle, _adapters = GroundingFactory.create_for_testing()
    projection = await bundle.service.build_projection("s1", consumer="front", turn_id="t1")

    assert projection.envelope_id
    assert projection.temporal.anchor.anchor_id
    assert projection.spatial.context_id == "unknown"

    restored = dict_to_projection(projection_to_dict(projection))
    assert restored.projection_id == projection.projection_id
    assert restored.spatial.context_id == "unknown"

    metadata = build_propagation_metadata(projection)
    assert metadata[PROPAGATION_FIELD_ENVELOPE_ID] == projection.envelope_id
    assert metadata[PROPAGATION_FIELD_TEMPORAL_ANCHOR_ID] == projection.temporal.anchor.anchor_id
    assert metadata[PROPAGATION_FIELD_SPATIAL_CONTEXT_ID] == "unknown"
    assert PROPAGATION_FIELD_RESOLVED_TEMPORAL_REFS in metadata
    assert PROPAGATION_FIELD_RESOLVED_SPATIAL_REFS in metadata

    lease = await bundle.service.issue_agent_lease("s1", task_scope="test-task")
    assert lease.status == "active"
    assert lease.spatial.context_id == "unknown"
    assert lease.task_scope == "test-task"


class _RefreshAwareSpatialPort:
    def __init__(self) -> None:
        self.refreshed = False
        self.refresh_calls: list[dict[str, object]] = []
        self.build_calls: list[dict[str, object]] = []

    async def refresh_turn(self, session_id: str, consumer: str, **kwargs):  # type: ignore[no-untyped-def]
        self.refreshed = True
        self.refresh_calls.append({"session_id": session_id, "consumer": consumer, **kwargs})
        return self._projection(session_id, consumer, freshness="live")

    async def build_projection(self, session_id: str, consumer: str, **kwargs):  # type: ignore[no-untyped-def]
        self.build_calls.append({"session_id": session_id, "consumer": consumer, **kwargs})
        return self._projection(
            session_id,
            consumer,
            freshness="live" if self.refreshed else "unavailable",
        )

    @staticmethod
    def _projection(session_id: str, consumer: str, *, freshness: str) -> SpatialProjection:
        return SpatialProjection(
            projection_id="sp1",
            context_id="ctx-live" if freshness == "live" else "ctx-stale",
            session_id=session_id,
            consumer=consumer,
            semantic_place="unknown",
            precision="address",
            place_refs=(),
            active_device_surface="web",
            co_presence=(),
            freshness=freshness,
            redactions=("raw_location_denied",),
            metadata={"location_accuracy_m": 42 if freshness == "live" else None},
        )


async def test_grounding_refresh_turn_refreshes_spatial_before_envelope_build() -> None:
    spatial = _RefreshAwareSpatialPort()
    bundle, _adapters = GroundingFactory.create_for_testing(spatial_port=spatial)

    envelope = await bundle.service.refresh_turn(
        "s1",
        consumer="front",
        turn_id="t1",
        device_id="alex_phone",
        installation_id="alex_phone",
    )

    assert spatial.refresh_calls == [
        {
            "session_id": "s1",
            "consumer": "front",
            "device_id": "alex_phone",
            "installation_id": "alex_phone",
            "requested_precision": "address",
        }
    ]
    assert spatial.build_calls
    assert envelope.spatial.context_id == "ctx-live"
    assert envelope.spatial.freshness == "live"


async def test_m15_e3_handle_and_prompt_block_renderer() -> None:
    bundle = GroundingFactory.create_standalone()
    handle = build_grounding_handle(bundle, session_id="s1", actor_id="actor-1")

    projection = await handle.get_projection("front")
    assert projection.metadata["identity_ref"] == "actor-1"

    assert render_now_block(projection).startswith("== NOW ==")
    assert render_place_block(projection).startswith("== PLACE ==")
    assert render_execution_grounding_block(projection).startswith("== EXECUTION GROUNDING ==")
    assert render_planning_grounding_block(projection).startswith("== PLANNING GROUNDING ==")


def test_place_block_signals_available_approximate_location_without_coordinates() -> None:
    projection = SimpleNamespace(
        spatial=SimpleNamespace(
            semantic_place="unknown",
            precision="approximate",
            freshness="live",
            active_device_surface="web",
            place_refs=(),
            approximate_location={"latitude": 33.21, "longitude": -97.13, "accuracy_m": 42},
            redactions=("raw_location_denied",),
        )
    )

    block = render_place_block(projection)

    assert "unknown (approximate, live)" in block
    assert "accuracy_m: 42" in block
    assert "approx_location: available" in block
    assert "33.21" not in block
    assert "-97.13" not in block
    assert "raw_location_denied" in block
    assert "raw_coordinates" not in block


def test_place_block_prefers_semantic_place_over_approximate_coordinates() -> None:
    projection = SimpleNamespace(
        spatial=SimpleNamespace(
            semantic_place="Plano, Texas",
            precision="approximate",
            freshness="live",
            active_device_surface="web",
            place_refs=(),
            approximate_location={"latitude": 33.01, "longitude": -96.82, "accuracy_m": 77},
            redactions=("raw_location_denied",),
        )
    )

    block = render_place_block(projection)

    assert "Plano, Texas (approximate, live)" in block
    assert "accuracy_m: 77" in block
    assert "approx_location" not in block
    assert "33.01" not in block


def test_place_block_renders_address_precision_without_coordinates() -> None:
    projection = SimpleNamespace(
        spatial=SimpleNamespace(
            semantic_place="123 Example Ln, Sampleton, Testland",
            precision="address",
            freshness="live",
            active_device_surface="web",
            place_refs=(),
            approximate_location=None,
            raw_location=None,
            metadata={"location_accuracy_m": 8},
            redactions=("raw_location_denied",),
        )
    )

    block = render_place_block(projection)

    assert "123 Example Ln, Sampleton, Testland (address, live)" in block
    assert "accuracy_m: 8" in block
    assert "raw_location_denied" in block
    assert "raw_coordinates" not in block


async def test_m15_e4_handle_protocol_aliases_preserve_envelope_for_agent_lease() -> None:
    bundle = GroundingFactory.create_standalone()
    handle = build_grounding_handle(bundle, session_id="s1", actor_id="actor-1")

    envelope = await handle.create_envelope(consumer="front", turn_id="t1")
    projection = await handle.build_projection(envelope, consumer="front")
    lease = await handle.build_agent_lease(envelope, task_scope="dispatch", ttl_seconds=30)

    assert projection.envelope_id == envelope.envelope_id
    assert lease.envelope_id == envelope.envelope_id
    assert lease.task_scope == "dispatch"
