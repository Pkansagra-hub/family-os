"""World generator for R5 Dream Phase benchmark packs.

This module constructs deterministic "worlds" (episodes, entities, edges,
actions, goals, fragments, schemas, and contexts) per scenario pack.
"""

from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .r5_embeddings import get_embedding_service

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# World dataclass - complete benchmark world for all algorithms
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class World:
    """Complete benchmark world for all R5 algorithms."""

    pack_name: str
    seed: int

    # CPN inputs
    episodes: List[Any]
    kg_edges: List[Any]  # CAUSES edges

    # BGT-SM inputs
    entities: List[Any]
    semantic_edges: List[Any]  # Non-causal edges
    embeddings: Dict[str, List[float]]

    # MCTS inputs
    initial_state: Dict[str, Any]
    actions: List[Any]
    goals: List[Any]
    constraints: Optional[Dict[str, Any]] = None

    # SPC-UQ inputs
    incomplete_episodes: Optional[List[Any]] = None
    fragments: Optional[List[Any]] = None
    schemas: Optional[List[Dict[str, Any]]] = None
    context: Optional[Dict[str, Any]] = None

    # Metadata / coverage expectations
    expected_properties: Dict[str, Any] = field(default_factory=dict)
    difficulty: str = "easy"

    def summary(self) -> Dict[str, Any]:
        """Return a summary of world contents for logging."""
        return {
            "pack_name": self.pack_name,
            "seed": self.seed,
            "difficulty": self.difficulty,
            "episodes": len(self.episodes),
            "kg_edges": len(self.kg_edges),
            "entities": len(self.entities),
            "semantic_edges": len(self.semantic_edges),
            "actions": len(self.actions),
            "goals": len(self.goals),
            "fragments": len(self.fragments) if self.fragments else 0,
            "schemas": len(self.schemas) if self.schemas else 0,
            "embedding_dim": len(next(iter(self.embeddings.values()), [])),
        }


# ─────────────────────────────────────────────────────────────────────────────
# Pack registry - maps pack names to builder functions
# ─────────────────────────────────────────────────────────────────────────────

# Type alias for pack builder functions
PackBuilder = Callable[[int, bool], World]

# Registry populated dynamically from packs submodule
_PACK_REGISTRY: Dict[str, PackBuilder] = {}


def register_pack(name: str, builder: PackBuilder) -> None:
    """Register a pack builder function.

    Args:
        name: Pack identifier (e.g., "toy", "causal_deep").
        builder: Function(seed, use_ultrabert) -> World.
    """
    _PACK_REGISTRY[name] = builder


def list_packs() -> List[str]:
    """Return list of registered pack names."""
    _ensure_packs_loaded()
    return list(_PACK_REGISTRY.keys())


def _ensure_packs_loaded() -> None:
    """Lazy-load pack modules to populate registry."""
    if _PACK_REGISTRY:
        return  # Already loaded

    pack_names = [
        "toy",
        "causal_deep",
        "causal_fork_join",
        "mcts_delayed",
        "mcts_constrained",
        "bgt_clustered",
        "bgt_adversarial",
        "spc_multi_prov",
        "spc_conflict",
        "mixed_stress",
        "real_world",
    ]

    for name in pack_names:
        try:
            module = importlib.import_module(
                f".packs.{name}",
                package="tests.k0.modules.consolidation.benchmarks",
            )
            if hasattr(module, "build_world"):
                _PACK_REGISTRY[name] = module.build_world
        except ImportError as e:
            logger.debug(f"Pack {name} not available: {e}")
        except Exception as e:
            logger.warning(f"Failed to load pack {name}: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Main factory function
# ─────────────────────────────────────────────────────────────────────────────


def make_world(
    pack: str,
    seed: int = 42,
    use_ultrabert: bool | None = None,
) -> World:
    """Build a World for a given pack name.

    Args:
        pack: Pack identifier (e.g., "toy", "causal_deep").
        seed: Random seed for deterministic generation.
        use_ultrabert: If True, use UltraBERT embeddings (768-dim).
                       If False, use clustered embeddings (64-dim).
                       If None, auto-detect availability.

    Returns:
        Populated World instance.

    Raises:
        ValueError: If pack is not registered.
    """
    _ensure_packs_loaded()

    if pack not in _PACK_REGISTRY:
        available = ", ".join(sorted(_PACK_REGISTRY.keys())) or "(none)"
        raise ValueError(f"Unknown pack: {pack}. Available: {available}")

    builder = _PACK_REGISTRY[pack]

    # Build the world
    world = builder(seed, use_ultrabert)

    logger.info(f"Built world: {world.summary()}")
    return world


def make_world_with_embeddings(
    pack: str,
    seed: int = 42,
    use_ultrabert: bool | None = None,
) -> World:
    """Build a World and ensure embeddings are populated.

    This is a convenience wrapper that generates embeddings if the pack
    builder didn't provide them.

    Args:
        pack: Pack identifier.
        seed: Random seed.
        use_ultrabert: Embedding mode selection.

    Returns:
        World with guaranteed embeddings dict.
    """
    world = make_world(pack, seed, use_ultrabert)

    # Generate embeddings if missing
    if not world.embeddings and world.entities:
        embedding_service = get_embedding_service(use_ultrabert)
        world.embeddings = embedding_service.embed_entities(world.entities)

    return world
