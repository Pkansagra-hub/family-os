"""M3-E3 place resolver tests."""

from __future__ import annotations

from k1.spatial.adapters import LocalPlaceRegistryAdapter
from k1.spatial.service.place_alias_catalog import normalize_place_label
from k1.spatial.service.place_resolver import resolve_place_candidate
from k1.spatial.types import PlaceCandidate, PlaceRef


async def test_local_place_registry_exposes_places_aliases_and_timezone() -> None:
    place = _home()
    registry = LocalPlaceRegistryAdapter(
        places=(place,), place_timezones={"home": "America/Chicago"}
    )

    assert tuple(await registry.list_places("s1")) == (place,)
    assert await registry.timezone_for_place("s1", "home") == "America/Chicago"
    assert (await registry.registry_metadata("s1"))["mode"] == "local"


def test_place_resolver_matches_alias_and_preserves_provenance() -> None:
    candidate = PlaceCandidate(
        raw_text="our-house",
        normalized_text=normalize_place_label("our-house"),
        source="task_param",
        confidence=0.7,
    )

    resolved = resolve_place_candidate(candidate, [_home()])

    assert resolved is not None
    assert resolved.place_id == "home"
    assert resolved.metadata["matched_candidate_source"] == "task_param"


def test_place_resolver_returns_unknown_safe_fallback() -> None:
    candidate = PlaceCandidate(
        raw_text="moon base",
        normalized_text="moon base",
        source="task_param",
        confidence=0.6,
    )

    resolved = resolve_place_candidate(candidate, [_home()])

    assert resolved is not None
    assert resolved.place_id == "unknown"
    assert resolved.label == "unknown"


def _home() -> PlaceRef:
    return PlaceRef(
        place_id="home",
        label="home",
        place_kind="home",
        confidence=0.95,
        source="registry",
        aliases=("our house",),
        timezone="America/Chicago",
    )
