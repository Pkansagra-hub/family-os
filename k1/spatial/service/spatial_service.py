"""Top-level deterministic spatial service API."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from k1.spatial.config import SpatialConfig
from k1.spatial.events import (
    SpatialContextCreatedPayload,
    SpatialLocationUnavailablePayload,
    SpatialPlaceResolvedPayload,
)
from k1.spatial.ports import (
    IDeviceLocationPort,
    IGeocoderPort,
    IPlaceRegistryPort,
    IPresencePort,
    ISpatialDeviceContextPort,
    ISpatialEventPort,
    ISpatialIdPort,
    ISpatialPolicyPort,
    ISpatialStatePort,
)
from k1.spatial.serialization import (
    geofence_to_dict,
    place_ref_to_dict,
    spatial_context_to_dict,
    spatial_projection_to_dict,
)
from k1.spatial.service.device_surface_resolver import resolve_device_surface
from k1.spatial.service.event_emitter import SpatialEventEmitter
from k1.spatial.service.geofence_matcher import match_geofences
from k1.spatial.service.health import SpatialHealth
from k1.spatial.service.location_normalizer import normalize_location_fix
from k1.spatial.service.place_candidate_source import candidates_from_device_context
from k1.spatial.service.place_resolver import resolve_place_candidate
from k1.spatial.service.presence_resolver import resolve_presence
from k1.spatial.service.projection_builder import SpatialProjectionBuilder
from k1.spatial.types import (
    LocationFix,
    PlaceRef,
    SpatialContext,
    SpatialProjection,
    SpatialTurnSnapshot,
)


class SpatialService:
    """Owns spatial refresh, place resolution, projection, and health."""

    def __init__(
        self,
        *,
        device_context_port: ISpatialDeviceContextPort,
        device_location_port: IDeviceLocationPort | None,
        place_registry_port: IPlaceRegistryPort,
        geocoder_port: IGeocoderPort | None = None,
        presence_port: IPresencePort | None = None,
        policy_port: ISpatialPolicyPort | None = None,
        state_port: ISpatialStatePort | None = None,
        event_port: ISpatialEventPort | None = None,
        id_port: ISpatialIdPort | None = None,
        config: SpatialConfig | None = None,
    ) -> None:
        self._device_context = device_context_port
        self._device_location = device_location_port
        self._registry = place_registry_port
        self._geocoder = geocoder_port
        self._presence = presence_port
        self._state = state_port
        self._events = SpatialEventEmitter(event_port)
        self._ids = id_port or _DeterministicSpatialIds()
        self._config = config or SpatialConfig()
        self._projection_builder = SpatialProjectionBuilder(
            policy_port=policy_port,
            config=self._config,
        )
        self._contexts: dict[str, SpatialContext] = {}
        self._projections: dict[tuple[str, str], SpatialProjection] = {}
        self._closed = False

    async def refresh_turn(
        self,
        session_id: str,
        *,
        device_id: str,
        installation_id: str,
        turn_id: str | None = None,
        trace_id: str | None = None,
        consumer: str = "front",
    ) -> SpatialTurnSnapshot:
        """Refresh spatial state from device context, registry, presence, and policy."""
        snapshot = await self._device_context.get_device_snapshot(
            session_id,
            device_id,
            installation_id,
        )
        surface = resolve_device_surface(snapshot)
        raw_fix: Any = snapshot.location_fix
        if raw_fix is None and self._device_location is not None:
            raw_fix = await self._device_location.get_location_fix(
                session_id,
                device_id,
                installation_id,
            )
        fix = normalize_location_fix(
            raw_fix,
            observed_at_utc=snapshot.observed_at_utc,
            permission_state=snapshot.location_permission,
        )
        places = tuple(await self._registry.list_places(session_id))
        geofences = tuple(await self._registry.list_geofences(session_id))
        candidates = candidates_from_device_context(snapshot)
        active_place = resolve_place_candidate(candidates[0] if candidates else None, places)
        geocoded_places: tuple[PlaceRef, ...] = ()
        if (
            active_place is None or active_place.place_id == "unknown"
        ) and fix.latitude is not None:
            matches = match_geofences(fix, geofences)
            if matches:
                matched = matches[0]
                active_place = next(
                    (place for place in places if place.place_id == matched.place_id),
                    active_place,
                )
            if active_place is None or active_place.place_id == "unknown":
                geocoded_places = await self._reverse_geocode(session_id, fix)
                if geocoded_places:
                    active_place = geocoded_places[0]
                    places = _merge_places(places, geocoded_places)
        now = datetime.now(UTC).isoformat()
        redactions = tuple(fix.redactions)
        context = SpatialContext(
            context_id=self._ids.new_context_id(),
            session_id=session_id,
            captured_at_utc=now,
            active_place=(
                active_place if active_place and active_place.place_id != "unknown" else None
            ),
            active_device_surface=surface,
            location_fix=fix if fix.latitude is not None else None,
            co_presence=await resolve_presence(self._presence, session_id),
            freshness="live" if fix.permission_state == "granted" or candidates else "unavailable",
            redactions=redactions,
            location_permission=fix.permission_state,
            precision="hidden" if redactions else self._config.default_precision,
            place_refs=places,
            mentioned_places=tuple(place for place in (active_place,) if place is not None),
            device_context=snapshot,
            provenance=(
                {"source": "device", "device_id": snapshot.device_id},
                {"source": "registry", "place_count": len(places)},
                {"source": "geocoder", "place_count": len(geocoded_places)},
            ),
            metadata={"trace_id": trace_id, "geofence_count": len(geofences)},
        )
        projection = await self._projection_builder.build(
            context=context,
            consumer=consumer,
            projection_id=self._ids.new_projection_id(),
        )
        self._contexts[session_id] = context
        self._projections[(session_id, consumer)] = projection
        if self._state is not None:
            await self._state.write_spatial_section(
                session_id,
                {
                    "current": spatial_context_to_dict(context),
                    "projection": spatial_projection_to_dict(projection),
                },
            )
            await self._state.write_place_registry_section(
                session_id,
                {
                    "places": [place_ref_to_dict(place) for place in places],
                    "geofences": [geofence_to_dict(geofence) for geofence in geofences],
                },
            )
        await self._events.context_created(
            SpatialContextCreatedPayload(
                context_id=context.context_id,
                session_id=session_id,
                captured_at_utc=now,
                semantic_place=projection.semantic_place,
                precision=projection.precision,
                source="device",
            )
        )
        if active_place is not None and active_place.place_id != "unknown":
            await self._events.place_resolved(
                SpatialPlaceResolvedPayload(
                    context_id=context.context_id,
                    session_id=session_id,
                    place_id=active_place.place_id,
                    raw_text=active_place.label,
                    source=active_place.source,
                    confidence=active_place.confidence,
                    resolved_at_utc=now,
                )
            )
        if fix.latitude is None:
            await self._events.location_unavailable(
                SpatialLocationUnavailablePayload(
                    session_id=session_id,
                    device_id=device_id,
                    installation_id=installation_id,
                    permission_state=fix.permission_state,
                    observed_at_utc=snapshot.observed_at_utc,
                    reason=redactions[0] if redactions else "source_unavailable",
                )
            )
        return SpatialTurnSnapshot(
            session_id=session_id,
            turn_id=turn_id,
            context=context,
            projection=projection,
            refreshed_at_utc=now,
            source="spatial_service",
            metadata={"trace_id": trace_id},
        )

    async def get_context(self, session_id: str) -> SpatialContext:
        context = self._contexts.get(session_id)
        if context is None:
            raise KeyError(f"spatial context not refreshed for session {session_id}")
        return context

    async def resolve_place(
        self,
        session_id: str,
        text: str,
        *,
        subject_ref: str | None = None,
    ) -> PlaceRef | None:
        places = tuple(await self._registry.list_places(session_id))
        from k1.spatial.service.place_alias_catalog import normalize_place_label
        from k1.spatial.types import PlaceCandidate

        candidate = PlaceCandidate(
            raw_text=text,
            normalized_text=normalize_place_label(text),
            source="task_param",
            confidence=0.65,
            subject_ref=subject_ref,
        )
        return resolve_place_candidate(candidate, places)

    async def _reverse_geocode(
        self,
        session_id: str,
        fix: LocationFix,
    ) -> tuple[PlaceRef, ...]:
        if self._geocoder is None:
            return ()
        try:
            return tuple(await self._geocoder.reverse_geocode(session_id, fix))
        except Exception:
            return ()

    async def build_projection(
        self,
        session_id: str,
        consumer: str,
        *,
        requested_precision: str | None = None,
    ) -> SpatialProjection:
        context = await self.get_context(session_id)
        projection = await self._projection_builder.build(
            context=context,
            consumer=consumer,
            projection_id=self._ids.new_projection_id(),
            requested_precision=requested_precision,
        )
        self._projections[(session_id, consumer)] = projection
        return projection

    async def get_projection(self, session_id: str, consumer: str) -> SpatialProjection:
        projection = self._projections.get((session_id, consumer))
        if projection is not None:
            return projection
        return await self.build_projection(session_id, consumer)

    def health(self) -> SpatialHealth:
        last_context = next(reversed(self._contexts.values()), None) if self._contexts else None
        return SpatialHealth(
            status="closed" if self._closed else ("ok" if last_context is not None else "degraded"),
            place_registry={"available": True, "mode": "port"},
            device_location={"available": self._device_location is not None},
            last_context_id=last_context.context_id if last_context is not None else None,
        )

    async def shutdown(self) -> None:
        self._closed = True


class _DeterministicSpatialIds:
    def __init__(self) -> None:
        self._counter = 0

    def _next(self, prefix: str) -> str:
        self._counter += 1
        return f"{prefix}_{self._counter}"

    def new_context_id(self) -> str:
        return self._next("spatial")

    def new_place_id(self) -> str:
        return self._next("place")

    def new_geofence_id(self) -> str:
        return self._next("geofence")

    def new_fix_id(self) -> str:
        return self._next("fix")

    def new_projection_id(self) -> str:
        return self._next("spatial_projection")


def _merge_places(
    places: tuple[PlaceRef, ...],
    extra_places: tuple[PlaceRef, ...],
) -> tuple[PlaceRef, ...]:
    by_id = {place.place_id: place for place in places}
    for place in extra_places:
        by_id.setdefault(place.place_id, place)
    return tuple(by_id.values())


__all__ = ["SpatialService"]
