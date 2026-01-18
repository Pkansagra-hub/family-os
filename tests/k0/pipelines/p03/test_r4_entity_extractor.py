"""
Tests for R4 UltraBERT Entity Extractor.

Issue: 4.4.1 - Integrate UltraBERT NER entity extraction from P02
Spec Reference: M4_EXECUTION.md, Dossier Section 4.5.1

Test Coverage:
1. Label mapping (KINSHIP -> FAMILY_MEMBER, PERSON -> PERSON, etc.)
2. 3-head merging (ner_family, ner_general, temporal)
3. Nickname normalization (wifey -> wife, kiddo -> child)
4. Deduplication with priority-based selection
5. JSON serialization for st_hipp_events
6. Metrics tracking

Author: K0 Architecture Team
Date: 2025-06-10
"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from k0.modules.consolidation.algorithms.entity_extractor import (
    ExtractedEntity,
    KGEntityType,
    UltraBERTEntityExtractor,
    get_entity_extractor,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def extractor() -> UltraBERTEntityExtractor:
    """Fresh entity extractor instance."""
    return UltraBERTEntityExtractor()


@pytest.fixture
def sample_ner_family_output() -> dict:
    """Sample ner_family head output."""
    return {
        "entities": [
            {"text": "wife", "label": "KINSHIP", "start_token": 6, "end_token": 6},
            {"text": "child", "label": "KINSHIP", "start_token": 12, "end_token": 12},
            {"text": "birthday", "label": "FAMILY_EVENT", "start_token": 3, "end_token": 3},
        ]
    }


@pytest.fixture
def sample_ner_general_output() -> dict:
    """Sample ner_general head output."""
    return {
        "entities": [
            {"text": "Costco", "label": "ORG", "start_token": 7, "end_token": 7},
            {"text": "John", "label": "PERSON", "start_token": 0, "end_token": 0},
            {"text": "Seattle", "label": "GPE", "start_token": 15, "end_token": 15},
        ]
    }


@pytest.fixture
def sample_temporal_output() -> dict:
    """Sample temporal head output."""
    return {
        "entities": [
            {"text": "Sunday", "label": "DATE_REL", "start_token": 11, "end_token": 12},
            {"text": "8:00 AM", "label": "TIME", "start_token": 14, "end_token": 15},
        ]
    }


# =============================================================================
# Test: Label Mapping
# =============================================================================


class TestLabelMapping:
    """Test UltraBERT label to KG entity type mapping."""

    def test_ner_family_kinship_mapping(self, extractor: UltraBERTEntityExtractor) -> None:
        """KINSHIP label maps to FAMILY_MEMBER with priority 0.95."""
        ner_family = {
            "entities": [{"text": "mom", "label": "KINSHIP", "start_token": 0, "end_token": 0}]
        }

        entities = extractor.extract_from_ultrabert(ner_family_output=ner_family)

        assert len(entities) == 1
        assert entities[0].kg_type == KGEntityType.FAMILY_MEMBER
        assert entities[0].priority == 0.95
        assert entities[0].source_head == "ner_family"

    def test_ner_general_person_mapping(self, extractor: UltraBERTEntityExtractor) -> None:
        """PERSON label maps to PERSON with priority 0.85."""
        ner_general = {
            "entities": [{"text": "John", "label": "PERSON", "start_token": 0, "end_token": 0}]
        }

        entities = extractor.extract_from_ultrabert(ner_general_output=ner_general)

        assert len(entities) == 1
        assert entities[0].kg_type == KGEntityType.PERSON
        assert entities[0].priority == 0.85
        assert entities[0].source_head == "ner_general"

    def test_temporal_date_rel_mapping(self, extractor: UltraBERTEntityExtractor) -> None:
        """DATE_REL label maps to TEMPORAL with priority 0.90."""
        temporal = {
            "entities": [
                {"text": "yesterday", "label": "DATE_REL", "start_token": 0, "end_token": 0}
            ]
        }

        entities = extractor.extract_from_ultrabert(temporal_output=temporal)

        assert len(entities) == 1
        assert entities[0].kg_type == KGEntityType.TEMPORAL
        assert entities[0].priority == 0.90
        assert entities[0].source_head == "temporal"

    def test_temporal_time_mapping(self, extractor: UltraBERTEntityExtractor) -> None:
        """TIME label maps to TEMPORAL with priority 0.90."""
        temporal = {
            "entities": [{"text": "8:00 AM", "label": "TIME", "start_token": 0, "end_token": 0}]
        }

        entities = extractor.extract_from_ultrabert(temporal_output=temporal)

        assert len(entities) == 1
        assert entities[0].kg_type == KGEntityType.TEMPORAL
        assert entities[0].priority == 0.90

    def test_ner_general_org_mapping(self, extractor: UltraBERTEntityExtractor) -> None:
        """ORG label maps to ORGANIZATION with priority 0.80."""
        ner_general = {
            "entities": [{"text": "Costco", "label": "ORG", "start_token": 0, "end_token": 0}]
        }

        entities = extractor.extract_from_ultrabert(ner_general_output=ner_general)

        assert len(entities) == 1
        assert entities[0].kg_type == KGEntityType.ORGANIZATION
        assert entities[0].priority == 0.80

    def test_ner_general_gpe_to_location(self, extractor: UltraBERTEntityExtractor) -> None:
        """GPE label maps to LOCATION with priority 0.80."""
        ner_general = {
            "entities": [{"text": "Seattle", "label": "GPE", "start_token": 0, "end_token": 0}]
        }

        entities = extractor.extract_from_ultrabert(ner_general_output=ner_general)

        assert len(entities) == 1
        assert entities[0].kg_type == KGEntityType.LOCATION
        assert entities[0].priority == 0.80

    def test_unknown_label_defaults_concept(self, extractor: UltraBERTEntityExtractor) -> None:
        """Unknown label defaults to CONCEPT with priority 0.50."""
        ner_general = {
            "entities": [
                {"text": "xyz", "label": "UNKNOWN_LABEL", "start_token": 0, "end_token": 0}
            ]
        }

        entities = extractor.extract_from_ultrabert(ner_general_output=ner_general)

        assert len(entities) == 1
        assert entities[0].kg_type == KGEntityType.CONCEPT
        assert entities[0].priority == 0.50
        assert extractor.metrics.unknown_labels == 1

    def test_family_event_mapping(self, extractor: UltraBERTEntityExtractor) -> None:
        """FAMILY_EVENT label maps to EVENT with priority 0.90."""
        ner_family = {
            "entities": [
                {"text": "birthday", "label": "FAMILY_EVENT", "start_token": 0, "end_token": 0}
            ]
        }

        entities = extractor.extract_from_ultrabert(ner_family_output=ner_family)

        assert len(entities) == 1
        assert entities[0].kg_type == KGEntityType.EVENT
        assert entities[0].priority == 0.90


# =============================================================================
# Test: Three-Head Merging
# =============================================================================


class TestThreeHeadMerging:
    """Test merging entities from all 3 NER heads."""

    def test_merge_three_heads(
        self,
        extractor: UltraBERTEntityExtractor,
        sample_ner_family_output: dict,
        sample_ner_general_output: dict,
        sample_temporal_output: dict,
    ) -> None:
        """Entities from all 3 heads are combined correctly."""
        entities = extractor.extract_from_ultrabert(
            ner_family_output=sample_ner_family_output,
            ner_general_output=sample_ner_general_output,
            temporal_output=sample_temporal_output,
        )

        # Should have all 8 entities (3 + 3 + 2)
        assert len(entities) == 8

        # Verify entities from each head
        heads = {e.source_head for e in entities}
        assert heads == {"ner_family", "ner_general", "temporal"}

        # Verify counts by head
        by_head = extractor.metrics.entities_by_head
        assert by_head["ner_family"] == 3
        assert by_head["ner_general"] == 3
        assert by_head["temporal"] == 2

    def test_empty_heads_handled(self, extractor: UltraBERTEntityExtractor) -> None:
        """No crash on empty entity lists."""
        entities = extractor.extract_from_ultrabert(
            ner_family_output={"entities": []},
            ner_general_output={"entities": []},
            temporal_output={"entities": []},
        )

        assert entities == []
        assert extractor.metrics.entities_extracted == 0

    def test_none_heads_handled(self, extractor: UltraBERTEntityExtractor) -> None:
        """No crash on None head outputs."""
        entities = extractor.extract_from_ultrabert(
            ner_family_output=None,
            ner_general_output=None,
            temporal_output=None,
        )

        assert entities == []
        assert extractor.metrics.entities_extracted == 0

    def test_partial_heads(self, extractor: UltraBERTEntityExtractor) -> None:
        """Works with only some heads provided."""
        ner_family = {
            "entities": [{"text": "mom", "label": "KINSHIP", "start_token": 0, "end_token": 0}]
        }

        entities = extractor.extract_from_ultrabert(ner_family_output=ner_family)

        assert len(entities) == 1
        assert entities[0].kg_type == KGEntityType.FAMILY_MEMBER


# =============================================================================
# Test: Nickname Normalization
# =============================================================================


class TestNicknameNormalization:
    """Test entity name normalization with nickname handling."""

    def test_normalize_wifey_to_wife(self, extractor: UltraBERTEntityExtractor) -> None:
        """'wifey' normalizes to 'wife'."""
        ner_family = {
            "entities": [{"text": "wifey", "label": "KINSHIP", "start_token": 0, "end_token": 0}]
        }

        entities = extractor.extract_from_ultrabert(ner_family_output=ner_family)

        assert len(entities) == 1
        assert entities[0].text == "wifey"  # Original text preserved
        assert entities[0].normalized_text == "wife"

    def test_normalize_kiddo_to_child(self, extractor: UltraBERTEntityExtractor) -> None:
        """'kiddo' normalizes to 'child'."""
        ner_family = {
            "entities": [{"text": "kiddo", "label": "KINSHIP", "start_token": 0, "end_token": 0}]
        }

        entities = extractor.extract_from_ultrabert(ner_family_output=ner_family)

        assert len(entities) == 1
        assert entities[0].text == "kiddo"
        assert entities[0].normalized_text == "child"

    def test_normalize_hubby_to_husband(self, extractor: UltraBERTEntityExtractor) -> None:
        """'hubby' normalizes to 'husband'."""
        ner_family = {
            "entities": [{"text": "hubby", "label": "KINSHIP", "start_token": 0, "end_token": 0}]
        }

        entities = extractor.extract_from_ultrabert(ner_family_output=ner_family)

        assert entities[0].normalized_text == "husband"

    def test_normalize_mom_to_mother(self, extractor: UltraBERTEntityExtractor) -> None:
        """'mom' normalizes to 'mother'."""
        ner_family = {
            "entities": [{"text": "Mom", "label": "KINSHIP", "start_token": 0, "end_token": 0}]
        }

        entities = extractor.extract_from_ultrabert(ner_family_output=ner_family)

        assert entities[0].text == "Mom"  # Original case preserved
        assert entities[0].normalized_text == "mother"

    def test_normalize_removes_punctuation(self, extractor: UltraBERTEntityExtractor) -> None:
        """Punctuation is removed during normalization. Possessive 's is stripped."""
        ner_general = {
            "entities": [{"text": "John's", "label": "PERSON", "start_token": 0, "end_token": 0}]
        }

        entities = extractor.extract_from_ultrabert(ner_general_output=ner_general)

        # "John's" -> "john" (possessive 's is removed by normalize_name)
        assert entities[0].normalized_text == "john"

    def test_normalize_collapses_spaces(self, extractor: UltraBERTEntityExtractor) -> None:
        """Multiple spaces are collapsed to single space."""
        ner_general = {
            "entities": [{"text": "New   York", "label": "GPE", "start_token": 0, "end_token": 0}]
        }

        entities = extractor.extract_from_ultrabert(ner_general_output=ner_general)

        assert entities[0].normalized_text == "new york"


# =============================================================================
# Test: Deduplication
# =============================================================================


class TestDeduplication:
    """Test entity deduplication with priority-based selection."""

    def test_deduplicate_keeps_highest_priority(self, extractor: UltraBERTEntityExtractor) -> None:
        """KINSHIP beats PERSON for same text (higher priority wins)."""
        # Same person mentioned in both heads with different labels
        ner_family = {
            "entities": [{"text": "mom", "label": "KINSHIP", "start_token": 0, "end_token": 0}]
        }
        ner_general = {
            "entities": [{"text": "mom", "label": "PERSON", "start_token": 0, "end_token": 0}]
        }

        entities = extractor.extract_from_ultrabert(
            ner_family_output=ner_family,
            ner_general_output=ner_general,
        )

        # Should only have one entity (deduplicated)
        assert len(entities) == 1
        # Should be FAMILY_MEMBER (KINSHIP has priority 0.95 > PERSON 0.85)
        assert entities[0].kg_type == KGEntityType.FAMILY_MEMBER
        assert entities[0].priority == 0.95

    def test_deduplicate_by_normalized_text(self, extractor: UltraBERTEntityExtractor) -> None:
        """Deduplication uses normalized text (case-insensitive)."""
        ner_general = {
            "entities": [
                {"text": "JOHN", "label": "PERSON", "start_token": 0, "end_token": 0},
                {"text": "John", "label": "PERSON", "start_token": 5, "end_token": 5},
            ]
        }

        entities = extractor.extract_from_ultrabert(ner_general_output=ner_general)

        # Should only have one entity (same normalized text "john")
        assert len(entities) == 1

    def test_same_text_different_types_deduplicated(
        self, extractor: UltraBERTEntityExtractor
    ) -> None:
        """Same text IS deduplicated across types - highest priority wins."""
        # Same "test" text labeled differently by different heads
        ner_family = {
            "entities": [
                {"text": "test", "label": "FAMILY_EVENT", "start_token": 0, "end_token": 0}
            ]
        }
        ner_general = {
            "entities": [{"text": "test", "label": "ORG", "start_token": 0, "end_token": 0}]
        }

        entities = extractor.extract_from_ultrabert(
            ner_family_output=ner_family,
            ner_general_output=ner_general,
        )

        # Should have 1 entity (deduplicated by normalized text)
        # FAMILY_EVENT has priority 0.90 > ORG 0.80, so EVENT wins
        assert len(entities) == 1
        assert entities[0].kg_type == KGEntityType.EVENT
        assert entities[0].priority == 0.90

    def test_metrics_track_duplicates_removed(self, extractor: UltraBERTEntityExtractor) -> None:
        """Metrics track number of duplicates removed."""
        ner_family = {
            "entities": [{"text": "mom", "label": "KINSHIP", "start_token": 0, "end_token": 0}]
        }
        ner_general = {
            "entities": [{"text": "mom", "label": "PERSON", "start_token": 0, "end_token": 0}]
        }

        extractor.extract_from_ultrabert(
            ner_family_output=ner_family,
            ner_general_output=ner_general,
        )

        assert extractor.metrics.duplicates_removed == 1


# =============================================================================
# Test: JSON Serialization
# =============================================================================


class TestJsonSerialization:
    """Test JSON output for st_hipp_events.entities_json."""

    def test_to_entities_json_format(self, extractor: UltraBERTEntityExtractor) -> None:
        """Valid JSON with all fields."""
        ner_family = {
            "entities": [{"text": "mom", "label": "KINSHIP", "start_token": 0, "end_token": 0}]
        }

        entities = extractor.extract_from_ultrabert(ner_family_output=ner_family)
        json_str = extractor.to_entities_json(entities)

        # Should be valid JSON
        parsed = json.loads(json_str)

        # Check structure
        assert "entities" in parsed
        assert "extraction_version" in parsed
        assert parsed["extraction_version"] == "2.0"
        assert parsed["extractor"] == "UltraBERTEntityExtractor"

        # Check entity fields
        assert len(parsed["entities"]) == 1
        entity = parsed["entities"][0]
        assert entity["text"] == "mom"
        assert entity["kg_type"] == "FAMILY_MEMBER"
        assert entity["normalized"] == "mother"
        assert entity["source_label"] == "KINSHIP"
        assert entity["source_head"] == "ner_family"
        assert entity["priority"] == 0.95

    def test_to_entities_json_empty(self, extractor: UltraBERTEntityExtractor) -> None:
        """Empty entity list produces valid JSON."""
        json_str = extractor.to_entities_json([])

        parsed = json.loads(json_str)
        assert parsed["entities"] == []


# =============================================================================
# Test: Metrics Tracking
# =============================================================================


class TestMetricsTracking:
    """Test entity extraction metrics."""

    def test_metrics_by_source_head(self, extractor: UltraBERTEntityExtractor) -> None:
        """Metrics labeled by source head."""
        ner_family = {
            "entities": [{"text": "mom", "label": "KINSHIP", "start_token": 0, "end_token": 0}]
        }
        ner_general = {
            "entities": [
                {"text": "John", "label": "PERSON", "start_token": 0, "end_token": 0},
                {"text": "Costco", "label": "ORG", "start_token": 0, "end_token": 0},
            ]
        }

        extractor.extract_from_ultrabert(
            ner_family_output=ner_family,
            ner_general_output=ner_general,
        )

        assert extractor.metrics.entities_by_head["ner_family"] == 1
        assert extractor.metrics.entities_by_head["ner_general"] == 2

    def test_metrics_by_kg_type(self, extractor: UltraBERTEntityExtractor) -> None:
        """Metrics track entity counts by KG type."""
        ner_family = {
            "entities": [
                {"text": "mom", "label": "KINSHIP", "start_token": 0, "end_token": 0},
                {"text": "dad", "label": "KINSHIP", "start_token": 0, "end_token": 0},
            ]
        }
        ner_general = {
            "entities": [{"text": "Costco", "label": "ORG", "start_token": 0, "end_token": 0}]
        }

        extractor.extract_from_ultrabert(
            ner_family_output=ner_family,
            ner_general_output=ner_general,
        )

        assert extractor.metrics.entities_by_type["FAMILY_MEMBER"] == 2
        assert extractor.metrics.entities_by_type["ORGANIZATION"] == 1

    def test_metrics_reset(self, extractor: UltraBERTEntityExtractor) -> None:
        """Metrics can be reset."""
        ner_family = {
            "entities": [{"text": "mom", "label": "KINSHIP", "start_token": 0, "end_token": 0}]
        }
        extractor.extract_from_ultrabert(ner_family_output=ner_family)

        assert extractor.metrics.entities_extracted == 1

        extractor.reset_metrics()

        assert extractor.metrics.entities_extracted == 0
        assert extractor.metrics.entities_by_head == {}

    def test_processing_time_tracked(self, extractor: UltraBERTEntityExtractor) -> None:
        """Processing time is tracked in metrics."""
        ner_family = {
            "entities": [{"text": "mom", "label": "KINSHIP", "start_token": 0, "end_token": 0}]
        }

        extractor.extract_from_ultrabert(ner_family_output=ner_family)

        assert extractor.metrics.processing_time_ms >= 0


# =============================================================================
# Test: Database Integration
# =============================================================================


class TestDatabaseIntegration:
    """Test database update functionality."""

    @pytest.mark.asyncio
    async def test_process_event_updates_db(self, extractor: UltraBERTEntityExtractor) -> None:
        """st_hipp_events.entities_json is updated."""
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()

        ultrabert_result = {
            "ner_family": {
                "entities": [{"text": "mom", "label": "KINSHIP", "start_token": 0, "end_token": 0}]
            },
            "ner_general": {"entities": []},
            "temporal": {"entities": []},
        }

        count = await extractor.process_event(
            event_id="test-event-123",
            ultrabert_result=ultrabert_result,
            db_conn=mock_conn,
        )

        assert count == 1
        mock_conn.execute.assert_called_once()

        # Check the SQL
        call_args = mock_conn.execute.call_args
        sql = call_args[0][0]
        assert "UPDATE st_hipp_events" in sql
        assert "entities_json" in sql


# =============================================================================
# Test: Factory Function
# =============================================================================


class TestFactoryFunction:
    """Test get_entity_extractor factory."""

    def test_get_entity_extractor_returns_instance(self) -> None:
        """get_entity_extractor returns fresh instance."""
        extractor = get_entity_extractor()
        assert isinstance(extractor, UltraBERTEntityExtractor)

    def test_get_entity_extractor_returns_new_instance(self) -> None:
        """Each call returns a new instance."""
        extractor1 = get_entity_extractor()
        extractor2 = get_entity_extractor()
        assert extractor1 is not extractor2


# =============================================================================
# Test: ExtractedEntity Dataclass
# =============================================================================


class TestExtractedEntityDataclass:
    """Test ExtractedEntity dataclass methods."""

    def test_to_dict(self) -> None:
        """to_dict produces correct dictionary."""
        entity = ExtractedEntity(
            text="mom",
            kg_type=KGEntityType.FAMILY_MEMBER,
            normalized_text="mother",
            source_label="KINSHIP",
            source_head="ner_family",
            priority=0.95,
            start_token=0,
            end_token=0,
        )

        d = entity.to_dict()

        assert d["text"] == "mom"
        assert d["kg_type"] == "FAMILY_MEMBER"
        assert d["normalized"] == "mother"
        assert d["source_label"] == "KINSHIP"
        assert d["source_head"] == "ner_family"
        assert d["priority"] == 0.95
        assert d["start_token"] == 0
        assert d["end_token"] == 0


# =============================================================================
# Test: Full Result Extraction
# =============================================================================


class TestFullResultExtraction:
    """Test extraction from full UltraBERT result."""

    def test_extract_from_full_result_dict_style(self, extractor: UltraBERTEntityExtractor) -> None:
        """Works with dict-style full result."""
        full_result = {
            "ner_family": {
                "entities": [{"text": "mom", "label": "KINSHIP", "start_token": 0, "end_token": 0}]
            },
            "ner_general": {
                "entities": [{"text": "Costco", "label": "ORG", "start_token": 0, "end_token": 0}]
            },
            "temporal": {
                "entities": [
                    {"text": "yesterday", "label": "DATE_REL", "start_token": 0, "end_token": 0}
                ]
            },
        }

        entities = extractor.extract_from_full_result(full_result)

        assert len(entities) == 3
        types = {e.kg_type for e in entities}
        assert types == {
            KGEntityType.FAMILY_MEMBER,
            KGEntityType.ORGANIZATION,
            KGEntityType.TEMPORAL,
        }

    def test_extract_from_full_result_object_style(
        self, extractor: UltraBERTEntityExtractor
    ) -> None:
        """Works with object-style full result (ClientResult)."""
        # Mock ClientResult-like object
        mock_result = MagicMock()
        mock_result.entities = [
            {"text": "mom", "label": "KINSHIP", "start_token": 0, "end_token": 0}
        ]
        mock_result.general_entities = [
            {"text": "Costco", "label": "ORG", "start_token": 0, "end_token": 0}
        ]
        mock_result.temporal = [
            {"text": "yesterday", "label": "DATE_REL", "start_token": 0, "end_token": 0}
        ]

        entities = extractor.extract_from_full_result(mock_result)

        assert len(entities) == 3


# =============================================================================
# Test: M10.2 - Universal Garbage Word Filtering
# =============================================================================


class TestUniversalGarbageFiltering:
    """M10.2: GARBAGE_ENTITY_WORDS must be filtered from ALL heads/labels."""

    def test_garbage_words_filtered_from_ner_general(
        self, extractor: UltraBERTEntityExtractor
    ) -> None:
        """Garbage words from ner_general are filtered (previously unfiltered)."""
        ner_general = {
            "entities": [
                # "the" is in GARBAGE_ENTITY_WORDS - should be filtered
                {"text": "the", "label": "PERSON", "start_token": 0, "end_token": 1},
                # "Microsoft" is valid - should pass
                {"text": "Microsoft", "label": "ORG", "start_token": 2, "end_token": 3},
                # "is" is in GARBAGE_ENTITY_WORDS - should be filtered
                {"text": "is", "label": "MISC", "start_token": 4, "end_token": 5},
            ]
        }

        entities = extractor.extract_from_ultrabert(ner_general_output=ner_general)

        assert len(entities) == 1
        assert entities[0].text == "Microsoft"

    def test_garbage_words_filtered_from_temporal(
        self, extractor: UltraBERTEntityExtractor
    ) -> None:
        """Garbage words from temporal head are filtered (previously unfiltered)."""
        temporal = {
            "entities": [
                # "was" is in GARBAGE_ENTITY_WORDS - should be filtered
                {"text": "was", "label": "DATE", "start_token": 0, "end_token": 1},
                # "yesterday" is valid - should pass
                {"text": "yesterday", "label": "DATE_REL", "start_token": 2, "end_token": 3},
                # "the" is in GARBAGE_ENTITY_WORDS - should be filtered
                {"text": "the", "label": "TIME", "start_token": 4, "end_token": 5},
            ]
        }

        entities = extractor.extract_from_ultrabert(temporal_output=temporal)

        assert len(entities) == 1
        assert entities[0].text == "yesterday"

    def test_garbage_words_filtered_from_trusted_ner_family(
        self, extractor: UltraBERTEntityExtractor
    ) -> None:
        """Garbage words from TRUSTED ner_family labels are now filtered."""
        ner_family = {
            "entities": [
                # "mom" is valid KINSHIP - should pass
                {"text": "mom", "label": "KINSHIP", "start_token": 0, "end_token": 1},
                # "the" even with KINSHIP label should be filtered (edge case)
                {"text": "the", "label": "KINSHIP", "start_token": 2, "end_token": 3},
                # "home" is valid HOME_LOC - should pass
                {"text": "home", "label": "HOME_LOC", "start_token": 4, "end_token": 5},
            ]
        }

        entities = extractor.extract_from_ultrabert(ner_family_output=ner_family)

        # "the" should be filtered, "mom" and "home" should pass
        assert len(entities) == 2
        texts = {e.text for e in entities}
        assert texts == {"mom", "home"}

    def test_common_verbs_filtered_universally(self, extractor: UltraBERTEntityExtractor) -> None:
        """Common verbs in GARBAGE_ENTITY_WORDS filtered from all heads."""
        # Test verbs that were previously slipping through ner_general
        ner_general = {
            "entities": [
                {"text": "met", "label": "PERSON", "start_token": 0, "end_token": 1},
                {"text": "fixed", "label": "EVENT", "start_token": 2, "end_token": 3},
                {"text": "deployed", "label": "MISC", "start_token": 4, "end_token": 5},
                {"text": "John", "label": "PERSON", "start_token": 6, "end_token": 7},
            ]
        }

        entities = extractor.extract_from_ultrabert(ner_general_output=ner_general)

        # Only "John" should pass
        assert len(entities) == 1
        assert entities[0].text == "John"
