"""Apply privacy precision to spatial context."""

from __future__ import annotations

from dataclasses import replace

from k1.spatial.config import SpatialConfig
from k1.spatial.types import LocationFix, PlaceRef, SpatialContext, SpatialProjection

_ADDRESS_PRECISIONS = {"address", "raw"}


def project_context(
    context: SpatialContext,
    *,
    consumer: str,
    projection_id: str,
    precision: str,
    config: SpatialConfig | None = None,
    redactions: tuple[str, ...] = (),
) -> SpatialProjection:
    """Build a policy-shaped projection without leaking raw coordinates by default."""
    cfg = config or SpatialConfig()
    place_refs = _place_refs_for_precision(context, precision)
    semantic_place = _semantic_place(context, cfg.unknown_place_label, precision)
    raw_location = context.location_fix if precision == "raw" else None
    approximate_location = None
    if precision == "approximate" and context.location_fix is not None:
        approximate_location = _approximate_location(
            context.location_fix, cfg.approximate_decimal_places
        )
    redaction_values = tuple(dict.fromkeys((*context.redactions, *redactions)))
    if precision != "raw" and context.location_fix is not None:
        redaction_values = tuple(dict.fromkeys((*redaction_values, "raw_location_denied")))
    return SpatialProjection(
        projection_id=projection_id,
        context_id=context.context_id,
        session_id=context.session_id,
        consumer=consumer,
        semantic_place=semantic_place,
        precision=precision,
        place_refs=place_refs,
        active_device_surface=(
            context.active_device_surface.surface_kind
            if context.active_device_surface is not None
            else "unknown"
        ),
        co_presence=context.co_presence if precision != "hidden" else (),
        freshness=context.freshness,
        redactions=redaction_values,
        location_permission=context.location_permission,
        approximate_location=approximate_location,
        raw_location=raw_location,
        relevant_place_refs=_relevant_place_refs_for_precision(context, precision),
        provenance=context.provenance,
        metadata={
            "captured_at_utc": context.captured_at_utc,
            "location_accuracy_m": (
                context.location_fix.accuracy_m if context.location_fix is not None else None
            ),
            **dict(context.metadata),
        },
    )


def _semantic_place(context: SpatialContext, unknown_label: str, precision: str) -> str:
    if precision == "hidden":
        return unknown_label
    if context.active_place is not None:
        if _is_address_level(context.active_place) and precision not in _ADDRESS_PRECISIONS:
            return _locality_label(context.active_place) or unknown_label
        return context.active_place.label
    return unknown_label


def _place_refs_for_precision(context: SpatialContext, precision: str) -> tuple[PlaceRef, ...]:
    if precision in {"hidden", "semantic", "approximate"}:
        return ()
    if precision not in _ADDRESS_PRECISIONS:
        return tuple(
            _downgrade_address_place_ref(place)
            for place in _all_place_refs(context)
            if not _is_address_level(place) or _locality_label(place)
        )
    return _all_place_refs(context)


def _relevant_place_refs_for_precision(
    context: SpatialContext, precision: str
) -> tuple[PlaceRef, ...]:
    if precision in _ADDRESS_PRECISIONS:
        return _all_place_refs(context)
    return tuple(
        _downgrade_address_place_ref(place)
        for place in context.place_refs
        if not _is_address_level(place) or _locality_label(place)
    )


def _all_place_refs(context: SpatialContext) -> tuple[PlaceRef, ...]:
    if context.active_place is None:
        return tuple(context.place_refs)
    by_id: dict[str, PlaceRef] = {context.active_place.place_id: context.active_place}
    for place in context.place_refs:
        by_id.setdefault(place.place_id, place)
    return tuple(by_id.values())


def _is_address_level(place: PlaceRef) -> bool:
    return place.place_kind in {"address", "street"} or bool(place.metadata.get("address_level"))


def _locality_label(place: PlaceRef) -> str | None:
    value = place.metadata.get("locality_label")
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _downgrade_address_place_ref(place: PlaceRef) -> PlaceRef:
    if not _is_address_level(place):
        return place
    locality = _locality_label(place)
    if not locality:
        return place
    return replace(
        place,
        place_id=place.metadata.get("locality_place_id", place.place_id),
        label=locality,
        place_kind=str(place.metadata.get("locality_kind") or "locality"),
        aliases=tuple(alias for alias in place.aliases if locality.lower() in alias.lower()),
        metadata={
            key: value
            for key, value in place.metadata.items()
            if key
            in {
                "provider",
                "matched_candidate_source",
                "country",
                "locality_label",
                "locality_kind",
                "locality_place_id",
            }
        },
    )


def _approximate_location(fix: LocationFix, decimals: int) -> dict[str, float | None]:
    if fix.latitude is None or fix.longitude is None:
        return {"latitude": None, "longitude": None, "accuracy_m": fix.accuracy_m}
    return {
        "latitude": round(fix.latitude, decimals),
        "longitude": round(fix.longitude, decimals),
        "accuracy_m": fix.accuracy_m,
    }


__all__ = ["project_context"]
