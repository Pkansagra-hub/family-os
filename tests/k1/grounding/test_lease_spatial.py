"""M3-E6 leases use policy-shaped spatial projections."""

from __future__ import annotations

from k1.grounding.adapters import (
    GroundingStateAdapter,
    SelfModelPolicyAdapter,
    SpatialHandleAdapter,
)
from k1.grounding.service.grounding_service import GroundingService
from k1.grounding.types import DeviceContextSnapshot
from k1.spatial.adapters import SpatialDeviceContextAdapter, SpatialStateAdapter
from k1.spatial.factory import SpatialFactory
from k1.spatial.kernel import build_spatial_handle
from k1.temporal.types import TemporalAnchor, TemporalProjection


class _TemporalPort:
    async def refresh_turn(self, session_id: str, **kwargs) -> None:  # type: ignore[no-untyped-def]
        return None

    async def build_projection(self, session_id: str, consumer: str) -> TemporalProjection:
        return TemporalProjection(
            anchor=TemporalAnchor(
                anchor_id="ta1",
                captured_at_utc="2026-05-23T01:00:00+00:00",
                now_utc="2026-05-23T01:00:00+00:00",
                now_local="2026-05-22T20:00:00-05:00",
                timezone="America/Chicago",
                timezone_source="device",
                local_date="2026-05-22",
                local_time="20:00:00",
                day_of_week="Friday",
                hour_24=20,
                time_of_day="evening",
                is_weekend=False,
                locale="en-US",
                week_start_day="monday",
                freshness_ms=0,
                source="test",
                confidence=1.0,
            ),
            windows={},
            resolved_expressions=(),
            consumer=consumer,
            freshness="live",
            precision="exact",
        )


class _GroundingIdPort:
    def new_envelope_id(self) -> str:
        return "ge1"

    def new_projection_id(self) -> str:
        return "gp1"

    def new_lease_id(self) -> str:
        return "gl1"


class _DeviceContextPort:
    async def get_snapshot(
        self,
        session_id: str,
        device_id: str,
        installation_id: str,
    ) -> DeviceContextSnapshot:
        return DeviceContextSnapshot(
            session_id=session_id,
            device_id=device_id,
            installation_id=installation_id,
            observed_at_utc="2026-05-23T01:00:00+00:00",
            surface="mobile",
            location_permission="granted",
            semantic_place_hint="home",
        )


async def test_issue_agent_lease_uses_agent_spatial_precision() -> None:
    device_context = SpatialDeviceContextAdapter(_DeviceContextPort())
    bundle = SpatialFactory.create_production(
        device_context_port=device_context,
        state_port=SpatialStateAdapter(),
    )
    spatial_handle = build_spatial_handle(
        bundle,
        session_id="s1",
        device_id="device-1",
        installation_id="install-1",
    )
    service = GroundingService(
        temporal_port=_TemporalPort(),
        spatial_port=SpatialHandleAdapter(spatial_handle),
        id_port=_GroundingIdPort(),
        state_port=GroundingStateAdapter(None, allow_memory_fallback=True),
        policy_port=SelfModelPolicyAdapter(None),
    )

    lease = await service.issue_agent_lease("s1", consumer="agent")

    assert lease.spatial.consumer == "agent"
    assert lease.spatial.precision == "semantic"
