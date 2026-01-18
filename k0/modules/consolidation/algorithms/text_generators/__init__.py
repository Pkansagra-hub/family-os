"""
Text Generators Registry — GAP-001 Milestone 2

Registry and factory functions for layer-specific text generators.
Used by the embedding pipeline to generate embeddable text for each truth layer.

GAP Reference: GAP_001_CROSS_LAYER_VECTOR_LINKING.md §4
Milestone: GAP_001_MILESTONE_2_SUMMARY_GENERATOR.md Issue 2.9

Usage:
    from k0.modules.consolidation.algorithms.text_generators import (
        get_generator,
        GENERATOR_REGISTRY,
    )

    # Get generator by layer name
    generator = get_generator("st_epi")
    result = generator.generate(record_data, source_texts)

    # Or iterate all generators
    for layer, generator in GENERATOR_REGISTRY.items():
        print(f"{layer}: {generator.layer}")

TIMESTAMP CONVENTION: All timestamps use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

from typing import Dict, Optional, Type

from k0.modules.consolidation.algorithms.embedding_text_generator import (
    EmbeddingTextGenerator,
    GeneratedText,
    TextGenerationStrategy,
)
from k0.modules.consolidation.algorithms.text_generators.episodic import (
    EpisodicTextGenerator,
)
from k0.modules.consolidation.algorithms.text_generators.kg_entity import (
    KGEntityTextGenerator,
)
from k0.modules.consolidation.algorithms.text_generators.procedural import (
    ProceduralTextGenerator,
)
from k0.modules.consolidation.algorithms.text_generators.prospective import (
    ProspectiveTextGenerator,
)
from k0.modules.consolidation.algorithms.text_generators.semantic import (
    SemanticTextGenerator,
)
from k0.modules.consolidation.algorithms.text_generators.social import (
    SocialTextGenerator,
)
from k0.modules.consolidation.algorithms.text_generators.textrank import (
    narrative_arc_summarize,
    textrank_summarize,
)

# Registry mapping layer names to generator classes
GENERATOR_CLASS_REGISTRY: Dict[str, Type[EmbeddingTextGenerator]] = {
    "st_epi": EpisodicTextGenerator,
    "st_sem": SemanticTextGenerator,
    "st_procedural": ProceduralTextGenerator,
    "st_social": SocialTextGenerator,
    "st_prospective": ProspectiveTextGenerator,
    "st_kg_dom": KGEntityTextGenerator,
}

# Singleton instances for efficiency
_generator_instances: Dict[str, EmbeddingTextGenerator] = {}


def get_generator(layer: str) -> EmbeddingTextGenerator:
    """
    Get the text generator for a specific layer.

    Args:
        layer: Layer name (st_epi, st_sem, etc.)

    Returns:
        EmbeddingTextGenerator instance for the layer

    Raises:
        KeyError: If no generator exists for the layer
    """
    if layer not in _generator_instances:
        if layer not in GENERATOR_CLASS_REGISTRY:
            raise KeyError(
                f"No generator registered for layer '{layer}'. "
                f"Available layers: {list(GENERATOR_CLASS_REGISTRY.keys())}"
            )
        _generator_instances[layer] = GENERATOR_CLASS_REGISTRY[layer]()

    return _generator_instances[layer]


def get_generator_or_none(layer: str) -> Optional[EmbeddingTextGenerator]:
    """
    Get the text generator for a layer, or None if not found.

    Args:
        layer: Layer name (st_epi, st_sem, etc.)

    Returns:
        EmbeddingTextGenerator instance or None
    """
    try:
        return get_generator(layer)
    except KeyError:
        return None


def register_generator(layer: str, generator_class: Type[EmbeddingTextGenerator]) -> None:
    """
    Register a new generator class for a layer.

    Args:
        layer: Layer name
        generator_class: Generator class to register
    """
    GENERATOR_CLASS_REGISTRY[layer] = generator_class
    # Clear cached instance if exists
    if layer in _generator_instances:
        del _generator_instances[layer]


def get_all_generators() -> Dict[str, EmbeddingTextGenerator]:
    """
    Get all registered generators (instantiated).

    Returns:
        Dictionary mapping layer names to generator instances
    """
    return {layer: get_generator(layer) for layer in GENERATOR_CLASS_REGISTRY}


# Expose key types and functions
__all__ = [
    # Factory functions
    "get_generator",
    "get_generator_or_none",
    "register_generator",
    "get_all_generators",
    # Registry
    "GENERATOR_CLASS_REGISTRY",
    # Base types
    "EmbeddingTextGenerator",
    "GeneratedText",
    "TextGenerationStrategy",
    # Layer generators
    "EpisodicTextGenerator",
    "SemanticTextGenerator",
    "ProceduralTextGenerator",
    "SocialTextGenerator",
    "ProspectiveTextGenerator",
    "KGEntityTextGenerator",
    # Utilities
    "textrank_summarize",
    "narrative_arc_summarize",
]
