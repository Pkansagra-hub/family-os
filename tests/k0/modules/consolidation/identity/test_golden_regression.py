"""Golden set regression test for EpisodicIdentity (M9.2 -- D12).

Validates V5 and V9 exit gates using pre-computed feature vectors
from the POC golden annotation set (300 pairs).

The feature vectors were extracted by running the POC
``golden_pair_features()`` function against ``life_events_enriched.jsonl``
and stored in ``golden_features.npz`` (X: 300x11, y: 300 labels).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from k0.modules.consolidation.identity.episodic import EpisodicIdentity

WEIGHTS_DIR = (
    Path(__file__).parents[5] / "k0" / "modules" / "consolidation" / "identity" / "weights"
)


@pytest.fixture(scope="module")
def scorer() -> EpisodicIdentity:
    return EpisodicIdentity()


@pytest.fixture(scope="module")
def golden_data() -> tuple[np.ndarray, np.ndarray]:
    npz = np.load(str(WEIGHTS_DIR / "golden_features.npz"))
    return npz["X"], npz["y"]


# ---------------------------------------------------------------------------
# V5: Golden set regression -- macro F1 >= 0.72
# ---------------------------------------------------------------------------


class TestGoldenRegression:
    def test_golden_set_size(self, golden_data: tuple[np.ndarray, np.ndarray]):
        X, y = golden_data
        assert X.shape == (300, 11)
        assert y.shape == (300,)

    def test_macro_f1_at_least_072(
        self,
        scorer: EpisodicIdentity,
        golden_data: tuple[np.ndarray, np.ndarray],
    ):
        """V5: macro F1 >= 0.72 on 300 golden pairs."""
        X, y = golden_data
        labels = ["CREATE", "EXTEND", "REINFORCE"]

        predictions = []
        for features in X:
            _, best_action = scorer._predict(features)
            predictions.append(best_action)

        predictions = np.array(predictions)

        # Compute per-class F1 and macro-average
        f1s = []
        for label in labels:
            tp = int(np.sum((predictions == label) & (y == label)))
            fp = int(np.sum((predictions == label) & (y != label)))
            fn = int(np.sum((predictions != label) & (y == label)))
            precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
            f1s.append(f1)

        macro_f1 = sum(f1s) / len(f1s)
        assert macro_f1 >= 0.72, f"Macro F1 = {macro_f1:.4f} < 0.72"

    def test_accuracy_at_least_079(
        self,
        scorer: EpisodicIdentity,
        golden_data: tuple[np.ndarray, np.ndarray],
    ):
        X, y = golden_data
        predictions = np.array([scorer._predict(f)[1] for f in X])
        accuracy = float(np.mean(predictions == y))
        assert accuracy >= 0.79, f"Accuracy = {accuracy:.4f} < 0.79"


# ---------------------------------------------------------------------------
# V9: Threshold 0.35 episode count regression
# ---------------------------------------------------------------------------


class TestThresholdRegression:
    def test_threshold_value(self, scorer: EpisodicIdentity):
        """Optimal threshold from frozen weights is 0.35."""
        assert scorer._threshold == pytest.approx(0.35)

    def test_p_assign_distribution(
        self,
        scorer: EpisodicIdentity,
        golden_data: tuple[np.ndarray, np.ndarray],
    ):
        """p_assign values span a useful range (not degenerate)."""
        X, _ = golden_data
        scores = []
        for features in X:
            proba, _ = scorer._predict(features)
            scores.append(proba["EXTEND"] + proba["REINFORCE"])

        scores = np.array(scores)
        assert scores.min() < 0.35
        assert scores.max() > 0.35
        # At least 10% of pairs are below threshold (-> CREATE)
        create_frac = float(np.mean(scores < 0.35))
        assert create_frac > 0.10, f"Only {create_frac:.2%} below threshold"


# ---------------------------------------------------------------------------
# Model weight consistency
# ---------------------------------------------------------------------------


class TestWeightConsistency:
    def test_softmax_sums_to_one_for_all_golden_pairs(
        self,
        scorer: EpisodicIdentity,
        golden_data: tuple[np.ndarray, np.ndarray],
    ):
        """V4 extended: softmax sums to 1.0 for all 300 golden pairs."""
        X, _ = golden_data
        for features in X:
            proba, _ = scorer._predict(features)
            total = sum(proba.values())
            assert total == pytest.approx(1.0, abs=1e-6)

    def test_predictions_deterministic(
        self,
        scorer: EpisodicIdentity,
        golden_data: tuple[np.ndarray, np.ndarray],
    ):
        """Same inputs produce same outputs."""
        X, _ = golden_data
        run1 = [scorer._predict(f)[1] for f in X]
        run2 = [scorer._predict(f)[1] for f in X]
        assert run1 == run2
