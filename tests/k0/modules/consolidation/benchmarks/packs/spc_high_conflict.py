"""SPC High Conflict pack - Edge case testing with highly conflicting provenance data.

Focus: Test SPC-UQ behavior when multiple sources provide contradictory information.
Key scenarios:
- Multiple provenance types all claiming different values for same attribute
- Nested conflicts (conflicts within conflicts)
- Confidence inversions (low-confidence sources contradict high-confidence ones)
- Cascade conflicts (conflict in one attribute affects reconstruction of others)

Expected behavior:
- SPC-UQ should produce high uncertainty (>0.7) for all conflicted reconstructions
- Algorithm should detect and report all conflicts
- Should not crash or produce invalid output
- Should prefer higher-confidence sources when available
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# ─────────────────────────────────────────────────────────────────────────────
# Domain dataclasses
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class HighConflictEpisode:
    """Episode with highly conflicting information from multiple sources."""

    episode_id: str
    summary: str
    timestamp: int
    location_name: Optional[str] = None
    participants: Optional[List[str]] = None
    activity_type: Optional[str] = None
    ambiguity_score: float = 0.9  # High ambiguity for conflict scenarios
    conflict_count: int = 0  # Number of conflicts affecting this episode


@dataclass
class HighConflictFragment:
    """Fragment that conflicts with many others."""

    fragment_id: str
    content: str
    timestamp_ms: int
    provenance_type: str  # calendar, message, sensor, routine, inferred
    confidence: float
    source_id: str
    # Conflict metadata
    conflicts_with: List[str] = field(default_factory=list)  # IDs of conflicting fragments
    conflict_type: str = None  # temporal, spatial, factual, attribution
    conflict_severity: float = 0.5  # 0.0 = minor, 1.0 = complete contradiction
    claimed_value: Any = None  # The value this fragment claims

    @property
    def attributes(self) -> tuple:
        """Return attributes tuple for SPC-UQ compatibility."""
        return (self.provenance_type,)


@dataclass
class ConflictNetwork:
    """Represents a network of conflicting fragments."""

    network_id: str
    fragment_ids: List[str]
    conflict_type: str
    affected_attribute: str
    conflicting_values: List[Any]
    ground_truth: Optional[Any] = None  # What actually happened (for validation)


@dataclass
class HighConflictEntity:
    """Entity referenced in conflicting fragments."""

    entity_id: str
    name: str
    entity_type: str
    category: str
    _observation_count: int = 1

    @property
    def observation_count(self) -> int:
        return self._observation_count


@dataclass
class HighConflictWorld:
    """World with extensive conflicting provenance data."""

    seed: int
    incomplete_episodes: List[HighConflictEpisode]
    fragments: List[HighConflictFragment]
    conflict_networks: List[ConflictNetwork]
    schemas: List[Any]
    context: Dict[str, Any]

    # For algorithm compatibility
    episodes: List[Any] = field(default_factory=list)
    entities: List[HighConflictEntity] = field(default_factory=list)
    kg_edges: List[Any] = field(default_factory=list)
    semantic_edges: List[Any] = field(default_factory=list)
    embeddings: Dict[str, List[float]] = field(default_factory=dict)
    goals: List[Any] = field(default_factory=list)
    actions: List[Any] = field(default_factory=list)
    initial_state: Any = None

    # Conflict metrics
    total_conflicts: int = 0
    max_conflicts_per_attribute: int = 0
    avg_conflict_severity: float = 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Coverage thresholds for high conflict testing
# ─────────────────────────────────────────────────────────────────────────────

COVERAGE_THRESHOLDS = {
    # SPC should detect all conflicts
    "min_reconstructions": 1,
    "min_conflicts": 3,  # High - expect many conflicts
    "require_high_uncertainty_on_conflict": True,
    "uncertainty_on_conflict_min": 0.7,  # Must be high when conflicted

    # Provenance tracking
    "provenance_types_min": 3,  # Multiple sources should be used

    # Performance
    "max_execution_time_ms": 10000,  # 10 second timeout for complex conflict resolution
}


# ─────────────────────────────────────────────────────────────────────────────
# World builder
# ─────────────────────────────────────────────────────────────────────────────


def build_world(seed: int = 42, use_ultrabert: bool = False) -> HighConflictWorld:
    """Build a world with extensive conflicting provenance data.

    Structure:
    - 5 episodes, each with 4+ conflicting fragments
    - Multiple provenance types claiming different values
    - Conflict networks showing which fragments contradict each other
    - Ground truth for validation
    """
    rng = random.Random(seed)
    base_time = 1700000000000

    fragments = []
    conflict_networks = []
    incomplete_episodes = []

    # ─── Conflict Scenario 1: Four-way temporal conflict ─────────────────────
    # Four different sources claim different times for the same event

    incomplete_episodes.append(HighConflictEpisode(
        episode_id="episode_temporal_chaos",
        summary="Event with completely conflicting time claims",
        timestamp=base_time,
        location_name="home",
        participants=None,  # Gap for reconstruction
        activity_type=None,  # Gap for reconstruction
        ambiguity_score=0.95,
        conflict_count=4,
    ))

    temporal_conflict_frags = [
        HighConflictFragment(
            fragment_id="frag_cal_time_1",
            content="Calendar shows meeting at 9:00 AM",
            timestamp_ms=base_time - 3600000,
            provenance_type="calendar",
            confidence=0.9,
            source_id="google_calendar",
            conflict_type="temporal",
            conflict_severity=0.8,
            claimed_value="09:00",
        ),
        HighConflictFragment(
            fragment_id="frag_msg_time_1",
            content="Text from Bob: 'See you at 10:30!'",
            timestamp_ms=base_time - 7200000,
            provenance_type="message",
            confidence=0.7,
            source_id="sms_bob",
            conflict_type="temporal",
            conflict_severity=0.8,
            claimed_value="10:30",
        ),
        HighConflictFragment(
            fragment_id="frag_sens_time_1",
            content="GPS shows arrival at location at 11:15 AM",
            timestamp_ms=base_time,
            provenance_type="sensor",
            confidence=0.95,
            source_id="gps_tracker",
            conflict_type="temporal",
            conflict_severity=0.8,
            claimed_value="11:15",
        ),
        HighConflictFragment(
            fragment_id="frag_rout_time_1",
            content="Typical meeting pattern: 2:00 PM on Wednesdays",
            timestamp_ms=base_time - 86400000,
            provenance_type="routine",
            confidence=0.4,
            source_id="routine_analyzer",
            conflict_type="temporal",
            conflict_severity=0.8,
            claimed_value="14:00",
        ),
    ]

    # Set up conflict relationships
    for i, frag in enumerate(temporal_conflict_frags):
        frag.conflicts_with = [f.fragment_id for f in temporal_conflict_frags if f.fragment_id != frag.fragment_id]

    fragments.extend(temporal_conflict_frags)

    conflict_networks.append(ConflictNetwork(
        network_id="net_temporal_chaos",
        fragment_ids=[f.fragment_id for f in temporal_conflict_frags],
        conflict_type="temporal",
        affected_attribute="time",
        conflicting_values=["09:00", "10:30", "11:15", "14:00"],
        ground_truth="11:15",  # GPS is most reliable
    ))

    # ─── Conflict Scenario 2: Location conflict with confidence inversion ────
    # Low-confidence source has the truth, high-confidence sources are wrong

    incomplete_episodes.append(HighConflictEpisode(
        episode_id="episode_location_inversion",
        summary="Location conflict where reliable sources are wrong",
        timestamp=base_time + 86400000,
        location_name=None,  # Gap for reconstruction
        participants=["Alice"],
        activity_type="meeting",
        ambiguity_score=0.85,
        conflict_count=3,
    ))

    location_conflict_frags = [
        HighConflictFragment(
            fragment_id="frag_cal_loc_1",
            content="Meeting scheduled at Conference Room A",
            timestamp_ms=base_time + 86400000 - 3600000,
            provenance_type="calendar",
            confidence=0.9,  # High confidence, but wrong
            source_id="outlook_calendar",
            conflict_type="spatial",
            conflict_severity=0.9,
            claimed_value="Conference Room A",
        ),
        HighConflictFragment(
            fragment_id="frag_msg_loc_1",
            content="Alice: 'Room changed to Building B lobby'",
            timestamp_ms=base_time + 86400000 - 1800000,
            provenance_type="message",
            confidence=0.6,  # Lower confidence, but correct!
            source_id="slack_alice",
            conflict_type="spatial",
            conflict_severity=0.9,
            claimed_value="Building B lobby",
        ),
        HighConflictFragment(
            fragment_id="frag_inf_loc_1",
            content="Usually meet in Conference Room A based on pattern",
            timestamp_ms=base_time + 86400000 - 86400000,
            provenance_type="inferred",
            confidence=0.5,
            source_id="pattern_analyzer",
            conflict_type="spatial",
            conflict_severity=0.7,
            claimed_value="Conference Room A",
        ),
    ]

    for frag in location_conflict_frags:
        frag.conflicts_with = [f.fragment_id for f in location_conflict_frags if f.fragment_id != frag.fragment_id and f.claimed_value != frag.claimed_value]

    fragments.extend(location_conflict_frags)

    conflict_networks.append(ConflictNetwork(
        network_id="net_location_inversion",
        fragment_ids=[f.fragment_id for f in location_conflict_frags],
        conflict_type="spatial",
        affected_attribute="location",
        conflicting_values=["Conference Room A", "Building B lobby"],
        ground_truth="Building B lobby",  # The message was correct
    ))

    # ─── Conflict Scenario 3: Cascade conflict (attribution affects facts) ───
    # Who did something affects what was done

    incomplete_episodes.append(HighConflictEpisode(
        episode_id="episode_cascade_conflict",
        summary="Cascading conflict - attribution affects factual reconstruction",
        timestamp=base_time + 172800000,
        location_name="office",
        participants=None,  # Gap - who was there?
        activity_type=None,  # Gap - what happened depends on who
        ambiguity_score=0.9,
        conflict_count=5,
    ))

    cascade_conflict_frags = [
        HighConflictFragment(
            fragment_id="frag_msg_who_1",
            content="Bob: 'I'll handle the presentation'",
            timestamp_ms=base_time + 172800000 - 7200000,
            provenance_type="message",
            confidence=0.8,
            source_id="email_bob",
            conflict_type="attribution",
            conflict_severity=0.8,
            claimed_value={"who": "Bob", "what": "presentation"},
        ),
        HighConflictFragment(
            fragment_id="frag_msg_who_2",
            content="Carol: 'Taking over the presentation from Bob'",
            timestamp_ms=base_time + 172800000 - 3600000,
            provenance_type="message",
            confidence=0.85,
            source_id="email_carol",
            conflict_type="attribution",
            conflict_severity=0.9,
            claimed_value={"who": "Carol", "what": "presentation"},
        ),
        HighConflictFragment(
            fragment_id="frag_cal_who_1",
            content="Presentation - Bob (presenter)",
            timestamp_ms=base_time + 172800000 - 86400000,
            provenance_type="calendar",
            confidence=0.7,
            source_id="team_calendar",
            conflict_type="attribution",
            conflict_severity=0.7,
            claimed_value={"who": "Bob", "what": "presentation"},
        ),
        HighConflictFragment(
            fragment_id="frag_sens_who_1",
            content="Badge scan: Carol entered presentation room at 2:00 PM",
            timestamp_ms=base_time + 172800000,
            provenance_type="sensor",
            confidence=0.95,
            source_id="badge_system",
            conflict_type="attribution",
            conflict_severity=0.5,
            claimed_value={"who": "Carol", "location": "presentation room"},
        ),
        HighConflictFragment(
            fragment_id="frag_sens_who_2",
            content="Badge scan: Bob entered break room at 2:00 PM",
            timestamp_ms=base_time + 172800000,
            provenance_type="sensor",
            confidence=0.95,
            source_id="badge_system",
            conflict_type="attribution",
            conflict_severity=0.5,
            claimed_value={"who": "Bob", "location": "break room"},
        ),
    ]

    # Complex conflict relationships
    cascade_conflict_frags[0].conflicts_with = ["frag_msg_who_2", "frag_sens_who_2"]
    cascade_conflict_frags[1].conflicts_with = ["frag_msg_who_1", "frag_cal_who_1"]
    cascade_conflict_frags[2].conflicts_with = ["frag_msg_who_2", "frag_sens_who_1"]
    cascade_conflict_frags[3].conflicts_with = ["frag_msg_who_1", "frag_cal_who_1"]
    cascade_conflict_frags[4].conflicts_with = ["frag_msg_who_1", "frag_cal_who_1"]

    fragments.extend(cascade_conflict_frags)

    conflict_networks.append(ConflictNetwork(
        network_id="net_cascade_conflict",
        fragment_ids=[f.fragment_id for f in cascade_conflict_frags],
        conflict_type="attribution",
        affected_attribute="participants",
        conflicting_values=["Bob", "Carol"],
        ground_truth="Carol",  # Carol actually did the presentation
    ))

    # ─── Conflict Scenario 4: Complete information void with false signals ───
    # All sources provide conflicting info, no clear winner

    incomplete_episodes.append(HighConflictEpisode(
        episode_id="episode_void_conflict",
        summary="Complete information chaos - no source is reliable",
        timestamp=base_time + 259200000,
        location_name=None,
        participants=None,
        activity_type=None,
        ambiguity_score=0.99,  # Maximum ambiguity
        conflict_count=4,
    ))

    void_conflict_frags = [
        HighConflictFragment(
            fragment_id="frag_cal_void_1",
            content="Dentist appointment at 3 PM",
            timestamp_ms=base_time + 259200000 - 86400000,
            provenance_type="calendar",
            confidence=0.3,  # Low - calendar often wrong
            source_id="personal_calendar",
            conflict_type="factual",
            conflict_severity=1.0,
            claimed_value="dentist",
        ),
        HighConflictFragment(
            fragment_id="frag_msg_void_1",
            content="Mom: 'Don't forget dinner at 3!'",
            timestamp_ms=base_time + 259200000 - 3600000,
            provenance_type="message",
            confidence=0.4,
            source_id="sms_mom",
            conflict_type="factual",
            conflict_severity=1.0,
            claimed_value="dinner with mom",
        ),
        HighConflictFragment(
            fragment_id="frag_rout_void_1",
            content="Thursdays at 3 PM: Usually gym session",
            timestamp_ms=base_time + 259200000 - 604800000,
            provenance_type="routine",
            confidence=0.35,
            source_id="routine_analyzer",
            conflict_type="factual",
            conflict_severity=1.0,
            claimed_value="gym",
        ),
        HighConflictFragment(
            fragment_id="frag_inf_void_1",
            content="Likely free time based on low activity pattern",
            timestamp_ms=base_time + 259200000 - 172800000,
            provenance_type="inferred",
            confidence=0.25,
            source_id="activity_analyzer",
            conflict_type="factual",
            conflict_severity=0.8,
            claimed_value="free time",
        ),
    ]

    for frag in void_conflict_frags:
        frag.conflicts_with = [f.fragment_id for f in void_conflict_frags if f.fragment_id != frag.fragment_id]

    fragments.extend(void_conflict_frags)

    conflict_networks.append(ConflictNetwork(
        network_id="net_void_conflict",
        fragment_ids=[f.fragment_id for f in void_conflict_frags],
        conflict_type="factual",
        affected_attribute="activity",
        conflicting_values=["dentist", "dinner with mom", "gym", "free time"],
        ground_truth=None,  # Unknown - true ambiguity
    ))

    # ─── Conflict Scenario 5: Nested conflicts (meta-conflict) ───────────────
    # Conflicts about when the conflicting events happened

    incomplete_episodes.append(HighConflictEpisode(
        episode_id="episode_nested_conflict",
        summary="Nested conflict - even the conflict timeline is disputed",
        timestamp=base_time + 345600000,
        location_name="park",
        participants=["family"],
        activity_type=None,
        ambiguity_score=0.88,
        conflict_count=3,
    ))

    nested_conflict_frags = [
        HighConflictFragment(
            fragment_id="frag_cal_nested_1",
            content="Picnic scheduled for Saturday",
            timestamp_ms=base_time + 345600000 - 172800000,
            provenance_type="calendar",
            confidence=0.7,
            source_id="family_calendar",
            conflict_type="temporal",
            conflict_severity=0.7,
            claimed_value="Saturday",
        ),
        HighConflictFragment(
            fragment_id="frag_msg_nested_1",
            content="Spouse: 'Picnic moved to Sunday because of rain'",
            timestamp_ms=base_time + 345600000 - 86400000,
            provenance_type="message",
            confidence=0.8,
            source_id="spouse_text",
            conflict_type="temporal",
            conflict_severity=0.8,
            claimed_value="Sunday",
        ),
        HighConflictFragment(
            fragment_id="frag_sens_nested_1",
            content="Weather data: Saturday was sunny, Sunday had rain",
            timestamp_ms=base_time + 345600000,
            provenance_type="sensor",
            confidence=0.99,
            source_id="weather_api",
            conflict_type="factual",  # Conflicts with the message's reasoning
            conflict_severity=0.9,
            claimed_value="Saturday sunny",
        ),
    ]

    nested_conflict_frags[0].conflicts_with = ["frag_msg_nested_1"]
    nested_conflict_frags[1].conflicts_with = ["frag_cal_nested_1", "frag_sens_nested_1"]
    nested_conflict_frags[2].conflicts_with = ["frag_msg_nested_1"]

    fragments.extend(nested_conflict_frags)

    conflict_networks.append(ConflictNetwork(
        network_id="net_nested_conflict",
        fragment_ids=[f.fragment_id for f in nested_conflict_frags],
        conflict_type="nested",
        affected_attribute="day",
        conflicting_values=["Saturday", "Sunday"],
        ground_truth="Saturday",  # Weather proves the message was wrong
    ))

    # Create entities for compatibility
    entities = [
        HighConflictEntity("ENT_BOB", "Bob", "person", "colleague"),
        HighConflictEntity("ENT_CAROL", "Carol", "person", "colleague"),
        HighConflictEntity("ENT_ALICE", "Alice", "person", "friend"),
        HighConflictEntity("ENT_MOM", "Mom", "person", "family"),
        HighConflictEntity("ENT_SPOUSE", "Spouse", "person", "family"),
    ]

    # Calculate conflict metrics
    total_conflicts = len(conflict_networks)
    max_conflicts = max(len(cn.conflicting_values) for cn in conflict_networks)
    avg_severity = sum(f.conflict_severity for f in fragments if f.conflict_severity) / len(fragments)

    return HighConflictWorld(
        seed=seed,
        incomplete_episodes=incomplete_episodes,
        fragments=fragments,
        conflict_networks=conflict_networks,
        schemas=[],
        context={
            "conflict_mode": "high",
            "provenance_types": ["calendar", "message", "sensor", "routine", "inferred"],
            "nearby_locations": ["home", "office", "park", "Conference Room A", "Building B lobby"],
            "known_locations": ["home", "office", "park"],
            "frequent_contacts": ["Bob", "Carol", "Alice", "Mom", "Spouse"],
        },
        entities=entities,
        embeddings={e.entity_id: [0.5] * 384 for e in entities},
        total_conflicts=total_conflicts,
        max_conflicts_per_attribute=max_conflicts,
        avg_conflict_severity=avg_severity,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Expected properties for validation
# ─────────────────────────────────────────────────────────────────────────────

EXPECTED_PROPERTIES = {
    "total_conflict_networks": 5,
    "min_fragments_with_conflicts": 15,
    "provenance_types_used": 5,
    "should_produce_high_uncertainty": True,
    "avg_uncertainty_min": 0.7,
}
