"""
M07: social.family_graph_resolve - Family Graph Resolver (Social Context Attribution)

Trust-Then-Fill v2: MW participant_relationships fast path + st_kg_edges fallback.

Waterfall tiers:
  tier0: MW v2 participant_relationships mapping + KG write (~85%)
  tier1: st_kg_edges READ (may have MW-seeded data) (~8%)
  tier2: M02 NER person entities + name-pattern heuristics (~5%)
  tier3: Defaults (solo/unknown) (~2%)

CRITICAL FIX: v1 always returned social_context="friends" because st_kg_edges was
empty. MW v2 provides typed relationships that immediately fix social_context,
has_partner_present, and has_parent_present.

Side effect: MW relationships WRITTEN to st_kg_edges to progressively seed the KG.

Supports 9 relationship types: SPOUSE_OF, PARENT_OF, CHILD_OF, SIBLING_OF,
CARETAKER_OF, GRANDPARENT_OF, GRANDCHILD_OF, FRIEND_OF, COLLEAGUE_OF

Performance target: <=3ms P95 (MW fast path), <=12ms P95 (fallback)
Contract: k0/contracts/modules/social.family_graph_resolve.v2.yaml
ADR: docs/architecture/decisions-K0/k022-remove-neo4j-postgresql-graph.md

Usage:
    result = await run(envelope)

Research Foundation:
- Issue 4.1.2: Hamilton et al. (2017) GraphSAGE, Kipf & Welling (2016) GCN
- Issue 4.1.3: Dunbar (1992) Social group sizes, Granovetter (1973) Tie strength
"""

import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

# Import enhanced modules
from k0.modules.social.relationship_inference import RelationType, _infer_from_name_pattern
from k0.modules.social.social_context_classifier import (
    SocialContextResult,
    get_classifier,
    get_relationship_strength,
)

logger = logging.getLogger(__name__)

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
    social_context: str  # solo/nuclear_family/extended_family/friends/colleagues/community/unknown
    social_intimacy: str  # HIGH/MED/LOW
    social_resolved_at_utc: str
    participant_relationships_json: str  # v2: MW passthrough for M13 column
    social_source: str  # v2: provenance "mw_v2"|"kg_edges"|"ner_heuristic"|"default"


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
# Trust-Then-Fill: MW Relationship Extraction (v2)
# ============================================================================

# Relationship type to social context mapping (from v2 contract)
_RELATIONSHIP_TO_SOCIAL_CONTEXT: Dict[str, str] = {
    "PARENT_OF": "nuclear_family",
    "CHILD_OF": "nuclear_family",
    "SPOUSE_OF": "nuclear_family",
    "SIBLING_OF": "nuclear_family",
    "CAREGIVER_OF": "nuclear_family",
    "GRANDPARENT_OF": "extended_family",
    "AUNT_UNCLE_OF": "extended_family",
    "COUSIN_OF": "extended_family",
    "FRIEND_OF": "friends",
    "COLLEAGUE_OF": "colleagues",
}

# Priority order: nuclear_family > extended_family > friends > colleagues > community > unknown > solo
_SOCIAL_CONTEXT_PRIORITY: Dict[str, int] = {
    "nuclear_family": 7,
    "extended_family": 6,
    "friends": 5,
    "colleagues": 4,
    "community": 3,
    "unknown": 2,
    "solo": 1,
}


def _extract_mw_relationships(body: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
    """
    Extract and validate MW v2 participant_relationships from envelope body.

    Validates that the field is a non-empty list with valid structure.
    Each entry must have at least 'person' and 'relationship_type' keys.

    Args:
        body: Envelope body dict

    Returns:
        Validated list of relationship dicts, or None if missing/invalid.
    """
    rels = body.get("participant_relationships")
    if not rels:
        return None
    if not isinstance(rels, list):
        return None
    if len(rels) == 0:
        return None

    # Validate structure: each entry must have person + relationship_type
    validated = []
    for entry in rels:
        if not isinstance(entry, dict):
            continue
        person = entry.get("person")
        rel_type = entry.get("relationship_type")
        if not person or not rel_type:
            continue
        validated.append(entry)

    return validated if validated else None


def _derive_social_context(relationships: List[Dict[str, Any]]) -> str:
    """
    Derive social_context from MW relationship types using priority mapping.

    Uses relationship_type_to_social_context mapping from v2 contract.
    When multiple participants have different types, highest priority wins.

    Args:
        relationships: List of {person, relationship_type, confidence} dicts

    Returns:
        Social context string (nuclear_family, extended_family, friends, etc.)
    """
    best_context = "unknown"
    best_priority = _SOCIAL_CONTEXT_PRIORITY.get("unknown", 2)

    for rel in relationships:
        rel_type = rel.get("relationship_type", "")
        context = _RELATIONSHIP_TO_SOCIAL_CONTEXT.get(rel_type, "unknown")
        priority = _SOCIAL_CONTEXT_PRIORITY.get(context, 2)
        if priority > best_priority:
            best_priority = priority
            best_context = context

    return best_context


def _derive_family_flags(
    relationships: List[Dict[str, Any]],
) -> Tuple[bool, bool]:
    """
    Derive has_partner_present and has_parent_present from relationship types.

    Args:
        relationships: List of {person, relationship_type, confidence} dicts

    Returns:
        Tuple of (has_partner_present, has_parent_present)
    """
    has_partner = False
    has_parent = False

    for rel in relationships:
        rel_type = rel.get("relationship_type", "")
        if rel_type == "SPOUSE_OF":
            has_partner = True
        if rel_type == "PARENT_OF":
            has_parent = True

    return has_partner, has_parent


def _derive_intimacy_from_context(social_context: str) -> str:
    """
    Derive social_intimacy from social_context.

    Args:
        social_context: Derived social context string

    Returns:
        Intimacy level: HIGH, MED, or LOW
    """
    if social_context == "nuclear_family":
        return "HIGH"
    elif social_context in ("extended_family", "friends"):
        return "MED"
    else:
        return "LOW"


def _build_participant_roles_from_mw(
    actor_id: str,
    relationships: List[Dict[str, Any]],
) -> Dict[str, str]:
    """
    Build participant_roles dict from MW relationships.

    Maps MW relationship_type to role strings compatible with existing output format.

    Args:
        actor_id: Actor performing the action
        relationships: List of {person, relationship_type, confidence} dicts

    Returns:
        Dict mapping person_id to role string
    """
    _MW_REL_TO_ROLE: Dict[str, str] = {
        "SPOUSE_OF": "SPOUSE",
        "PARENT_OF": "CHILD",  # Actor is parent_of person -> person's role is CHILD
        "CHILD_OF": "PARENT",  # Actor is child_of person -> person's role is PARENT
        "SIBLING_OF": "SIBLING",
        "CAREGIVER_OF": "CAREGIVER",
        "GRANDPARENT_OF": "GRANDCHILD",  # Actor is grandparent -> person is GRANDCHILD
        "GRANDCHILD_OF": "GRANDPARENT",  # Actor is grandchild -> person is GRANDPARENT
        "AUNT_UNCLE_OF": "AUNT_UNCLE",
        "COUSIN_OF": "COUSIN",
        "FRIEND_OF": "FRIEND",
        "COLLEAGUE_OF": "COLLEAGUE",
    }

    roles: Dict[str, str] = {actor_id: "SELF"}
    for rel in relationships:
        person = rel.get("person", "")
        rel_type = rel.get("relationship_type", "")
        role = _MW_REL_TO_ROLE.get(rel_type, "OTHER")
        if person and person != actor_id:
            roles[person] = role

    return roles


async def _write_relationships_to_kg(
    relationships: List[Dict[str, Any]],
    actor_id: str,
    syscalls: Any,
    confidence_threshold: float = 0.5,
    source_tag: str = "mw_v2",
    cognitive_trace_id: str | None = None,
) -> None:
    """
    Write MW relationships to st_kg_edges for progressive KG seeding.

    Non-blocking: if write fails, log and continue (social output still valid).
    Only writes relationships with confidence >= threshold.

    Args:
        relationships: List of {person, relationship_type, confidence} dicts
        actor_id: Actor ID (source entity)
        syscalls: Kernel syscalls (may or may not have kg_edges_upsert)
        confidence_threshold: Minimum confidence to write (default 0.5)
        source_tag: Source tag for KG writes (default "mw_v2")
        cognitive_trace_id: Optional trace ID for observability
    """
    try:
        # Check if syscalls has kg_edges_upsert capability
        write_fn = getattr(syscalls, "kg_edges_upsert", None)
        if write_fn is None:
            # Syscall not yet implemented -- log and skip (non-blocking)
            logger.debug(
                "M07 kg_edges_upsert not available, skipping KG write",
                extra={
                    "module_id": "social.family_graph_resolve",
                    "actor_id": actor_id,
                    "num_relationships": len(relationships),
                },
            )
            return

        for rel in relationships:
            confidence = rel.get("confidence", 0.0)
            if confidence < confidence_threshold:
                continue
            await write_fn(
                subject_id=actor_id,
                predicate=rel.get("relationship_type", "UNKNOWN"),
                object_id=rel.get("person", ""),
                confidence=confidence,
                source=source_tag,
                cognitive_trace_id=cognitive_trace_id,
            )
    except Exception as exc:
        # KG_EDGES_WRITE_FAILED: log_and_continue per contract failure mode
        logger.warning(
            "M07 st_kg_edges write failed (non-blocking)",
            extra={
                "module_id": "social.family_graph_resolve",
                "actor_id": actor_id,
                "error": str(exc),
            },
        )


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
    M07: Family Graph Resolver - Trust-Then-Fill v2.

    4-tier waterfall:
      tier0: MW participant_relationships mapping + st_kg_edges WRITE (~85%)
      tier1: st_kg_edges READ (may have MW-seeded data) (~8%)
      tier2: NER + name-pattern heuristics (~5%)
      tier3: Defaults (solo/unknown) (~2%)

    Args:
        message: BusMessage with .payload, .trace_id, .offset
        context: PipelineContext with .syscalls, .logger, .config
        **config: Module configuration
            - cache_ttl_seconds: Cache TTL (default 300s = 5 minutes)
            - default_social_context: Fallback context (default "solo")
            - default_social_intimacy: Fallback intimacy (default "LOW")
            - max_participants_to_resolve: Max participants to process (default 20)
            - kg_write_confidence_threshold: Min MW confidence for KG write (default 0.5)
            - kg_write_source_tag: Source tag for KG writes (default "mw_v2")

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
            - participant_relationships_json: TEXT (v2: MW passthrough)
            - social_source: TEXT (v2: provenance)

    Performance: <=3ms P95 (MW fast path), <=12ms P95 (fallback)

    Contract: k0/contracts/modules/social.family_graph_resolve.v2.yaml
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
    kg_confidence_threshold = config.get("kg_write_confidence_threshold", 0.5)
    kg_source_tag = config.get("kg_write_source_tag", "mw_v2")

    # Extract actor and participants
    actor_id = envelope.get("actor_id")
    if not actor_id:
        # Fallback: Try to extract from body
        body = envelope.get("body", {})
        actor_id = body.get("actor_id", "unknown_actor")

    body = envelope.get("body", {})
    participants = body.get("participants", [])

    # ---------------------------------------------------------------
    # TIER 0: MW participant_relationships fast path
    # ---------------------------------------------------------------
    mw_rels = _extract_mw_relationships(body)

    if mw_rels is not None:
        try:
            # Derive social outputs from MW relationships (no DB READ)
            social_context = _derive_social_context(mw_rels)
            has_partner, has_parent = _derive_family_flags(mw_rels)
            social_intimacy = _derive_intimacy_from_context(social_context)
            participant_roles = _build_participant_roles_from_mw(actor_id, mw_rels)
            num_participants = len(participant_roles)
            is_solo = num_participants <= 1

            # Passthrough MW relationships for M13 new column
            participant_relationships_json = json.dumps(mw_rels)
            social_source = "mw_v2"

            # Non-blocking st_kg_edges WRITE (progressive KG seeding)
            await _write_relationships_to_kg(
                relationships=mw_rels,
                actor_id=actor_id,
                syscalls=context.syscalls,
                confidence_threshold=kg_confidence_threshold,
                source_tag=kg_source_tag,
                cognitive_trace_id=message.trace_id,
            )

            result = {
                "num_participants": num_participants,
                "participant_roles_json": json.dumps(participant_roles),
                "has_partner_present": has_partner,
                "has_parent_present": has_parent,
                "is_solo_event": is_solo,
                "social_context": social_context,
                "social_intimacy": social_intimacy,
                "social_resolved_at_utc": datetime.now(timezone.utc).isoformat(),
                "participant_relationships_json": participant_relationships_json,
                "social_source": social_source,
            }

            elapsed_ms = (time.perf_counter() - start_time) * 1000
            context.logger.debug(
                "M07 social.family_graph_resolve completed (tier0 mw_v2)",
                extra={
                    "module_id": "social.family_graph_resolve",
                    "trace_id": message.trace_id,
                    "social_context": social_context,
                    "social_source": social_source,
                    "num_participants": num_participants,
                    "elapsed_ms": elapsed_ms,
                },
            )
            return {**envelope, **result}

        except Exception as exc:
            # MW_RELATIONSHIPS_MALFORMED: fall through to tier1
            context.logger.warning(
                "M07 MW relationships malformed, falling back to tier1",
                extra={
                    "module_id": "social.family_graph_resolve",
                    "trace_id": message.trace_id,
                    "error": str(exc),
                },
            )
            # Fall through to tier1/2/3

    # ---------------------------------------------------------------
    # Handle solo events (no participants at all)
    # ---------------------------------------------------------------
    if not participants:
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
        # ---------------------------------------------------------------
        # TIER 1: st_kg_edges READ (may have data from previous MW writes)
        # ---------------------------------------------------------------
        cache_ttl = config.get("cache_ttl_seconds", _CACHE_TTL_SECONDS)

        relationships = await _lookup_relationships(
            actor_id=actor_id,
            syscalls=context.syscalls,
            ttl_seconds=cache_ttl,
            cognitive_trace_id=message.trace_id,
        )

        if relationships:
            # KG edges found -- use existing v1 logic as fallback
            participant_roles = _map_participant_roles(actor_id, participants, relationships)
            social_context = _classify_social_context(participant_roles)
            social_intimacy = _score_social_intimacy(social_context)
            has_partner = _check_partner_present(participant_roles)
            has_parent = _check_parent_present(participant_roles)
            is_solo = len(participants) == 1
            social_source = "kg_edges"

            result = {
                "num_participants": len(participants),
                "participant_roles_json": json.dumps(participant_roles),
                "has_partner_present": has_partner,
                "has_parent_present": has_parent,
                "is_solo_event": is_solo,
                "social_context": social_context,
                "social_intimacy": social_intimacy,
                "social_resolved_at_utc": datetime.now(timezone.utc).isoformat(),
                "participant_relationships_json": json.dumps([]),
                "social_source": social_source,
            }

            elapsed_ms = (time.perf_counter() - start_time) * 1000
            context.logger.debug(
                "M07 social.family_graph_resolve completed (tier1 kg_edges)",
                extra={
                    "module_id": "social.family_graph_resolve",
                    "trace_id": message.trace_id,
                    "social_context": social_context,
                    "social_source": social_source,
                    "num_participants": len(participants),
                    "elapsed_ms": elapsed_ms,
                },
            )
            return {**envelope, **result}

        # ---------------------------------------------------------------
        # TIER 2: NER + name-pattern heuristics
        # ---------------------------------------------------------------
        # Use existing _map_participant_roles which falls back to
        # _infer_from_name_pattern for unresolved participants
        participant_roles = _map_participant_roles(actor_id, participants, relationships)

        # Check if name-pattern inference resolved anything beyond SELF/OTHER
        has_inferred = any(role not in ("SELF", "OTHER") for role in participant_roles.values())

        if has_inferred:
            social_context = _classify_social_context(participant_roles)
            social_intimacy = _score_social_intimacy(social_context)
            has_partner = _check_partner_present(participant_roles)
            has_parent = _check_parent_present(participant_roles)
            is_solo = len(participants) == 1
            social_source = "ner_heuristic"

            result = {
                "num_participants": len(participants),
                "participant_roles_json": json.dumps(participant_roles),
                "has_partner_present": has_partner,
                "has_parent_present": has_parent,
                "is_solo_event": is_solo,
                "social_context": social_context,
                "social_intimacy": social_intimacy,
                "social_resolved_at_utc": datetime.now(timezone.utc).isoformat(),
                "participant_relationships_json": json.dumps([]),
                "social_source": social_source,
            }

            elapsed_ms = (time.perf_counter() - start_time) * 1000
            context.logger.debug(
                "M07 social.family_graph_resolve completed (tier2 ner_heuristic)",
                extra={
                    "module_id": "social.family_graph_resolve",
                    "trace_id": message.trace_id,
                    "social_context": social_context,
                    "social_source": social_source,
                    "num_participants": len(participants),
                    "elapsed_ms": elapsed_ms,
                },
            )
            return {**envelope, **result}

        # ---------------------------------------------------------------
        # TIER 3: Defaults (no relationship data from any source)
        # ---------------------------------------------------------------
        # Multiple participants but no relationships resolved -> "unknown"
        social_context = "unknown" if len(participants) > 1 else "solo"
        social_intimacy = "LOW"
        social_source = "default"

        result = {
            "num_participants": len(participants),
            "participant_roles_json": json.dumps(participant_roles),
            "has_partner_present": False,
            "has_parent_present": False,
            "is_solo_event": len(participants) <= 1,
            "social_context": social_context,
            "social_intimacy": social_intimacy,
            "social_resolved_at_utc": datetime.now(timezone.utc).isoformat(),
            "participant_relationships_json": json.dumps([]),
            "social_source": social_source,
        }

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        context.logger.debug(
            "M07 social.family_graph_resolve completed (tier3 default)",
            extra={
                "module_id": "social.family_graph_resolve",
                "trace_id": message.trace_id,
                "social_context": social_context,
                "social_source": social_source,
                "num_participants": len(participants),
                "elapsed_ms": elapsed_ms,
            },
        )
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
            "participant_roles_json": json.dumps({p: "OTHER" for p in participants}),
            "has_partner_present": False,
            "has_parent_present": False,
            "is_solo_event": False,
            "social_context": default_context,
            "social_intimacy": default_intimacy,
            "social_resolved_at_utc": datetime.now(timezone.utc).isoformat(),
            "participant_relationships_json": json.dumps([]),
            "social_source": "default",
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
        "participant_roles_json": json.dumps({}),
        "has_partner_present": False,
        "has_parent_present": False,
        "is_solo_event": True,
        "social_context": "solo",
        "social_intimacy": "LOW",
        "social_resolved_at_utc": datetime.now(timezone.utc).isoformat(),
        "participant_relationships_json": json.dumps([]),
        "social_source": "default",
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
            "module_version": "v2",
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
