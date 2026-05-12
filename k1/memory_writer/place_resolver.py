"""
PlaceResolver -- Resolve location names to stable place_ids (GAP-002 Epic 3.1).

Follows the PersonResolver pattern: reads EntityRef objects (type=LOCATION)
from beliefs_active.mentioned_entities, builds a case-insensitive alias map,
resolves raw location strings to stable place_id identifiers.

place_id format: place_<slug> where slug = lowercase, spaces to underscores,
punctuation stripped. Example: "Olive Garden" -> "place_olive_garden".

Import graph:
  - k1.memory_writer.place_resolver -> re (stdlib)
  - k1.memory_writer.place_resolver -> dataclasses (stdlib)
  - NEVER imports from k1.sessionstate (loose coupling via entity list)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

_SLUG_RE = re.compile(r"[^a-z0-9]+")

# Geohash sentinel: K0 stage_42 geo_metadata will enrich with real coordinates.
GEOHASH_SENTINEL = "000000"


@dataclass(frozen=True)
class ResolvedPlace:
    """Result of a place resolution: stable ID + canonical name + confidence."""

    place_id: str
    canonical_name: str
    confidence: float


class PlaceResolver:
    """Resolve location names to stable place_ids.

    Reads EntityRef objects (type=LOCATION) from beliefs_active,
    builds a case-insensitive lookup map, resolves raw location strings
    to stable place_id identifiers.

    Construction is O(n) where n = number of location entities.
    Resolution is O(1) for exact match, O(n) for prefix fallback.
    """

    __slots__ = ("_exact_map", "_entries")

    def __init__(self, location_entities: list) -> None:
        self._exact_map: dict[str, ResolvedPlace] = {}
        self._entries: list[tuple[str, ResolvedPlace]] = []

        for entity in location_entities:
            etype = getattr(entity, "type", None)
            if etype != "LOCATION":
                continue
            canonical = getattr(entity, "display_name", "") or ""
            if not canonical.strip():
                continue

            place_id = _to_place_id(canonical)
            confidence = float(getattr(entity, "confidence", 1.0))
            resolved = ResolvedPlace(
                place_id=place_id,
                canonical_name=canonical.strip(),
                confidence=confidence,
            )

            key = canonical.strip().lower()
            self._exact_map[key] = resolved
            self._entries.append((key, resolved))

    def set_entities(self, location_entities: list) -> None:
        """Replace the entity map with a new list (called per-turn from pipeline Stage 2).

        Allows the resolver singleton constructed at factory time to be updated
        with fresh SessionState snapshot data before envelope building (MW-04-A).
        """
        self._exact_map.clear()
        self._entries.clear()
        for entity in location_entities:
            etype = getattr(entity, "type", None)
            if etype != "LOCATION":
                continue
            canonical = getattr(entity, "display_name", "") or ""
            if not canonical.strip():
                continue
            place_id = _to_place_id(canonical)
            confidence = float(getattr(entity, "confidence", 1.0))
            resolved = ResolvedPlace(
                place_id=place_id,
                canonical_name=canonical.strip(),
                confidence=confidence,
            )
            key = canonical.strip().lower()
            self._exact_map[key] = resolved
            self._entries.append((key, resolved))

    def resolve(self, name: Optional[str]) -> Optional[str]:
        """Resolve a location name to a stable place_id.

        Returns None if name is empty or no match found.
        Exact match (case-insensitive) is tried first, then prefix match.
        """
        if not name or not name.strip():
            return None

        key = _normalize_key(name)

        # Exact match (O(1))
        resolved = self._exact_map.get(key)
        if resolved:
            return resolved.place_id

        # Prefix match: "Olive Garden" matches "olive garden on main st"
        # or "olive garden on main st" matches entity "Olive Garden"
        for alias_key, alias_resolved in self._entries:
            if alias_key.startswith(key) or key.startswith(alias_key):
                return alias_resolved.place_id

        return None

    def resolve_with_geohash(
        self,
        name: Optional[str],
        known_geohashes: Optional[Dict[str, str]] = None,
    ) -> Tuple[Optional[str], Optional[str]]:
        """Resolve a location name to (place_id, geohash_6).

        Geohash resolution order:
          1. Exact case-insensitive match in known_geohashes dict.
          2. Prefix match in known_geohashes (same logic as resolve()).
          3. Fallback sentinel "000000" if place_id resolved but no geohash.
          4. (None, None) if name is None/empty or no place match.

        Args:
            name: Raw location name from the turn.
            known_geohashes: Tenant-configured mapping of location names
                to 6-char geohash strings. Keys are case-insensitive.

        Returns:
            (place_id, geohash_6) tuple. geohash_6 is a valid 6-char
            geohash, the sentinel "000000", or None.
        """
        if not name or not name.strip():
            return (None, None)

        place_id = self.resolve(name)
        if place_id is None:
            return (None, None)

        geohash = self._lookup_geohash(name, known_geohashes)
        return (place_id, geohash)

    @staticmethod
    def _lookup_geohash(
        name: str,
        known_geohashes: Optional[Dict[str, str]],
    ) -> str:
        """Look up geohash for a location name.

        Returns a 6-char geohash string or the sentinel "000000".
        """
        if not known_geohashes:
            return GEOHASH_SENTINEL

        key = _normalize_key(name)

        # Exact match (O(1))
        for known_name, ghash in known_geohashes.items():
            if _normalize_key(known_name) == key:
                return ghash

        # Prefix match (same logic as resolve())
        for known_name, ghash in known_geohashes.items():
            known_key = _normalize_key(known_name)
            if known_key.startswith(key) or key.startswith(known_key):
                return ghash

        return GEOHASH_SENTINEL


def _normalize_key(name: str) -> str:
    """Normalize a location name for case-insensitive lookup."""
    return name.strip().lower()


def _to_place_id(canonical_name: str) -> str:
    """Convert canonical location name to place_id slug.

    "Olive Garden" -> "place_olive_garden"
    "Mom's House" -> "place_mom_s_house"
    """
    slug = _SLUG_RE.sub("_", canonical_name.strip().lower()).strip("_")
    return f"place_{slug}"
