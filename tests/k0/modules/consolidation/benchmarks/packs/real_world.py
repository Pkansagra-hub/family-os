"""Real-world inspired pack with realistic family scenarios.

This pack models authentic family life situations:
- Morning routines with school preparation
- Work-life balance conflicts
- Weekend family activities
- School events and homework
- Health and wellness moments
- Financial decisions
- Relationship dynamics

Designed to test algorithms on realistic, domain-relevant scenarios.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

# ─────────────────────────────────────────────────────────────────────────────
# Data Classes
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class RealWorldEpisode:
    """Realistic family episode."""

    episode_id: str
    summary: str
    timestamp: int
    emotional_valence: float
    participants: List[str]
    location: str
    activity_type: str
    entity_ids: List[str] = field(default_factory=list)

    @property
    def sentiment_score(self) -> float:
        return self.emotional_valence

    @property
    def salience(self) -> float:
        return abs(self.emotional_valence) + 0.3

    @property
    def start_time_ms(self) -> int:
        return self.timestamp


@dataclass
class RealWorldEntity:
    """Entity representing real family life concepts."""

    entity_id: str
    name: str
    entity_type: str
    category: str
    _observation_count: int = 1

    @property
    def observation_count(self) -> int:
        return self._observation_count


@dataclass
class RealWorldEdge:
    """Edge for realistic scenarios."""

    source_id: str
    target_id: str
    relation: str
    weight: float
    edge_type: str = "SEMANTIC"
    _observation_count: int = 1

    @property
    def source_entity_id(self) -> str:
        return self.source_id

    @property
    def target_entity_id(self) -> str:
        return self.target_id

    @property
    def observation_count(self) -> int:
        return self._observation_count

    @property
    def relation_type(self) -> str:
        return self.relation


@dataclass
class RealWorldGoal:
    """Realistic family goals."""

    goal_id: str
    description: str
    priority: float
    target_value: float = 1.0


@dataclass
class RealWorldAction:
    """Realistic family actions."""

    action_id: str
    name: str
    duration_hours: float
    goal_alignment: float
    expected_reward: float
    preconditions: List[str] = field(default_factory=list)
    effects: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RealWorldFragment:
    """Memory fragment from real situations."""

    fragment_id: str
    source_episode_id: str
    source_event_id: str
    start_time_ms: int
    end_time_ms: int
    content: str
    attributes: tuple


@dataclass
class RealWorldIncompleteEpisode:
    """Incomplete memory of real events."""

    episode_id: str
    summary: str
    timestamp: int
    location_name: Optional[str] = None
    participants: Optional[List[str]] = None
    activity_type: Optional[str] = None
    ambiguity_score: float = 0.5


# ─────────────────────────────────────────────────────────────────────────────
# Family Member Definitions
# ─────────────────────────────────────────────────────────────────────────────

FAMILY_MEMBERS = {
    "self": {"name": "Parent", "entity_type": "person", "category": "family"},
    "spouse": {"name": "Spouse", "entity_type": "person", "category": "family"},
    "sarah": {"name": "Sarah (12yo)", "entity_type": "person", "category": "family"},
    "tommy": {"name": "Tommy (8yo)", "entity_type": "person", "category": "family"},
    "grandma": {"name": "Grandma", "entity_type": "person", "category": "family"},
    "uncle_bob": {"name": "Uncle Bob", "entity_type": "person", "category": "family"},
}

# ─────────────────────────────────────────────────────────────────────────────
# Realistic Scenario Templates
# ─────────────────────────────────────────────────────────────────────────────

MORNING_SCENARIOS = [
    {
        "summary": "Rushed breakfast before school. Sarah couldn't find her homework and everyone was stressed.",
        "valence": -0.4,
        "participants": ["self", "sarah", "tommy"],
        "location": "home_kitchen",
        "activity": "morning_routine",
        "entities": ["breakfast", "homework", "school_bus", "stress"],
    },
    {
        "summary": "Peaceful morning routine. Everyone got ready on time and had a nice family breakfast.",
        "valence": 0.7,
        "participants": ["self", "spouse", "sarah", "tommy"],
        "location": "home_kitchen",
        "activity": "family_meal",
        "entities": ["breakfast", "family_time", "morning_routine"],
    },
    {
        "summary": "Tommy had a stomach ache and didn't want to go to school. Had to stay home with him.",
        "valence": -0.3,
        "participants": ["self", "tommy"],
        "location": "home_bedroom",
        "activity": "caregiving",
        "entities": ["illness", "school_absence", "caring"],
    },
]

WORK_SCENARIOS = [
    {
        "summary": "Important work deadline conflicted with Sarah's school play. Felt guilty missing it.",
        "valence": -0.7,
        "participants": ["self"],
        "location": "office",
        "activity": "work_conflict",
        "entities": ["deadline", "school_play", "guilt", "work_life_balance"],
    },
    {
        "summary": "Got a promotion at work. Family celebration dinner to share the good news.",
        "valence": 0.9,
        "participants": ["self", "spouse", "sarah", "tommy"],
        "location": "restaurant",
        "activity": "celebration",
        "entities": ["promotion", "career", "celebration", "family_dinner"],
    },
    {
        "summary": "Worked from home to help Tommy with his science fair project. Great bonding time.",
        "valence": 0.8,
        "participants": ["self", "tommy"],
        "location": "home_office",
        "activity": "parenting",
        "entities": ["work_from_home", "science_fair", "bonding", "education"],
    },
]

EDUCATION_SCENARIOS = [
    {
        "summary": "Sarah struggled with algebra homework. Spent two hours helping her understand fractions.",
        "valence": 0.4,
        "participants": ["self", "sarah"],
        "location": "home_study",
        "activity": "homework_help",
        "entities": ["homework", "math", "fractions", "learning"],
    },
    {
        "summary": "Parent-teacher conference revealed Tommy is falling behind in reading. Need intervention plan.",
        "valence": -0.5,
        "participants": ["self", "spouse"],
        "location": "school",
        "activity": "school_meeting",
        "entities": ["reading_skills", "academic_concern", "intervention"],
    },
    {
        "summary": "Sarah won the spelling bee! So proud of her dedication to studying.",
        "valence": 0.95,
        "participants": ["self", "spouse", "sarah"],
        "location": "school",
        "activity": "school_event",
        "entities": ["spelling_bee", "achievement", "pride", "education"],
    },
]

WEEKEND_SCENARIOS = [
    {
        "summary": "Family bike ride in the park. Everyone laughed when Tommy fell in a puddle.",
        "valence": 0.85,
        "participants": ["self", "spouse", "sarah", "tommy"],
        "location": "park",
        "activity": "outdoor_recreation",
        "entities": ["biking", "outdoor_activity", "family_fun", "laughter"],
    },
    {
        "summary": "Rainy Saturday. Movie marathon with popcorn and blankets. Perfect cozy day.",
        "valence": 0.75,
        "participants": ["self", "spouse", "sarah", "tommy"],
        "location": "home_living_room",
        "activity": "movie_night",
        "entities": ["movies", "relaxation", "quality_time", "comfort"],
    },
    {
        "summary": "Visited grandma for Sunday lunch. She taught Sarah her secret recipe.",
        "valence": 0.8,
        "participants": ["self", "sarah", "grandma"],
        "location": "grandma_house",
        "activity": "family_visit",
        "entities": ["grandma", "tradition", "cooking", "family_bond"],
    },
]

CONFLICT_SCENARIOS = [
    {
        "summary": "Argument with spouse about household budget. Credit card bill was higher than expected.",
        "valence": -0.65,
        "participants": ["self", "spouse"],
        "location": "home_bedroom",
        "activity": "relationship_conflict",
        "entities": ["budget", "finances", "argument", "stress"],
    },
    {
        "summary": "Sarah and Tommy had a big fight over the video game. Had to confiscate the controller.",
        "valence": -0.4,
        "participants": ["self", "sarah", "tommy"],
        "location": "home_living_room",
        "activity": "sibling_conflict",
        "entities": ["sibling_rivalry", "video_games", "discipline"],
    },
    {
        "summary": "Made up with spouse after budget argument. Agreed on a savings plan together.",
        "valence": 0.6,
        "participants": ["self", "spouse"],
        "location": "home_kitchen",
        "activity": "reconciliation",
        "entities": ["apology", "compromise", "financial_planning", "relationship"],
    },
]

HEALTH_SCENARIOS = [
    {
        "summary": "Family went for annual checkups. Doctor praised the kids' healthy development.",
        "valence": 0.6,
        "participants": ["self", "sarah", "tommy"],
        "location": "hospital",
        "activity": "healthcare",
        "entities": ["checkup", "health", "development", "pediatrician"],
    },
    {
        "summary": "Started morning yoga routine with the family. Kids giggled through the poses.",
        "valence": 0.7,
        "participants": ["self", "spouse", "sarah", "tommy"],
        "location": "home_living_room",
        "activity": "exercise",
        "entities": ["yoga", "wellness", "family_activity", "morning_routine"],
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# Generators
# ─────────────────────────────────────────────────────────────────────────────


def _create_entities(seed: int) -> List[RealWorldEntity]:
    """Create entities for realistic family scenarios."""
    entities = []

    # Family members
    for member_id, info in FAMILY_MEMBERS.items():
        entities.append(
            RealWorldEntity(
                entity_id=f"ENT_{member_id.upper()}",
                name=info["name"],
                entity_type=info["entity_type"],
                category=info["category"],
                _observation_count=50 if member_id in ["self", "spouse"] else 30,
            )
        )

    # Common family life entities
    family_entities = [
        ("breakfast", "activity", "family", 40),
        ("homework", "activity", "education", 35),
        ("school_bus", "object", "education", 20),
        ("school", "location", "education", 45),
        ("dinner", "activity", "family", 45),
        ("bedtime_routine", "activity", "family", 40),
        ("video_games", "activity", "entertainment", 25),
        ("tv_time", "activity", "entertainment", 30),
        ("playground", "location", "recreation", 15),
        ("grocery_store", "location", "errands", 20),
        ("doctor", "person", "health", 8),
        ("soccer_practice", "activity", "sports", 12),
        ("piano_lessons", "activity", "education", 10),
        ("birthday_party", "event", "social", 6),
        ("vacation", "event", "travel", 4),
    ]

    for name, etype, category, obs in family_entities:
        entities.append(
            RealWorldEntity(
                entity_id=f"ENT_{name.upper()}",
                name=name.replace("_", " ").title(),
                entity_type=etype,
                category=category,
                _observation_count=obs,
            )
        )

    # Emotional/state entities
    emotional_entities = [
        ("stress", "state", "emotional", 25),
        ("happiness", "state", "emotional", 30),
        ("guilt", "state", "emotional", 15),
        ("pride", "state", "emotional", 20),
        ("frustration", "state", "emotional", 18),
        ("love", "state", "emotional", 35),
        ("worry", "state", "emotional", 20),
        ("relief", "state", "emotional", 12),
    ]

    for name, etype, category, obs in emotional_entities:
        entities.append(
            RealWorldEntity(
                entity_id=f"ENT_{name.upper()}",
                name=name.title(),
                entity_type=etype,
                category=category,
                _observation_count=obs,
            )
        )

    return entities


def _create_episodes(rng: random.Random, entities: List[RealWorldEntity]) -> List[RealWorldEpisode]:
    """Create realistic family episodes."""
    episodes = []
    all_scenarios = (
        MORNING_SCENARIOS
        + WORK_SCENARIOS
        + EDUCATION_SCENARIOS
        + WEEKEND_SCENARIOS
        + CONFLICT_SCENARIOS
        + HEALTH_SCENARIOS
    )

    base_time = int(datetime.now().timestamp() * 1000)
    day_ms = 24 * 60 * 60 * 1000

    # Build entity lookup
    entity_lookup = {e.name.lower().replace(" ", "_"): e.entity_id for e in entities}

    for i, scenario in enumerate(all_scenarios):
        # Map entity names to IDs
        entity_ids = []
        for ent_name in scenario["entities"]:
            ent_key = ent_name.lower().replace(" ", "_")
            if ent_key in entity_lookup:
                entity_ids.append(entity_lookup[ent_key])
            else:
                entity_ids.append(f"ENT_{ent_name.upper()}")

        episode = RealWorldEpisode(
            episode_id=f"EP_REAL_{i:03d}",
            summary=scenario["summary"],
            timestamp=base_time - (i + 1) * day_ms + rng.randint(-43200000, 43200000),
            emotional_valence=scenario["valence"],
            participants=scenario["participants"],
            location=scenario["location"],
            activity_type=scenario["activity"],
            entity_ids=entity_ids,
        )
        episodes.append(episode)

    return episodes


def _create_semantic_edges(
    rng: random.Random, entities: List[RealWorldEntity]
) -> List[RealWorldEdge]:
    """Create semantic edges based on realistic relationships."""
    edges = []

    # Define realistic relationship patterns
    relationships = [
        # Family relationships
        ("ENT_SELF", "ENT_SPOUSE", "married_to", 1.0),
        ("ENT_SELF", "ENT_SARAH", "parent_of", 0.95),
        ("ENT_SELF", "ENT_TOMMY", "parent_of", 0.95),
        ("ENT_SPOUSE", "ENT_SARAH", "parent_of", 0.95),
        ("ENT_SPOUSE", "ENT_TOMMY", "parent_of", 0.95),
        ("ENT_SARAH", "ENT_TOMMY", "sibling_of", 0.9),
        ("ENT_GRANDMA", "ENT_SARAH", "grandparent_of", 0.85),
        ("ENT_GRANDMA", "ENT_TOMMY", "grandparent_of", 0.85),
        # Activity relationships
        ("ENT_SARAH", "ENT_HOMEWORK", "does", 0.8),
        ("ENT_TOMMY", "ENT_VIDEO_GAMES", "plays", 0.75),
        ("ENT_SARAH", "ENT_PIANO_LESSONS", "takes", 0.7),
        ("ENT_TOMMY", "ENT_SOCCER_PRACTICE", "attends", 0.8),
        # Location relationships
        ("ENT_SARAH", "ENT_SCHOOL", "attends", 0.9),
        ("ENT_TOMMY", "ENT_SCHOOL", "attends", 0.9),
        # Causal patterns
        ("ENT_STRESS", "ENT_FRUSTRATION", "leads_to", 0.7),
        ("ENT_HOMEWORK", "ENT_STRESS", "can_cause", 0.5),
        ("ENT_VIDEO_GAMES", "ENT_HAPPINESS", "provides", 0.6),
        ("ENT_DINNER", "ENT_HAPPINESS", "facilitates", 0.7),
    ]

    for src, tgt, rel, weight in relationships:
        edges.append(
            RealWorldEdge(
                source_id=src,
                target_id=tgt,
                relation=rel,
                weight=weight,
                edge_type="SEMANTIC",
                _observation_count=int(weight * 20),
            )
        )

    return edges


def _create_kg_edges(rng: random.Random) -> List[RealWorldEdge]:
    """Create causal edges for realistic scenarios."""
    causal_chains = [
        # Work-life balance chain
        [
            ("ENT_WORK_MEETING", "ENT_MISSED_EVENT", "CAUSES", 0.8),
            ("ENT_MISSED_EVENT", "ENT_GUILT", "CAUSES", 0.85),
            ("ENT_GUILT", "ENT_STRESS", "CAUSES", 0.7),
            ("ENT_STRESS", "ENT_FRUSTRATION", "CAUSES", 0.65),
        ],
        # Positive homework chain
        [
            ("ENT_HOMEWORK", "ENT_LEARNING", "CAUSES", 0.9),
            ("ENT_LEARNING", "ENT_ACHIEVEMENT", "CAUSES", 0.8),
            ("ENT_ACHIEVEMENT", "ENT_PRIDE", "CAUSES", 0.9),
        ],
        # Conflict resolution chain
        [
            ("ENT_BUDGET", "ENT_STRESS", "CAUSES", 0.7),
            ("ENT_STRESS", "ENT_ARGUMENT", "CAUSES", 0.6),
            ("ENT_ARGUMENT", "ENT_APOLOGY", "CAUSES", 0.5),
            ("ENT_APOLOGY", "ENT_RELIEF", "CAUSES", 0.8),
        ],
        # Family time chain
        [
            ("ENT_DINNER", "ENT_FAMILY_TIME", "CAUSES", 0.85),
            ("ENT_FAMILY_TIME", "ENT_BONDING", "CAUSES", 0.9),
            ("ENT_BONDING", "ENT_LOVE", "CAUSES", 0.95),
        ],
    ]

    edges = []
    for chain in causal_chains:
        for src, tgt, rel, weight in chain:
            edges.append(
                RealWorldEdge(
                    source_id=src,
                    target_id=tgt,
                    relation=rel,
                    weight=weight,
                    edge_type="CAUSES",
                    _observation_count=int(weight * 10),
                )
            )

    return edges


def _create_actions(rng: random.Random) -> List[RealWorldAction]:
    """Create realistic family actions for MCTS."""
    return [
        RealWorldAction(
            "ACT_PARK", "Take kids to the park", 2.0, 0.9, 0.85,
            effects={"family_mood": +0.3, "energy": -0.2},
        ),
        RealWorldAction(
            "ACT_HOMEWORK", "Help with homework", 1.0, 0.8, 0.7,
            effects={"education_progress": +0.2},
        ),
        RealWorldAction(
            "ACT_GROCERY", "Go grocery shopping", 1.0, 0.3, 0.35,
            effects={"pantry_stocked": True},
        ),
        RealWorldAction(
            "ACT_FAMILY_GROCERY", "Family grocery trip", 1.5, 0.6, 0.55,
            effects={"pantry_stocked": True, "family_time": +0.1},
        ),
        RealWorldAction(
            "ACT_EXERCISE", "Morning exercise", 1.0, 0.6, 0.65,
            effects={"energy": +0.2, "stress": -0.1},
        ),
        RealWorldAction(
            "ACT_MOVIE", "Family movie night", 2.0, 0.85, 0.8,
            effects={"family_mood": +0.2, "relaxation": +0.3},
        ),
        RealWorldAction(
            "ACT_COOK", "Cook dinner together", 1.5, 0.75, 0.7,
            effects={"family_bonding": +0.2, "dinner_ready": True},
        ),
        RealWorldAction(
            "ACT_APOLOGIZE", "Apologize to spouse", 0.5, 0.4, 0.3,
            preconditions=["had_argument"],
            effects={"relationship_score": +0.3, "stress": -0.2},
        ),
        RealWorldAction(
            "ACT_QUALITY_TIME", "Quality time with spouse", 1.5, 0.85, 0.8,
            preconditions=["kids_asleep"],
            effects={"relationship_score": +0.4},
        ),
        RealWorldAction(
            "ACT_READ_STORY", "Read bedtime story", 0.5, 0.8, 0.75,
            effects={"bedtime_routine_complete": True, "bonding": +0.2},
        ),
    ]


def _create_goals(rng: random.Random) -> List[RealWorldGoal]:
    """Create realistic family goals."""
    return [
        RealWorldGoal("GOAL_PRESENT", "Be more present with family", 0.95),
        RealWorldGoal("GOAL_EDUCATION", "Support kids' education", 0.9),
        RealWorldGoal("GOAL_BALANCE", "Improve work-life balance", 0.85),
        RealWorldGoal("GOAL_RELATIONSHIP", "Strengthen relationship with spouse", 0.9),
        RealWorldGoal("GOAL_HEALTH", "Maintain family health", 0.8),
        RealWorldGoal("GOAL_MEMORIES", "Create lasting family memories", 0.85),
    ]


def _create_initial_state(rng: random.Random) -> Dict[str, Any]:
    """Create realistic initial state for MCTS."""
    return {
        "time_of_day": "afternoon",
        "day": "Saturday",
        "family_mood": "neutral",
        "spouse_mood": "slightly_frustrated",  # Need repair
        "energy_level": 0.7,
        "pending_tasks": ["grocery_shopping", "homework_help", "laundry"],
        "relationship_debt": 0.2,
        "time_budget_hours": 5.0,
        "kids_homework_done": False,
        "pantry_stocked": False,
    }


def _create_incomplete_episodes(rng: random.Random) -> List[RealWorldIncompleteEpisode]:
    """Create incomplete memories for SPC-UQ."""
    base_time = int(datetime.now().timestamp() * 1000)
    return [
        RealWorldIncompleteEpisode(
            episode_id="INC_REAL_001",
            summary="Something happened with Sarah this morning... can't quite remember the details",
            timestamp=base_time - 3600000,
            location_name=None,  # Missing
            participants=["sarah"],
            activity_type=None,  # Missing
            ambiguity_score=0.7,
        ),
        RealWorldIncompleteEpisode(
            episode_id="INC_REAL_002",
            summary="There was a conversation with spouse about something important...",
            timestamp=base_time - 86400000,
            location_name="home",
            participants=None,  # Missing
            activity_type="discussion",
            ambiguity_score=0.6,
        ),
        RealWorldIncompleteEpisode(
            episode_id="INC_REAL_003",
            summary="Tommy said something that made me laugh...",
            timestamp=base_time - 172800000,
            location_name=None,
            participants=["tommy"],
            activity_type=None,
            ambiguity_score=0.8,
        ),
    ]


def _create_fragments(
    rng: random.Random, incomplete_episodes: List[RealWorldIncompleteEpisode]
) -> List[RealWorldFragment]:
    """Create memory fragments for SPC-UQ."""
    fragments = []
    base_time = int(datetime.now().timestamp() * 1000)

    fragment_templates = [
        ("calendar", "Calendar showed school event at 9am", 0.95),
        ("message", "Text from spouse: 'Remember to pick up milk'", 0.85),
        ("sensory", "Heard kids laughing in the backyard", 0.5),
        ("inferred", "Probably had breakfast around 7am", 0.35),
        ("photo", "Photo shows family at dinner table", 0.9),
        ("voice", "Voice memo: 'Don't forget Tommy's doctor appointment'", 0.75),
    ]

    for ep in incomplete_episodes:
        for i, (prov, content, confidence) in enumerate(rng.sample(fragment_templates, 3)):
            fragments.append(
                RealWorldFragment(
                    fragment_id=f"FRAG_{ep.episode_id}_{i:02d}",
                    source_episode_id=ep.episode_id,
                    source_event_id=f"EVT_{rng.randint(1, 100):03d}",
                    start_time_ms=base_time - rng.randint(0, 86400000),
                    end_time_ms=base_time - rng.randint(0, 43200000),
                    content=content,
                    attributes=(("prov", prov), ("confidence", confidence)),
                )
            )

    return fragments


def _create_context(rng: random.Random) -> Dict[str, Any]:
    """Create context for SPC-UQ."""
    return {
        "time_of_day": "evening",
        "day": "weekday",
        "nearby_locations": ["home_kitchen", "home_living_room", "home_bedroom"],
        "known_locations": [
            "home_kitchen",
            "home_living_room",
            "home_bedroom",
            "home_study",
            "school",
            "office",
            "park",
            "grocery_store",
            "grandma_house",
        ],
        "frequent_contacts": ["spouse", "sarah", "tommy", "grandma"],
        "typical_weekday_activities": [
            "breakfast",
            "school_dropoff",
            "work",
            "homework",
            "dinner",
            "bedtime",
        ],
    }


def _create_schemas() -> List[Dict[str, Any]]:
    """Create schema library for SPC-UQ."""
    return [
        {
            "schema_id": "morning_routine",
            "name": "Morning Routine",
            "typical_sequence": ["wake_up", "breakfast", "get_ready", "school_bus"],
            "locations": ["home_bedroom", "home_kitchen", "home_bathroom"],
            "participants": ["self", "sarah", "tommy"],
            "time_range": {"start": "06:30", "end": "08:30"},
            "confidence_boost": 0.2,
        },
        {
            "schema_id": "weekend_family",
            "name": "Weekend Family Time",
            "typical_sequence": ["breakfast", "activity", "lunch", "rest", "activity", "dinner"],
            "locations": ["home", "park", "restaurant", "grandma_house"],
            "participants": ["self", "spouse", "sarah", "tommy"],
            "time_range": {"start": "08:00", "end": "20:00"},
            "confidence_boost": 0.15,
        },
        {
            "schema_id": "work_conflict",
            "name": "Work Conflict Pattern",
            "typical_sequence": ["urgent_work", "missed_event", "guilt", "repair_attempt"],
            "emotions": ["stress", "guilt", "frustration", "relief"],
            "confidence_boost": 0.1,
        },
        {
            "schema_id": "school_event",
            "name": "School Event",
            "typical_sequence": ["arrive", "event", "congratulate", "celebrate"],
            "locations": ["school", "restaurant"],
            "participants": ["self", "spouse", "sarah", "tommy"],
            "confidence_boost": 0.2,
        },
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Coverage Thresholds
# ─────────────────────────────────────────────────────────────────────────────

REALWORLD_EXPECTED_PROPERTIES = {
    # CPN thresholds
    "cpn_min_counterfactuals": 8,
    "cpn_path_length_ge_2_ratio": 0.4,
    "cpn_path_length_ge_3_count": 2,
    "cpn_max_path_length": 4,
    "cpn_plausibility_variance_min": 0.01,
    "cpn_scenario_type_count": 3,
    # MCTS thresholds
    "mcts_budget_consumption_ratio": 0.7,
    "mcts_max_visit_count": 10,
    "mcts_finds_delayed_reward": True,
    "mcts_reward_spread_min": 0.3,
    # BGT-SM thresholds
    "bgt_insights_min": 3,
    "bgt_pmi_variance_required": True,
    "bgt_semantic_distance_range": [0.2, 0.8],
    # SPC-UQ thresholds
    "spc_reconstructions_min": 2,
    "spc_provenance_types_min": 3,
    "spc_confidence_variance_min": 0.1,
    "spc_schema_match_boost_detected": True,
}


# ─────────────────────────────────────────────────────────────────────────────
# Main Builder
# ─────────────────────────────────────────────────────────────────────────────


def build_world(seed: int = 42, use_ultrabert: bool | None = None):
    """Build the real-world family scenario world.

    Args:
        seed: Random seed for reproducibility.
        use_ultrabert: If True, use UltraBERT embeddings.

    Returns:
        World instance with realistic family data.
    """
    from ..r5_data_factory import World
    from ..r5_embeddings import get_embedding_service

    rng = random.Random(seed)

    # Generate all components
    entities = _create_entities(seed)
    episodes = _create_episodes(rng, entities)
    semantic_edges = _create_semantic_edges(rng, entities)
    kg_edges = _create_kg_edges(rng)
    actions = _create_actions(rng)
    goals = _create_goals(rng)
    initial_state = _create_initial_state(rng)
    incomplete_episodes = _create_incomplete_episodes(rng)
    fragments = _create_fragments(rng, incomplete_episodes)
    context = _create_context(rng)
    schemas = _create_schemas()

    # Generate embeddings
    embedding_service = get_embedding_service(use_ultrabert)
    embeddings = embedding_service.embed_entities(entities)

    return World(
        pack_name="real_world",
        seed=seed,
        episodes=episodes,
        kg_edges=kg_edges,
        entities=entities,
        semantic_edges=semantic_edges,
        embeddings=embeddings,
        initial_state=initial_state,
        actions=actions,
        goals=goals,
        constraints={"time_budget_hours": initial_state["time_budget_hours"]},
        incomplete_episodes=incomplete_episodes,
        fragments=fragments,
        schemas=schemas,
        context=context,
        expected_properties=REALWORLD_EXPECTED_PROPERTIES,
        difficulty="medium",
    )
