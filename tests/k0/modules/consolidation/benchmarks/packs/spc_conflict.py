"""SPC-UQ conflicting fragments pack.

Focus: Test SPC-UQ handling of contradictory/conflicting fragments.
Key metrics:
- uncertainty_on_conflict > 0.5 when fragments contradict
- conflict_detection_rate >= 0.9
- resolution_strategy selection accuracy
- calibrated uncertainty when sources disagree
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

# ─────────────────────────────────────────────────────────────────────────────
# Domain dataclasses
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class Entity:
    """Entity in the conflict scenario world."""

    id: str
    type: str
    name: str
    attributes: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ConflictingFragment:
    """Memory fragment that may conflict with others."""

    id: str
    content: str
    timestamp: str
    provenance_type: str
    confidence: float
    source_id: Optional[str] = None
    entities_mentioned: List[str] = field(default_factory=list)
    conflicts_with: List[str] = field(default_factory=list)  # IDs of conflicting fragments
    conflict_type: Optional[str] = None  # temporal, spatial, factual, attribution


@dataclass
class ConflictCluster:
    """Group of fragments that contradict each other."""

    id: str
    fragment_ids: List[str]
    conflict_type: str  # temporal, spatial, factual, attribution
    resolution_hint: Optional[str] = None  # recency, authority, corroboration, none
    ground_truth_fragment: Optional[str] = None  # Which fragment is actually correct


@dataclass
class IncompleteEpisode:
    """Incomplete episode for SPC-UQ reconstruction.

    Format matches SPC-UQ algorithm expectations for conflict scenarios:
    - None values for location_name, participants, activity_type indicate gaps
    - High ambiguity_score indicates conflicting information
    """

    episode_id: str
    summary: str
    timestamp: int
    location_name: Optional[str] = None  # None = gap for reconstruction
    participants: Optional[List[str]] = None  # None = gap for reconstruction
    activity_type: Optional[str] = None  # None = gap for reconstruction
    ambiguity_score: float = 0.8  # High ambiguity for conflict scenarios


@dataclass
class Edge:
    """Semantic edge between entities."""

    source: str
    target: str
    relation: str
    weight: float = 1.0


# ─────────────────────────────────────────────────────────────────────────────
# Schema loader
# ─────────────────────────────────────────────────────────────────────────────


def _load_schemas() -> List[Dict[str, Any]]:
    """Load all schema files from the schemas directory."""
    schemas_dir = Path(__file__).parent / "schemas"
    schemas = []
    for schema_file in schemas_dir.glob("*.json"):
        try:
            with open(schema_file, "r", encoding="utf-8") as f:
                schema = json.load(f)
                schemas.append(schema)
        except (json.JSONDecodeError, IOError):
            continue
    return schemas


# ─────────────────────────────────────────────────────────────────────────────
# World construction helpers
# ─────────────────────────────────────────────────────────────────────────────


def _create_entities() -> List[Entity]:
    """Create entities for conflict scenario."""
    return [
        # People
        Entity("person_alice", "person", "Alice", {"role": "parent", "reliability": "high"}),
        Entity("person_bob", "person", "Bob", {"role": "parent", "reliability": "high"}),
        Entity("person_charlie", "person", "Charlie", {"role": "child", "age": 12}),
        Entity("person_diana", "person", "Diana", {"role": "child", "age": 9}),
        Entity("person_neighbor", "person", "Mr. Wilson", {"role": "neighbor", "reliability": "medium"}),
        Entity("person_teacher", "person", "Ms. Garcia", {"role": "teacher", "reliability": "high"}),
        # Locations
        Entity("loc_home", "location", "Home", {"type": "residence"}),
        Entity("loc_park", "location", "Central Park", {"type": "recreation"}),
        Entity("loc_mall", "location", "Shopping Mall", {"type": "shopping"}),
        Entity("loc_school", "location", "Middle School", {"type": "school"}),
        Entity("loc_library", "location", "Public Library", {"type": "public"}),
        Entity("loc_restaurant", "location", "Pizza Place", {"type": "dining"}),
        # Time slots
        Entity("time_3pm", "time_slot", "3:00 PM", {"hour": 15}),
        Entity("time_4pm", "time_slot", "4:00 PM", {"hour": 16}),
        Entity("time_5pm", "time_slot", "5:00 PM", {"hour": 17}),
        # Objects
        Entity("obj_car", "object", "Family Car", {"type": "vehicle"}),
        Entity("obj_bike", "object", "Charlie's Bike", {"type": "vehicle"}),
        Entity("obj_phone", "object", "Alice's Phone", {"type": "device"}),
    ]


def _create_conflicting_fragments() -> List[ConflictingFragment]:
    """Create fragments with explicit conflicts.

    Conflict types:
    - temporal: Disagreement about when something happened
    - spatial: Disagreement about where something happened
    - factual: Disagreement about what happened
    - attribution: Disagreement about who did something
    """
    return [
        # ═══════════════════════════════════════════════════════════════════
        # Conflict Cluster 1: TEMPORAL - When did Charlie get home?
        # ═══════════════════════════════════════════════════════════════════
        ConflictingFragment(
            "frag_temp_1a",
            "Charlie came home at 3:30 PM",
            "2024-02-15T15:35:00",
            "sensory",
            0.80,
            "person_alice",
            ["person_charlie", "loc_home", "time_3pm"],
            ["frag_temp_1b", "frag_temp_1c"],
            "temporal",
        ),
        ConflictingFragment(
            "frag_temp_1b",
            "Saw Charlie arrive around 4:15 PM, was watering plants",
            "2024-02-15T16:20:00",
            "sensory",
            0.65,
            "person_neighbor",
            ["person_charlie", "loc_home", "time_4pm"],
            ["frag_temp_1a", "frag_temp_1c"],
            "temporal",
        ),
        ConflictingFragment(
            "frag_temp_1c",
            "School bus dropped Charlie at 3:45 PM",
            "2024-02-15T15:45:00",
            "routine",
            0.75,
            None,
            ["person_charlie", "loc_home"],
            ["frag_temp_1a", "frag_temp_1b"],
            "temporal",
        ),
        # Corroborating fragment (not conflicting)
        ConflictingFragment(
            "frag_temp_1d",
            "Bus tracking shows arrival at Oak Street stop 3:42 PM",
            "2024-02-15T15:42:00",
            "calendar",
            0.95,
            "obj_phone",
            ["person_charlie"],
            [],  # No conflicts - this corroborates 1c
            None,
        ),
        # ═══════════════════════════════════════════════════════════════════
        # Conflict Cluster 2: SPATIAL - Where was the family on Saturday?
        # ═══════════════════════════════════════════════════════════════════
        ConflictingFragment(
            "frag_spat_2a",
            "We went to the mall on Saturday afternoon",
            "2024-02-17T14:00:00",
            "message",
            0.75,
            "person_alice",
            ["loc_mall"],
            ["frag_spat_2b"],
            "spatial",
        ),
        ConflictingFragment(
            "frag_spat_2b",
            "Saturday was park day, remember the picnic?",
            "2024-02-17T14:00:00",
            "message",
            0.80,
            "person_bob",
            ["loc_park"],
            ["frag_spat_2a"],
            "spatial",
        ),
        # Photo metadata (high confidence)
        ConflictingFragment(
            "frag_spat_2c",
            "Photo EXIF: GPS coordinates match Central Park, 2:15 PM",
            "2024-02-17T14:15:00",
            "sensory",
            0.95,
            "obj_phone",
            ["loc_park"],
            [],  # Corroborates 2b
            None,
        ),
        # ═══════════════════════════════════════════════════════════════════
        # Conflict Cluster 3: FACTUAL - What happened at school meeting?
        # ═══════════════════════════════════════════════════════════════════
        ConflictingFragment(
            "frag_fact_3a",
            "Diana got an award at the school meeting",
            "2024-02-16T19:00:00",
            "message",
            0.70,
            "person_bob",
            ["person_diana", "loc_school"],
            ["frag_fact_3b"],
            "factual",
        ),
        ConflictingFragment(
            "frag_fact_3b",
            "Diana's class performed a song, no awards given",
            "2024-02-16T19:30:00",
            "message",
            0.75,
            "person_alice",
            ["person_diana", "loc_school"],
            ["frag_fact_3a"],
            "factual",
        ),
        ConflictingFragment(
            "frag_fact_3c",
            "Official: 3rd grade performed 'Spring Song', attendance certificates distributed",
            "2024-02-16T20:00:00",
            "calendar",
            0.90,
            "person_teacher",
            ["person_diana", "loc_school"],
            [],  # This clarifies - both parents were partially right
            None,
        ),
        # ═══════════════════════════════════════════════════════════════════
        # Conflict Cluster 4: ATTRIBUTION - Who picked up Diana?
        # ═══════════════════════════════════════════════════════════════════
        ConflictingFragment(
            "frag_attr_4a",
            "I picked up Diana from library at 5",
            "2024-02-14T17:05:00",
            "message",
            0.85,
            "person_alice",
            ["person_diana", "loc_library", "person_alice"],
            ["frag_attr_4b"],
            "attribution",
        ),
        ConflictingFragment(
            "frag_attr_4b",
            "Got Diana from library, she was reading Harry Potter",
            "2024-02-14T17:10:00",
            "message",
            0.85,
            "person_bob",
            ["person_diana", "loc_library", "person_bob"],
            ["frag_attr_4a"],
            "attribution",
        ),
        # Resolution fragment
        ConflictingFragment(
            "frag_attr_4c",
            "Both parents arrived at same time, took separate cars home",
            "2024-02-14T17:15:00",
            "sensory",
            0.60,
            "person_diana",
            ["person_alice", "person_bob", "loc_library"],
            [],
            None,
        ),
        # ═══════════════════════════════════════════════════════════════════
        # Conflict Cluster 5: MIXED - Pizza night confusion
        # ═══════════════════════════════════════════════════════════════════
        ConflictingFragment(
            "frag_mix_5a",
            "Pizza night was Thursday, got pepperoni",
            "2024-02-15T19:00:00",
            "sensory",
            0.70,
            "person_charlie",
            ["loc_restaurant"],
            ["frag_mix_5b", "frag_mix_5c"],
            "temporal",
        ),
        ConflictingFragment(
            "frag_mix_5b",
            "We had pizza on Friday after the game",
            "2024-02-16T20:00:00",
            "sensory",
            0.75,
            "person_diana",
            ["loc_restaurant"],
            ["frag_mix_5a", "frag_mix_5c"],
            "temporal",
        ),
        ConflictingFragment(
            "frag_mix_5c",
            "Credit card: Pizza Place $45.67, Friday 7:32 PM",
            "2024-02-16T19:32:00",
            "calendar",
            0.98,
            "obj_phone",
            ["loc_restaurant"],
            [],  # Corroborates 5b
            None,
        ),
        # ═══════════════════════════════════════════════════════════════════
        # Conflict Cluster 6: UNRESOLVABLE - True ambiguity
        # ═══════════════════════════════════════════════════════════════════
        ConflictingFragment(
            "frag_unres_6a",
            "Think we left the park around 4 PM",
            "2024-02-17T16:00:00",
            "inferred",
            0.50,
            "person_alice",
            ["loc_park", "time_4pm"],
            ["frag_unres_6b"],
            "temporal",
        ),
        ConflictingFragment(
            "frag_unres_6b",
            "Probably left closer to 5, sun was getting low",
            "2024-02-17T17:00:00",
            "inferred",
            0.50,
            "person_bob",
            ["loc_park", "time_5pm"],
            ["frag_unres_6a"],
            "temporal",
        ),
        # No corroborating evidence - must remain uncertain
    ]


def _create_conflict_clusters() -> List[ConflictCluster]:
    """Define conflict clusters for testing."""
    return [
        ConflictCluster(
            "cluster_temporal_arrival",
            ["frag_temp_1a", "frag_temp_1b", "frag_temp_1c"],
            "temporal",
            "corroboration",  # frag_temp_1d corroborates 1c
            "frag_temp_1c",
        ),
        ConflictCluster(
            "cluster_spatial_saturday",
            ["frag_spat_2a", "frag_spat_2b"],
            "spatial",
            "authority",  # Photo EXIF has higher authority
            "frag_spat_2b",
        ),
        ConflictCluster(
            "cluster_factual_meeting",
            ["frag_fact_3a", "frag_fact_3b"],
            "factual",
            "authority",  # Teacher is authoritative source
            None,  # Both partially correct
        ),
        ConflictCluster(
            "cluster_attribution_pickup",
            ["frag_attr_4a", "frag_attr_4b"],
            "attribution",
            "corroboration",  # Child's account resolves
            None,  # Both correct (both arrived)
        ),
        ConflictCluster(
            "cluster_pizza_night",
            ["frag_mix_5a", "frag_mix_5b"],
            "temporal",
            "authority",  # Credit card is definitive
            "frag_mix_5b",
        ),
        ConflictCluster(
            "cluster_unresolvable",
            ["frag_unres_6a", "frag_unres_6b"],
            "temporal",
            "none",  # Cannot be resolved
            None,
        ),
    ]


def _create_incomplete_episodes(conflict_clusters: List[ConflictCluster]) -> List[IncompleteEpisode]:
    """Create incomplete episodes from conflict clusters for SPC-UQ reconstruction.

    Each conflict cluster becomes an episode with ambiguous/conflicting attributes.
    High ambiguity scores reflect the conflicting nature of the sources.
    """
    from datetime import datetime
    base_time = int(datetime.now().timestamp() * 1000)
    day_ms = 24 * 60 * 60 * 1000

    episodes = []
    for i, cluster in enumerate(conflict_clusters):
        # Determine ambiguity based on conflict resolution possibility
        if cluster.resolution_hint == "none":
            ambiguity = 0.95  # Unresolvable conflicts have highest ambiguity
        elif cluster.resolution_hint == "corroboration":
            ambiguity = 0.75  # Need additional evidence
        else:  # authority, recency
            ambiguity = 0.65  # Can be resolved with proper weighting

        # Create episode with gaps based on conflict type
        episode = IncompleteEpisode(
            episode_id=f"episode_{cluster.id}",
            summary=f"Conflicting information about {cluster.conflict_type} details...",
            timestamp=base_time - (i + 1) * day_ms,
            # Conflict-type specific gaps
            location_name=None if cluster.conflict_type == "spatial" else "Unknown Location",
            participants=None if cluster.conflict_type == "attribution" else ["Unknown"],
            activity_type=None if cluster.conflict_type == "factual" else "conflicted_activity",
            ambiguity_score=ambiguity,
        )
        episodes.append(episode)

    return episodes


def _create_edges(entities: List[Entity]) -> List[Edge]:
    """Create semantic edges between entities."""
    return [
        # Family relationships
        Edge("person_alice", "person_charlie", "parent_of", 1.0),
        Edge("person_alice", "person_diana", "parent_of", 1.0),
        Edge("person_bob", "person_charlie", "parent_of", 1.0),
        Edge("person_bob", "person_diana", "parent_of", 1.0),
        Edge("person_charlie", "person_diana", "sibling_of", 1.0),
        # Location relationships
        Edge("person_alice", "loc_home", "lives_at", 0.95),
        Edge("person_bob", "loc_home", "lives_at", 0.95),
        Edge("person_charlie", "loc_school", "attends", 0.90),
        Edge("person_diana", "loc_school", "attends", 0.90),
        Edge("person_neighbor", "loc_home", "neighbor_of", 0.80),
        # Trust/reliability relationships
        Edge("person_teacher", "loc_school", "works_at", 0.95),
        Edge("person_alice", "obj_phone", "owns", 0.90),
    ]


def _generate_embeddings(
    entities: List[Entity], use_ultrabert: bool, rng: random.Random
) -> Dict[str, List[float]]:
    """Generate embeddings for all entities."""
    from ..r5_embeddings import get_embedding_service

    embedding_service = get_embedding_service(use_ultrabert)
    embeddings = {}

    for entity in entities:
        text = f"{entity.type}: {entity.name}"
        if entity.attributes:
            text += f" ({', '.join(f'{k}={v}' for k, v in entity.attributes.items())})"
        embeddings[entity.id] = embedding_service.embed_text(text)

    return embeddings


# ─────────────────────────────────────────────────────────────────────────────
# Fragment to episode ID mapping
# ─────────────────────────────────────────────────────────────────────────────

# Map fragments to their corresponding conflict cluster episodes
_FRAGMENT_EPISODE_MAP = {
    # Cluster 1: temporal_arrival
    "frag_temp_1a": "episode_cluster_temporal_arrival",
    "frag_temp_1b": "episode_cluster_temporal_arrival",
    "frag_temp_1c": "episode_cluster_temporal_arrival",
    "frag_temp_1d": "episode_cluster_temporal_arrival",
    # Cluster 2: spatial_saturday
    "frag_spat_2a": "episode_cluster_spatial_saturday",
    "frag_spat_2b": "episode_cluster_spatial_saturday",
    # Cluster 3: factual_meeting
    "frag_fact_3a": "episode_cluster_factual_meeting",
    "frag_fact_3b": "episode_cluster_factual_meeting",
    # Cluster 4: attribution_pickup
    "frag_attr_4a": "episode_cluster_attribution_pickup",
    "frag_attr_4b": "episode_cluster_attribution_pickup",
    "frag_attr_4c": "episode_cluster_attribution_pickup",
    # Cluster 5: pizza_night
    "frag_mix_5a": "episode_cluster_pizza_night",
    "frag_mix_5b": "episode_cluster_pizza_night",
    # Cluster 6: unresolvable
    "frag_unres_6a": "episode_cluster_unresolvable",
    "frag_unres_6b": "episode_cluster_unresolvable",
}


def _create_spc_fragments(fragments: List[ConflictingFragment]) -> List[Any]:
    """Create SPC-compatible fragment objects with source_episode_id.

    The SPC-UQ algorithm expects fragments with source_episode_id attribute
    to match fragments to their corresponding episodes for coherence calculation.
    """
    from dataclasses import dataclass, field
    from datetime import datetime

    @dataclass
    class SPCFragment:
        """Fragment compatible with SPC-UQ algorithm."""
        fragment_id: str
        source_episode_id: str
        source_event_id: str
        start_time_ms: int
        end_time_ms: int
        content: str
        attributes: tuple = ()
        entities_mentioned: List[str] = field(default_factory=list)
        conflicting_with: List[str] = field(default_factory=list)
        conflict_type: str = ""

    spc_fragments = []
    for f in fragments:
        # Get episode ID from mapping
        episode_id = _FRAGMENT_EPISODE_MAP.get(f.id, "unknown_episode")

        # Convert timestamp to ms
        try:
            dt = datetime.fromisoformat(f.timestamp)
            start_ms = int(dt.timestamp() * 1000)
        except (ValueError, AttributeError):
            start_ms = 0

        spc_frag = SPCFragment(
            fragment_id=f.id,
            source_episode_id=episode_id,
            source_event_id=f.source_id or f.id,
            start_time_ms=start_ms,
            end_time_ms=start_ms + 3600000,  # 1 hour duration default
            content=f.content,
            attributes=(
                ("provenance_type", f.provenance_type),
                ("confidence", f.confidence),
                ("conflict_type", f.conflict_type),
            ),
            entities_mentioned=f.entities_mentioned,
            conflicting_with=f.conflicts_with or [],
            conflict_type=f.conflict_type or "",
        )
        spc_fragments.append(spc_frag)

    return spc_fragments


# ─────────────────────────────────────────────────────────────────────────────
# Coverage thresholds for SPC-UQ conflict handling
# ─────────────────────────────────────────────────────────────────────────────

COVERAGE_THRESHOLDS = {
    # STRICT: Conflict pack MUST demonstrate conflict detection
    "min_reconstructions": 1,  # At least 1 reconstruction with conflicts
    "min_conflicts": 1,  # STRICT: Require at least 1 conflict detected
    "require_high_uncertainty_on_conflict": True,  # STRICT: High uncertainty on conflict
    "provenance_types_min": 1,  # At least 1 provenance type (less strict here)
    "confidence_variance_min": 0.0,  # Allow any variance
}


# ─────────────────────────────────────────────────────────────────────────────
# Main builder
# ─────────────────────────────────────────────────────────────────────────────


def build_world(seed: int = 42, use_ultrabert: bool = False):
    """Build conflicting fragment world.

    This world tests SPC-UQ's ability to:
    1. Detect conflicting fragments from different sources
    2. Classify conflict types (temporal, spatial, factual, attribution)
    3. Apply resolution strategies (recency, authority, corroboration)
    4. Maintain high uncertainty for unresolvable conflicts
    5. Boost confidence when corroborating evidence exists
    """
    from ..r5_data_factory import World

    rng = random.Random(seed)

    entities = _create_entities()
    fragments = _create_conflicting_fragments()
    conflict_clusters = _create_conflict_clusters()
    incomplete_episodes = _create_incomplete_episodes(conflict_clusters)
    edges = _create_edges(entities)
    schemas = _load_schemas()
    embeddings = _generate_embeddings(entities, use_ultrabert, rng)

    # Create context for conflict resolution
    context = {
        "current_date": "2024-02-18",
        "day_of_week": "Sunday",
        "family_members": ["person_alice", "person_bob", "person_charlie", "person_diana"],
        "source_reliability": {
            "person_alice": 0.85,
            "person_bob": 0.85,
            "person_charlie": 0.70,
            "person_diana": 0.65,
            "person_neighbor": 0.60,
            "person_teacher": 0.95,
            "obj_phone": 0.98,  # Digital sources are highly reliable
        },
        "conflict_clusters": [
            {
                "id": c.id,
                "fragments": c.fragment_ids,
                "type": c.conflict_type,
                "resolution_hint": c.resolution_hint,
                "ground_truth": c.ground_truth_fragment,
            }
            for c in conflict_clusters
        ],
        # Required for SPC-UQ context-based reconstruction
        "nearby_locations": ["loc_home", "loc_park", "loc_mall", "loc_school", "loc_library", "loc_restaurant"],
        "known_locations": ["loc_home", "loc_park", "loc_mall", "loc_school", "loc_library", "loc_restaurant"],
        "frequent_contacts": ["Alice", "Bob", "Charlie", "Diana", "Mr. Wilson", "Ms. Garcia"],
    }

    # Create episodes from conflict clusters (for CPN compatibility)
    episodes = [
        {
            "id": f"episode_{cluster.id}",
            "fragments": cluster.fragment_ids,
            "conflict_type": cluster.conflict_type,
            "resolvable": cluster.resolution_hint != "none",
        }
        for cluster in conflict_clusters
    ]

    return World(
        pack_name="spc_conflict",
        seed=seed,
        # CPN inputs (minimal)
        episodes=episodes,
        kg_edges=[],
        # BGT-SM inputs (minimal)
        entities=[{"id": e.id, "type": e.type, "name": e.name} for e in entities],
        semantic_edges=[
            {"source": e.source, "target": e.target, "relation": e.relation}
            for e in edges
        ],
        embeddings=embeddings,
        # MCTS inputs (minimal)
        initial_state={"conflict_clusters": [c.id for c in conflict_clusters]},
        actions=[],
        goals=[],
        # SPC-UQ inputs (primary focus) - pass dataclass instances directly
        incomplete_episodes=incomplete_episodes,
        # Create proper fragment objects with source_episode_id for SPC-UQ
        fragments=_create_spc_fragments(fragments),
        schemas=schemas,
        context=context,
        expected_properties=COVERAGE_THRESHOLDS,
        difficulty="hard",
    )
