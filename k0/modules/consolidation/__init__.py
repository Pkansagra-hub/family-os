"""
Consolidation Module — Domain logic for memory consolidation (P03).

This module contains reusable cognitive algorithms and data structures
for memory consolidation. It is imported by pipelines/p03 for orchestration.

Structure:
    algorithms/     — Core algorithms (DBSCAN, decay, dedup, etc.)
    event_state.py  — Per-event state model (future migration from pipelines)
    phase_outputs.py — Phase output models (future migration from pipelines)

Design Philosophy:
    - Modules contain cognition and domain logic
    - Pipelines contain orchestration and execution control
    - Modules have zero knowledge of runners, offsets, or phases

Spec Reference:
    - Dossier §4 (R1-R4 algorithms)
    - ADR: k010.X-consolidation-module-split (pending)
"""

# Imports will be enabled as algorithms are implemented:
#
# from k0.modules.consolidation.algorithms import (
#     # R2 Episodic Clustering (Epic 4.2)
#     CompositeDistance,     # 4.2.1
#     EpisodeSplitter,       # 4.2.2
#     EpisodicHDBSCAN,      # 4.2.3
#     CentroidCalculator,    # 4.2.4
#     EpsAdjuster,           # 4.2.5
#     MinSamplesAdjuster,    # 4.2.6
#     ClusterQualityTracker, # 4.2.7
#
#     # R3 Dedup + Decay (Epic 4.3)
#     SimHasher,             # 4.3.1
#     TwoStageDeduplicator,  # 4.3.2
#     UnifiedDecayEngine,    # 4.3.3
#     RetentionEnforcer,     # 4.3.4
# )

__all__ = [
    # Uncomment as algorithms are implemented
    # "CompositeDistance",
    # "EpisodeSplitter",
    # "EpisodicHDBSCAN",
    # "CentroidCalculator",
    # "EpsAdjuster",
    # "MinSamplesAdjuster",
    # "ClusterQualityTracker",
    # "SimHasher",
    # "TwoStageDeduplicator",
    # "UnifiedDecayEngine",
    # "RetentionEnforcer",
]
