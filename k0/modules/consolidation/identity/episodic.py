"""EpisodicIdentity -- 11-feature logistic scorer for st_epi (M9.2).

Implements :class:`IdentityStrategy` for the episodic truth layer.
Uses a frozen 3-way multinomial logistic regression model
(CREATE / EXTEND / REINFORCE) trained on 300 golden pairs from the
POC reconciliation engine experiments.

Runtime inference uses numpy only -- no sklearn dependency.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from k0.modules.consolidation.identity.features import FEATURE_NAMES, NUM_FEATURES, extract_features
from k0.modules.consolidation.types import IdentityResult, ReconciliationCandidate, TruthRecord

_DEFAULT_WEIGHTS = Path(__file__).parent / "weights" / "episodic_v1.json"


class EpisodicIdentity:
    """Identity strategy for st_epi (episodic memory).

    Uses an 11-feature logistic regression scorer trained on 300 golden
    pairs from the POC (EXP-0 through EXP-11).  The model is a 3-way
    multinomial classifier (CREATE / EXTEND / REINFORCE) with frozen
    weights.

    Pipeline:
      1. ``match_key()`` returns ``None`` (episodes have no key-match path).
      2. ``score_identity()`` computes 11 features -> logistic model -> probabilities.
      3. ``p_assign = P(EXTEND) + P(REINFORCE)`` is the identity score.
    """

    layer_name: str = "st_epi"

    def __init__(self, weights_path: Path | None = None) -> None:
        path = weights_path or _DEFAULT_WEIGHTS
        with open(path) as fh:
            data = json.load(fh)

        self._classes: list[str] = data["classes"]
        self._coef = np.array(data["coefficients"], dtype=np.float64)  # (3, 11)
        self._intercept = np.array(data["intercepts"], dtype=np.float64)  # (3,)
        self._threshold: float = data.get("optimal_threshold", 0.35)

        if self._coef.shape != (len(self._classes), NUM_FEATURES):
            raise ValueError(
                f"Weight matrix shape {self._coef.shape} does not match "
                f"({len(self._classes)}, {NUM_FEATURES})"
            )

    # -- IdentityStrategy protocol -----------------------------------------

    def score_identity(
        self,
        candidate: ReconciliationCandidate,
        existing: TruthRecord,
        cosine_sim: float,
    ) -> IdentityResult:
        features = extract_features(candidate, existing, cosine_sim)
        proba, best_action = self._predict(features)

        score = proba["EXTEND"] + proba["REINFORCE"]

        return IdentityResult(
            score=score,
            p_create=proba["CREATE"],
            p_extend=proba["EXTEND"],
            p_reinforce=proba["REINFORCE"],
            recommended_action=best_action,
            features=dict(zip(FEATURE_NAMES, features.tolist())),
        )

    def match_key(
        self,
        candidate: ReconciliationCandidate,
        existing: TruthRecord,
    ) -> bool | None:
        return None

    # -- internals ----------------------------------------------------------

    def _predict(self, features: np.ndarray) -> tuple[dict[str, float], str]:
        logits = features @ self._coef.T + self._intercept  # (3,)
        exp_logits = np.exp(logits - logits.max())
        proba = exp_logits / exp_logits.sum()

        prob_dict = {cls: float(p) for cls, p in zip(self._classes, proba)}
        best_action = self._classes[int(np.argmax(proba))]
        return prob_dict, best_action
