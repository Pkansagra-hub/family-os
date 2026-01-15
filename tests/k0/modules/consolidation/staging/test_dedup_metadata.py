"""
Unit tests for DedupMetadataPopulator — Issue 5.1.3

Tests the deduplication metadata population logic for staged
event updates from DuplicateDetector results.

Spec Reference:
    - Dossier §4.7.2 (Deduplication Metadata)
    - Dossier §7.4.2 (M19 DuplicateDetector)
    - M5_EXECUTION.md Issue 5.1.3
"""

from __future__ import annotations

import json
from typing import List, Optional

import pytest

from k0.modules.consolidation.staging.dedup_metadata import (
    DedupMetadata,
    DedupMetadataPopulator,
    NearDuplicateEntry,
    create_near_duplicate_entry,
    parse_near_duplicates_json,
    parse_novelty_bonuses_json,
)

# =============================================================================
# Test Fixtures: Mock Classes
# =============================================================================


class MockNoveltyBonuses:
    """Mock NoveltyBonuses for testing."""

    def __init__(
        self,
        first_occurrence: float = 0.0,
        milestone: float = 0.0,
        rare_pattern: float = 0.0,
        temporal_anomaly: float = 0.0,
        routine_penalty: float = 0.0,
    ):
        self.first_occurrence = first_occurrence
        self.milestone = milestone
        self.rare_pattern = rare_pattern
        self.temporal_anomaly = temporal_anomaly
        self.routine_penalty = routine_penalty

    @property
    def total_bonus(self) -> float:
        """Calculate total bonus."""
        return (
            self.first_occurrence
            + self.milestone
            + self.rare_pattern
            + self.temporal_anomaly
            - self.routine_penalty
        )


class MockDuplicationResult:
    """Mock DuplicationResult for testing."""

    def __init__(
        self,
        is_duplicate: bool = False,
        duplicate_of: Optional[str] = None,
        near_duplicates: Optional[List[str]] = None,
        novelty_score: float = 1.0,
        bonuses: Optional[MockNoveltyBonuses] = None,
        match_method: str = "TWO_STAGE",
        max_similarity: float = 0.0,
    ):
        self.is_duplicate = is_duplicate
        self.duplicate_of = duplicate_of
        self.near_duplicates = near_duplicates or []
        self.novelty_score = novelty_score
        self.bonuses = bonuses or MockNoveltyBonuses()
        self.match_method = match_method
        self.max_similarity = max_similarity


class MockEventState:
    """Mock P03EventState for testing."""

    def __init__(
        self,
        event_id: str = "evt_001",
        is_duplicate: bool = False,
        duplicate_of_id: Optional[str] = None,
        cluster_id: Optional[str] = None,
        novelty_factor: float = 1.0,
    ):
        self.event_id = event_id
        self.is_duplicate = is_duplicate
        self.duplicate_of_id = duplicate_of_id
        self.cluster_id = cluster_id
        self.novelty_factor = novelty_factor


class MockDedupMerge:
    """Mock DedupMerge for testing."""

    def __init__(
        self,
        duplicate_id: str,
        canonical_id: str,
        hamming_distance: int = 2,
        merge_confidence: float = 0.95,
    ):
        self.duplicate_id = duplicate_id
        self.canonical_id = canonical_id
        self.hamming_distance = hamming_distance
        self.merge_confidence = merge_confidence


@pytest.fixture
def populator() -> DedupMetadataPopulator:
    """Provide a DedupMetadataPopulator instance."""
    return DedupMetadataPopulator()


@pytest.fixture
def default_bonuses() -> MockNoveltyBonuses:
    """Provide default bonuses with all zeros."""
    return MockNoveltyBonuses()


@pytest.fixture
def active_bonuses() -> MockNoveltyBonuses:
    """Provide bonuses with non-zero values."""
    return MockNoveltyBonuses(
        first_occurrence=0.1,
        milestone=0.05,
        rare_pattern=0.02,
        temporal_anomaly=0.0,
        routine_penalty=0.03,
    )


# =============================================================================
# Test: NearDuplicateEntry
# =============================================================================


class TestNearDuplicateEntry:
    """Tests for NearDuplicateEntry dataclass."""

    def test_create_entry_with_all_fields(self):
        """Create entry with all fields populated."""
        entry = NearDuplicateEntry(
            event_id="evt_002",
            hamming_distance=3,
            embedding_similarity=0.9234,
            detection_stage="SIMHASH",
        )

        assert entry.event_id == "evt_002"
        assert entry.hamming_distance == 3
        assert entry.embedding_similarity == 0.9234
        assert entry.detection_stage == "SIMHASH"

    def test_create_entry_with_none_hamming(self):
        """Create entry with None hamming_distance (embedding-only)."""
        entry = NearDuplicateEntry(
            event_id="evt_003",
            hamming_distance=None,
            embedding_similarity=0.85,
            detection_stage="EMBEDDING",
        )

        assert entry.hamming_distance is None

    def test_to_dict_rounds_similarity(self):
        """to_dict() should round embedding_similarity to 4 decimals."""
        entry = NearDuplicateEntry(
            event_id="evt_004",
            hamming_distance=2,
            embedding_similarity=0.9234567,
            detection_stage="TWO_STAGE",
        )

        d = entry.to_dict()

        assert d["embedding_similarity"] == 0.9235  # Rounded

    def test_to_dict_structure(self):
        """to_dict() should return proper structure."""
        entry = NearDuplicateEntry(
            event_id="evt_005",
            hamming_distance=None,
            embedding_similarity=0.8,
            detection_stage="EMBEDDING",
        )

        d = entry.to_dict()

        assert d == {
            "event_id": "evt_005",
            "hamming_distance": None,
            "embedding_similarity": 0.8,
            "detection_stage": "EMBEDDING",
        }


# =============================================================================
# Test: DedupMetadata
# =============================================================================


class TestDedupMetadata:
    """Tests for DedupMetadata dataclass."""

    def test_create_with_defaults(self):
        """Create DedupMetadata with default values."""
        metadata = DedupMetadata(event_id="evt_001")

        assert metadata.event_id == "evt_001"
        assert metadata.near_duplicates_json == "[]"
        assert metadata.novelty_score == 1.0
        assert metadata.episode_cluster_id is None
        assert metadata.novelty_bonuses_json == "{}"
        assert metadata.is_duplicate is False
        assert metadata.duplicate_of is None

    def test_create_with_all_fields(self):
        """Create DedupMetadata with all fields populated."""
        metadata = DedupMetadata(
            event_id="evt_001",
            near_duplicates_json='[{"event_id":"evt_002"}]',
            novelty_score=0.75,
            episode_cluster_id="cluster_001",
            novelty_bonuses_json='{"first_occurrence":0.1}',
            is_duplicate=True,
            duplicate_of="evt_canonical",
        )

        assert metadata.novelty_score == 0.75
        assert metadata.episode_cluster_id == "cluster_001"
        assert metadata.is_duplicate is True
        assert metadata.duplicate_of == "evt_canonical"

    def test_clamps_novelty_score_above_one(self):
        """novelty_score should be clamped to [0, 1]."""
        metadata = DedupMetadata(
            event_id="evt_001",
            novelty_score=1.5,
        )

        assert metadata.novelty_score == 1.0

    def test_clamps_novelty_score_below_zero(self):
        """novelty_score should be clamped to [0, 1]."""
        metadata = DedupMetadata(
            event_id="evt_001",
            novelty_score=-0.5,
        )

        assert metadata.novelty_score == 0.0

    def test_validates_near_duplicates_json(self):
        """Invalid near_duplicates_json should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid near_duplicates_json"):
            DedupMetadata(
                event_id="evt_001",
                near_duplicates_json="not valid json",
            )

    def test_validates_novelty_bonuses_json(self):
        """Invalid novelty_bonuses_json should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid novelty_bonuses_json"):
            DedupMetadata(
                event_id="evt_001",
                novelty_bonuses_json="{invalid}",
            )


# =============================================================================
# Test: DedupMetadataPopulator.from_duplication_result
# =============================================================================


class TestFromDuplicationResult:
    """Tests for from_duplication_result method."""

    def test_basic_population(
        self, populator: DedupMetadataPopulator, default_bonuses: MockNoveltyBonuses
    ):
        """Basic population from DuplicationResult."""
        event_state = MockEventState(event_id="evt_001", cluster_id="cluster_A")
        dedup_result = MockDuplicationResult(
            is_duplicate=False,
            novelty_score=0.85,
            bonuses=default_bonuses,
        )

        metadata = populator.from_duplication_result(event_state, dedup_result)

        assert metadata.event_id == "evt_001"
        assert metadata.novelty_score == 0.85
        assert metadata.episode_cluster_id == "cluster_A"
        assert metadata.is_duplicate is False

    def test_with_near_duplicates_ids(
        self, populator: DedupMetadataPopulator, default_bonuses: MockNoveltyBonuses
    ):
        """Population with near_duplicates (event IDs only)."""
        event_state = MockEventState(event_id="evt_001")
        dedup_result = MockDuplicationResult(
            near_duplicates=["evt_002", "evt_003"],
            novelty_score=0.6,
            bonuses=default_bonuses,
            match_method="SIMHASH",
            max_similarity=0.92,
        )

        metadata = populator.from_duplication_result(event_state, dedup_result)

        # Parse and verify near_duplicates
        near_dups = json.loads(metadata.near_duplicates_json)
        assert len(near_dups) == 2
        assert near_dups[0]["event_id"] == "evt_002"
        assert near_dups[0]["detection_stage"] == "SIMHASH"
        assert near_dups[0]["embedding_similarity"] == 0.92

    def test_with_near_duplicate_details(
        self, populator: DedupMetadataPopulator, default_bonuses: MockNoveltyBonuses
    ):
        """Population with pre-built NearDuplicateEntry list."""
        event_state = MockEventState(event_id="evt_001")
        dedup_result = MockDuplicationResult(
            near_duplicates=["evt_002"],  # Will be overridden
            novelty_score=0.5,
            bonuses=default_bonuses,
        )
        entries = [
            NearDuplicateEntry(
                event_id="evt_002",
                hamming_distance=2,
                embedding_similarity=0.95,
                detection_stage="SIMHASH",
            ),
        ]

        metadata = populator.from_duplication_result(
            event_state, dedup_result, near_duplicate_details=entries
        )

        near_dups = json.loads(metadata.near_duplicates_json)
        assert len(near_dups) == 1
        assert near_dups[0]["hamming_distance"] == 2
        assert near_dups[0]["embedding_similarity"] == 0.95

    def test_duplicate_event(
        self, populator: DedupMetadataPopulator, default_bonuses: MockNoveltyBonuses
    ):
        """Population for a duplicate event."""
        event_state = MockEventState(event_id="evt_dup")
        dedup_result = MockDuplicationResult(
            is_duplicate=True,
            duplicate_of="evt_canonical",
            novelty_score=0.0,
            bonuses=default_bonuses,
        )

        metadata = populator.from_duplication_result(event_state, dedup_result)

        assert metadata.is_duplicate is True
        assert metadata.duplicate_of == "evt_canonical"
        assert metadata.novelty_score == 0.0

    def test_bonuses_json_structure(
        self, populator: DedupMetadataPopulator, active_bonuses: MockNoveltyBonuses
    ):
        """Verify bonuses JSON structure."""
        event_state = MockEventState(event_id="evt_001")
        dedup_result = MockDuplicationResult(
            novelty_score=0.8,
            bonuses=active_bonuses,
        )

        metadata = populator.from_duplication_result(event_state, dedup_result)

        bonuses = json.loads(metadata.novelty_bonuses_json)
        assert bonuses["first_occurrence"] == 0.1
        assert bonuses["milestone"] == 0.05
        assert bonuses["rare_pattern"] == 0.02
        assert bonuses["temporal_anomaly"] == 0.0
        assert bonuses["routine_penalty"] == 0.03
        assert "total_bonus" in bonuses


# =============================================================================
# Test: DedupMetadataPopulator.from_event_state
# =============================================================================


class TestFromEventState:
    """Tests for from_event_state method."""

    def test_basic_population_no_merges(self, populator: DedupMetadataPopulator):
        """Basic population from event state without dedup_merges."""
        event_state = MockEventState(
            event_id="evt_001",
            cluster_id="cluster_B",
            novelty_factor=0.7,
        )

        metadata = populator.from_event_state(event_state)

        assert metadata.event_id == "evt_001"
        assert metadata.episode_cluster_id == "cluster_B"
        assert metadata.novelty_score == 0.7
        assert metadata.near_duplicates_json == "[]"

    def test_uses_default_novelty_when_zero(self, populator: DedupMetadataPopulator):
        """Uses default novelty score when novelty_factor is 0."""
        event_state = MockEventState(
            event_id="evt_001",
            novelty_factor=0.0,
        )

        metadata = populator.from_event_state(event_state)

        assert metadata.novelty_score == 1.0  # Default

    def test_with_dedup_merges_as_duplicate(self, populator: DedupMetadataPopulator):
        """Population with dedup_merges where event is the duplicate."""
        event_state = MockEventState(
            event_id="evt_dup",
            is_duplicate=True,
            duplicate_of_id="evt_canonical",
        )
        merges = [
            MockDedupMerge(
                duplicate_id="evt_dup",
                canonical_id="evt_canonical",
                hamming_distance=2,
                merge_confidence=0.95,
            ),
        ]

        metadata = populator.from_event_state(event_state, dedup_merges=merges)

        assert metadata.is_duplicate is True
        assert metadata.duplicate_of == "evt_canonical"

        near_dups = json.loads(metadata.near_duplicates_json)
        assert len(near_dups) == 1
        assert near_dups[0]["event_id"] == "evt_canonical"
        assert near_dups[0]["hamming_distance"] == 2

    def test_with_dedup_merges_as_canonical(self, populator: DedupMetadataPopulator):
        """Population with dedup_merges where event is the canonical."""
        event_state = MockEventState(
            event_id="evt_canonical",
            is_duplicate=False,
        )
        merges = [
            MockDedupMerge(
                duplicate_id="evt_dup",
                canonical_id="evt_canonical",
                hamming_distance=2,
                merge_confidence=0.95,
            ),
        ]

        metadata = populator.from_event_state(event_state, dedup_merges=merges)

        near_dups = json.loads(metadata.near_duplicates_json)
        assert len(near_dups) == 1
        assert near_dups[0]["event_id"] == "evt_dup"


# =============================================================================
# Test: build_near_duplicates_json
# =============================================================================


class TestBuildNearDuplicatesJson:
    """Tests for build_near_duplicates_json method."""

    def test_empty_list(self, populator: DedupMetadataPopulator):
        """Empty list produces empty JSON array."""
        result = populator.build_near_duplicates_json([])

        assert result == "[]"

    def test_single_entry(self, populator: DedupMetadataPopulator):
        """Single entry produces correct JSON."""
        entries = [
            NearDuplicateEntry(
                event_id="evt_002",
                hamming_distance=3,
                embedding_similarity=0.9,
                detection_stage="SIMHASH",
            ),
        ]

        result = populator.build_near_duplicates_json(entries)
        parsed = json.loads(result)

        assert len(parsed) == 1
        assert parsed[0]["event_id"] == "evt_002"

    def test_multiple_entries(self, populator: DedupMetadataPopulator):
        """Multiple entries produce correct JSON array."""
        entries = [
            NearDuplicateEntry("evt_002", 2, 0.95, "SIMHASH"),
            NearDuplicateEntry("evt_003", None, 0.87, "EMBEDDING"),
            NearDuplicateEntry("evt_004", 5, 0.82, "TWO_STAGE"),
        ]

        result = populator.build_near_duplicates_json(entries)
        parsed = json.loads(result)

        assert len(parsed) == 3
        assert parsed[1]["hamming_distance"] is None

    def test_compact_json_format(self, populator: DedupMetadataPopulator):
        """JSON should be compact (no extra whitespace)."""
        entries = [
            NearDuplicateEntry("evt_002", 2, 0.9, "SIMHASH"),
        ]

        result = populator.build_near_duplicates_json(entries)

        assert " " not in result  # No spaces in compact format


# =============================================================================
# Test: Detection Stage Normalization
# =============================================================================


class TestDetectionStageNormalization:
    """Tests for _normalize_detection_stage method."""

    def test_simhash_variations(self, populator: DedupMetadataPopulator):
        """Various SIMHASH spellings normalize correctly."""
        assert populator._normalize_detection_stage("SIMHASH") == "SIMHASH"
        assert populator._normalize_detection_stage("simhash") == "SIMHASH"
        assert populator._normalize_detection_stage("SimHash") == "SIMHASH"

    def test_embedding_variations(self, populator: DedupMetadataPopulator):
        """Various EMBEDDING spellings normalize correctly."""
        assert populator._normalize_detection_stage("EMBEDDING") == "EMBEDDING"
        assert populator._normalize_detection_stage("embedding") == "EMBEDDING"
        assert populator._normalize_detection_stage("EMBEDDING_FALLBACK") == "EMBEDDING"

    def test_two_stage_variations(self, populator: DedupMetadataPopulator):
        """Various TWO_STAGE spellings normalize correctly."""
        assert populator._normalize_detection_stage("TWO_STAGE") == "TWO_STAGE"
        assert populator._normalize_detection_stage("two_stage") == "TWO_STAGE"
        assert populator._normalize_detection_stage("TWOSTAGE") == "TWO_STAGE"

    def test_unknown_method_defaults_to_two_stage(self, populator: DedupMetadataPopulator):
        """Unknown methods default to TWO_STAGE."""
        assert populator._normalize_detection_stage("CUSTOM_METHOD") == "TWO_STAGE"

    def test_empty_string_returns_unknown(self, populator: DedupMetadataPopulator):
        """Empty string returns UNKNOWN."""
        assert populator._normalize_detection_stage("") == "UNKNOWN"


# =============================================================================
# Test: Utility Functions
# =============================================================================


class TestUtilityFunctions:
    """Tests for module-level utility functions."""

    def test_create_near_duplicate_entry(self):
        """Factory function creates proper entry."""
        entry = create_near_duplicate_entry(
            event_id="evt_002",
            hamming_distance=3,
            embedding_similarity=0.9,
            detection_stage="SIMHASH",
        )

        assert isinstance(entry, NearDuplicateEntry)
        assert entry.event_id == "evt_002"

    def test_create_near_duplicate_entry_defaults(self):
        """Factory function uses defaults."""
        entry = create_near_duplicate_entry(event_id="evt_003")

        assert entry.hamming_distance is None
        assert entry.embedding_similarity == 0.0
        assert entry.detection_stage == "TWO_STAGE"

    def test_parse_near_duplicates_json(self):
        """Parsing JSON produces NearDuplicateEntry list."""
        json_str = '[{"event_id":"evt_002","hamming_distance":2,"embedding_similarity":0.95,"detection_stage":"SIMHASH"}]'

        entries = parse_near_duplicates_json(json_str)

        assert len(entries) == 1
        assert entries[0].event_id == "evt_002"
        assert entries[0].hamming_distance == 2

    def test_parse_near_duplicates_json_empty(self):
        """Parsing empty JSON array produces empty list."""
        entries = parse_near_duplicates_json("[]")

        assert entries == []

    def test_parse_novelty_bonuses_json(self):
        """Parsing bonuses JSON produces dict."""
        json_str = '{"first_occurrence":0.1,"milestone":0.05,"total_bonus":0.12}'

        result = parse_novelty_bonuses_json(json_str)

        assert result["first_occurrence"] == 0.1
        assert result["total_bonus"] == 0.12

    def test_parse_novelty_bonuses_json_empty(self):
        """Parsing empty JSON object produces empty dict."""
        result = parse_novelty_bonuses_json("{}")

        assert result == {}


# =============================================================================
# Test: Edge Cases
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_very_high_similarity(self, populator: DedupMetadataPopulator):
        """Similarity of exactly 1.0 handled correctly."""
        entries = [NearDuplicateEntry("evt_002", 0, 1.0, "SIMHASH")]

        result = populator.build_near_duplicates_json(entries)
        parsed = json.loads(result)

        assert parsed[0]["embedding_similarity"] == 1.0

    def test_very_low_similarity(self, populator: DedupMetadataPopulator):
        """Similarity close to 0.0 handled correctly."""
        entries = [NearDuplicateEntry("evt_002", None, 0.0001, "EMBEDDING")]

        result = populator.build_near_duplicates_json(entries)
        parsed = json.loads(result)

        assert parsed[0]["embedding_similarity"] == 0.0001

    def test_no_cluster_id(
        self, populator: DedupMetadataPopulator, default_bonuses: MockNoveltyBonuses
    ):
        """None cluster_id preserved correctly."""
        event_state = MockEventState(event_id="evt_001", cluster_id=None)
        dedup_result = MockDuplicationResult(bonuses=default_bonuses)

        metadata = populator.from_duplication_result(event_state, dedup_result)

        assert metadata.episode_cluster_id is None

    def test_special_characters_in_event_id(self, populator: DedupMetadataPopulator):
        """Event IDs with special characters handled in JSON."""
        entries = [NearDuplicateEntry('evt_"special', None, 0.5, "EMBEDDING")]

        result = populator.build_near_duplicates_json(entries)
        parsed = json.loads(result)

        assert parsed[0]["event_id"] == 'evt_"special'
