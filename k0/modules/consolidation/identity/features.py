"""Feature extraction for reconciliation identity scoring (M9.2).

Ported from POC ``event_vs_episode_features()`` -- 11 structural features.
"""

from __future__ import annotations

import numpy as np

from k0.modules.consolidation.types import ReconciliationCandidate, TruthRecord

FEATURE_NAMES: list[str] = [
    "cosine_sim",
    "topic_overlap",
    "participant_overlap",
    "focus_match",
    "social_context_match",
    "location_match",
    "source_type_match",
    "sim_x_focus_match",
    "sim_x_participant_overlap",
    "correction_signal_any",
    "contradiction_signal_any",
]

NUM_FEATURES: int = len(FEATURE_NAMES)


def jaccard(set_a: set, set_b: set) -> float:
    """Jaccard similarity between two sets."""
    if not set_a and not set_b:
        return 0.0
    sa, sb = set(set_a), set(set_b)
    union = sa | sb
    return len(sa & sb) / len(union) if union else 0.0


def extract_features(
    candidate: ReconciliationCandidate,
    existing: TruthRecord,
    cosine_sim: float,
) -> np.ndarray:
    """Compute the 11 structural features for a (candidate, existing) pair.

    Returns a float64 array of shape ``(11,)``.  Feature order matches
    :data:`FEATURE_NAMES`.
    """
    cm = candidate.metadata
    em = existing.metadata

    topic_ovl = jaccard(cm.get("topics", set()), em.get("topics", set()))
    part_ovl = jaccard(cm.get("participants", set()), em.get("participants", set()))

    c_focal = cm.get("focal", "")
    e_focal = em.get("focal", "")
    focus = 1.0 if c_focal and c_focal == e_focal else 0.0

    c_social = cm.get("social_context", "")
    e_social = em.get("social_context", "")
    social = 1.0 if c_social and c_social == e_social else 0.0

    c_place = cm.get("place_id", "")
    e_locations = em.get("locations", set())
    loc = 1.0 if c_place and c_place in e_locations else 0.0

    c_source = cm.get("source_type", "")
    e_sources = em.get("source_types", set())
    src = 1.0 if c_source and c_source in e_sources else 0.0

    corr = float(candidate.k1_signals.correction_signal)
    contra = float(candidate.k1_signals.contradiction_signal)

    return np.array(
        [
            cosine_sim,
            topic_ovl,
            part_ovl,
            focus,
            social,
            loc,
            src,
            cosine_sim * focus,
            cosine_sim * part_ovl,
            corr,
            contra,
        ],
        dtype=np.float64,
    )
