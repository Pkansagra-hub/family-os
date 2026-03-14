"""
Tests for Hebbian -> Importance Reinforcement Cycle -- Epic 5.F.2

5.F.2.1: End-to-end cycle simulation test
    Simulates 5 P03 cycles: R1 scoring -> R4 Hebbian -> write edges
    -> next cycle R1 reads edges -> verify boost increases.
    AC: Monotonic increase in edge weights AND importance scores
    for consistently co-occurring entity pairs.

5.F.2.2: Convergence analysis
    Verifies the reinforcement cycle converges to a stable equilibrium.
    Soft saturation in Hebbian prevents runaway; boost cap in R1
    prevents inflation. Simulation shows convergence within N cycles.

References:
    - ADR-K026: KG Relationship Boost for R1 Importance Scoring
    - HebbianLearner: soft saturation formula
    - Plan: PLAN_HEBBIAN_WEIGHT_LEARNER_INTEGRATION.md Epic 5.F.2
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from k0.modules.consolidation.algorithms.hebbian_learner import HebbianConfig, HebbianLearner
from k0.modules.consolidation.algorithms.importance_scorer import (
    ImportanceScorer,
    ImportanceWeights,
)
from k0.modules.consolidation.algorithms.kg_relationship_boost import (
    EdgeWeightVelocityMonitor,
    KGBoostConfig,
    KGEdgeCache,
    RunawayDetectionConfig,
    _make_pair_key,
    emergency_weight_reset,
    selective_weight_reset,
)

# =============================================================================
# Mock Event for Cycle Simulation
# =============================================================================


@dataclass
class CycleEvent:
    """Event for cycle simulation. Mirrors ImportanceScorer's field requirements."""

    event_id: str = "evt_cycle"
    sentiment_score: float = 0.5
    affect_valence: float = 0.4
    affect_arousal: float = 0.3
    surprise_level: float = 0.3
    novelty: str = "NOVEL"
    salience_score: float = 0.0
    num_participants: int = 2
    social_intimacy: str = "HIGH"
    identity_relevance: float = 0.5
    identity_domains_json: str = "[]"
    timestamp: int = 0
    content_type: str = "message"
    activity_type_ultrabert: str = ""
    intent_label: str = ""
    intent_ultrabert: str = ""
    elaboration_depth: str = ""
    narrative_is_goal_event: bool = False
    narrative_arc_position: str = ""
    temporal_orientation: str = ""
    source_reliability: float = 1.0
    source_type: str = ""
    memory_tier: str = "routine"
    ner_entities_json: str = "[]"
    importance_score: float = 0.0
    importance_computed: bool = False

    def set_importance(
        self,
        score: float,
        recency: float,
        affect: float,
        social: float,
        novelty: float,
        surprise: float = 0.0,
        identity: float = 0.0,
    ) -> None:
        self.importance_score = score
        self.importance_computed = True


# =============================================================================
# Helpers
# =============================================================================


def _build_edge_cache(entity_a: str, entity_b: str, weight: float) -> KGEdgeCache:
    """Build an edge cache with a single edge."""
    cache = KGEdgeCache()
    cache._loaded = True
    key = _make_pair_key(entity_a, entity_b)
    cache._edges = {key: weight}
    cache._edge_count = 1
    return cache


def _run_cycle(
    entity_a: str,
    entity_b: str,
    current_edge_weight: float,
    current_cooccurrence_count: int,
    event: CycleEvent,
    kg_boost_config: KGBoostConfig,
    weights: ImportanceWeights,
    hebbian_learner: HebbianLearner,
    now_ms: int,
) -> tuple[float, float, int]:
    """
    Run one complete R1 -> R4 cycle.

    Returns:
        (importance_score, new_edge_weight, new_cooccurrence_count)
    """
    # Step 1: R1 scores event with current edge weight
    cache = _build_edge_cache(entity_a, entity_b, current_edge_weight)
    scorer = ImportanceScorer(
        space_id="sp_cycle",
        kg_boost_config=kg_boost_config,
        kg_edge_cache=cache,
    )
    importance, breakdown = scorer.compute_importance_score(event, weights, now_ms)

    # Step 2: R4 Hebbian updates edge weight based on importance
    new_weight, new_count = hebbian_learner.update_edge_weight(
        current_weight=current_edge_weight,
        current_count=current_cooccurrence_count,
        event_importance=importance,
    )

    return importance, new_weight, new_count


# =============================================================================
# 5.F.2.1: End-to-End Cycle Simulation
# =============================================================================


class TestReinforcementCycleE2E:
    """
    End-to-end reinforcement cycle simulation.

    AC: Monotonic increase in edge weights AND importance scores
    for consistently co-occurring entity pairs over 5 cycles.
    """

    def test_five_cycles_monotonic_increase(self) -> None:
        """
        5 cycles of R1 -> R4 produce monotonically increasing
        edge weights and importance scores for Mom-Dad entity pair.
        """
        entity_a = "Mom"
        entity_b = "Dad"
        initial_weight = 0.3
        now_ms = int(time.time() * 1000)

        config = KGBoostConfig(enabled=True, boost_scale=0.15, max_boost_cap=0.20)
        weights = ImportanceWeights()
        learner = HebbianLearner(HebbianConfig(learning_rate=0.1))

        event = CycleEvent(
            timestamp=now_ms - 3600_000,
            ner_entities_json='[{"entity_id": "Mom"}, {"entity_id": "Dad"}]',
        )

        edge_weight = initial_weight
        cooccurrence_count = 5
        prev_importance = 0.0
        prev_weight = 0.0

        importance_history: list[float] = []
        weight_history: list[float] = [initial_weight]

        for cycle in range(5):
            importance, edge_weight, cooccurrence_count = _run_cycle(
                entity_a,
                entity_b,
                edge_weight,
                cooccurrence_count,
                event,
                config,
                weights,
                learner,
                now_ms,
            )
            importance_history.append(importance)
            weight_history.append(edge_weight)

            # After first cycle, verify monotonic increase
            if cycle > 0:
                assert (
                    importance >= prev_importance
                ), f"Cycle {cycle}: importance {importance} < prev {prev_importance}"
                assert (
                    edge_weight >= prev_weight
                ), f"Cycle {cycle}: weight {edge_weight} < prev {prev_weight}"

            prev_importance = importance
            prev_weight = edge_weight

        # Final weight should be greater than initial
        assert (
            weight_history[-1] > weight_history[0]
        ), f"Final weight {weight_history[-1]} not > initial {weight_history[0]}"
        # Verify we had actual growth
        assert len(importance_history) == 5

    def test_unrelated_entities_no_boost_growth(self) -> None:
        """
        Entity pair NOT in the event gets no boost growth.
        Edge weight only changes via Hebbian from event importance,
        not via R1 boost (since the entities are not mentioned).
        """
        entity_a = "Mom"
        entity_b = "Dad"
        now_ms = int(time.time() * 1000)

        config = KGBoostConfig(enabled=True, boost_scale=0.15)
        weights = ImportanceWeights()

        # Event mentions DIFFERENT entities
        event = CycleEvent(
            timestamp=now_ms - 3600_000,
            ner_entities_json='[{"entity_id": "Alice"}, {"entity_id": "Bob"}]',
        )

        # But we track Mom-Dad edge in the cache
        cache = _build_edge_cache(entity_a, entity_b, 0.5)
        scorer = ImportanceScorer(
            space_id="sp_cycle",
            kg_boost_config=config,
            kg_edge_cache=cache,
        )
        _, breakdown = scorer.compute_importance_score(event, weights, now_ms)

        # Mom-Dad edge should NOT boost Alice-Bob event
        assert breakdown.relationship_boost == 1.0
        assert breakdown.max_edge_weight == 0.0

    def test_cycle_with_multiple_entity_pairs(self) -> None:
        """
        Events with 3 entities (6 pairs) correctly use max edge weight.
        """
        now_ms = int(time.time() * 1000)
        config = KGBoostConfig(enabled=True, boost_scale=0.15)
        weights = ImportanceWeights()

        event = CycleEvent(
            timestamp=now_ms - 3600_000,
            ner_entities_json='[{"entity_id": "Mom"}, {"entity_id": "Dad"}, {"entity_id": "Home"}]',
        )

        # Mom-Dad strong, others weak
        cache = KGEdgeCache()
        cache._loaded = True
        cache._edges = {
            _make_pair_key("Mom", "Dad"): 0.9,
            _make_pair_key("Mom", "Home"): 0.2,
            _make_pair_key("Dad", "Home"): 0.1,
        }
        cache._edge_count = 3

        scorer = ImportanceScorer(
            space_id="sp_cycle",
            kg_boost_config=config,
            kg_edge_cache=cache,
        )
        _, breakdown = scorer.compute_importance_score(event, weights, now_ms)

        # Should use max edge weight (0.9 from Mom-Dad)
        assert breakdown.max_edge_weight == 0.9
        expected_boost = 1.0 + 0.15 * 0.9  # 1.135
        assert abs(breakdown.relationship_boost - expected_boost) < 0.001

    def test_boost_disabled_no_reinforcement_difference(self) -> None:
        """
        With boost disabled, edge weight still grows from Hebbian
        but importance scores don't increase across cycles.
        """
        entity_a = "Mom"
        entity_b = "Dad"
        now_ms = int(time.time() * 1000)

        # Disabled boost
        config = KGBoostConfig(enabled=False)
        weights = ImportanceWeights()
        learner = HebbianLearner(HebbianConfig(learning_rate=0.1))

        event = CycleEvent(
            timestamp=now_ms - 3600_000,
            ner_entities_json='[{"entity_id": "Mom"}, {"entity_id": "Dad"}]',
        )

        importance_scores: list[float] = []
        edge_weight = 0.3
        count = 5

        for _ in range(5):
            cache = _build_edge_cache(entity_a, entity_b, edge_weight)
            scorer = ImportanceScorer(
                space_id="sp_cycle",
                kg_boost_config=config,
                kg_edge_cache=cache,
            )
            importance, breakdown = scorer.compute_importance_score(event, weights, now_ms)
            assert breakdown.relationship_boost == 1.0  # Always 1.0 when disabled

            # Hebbian still updates
            edge_weight, count = learner.update_edge_weight(edge_weight, count, importance)
            importance_scores.append(importance)

        # All importance scores should be identical (no boost feedback)
        for i in range(1, len(importance_scores)):
            assert abs(importance_scores[i] - importance_scores[0]) < 0.0001


# =============================================================================
# 5.F.2.2: Convergence Analysis
# =============================================================================


class TestConvergenceAnalysis:
    """
    Verify the reinforcement cycle converges to stable equilibrium.

    Mathematical basis:
        Hebbian delta = learning_rate * (max_weight - current_weight) * importance
        As weight -> max_weight, delta -> 0 (soft saturation)
        R1 boost is capped: relationship_boost <= 1.0 + max_boost_cap
        Therefore the system has bounded output and converging input.

    Simulation: Run 100 cycles and verify weight stabilizes.
    """

    def test_convergence_within_100_cycles(self) -> None:
        """
        Edge weight converges to stable value within 100 cycles.
        Convergence = weight delta < 0.001 for 10 consecutive cycles.
        """
        entity_a = "Mom"
        entity_b = "Dad"
        now_ms = int(time.time() * 1000)

        config = KGBoostConfig(enabled=True, boost_scale=0.15, max_boost_cap=0.20)
        weights = ImportanceWeights()
        learner = HebbianLearner(HebbianConfig(learning_rate=0.1, max_weight=1.0))

        event = CycleEvent(
            timestamp=now_ms - 3600_000,
            ner_entities_json='[{"entity_id": "Mom"}, {"entity_id": "Dad"}]',
        )

        edge_weight = 0.1  # Start low
        count = 1
        converged_count = 0
        convergence_threshold = 0.001

        for cycle in range(100):
            old_weight = edge_weight
            importance, edge_weight, count = _run_cycle(
                entity_a,
                entity_b,
                edge_weight,
                count,
                event,
                config,
                weights,
                learner,
                now_ms,
            )

            delta = abs(edge_weight - old_weight)
            if delta < convergence_threshold:
                converged_count += 1
            else:
                converged_count = 0

            if converged_count >= 10:
                break

        assert converged_count >= 10, (
            f"Failed to converge within 100 cycles. "
            f"Last delta={delta:.6f}, converged_count={converged_count}"
        )
        # Weight should be well below max
        assert edge_weight < 1.0

    def test_weight_bounded_by_max(self) -> None:
        """Edge weight never exceeds max_weight regardless of cycles."""
        entity_a = "A"
        entity_b = "B"
        now_ms = int(time.time() * 1000)

        config = KGBoostConfig(enabled=True, boost_scale=0.50, max_boost_cap=0.50)
        weights = ImportanceWeights()
        learner = HebbianLearner(HebbianConfig(learning_rate=0.3, max_weight=1.0))

        event = CycleEvent(
            timestamp=now_ms - 3600_000,
            ner_entities_json='[{"entity_id": "A"}, {"entity_id": "B"}]',
            sentiment_score=1.0,
            affect_valence=1.0,
            affect_arousal=1.0,
            surprise_level=1.0,
            novelty="SURPRISING",
            identity_relevance=1.0,
            memory_tier="landmark",
        )

        edge_weight = 0.5
        count = 100

        for _ in range(200):
            importance, edge_weight, count = _run_cycle(
                entity_a,
                entity_b,
                edge_weight,
                count,
                event,
                config,
                weights,
                learner,
                now_ms,
            )
            assert edge_weight <= 1.0, f"Weight exceeded max: {edge_weight}"

    def test_soft_saturation_slows_growth(self) -> None:
        """
        Hebbian soft saturation: growth rate decreases as weight approaches max.
        Delta at weight=0.3 should be larger than delta at weight=0.8.
        """
        learner = HebbianLearner(HebbianConfig(learning_rate=0.1, max_weight=1.0))
        importance = 0.7

        # Delta at low weight
        new_low, _ = learner.update_edge_weight(0.3, 10, importance)
        delta_low = new_low - 0.3

        # Delta at high weight
        new_high, _ = learner.update_edge_weight(0.8, 10, importance)
        delta_high = new_high - 0.8

        assert (
            delta_low > delta_high
        ), f"Saturation broken: delta_low={delta_low:.4f} <= delta_high={delta_high:.4f}"

    def test_boost_cap_limits_importance_inflation(self) -> None:
        """
        Boost cap prevents importance from inflating beyond bounded range.
        Even with weight=1.0, boost cannot exceed 1.0 + max_boost_cap.
        """
        now_ms = int(time.time() * 1000)
        config = KGBoostConfig(enabled=True, boost_scale=0.15, max_boost_cap=0.20)
        weights = ImportanceWeights()

        event = CycleEvent(
            timestamp=now_ms - 3600_000,
            ner_entities_json='[{"entity_id": "X"}, {"entity_id": "Y"}]',
        )

        # Score with maximum possible edge weight
        cache = _build_edge_cache("X", "Y", 1.0)
        scorer = ImportanceScorer(
            space_id="sp_cycle",
            kg_boost_config=config,
            kg_edge_cache=cache,
        )
        _, breakdown = scorer.compute_importance_score(event, weights, now_ms)

        # Boost capped at 1.15 (scale 0.15 * weight 1.0 = 0.15 < cap 0.20)
        assert breakdown.relationship_boost <= 1.0 + config.max_boost_cap

    def test_equilibrium_is_stable(self) -> None:
        """
        After convergence, adding more cycles does not change weight.
        """
        entity_a = "Mom"
        entity_b = "Dad"
        now_ms = int(time.time() * 1000)

        config = KGBoostConfig(enabled=True, boost_scale=0.15, max_boost_cap=0.20)
        weights = ImportanceWeights()
        learner = HebbianLearner(HebbianConfig(learning_rate=0.1))

        event = CycleEvent(
            timestamp=now_ms - 3600_000,
            ner_entities_json='[{"entity_id": "Mom"}, {"entity_id": "Dad"}]',
        )

        # Run until converged
        edge_weight = 0.1
        count = 1
        for _ in range(100):
            _, edge_weight, count = _run_cycle(
                entity_a,
                entity_b,
                edge_weight,
                count,
                event,
                config,
                weights,
                learner,
                now_ms,
            )

        equilibrium_weight = edge_weight

        # Run 20 more cycles
        for _ in range(20):
            _, edge_weight, count = _run_cycle(
                entity_a,
                entity_b,
                edge_weight,
                count,
                event,
                config,
                weights,
                learner,
                now_ms,
            )

        # Weight should be essentially unchanged (tolerance accounts for
        # very slow asymptotic approach near max_weight)
        assert (
            abs(edge_weight - equilibrium_weight) < 0.005
        ), f"Equilibrium unstable: {equilibrium_weight:.6f} -> {edge_weight:.6f}"

    def test_different_initial_weights_converge_same(self) -> None:
        """
        Starting from different initial weights converges to same equilibrium.
        This proves the equilibrium is an attractor.
        """
        now_ms = int(time.time() * 1000)
        config = KGBoostConfig(enabled=True, boost_scale=0.15, max_boost_cap=0.20)
        weights = ImportanceWeights()
        learner = HebbianLearner(HebbianConfig(learning_rate=0.1))

        event = CycleEvent(
            timestamp=now_ms - 3600_000,
            ner_entities_json='[{"entity_id": "A"}, {"entity_id": "B"}]',
        )

        final_weights = []
        for initial in [0.05, 0.3, 0.6, 0.9]:
            edge_weight = initial
            count = 1
            for _ in range(100):
                _, edge_weight, count = _run_cycle(
                    "A",
                    "B",
                    edge_weight,
                    count,
                    event,
                    config,
                    weights,
                    learner,
                    now_ms,
                )
            final_weights.append(edge_weight)

        # All should converge to approximately the same value
        for w in final_weights:
            assert (
                abs(w - final_weights[0]) < 0.01
            ), f"Different initial weights diverge: {final_weights}"


# =============================================================================
# 5.F.2.3: Runaway Detection
# =============================================================================


class TestRunawayDetection:
    """
    Verify edge weight velocity monitoring detects runaway reinforcement.

    AC: Metric emitted; alert threshold configurable.
    """

    def test_no_alert_normal_growth(self) -> None:
        """Normal Hebbian growth does not trigger alert."""
        monitor = EdgeWeightVelocityMonitor(
            RunawayDetectionConfig(velocity_threshold=0.1),
        )

        # Cycle 1: initial state
        cache1 = KGEdgeCache()
        cache1._loaded = True
        cache1._edges = {_make_pair_key("Mom", "Dad"): 0.50}
        cache1._edge_count = 1
        alerts = monitor.record_cycle(cache1, cycle_number=1)
        assert alerts == []

        # Cycle 2: small increase (0.04 < 0.1 threshold)
        cache2 = KGEdgeCache()
        cache2._loaded = True
        cache2._edges = {_make_pair_key("Mom", "Dad"): 0.54}
        cache2._edge_count = 1
        alerts = monitor.record_cycle(cache2, cycle_number=2)
        assert alerts == []
        assert monitor.total_alerts == 0

    def test_alert_on_large_velocity(self) -> None:
        """Large weight jump triggers alert."""
        monitor = EdgeWeightVelocityMonitor(
            RunawayDetectionConfig(velocity_threshold=0.1),
        )

        pair_key = _make_pair_key("Mom", "Dad")

        # Cycle 1
        cache1 = KGEdgeCache()
        cache1._loaded = True
        cache1._edges = {pair_key: 0.30}
        cache1._edge_count = 1
        monitor.record_cycle(cache1, cycle_number=1)

        # Cycle 2: jump of 0.25 > threshold 0.1
        cache2 = KGEdgeCache()
        cache2._loaded = True
        cache2._edges = {pair_key: 0.55}
        cache2._edge_count = 1
        alerts = monitor.record_cycle(cache2, cycle_number=2)

        assert len(alerts) == 1
        assert alerts[0].pair_key == pair_key
        assert abs(alerts[0].delta - 0.25) < 0.001
        assert alerts[0].cycle_number == 2
        assert monitor.total_alerts == 1

    def test_configurable_threshold(self) -> None:
        """Different threshold values work correctly."""
        # Strict threshold: 0.02
        monitor = EdgeWeightVelocityMonitor(
            RunawayDetectionConfig(velocity_threshold=0.02),
        )

        pair_key = _make_pair_key("A", "B")
        cache1 = KGEdgeCache()
        cache1._loaded = True
        cache1._edges = {pair_key: 0.50}
        cache1._edge_count = 1
        monitor.record_cycle(cache1, cycle_number=1)

        cache2 = KGEdgeCache()
        cache2._loaded = True
        cache2._edges = {pair_key: 0.53}  # delta 0.03 > 0.02
        cache2._edge_count = 1
        alerts = monitor.record_cycle(cache2, cycle_number=2)

        assert len(alerts) == 1

    def test_disabled_no_alerts(self) -> None:
        """Disabled monitor emits no alerts."""
        monitor = EdgeWeightVelocityMonitor(
            RunawayDetectionConfig(enabled=False),
        )

        pair_key = _make_pair_key("X", "Y")
        cache1 = KGEdgeCache()
        cache1._loaded = True
        cache1._edges = {pair_key: 0.1}
        cache1._edge_count = 1
        monitor.record_cycle(cache1, 1)

        cache2 = KGEdgeCache()
        cache2._loaded = True
        cache2._edges = {pair_key: 0.9}  # Huge jump
        cache2._edge_count = 1
        alerts = monitor.record_cycle(cache2, 2)

        assert alerts == []

    def test_get_velocity(self) -> None:
        """get_velocity returns latest delta for a pair."""
        monitor = EdgeWeightVelocityMonitor()
        pair_key = _make_pair_key("A", "B")

        cache1 = KGEdgeCache()
        cache1._loaded = True
        cache1._edges = {pair_key: 0.40}
        cache1._edge_count = 1
        monitor.record_cycle(cache1, 1)

        assert monitor.get_velocity(pair_key) is None  # Only 1 snapshot

        cache2 = KGEdgeCache()
        cache2._loaded = True
        cache2._edges = {pair_key: 0.45}
        cache2._edge_count = 1
        monitor.record_cycle(cache2, 2)

        velocity = monitor.get_velocity(pair_key)
        assert velocity is not None
        assert abs(velocity - 0.05) < 0.001

    def test_multiple_pairs_independent(self) -> None:
        """Alerts are independent per entity pair."""
        monitor = EdgeWeightVelocityMonitor(
            RunawayDetectionConfig(velocity_threshold=0.1),
        )

        key_ab = _make_pair_key("A", "B")
        key_cd = _make_pair_key("C", "D")

        # Cycle 1
        cache1 = KGEdgeCache()
        cache1._loaded = True
        cache1._edges = {key_ab: 0.30, key_cd: 0.50}
        cache1._edge_count = 2
        monitor.record_cycle(cache1, 1)

        # Cycle 2: A-B normal, C-D runaway
        cache2 = KGEdgeCache()
        cache2._loaded = True
        cache2._edges = {key_ab: 0.34, key_cd: 0.75}  # C-D +0.25
        cache2._edge_count = 2
        alerts = monitor.record_cycle(cache2, 2)

        assert len(alerts) == 1
        assert alerts[0].pair_key == key_cd

    def test_window_size_limits_history(self) -> None:
        """History is trimmed to window_size."""
        monitor = EdgeWeightVelocityMonitor(
            RunawayDetectionConfig(window_size=3),
        )
        pair_key = _make_pair_key("A", "B")

        for i in range(10):
            cache = KGEdgeCache()
            cache._loaded = True
            cache._edges = {pair_key: 0.1 + i * 0.01}
            cache._edge_count = 1
            monitor.record_cycle(cache, i + 1)

        # History should be trimmed to 3 entries
        assert len(monitor._history[pair_key]) == 3


# =============================================================================
# 5.F.2.4: Emergency Brake (Weight Reset)
# =============================================================================


class TestEmergencyBrake:
    """
    Verify emergency weight reset capability.

    AC: Reset mechanism works; tested.
    """

    def test_full_reset_all_edges(self) -> None:
        """emergency_weight_reset resets all edges to given value."""
        cache = KGEdgeCache()
        cache._loaded = True
        cache._edges = {
            _make_pair_key("Mom", "Dad"): 0.9,
            _make_pair_key("Mom", "Home"): 0.7,
            _make_pair_key("Dad", "Home"): 0.5,
        }
        cache._edge_count = 3

        result = emergency_weight_reset(cache, reset_value=0.1, reason="test_reset")

        assert result.edges_reset == 3
        assert result.reset_to == 0.1
        assert result.reason == "test_reset"
        # All previous weights captured
        assert len(result.previous_weights) == 3
        assert result.previous_weights[_make_pair_key("Mom", "Dad")] == 0.9

        # All edges now at 0.1
        for w in cache._edges.values():
            assert w == 0.1

    def test_full_reset_empty_cache(self) -> None:
        """Reset on empty cache is a no-op."""
        cache = KGEdgeCache()
        cache._loaded = True
        result = emergency_weight_reset(cache)
        assert result.edges_reset == 0

    def test_selective_reset_specific_pairs(self) -> None:
        """selective_weight_reset only resets specified pairs."""
        cache = KGEdgeCache()
        cache._loaded = True
        key_md = _make_pair_key("Mom", "Dad")
        key_mh = _make_pair_key("Mom", "Home")
        cache._edges = {key_md: 0.9, key_mh: 0.7}
        cache._edge_count = 2

        result = selective_weight_reset(cache, [key_md], reset_value=0.1)

        assert result.edges_reset == 1
        assert cache._edges[key_md] == 0.1  # Reset
        assert cache._edges[key_mh] == 0.7  # Unchanged

    def test_selective_reset_nonexistent_pair(self) -> None:
        """Resetting a pair not in cache is harmless."""
        cache = KGEdgeCache()
        cache._loaded = True
        cache._edges = {_make_pair_key("A", "B"): 0.5}
        cache._edge_count = 1

        result = selective_weight_reset(cache, [_make_pair_key("X", "Y")])
        assert result.edges_reset == 0
        assert cache._edges[_make_pair_key("A", "B")] == 0.5  # Untouched

    def test_reset_after_runaway_detection(self) -> None:
        """Full workflow: detect runaway -> selective reset -> verify."""
        monitor = EdgeWeightVelocityMonitor(
            RunawayDetectionConfig(velocity_threshold=0.1),
        )

        key = _make_pair_key("Mom", "Dad")
        key2 = _make_pair_key("A", "B")

        # Cycle 1
        cache1 = KGEdgeCache()
        cache1._loaded = True
        cache1._edges = {key: 0.30, key2: 0.40}
        cache1._edge_count = 2
        monitor.record_cycle(cache1, 1)

        # Cycle 2: runaway on Mom-Dad
        cache2 = KGEdgeCache()
        cache2._loaded = True
        cache2._edges = {key: 0.60, key2: 0.42}  # Mom-Dad +0.30
        cache2._edge_count = 2
        alerts = monitor.record_cycle(cache2, 2)

        assert len(alerts) == 1
        assert alerts[0].pair_key == key

        # Apply selective reset on alerted pairs
        runaway_keys = [a.pair_key for a in alerts]
        result = selective_weight_reset(cache2, runaway_keys, reset_value=0.1)

        assert result.edges_reset == 1
        assert cache2._edges[key] == 0.1  # Reset
        assert cache2._edges[key2] == 0.42  # Untouched

    def test_previous_weights_captured(self) -> None:
        """Reset result captures all previous weights for audit."""
        cache = KGEdgeCache()
        cache._loaded = True
        k1 = _make_pair_key("A", "B")
        k2 = _make_pair_key("C", "D")
        cache._edges = {k1: 0.85, k2: 0.92}
        cache._edge_count = 2

        result = emergency_weight_reset(cache, reset_value=0.2)

        assert result.previous_weights[k1] == 0.85
        assert result.previous_weights[k2] == 0.92
        # After reset
        assert cache._edges[k1] == 0.2
        assert cache._edges[k2] == 0.2
