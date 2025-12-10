"""
Unit tests for TransformerNER module.

Tests cover:
1. Entity extraction with various tier configurations
2. Family term detection
3. Fallback behavior when transformer unavailable
4. Coreference resolution
5. Confidence thresholds
6. Performance characteristics

Issue: 2.1.1 - Upgrade NER to Transformer Model
"""

from unittest.mock import MagicMock, patch

import pytest

# Import the module under test
from k0.modules.hippocampus.transformer_ner import (
    FAMILY_TERMS,
    POSSESSIVE_FAMILY_PATTERN,
    Entity,
    TransformerNER,
    extract_entities_sync,
)

# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def transformer_ner():
    """Create a TransformerNER instance without initialization."""
    return TransformerNER(
        model_name="dslim/bert-base-NER",
        use_coref=False,
        confidence_threshold=0.6,
        enable_family_detection=True,
        device="cpu",
    )


@pytest.fixture
def initialized_ner_with_mock():
    """Create TransformerNER with mocked pipeline."""
    ner = TransformerNER(
        model_name="dslim/bert-base-NER",
        use_coref=False,
        confidence_threshold=0.6,
        enable_family_detection=True,
        device="cpu",
    )
    # Mock the pipeline to return sample entities
    ner._ner_pipeline = MagicMock()
    ner._ner_pipeline.return_value = [
        {"entity_group": "PER", "word": "Sarah", "score": 0.95, "start": 17, "end": 22},
        {"entity_group": "ORG", "word": "Olive Garden", "score": 0.92, "start": 26, "end": 38},
    ]
    ner._initialized = True
    return ner


# ============================================================================
# Entity Dataclass Tests
# ============================================================================


class TestEntityDataclass:
    """Tests for Entity dataclass."""

    def test_entity_creation(self):
        """Test basic entity creation."""
        entity = Entity(
            text="Sarah",
            label="PERSON",
            confidence=0.95,
            start=0,
            end=5,
            source="transformer",
        )
        assert entity.text == "Sarah"
        assert entity.label == "PERSON"
        assert entity.confidence == 0.95
        assert entity.start == 0
        assert entity.end == 5
        assert entity.source == "transformer"
        assert entity.canonical_id is None
        assert entity.coreference_cluster is None

    def test_entity_with_canonical_id(self):
        """Test entity with canonical ID."""
        entity = Entity(
            text="mom",
            label="PERSON",
            confidence=0.9,
            canonical_id="person_mom",
        )
        assert entity.canonical_id == "person_mom"

    def test_entity_with_coref(self):
        """Test entity with coreference cluster."""
        entity = Entity(
            text="she",
            label="PERSON",
            confidence=0.8,
            coreference_cluster=1,
        )
        assert entity.coreference_cluster == 1


# ============================================================================
# Family Term Detection Tests
# ============================================================================


class TestFamilyTermDetection:
    """Tests for family term detection."""

    def test_family_terms_list(self):
        """Test that common family terms are in the list."""
        assert "mom" in FAMILY_TERMS
        assert "dad" in FAMILY_TERMS
        assert "grandma" in FAMILY_TERMS
        assert "hubby" in FAMILY_TERMS
        assert "kiddo" in FAMILY_TERMS

    def test_possessive_pattern(self):
        """Test possessive family pattern matching."""
        text = "I went to lunch with my mom and my dad"
        matches = list(POSSESSIVE_FAMILY_PATTERN.finditer(text))
        assert len(matches) == 2
        assert matches[0].group() == "my mom"
        assert matches[1].group() == "my dad"

    def test_detect_family_terms_basic(self, transformer_ner):
        """Test basic family term detection."""
        text = "Had dinner with mom at the restaurant"
        entities = transformer_ner._detect_family_terms(text)

        assert len(entities) >= 1
        mom_entity = next((e for e in entities if e.text.lower() == "mom"), None)
        assert mom_entity is not None
        # Family terms now use FAMILY label instead of PERSON
        assert mom_entity.label == "FAMILY"
        assert mom_entity.source == "rule"

    def test_detect_multiple_family_terms(self, transformer_ner):
        """Test detecting multiple family terms."""
        text = "Dinner with mom, dad, and grandma"
        entities = transformer_ner._detect_family_terms(text)

        terms_found = {e.text.lower() for e in entities}
        assert "mom" in terms_found
        assert "dad" in terms_found
        assert "grandma" in terms_found

    def test_detect_informal_names(self, transformer_ner):
        """Test detecting informal family names."""
        text = "Hubby and kiddo went to the park"
        entities = transformer_ner._detect_family_terms(text)

        terms_found = {e.text.lower() for e in entities}
        assert "hubby" in terms_found
        assert "kiddo" in terms_found

    def test_word_boundary_detection(self, transformer_ner):
        """Test that partial matches are not detected."""
        text = "Dadaism is an art movement"  # "Dad" is part of "Dadaism"
        entities = transformer_ner._detect_family_terms(text)

        # Should not detect "dad" inside "Dadaism"
        dad_entities = [e for e in entities if e.text.lower() == "dad"]
        assert len(dad_entities) == 0


# ============================================================================
# Transformer NER Extraction Tests
# ============================================================================


class TestTransformerNERExtraction:
    """Tests for transformer NER extraction."""

    def test_extract_empty_text(self, transformer_ner):
        """Test extraction on empty text."""
        result = transformer_ner.extract("")
        assert len(result.entities) == 0
        assert result.processing_time_ms >= 0

    def test_extract_whitespace_text(self, transformer_ner):
        """Test extraction on whitespace-only text."""
        result = transformer_ner.extract("   \n\t  ")
        assert len(result.entities) == 0

    def test_extract_with_mock_pipeline(self, initialized_ner_with_mock):
        """Test extraction with mocked transformer pipeline."""
        text = "Had dinner with Sarah at Olive Garden"
        result = initialized_ner_with_mock.extract(text)

        assert len(result.entities) >= 2
        assert result.model_used == "transformer"
        assert not result.fallback_used

        # Check entity extraction
        entity_texts = {e.text for e in result.entities}
        assert "Sarah" in entity_texts
        assert "Olive Garden" in entity_texts

    def test_extract_with_family_enhancement(self, initialized_ner_with_mock):
        """Test that family terms are added to transformer results."""
        text = "Had dinner with mom at Olive Garden"

        # Mock pipeline returns only Olive Garden
        initialized_ner_with_mock._ner_pipeline.return_value = [
            {"entity_group": "ORG", "word": "Olive Garden", "score": 0.92, "start": 21, "end": 33},
        ]

        result = initialized_ner_with_mock.extract(text)

        # Should have both transformer result and family term
        entity_texts = {e.text.lower() for e in result.entities}
        assert "mom" in entity_texts
        assert "olive garden" in entity_texts

    def test_confidence_threshold_filtering(self, initialized_ner_with_mock):
        """Test that low confidence entities are filtered."""
        # Mock returns low confidence entity
        initialized_ner_with_mock._ner_pipeline.return_value = [
            {"entity_group": "PER", "word": "John", "score": 0.3, "start": 0, "end": 4},
        ]

        result = initialized_ner_with_mock.extract("John went home", confidence_threshold=0.6)

        # Low confidence entity should be filtered
        john_entities = [e for e in result.entities if e.text == "John"]
        assert len(john_entities) == 0

    def test_label_mapping(self, initialized_ner_with_mock):
        """Test that BERT labels are mapped correctly."""
        initialized_ner_with_mock._ner_pipeline.return_value = [
            {"entity_group": "PER", "word": "Sarah", "score": 0.9, "start": 0, "end": 5},
            {"entity_group": "LOC", "word": "New York", "score": 0.88, "start": 15, "end": 23},
        ]

        result = initialized_ner_with_mock.extract("Sarah lives in New York")

        sarah = next((e for e in result.entities if e.text == "Sarah"), None)
        ny = next((e for e in result.entities if e.text == "New York"), None)

        assert sarah is not None
        assert sarah.label == "PERSON"  # PER -> PERSON
        assert ny is not None
        # LOC is now preserved (not converted to GPE) per OntoNotes standard
        assert ny.label == "LOC"


# ============================================================================
# Fallback Behavior Tests
# ============================================================================


class TestFallbackBehavior:
    """Tests for fallback when transformer is unavailable."""

    def test_fallback_to_spacy(self, transformer_ner):
        """Test fallback to spaCy when transformer fails."""
        # Ensure transformer not initialized, but spaCy is
        transformer_ner._ner_pipeline = None
        transformer_ner._initialized = True

        # Mock spaCy
        mock_doc = MagicMock()
        mock_ent = MagicMock()
        mock_ent.text = "Sarah"
        mock_ent.label_ = "PERSON"
        mock_ent.start_char = 0
        mock_ent.end_char = 5
        mock_doc.ents = [mock_ent]

        transformer_ner._spacy_nlp = MagicMock(return_value=mock_doc)

        result = transformer_ner.extract("Sarah went home")

        assert result.fallback_used
        assert result.model_used == "spacy"

    def test_rule_only_when_no_models(self, transformer_ner):
        """Test rule-based extraction when no models available."""
        transformer_ner._ner_pipeline = None
        transformer_ner._spacy_nlp = None
        transformer_ner._initialized = True

        result = transformer_ner.extract("Had dinner with mom")

        assert result.model_used == "rule"
        assert result.fallback_used

        # Should still detect family terms
        mom = next((e for e in result.entities if e.text.lower() == "mom"), None)
        assert mom is not None


# ============================================================================
# Entity Deduplication Tests
# ============================================================================


class TestEntityDeduplication:
    """Tests for entity deduplication."""

    def test_deduplicate_same_position(self, transformer_ner):
        """Test that entities at same position are deduplicated."""
        entities = [
            Entity(text="Sarah", label="PERSON", confidence=0.8, start=0, end=5),
            Entity(text="Sarah", label="PERSON", confidence=0.9, start=0, end=5),
        ]

        result = transformer_ner._deduplicate_entities(entities)

        assert len(result) == 1
        assert result[0].confidence == 0.9  # Higher confidence kept

    def test_merge_non_overlapping(self, transformer_ner):
        """Test merging non-overlapping entity lists."""
        primary = [
            Entity(text="Sarah", label="PERSON", confidence=0.9, start=0, end=5),
        ]
        secondary = [
            Entity(text="mom", label="PERSON", confidence=0.85, start=20, end=23),
        ]

        result = transformer_ner._merge_entities(primary, secondary)

        assert len(result) == 2

    def test_merge_overlapping_skipped(self, transformer_ner):
        """Test that overlapping secondary entities are skipped."""
        primary = [
            Entity(text="my mom", label="PERSON", confidence=0.9, start=10, end=16),
        ]
        secondary = [
            Entity(text="mom", label="PERSON", confidence=0.85, start=13, end=16),
        ]

        result = transformer_ner._merge_entities(primary, secondary)

        assert len(result) == 1
        assert result[0].text == "my mom"


# ============================================================================
# Coreference Resolution Tests
# ============================================================================


class TestCoreferenceResolution:
    """Tests for coreference resolution."""

    def test_simple_pronoun_resolution(self, transformer_ner):
        """Test simple pronoun to entity linking."""
        text = "Sarah went to the store. She bought groceries."
        entities = [
            Entity(text="Sarah", label="PERSON", confidence=0.9, start=0, end=5),
        ]

        clusters = transformer_ner._resolve_coreferences(text, entities)

        assert len(clusters) >= 1
        assert clusters[0].canonical_mention == "Sarah"
        assert len(clusters[0].mentions) == 2  # Sarah and she

    def test_no_coref_without_person(self, transformer_ner):
        """Test that coref returns empty when no PERSON entities."""
        text = "The company released earnings. They were positive."
        entities = [
            Entity(text="The company", label="ORG", confidence=0.9, start=0, end=11),
        ]

        clusters = transformer_ner._resolve_coreferences(text, entities)

        # No PERSON entities, so no pronoun resolution
        assert len(clusters) == 0


# ============================================================================
# Statistics Tests
# ============================================================================


class TestNERStatistics:
    """Tests for NER statistics tracking."""

    def test_stats_initial(self, transformer_ner):
        """Test initial statistics."""
        stats = transformer_ner.get_stats()

        assert stats["extraction_count"] == 0
        assert stats["fallback_count"] == 0
        assert stats["avg_latency_ms"] == 0.0
        assert stats["initialized"] is False

    def test_stats_after_extraction(self, initialized_ner_with_mock):
        """Test statistics after extraction."""
        initialized_ner_with_mock.extract("Test text with Sarah")

        stats = initialized_ner_with_mock.get_stats()

        assert stats["extraction_count"] == 1
        assert stats["avg_latency_ms"] > 0


# ============================================================================
# Sync Extraction Tests
# ============================================================================


class TestSyncExtraction:
    """Tests for synchronous extraction function."""

    def test_sync_extraction_empty(self):
        """Test sync extraction with empty text."""
        entities = extract_entities_sync("")
        assert len(entities) == 0

    @patch("k0.modules.hippocampus.transformer_ner._transformer_ner", None)
    def test_sync_extraction_without_initialized_ner(self):
        """Test sync extraction falls back to spaCy."""
        # This will try spaCy fallback
        with patch("spacy.load") as mock_load:
            mock_doc = MagicMock()
            mock_ent = MagicMock()
            mock_ent.text = "Test"
            mock_ent.label_ = "PERSON"
            mock_ent.start_char = 0
            mock_ent.end_char = 4
            mock_doc.ents = [mock_ent]

            mock_nlp = MagicMock(return_value=mock_doc)
            mock_load.return_value = mock_nlp

            entities = extract_entities_sync("Test person")

            # Should have called spaCy
            mock_load.assert_called()


# ============================================================================
# Edge Cases
# ============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_special_characters(self, initialized_ner_with_mock):
        """Test extraction with special characters."""
        initialized_ner_with_mock._ner_pipeline.return_value = []

        result = initialized_ner_with_mock.extract("@#$%^& mom !!!")

        # Should still detect family term
        mom = next((e for e in result.entities if e.text.lower() == "mom"), None)
        assert mom is not None

    def test_very_long_text(self, initialized_ner_with_mock):
        """Test extraction on very long text."""
        long_text = "Sarah and " * 500 + "mom"
        initialized_ner_with_mock._ner_pipeline.return_value = [
            {"entity_group": "PER", "word": "Sarah", "score": 0.9, "start": 0, "end": 5},
        ]

        result = initialized_ner_with_mock.extract(long_text)

        assert result.processing_time_ms > 0
        assert len(result.entities) > 0

    def test_unicode_text(self, initialized_ner_with_mock):
        """Test extraction with unicode characters."""
        initialized_ner_with_mock._ner_pipeline.return_value = [
            {"entity_group": "PER", "word": "Mama", "score": 0.9, "start": 15, "end": 19},
        ]

        result = initialized_ner_with_mock.extract("Dinner with mamá at home")

        assert len(result.entities) >= 1

    def test_case_insensitive_family_terms(self, transformer_ner):
        """Test that family terms are detected case-insensitively."""
        texts = ["Had dinner with MOM", "Had dinner with Mom", "Had dinner with mom"]

        for text in texts:
            entities = transformer_ner._detect_family_terms(text)
            mom = next((e for e in entities if e.text.lower() == "mom"), None)
            assert mom is not None, f"Failed to detect mom in: {text}"


# ============================================================================
# Model Tier Tests
# ============================================================================


class TestModelTiers:
    """Tests for different NER model tiers."""

    def test_bert_base_tier_creation(self):
        """Test creating NER with BERT_BASE tier."""
        from k0.modules.hippocampus.transformer_ner import NERModelTier, TransformerNER

        ner = TransformerNER(model_tier=NERModelTier.BERT_BASE)
        assert ner.model_name == "dslim/bert-base-NER"

    def test_ontonotes_tier_creation(self):
        """Test creating NER with ONTONOTES_FAST tier."""
        from k0.modules.hippocampus.transformer_ner import NERModelTier, TransformerNER

        ner = TransformerNER(model_tier=NERModelTier.ONTONOTES_FAST)
        assert ner.model_name == "flair/ner-english-ontonotes-fast"

    def test_distilbert_tier_creation(self):
        """Test creating NER with DISTILBERT tier."""
        from k0.modules.hippocampus.transformer_ner import NERModelTier, TransformerNER

        ner = TransformerNER(model_tier=NERModelTier.DISTILBERT)
        assert ner.model_name == "dslim/distilbert-NER"

    def test_model_name_overrides_tier(self):
        """Test that explicit model_name overrides model_tier."""
        from k0.modules.hippocampus.transformer_ner import NERModelTier, TransformerNER

        ner = TransformerNER(
            model_name="custom/model",
            model_tier=NERModelTier.BERT_BASE,
        )
        assert ner.model_name == "custom/model"


# ============================================================================
# Integration with semantic_project Tests
# ============================================================================


class TestSemanticProjectIntegration:
    """Tests for integration with semantic_project module."""

    @pytest.mark.asyncio
    async def test_get_transformer_ner_singleton(self):
        """Test that get_transformer_ner returns singleton."""
        from k0.modules.hippocampus.transformer_ner import get_transformer_ner

        # Note: This test may fail if transformers not installed
        # In that case, it will fall back to spaCy
        try:
            ner1 = await get_transformer_ner(device="cpu")
            ner2 = await get_transformer_ner(device="cpu")
            assert ner1 is ner2
        except ImportError:
            pytest.skip("transformers not installed")
