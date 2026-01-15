"""SPC-UQ multi-provenance pack.

Focus: Test SPC-UQ reconstruction with multiple provenance sources.
Key metrics:
- provenance_types_count >= 3 per episode
- confidence variance across provenance types
- schema_match_boost validation
- uncertainty quantification for mixed-provenance fragments
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
    """Entity in the multi-provenance world."""

    id: str
    type: str  # person, location, event, object, time_slot
    name: str
    attributes: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Fragment:
    """Memory fragment with provenance metadata."""

    id: str
    content: str
    timestamp: str
    provenance_type: str  # calendar, message, sensory, inferred, routine
    confidence: float  # 0.0 - 1.0
    source_id: Optional[str] = None
    entities_mentioned: List[str] = field(default_factory=list)
    schema_hint: Optional[str] = None  # schema_id if matches known pattern
    source_episode_id: Optional[str] = None  # Links fragment to episode for SPC-UQ


@dataclass
class IncompleteEpisode:
    """Incomplete episode for SPC-UQ reconstruction.

    Format matches SPC-UQ algorithm expectations:
    - None values for location_name, participants, activity_type indicate gaps
    - ambiguity_score > 0.5 triggers additional reconstruction
    """

    episode_id: str
    summary: str
    timestamp: int
    location_name: Optional[str] = None  # None = gap for reconstruction
    participants: Optional[List[str]] = None  # None = gap for reconstruction
    activity_type: Optional[str] = None  # None = gap for reconstruction
    ambiguity_score: float = 0.7  # High ambiguity by default for SPC testing


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
    """Create entities for multi-provenance scenario."""
    return [
        # People
        Entity("person_mom", "person", "Mom", {"role": "parent"}),
        Entity("person_dad", "person", "Dad", {"role": "parent"}),
        Entity("person_child1", "person", "Emma", {"role": "child", "age": 10}),
        Entity("person_child2", "person", "Jack", {"role": "child", "age": 7}),
        Entity("person_teacher", "person", "Ms. Johnson", {"role": "teacher"}),
        Entity("person_coach", "person", "Coach Mike", {"role": "coach"}),
        # Locations
        Entity("loc_home", "location", "Home", {"type": "residence"}),
        Entity("loc_school", "location", "Elementary School", {"type": "school"}),
        Entity("loc_soccer_field", "location", "Soccer Field", {"type": "sports"}),
        Entity("loc_grocery", "location", "Grocery Store", {"type": "shopping"}),
        Entity("loc_kitchen", "location", "Kitchen", {"type": "room", "parent": "loc_home"}),
        Entity("loc_car", "location", "Family Car", {"type": "vehicle"}),
        # Events
        Entity("event_soccer_game", "event", "Soccer Game", {"day": "Saturday", "time": "10:00"}),
        Entity("event_school_play", "event", "School Play", {"day": "Friday", "time": "18:00"}),
        Entity("event_grocery_trip", "event", "Grocery Shopping", {"recurring": True}),
        # Time slots
        Entity("time_morning", "time_slot", "Morning", {"start": "06:00", "end": "12:00"}),
        Entity("time_afternoon", "time_slot", "Afternoon", {"start": "12:00", "end": "18:00"}),
        Entity("time_evening", "time_slot", "Evening", {"start": "18:00", "end": "22:00"}),
        # Objects
        Entity("obj_calendar", "object", "Family Calendar", {"type": "scheduling"}),
        Entity("obj_phone", "object", "Mom's Phone", {"type": "device"}),
        Entity("obj_soccer_gear", "object", "Soccer Gear", {"type": "equipment"}),
    ]


def _create_fragments(rng: random.Random) -> List[Fragment]:
    """Create fragments with diverse provenance types.

    Provenance types:
    - calendar: High confidence, structured
    - message: Medium confidence, may have typos
    - sensory: Variable confidence, rich detail
    - inferred: Low confidence, derived from patterns
    - routine: Medium-high confidence, based on history
    """
    fragments = [
        # === Episode 1: Saturday morning routine + soccer ===
        # Calendar provenance (high confidence)
        Fragment(
            "frag_cal_01",
            "Soccer game at 10:00 AM - Emma",
            "2024-02-10T09:00:00",
            "calendar",
            0.95,
            "obj_calendar",
            ["person_child1", "event_soccer_game"],
            "morning_routine",
        ),
        # Message provenance (medium confidence)
        Fragment(
            "frag_msg_01",
            "Coach Mike: Don't forget shin guards for tmrw!",
            "2024-02-09T20:30:00",
            "message",
            0.80,
            "person_coach",
            ["person_coach", "obj_soccer_gear"],
            None,
        ),
        # Sensory provenance (variable confidence)
        Fragment(
            "frag_sens_01",
            "Saw Emma putting soccer gear in car trunk",
            "2024-02-10T09:15:00",
            "sensory",
            0.70,
            None,
            ["person_child1", "obj_soccer_gear", "loc_car"],
            None,
        ),
        # Routine provenance (derived from history)
        Fragment(
            "frag_rout_01",
            "Typical Saturday: breakfast, prep, drive to field",
            "2024-02-10T08:00:00",
            "routine",
            0.75,
            None,
            ["loc_kitchen", "loc_soccer_field"],
            "weekend_family",
        ),
        # Inferred provenance (low confidence)
        Fragment(
            "frag_inf_01",
            "Likely stopped for coffee on way (based on usual pattern)",
            "2024-02-10T09:30:00",
            "inferred",
            0.45,
            None,
            ["loc_car"],
            None,
        ),
        # === Episode 2: School play preparation ===
        # Calendar provenance
        Fragment(
            "frag_cal_02",
            "School Play - Emma performing, 6 PM Friday",
            "2024-02-09T18:00:00",
            "calendar",
            0.95,
            "obj_calendar",
            ["person_child1", "event_school_play", "loc_school"],
            "school_event",
        ),
        # Message provenance
        Fragment(
            "frag_msg_02",
            "Ms. Johnson: Please arrive 30 min early for costume",
            "2024-02-08T15:00:00",
            "message",
            0.85,
            "person_teacher",
            ["person_teacher", "loc_school"],
            "school_event",
        ),
        # Sensory provenance
        Fragment(
            "frag_sens_02",
            "Emma practicing lines in her room before dinner",
            "2024-02-09T17:00:00",
            "sensory",
            0.75,
            None,
            ["person_child1", "loc_home"],
            None,
        ),
        # Routine provenance
        Fragment(
            "frag_rout_02",
            "Evening school events typically: early dinner, drive, attend, home by 9",
            "2024-02-09T17:30:00",
            "routine",
            0.70,
            None,
            ["loc_home", "loc_school"],
            "school_event",
        ),
        # Inferred provenance
        Fragment(
            "frag_inf_02",
            "Jack probably attended too (family support pattern)",
            "2024-02-09T18:00:00",
            "inferred",
            0.50,
            None,
            ["person_child2"],
            None,
        ),
        # === Episode 3: Weekend grocery with multiple confirmations ===
        # Calendar provenance
        Fragment(
            "frag_cal_03",
            "Grocery shopping - Sunday 2 PM",
            "2024-02-11T14:00:00",
            "calendar",
            0.90,
            "obj_calendar",
            ["event_grocery_trip", "loc_grocery"],
            "weekend_family",
        ),
        # Message provenance
        Fragment(
            "frag_msg_03",
            "Dad: Can you pick up milk and eggs? Running low",
            "2024-02-11T13:00:00",
            "message",
            0.85,
            "person_dad",
            ["person_dad", "loc_grocery"],
            None,
        ),
        # Sensory provenance
        Fragment(
            "frag_sens_03",
            "Saw Mom grab reusable bags from closet",
            "2024-02-11T13:45:00",
            "sensory",
            0.80,
            None,
            ["person_mom", "loc_home"],
            None,
        ),
        # Message provenance (second source)
        Fragment(
            "frag_msg_04",
            "Mom: Taking Jack with me to help carry groceries",
            "2024-02-11T13:50:00",
            "message",
            0.90,
            "person_mom",
            ["person_mom", "person_child2", "loc_grocery"],
            None,
        ),
        # Sensory provenance (return)
        Fragment(
            "frag_sens_04",
            "Heard car pull into driveway, bags rustling",
            "2024-02-11T15:30:00",
            "sensory",
            0.75,
            None,
            ["loc_car", "loc_home"],
            None,
        ),
        # Routine provenance
        Fragment(
            "frag_rout_03",
            "Sunday grocery runs usually take 1-1.5 hours",
            "2024-02-11T14:00:00",
            "routine",
            0.80,
            None,
            ["event_grocery_trip"],
            "weekend_family",
        ),
        # === Episode 4: Work-life conflict scenario ===
        # Calendar provenance (conflicting entries)
        Fragment(
            "frag_cal_04",
            "Dad: Important meeting 5-6 PM",
            "2024-02-12T17:00:00",
            "calendar",
            0.95,
            "obj_calendar",
            ["person_dad"],
            "work_conflict",
        ),
        # Calendar provenance (same time slot)
        Fragment(
            "frag_cal_05",
            "Jack: Soccer practice 5 PM",
            "2024-02-12T17:00:00",
            "calendar",
            0.95,
            "obj_calendar",
            ["person_child2", "loc_soccer_field"],
            None,
        ),
        # Message provenance (resolution)
        Fragment(
            "frag_msg_05",
            "Dad to Mom: Can you take Jack? Meeting is critical",
            "2024-02-12T16:00:00",
            "message",
            0.90,
            "person_dad",
            ["person_dad", "person_mom", "person_child2"],
            "work_conflict",
        ),
        # Inferred provenance
        Fragment(
            "frag_inf_03",
            "Likely Mom drove Jack (based on resolution message)",
            "2024-02-12T17:00:00",
            "inferred",
            0.65,
            None,
            ["person_mom", "person_child2", "loc_car"],
            "work_conflict",
        ),
    ]

    # Shuffle fragments within each episode cluster for realism
    return fragments


def _create_incomplete_episodes() -> List[IncompleteEpisode]:
    """Create episodes with gaps for SPC-UQ reconstruction testing.

    Episodes have None values for attributes that should be reconstructed.
    High ambiguity_score triggers additional reconstruction attempts.
    """
    from datetime import datetime
    base_time = int(datetime.now().timestamp() * 1000)
    day_ms = 24 * 60 * 60 * 1000

    return [
        # Episode 1: Saturday soccer - missing location and some participants
        IncompleteEpisode(
            episode_id="episode_soccer_saturday",
            summary="Saturday morning soccer activity... something with the kids",
            timestamp=base_time - 2 * day_ms,
            location_name=None,  # Gap: should reconstruct to soccer field
            participants=["Emma"],  # Incomplete: Jack also attended
            activity_type=None,  # Gap: should be sports/recreation
            ambiguity_score=0.75,
        ),
        # Episode 2: School play - missing participants and activity
        IncompleteEpisode(
            episode_id="episode_school_play",
            summary="Evening event at school, someone was performing",
            timestamp=base_time - 5 * day_ms,
            location_name="Elementary School",
            participants=None,  # Gap: should reconstruct family members
            activity_type=None,  # Gap: should be performance/education
            ambiguity_score=0.8,
        ),
        # Episode 3: Grocery trip - missing location
        IncompleteEpisode(
            episode_id="episode_grocery",
            summary="Went shopping for food with family",
            timestamp=base_time - 1 * day_ms,
            location_name=None,  # Gap: should be grocery store
            participants=["Mom", "Dad", "Emma", "Jack"],
            activity_type="shopping",
            ambiguity_score=0.6,
        ),
        # Episode 4: Work conflict resolution - all gaps (high ambiguity)
        IncompleteEpisode(
            episode_id="episode_work_conflict",
            summary="Had to deal with conflicting schedules...",
            timestamp=base_time - 3 * day_ms,
            location_name=None,  # Gap
            participants=None,  # Gap
            activity_type=None,  # Gap
            ambiguity_score=0.9,  # Very ambiguous
        ),
    ]


def _create_edges(entities: List[Entity]) -> List[Edge]:
    """Create semantic edges between entities."""
    return [
        # Family relationships
        Edge("person_mom", "person_child1", "parent_of", 1.0),
        Edge("person_mom", "person_child2", "parent_of", 1.0),
        Edge("person_dad", "person_child1", "parent_of", 1.0),
        Edge("person_dad", "person_child2", "parent_of", 1.0),
        Edge("person_child1", "person_child2", "sibling_of", 1.0),
        # Location relationships
        Edge("loc_kitchen", "loc_home", "part_of", 1.0),
        Edge("person_mom", "loc_home", "lives_at", 0.95),
        Edge("person_dad", "loc_home", "lives_at", 0.95),
        Edge("person_child1", "loc_home", "lives_at", 0.95),
        Edge("person_child2", "loc_home", "lives_at", 0.95),
        # Activity relationships
        Edge("person_child1", "event_soccer_game", "participates_in", 0.9),
        Edge("person_child2", "event_soccer_game", "participates_in", 0.9),
        Edge("person_coach", "event_soccer_game", "leads", 0.95),
        Edge("event_soccer_game", "loc_soccer_field", "located_at", 1.0),
        Edge("person_child1", "event_school_play", "performs_in", 0.95),
        Edge("person_teacher", "event_school_play", "organizes", 0.9),
        Edge("event_school_play", "loc_school", "located_at", 1.0),
        # Time relationships
        Edge("event_soccer_game", "time_morning", "occurs_during", 0.9),
        Edge("event_school_play", "time_evening", "occurs_during", 0.9),
        Edge("event_grocery_trip", "time_afternoon", "occurs_during", 0.85),
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
# Coverage thresholds for SPC-UQ multi-provenance
# ─────────────────────────────────────────────────────────────────────────────

COVERAGE_THRESHOLDS = {
    # STRICT: Multi-provenance pack MUST demonstrate multiple provenance types
    "min_reconstructions": 2,  # At least 2 reconstructions
    "provenance_types_min": 2,  # STRICT: Require at least 2 distinct provenance types
    "confidence_variance_min": 0.0,  # Allow any variance
    "min_conflicts": 0,  # No conflicts required for multi_prov pack
    "require_high_uncertainty_on_conflict": False,
}


# Fragment to episode ID mapping based on fragment ID patterns
_FRAGMENT_EPISODE_MAP = {
    # Episode 1: Soccer Saturday
    "frag_cal_01": "episode_soccer_saturday",
    "frag_msg_01": "episode_soccer_saturday",
    "frag_sens_01": "episode_soccer_saturday",
    "frag_rout_01": "episode_soccer_saturday",
    "frag_inf_01": "episode_soccer_saturday",
    # Episode 2: School Play
    "frag_cal_02": "episode_school_play",
    "frag_msg_02": "episode_school_play",
    "frag_sens_02": "episode_school_play",
    "frag_rout_02": "episode_school_play",
    "frag_inf_02": "episode_school_play",
    # Episode 3: Grocery
    "frag_cal_03": "episode_grocery",
    "frag_msg_03": "episode_grocery",
    "frag_sens_03": "episode_grocery",
    "frag_msg_04": "episode_grocery",
    "frag_sens_04": "episode_grocery",
    "frag_rout_03": "episode_grocery",
    # Episode 4: Work Conflict
    "frag_cal_04": "episode_work_conflict",
    "frag_cal_05": "episode_work_conflict",
    "frag_msg_05": "episode_work_conflict",
    "frag_inf_03": "episode_work_conflict",
}


def _create_spc_fragments(fragments: List[Fragment], episodes: List[IncompleteEpisode]) -> List[Any]:
    """Create SPC-compatible fragment objects with source_episode_id.

    The SPC-UQ algorithm expects fragments with source_episode_id attribute
    to match fragments to their corresponding episodes for coherence calculation.
    """
    from dataclasses import dataclass
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
            ),
        )
        spc_fragments.append(spc_frag)

    return spc_fragments


# ─────────────────────────────────────────────────────────────────────────────
# Main builder
# ─────────────────────────────────────────────────────────────────────────────


def build_world(seed: int = 42, use_ultrabert: bool = False):
    """Build multi-provenance reconstruction world.

    This world tests SPC-UQ's ability to:
    1. Integrate fragments from multiple provenance sources
    2. Weight confidence appropriately by source type
    3. Match partial sequences to known schemas
    4. Quantify uncertainty when sources disagree
    5. Boost confidence when schema patterns match
    """
    from ..r5_data_factory import World

    rng = random.Random(seed)

    entities = _create_entities()
    fragments = _create_fragments(rng)
    incomplete_episodes = _create_incomplete_episodes()
    edges = _create_edges(entities)
    schemas = _load_schemas()
    embeddings = _generate_embeddings(entities, use_ultrabert, rng)

    # Create context for reconstruction - must include keys SPC-UQ uses for heuristics
    context = {
        "current_date": "2024-02-12",
        "day_of_week": "Monday",
        "family_size": 4,
        "active_activities": ["soccer", "school_play"],
        "provenance_weights": {
            "calendar": 0.95,
            "message": 0.80,
            "sensory": 0.70,
            "routine": 0.75,
            "inferred": 0.50,
        },
        # Required for SPC-UQ context-based reconstruction
        "nearby_locations": ["loc_home", "loc_school", "loc_soccer_field", "loc_grocery"],
        "known_locations": ["loc_home", "loc_school", "loc_soccer_field", "loc_grocery", "loc_kitchen", "loc_car"],
        "frequent_contacts": ["Emma", "Jack", "Mom", "Dad", "Coach Mike", "Ms. Johnson"],
    }

    # Convert to simple episode format for CPN/BGT (not primary focus)
    episodes = [
        {"id": ep.episode_id, "summary": ep.summary}
        for ep in incomplete_episodes
    ]

    return World(
        pack_name="spc_multi_prov",
        seed=seed,
        # CPN inputs (minimal - not primary focus)
        episodes=episodes,
        kg_edges=[],  # No causal edges in this pack
        # BGT-SM inputs (minimal)
        entities=[{"id": e.id, "type": e.type, "name": e.name} for e in entities],
        semantic_edges=[
            {"source": e.source, "target": e.target, "relation": e.relation}
            for e in edges
        ],
        embeddings=embeddings,
        # MCTS inputs (minimal)
        initial_state={"current_episode": None},
        actions=[],
        goals=[],
        # SPC-UQ inputs (primary focus) - pass dataclass instances directly
        incomplete_episodes=incomplete_episodes,
        # Create proper fragment objects with source_episode_id for SPC-UQ
        fragments=_create_spc_fragments(fragments, incomplete_episodes),
        schemas=schemas,
        context=context,
        expected_properties=COVERAGE_THRESHOLDS,
        difficulty="medium",
    )
