"""Salience Scorer - Write-Path Priority | ADR: K006.1 | Module: M06"""

import logging
from typing import Dict, Optional

from .salience_types import SalienceConfig, SalienceScore

logger = logging.getLogger(__name__)


class SalienceScorer:
    """Compute write-path salience: 0.50×social + 0.40×affect + 0.10×recency. Performance: <5ms P95"""

    def __init__(self, config: Optional[SalienceConfig] = None):
        self.config = config or SalienceConfig()
        self.version = "0.1.0"
        logger.info(f"SalienceScorer initialized (v{self.version})")

    async def compute_salience(
        self,
        participant_roles: Dict[str, str],
        affect_valence: float,
        affect_arousal: float,
        event_time_utc: str,
    ) -> SalienceScore:
        """Compute write-path salience score and band."""
        # TODO: Compute social_importance from participant_roles
        # TODO: Compute affect_intensity from valence + arousal
        # TODO: Compute recency_score from event_time
        # TODO: Apply formula: 0.50×social + 0.40×affect + 0.10×recency
        # TODO: Determine band (HIGH/MED/LOW) and reasons
        raise NotImplementedError("SalienceScorer.compute_salience - Step 7")

    # Future: async def rerank_query_results(self, ...), async def learn_attention_weights(self, ...)
    # Future: async def rerank_query_results(self, ...), async def learn_attention_weights(self, ...)
    # Future: async def rerank_query_results(self, ...), async def learn_attention_weights(self, ...)
