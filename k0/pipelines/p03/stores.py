"""
P03 Store Adapters — thin wrappers translating syscalls into module protocols.

These adapters live in pipeline code (not kernel code) because they translate
between generic syscall interfaces and domain-specific module protocols.

No pipeline-specific constants here. Callers provide their own key namespaces.

Architecture:
    migrations (0040, 0041) -> syscalls (learned_weights_*) -> these adapters -> modules
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from k0.modules.consolidation.algorithms.importance_scorer import LearnedWeights

logger = logging.getLogger(__name__)


class SyscallWeightStore:
    """
    Implements WeightStoreProtocol for R1 ImportanceScorer using syscalls.

    Translates syscalls.learned_weights_query() bulk rows into the
    LearnedWeights container that ImportanceScorer expects.

    Usage:
        store = SyscallWeightStore(syscalls=ctx.syscalls)
        scorer = ImportanceScorer(space_id=space_id, weight_store=store)
    """

    def __init__(self, syscalls: Any) -> None:
        self._syscalls = syscalls

    async def get_weights(
        self,
        space_id: str,
        param_prefix: str,
    ) -> Optional[LearnedWeights]:
        """
        Fetch learned weights by prefix, stripping prefix from keys.

        Calls syscalls.learned_weights_query(space_id, param_prefix) and
        converts rows into LearnedWeights dict. Keys are returned WITHOUT
        the prefix (e.g. "importance_sentiment" -> "sentiment").

        Returns None if no rows found.
        """
        result = await self._syscalls.learned_weights_query(
            space_id=space_id,
            param_prefix=param_prefix,
        )

        rows = result.get("rows", [])
        if not rows:
            return None

        prefix_len = len(param_prefix)
        weights: dict[str, float] = {}
        min_sample_count = rows[0].get("sample_count", 0)
        max_updated_at = 0

        for row in rows:
            key = row["param_key"]
            short_key = key[prefix_len:] if key.startswith(param_prefix) else key
            weights[short_key] = row["current_value"]

            sc = row.get("sample_count", 0)
            if sc < min_sample_count:
                min_sample_count = sc

            ua = row.get("updated_at", 0) or 0
            if ua > max_updated_at:
                max_updated_at = ua

        return LearnedWeights(
            weights=weights,
            sample_count=min_sample_count,
            updated_at=max_updated_at,
        )


class SyscallLearnedWeightsStore:
    """
    Implements LearnedWeightsStoreProtocol for R3 NoveltyBonusLearner using syscalls.

    Maps 1:1 to syscalls.learned_weights_get() and learned_weights_upsert().

    Usage:
        store = SyscallLearnedWeightsStore(syscalls=ctx.syscalls)
        R3Stores(..., learned_weights_store=store)
    """

    def __init__(self, syscalls: Any) -> None:
        self._syscalls = syscalls

    async def get_weight(self, param_key: str, space_id: str) -> Optional[float]:
        """Fetch single weight value by exact key."""
        row = await self._syscalls.learned_weights_get(
            space_id=space_id,
            param_key=param_key,
        )
        if row is None:
            return None
        return row.get("current_value")

    async def upsert_weight(
        self,
        param_key: str,
        space_id: str,
        value: float,
        prior_value: float,
    ) -> None:
        """Upsert weight value via syscalls."""
        await self._syscalls.learned_weights_upsert(
            space_id=space_id,
            param_key=param_key,
            value=value,
            prior_value=prior_value,
        )
