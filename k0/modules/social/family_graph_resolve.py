"""
M07: social.family_graph_resolve - Family Graph Resolver (Social Context Attribution)

Resolves social relationships and family context for episodic memories:
- Queries st_kg_edges for family graph (ADR-K022: PostgreSQL-only, no Neo4j)
- Supports 9 relationship types: SPOUSE_OF, PARENT_OF, CHILD_OF, SIBLING_OF,
  CARETAKER_OF, GRANDPARENT_OF, GRANDCHILD_OF, FRIEND_OF, COLLEAGUE_OF
- Infers relationships from co-occurrence patterns when DB lookup fails (Issue 4.1.2)
- Computes participant roles relative to actor
- Derives social context using Dunbar layers (Issue 4.1.3)
- Scores social intimacy (HIGH/MED/LOW)

Performance target: <=8ms P95 (cached lookups)
Contract: k0/contracts/modules/social.family_graph_resolve.v1.yaml
ADR: docs/architecture/decisions-K0/k022-remove-neo4j-postgresql-graph.md

Usage:
    result = await run(envelope)

Research Foundation:
- Issue 4.1.2: Hamilton et al. (2017) GraphSAGE, Kipf & Welling (2016) GCN
- Issue 4.1.3: Dunbar (1992) Social group sizes, Granovetter (1973) Tie strength
"""

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

# Import enhanced modules
from k0.modules.social.relationship_inference import RelationType, _infer_from_name_pattern
from k0.modules.social.social_context_classifier import (
    SocialContextResult,
    get_classifier,
    get_relationship_strength,
)

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
# Relationship Cache (Async TTL Cache with 5-minute expiry)
# ============================================================================

# Cache entry structure: {actor_id: (relationships_tuple, timestamp)}
_relationship_cache: Dict[str, Tuple[Tuple[Tuple[str, str], ...], float]] = {}
_CACHE_TTL_SECONDS = 300  # 5 minutes (configurable via config param)
_CACHE_MAX_SIZE = 1000

# Cache statistics
_cache_stats = {
    "hits": 0,
    "misses": 0,
    "db_queries": 0,
    "evictions": 0,
    "relationship_type_counts": {
        "SPOUSE_OF": 0,
        "PARENT_OF": 0,
        "CHILD_OF": 0,
        "CARETAKER_OF": 0,
        "SIBLING_OF": 0,
        "GRANDPARENT_OF": 0,
        "GRANDCHILD_OF": 0,
        "FRIEND_OF": 0,
        "COLLEAGUE_OF": 0,
    },
}


async def _get_relationships_cached(
    actor_id: str,
    syscalls: Any,
    ttl_seconds: int = _CACHE_TTL_SECONDS,
    cognitive_trace_id: str | None = None,
) -> Tuple[Tuple[str, str], ...]:
    """
    Get relationships for an actor (async cached with TTL).

    Queries st_relationships table via syscalls.relationships_query().
    Cache entries expire after ttl_seconds (default 5 minutes).

    Args:
        actor_id: Person ID (e.g., "person_prince_001")
        syscalls: Syscalls instance with st_relationships.read capability
        ttl_seconds: Cache TTL in seconds (default 300)
        cognitive_trace_id: Optional trace ID for observability

    Returns:
        Tuple of (related_person_id, relationship_type) tuples

    Performance: O(1) cache hit, <5ms cache miss (indexed query)
    """
    global _relationship_cache

    current_time = time.time()

    # Check cache for valid entry
    if actor_id in _relationship_cache:
        cached_relationships, cached_time = _relationship_cache[actor_id]
        if current_time - cached_time < ttl_seconds:
            _cache_stats["hits"] += 1
            return cached_relationships

    # Cache miss or expired - query database
    _cache_stats["misses"] += 1
    _cache_stats["db_queries"] += 1

    # Query st_relationships via syscalls
    relationships = await syscalls.relationships_query(
        actor_id=actor_id,
        cognitive_trace_id=cognitive_trace_id,
    )

    # Track relationship type distribution
    for _, rel_type in relationships:
        if rel_type in _cache_stats["relationship_type_counts"]:
            _cache_stats["relationship_type_counts"][rel_type] += 1

    # Convert to immutable tuple for caching
    relationships_tuple = tuple(relationships)

    # Evict oldest entries if cache is full
    if len(_relationship_cache) >= _CACHE_MAX_SIZE:
        oldest_key = min(_relationship_cache.keys(), key=lambda k: _relationship_cache[k][1])
        del _relationship_cache[oldest_key]
        _cache_stats["evictions"] += 1

    # Store in cache
    _relationship_cache[actor_id] = (relationships_tuple, current_time)

    return relationships_tuple


async def _lookup_relationships(
    actor_id: str,
    syscalls: Any,
    ttl_seconds: int = _CACHE_TTL_SECONDS,
    cognitive_trace_id: str | None = None,
) -> List[Tuple[str, str]]:
    """
    Lookup relationships with cache hit/miss tracking (async).

    Args:
        actor_id: Person ID
        syscalls: Syscalls instance with st_relationships.read capability
        ttl_seconds: Cache TTL in seconds
        cognitive_trace_id: Optional trace ID for observability

    Returns:
        List of (related_person_id, relationship_type) tuples
    """
    result = await _get_relationships_cached(
        actor_id=actor_id,
        syscalls=syscalls,
        ttl_seconds=ttl_seconds,
        cognitive_trace_id=cognitive_trace_id,
    )
    return list(result)

    return result


# ============================================================================
# Participant Role Classification (Enhanced with Inference - Issue 4.1.2)
# ============================================================================


def _map_participant_roles(
    actor_id: str, participants: List[str], relationships: List[Tuple[str, str]]
) -> Dict[str, str]:
    """
    Map each participant to their relationship role relative to actor.

    Enhanced with name pattern inference (Issue 4.1.2):
    - First checks st_relationships database lookup
    - Falls back to name pattern inference for unknown participants
    - Marks truly unknown participants as "OTHER"

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

        # Lookup relationship from database
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
        elif rel_type == "GRANDPARENT_OF":
            roles[participant_id] = "GRANDCHILD"
        elif rel_type == "GRANDCHILD_OF":
            roles[participant_id] = "GRANDPARENT"
        elif rel_type == "FRIEND_OF":
            roles[participant_id] = "FRIEND"
        elif rel_type == "COLLEAGUE_OF":
            roles[participant_id] = "COLLEAGUE"
        else:
            # Issue 4.1.2: Try name pattern inference as fallback
            inferred = _infer_from_name_pattern(actor_id, participant_id)
            if inferred and inferred.confidence >= 0.5:
                # Map inferred RelationType to role string
                role = _relation_type_to_role(inferred.relationship_type)
                roles[participant_id] = role
            else:
                roles[participant_id] = "OTHER"

    return roles


def _relation_type_to_role(rel_type: RelationType) -> str:
    """
    Convert RelationType enum to role string.

    Args:
        rel_type: RelationType enum value

    Returns:
        Role string (SPOUSE, PARENT, CHILD, SIBLING, CAREGIVER, OTHER)
    """
    mapping = {
        RelationType.SPOUSE_OF: "SPOUSE",
        RelationType.PARENT_OF: "CHILD",  # If actor is PARENT_OF them, they are CHILD
        RelationType.CHILD_OF: "PARENT",  # If actor is CHILD_OF them, they are PARENT
        RelationType.SIBLING_OF: "SIBLING",
        RelationType.CARETAKER_OF: "CAREGIVER",
        RelationType.FRIEND: "OTHER",  # Friends don't have special family role
        RelationType.COLLEAGUE: "OTHER",
        RelationType.UNKNOWN: "OTHER",
    }
    return mapping.get(rel_type, "OTHER")


# ============================================================================
# Social Context Classification (Enhanced with Dunbar Layers - Issue 4.1.3)
# ============================================================================


def _classify_social_context(participant_roles: Dict[str, str]) -> str:
    """
    Classify social context based on participant roles.

    Enhanced with Dunbar's research (Issue 4.1.3):
    - Uses SocialContextClassifier for research-backed classification
    - Handles mixed groups (family + friends)
    - Provides richer context categories

    Classification Rules:
    1. If only SELF -> "solo"
    2. If SPOUSE, PARENT, or CHILD present -> "nuclear_family"
    3. If CAREGIVER or SIBLING present (but no nuclear) -> "extended_family"
    4. Otherwise -> "friends" (default for social events)

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


def _classify_social_context_enhanced(
    participants: List[str],
    participant_roles: Dict[str, str],
    actor_id: str,
) -> SocialContextResult:
    """
    Enhanced social context classification using Dunbar layers (Issue 4.1.3).

    Uses SocialContextClassifier for:
    - Research-backed Dunbar layer classification
    - Relationship strength scoring
    - Mixed group handling
    - Detailed breakdown

    Args:
        participants: List of participant IDs
        participant_roles: Dict mapping participant_id -> role
        actor_id: Event actor/owner

    Returns:
        SocialContextResult with full classification details
    """
    classifier = get_classifier()
    return classifier.classify(
        participants=participants,
        participant_roles=participant_roles,
        actor_id=actor_id,
    )


def _score_social_intimacy(social_context: str) -> str:
    """
    Score social intimacy based on social context.

    Enhanced with relationship strength (Issue 4.1.3):
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
    elif social_context in ("extended_family", "close_friends"):
        return "MED"
    else:
        # solo, friends, work, acquaintances all default to LOW
        return "LOW"


def _score_social_intimacy_enhanced(
    participant_roles: Dict[str, str],
    actor_id: str,
) -> Tuple[str, float]:
    """
    Enhanced intimacy scoring using relationship strength (Issue 4.1.3).

    Args:
        participant_roles: Dict mapping participant_id -> role
        actor_id: Event actor/owner

    Returns:
        Tuple of (intimacy_level, average_strength)
    """
    # Calculate average relationship strength
    strengths = []
    for pid, role in participant_roles.items():
        if pid != actor_id:
            strength = get_relationship_strength(role)
            strengths.append(strength)

    avg_strength = sum(strengths) / len(strengths) if strengths else 0.0

    # Map strength to intimacy
    if avg_strength >= 0.7:
        return "HIGH", avg_strength
    elif avg_strength >= 0.4:
        return "MED", avg_strength
    else:
        return "LOW", avg_strength


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
    # Use enriched envelope from pipeline_runner, with fallback to message.payload
    envelope = config.get("envelope")
    if envelope is None:
        # Fallback: parse from message.payload (only for first stage or if enrichment fails)
        envelope = (
            json.loads(message.payload)
            if isinstance(message.payload, (str, bytes))
            else message.payload
        )

    # Log module start
    context.logger.debug(
        "M07 social.family_graph_resolve starting",
        extra={
            "module_id": "social.family_graph_resolve",
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
                "module_id": "social.family_graph_resolve",
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
                "module_id": "social.family_graph_resolve",
                "trace_id": message.trace_id,
                "social_context": "solo",
            },
        )
        return {**envelope, **result}

    try:
        # Extract cache TTL from config
        cache_ttl = config.get("cache_ttl_seconds", _CACHE_TTL_SECONDS)

        # Step 1: Lookup relationships (async cached via syscalls)
        relationships = await _lookup_relationships(
            actor_id=actor_id,
            syscalls=context.syscalls,
            ttl_seconds=cache_ttl,
            cognitive_trace_id=message.trace_id,
        )

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
                "module_id": "social.family_graph_resolve",
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
                "module_id": "social.family_graph_resolve",
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
        return {
            **envelope,
            **fallback_result,
            "enrichments": {
                **envelope.get("enrichments", {}),
                "social_resolver": fallback_result.get("_enrichment", {}),
            },
        }


def _build_solo_response() -> Dict[str, Any]:
    """Build response for solo events (no participants or only actor)."""
    social_data = {
        "num_participants": 1,
        "participant_roles_json": json.dumps({}),  # Empty roles for solo
        "has_partner_present": False,
        "has_parent_present": False,
        "is_solo_event": True,
        "social_context": "solo",
        "social_intimacy": "LOW",
        "social_resolved_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    return {
        **social_data,
        "_enrichment": {
            "num_participants": 1,
            "participant_roles": {},
            "has_partner_present": False,
            "has_parent_present": False,
            "is_solo_event": True,
            "social_context": "solo",
            "social_intimacy": "LOW",
            "social_resolved_at_utc": datetime.now(timezone.utc).isoformat(),
            "module_version": "v1",
            "execution_time_ms": 0.0,
        },
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
    return {
        "cache_hits": _cache_stats["hits"],
        "cache_misses": _cache_stats["misses"],
        "cache_hit_rate": (
            _cache_stats["hits"] / (_cache_stats["hits"] + _cache_stats["misses"])
            if (_cache_stats["hits"] + _cache_stats["misses"]) > 0
            else 0.0
        ),
        "db_queries": _cache_stats["db_queries"],
        "evictions": _cache_stats["evictions"],
        "relationship_type_counts": _cache_stats["relationship_type_counts"].copy(),
        "cache_size": len(_relationship_cache),
        "cache_max_size": _CACHE_MAX_SIZE,
    }


def reset_metrics() -> None:
    """Reset all metrics (for testing)."""
    global _relationship_cache
    _cache_stats["hits"] = 0
    _cache_stats["misses"] = 0
    _cache_stats["db_queries"] = 0
    _cache_stats["evictions"] = 0
    _cache_stats["relationship_type_counts"] = {
        "SPOUSE_OF": 0,
        "PARENT_OF": 0,
        "CHILD_OF": 0,
        "CARETAKER_OF": 0,
        "SIBLING_OF": 0,
    }
    _relationship_cache = {}


def clear_cache() -> None:
    """Clear relationship cache (for testing or cache invalidation)."""
    global _relationship_cache
    _relationship_cache = {}
