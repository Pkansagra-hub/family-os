"""M3-E3 spatial privacy projection tests."""

from __future__ import annotations

from k1.spatial.service import build_spatial_projection, render_execution_place_block
from k1.spatial.service.precision_selector import clamp_precision
from k1.spatial.types import DeviceSurface, LocationFix, PlaceRef, SpatialContext


def test_privacy_projector_hides_raw_coordinates_for_semantic_projection() -> None:
    projection = build_spatial_projection(
        context=_context(),
        consumer="front",
        projection_id="proj1",
        precision="semantic",
    )

    assert projection.semantic_place == "home"
    assert projection.raw_location is None
    assert "raw_location_denied" in projection.redactions
    assert "33.2" not in render_execution_place_block(projection)


def test_privacy_projector_allows_raw_only_when_precision_is_raw() -> None:
    projection = build_spatial_projection(
        context=_context(),
        consumer="tool",
        projection_id="proj1",
        precision="raw",
    )

    assert projection.raw_location is not None
    assert "33.2" in render_execution_place_block(projection)


def test_privacy_projector_address_precision_exposes_address_without_raw_coordinates() -> None:
    projection = build_spatial_projection(
        context=_context(
            PlaceRef(
                place_id="geocoder:address:123-example-ln-sampleton-testland",
                label="123 Example Ln, Sampleton, Testland",
                place_kind="address",
                confidence=0.88,
                source="geocoder",
                metadata={"address_level": True, "locality_label": "Sampleton, Testland"},
            )
        ),
        consumer="front",
        projection_id="proj1",
        precision="address",
    )

    assert projection.semantic_place == "123 Example Ln, Sampleton, Testland"
    assert projection.raw_location is None
    assert projection.metadata["location_accuracy_m"] == 20
    assert "raw_location_denied" in projection.redactions


def test_privacy_projector_downgrades_address_for_approximate_precision() -> None:
    projection = build_spatial_projection(
        context=_context(
            PlaceRef(
                place_id="geocoder:address:123-example-ln-sampleton-testland",
                label="123 Example Ln, Sampleton, Testland",
                place_kind="address",
                confidence=0.88,
                source="geocoder",
                metadata={"address_level": True, "locality_label": "Sampleton, Testland"},
            )
        ),
        consumer="front",
        projection_id="proj1",
        precision="approximate",
    )

    assert projection.semantic_place == "Sampleton, Testland"
    assert "123 Example" not in render_execution_place_block(projection)


def test_precision_selector_never_exceeds_allowed_precision() -> None:
    assert clamp_precision("raw", "semantic") == "semantic"
    assert clamp_precision("semantic", "place_id") == "semantic"
    assert clamp_precision("raw", "address") == "address"


def _context(place: PlaceRef | None = None) -> SpatialContext:
    place = place or PlaceRef(
        place_id="home",
        label="home",
        place_kind="home",
        confidence=0.95,
        source="registry",
    )
    return SpatialContext(
        context_id="ctx1",
        session_id="s1",
        captured_at_utc="2026-05-23T01:00:00+00:00",
        active_place=place,
        active_device_surface=DeviceSurface(
            surface_id="install",
            surface_kind="mobile",
            device_id="phone",
            installation_id="install",
        ),
        location_fix=LocationFix(
            latitude=33.2,
            longitude=-97.1,
            accuracy_m=20,
            captured_at_utc="2026-05-23T01:00:00+00:00",
            permission_state="granted",
            source="device",
            confidence=0.9,
        ),
        co_presence=(),
        freshness="live",
        redactions=(),
        location_permission="granted",
        precision="semantic",
        place_refs=(place,),
    )
