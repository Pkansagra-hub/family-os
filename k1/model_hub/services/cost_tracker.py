"""Per-request cost computation from manifest tables [F50].

Computes cost_usd from TokenUsage + ModelSpec cost tables (MH-07).
Aggregates spending per-consumer, per-model, per-capability.

Import graph (Layer 3 -- imports Layer 0 + Layer 1 + Layer 2)
--------------------------------------------------------------
k1.model_hub.services.cost_tracker
  -> k1.model_hub.types      (Layer 0: CapabilityType, TokenUsage)
  -> k1.model_hub.manifest   (Layer 0: ModelSpec)
  -> stdlib only

NEVER import from any adapter or runtime module.

References
----------
- model_hub.mmd: CostTracker service
- Invariant MH-07: Cost from manifest model cost tables (not hardcoded)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from k1.model_hub.manifest import ModelSpec
from k1.model_hub.types import CapabilityType, TokenUsage

# ===========================================================================
# CostRecord -- output of cost computation
# ===========================================================================


@dataclass(frozen=True)
class CostRecord:
    """Result of a single cost computation."""

    cost_usd: float
    input_cost_usd: float
    output_cost_usd: float
    model_id: str
    provider_id: str
    prompt_tokens: int
    completion_tokens: int
    capability: CapabilityType
    consumer_id: str = ""


# ===========================================================================
# CostTracker
# ===========================================================================


class CostTracker:
    """Per-request cost computation from manifest model cost tables (MH-07).

    Computes cost_usd = (prompt_tokens * cost_per_1m_input / 1_000_000)
                      + (completion_tokens * cost_per_1m_output / 1_000_000).

    Cost tables come from ModelSpec in provider manifest, never hardcoded.

    Maintains per-consumer, per-model, per-capability aggregation counters.
    """

    def __init__(self) -> None:
        self._records: List[CostRecord] = []
        self._by_consumer: Dict[str, float] = {}
        self._by_model: Dict[str, float] = {}
        self._by_capability: Dict[str, float] = {}

    # -- Compute ---------------------------------------------------------------

    @staticmethod
    def compute_cost(
        usage: TokenUsage,
        model_spec: ModelSpec,
    ) -> tuple[float, float]:
        """Compute (input_cost, output_cost) from usage + manifest cost table.

        Args:
            usage: Token usage from provider response.
            model_spec: Model spec with cost_per_1m_input/output from manifest.

        Returns:
            Tuple of (input_cost_usd, output_cost_usd).
        """
        input_cost = usage.prompt_tokens * model_spec.cost_per_1m_input / 1_000_000
        output_cost = usage.completion_tokens * model_spec.cost_per_1m_output / 1_000_000
        return input_cost, output_cost

    # -- Track -----------------------------------------------------------------

    def track(
        self,
        usage: TokenUsage,
        model_spec: ModelSpec,
        *,
        provider_id: str,
        capability: CapabilityType,
        consumer_id: str = "",
    ) -> CostRecord:
        """Compute and record cost for a completed request.

        Args:
            usage: Token usage from provider response.
            model_spec: Model spec from manifest cost table (MH-07).
            provider_id: Provider that handled the request.
            capability: Capability type of the request.
            consumer_id: Consumer ID (for per-consumer aggregation).

        Returns:
            CostRecord with computed costs.
        """
        input_cost, output_cost = self.compute_cost(usage, model_spec)
        total = input_cost + output_cost

        record = CostRecord(
            cost_usd=total,
            input_cost_usd=input_cost,
            output_cost_usd=output_cost,
            model_id=model_spec.id,
            provider_id=provider_id,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            capability=capability,
            consumer_id=consumer_id,
        )

        self._records.append(record)

        # Aggregation
        self._by_consumer[consumer_id] = self._by_consumer.get(consumer_id, 0.0) + total
        self._by_model[model_spec.id] = self._by_model.get(model_spec.id, 0.0) + total
        cap_key = capability.value
        self._by_capability[cap_key] = self._by_capability.get(cap_key, 0.0) + total

        return record

    # -- Query -----------------------------------------------------------------

    @property
    def records(self) -> List[CostRecord]:
        """All cost records."""
        return list(self._records)

    @property
    def total_cost_usd(self) -> float:
        """Total cost across all records."""
        return sum(r.cost_usd for r in self._records)

    @property
    def by_consumer(self) -> Dict[str, float]:
        """Cumulative cost per consumer_id."""
        return dict(self._by_consumer)

    @property
    def by_model(self) -> Dict[str, float]:
        """Cumulative cost per model_id."""
        return dict(self._by_model)

    @property
    def by_capability(self) -> Dict[str, float]:
        """Cumulative cost per capability."""
        return dict(self._by_capability)

    def reset(self) -> None:
        """Reset all records and aggregations."""
        self._records.clear()
        self._by_consumer.clear()
        self._by_model.clear()
        self._by_capability.clear()


__all__ = [
    "CostRecord",
    "CostTracker",
]
