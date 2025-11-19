"""
M07: social.family_graph_resolve - Family Graph Resolver (Social Context Attribution)

Resolves social relationships and family context for episodic memories:
- Queries st_relationships for family graph (5 relationship types)
- Computes participant roles relative to actor
- Derives social context (solo/nuclear_family/extended_family/friends/work)
- Scores social intimacy (HIGH/MED/LOW)

Performance target: ≤8ms P95 (cached lookups)
Contract: k0/contracts/modules/social.family_graph_resolve.v1.yaml
ADR: docs/architecture/decisions-K0/modules/k008.1-family-graph-resolver.md

Usage:
    result = await run(envelope)
"""

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Dict, List, Tuple

# ============================================================================
# Data Structures
# ============================================================================


@dataclass(frozen=True)
class SocialContext:
    """Social context output for an episodic event."""

    num_participants: int
    participant_roles_json: str  # JSON string for st_hipp_events TEXT column
    has_partner_present: bool
    has_parent_present: bool
    is_solo_event: bool
    social_context: str  # solo/nuclear_family/extended_family/friends/work
    social_intimacy: str  # HIGH/MED/LOW
    social_resolved_at_utc: str


# ============================================================================
# Relationship Cache (LRU Cache with 5-minute TTL simulation)
# ============================================================================

# In-memory relationship database (simulates st_relationships table)
# Format: {actor_id: [(related_person_id, relationship_type), ...]}
_RELATIONSHIP_DB: Dict[str, List[Tuple[str, str]]] = {
    "person_dad": [
        ("person_mom", "SPOUSE_OF"),
        ("person_sharvi", "PARENT_OF"),
    ],
    "person_mom": [
        ("person_dad", "SPOUSE_OF"),
        ("person_sharvi", "PARENT_OF"),
    ],
    "person_sharvi": [
        ("person_dad", "CHILD_OF"),
        ("person_mom", "CHILD_OF"),
    ],
    # Add more relationships as needed
}

# Cache statistics
_cache_stats = {
    "hits": 0,
    "misses": 0,
    "db_queries": 0,
    "relationship_type_counts": {
        "SPOUSE_OF": 0,
        "PARENT_OF": 0,
        "CHILD_OF": 0,
        "CARETAKER_OF": 0,
        "SIBLING_OF": 0,
    },
}


@lru_cache(maxsize=1000)
def _get_relationships_cached(actor_id: str) -> Tuple[Tuple[str, str], ...]:
    """
    Get relationships for an actor (cached with LRU eviction).

    Args:
        actor_id: Person ID (e.g., "person_dad")

    Returns:
        Tuple of (related_person_id, relationship_type) tuples

    Performance: O(1) cache hit, O(N) cache miss (N = number of relationships)
    """
    _cache_stats["db_queries"] += 1

    # Simulate database query (in production, this would be async)
    relationships = _RELATIONSHIP_DB.get(actor_id, [])

    # Track relationship type distribution
    for _, rel_type in relationships:
        if rel_type in _cache_stats["relationship_type_counts"]:
            _cache_stats["relationship_type_counts"][rel_type] += 1

    # Return as tuple of tuples (immutable for caching)
    return tuple(relationships)


def _lookup_relationships(actor_id: str) -> List[Tuple[str, str]]:
    """
    Lookup relationships with cache hit/miss tracking.

    Args:
        actor_id: Person ID

    Returns:
        List of (related_person_id, relationship_type) tuples
    """
    # Check if already in cache
    cache_info = _get_relationships_cached.cache_info()
    initial_hits = cache_info.hits

    # Perform lookup
    result = list(_get_relationships_cached(actor_id))

    # Update cache stats
    new_cache_info = _get_relationships_cached.cache_info()
    if new_cache_info.hits > initial_hits:
        _cache_stats["hits"] += 1
    else:
        _cache_stats["misses"] += 1

    return result


# ============================================================================
# Participant Role Classification
# ============================================================================


def _map_participant_roles(
    actor_id: str, participants: List[str], relationships: List[Tuple[str, str]]
) -> Dict[str, str]:
    """
    Map each participant to their relationship role relative to actor.

    Args:
        actor_id: Event actor (owner)
        participants: List of participant IDs
        relationships: List of (related_person_id, relationship_type) tuples

    Returns:
        Dict mapping participant_id -> role (SELF/SPOUSE/PARENT/CHILD/CAREGIVER/SIBLING/OTHER)

    Examples:
        >>> _map_participant_roles("person_dad", ["person_dad", "person_mom"], [...])
        {"person_dad": "SELF", "person_mom": "SPOUSE"}
    """
    roles = {}

    # Build relationship lookup dict for O(1) access
    rel_dict = {person_id: rel_type for person_id, rel_type in relationships}

    for participant_id in participants:
        if participant_id == actor_id:
            roles[participant_id] = "SELF"
            continue

        # Lookup relationship
        rel_type = rel_dict.get(participant_id)

        if rel_type == "SPOUSE_OF":
            roles[participant_id] = "SPOUSE"
        elif rel_type == "PARENT_OF":
            roles[participant_id] = "CHILD"
        elif rel_type == "CHILD_OF":
            roles[participant_id] = "PARENT"
        elif rel_type == "CARETAKER_OF":
            roles[participant_id] = "CAREGIVER"
        elif rel_type == "SIBLING_OF":
            roles[participant_id] = "SIBLING"
        else:
            roles[participant_id] = "OTHER"

    return roles


# ============================================================================
# Social Context Classification
# ============================================================================


def _classify_social_context(participant_roles: Dict[str, str]) -> str:
    """
    Classify social context based on participant roles.

    Classification Rules:
    1. If only SELF → "solo"
    2. If SPOUSE, PARENT, or CHILD present → "nuclear_family"
    3. If CAREGIVER or SIBLING present (but no nuclear) → "extended_family"
    4. Otherwise → "friends" (default for social events)

    Args:
        participant_roles: Dict mapping participant_id -> role

    Returns:
        Social context string (solo/nuclear_family/extended_family/friends)

    Note: "work" context requires additional heuristics (work hours + location),
          deferred to future enhancement.
    """
    roles_set = set(participant_roles.values())

    # Rule 1: Solo event
    if roles_set == {"SELF"}:
        return "solo"

    # Rule 2: Nuclear family (spouse, parents, children)
    nuclear_roles = {"SPOUSE", "PARENT", "CHILD"}
    if roles_set & nuclear_roles:  # Intersection
        return "nuclear_family"

    # Rule 3: Extended family (caregivers, siblings)
    extended_roles = {"CAREGIVER", "SIBLING"}
    if roles_set & extended_roles:
        return "extended_family"

    # Rule 4: Default to friends (social events without family)
    return "friends"


def _score_social_intimacy(social_context: str) -> str:
    """
    Score social intimacy based on social context.

    Intimacy Levels:
    - HIGH: Nuclear family (spouse, parents, children)
    - MED: Extended family, close friends
    - LOW: Acquaintances, work colleagues, solo

    Args:
        social_context: Social context string

    Returns:
        Intimacy level (HIGH/MED/LOW)
    """
    if social_context == "nuclear_family":
        return "HIGH"
    elif social_context == "extended_family":
        return "MED"
    else:
        # solo, friends, work all default to LOW
        return "LOW"


# ============================================================================
# Boolean Flags
# ============================================================================


def _check_partner_present(participant_roles: Dict[str, str]) -> bool:
    """Check if spouse/partner is present in event."""
    return "SPOUSE" in participant_roles.values()


def _check_parent_present(participant_roles: Dict[str, str]) -> bool:
    """Check if parent is present in event (actor's parent)."""
    return "PARENT" in participant_roles.values()


# ============================================================================
# Main Entry Point
# ============================================================================


async def run(message: Any, context: Any, **config: Any) -> Dict[str, Any]:
    """
    M07: Family Graph Resolver - Resolve social context from family relationships.

    Args:
        message: BusMessage with .payload, .trace_id, .offset
        context: PipelineContext with .syscalls, .logger, .config
        **config: Module configuration
            - cache_ttl_seconds: Cache TTL (default 300s = 5 minutes)
            - default_social_context: Fallback context (default "solo")
            - default_social_intimacy: Fallback intimacy (default "LOW")
            - max_participants_to_resolve: Max participants to process (default 20)

    Returns:
        Enriched envelope dict with social context fields:
            - num_participants: INTEGER
            - participant_roles_json: JSON string
            - has_partner_present: BOOLEAN
            - has_parent_present: BOOLEAN
            - is_solo_event: BOOLEAN
            - social_context: TEXT
            - social_intimacy: TEXT
            - social_resolved_at_utc: ISO timestamp

    Performance: ≤8ms P95 (cached lookups)

    Contract: k0/contracts/modules/social.family_graph_resolve.v1.yaml
    """
    # Parse envelope from message payload
    envelope = (
        json.loads(message.payload)
        if isinstance(message.payload, (str, bytes))
        else message.payload
    )

    # Log module start
    context.logger.debug(
        "M07 social.family_graph_resolve starting",
        extra={
            "module": "social.family_graph_resolve",
            "trace_id": message.trace_id,
            "event_id": envelope.get("event_id"),
        },
    )

    start_time = time.perf_counter()

    # Extract configuration
    default_context = config.get("default_social_context", "solo")
    default_intimacy = config.get("default_social_intimacy", "LOW")
    max_participants = config.get("max_participants_to_resolve", 20)

    # Extract actor and participants
    actor_id = envelope.get("actor_id")
    if not actor_id:
        # Fallback: Try to extract from body
        body = envelope.get("body", {})
        actor_id = body.get("actor_id", "unknown_actor")

    body = envelope.get("body", {})
    participants = body.get("participants", [])

    # Handle missing or empty participants
    if not participants:
        # Solo event (actor only)
        result = _build_solo_response()
        context.logger.debug(
            "M07 social.family_graph_resolve completed (solo)",
            extra={
                "module": "social.family_graph_resolve",
                "trace_id": message.trace_id,
                "social_context": "solo",
            },
        )
        return {**envelope, **result}

    # Limit participant count
    if len(participants) > max_participants:
        participants = participants[:max_participants]

    # Check if truly solo (only actor in participants list)
    if len(participants) == 1 and participants[0] == actor_id:
        result = _build_solo_response()
        context.logger.debug(
            "M07 social.family_graph_resolve completed (solo)",
            extra={
                "module": "social.family_graph_resolve",
                "trace_id": message.trace_id,
                "social_context": "solo",
            },
        )
        return {**envelope, **result}

    try:
        # Step 1: Lookup relationships (cached)
        relationships = _lookup_relationships(actor_id)

        # Step 2: Map participant roles
        participant_roles = _map_participant_roles(actor_id, participants, relationships)

        # Step 3: Classify social context
        social_context = _classify_social_context(participant_roles)

        # Step 4: Score social intimacy
        social_intimacy = _score_social_intimacy(social_context)

        # Step 5: Compute boolean flags
        has_partner = _check_partner_present(participant_roles)
        has_parent = _check_parent_present(participant_roles)
        is_solo = len(participants) == 1

        # Build response
        result = {
            "num_participants": len(participants),
            "participant_roles_json": json.dumps(participant_roles),
            "has_partner_present": has_partner,
            "has_parent_present": has_parent,
            "is_solo_event": is_solo,
            "social_context": social_context,
            "social_intimacy": social_intimacy,
            "social_resolved_at_utc": datetime.now(timezone.utc).isoformat(),
        }

        # Track performance (could emit metric here)
        elapsed_ms = (time.perf_counter() - start_time) * 1000

        # Log completion
        context.logger.debug(
            "M07 social.family_graph_resolve completed",
            extra={
                "module": "social.family_graph_resolve",
                "trace_id": message.trace_id,
                "social_context": social_context,
                "social_intimacy": social_intimacy,
                "num_participants": len(participants),
                "elapsed_ms": elapsed_ms,
            },
        )

        # Return enriched envelope (merge social fields into original envelope)
        return {**envelope, **result}

    except Exception as e:
        # Log error
        context.logger.error(
            "M07 social.family_graph_resolve error",
            extra={
                "module": "social.family_graph_resolve",
                "trace_id": message.trace_id,
                "error": str(e),
            },
        )

        # Fallback to default values on error
        fallback_result = {
            "num_participants": len(participants),
            "participant_roles_json": json.dumps({p: "OTHER" for p in participants}),  # All unknown
            "has_partner_present": False,
            "has_parent_present": False,
            "is_solo_event": False,
            "social_context": default_context,
            "social_intimacy": default_intimacy,
            "social_resolved_at_utc": datetime.now(timezone.utc).isoformat(),
            "error": str(e),
        }
        return {**envelope, **fallback_result}


def _build_solo_response() -> Dict[str, Any]:
    """Build response for solo events (no participants or only actor)."""
    return {
        "num_participants": 1,
        "participant_roles_json": json.dumps({}),  # Empty roles for solo
        "has_partner_present": False,
        "has_parent_present": False,
        "is_solo_event": True,
        "social_context": "solo",
        "social_intimacy": "LOW",
        "social_resolved_at_utc": datetime.now(timezone.utc).isoformat(),
    }


# ============================================================================
# Metrics & Observability
# ============================================================================


def get_metrics() -> Dict[str, Any]:
    """
    Get module metrics for observability.

    Returns:
        Dict with cache statistics and relationship type distribution
    """
    cache_info = _get_relationships_cached.cache_info()

    return {
        "cache_hits": _cache_stats["hits"],
        "cache_misses": _cache_stats["misses"],
        "cache_hit_rate": (
            _cache_stats["hits"] / (_cache_stats["hits"] + _cache_stats["misses"])
            if (_cache_stats["hits"] + _cache_stats["misses"]) > 0
            else 0.0
        ),
        "db_queries": _cache_stats["db_queries"],
        "relationship_type_counts": _cache_stats["relationship_type_counts"].copy(),
        "lru_cache_size": cache_info.currsize,
        "lru_cache_max_size": cache_info.maxsize,
    }


def reset_metrics() -> None:
    """Reset all metrics (for testing)."""
    _cache_stats["hits"] = 0
    _cache_stats["misses"] = 0
    _cache_stats["db_queries"] = 0
    _cache_stats["relationship_type_counts"] = {
        "SPOUSE_OF": 0,
        "PARENT_OF": 0,
        "CHILD_OF": 0,
        "CARETAKER_OF": 0,
        "SIBLING_OF": 0,
    }
    _get_relationships_cached.cache_clear()


def clear_cache() -> None:
    """Clear relationship cache (for testing or cache invalidation)."""
    _get_relationships_cached.cache_clear()
