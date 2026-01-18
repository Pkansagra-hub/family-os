"""
Unit Tests for GAP-001 Milestone 5: Entity Extractor

Tests for EntityExtractor component:
- Entity extraction from truth layer records
- Handling of different entity column types (JSON arrays vs scalars)
- SearchResult integration

Test Coverage:
- extract_from_record for each layer type
- extract_from_records batch processing
- extract_from_search_results with records_by_id
- Edge cases: empty records, missing columns

GAP Reference: GAP_001 Section 6 (Rich LLM Context)
Milestone Reference: GAP_001_MILESTONE_5_CONTEXT_EXPANDER (Issue 5.1)
"""

from k0.modules.recall.entity_extractor import EntityExtractor, ExtractionResult


class TestExtractionResult:
    """Tests for ExtractionResult dataclass."""

    def test_create_empty_result(self):
        """Test creating empty ExtractionResult."""
        result = ExtractionResult()
        assert len(result.entity_ids) == 0
        assert len(result.by_layer) == 0
        assert result.record_count == 0

    def test_create_with_entities(self):
        """Test creating ExtractionResult with data."""
        result = ExtractionResult(
            entity_ids={"Mom", "Dad"},
            by_layer={"st_epi": {"Mom", "Dad"}},
            record_count=2,
        )
        assert "Mom" in result.entity_ids
        assert "Dad" in result.entity_ids
        assert len(result.entity_ids) == 2

    def test_merge_results(self):
        """Test merging two ExtractionResults."""
        result1 = ExtractionResult(
            entity_ids={"Mom"},
            by_layer={"st_epi": {"Mom"}},
            record_count=1,
        )
        result2 = ExtractionResult(
            entity_ids={"Dad"},
            by_layer={"st_sem": {"Dad"}},
            record_count=1,
        )
        merged = result1.merge(result2)
        assert merged.entity_ids == {"Mom", "Dad"}
        assert merged.record_count == 2


class TestEntityExtractor:
    """Tests for EntityExtractor."""

    def test_init(self):
        """Test EntityExtractor initialization."""
        extractor = EntityExtractor()
        assert extractor is not None

    # =========================================================================
    # extract_from_record Tests
    # =========================================================================

    def test_extract_from_st_epi_record(self):
        """Test extracting entities from st_epi (participants_json)."""
        extractor = EntityExtractor()
        record = {
            "episode_id": "epi_123",
            "participants_json": ["Mom", "Dad", "Child"],
            "embedding_text": "Family dinner",
        }
        entities = extractor.extract_from_record(record, "st_epi")
        assert entities == {"Mom", "Dad", "Child"}

    def test_extract_from_st_epi_with_json_string(self):
        """Test extracting from st_epi with JSON string participants."""
        extractor = EntityExtractor()
        record = {
            "episode_id": "epi_123",
            "participants_json": '["Mom", "Dad"]',
            "embedding_text": "Family dinner",
        }
        entities = extractor.extract_from_record(record, "st_epi")
        assert entities == {"Mom", "Dad"}

    def test_extract_from_st_sem_record(self):
        """Test extracting entities from st_sem (actor_id)."""
        extractor = EntityExtractor()
        record = {
            "pattern_id": "sem_456",
            "actor_id": "Mom",
            "pattern_type": "PREFERENCE",
        }
        entities = extractor.extract_from_record(record, "st_sem")
        assert entities == {"Mom"}

    def test_extract_from_st_procedural_record(self):
        """Test extracting entities from st_procedural (actor_id)."""
        extractor = EntityExtractor()
        record = {
            "routine_id": "proc_789",
            "actor_id": "Dad",
            "routine_name": "Morning coffee",
        }
        entities = extractor.extract_from_record(record, "st_procedural")
        assert entities == {"Dad"}

    def test_extract_from_st_social_record(self):
        """Test extracting entities from st_social (actor_a_id, actor_b_id)."""
        extractor = EntityExtractor()
        record = {
            "relationship_id": "soc_101",
            "actor_a_id": "Mom",
            "actor_b_id": "Dad",
            "relationship_type": "SPOUSE",
        }
        entities = extractor.extract_from_record(record, "st_social")
        assert entities == {"Mom", "Dad"}

    def test_extract_from_st_prospective_record(self):
        """Test extracting entities from st_prospective (actor_id)."""
        extractor = EntityExtractor()
        record = {
            "intention_id": "int_202",
            "actor_id": "Child",
            "description": "Finish homework",
        }
        entities = extractor.extract_from_record(record, "st_prospective")
        assert entities == {"Child"}

    def test_extract_from_st_kg_dom_record(self):
        """Test extracting entities from st_kg_dom (entity_id IS the entity)."""
        extractor = EntityExtractor()
        record = {
            "entity_id": "Mom",
            "entity_type": "PERSON",
            "display_name": "Mom",
        }
        entities = extractor.extract_from_record(record, "st_kg_dom")
        assert entities == {"Mom"}

    def test_extract_with_missing_column(self):
        """Test extraction when entity column is missing."""
        extractor = EntityExtractor()
        record = {
            "pattern_id": "sem_456",
            "pattern_type": "PREFERENCE",
            # actor_id is missing
        }
        entities = extractor.extract_from_record(record, "st_sem")
        assert entities == set()

    def test_extract_with_none_value(self):
        """Test extraction when entity column is None."""
        extractor = EntityExtractor()
        record = {
            "pattern_id": "sem_456",
            "actor_id": None,
            "pattern_type": "PREFERENCE",
        }
        entities = extractor.extract_from_record(record, "st_sem")
        assert entities == set()

    def test_extract_from_unknown_layer(self):
        """Test extraction from unknown layer returns empty set."""
        extractor = EntityExtractor()
        record = {"id": "unknown_123"}
        entities = extractor.extract_from_record(record, "unknown_layer")
        assert entities == set()

    # =========================================================================
    # extract_from_records Tests
    # =========================================================================

    def test_extract_from_records_batch(self):
        """Test batch extraction from multiple records of same layer."""
        extractor = EntityExtractor()
        records = [
            {"episode_id": "epi_1", "participants_json": ["Mom", "Dad"]},
            {"episode_id": "epi_2", "participants_json": ["Child"]},
        ]
        result = extractor.extract_from_records(records, "st_epi")

        assert "Mom" in result.entity_ids
        assert "Dad" in result.entity_ids
        assert "Child" in result.entity_ids
        assert result.record_count == 2

    def test_extract_from_empty_records(self):
        """Test extraction from empty records list."""
        extractor = EntityExtractor()
        result = extractor.extract_from_records([], "st_epi")
        assert len(result.entity_ids) == 0
        assert result.record_count == 0

    def test_extract_deduplicates_entities(self):
        """Test that entities are deduplicated across records."""
        extractor = EntityExtractor()
        records = [
            {"episode_id": "epi_1", "participants_json": ["Mom", "Dad"]},
            {"episode_id": "epi_2", "participants_json": ["Mom", "Child"]},
        ]
        result = extractor.extract_from_records(records, "st_epi")

        # Mom appears twice but should be deduplicated
        assert len(result.entity_ids) == 3
        assert result.entity_ids == {"Mom", "Dad", "Child"}

    # =========================================================================
    # extract_from_search_results Tests
    # =========================================================================

    def test_extract_from_search_results(self):
        """Test extraction from search results with records_by_id."""
        extractor = EntityExtractor()

        # Search results as tuples: (layer, record_id, score)
        results = [
            ("st_epi", "epi_1", 0.95),
            ("st_sem", "sem_1", 0.87),
        ]

        # Pre-fetched records
        records_by_id = {
            "epi_1": {"participants_json": ["Mom", "Dad"]},
            "sem_1": {"actor_id": "Child"},
        }

        extraction = extractor.extract_from_search_results(results, records_by_id)

        assert "Mom" in extraction.entity_ids
        assert "Dad" in extraction.entity_ids
        assert "Child" in extraction.entity_ids
        assert len(extraction.entity_ids) == 3

    def test_extract_from_empty_search_results(self):
        """Test extraction from empty search results."""
        extractor = EntityExtractor()
        result = extractor.extract_from_search_results([], {})
        assert len(result.entity_ids) == 0

    def test_extract_handles_missing_records(self):
        """Test extraction when record not found in records_by_id."""
        extractor = EntityExtractor()

        results = [
            ("st_sem", "sem_1", 0.87),
        ]
        records_by_id = {}  # Empty - record not found

        extraction = extractor.extract_from_search_results(results, records_by_id)
        assert len(extraction.entity_ids) == 0
