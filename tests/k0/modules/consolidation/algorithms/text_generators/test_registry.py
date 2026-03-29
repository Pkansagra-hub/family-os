"""
Unit tests for text generators registry.

GAP Reference: GAP_001_CROSS_LAYER_VECTOR_LINKING.md §4
Milestone: GAP_001_MILESTONE_2_SUMMARY_GENERATOR.md Issue 2.10
"""

from __future__ import annotations

import pytest

from k0.modules.consolidation.algorithms.embedding_text_generator import (
    EmbeddingTextGenerator,
)
from k0.modules.consolidation.algorithms.text_generators import (
    GENERATOR_CLASS_REGISTRY,
    EpisodicTextGenerator,
    KGEntityTextGenerator,
    ProceduralTextGenerator,
    ProspectiveTextGenerator,
    SemanticTextGenerator,
    SocialTextGenerator,
    get_all_generators,
    get_generator,
    get_generator_or_none,
    register_generator,
)


class TestGeneratorRegistry:
    """Tests for generator registry functions."""

    def test_all_layers_registered(self) -> None:
        """Test that all 6 layers are registered."""
        expected_layers = {
            "st_epi",
            "st_sem",
            "st_procedural",
            "st_social",
            "st_prospective",
            "st_kg_dom",
        }
        assert set(GENERATOR_CLASS_REGISTRY.keys()) == expected_layers

    def test_get_generator_episodic(self) -> None:
        """Test getting episodic generator."""
        generator = get_generator("st_epi")
        assert isinstance(generator, EpisodicTextGenerator)
        assert generator.layer == "st_epi"

    def test_get_generator_semantic(self) -> None:
        """Test getting semantic generator."""
        generator = get_generator("st_sem")
        assert isinstance(generator, SemanticTextGenerator)
        assert generator.layer == "st_sem"

    def test_get_generator_procedural(self) -> None:
        """Test getting procedural generator."""
        generator = get_generator("st_procedural")
        assert isinstance(generator, ProceduralTextGenerator)
        assert generator.layer == "st_procedural"

    def test_get_generator_social(self) -> None:
        """Test getting social generator."""
        generator = get_generator("st_social")
        assert isinstance(generator, SocialTextGenerator)
        assert generator.layer == "st_social"

    def test_get_generator_prospective(self) -> None:
        """Test getting prospective generator."""
        generator = get_generator("st_prospective")
        assert isinstance(generator, ProspectiveTextGenerator)
        assert generator.layer == "st_prospective"

    def test_get_generator_kg_entity(self) -> None:
        """Test getting KG entity generator."""
        generator = get_generator("st_kg_dom")
        assert isinstance(generator, KGEntityTextGenerator)
        assert generator.layer == "st_kg_dom"

    def test_get_generator_singleton(self) -> None:
        """Test that generators are singletons."""
        gen1 = get_generator("st_epi")
        gen2 = get_generator("st_epi")
        assert gen1 is gen2

    def test_get_generator_unknown_layer(self) -> None:
        """Test getting generator for unknown layer raises."""
        with pytest.raises(KeyError) as exc_info:
            get_generator("st_unknown")
        assert "st_unknown" in str(exc_info.value)

    def test_get_generator_or_none_exists(self) -> None:
        """Test get_generator_or_none with existing layer."""
        generator = get_generator_or_none("st_epi")
        assert generator is not None
        assert isinstance(generator, EpisodicTextGenerator)

    def test_get_generator_or_none_missing(self) -> None:
        """Test get_generator_or_none with missing layer."""
        generator = get_generator_or_none("st_nonexistent")
        assert generator is None

    def test_get_all_generators(self) -> None:
        """Test getting all generators."""
        generators = get_all_generators()

        assert len(generators) == 6
        for layer, generator in generators.items():
            assert isinstance(generator, EmbeddingTextGenerator)
            assert generator.layer == layer

    def test_register_generator(self) -> None:
        """Test registering a custom generator."""
        from typing import Any, Dict, List, Optional

        from k0.modules.consolidation.algorithms.embedding_text_generator import (
            GeneratedText,
        )

        class CustomGenerator(EmbeddingTextGenerator):
            @property
            def layer(self) -> str:
                return "custom_layer"

            def generate(
                self,
                record_data: Dict[str, Any],
                source_texts: Optional[List[str]] = None,
            ) -> GeneratedText:
                return GeneratedText(
                    embedding_text="Custom",
                    layer=self.layer,
                    record_id=str(record_data.get("id", "")),
                )

        register_generator("custom_layer", CustomGenerator)

        generator = get_generator("custom_layer")
        assert isinstance(generator, CustomGenerator)

        # Cleanup
        del GENERATOR_CLASS_REGISTRY["custom_layer"]


class TestGeneratorIntegration:
    """Integration tests for generators."""

    def test_all_generators_produce_valid_output(self) -> None:
        """Test that all generators produce valid output."""
        test_records = {
            "st_epi": {"episode_id": "ep_1"},
            "st_sem": {"pattern_id": "pat_1", "pattern_type": "preference"},
            "st_procedural": {"routine_id": "rtn_1", "routine_name": "Test"},
            "st_social": {"relationship_id": "rel_1", "person_a_name": "A", "person_b_name": "B"},
            "st_prospective": {"intention_id": "int_1", "action": "Test action"},
            "st_kg_dom": {"entity_id": "ent_1", "entity_type": "person", "name": "Test"},
        }

        for layer, record_data in test_records.items():
            generator = get_generator(layer)
            result = generator.generate(record_data)

            assert result.embedding_text, f"{layer} should produce non-empty text"
            assert result.layer == layer
            assert result.source_texts_json == "[]"

    def test_generators_handle_source_texts(self) -> None:
        """Test that all generators handle source texts."""
        source_texts = ["Source 1", "Source 2"]

        for layer in GENERATOR_CLASS_REGISTRY:
            generator = get_generator(layer)
            result = generator.generate({}, source_texts)

            assert '["Source 1", "Source 2"]' == result.source_texts_json
