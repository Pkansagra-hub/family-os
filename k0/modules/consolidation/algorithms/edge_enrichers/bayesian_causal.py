"""
BayesianCausalEnricher - GAP-007 Epic 3.5

Infers causal edges under sparse observations using Bayesian inference
from temporal precedence patterns.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Dict, List, Mapping, Optional, Sequence, Tuple

from k0.modules.consolidation.algorithms.observation_context import ObservationContext
from k0.pipelines.p03.phase_outputs import KGEdge, KGEdgeUpdate

if TYPE_CHECKING:
    from k0.pipelines.p03.phases.r4_config import BayesianCausalConfig

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExistingEdgeInfo:
    edge_id: str
    relationship_type: Optional[str] = None


class BayesianCausalEnricher:
    """Infers causal edges using Bayesian inference from temporal precedence."""

    def __init__(self, config: Optional["BayesianCausalConfig"]) -> None:
        self.config = config or BayesianCausalConfig()

    async def enrich(
        self,
        entity_contexts: Mapping[str, Sequence[ObservationContext]],
        existing_edges: Mapping[object, object],
    ) -> Tuple[List[KGEdge], List[KGEdgeUpdate]]:
        if not self.config.enabled:
            return [], []

        entity_observations = self._build_entity_observations(entity_contexts)
        if len(entity_observations) < 2:
            return [], []

        normalized_existing = self._normalize_existing_edges(existing_edges)
        new_edges: List[KGEdge] = []
        updates: List[KGEdgeUpdate] = []

        entity_ids = list(entity_observations.keys())
        for entity_a in entity_ids:
            observations_a = entity_observations[entity_a]

            for entity_b in entity_ids:
                if entity_a == entity_b:
                    continue

                observations_b = entity_observations[entity_b]

                # Count temporal precedence evidence
                a_before_b = 0
                b_before_a = 0

                for ts_a, ctx_a in observations_a:
                    for ts_b, ctx_b in observations_b:
                        if ts_a < ts_b:
                            a_before_b += 1
                        elif ts_b < ts_a:
                            b_before_a += 1

                total_pairs = a_before_b + b_before_a

                if total_pairs < self.config.min_evidence_count:
                    continue

                # Bayesian update
                prior = self.config.prior_strength

                # Likelihood ratio - direction with more evidence
                if a_before_b > b_before_a:
                    likelihood_ratio = a_before_b / max(1, b_before_a)
                    cause, effect = entity_a, entity_b
                    precedence_count = a_before_b
                elif b_before_a > a_before_b:
                    likelihood_ratio = b_before_a / max(1, a_before_b)
                    cause, effect = entity_b, entity_a
                    precedence_count = b_before_a
                else:
                    # Equal evidence - skip
                    continue

                # Posterior probability (simplified Bayesian update)
                posterior = (prior * likelihood_ratio) / (prior * likelihood_ratio + (1 - prior))

                if posterior < self.config.posterior_threshold:
                    continue

                # Directed edge
                edge_key = (cause, effect)
                evidence_event_ids = self._evidence_event_ids(observations_a, observations_b)
                context = self._select_best_context(observations_a, observations_b)

                existing = normalized_existing.get(edge_key)
                if existing:
                    updates.append(
                        KGEdgeUpdate(
                            edge_id=existing.edge_id,
                            weight_delta=0.05,
                            confidence_delta=0.05,
                            source_algorithm="bayesian_causal",
                            new_evidence_event_ids=evidence_event_ids,
                            observation_context=context,
                        )
                    )
                else:
                    edge_id = self._edge_id_for_pair(edge_key)
                    new_edges.append(
                        KGEdge(
                            edge_id=edge_id,
                            source_entity_id=cause,
                            target_entity_id=effect,
                            relationship_type=self.config.relation_type,
                            weight=posterior,
                            confidence=posterior,
                            source_algorithm="bayesian_causal",
                            evidence_event_ids=evidence_event_ids,
                            properties_json=json.dumps(
                                {
                                    "precedence_count": precedence_count,
                                    "total_pairs": total_pairs,
                                    "posterior": posterior,
                                    "prior": prior,
                                    "likelihood_ratio": likelihood_ratio,
                                }
                            ),
                            algorithm_params_json=json.dumps(
                                {
                                    "prior_strength": self.config.prior_strength,
                                    "min_evidence_count": self.config.min_evidence_count,
                                    "posterior_threshold": self.config.posterior_threshold,
                                }
                            ),
                            observation_context=context,
                        )
                    )

        return new_edges, updates

    def _build_entity_observations(
        self,
        entity_contexts: Mapping[str, Sequence[ObservationContext]],
    ) -> Dict[str, List[Tuple[int, ObservationContext]]]:
        """Build entity->[(timestamp, context)] mapping."""
        result: Dict[str, List[Tuple[int, ObservationContext]]] = {}
        for entity_id, contexts in entity_contexts.items():
            observations = []
            for ctx in contexts:
                if ctx.observed_at is not None:
                    observations.append((ctx.observed_at, ctx))
            if observations:
                observations.sort(key=lambda x: x[0])
                result[entity_id] = observations
        return result

    def _normalize_existing_edges(
        self, existing_edges: Mapping[object, object]
    ) -> Dict[Tuple[str, str], ExistingEdgeInfo]:
        """Convert existing edge mapping to directed key lookup."""
        result: Dict[Tuple[str, str], ExistingEdgeInfo] = {}
        for key, edge_info in existing_edges.items():
            if isinstance(key, tuple) and len(key) == 2:
                edge_key = (str(key[0]), str(key[1]))
                if hasattr(edge_info, "edge_id"):
                    result[edge_key] = ExistingEdgeInfo(
                        edge_id=edge_info.edge_id,
                        relationship_type=getattr(edge_info, "relationship_type", None),
                    )
        return result

    def _evidence_event_ids(
        self,
        observations_a: List[Tuple[int, ObservationContext]],
        observations_b: List[Tuple[int, ObservationContext]],
    ) -> List[str]:
        """Extract event IDs from observations."""
        event_ids = []
        for _, ctx in observations_a[:3]:  # Limit to first 3
            if ctx.source_event_id:
                event_ids.append(ctx.source_event_id)
        for _, ctx in observations_b[:3]:
            if ctx.source_event_id:
                event_ids.append(ctx.source_event_id)
        return list(dict.fromkeys(event_ids))  # Deduplicate while preserving order

    def _select_best_context(
        self,
        observations_a: List[Tuple[int, ObservationContext]],
        observations_b: List[Tuple[int, ObservationContext]],
    ) -> Optional[ObservationContext]:
        """Select the most recent context with complete information."""
        all_contexts = [ctx for _, ctx in observations_a] + [ctx for _, ctx in observations_b]
        for ctx in reversed(all_contexts):  # Most recent first
            if ctx.location_type or ctx.social_context:
                return ctx
        return all_contexts[-1] if all_contexts else None

    def _edge_id_for_pair(self, edge_key: Tuple[str, str]) -> str:
        """Generate deterministic edge ID for entity pair."""
        pair_str = f"{edge_key[0]}|{edge_key[1]}|bayesian_causal"
        return hashlib.sha256(pair_str.encode()).hexdigest()[:32]
