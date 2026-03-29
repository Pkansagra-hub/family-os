"""
P03 integration with K0 QoS Scheduler.

Uses K0 Scheduler for token-based resource management with WDRR algorithm
and priority bands. Provides P03-specific scheduler profiles for different
operation types (batch consolidation, similarity search, dream exploration).

Dossier Reference: Section 15.2 K0 Scheduler Integration
K0 Reference: k0/qos/scheduler.py, k0/qos/metrics.py

Issue 6.4.1: Token-based resource management for P03 operations.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from k0.qos.metrics import QoSMetrics
    from k0.qos.scheduler import Scheduler, SchedulerToken

logger = logging.getLogger(__name__)


# Privacy/QoS bands - aligns with K0 privacy band system
P03Band = Literal["GREEN", "AMBER", "RED"]

# Scheduler ports - aligns with K0 scheduler port types
P03Port = Literal["command", "query", "sse"]


@dataclass(frozen=True, slots=True)
class P03SchedulerProfile:
    """
    Scheduler profile for P03 operations.

    Defines the token cost and port allocation for different
    operation types within the P03 consolidation pipeline.

    Attributes:
        name: Profile identifier (e.g., "BATCH_CONSOLIDATION")
        description: Human-readable description
        port: K0 scheduler port (command/query/sse)
        base_cost: Base token cost for this operation
        cost_per_event: Additional cost per event in batch
    """

    name: str
    description: str
    port: P03Port = "command"
    base_cost: int = 10
    cost_per_event: float = 0.1


# P03-specific scheduler profiles from dossier Section 15.2
P03_SCHEDULER_PROFILES: dict[str, P03SchedulerProfile] = {
    "BATCH_CONSOLIDATION": P03SchedulerProfile(
        name="BATCH_CONSOLIDATION",
        description="Standard batch consolidation (R0-R8)",
        port="command",
        base_cost=10,
        cost_per_event=0.1,
    ),
    "SIMILARITY_SEARCH": P03SchedulerProfile(
        name="SIMILARITY_SEARCH",
        description="pgvector similarity queries during R2-R4",
        port="query",
        base_cost=5,
        cost_per_event=0.05,
    ),
    "DREAM_EXPLORATION": P03SchedulerProfile(
        name="DREAM_EXPLORATION",
        description="R5 dream phase (optional, creative)",
        port="command",
        base_cost=20,
        cost_per_event=0.2,
    ),
}


class P03SchedulerIntegration:
    """
    P03 integration with K0 QoS Scheduler.

    Provides token-based resource management using K0's Weighted Deficit
    Round Robin (WDRR) scheduler. Priority bands (GREEN > AMBER > RED)
    affect scheduling priority.

    K0 References:
    - k0/qos/scheduler.py: Scheduler.acquire(), SchedulerToken
    - k0/qos/metrics.py: QoSMetrics.record_acquisition()

    Usage:
        scheduler = Scheduler(profile=SchedulerProfile(...))
        integration = P03SchedulerIntegration(scheduler)

        # Acquire token before batch processing
        with integration.acquire_batch_token(batch_size=100, band="GREEN") as token:
            # Process batch...
            pass
        # Token auto-released on context exit
    """

    def __init__(
        self,
        scheduler: Scheduler,
        qos_metrics: QoSMetrics | None = None,
        pipeline_id: str = "p03_consolidation",
    ) -> None:
        """
        Initialize P03 scheduler integration.

        Args:
            scheduler: K0 Scheduler instance for token management
            qos_metrics: Optional K0 QoSMetrics for acquisition tracking
            pipeline_id: Pipeline identifier for metrics labeling
        """
        self._scheduler = scheduler
        self._qos_metrics = qos_metrics
        self._pipeline_id = pipeline_id

    @property
    def scheduler(self) -> Scheduler:
        """Access underlying K0 scheduler."""
        return self._scheduler

    @property
    def pipeline_id(self) -> str:
        """Get pipeline identifier."""
        return self._pipeline_id

    def acquire_batch_token(
        self,
        batch_size: int,
        band: P03Band = "AMBER",
        profile_name: str = "BATCH_CONSOLIDATION",
    ) -> SchedulerToken:
        """
        Acquire scheduler token for batch processing.

        Uses K0 Scheduler.acquire() with WDRR algorithm. Returns a
        SchedulerToken that can be used as a context manager for
        automatic release.

        Args:
            batch_size: Number of events in batch (affects cost)
            band: Privacy/QoS band (GREEN/AMBER/RED) - affects priority
            profile_name: Profile to use from P03_SCHEDULER_PROFILES

        Returns:
            SchedulerToken for resource reservation

        Raises:
            SchedulerCapacityError: If scheduler capacity exceeded

        Example:
            with integration.acquire_batch_token(100, "GREEN") as token:
                # Process batch within token reservation
                pass
        """
        profile = P03_SCHEDULER_PROFILES.get(profile_name)
        if profile is None:
            profile = P03_SCHEDULER_PROFILES["BATCH_CONSOLIDATION"]
            logger.warning(
                "Unknown profile '%s', using BATCH_CONSOLIDATION",
                profile_name,
            )

        # Calculate cost based on batch size
        cost = self._calculate_cost(batch_size, profile)

        logger.debug(
            "Acquiring scheduler token: batch_size=%d, band=%s, port=%s, cost=%d",
            batch_size,
            band,
            profile.port,
            cost,
        )

        # Acquire token from K0 scheduler
        token = self._scheduler.acquire(
            band=band,
            port=profile.port,
            cost=cost,
        )

        logger.debug(
            "Token acquired: port=%s, cost=%d",
            token.port,
            token.cost,
        )

        return token

    def acquire_query_token(
        self,
        query_count: int = 1,
        band: P03Band = "AMBER",
    ) -> SchedulerToken:
        """
        Acquire scheduler token for similarity queries.

        Uses SIMILARITY_SEARCH profile for query-side operations
                (pgvector queries, pattern matching).

        Args:
            query_count: Number of queries to execute
            band: Privacy/QoS band

        Returns:
            SchedulerToken for query reservation
        """
        profile = P03_SCHEDULER_PROFILES["SIMILARITY_SEARCH"]
        cost = max(1, profile.base_cost + int(query_count * profile.cost_per_event))

        return self._scheduler.acquire(
            band=band,
            port=profile.port,
            cost=cost,
        )

    def acquire_dream_token(
        self,
        batch_size: int,
        band: P03Band = "GREEN",
    ) -> SchedulerToken:
        """
        Acquire scheduler token for R5 dream exploration.

        Dream phase is optional and creative, uses higher cost
        to reflect resource intensity.

        Args:
            batch_size: Number of events for dream exploration
            band: Privacy/QoS band (typically GREEN for dreams)

        Returns:
            SchedulerToken for dream phase reservation
        """
        profile = P03_SCHEDULER_PROFILES["DREAM_EXPLORATION"]
        cost = self._calculate_cost(batch_size, profile)

        return self._scheduler.acquire(
            band=band,
            port=profile.port,
            cost=cost,
        )

    def release_token(self, token: SchedulerToken) -> None:
        """
        Explicitly release a scheduler token.

        Normally not needed when using token as context manager.
        Use for manual token lifecycle management.

        Args:
            token: Token to release
        """
        token.release()
        logger.debug("Token released: port=%s, cost=%d", token.port, token.cost)

    def get_active_tokens(self, port: P03Port = "command") -> int:
        """
        Get count of active tokens for a port.

        Useful for adaptive batch sizing based on contention.

        Args:
            port: Scheduler port to check

        Returns:
            Number of active tokens on port
        """
        return self._scheduler.active_tokens(port)

    def get_contention_factor(self) -> float:
        """
        Calculate contention factor for adaptive batch sizing.

        Returns a factor between 0.5 and 1.0 based on scheduler load:
        - Low contention (0-5 tokens): 1.0 (full batch size)
        - Medium contention (5-10 tokens): 0.75
        - High contention (>10 tokens): 0.5 (reduced batch size)

        Returns:
            Contention factor for batch size adjustment
        """
        active_command = self._scheduler.active_tokens("command")
        active_query = self._scheduler.active_tokens("query")
        total_active = active_command + active_query

        if total_active > 10:
            return 0.5
        elif total_active > 5:
            return 0.75
        else:
            return 1.0

    def _calculate_cost(self, batch_size: int, profile: P03SchedulerProfile) -> int:
        """
        Calculate token cost for a batch operation.

        Args:
            batch_size: Number of events in batch
            profile: Scheduler profile with cost configuration

        Returns:
            Total token cost (minimum 1)
        """
        cost = profile.base_cost + int(batch_size * profile.cost_per_event)
        return max(1, cost)
