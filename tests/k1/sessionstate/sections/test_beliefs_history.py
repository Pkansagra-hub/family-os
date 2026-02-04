"""
Test Suite: BeliefsHistorySection (WARM tier)
==============================================

Tests for k1/sessionstate/sections/beliefs_history.py

Coverage:
- Data class tests (Fact, ArchivedFact, EntityFactIndex, EvictedData)
- ISection protocol compliance
- IEvictable protocol compliance
- Demotion API (accept from HOT)
- Access API (get, list, count)
- Query API (by entity, subject, predicate, turn range, search)
- Promotion API (get candidates, remove for promotion)
- LRU management and turn advancement
- Archive management
- Statistics
- Integrity API
- FlatBuffer serialization
- Apply operations (MutationGuard pattern)
- Factory function
- Edge cases
"""

import time
from typing import Any, Dict, List

import pytest

from k1.sessionstate.sections.beliefs_history import (
    ArchivedFact,
    BeliefsHistorySection,
    EntityFactIndex,
    EvictedData,
    Fact,
    PrivacyBand,
    create_beliefs_history_section,
)

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def section() -> BeliefsHistorySection:
    """Create empty section for testing."""
    return BeliefsHistorySection()


@pytest.fixture
def sample_fact() -> Fact:
    """Create sample fact."""
    return Fact(
        id="fact-001",
        subject="user",
        predicate="likes",
        object="pizza",
        confidence=0.9,
        source="inference",
        timestamp_ms=1700000000000,
        privacy_band=PrivacyBand.GREEN,
    )


@pytest.fixture
def sample_fact_dict() -> Dict[str, Any]:
    """Create sample fact as dict (from HOT tier)."""
    return {
        "id": "fact-001",
        "subject": "user",
        "predicate": "likes",
        "object": "pizza",
        "confidence": 0.9,
        "source": "inference",
        "timestamp_ms": 1700000000000,
        "privacy_band": 0,
        "original_turn": 5,
        "last_accessed_turn": 5,
        "access_count": 3,
    }


@pytest.fixture
def multiple_facts() -> List[Dict[str, Any]]:
    """Create multiple facts for testing."""
    return [
        {
            "id": f"fact-{i:03d}",
            "subject": f"entity-{i % 3}",
            "predicate": "has_property",
            "object": f"value-{i}",
            "confidence": 0.8 + (i % 3) * 0.05,
            "original_turn": i,
            "access_count": i % 5,
        }
        for i in range(10)
    ]


# =============================================================================
# Test Class: Fact Dataclass
# =============================================================================


class TestFact:
    """Tests for Fact dataclass."""

    def test_create_fact(self, sample_fact: Fact):
        """Test fact creation."""
        assert sample_fact.id == "fact-001"
        assert sample_fact.subject == "user"
        assert sample_fact.predicate == "likes"
        assert sample_fact.object == "pizza"
        assert sample_fact.confidence == 0.9
        assert sample_fact.privacy_band == PrivacyBand.GREEN

    def test_fact_defaults(self):
        """Test fact default values."""
        fact = Fact(id="f1", subject="s", predicate="p", object="o")
        assert fact.confidence == 1.0
        assert fact.source == ""
        assert fact.timestamp_ms == 0
        assert fact.privacy_band == PrivacyBand.GREEN

    def test_fact_privacy_bands(self):
        """Test all privacy bands."""
        for band in PrivacyBand:
            fact = Fact(id="f1", subject="s", predicate="p", object="o", privacy_band=band)
            assert fact.privacy_band == band


# =============================================================================
# Test Class: ArchivedFact Dataclass
# =============================================================================


class TestArchivedFact:
    """Tests for ArchivedFact dataclass."""

    def test_create_archived_fact(self, sample_fact: Fact):
        """Test archived fact creation."""
        archived = ArchivedFact(fact=sample_fact, original_turn=5)
        assert archived.fact.id == "fact-001"
        assert archived.original_turn == 5
        assert archived.lru_score == 1.0
        assert archived.is_stale is False

    def test_mark_accessed(self, sample_fact: Fact):
        """Test marking as accessed."""
        archived = ArchivedFact(fact=sample_fact, access_count=0)
        archived.mark_accessed(turn=10)

        assert archived.access_count == 1
        assert archived.last_accessed_turn == 10
        assert archived.is_stale is False

    def test_update_lru_score_fresh(self, sample_fact: Fact):
        """Test LRU score for recently accessed fact."""
        archived = ArchivedFact(fact=sample_fact, last_accessed_turn=10)
        archived.update_lru_score(current_turn=10)

        # Should have high score (recently accessed)
        assert archived.lru_score >= 0.9

    def test_update_lru_score_stale(self, sample_fact: Fact):
        """Test LRU score decays over time."""
        archived = ArchivedFact(fact=sample_fact, last_accessed_turn=5, access_count=0)
        archived.update_lru_score(current_turn=20)

        # Should have decayed score
        assert archived.lru_score < 1.0

    def test_to_dict(self, sample_fact: Fact):
        """Test dictionary conversion."""
        archived = ArchivedFact(
            fact=sample_fact,
            original_turn=5,
            access_count=3,
        )
        d = archived.to_dict()

        assert d["fact"]["id"] == "fact-001"
        assert d["original_turn"] == 5
        assert d["access_count"] == 3


# =============================================================================
# Test Class: EntityFactIndex Dataclass
# =============================================================================


class TestEntityFactIndex:
    """Tests for EntityFactIndex dataclass."""

    def test_create_entity_index(self):
        """Test entity index creation."""
        idx = EntityFactIndex(entity_id="entity-1")
        assert idx.entity_id == "entity-1"
        assert idx.fact_indices == []

    def test_add_fact_index(self):
        """Test adding fact index."""
        idx = EntityFactIndex(entity_id="entity-1")
        idx.add_fact_index(0, turn=5)
        idx.add_fact_index(3, turn=5)

        assert 0 in idx.fact_indices
        assert 3 in idx.fact_indices
        assert idx.last_updated_turn == 5

    def test_add_duplicate_index(self):
        """Test adding duplicate index is ignored."""
        idx = EntityFactIndex(entity_id="entity-1")
        idx.add_fact_index(0, turn=5)
        idx.add_fact_index(0, turn=6)

        assert idx.fact_indices.count(0) == 1

    def test_remove_fact_index(self):
        """Test removing fact index."""
        idx = EntityFactIndex(entity_id="entity-1", fact_indices=[0, 1, 2])
        idx.remove_fact_index(1)

        assert 1 not in idx.fact_indices
        assert len(idx.fact_indices) == 2


# =============================================================================
# Test Class: EvictedData Dataclass
# =============================================================================


class TestEvictedData:
    """Tests for EvictedData dataclass."""

    def test_create_evicted_data(self, sample_fact: Fact):
        """Test evicted data creation."""
        archived = ArchivedFact(fact=sample_fact)
        evicted = EvictedData(facts=[archived], bytes_freed=100)

        assert len(evicted.facts) == 1
        assert evicted.bytes_freed == 100
        assert evicted.eviction_reason == "pressure"


# =============================================================================
# Test Class: ISection Protocol
# =============================================================================


class TestISectionProtocol:
    """Tests for ISection protocol compliance."""

    def test_name(self, section: BeliefsHistorySection):
        """Test section name."""
        assert section.name == "beliefs_history"

    def test_tier(self, section: BeliefsHistorySection):
        """Test section tier."""
        assert section.tier == "warm"

    def test_budget_bytes(self, section: BeliefsHistorySection):
        """Test budget."""
        assert section.budget_bytes == 12288  # 12KB

    def test_get_size_bytes_empty(self, section: BeliefsHistorySection):
        """Test size calculation for empty section."""
        size = section.get_size_bytes()
        assert size > 0  # Base overhead
        assert size < 500

    def test_get_size_bytes_with_facts(
        self, section: BeliefsHistorySection, sample_fact_dict: Dict[str, Any]
    ):
        """Test size increases with facts."""
        initial_size = section.get_size_bytes()
        section.accept_demoted([sample_fact_dict], turn=5)
        assert section.get_size_bytes() > initial_size

    def test_clear(self, section: BeliefsHistorySection, sample_fact_dict: Dict[str, Any]):
        """Test clear removes all data."""
        section.accept_demoted([sample_fact_dict], turn=5)
        section.clear()

        assert section.count() == 0
        assert len(section._entity_index) == 0

    def test_to_dict(self, section: BeliefsHistorySection):
        """Test dictionary representation."""
        d = section.to_dict()

        assert d["name"] == "beliefs_history"
        assert d["tier"] == "warm"
        assert "facts" in d
        assert "total_facts" in d


# =============================================================================
# Test Class: IEvictable Protocol
# =============================================================================


class TestIEvictableProtocol:
    """Tests for IEvictable protocol compliance."""

    def test_get_eviction_priority(self, section: BeliefsHistorySection):
        """Test eviction priority."""
        assert section.get_eviction_priority() == 2

    def test_can_evict_empty(self, section: BeliefsHistorySection):
        """Test can_evict when empty."""
        assert section.can_evict() is False

    def test_can_evict_with_facts(
        self, section: BeliefsHistorySection, sample_fact_dict: Dict[str, Any]
    ):
        """Test can_evict with facts."""
        section.accept_demoted([sample_fact_dict], turn=5)
        assert section.can_evict() is True

    def test_evict_partial(
        self, section: BeliefsHistorySection, multiple_facts: List[Dict[str, Any]]
    ):
        """Test partial eviction."""
        section.accept_demoted(multiple_facts, turn=10)
        initial_count = section.count()

        # Make some facts stale
        section.advance_turn(50)

        evicted = section.evict_partial(target_kb=0.5)

        assert len(evicted.facts) > 0
        assert evicted.bytes_freed > 0
        assert section.count() < initial_count

    def test_get_eviction_candidates(
        self, section: BeliefsHistorySection, multiple_facts: List[Dict[str, Any]]
    ):
        """Test getting eviction candidates."""
        section.accept_demoted(multiple_facts, turn=10)
        section.advance_turn(50)

        candidates = section.get_eviction_candidates(count=3)

        assert len(candidates) == 3
        # Should be sorted by LRU score (lowest first)
        assert candidates[0].lru_score <= candidates[1].lru_score


# =============================================================================
# Test Class: Demotion API
# =============================================================================


class TestDemotionAPI:
    """Tests for demotion/accept from HOT tier."""

    def test_accept_demoted_single(
        self, section: BeliefsHistorySection, sample_fact_dict: Dict[str, Any]
    ):
        """Test accepting single demoted fact."""
        count = section.accept_demoted([sample_fact_dict], turn=5)

        assert count == 1
        assert section.count() == 1

    def test_accept_demoted_multiple(
        self, section: BeliefsHistorySection, multiple_facts: List[Dict[str, Any]]
    ):
        """Test accepting multiple demoted facts."""
        count = section.accept_demoted(multiple_facts, turn=10)

        assert count == len(multiple_facts)
        assert section.count() == len(multiple_facts)

    def test_accept_demoted_preserves_metadata(
        self, section: BeliefsHistorySection, sample_fact_dict: Dict[str, Any]
    ):
        """Test demotion preserves original metadata."""
        section.accept_demoted([sample_fact_dict], turn=5)

        fact = section.get_without_access("fact-001")
        assert fact is not None
        assert fact.original_turn == 5
        assert fact.access_count == 3

    def test_accept_demoted_sets_demoted_at(
        self, section: BeliefsHistorySection, sample_fact_dict: Dict[str, Any]
    ):
        """Test demotion sets demoted_at_ms."""
        before = int(time.time() * 1000)
        section.accept_demoted([sample_fact_dict], turn=5)
        after = int(time.time() * 1000)

        fact = section.get("fact-001")
        assert fact is not None
        assert before <= fact.demoted_at_ms <= after

    def test_accept_demoted_updates_entity_index(
        self, section: BeliefsHistorySection, sample_fact_dict: Dict[str, Any]
    ):
        """Test demotion updates entity index."""
        section.accept_demoted([sample_fact_dict], turn=5)

        # Should have index entries for subject and object
        assert "user" in section._entity_index
        assert "pizza" in section._entity_index

    def test_accept_demoted_at_max_evicts_oldest(self, section: BeliefsHistorySection):
        """Test accepting at max capacity evicts oldest."""
        section._max_facts = 5

        # Add 5 facts
        facts = [
            {"id": f"f-{i}", "subject": "s", "predicate": "p", "object": "o"} for i in range(5)
        ]
        section.accept_demoted(facts, turn=5)
        assert section.count() == 5

        # Add one more - should evict one
        section.accept_demoted(
            [{"id": "f-new", "subject": "s", "predicate": "p", "object": "o"}], turn=10
        )
        assert section.count() == 5
        assert section.get_archived_count() == 1


# =============================================================================
# Test Class: Access API
# =============================================================================


class TestAccessAPI:
    """Tests for access/retrieval API."""

    def test_get_existing(self, section: BeliefsHistorySection, sample_fact_dict: Dict[str, Any]):
        """Test getting existing fact."""
        section.accept_demoted([sample_fact_dict], turn=5)

        fact = section.get("fact-001")
        assert fact is not None
        assert fact.fact.id == "fact-001"

    def test_get_nonexistent(self, section: BeliefsHistorySection):
        """Test getting nonexistent fact."""
        fact = section.get("nonexistent")
        assert fact is None

    def test_get_increments_access_count(
        self, section: BeliefsHistorySection, sample_fact_dict: Dict[str, Any]
    ):
        """Test get increments access count."""
        section.accept_demoted([sample_fact_dict], turn=5)
        initial_count = section.get("fact-001").access_count

        section.get("fact-001")
        assert section.get("fact-001").access_count > initial_count

    def test_get_without_access(
        self, section: BeliefsHistorySection, sample_fact_dict: Dict[str, Any]
    ):
        """Test get without incrementing access."""
        sample_fact_dict["access_count"] = 0
        section.accept_demoted([sample_fact_dict], turn=5)

        fact = section.get_without_access("fact-001")
        assert fact is not None
        assert fact.access_count == 0

    def test_list_facts(self, section: BeliefsHistorySection, multiple_facts: List[Dict[str, Any]]):
        """Test listing all facts."""
        section.accept_demoted(multiple_facts, turn=10)

        facts = section.list_facts()
        assert len(facts) == len(multiple_facts)

    def test_count(self, section: BeliefsHistorySection, multiple_facts: List[Dict[str, Any]]):
        """Test count."""
        section.accept_demoted(multiple_facts, turn=10)
        assert section.count() == len(multiple_facts)

    def test_contains(self, section: BeliefsHistorySection, sample_fact_dict: Dict[str, Any]):
        """Test contains check."""
        section.accept_demoted([sample_fact_dict], turn=5)

        assert section.contains("fact-001") is True
        assert section.contains("nonexistent") is False


# =============================================================================
# Test Class: Query API
# =============================================================================


class TestQueryAPI:
    """Tests for query/search API."""

    def test_get_by_entity(
        self, section: BeliefsHistorySection, multiple_facts: List[Dict[str, Any]]
    ):
        """Test getting facts by entity."""
        section.accept_demoted(multiple_facts, turn=10)

        facts = section.get_by_entity("entity-0")
        assert len(facts) > 0
        for fact in facts:
            assert "entity-0" in [fact.fact.subject, fact.fact.object]

    def test_get_by_subject(
        self, section: BeliefsHistorySection, multiple_facts: List[Dict[str, Any]]
    ):
        """Test getting facts by subject."""
        section.accept_demoted(multiple_facts, turn=10)

        facts = section.get_by_subject("entity-1")
        assert all(f.fact.subject == "entity-1" for f in facts)

    def test_get_by_predicate(
        self, section: BeliefsHistorySection, multiple_facts: List[Dict[str, Any]]
    ):
        """Test getting facts by predicate."""
        section.accept_demoted(multiple_facts, turn=10)

        facts = section.get_by_predicate("has_property")
        assert len(facts) == len(multiple_facts)

    def test_get_by_turn_range(
        self, section: BeliefsHistorySection, multiple_facts: List[Dict[str, Any]]
    ):
        """Test getting facts by turn range."""
        section.accept_demoted(multiple_facts, turn=10)

        facts = section.get_by_turn_range(3, 6)
        for fact in facts:
            assert 3 <= fact.original_turn <= 6

    def test_search_by_subject(
        self, section: BeliefsHistorySection, multiple_facts: List[Dict[str, Any]]
    ):
        """Test search by subject."""
        section.accept_demoted(multiple_facts, turn=10)

        results = section.search(subject="entity-0")
        assert all(r.fact.subject == "entity-0" for r in results)

    def test_search_by_predicate(
        self, section: BeliefsHistorySection, multiple_facts: List[Dict[str, Any]]
    ):
        """Test search by predicate."""
        section.accept_demoted(multiple_facts, turn=10)

        results = section.search(predicate="has_property")
        assert len(results) == len(multiple_facts)

    def test_search_combined(self, section: BeliefsHistorySection):
        """Test search with multiple criteria."""
        facts = [
            {"id": "f1", "subject": "a", "predicate": "p", "object": "x"},
            {"id": "f2", "subject": "a", "predicate": "q", "object": "y"},
            {"id": "f3", "subject": "b", "predicate": "p", "object": "z"},
        ]
        section.accept_demoted(facts, turn=5)

        results = section.search(subject="a", predicate="p")
        assert len(results) == 1
        assert results[0].fact.id == "f1"


# =============================================================================
# Test Class: Promotion API
# =============================================================================


class TestPromotionAPI:
    """Tests for promotion back to HOT tier."""

    def test_get_promotion_candidates_empty(self, section: BeliefsHistorySection):
        """Test no candidates when empty."""
        candidates = section.get_promotion_candidates()
        assert len(candidates) == 0

    def test_get_promotion_candidates_threshold(
        self, section: BeliefsHistorySection, multiple_facts: List[Dict[str, Any]]
    ):
        """Test candidates meet threshold."""
        section.accept_demoted(multiple_facts, turn=10)

        # Access some facts multiple times
        section.get("fact-003")
        section.get("fact-003")
        section.get("fact-003")  # 3+ accesses

        candidates = section.get_promotion_candidates()
        assert all(c.access_count >= section.PROMOTION_THRESHOLD for c in candidates)

    def test_get_promotion_candidates_sorted(self, section: BeliefsHistorySection):
        """Test candidates sorted by access count."""
        facts = [
            {"id": "f1", "subject": "s", "predicate": "p", "object": "o", "access_count": 5},
            {"id": "f2", "subject": "s", "predicate": "p", "object": "o", "access_count": 10},
            {"id": "f3", "subject": "s", "predicate": "p", "object": "o", "access_count": 3},
        ]
        section.accept_demoted(facts, turn=5)

        candidates = section.get_promotion_candidates()
        assert candidates[0].access_count >= candidates[-1].access_count

    def test_remove_for_promotion(
        self, section: BeliefsHistorySection, sample_fact_dict: Dict[str, Any]
    ):
        """Test removing facts for promotion."""
        section.accept_demoted([sample_fact_dict], turn=5)

        removed = section.remove_for_promotion(["fact-001"])

        assert len(removed) == 1
        assert removed[0].fact.id == "fact-001"
        assert section.count() == 0


# =============================================================================
# Test Class: LRU Management
# =============================================================================


class TestLRUManagement:
    """Tests for LRU score management."""

    def test_advance_turn_updates_scores(
        self, section: BeliefsHistorySection, sample_fact_dict: Dict[str, Any]
    ):
        """Test advancing turn updates LRU scores."""
        section.accept_demoted([sample_fact_dict], turn=5)
        initial_score = section.get_without_access("fact-001").lru_score

        section.advance_turn(50)
        new_score = section.get_without_access("fact-001").lru_score

        assert new_score < initial_score

    def test_advance_turn_marks_stale(self, section: BeliefsHistorySection):
        """Test advancing turn marks facts as stale."""
        facts = [{"id": "f1", "subject": "s", "predicate": "p", "object": "o", "access_count": 0}]
        section.accept_demoted(facts, turn=5)

        section.advance_turn(100)

        fact = section.get_without_access("f1")
        # Low LRU score should mark as stale
        assert fact.lru_score < 0.3

    def test_get_current_turn(self, section: BeliefsHistorySection):
        """Test getting current turn."""
        section.advance_turn(25)
        assert section.get_current_turn() == 25


# =============================================================================
# Test Class: Archive Management
# =============================================================================


class TestArchiveManagement:
    """Tests for K0 archive management."""

    def test_set_get_archive_pointer(self, section: BeliefsHistorySection):
        """Test setting/getting archive pointer."""
        section.set_archive_pointer("k0://beliefs/session-123")
        assert section.get_archive_pointer() == "k0://beliefs/session-123"

    def test_get_archived_count_initial(self, section: BeliefsHistorySection):
        """Test initial archived count is zero."""
        assert section.get_archived_count() == 0

    def test_archived_count_increments_on_eviction(
        self, section: BeliefsHistorySection, multiple_facts: List[Dict[str, Any]]
    ):
        """Test archived count increments on eviction."""
        section.accept_demoted(multiple_facts, turn=10)
        section.advance_turn(100)

        section.evict_partial(target_kb=1.0)

        assert section.get_archived_count() > 0


# =============================================================================
# Test Class: Statistics
# =============================================================================


class TestStatistics:
    """Tests for statistics API."""

    def test_get_statistics_empty(self, section: BeliefsHistorySection):
        """Test statistics for empty section."""
        stats = section.get_statistics()

        assert stats["total_facts"] == 0
        assert stats["entity_count"] == 0
        assert stats["avg_lru_score"] == 0.0

    def test_get_statistics_with_facts(
        self, section: BeliefsHistorySection, multiple_facts: List[Dict[str, Any]]
    ):
        """Test statistics with facts."""
        section.accept_demoted(multiple_facts, turn=10)

        stats = section.get_statistics()

        assert stats["total_facts"] == len(multiple_facts)
        assert stats["max_facts"] == 100
        assert stats["entity_count"] > 0
        assert "avg_lru_score" in stats


# =============================================================================
# Test Class: Integrity API
# =============================================================================


class TestIntegrityAPI:
    """Tests for integrity hash API."""

    def test_compute_integrity(
        self, section: BeliefsHistorySection, sample_fact_dict: Dict[str, Any]
    ):
        """Test computing integrity hash."""
        section.accept_demoted([sample_fact_dict], turn=5)

        hash_val = section.compute_integrity()
        assert len(hash_val) == 64  # SHA256 hex

    def test_set_get_integrity(self, section: BeliefsHistorySection):
        """Test setting/getting integrity hash."""
        section.set_integrity("abc123")
        assert section.get_integrity() == "abc123"

    def test_verify_integrity_no_hash(self, section: BeliefsHistorySection):
        """Test verify returns True when no hash set."""
        assert section.verify_integrity() is True

    def test_verify_integrity_matching(
        self, section: BeliefsHistorySection, sample_fact_dict: Dict[str, Any]
    ):
        """Test verify returns True when hash matches."""
        section.accept_demoted([sample_fact_dict], turn=5)
        section.update_integrity()

        assert section.verify_integrity() is True

    def test_verify_integrity_mismatch(
        self, section: BeliefsHistorySection, sample_fact_dict: Dict[str, Any]
    ):
        """Test verify returns False when hash mismatches."""
        section.accept_demoted([sample_fact_dict], turn=5)
        section.set_integrity("wrong-hash")

        assert section.verify_integrity() is False


# =============================================================================
# Test Class: FlatBuffer Serialization
# =============================================================================


class TestFlatBufferSerialization:
    """Tests for FlatBuffer serialization."""

    def test_to_flatbuffer_returns_bytes(
        self, section: BeliefsHistorySection, sample_fact_dict: Dict[str, Any]
    ):
        """Test serialization returns bytes."""
        section.accept_demoted([sample_fact_dict], turn=5)

        data = section.to_flatbuffer()
        assert isinstance(data, bytes)
        assert len(data) > 0

    def test_to_flatbuffer_caching(
        self, section: BeliefsHistorySection, sample_fact_dict: Dict[str, Any]
    ):
        """Test serialization is cached."""
        section.accept_demoted([sample_fact_dict], turn=5)

        data1 = section.to_flatbuffer()
        data2 = section.to_flatbuffer()

        assert data1 is data2  # Same object (cached)

    def test_cache_invalidated_on_mutation(
        self, section: BeliefsHistorySection, sample_fact_dict: Dict[str, Any]
    ):
        """Test cache invalidated on mutation."""
        section.accept_demoted([sample_fact_dict], turn=5)
        data1 = section.to_flatbuffer()

        section.accept_demoted([{**sample_fact_dict, "id": "fact-002"}], turn=6)
        data2 = section.to_flatbuffer()

        assert data1 is not data2

    def test_from_flatbuffer_restores_facts(
        self, section: BeliefsHistorySection, sample_fact_dict: Dict[str, Any]
    ):
        """Test deserialization restores facts."""
        section.accept_demoted([sample_fact_dict], turn=5)

        data = section.to_flatbuffer()
        restored = BeliefsHistorySection.from_flatbuffer(data)

        assert restored.count() == 1
        fact = restored.get_without_access("fact-001")
        assert fact is not None
        assert fact.fact.subject == "user"
        assert fact.fact.object == "pizza"

    def test_from_flatbuffer_restores_metadata(
        self, section: BeliefsHistorySection, multiple_facts: List[Dict[str, Any]]
    ):
        """Test deserialization restores metadata."""
        section.accept_demoted(multiple_facts, turn=10)
        section._archived_count = 5
        section.set_archive_pointer("k0://test")

        data = section.to_flatbuffer()
        restored = BeliefsHistorySection.from_flatbuffer(data)

        assert restored.get_archived_count() == 5
        assert restored.get_archive_pointer() == "k0://test"

    def test_round_trip_preserves_data(
        self, section: BeliefsHistorySection, multiple_facts: List[Dict[str, Any]]
    ):
        """Test round-trip preserves all data."""
        section.accept_demoted(multiple_facts, turn=10)
        section.advance_turn(15)

        data = section.to_flatbuffer()
        restored = BeliefsHistorySection.from_flatbuffer(data)

        assert restored.count() == section.count()
        for fact in section.list_facts():
            restored_fact = restored.get_without_access(fact.fact.id)
            assert restored_fact is not None
            # Use approximate comparison for float32 precision
            assert abs(restored_fact.fact.confidence - fact.fact.confidence) < 0.001


# =============================================================================
# Test Class: Apply Operations
# =============================================================================


class TestApplyOperations:
    """Tests for MutationGuard apply operations."""

    def test_apply_accept_demoted(
        self, section: BeliefsHistorySection, sample_fact_dict: Dict[str, Any]
    ):
        """Test apply accept_demoted operation."""
        result = section.apply("accept_demoted", {"facts": [sample_fact_dict], "turn": 5})

        assert result == 1
        assert section.count() == 1

    def test_apply_get(self, section: BeliefsHistorySection, sample_fact_dict: Dict[str, Any]):
        """Test apply get operation."""
        section.accept_demoted([sample_fact_dict], turn=5)

        result = section.apply("get", {"fact_id": "fact-001"})

        assert result is not None
        assert result.fact.id == "fact-001"

    def test_apply_remove(self, section: BeliefsHistorySection, sample_fact_dict: Dict[str, Any]):
        """Test apply remove operation."""
        section.accept_demoted([sample_fact_dict], turn=5)

        result = section.apply("remove", {"fact_id": "fact-001"})

        assert result is True
        assert section.count() == 0

    def test_apply_advance_turn(self, section: BeliefsHistorySection):
        """Test apply advance_turn operation."""
        section.apply("advance_turn", {"turn": 25})

        assert section.get_current_turn() == 25

    def test_apply_evict_partial(
        self, section: BeliefsHistorySection, multiple_facts: List[Dict[str, Any]]
    ):
        """Test apply evict_partial operation."""
        section.accept_demoted(multiple_facts, turn=10)
        section.advance_turn(100)

        result = section.apply("evict_partial", {"target_kb": 1.0})

        assert isinstance(result, EvictedData)
        assert len(result.facts) > 0

    def test_apply_set_archive_pointer(self, section: BeliefsHistorySection):
        """Test apply set_archive_pointer operation."""
        section.apply("set_archive_pointer", {"pointer": "k0://test"})

        assert section.get_archive_pointer() == "k0://test"

    def test_apply_clear(self, section: BeliefsHistorySection, sample_fact_dict: Dict[str, Any]):
        """Test apply clear operation."""
        section.accept_demoted([sample_fact_dict], turn=5)

        section.apply("clear", {})

        assert section.count() == 0

    def test_apply_unknown_operation(self, section: BeliefsHistorySection):
        """Test apply raises for unknown operation."""
        with pytest.raises(ValueError, match="Unknown operation"):
            section.apply("unknown_op", {})


# =============================================================================
# Test Class: Factory Function
# =============================================================================


class TestFactoryFunction:
    """Tests for factory function."""

    def test_create_default(self):
        """Test creating with defaults."""
        section = create_beliefs_history_section()

        assert section.name == "beliefs_history"
        assert section._max_facts == 100
        assert section._eviction_threshold == 0.2

    def test_create_with_params(self):
        """Test creating with custom params."""
        section = create_beliefs_history_section(
            max_facts=50,
            eviction_threshold=0.3,
        )

        assert section._max_facts == 50
        assert section._eviction_threshold == 0.3


# =============================================================================
# Test Class: Utility Methods
# =============================================================================


class TestUtilityMethods:
    """Tests for utility methods."""

    def test_repr(self, section: BeliefsHistorySection, sample_fact_dict: Dict[str, Any]):
        """Test string representation."""
        section.accept_demoted([sample_fact_dict], turn=5)

        repr_str = repr(section)
        assert "BeliefsHistorySection" in repr_str
        assert "facts=" in repr_str

    def test_len(self, section: BeliefsHistorySection, multiple_facts: List[Dict[str, Any]]):
        """Test __len__ method."""
        section.accept_demoted(multiple_facts, turn=10)
        assert len(section) == len(multiple_facts)


# =============================================================================
# Test Class: Edge Cases
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_empty_fact_strings(self, section: BeliefsHistorySection):
        """Test handling empty strings."""
        facts = [{"id": "f1", "subject": "", "predicate": "", "object": ""}]
        section.accept_demoted(facts, turn=5)

        assert section.count() == 1

    def test_unicode_strings(self, section: BeliefsHistorySection):
        """Test handling unicode strings."""
        facts = [{"id": "f1", "subject": "user", "predicate": "likes", "object": "pizza"}]
        section.accept_demoted(facts, turn=5)

        fact = section.get("f1")
        assert fact.fact.object == "pizza"

    def test_max_facts_boundary(self, section: BeliefsHistorySection):
        """Test at max facts boundary."""
        section._max_facts = 5
        facts = [
            {"id": f"f-{i}", "subject": "s", "predicate": "p", "object": "o"} for i in range(5)
        ]
        section.accept_demoted(facts, turn=5)

        assert section.count() == 5
        assert section.get_archived_count() == 0

    def test_remove_nonexistent(self, section: BeliefsHistorySection):
        """Test removing nonexistent fact."""
        result = section.remove("nonexistent")
        assert result is False

    def test_search_no_results(self, section: BeliefsHistorySection):
        """Test search with no results."""
        results = section.search(subject="nonexistent")
        assert len(results) == 0

    def test_entity_index_cleanup(self, section: BeliefsHistorySection):
        """Test entity index is cleaned up on removal."""
        facts = [{"id": "f1", "subject": "entity-unique", "predicate": "p", "object": "o"}]
        section.accept_demoted(facts, turn=5)

        assert "entity-unique" in section._entity_index

        section.remove("f1")

        assert "entity-unique" not in section._entity_index

    def test_multiple_entities_same_fact(self, section: BeliefsHistorySection):
        """Test fact indexed by multiple entities."""
        facts = [
            {"id": "f1", "subject": "entity-a", "predicate": "related_to", "object": "entity-b"}
        ]
        section.accept_demoted(facts, turn=5)

        assert "entity-a" in section._entity_index
        assert "entity-b" in section._entity_index

    def test_high_access_count_boosts_lru(self, section: BeliefsHistorySection):
        """Test high access count boosts LRU score."""
        facts = [{"id": "f1", "subject": "s", "predicate": "p", "object": "o", "access_count": 100}]
        section.accept_demoted(facts, turn=5)
        section.advance_turn(20)

        fact = section.get_without_access("f1")
        # High access count should give bonus to LRU score
        assert fact.lru_score > 0.4
