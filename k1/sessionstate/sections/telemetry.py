"""
TelemetrySection - Performance Metrics (WARM Tier).

Issue: 2.3.4 (WARM tier - telemetry)
Budget: 8KB (8192 bytes)
Eviction Priority: 1 (FIRST to evict - lowest value)

Implements ISection + IEvictable protocols.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any

import flatbuffers

from k1.sessionstate.generated.flatbuffers.K1.SessionState import (
    CostMetricsAddAvgCostPerTurn,
    CostMetricsAddEmbeddingCost,
    CostMetricsAddGenerationCost,
    CostMetricsAddReasoningCost,
    CostMetricsAddToolCost,
    CostMetricsAddTotalCostMicrodollars,
    CostMetricsEnd,
    CostMetricsStart,
    ErrorMetricsAddErrorRate,
    ErrorMetricsAddLastErrorMessage,
    ErrorMetricsAddLastErrorTurn,
    ErrorMetricsAddModelErrors,
    ErrorMetricsAddRateLimitErrors,
    ErrorMetricsAddTimeoutErrors,
    ErrorMetricsAddToolErrors,
    ErrorMetricsAddTotalErrors,
    ErrorMetricsAddValidationErrors,
    ErrorMetricsEnd,
    ErrorMetricsStart,
    LatencyMetricsAddMaxMs,
    LatencyMetricsAddMinMs,
    LatencyMetricsAddModelLatencyP50Ms,
    LatencyMetricsAddOrchestrationLatencyP50Ms,
    LatencyMetricsAddP50Ms,
    LatencyMetricsAddP90Ms,
    LatencyMetricsAddP95Ms,
    LatencyMetricsAddP99Ms,
    LatencyMetricsAddRetrievalLatencyP50Ms,
    LatencyMetricsAddToolLatencyP50Ms,
    LatencyMetricsEnd,
    LatencyMetricsStart,
    PerformanceSummaryAddAvgLatencyMs,
    PerformanceSummaryAddAvgResponseLength,
    PerformanceSummaryAddBudgetSlaMet,
    PerformanceSummaryAddCostPerTurn,
    PerformanceSummaryAddErrorRate,
    PerformanceSummaryAddLatencySlaMet,
    PerformanceSummaryAddToolCallRate,
    PerformanceSummaryEnd,
    PerformanceSummaryStart,
    SectionHeaderAddChecksum,
    SectionHeaderAddLastUpdatedMs,
    SectionHeaderAddSectionName,
    SectionHeaderAddSizeBytes,
    SectionHeaderEnd,
    SectionHeaderStart,
)
from k1.sessionstate.generated.flatbuffers.K1.SessionState import (
    TelemetrySection as FBTelemetrySection,
)
from k1.sessionstate.generated.flatbuffers.K1.SessionState import (
    TelemetrySectionAddCost,
    TelemetrySectionAddErrors,
    TelemetrySectionAddHeader,
    TelemetrySectionAddLatency,
    TelemetrySectionAddSampleCount,
    TelemetrySectionAddSummary,
    TelemetrySectionAddTokens,
    TelemetrySectionAddTurnTimings,
    TelemetrySectionEnd,
    TelemetrySectionStart,
    TelemetrySectionStartTurnTimingsVector,
    TokenMetricsAddAvgInputPerTurn,
    TokenMetricsAddAvgOutputPerTurn,
    TokenMetricsAddEmbeddingTokens,
    TokenMetricsAddGenerationTokens,
    TokenMetricsAddInputTokens,
    TokenMetricsAddOutputTokens,
    TokenMetricsAddReasoningTokens,
    TokenMetricsAddTotalTokens,
    TokenMetricsEnd,
    TokenMetricsStart,
    TurnTimingAddDurationMs,
    TurnTimingAddHadError,
    TurnTimingAddHadToolCall,
    TurnTimingAddTokenCount,
    TurnTimingAddTurnNumber,
    TurnTimingEnd,
    TurnTimingStart,
)

# =============================================================================
# Error Types
# =============================================================================


class ErrorType(IntEnum):
    """Error type classification."""

    TIMEOUT = 0
    RATE_LIMIT = 1
    MODEL = 2
    TOOL = 3
    VALIDATION = 4
    OTHER = 5


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class TokenData:
    """Token usage metrics."""

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    reasoning_tokens: int = 0
    generation_tokens: int = 0
    embedding_tokens: int = 0
    avg_input_per_turn: int = 0
    avg_output_per_turn: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "reasoning_tokens": self.reasoning_tokens,
            "generation_tokens": self.generation_tokens,
            "embedding_tokens": self.embedding_tokens,
            "avg_input_per_turn": self.avg_input_per_turn,
            "avg_output_per_turn": self.avg_output_per_turn,
        }


@dataclass
class CostData:
    """Cost metrics in microdollars (1/1,000,000 USD)."""

    total_cost_microdollars: int = 0
    reasoning_cost: int = 0
    generation_cost: int = 0
    embedding_cost: int = 0
    tool_cost: int = 0
    avg_cost_per_turn: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "total_cost_microdollars": self.total_cost_microdollars,
            "total_cost_usd": self.total_cost_microdollars / 1_000_000,
            "reasoning_cost": self.reasoning_cost,
            "generation_cost": self.generation_cost,
            "embedding_cost": self.embedding_cost,
            "tool_cost": self.tool_cost,
            "avg_cost_per_turn": self.avg_cost_per_turn,
        }


@dataclass
class LatencyData:
    """Latency metrics with percentiles."""

    p50_ms: int = 0
    p90_ms: int = 0
    p95_ms: int = 0
    p99_ms: int = 0
    min_ms: int = 0
    max_ms: int = 0
    model_latency_p50_ms: int = 0
    retrieval_latency_p50_ms: int = 0
    tool_latency_p50_ms: int = 0
    orchestration_latency_p50_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "p50_ms": self.p50_ms,
            "p90_ms": self.p90_ms,
            "p95_ms": self.p95_ms,
            "p99_ms": self.p99_ms,
            "min_ms": self.min_ms,
            "max_ms": self.max_ms,
            "model_latency_p50_ms": self.model_latency_p50_ms,
            "retrieval_latency_p50_ms": self.retrieval_latency_p50_ms,
            "tool_latency_p50_ms": self.tool_latency_p50_ms,
            "orchestration_latency_p50_ms": self.orchestration_latency_p50_ms,
        }


@dataclass
class TurnTimingData:
    """Per-turn timing data."""

    turn_number: int = 0
    duration_ms: int = 0
    token_count: int = 0
    had_error: bool = False
    had_tool_call: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "turn_number": self.turn_number,
            "duration_ms": self.duration_ms,
            "token_count": self.token_count,
            "had_error": self.had_error,
            "had_tool_call": self.had_tool_call,
        }


@dataclass
class ErrorData:
    """Error tracking metrics."""

    total_errors: int = 0
    timeout_errors: int = 0
    rate_limit_errors: int = 0
    model_errors: int = 0
    tool_errors: int = 0
    validation_errors: int = 0
    last_error_turn: int = 0
    last_error_message: str = ""
    error_rate: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "total_errors": self.total_errors,
            "timeout_errors": self.timeout_errors,
            "rate_limit_errors": self.rate_limit_errors,
            "model_errors": self.model_errors,
            "tool_errors": self.tool_errors,
            "validation_errors": self.validation_errors,
            "last_error_turn": self.last_error_turn,
            "last_error_message": self.last_error_message,
            "error_rate": self.error_rate,
        }


@dataclass
class SummaryData:
    """Performance summary."""

    avg_latency_ms: int = 0
    error_rate: float = 0.0
    cost_per_turn: float = 0.0
    avg_response_length: int = 0
    tool_call_rate: float = 0.0
    latency_sla_met: bool = True
    budget_sla_met: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "avg_latency_ms": self.avg_latency_ms,
            "error_rate": self.error_rate,
            "cost_per_turn": self.cost_per_turn,
            "avg_response_length": self.avg_response_length,
            "tool_call_rate": self.tool_call_rate,
            "latency_sla_met": self.latency_sla_met,
            "budget_sla_met": self.budget_sla_met,
        }


@dataclass
class EvictedData:
    """Data returned when eviction occurs."""

    turn_timings: list[TurnTimingData] = field(default_factory=list)
    bytes_freed: int = 0
    eviction_reason: str = "pressure"


# =============================================================================
# TelemetrySection
# =============================================================================


class TelemetrySection:
    """
    Telemetry section - performance metrics.

    WARM tier, 8KB budget, eviction priority 1 (first to evict).

    Implements ISection + IEvictable protocols.
    """

    BUDGET_BYTES = 8192  # 8KB
    TIER = "warm"
    SECTION_NAME = "telemetry"
    CAN_EVICT = True
    EVICTION_PRIORITY = 1  # FIRST to evict

    MAX_TURN_TIMINGS = 20
    MAX_LATENCY_SAMPLES = 100
    LATENCY_SLA_P95_MS = 500

    def __init__(self) -> None:
        """Initialize TelemetrySection."""
        now_ms = int(time.time() * 1000)

        # Core metrics
        self._tokens = TokenData()
        self._cost = CostData()
        self._latency = LatencyData()
        self._errors = ErrorData()
        self._summary = SummaryData()

        # Turn timings (rolling window)
        self._turn_timings: list[TurnTimingData] = []

        # Raw latency samples for percentile calculation
        self._latency_samples: list[int] = []

        # Metadata
        self._collection_started_ms = now_ms
        self._last_updated_ms = now_ms
        self._sample_count = 0
        self._turn_count = 0
        self._tool_call_count = 0

        # Integrity
        self._integrity_hash: str = ""

        # Cache
        self._cached_flatbuffer: bytes | None = None

    # -------------------------------------------------------------------------
    # ISection Protocol
    # -------------------------------------------------------------------------

    @property
    def name(self) -> str:
        """Section name."""
        return self.SECTION_NAME

    @property
    def tier(self) -> str:
        """Section tier."""
        return self.TIER

    @property
    def budget_bytes(self) -> int:
        """Budget in bytes."""
        return self.BUDGET_BYTES

    def get_size_bytes(self) -> int:
        """
        Get current size in bytes.

        Estimates based on content.
        """
        # Base size ~400 bytes
        size = 400

        # Turn timings: ~20 bytes each
        size += len(self._turn_timings) * 20

        # Latency samples: ~4 bytes each
        size += len(self._latency_samples) * 4

        # Error message
        size += len(self._errors.last_error_message.encode("utf-8"))

        return size

    def clear(self) -> None:
        """Clear section to initial state."""
        now_ms = int(time.time() * 1000)

        self._tokens = TokenData()
        self._cost = CostData()
        self._latency = LatencyData()
        self._errors = ErrorData()
        self._summary = SummaryData()
        self._turn_timings = []
        self._latency_samples = []
        self._collection_started_ms = now_ms
        self._last_updated_ms = now_ms
        self._sample_count = 0
        self._turn_count = 0
        self._tool_call_count = 0
        self._integrity_hash = ""
        self._invalidate_cache()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "tier": self.tier,
            "budget_bytes": self.budget_bytes,
            "size_bytes": self.get_size_bytes(),
            "tokens": self._tokens.to_dict(),
            "cost": self._cost.to_dict(),
            "latency": self._latency.to_dict(),
            "errors": self._errors.to_dict(),
            "summary": self._summary.to_dict(),
            "turn_timings": [t.to_dict() for t in self._turn_timings],
            "collection_started_ms": self._collection_started_ms,
            "last_updated_ms": self._last_updated_ms,
            "sample_count": self._sample_count,
            "turn_count": self._turn_count,
        }

    # -------------------------------------------------------------------------
    # IEvictable Protocol
    # -------------------------------------------------------------------------

    def get_eviction_priority(self) -> int:
        """Get eviction priority (lower = evict first)."""
        return self.EVICTION_PRIORITY

    def can_evict(self) -> bool:
        """Check if section can be evicted."""
        # Can evict if we have turn timings or samples
        return len(self._turn_timings) > 0 or len(self._latency_samples) > 5

    def evict_partial(self, target_kb: float = 0.5) -> EvictedData:
        """
        Evict data to reduce size.

        Strategy:
        1. Clear turn timings first (most space)
        2. Reduce latency samples
        3. Aggregate to summary

        Args:
            target_kb: Target KB to free

        Returns:
            EvictedData with evicted turn timings
        """
        evicted = EvictedData()
        target_bytes = int(target_kb * 1024)
        bytes_freed = 0

        # 1. Evict turn timings
        while self._turn_timings and bytes_freed < target_bytes:
            timing = self._turn_timings.pop(0)
            evicted.turn_timings.append(timing)
            bytes_freed += 20  # ~20 bytes per timing

        # 2. Reduce latency samples to minimum (keep last 10 for percentiles)
        if bytes_freed < target_bytes and len(self._latency_samples) > 10:
            samples_to_remove = len(self._latency_samples) - 10
            self._latency_samples = self._latency_samples[-10:]
            bytes_freed += samples_to_remove * 4

        evicted.bytes_freed = bytes_freed
        self._touch()
        return evicted

    # -------------------------------------------------------------------------
    # Token API
    # -------------------------------------------------------------------------

    def get_tokens(self) -> TokenData:
        """Get token metrics."""
        return self._tokens

    def record_tokens(
        self,
        input_tokens: int = 0,
        output_tokens: int = 0,
        *,
        reasoning_tokens: int = 0,
        generation_tokens: int = 0,
        embedding_tokens: int = 0,
    ) -> None:
        """
        Record token usage for a turn.

        Args:
            input_tokens: Input tokens used
            output_tokens: Output tokens generated
            reasoning_tokens: Tokens used for reasoning
            generation_tokens: Tokens used for generation
            embedding_tokens: Tokens used for embeddings
        """
        self._tokens.input_tokens += input_tokens
        self._tokens.output_tokens += output_tokens
        self._tokens.total_tokens += input_tokens + output_tokens
        self._tokens.reasoning_tokens += reasoning_tokens
        self._tokens.generation_tokens += generation_tokens
        self._tokens.embedding_tokens += embedding_tokens

        # Update averages
        if self._turn_count > 0:
            self._tokens.avg_input_per_turn = self._tokens.input_tokens // self._turn_count
            self._tokens.avg_output_per_turn = self._tokens.output_tokens // self._turn_count

        self._touch()

    # -------------------------------------------------------------------------
    # Cost API
    # -------------------------------------------------------------------------

    def get_cost(self) -> CostData:
        """Get cost metrics."""
        return self._cost

    def record_cost(
        self,
        cost_microdollars: int,
        *,
        reasoning_cost: int = 0,
        generation_cost: int = 0,
        embedding_cost: int = 0,
        tool_cost: int = 0,
    ) -> None:
        """
        Record cost for a turn.

        Args:
            cost_microdollars: Total cost in microdollars
            reasoning_cost: Cost for reasoning
            generation_cost: Cost for generation
            embedding_cost: Cost for embeddings
            tool_cost: Cost for tool calls
        """
        self._cost.total_cost_microdollars += cost_microdollars
        self._cost.reasoning_cost += reasoning_cost
        self._cost.generation_cost += generation_cost
        self._cost.embedding_cost += embedding_cost
        self._cost.tool_cost += tool_cost

        # Update average
        if self._turn_count > 0:
            self._cost.avg_cost_per_turn = self._cost.total_cost_microdollars // self._turn_count

        # Update summary
        self._summary.cost_per_turn = self._cost.avg_cost_per_turn / 1_000_000

        self._touch()

    def get_total_cost_usd(self) -> float:
        """Get total cost in USD."""
        return self._cost.total_cost_microdollars / 1_000_000

    # -------------------------------------------------------------------------
    # Latency API
    # -------------------------------------------------------------------------

    def get_latency(self) -> LatencyData:
        """Get latency metrics."""
        return self._latency

    def record_latency(
        self,
        duration_ms: int,
        *,
        model_latency_ms: int = 0,
        retrieval_latency_ms: int = 0,
        tool_latency_ms: int = 0,
        orchestration_latency_ms: int = 0,
    ) -> None:
        """
        Record latency for a turn.

        Args:
            duration_ms: Total turn duration in milliseconds
            model_latency_ms: Model call latency
            retrieval_latency_ms: Retrieval latency
            tool_latency_ms: Tool call latency
            orchestration_latency_ms: Orchestration latency
        """
        # Add to samples
        self._latency_samples.append(duration_ms)
        if len(self._latency_samples) > self.MAX_LATENCY_SAMPLES:
            self._latency_samples = self._latency_samples[-self.MAX_LATENCY_SAMPLES :]

        # Recalculate percentiles
        self._recalculate_percentiles()

        # Track component latencies (using P50 approximation)
        if model_latency_ms > 0:
            self._latency.model_latency_p50_ms = (
                self._latency.model_latency_p50_ms + model_latency_ms
            ) // 2
        if retrieval_latency_ms > 0:
            self._latency.retrieval_latency_p50_ms = (
                self._latency.retrieval_latency_p50_ms + retrieval_latency_ms
            ) // 2
        if tool_latency_ms > 0:
            self._latency.tool_latency_p50_ms = (
                self._latency.tool_latency_p50_ms + tool_latency_ms
            ) // 2
        if orchestration_latency_ms > 0:
            self._latency.orchestration_latency_p50_ms = (
                self._latency.orchestration_latency_p50_ms + orchestration_latency_ms
            ) // 2

        # Check SLA
        self._summary.latency_sla_met = self._latency.p95_ms <= self.LATENCY_SLA_P95_MS

        self._touch()

    def _recalculate_percentiles(self) -> None:
        """Recalculate latency percentiles from samples."""
        if not self._latency_samples:
            return

        sorted_samples = sorted(self._latency_samples)
        n = len(sorted_samples)

        self._latency.min_ms = sorted_samples[0]
        self._latency.max_ms = sorted_samples[-1]
        self._latency.p50_ms = sorted_samples[int(n * 0.50)]
        self._latency.p90_ms = sorted_samples[min(int(n * 0.90), n - 1)]
        self._latency.p95_ms = sorted_samples[min(int(n * 0.95), n - 1)]
        self._latency.p99_ms = sorted_samples[min(int(n * 0.99), n - 1)]

        # Update summary
        self._summary.avg_latency_ms = sum(sorted_samples) // n

    # -------------------------------------------------------------------------
    # Turn Timing API
    # -------------------------------------------------------------------------

    def record_turn(
        self,
        turn_number: int,
        duration_ms: int,
        token_count: int = 0,
        *,
        had_error: bool = False,
        had_tool_call: bool = False,
    ) -> None:
        """
        Record a complete turn.

        Args:
            turn_number: Turn number
            duration_ms: Duration in milliseconds
            token_count: Total tokens for turn
            had_error: Whether turn had an error
            had_tool_call: Whether turn had a tool call
        """
        self._turn_count += 1
        self._sample_count += 1

        if had_tool_call:
            self._tool_call_count += 1

        # Add turn timing
        timing = TurnTimingData(
            turn_number=turn_number,
            duration_ms=duration_ms,
            token_count=token_count,
            had_error=had_error,
            had_tool_call=had_tool_call,
        )
        self._turn_timings.append(timing)

        # Trim to max
        if len(self._turn_timings) > self.MAX_TURN_TIMINGS:
            self._turn_timings = self._turn_timings[-self.MAX_TURN_TIMINGS :]

        # Record latency
        self.record_latency(duration_ms)

        # Update summary
        if self._turn_count > 0:
            self._summary.tool_call_rate = self._tool_call_count / self._turn_count
            self._summary.avg_response_length = self._tokens.output_tokens // self._turn_count

        self._touch()

    def get_turn_timings(self) -> list[TurnTimingData]:
        """Get recent turn timings."""
        return list(self._turn_timings)

    def get_turn_count(self) -> int:
        """Get total turn count."""
        return self._turn_count

    # -------------------------------------------------------------------------
    # Error API
    # -------------------------------------------------------------------------

    def get_errors(self) -> ErrorData:
        """Get error metrics."""
        return self._errors

    def record_error(
        self,
        error_type: ErrorType,
        turn_number: int,
        message: str = "",
    ) -> None:
        """
        Record an error.

        Args:
            error_type: Type of error
            turn_number: Turn where error occurred
            message: Error message (truncated to 200 chars)
        """
        self._errors.total_errors += 1
        self._errors.last_error_turn = turn_number
        self._errors.last_error_message = message[:200]

        # Increment by type
        if error_type == ErrorType.TIMEOUT:
            self._errors.timeout_errors += 1
        elif error_type == ErrorType.RATE_LIMIT:
            self._errors.rate_limit_errors += 1
        elif error_type == ErrorType.MODEL:
            self._errors.model_errors += 1
        elif error_type == ErrorType.TOOL:
            self._errors.tool_errors += 1
        elif error_type == ErrorType.VALIDATION:
            self._errors.validation_errors += 1

        # Update error rate
        if self._turn_count > 0:
            self._errors.error_rate = self._errors.total_errors / self._turn_count
            self._summary.error_rate = self._errors.error_rate

        self._touch()

    # -------------------------------------------------------------------------
    # Summary API
    # -------------------------------------------------------------------------

    def get_summary(self) -> SummaryData:
        """Get performance summary."""
        return self._summary

    def set_budget_sla_met(self, met: bool) -> None:
        """Set budget SLA status."""
        self._summary.budget_sla_met = met
        self._touch()

    # -------------------------------------------------------------------------
    # Statistics
    # -------------------------------------------------------------------------

    def get_statistics(self) -> dict[str, Any]:
        """Get section statistics."""
        return {
            "turn_count": self._turn_count,
            "sample_count": self._sample_count,
            "tool_call_count": self._tool_call_count,
            "total_tokens": self._tokens.total_tokens,
            "total_cost_usd": self.get_total_cost_usd(),
            "avg_latency_ms": self._summary.avg_latency_ms,
            "p95_latency_ms": self._latency.p95_ms,
            "error_rate": self._errors.error_rate,
            "latency_sla_met": self._summary.latency_sla_met,
            "budget_sla_met": self._summary.budget_sla_met,
            "turn_timings_count": len(self._turn_timings),
            "latency_samples_count": len(self._latency_samples),
            "collection_started_ms": self._collection_started_ms,
            "last_updated_ms": self._last_updated_ms,
        }

    # -------------------------------------------------------------------------
    # Integrity
    # -------------------------------------------------------------------------

    def compute_integrity(self) -> str:
        """Compute integrity hash."""
        content = (
            f"{self._tokens.total_tokens}:"
            f"{self._cost.total_cost_microdollars}:"
            f"{self._latency.p95_ms}:"
            f"{self._errors.total_errors}:"
            f"{self._turn_count}:"
            f"{self._sample_count}"
        )
        return hashlib.sha256(content.encode()).hexdigest()

    def update_integrity(self) -> None:
        """Update stored integrity hash."""
        self._integrity_hash = self.compute_integrity()

    def verify_integrity(self) -> bool:
        """Verify integrity hash matches."""
        if not self._integrity_hash:
            return True
        return self._integrity_hash == self.compute_integrity()

    # -------------------------------------------------------------------------
    # Internal
    # -------------------------------------------------------------------------

    def _touch(self) -> None:
        """Update timestamp and invalidate cache."""
        self._last_updated_ms = int(time.time() * 1000)
        self._invalidate_cache()

    def _invalidate_cache(self) -> None:
        """Invalidate FlatBuffer cache."""
        self._cached_flatbuffer = None

    # -------------------------------------------------------------------------
    # FlatBuffer Serialization
    # -------------------------------------------------------------------------

    def to_flatbuffer(self) -> bytes:
        """Serialize to FlatBuffer bytes."""
        if self._cached_flatbuffer is not None:
            return self._cached_flatbuffer

        builder = flatbuffers.Builder(2048)

        # Build strings
        section_name = builder.CreateString(self.SECTION_NAME)
        error_msg = builder.CreateString(self._errors.last_error_message)

        # Build TokenMetrics
        TokenMetricsStart(builder)
        TokenMetricsAddInputTokens(builder, self._tokens.input_tokens)
        TokenMetricsAddOutputTokens(builder, self._tokens.output_tokens)
        TokenMetricsAddTotalTokens(builder, self._tokens.total_tokens)
        TokenMetricsAddReasoningTokens(builder, self._tokens.reasoning_tokens)
        TokenMetricsAddGenerationTokens(builder, self._tokens.generation_tokens)
        TokenMetricsAddEmbeddingTokens(builder, self._tokens.embedding_tokens)
        TokenMetricsAddAvgInputPerTurn(builder, self._tokens.avg_input_per_turn)
        TokenMetricsAddAvgOutputPerTurn(builder, self._tokens.avg_output_per_turn)
        tokens_offset = TokenMetricsEnd(builder)

        # Build CostMetrics
        CostMetricsStart(builder)
        CostMetricsAddTotalCostMicrodollars(builder, self._cost.total_cost_microdollars)
        CostMetricsAddReasoningCost(builder, self._cost.reasoning_cost)
        CostMetricsAddGenerationCost(builder, self._cost.generation_cost)
        CostMetricsAddEmbeddingCost(builder, self._cost.embedding_cost)
        CostMetricsAddToolCost(builder, self._cost.tool_cost)
        CostMetricsAddAvgCostPerTurn(builder, self._cost.avg_cost_per_turn)
        cost_offset = CostMetricsEnd(builder)

        # Build LatencyMetrics
        LatencyMetricsStart(builder)
        LatencyMetricsAddP50Ms(builder, self._latency.p50_ms)
        LatencyMetricsAddP90Ms(builder, self._latency.p90_ms)
        LatencyMetricsAddP95Ms(builder, self._latency.p95_ms)
        LatencyMetricsAddP99Ms(builder, self._latency.p99_ms)
        LatencyMetricsAddMinMs(builder, self._latency.min_ms)
        LatencyMetricsAddMaxMs(builder, self._latency.max_ms)
        LatencyMetricsAddModelLatencyP50Ms(builder, self._latency.model_latency_p50_ms)
        LatencyMetricsAddRetrievalLatencyP50Ms(builder, self._latency.retrieval_latency_p50_ms)
        LatencyMetricsAddToolLatencyP50Ms(builder, self._latency.tool_latency_p50_ms)
        LatencyMetricsAddOrchestrationLatencyP50Ms(
            builder, self._latency.orchestration_latency_p50_ms
        )
        latency_offset = LatencyMetricsEnd(builder)

        # Build TurnTimings vector
        timing_offsets = []
        for timing in self._turn_timings:
            TurnTimingStart(builder)
            TurnTimingAddTurnNumber(builder, timing.turn_number)
            TurnTimingAddDurationMs(builder, timing.duration_ms)
            TurnTimingAddTokenCount(builder, timing.token_count)
            TurnTimingAddHadError(builder, timing.had_error)
            TurnTimingAddHadToolCall(builder, timing.had_tool_call)
            timing_offsets.append(TurnTimingEnd(builder))

        TelemetrySectionStartTurnTimingsVector(builder, len(timing_offsets))
        for offset in reversed(timing_offsets):
            builder.PrependUOffsetTRelative(offset)
        timings_vector = builder.EndVector()

        # Build ErrorMetrics
        ErrorMetricsStart(builder)
        ErrorMetricsAddTotalErrors(builder, self._errors.total_errors)
        ErrorMetricsAddTimeoutErrors(builder, self._errors.timeout_errors)
        ErrorMetricsAddRateLimitErrors(builder, self._errors.rate_limit_errors)
        ErrorMetricsAddModelErrors(builder, self._errors.model_errors)
        ErrorMetricsAddToolErrors(builder, self._errors.tool_errors)
        ErrorMetricsAddValidationErrors(builder, self._errors.validation_errors)
        ErrorMetricsAddLastErrorTurn(builder, self._errors.last_error_turn)
        ErrorMetricsAddLastErrorMessage(builder, error_msg)
        ErrorMetricsAddErrorRate(builder, self._errors.error_rate)
        errors_offset = ErrorMetricsEnd(builder)

        # Build PerformanceSummary
        PerformanceSummaryStart(builder)
        PerformanceSummaryAddAvgLatencyMs(builder, self._summary.avg_latency_ms)
        PerformanceSummaryAddErrorRate(builder, self._summary.error_rate)
        PerformanceSummaryAddCostPerTurn(builder, self._summary.cost_per_turn)
        PerformanceSummaryAddAvgResponseLength(builder, self._summary.avg_response_length)
        PerformanceSummaryAddToolCallRate(builder, self._summary.tool_call_rate)
        PerformanceSummaryAddLatencySlaMet(builder, self._summary.latency_sla_met)
        PerformanceSummaryAddBudgetSlaMet(builder, self._summary.budget_sla_met)
        summary_offset = PerformanceSummaryEnd(builder)

        # Build SectionHeader
        SectionHeaderStart(builder)
        SectionHeaderAddSectionName(builder, section_name)
        SectionHeaderAddSizeBytes(builder, self.get_size_bytes())
        SectionHeaderAddLastUpdatedMs(builder, self._last_updated_ms)
        SectionHeaderAddChecksum(builder, hash(self._integrity_hash) & 0xFFFFFFFF)
        header_offset = SectionHeaderEnd(builder)

        # Build TelemetrySection
        TelemetrySectionStart(builder)
        TelemetrySectionAddHeader(builder, header_offset)
        TelemetrySectionAddTokens(builder, tokens_offset)
        TelemetrySectionAddCost(builder, cost_offset)
        TelemetrySectionAddLatency(builder, latency_offset)
        TelemetrySectionAddTurnTimings(builder, timings_vector)
        TelemetrySectionAddErrors(builder, errors_offset)
        TelemetrySectionAddSummary(builder, summary_offset)
        TelemetrySectionAddSampleCount(builder, self._sample_count)
        section_offset = TelemetrySectionEnd(builder)

        builder.Finish(section_offset)
        self._cached_flatbuffer = bytes(builder.Output())
        return self._cached_flatbuffer

    def from_flatbuffer(self, data: bytes) -> None:
        """Deserialize from FlatBuffer bytes (in-place mutation)."""
        fb = FBTelemetrySection.GetRootAsTelemetrySection(data, 0)

        # Restore tokens
        tokens = fb.Tokens()
        if tokens:
            self._tokens = TokenData(
                input_tokens=tokens.InputTokens(),
                output_tokens=tokens.OutputTokens(),
                total_tokens=tokens.TotalTokens(),
                reasoning_tokens=tokens.ReasoningTokens(),
                generation_tokens=tokens.GenerationTokens(),
                embedding_tokens=tokens.EmbeddingTokens(),
                avg_input_per_turn=tokens.AvgInputPerTurn(),
                avg_output_per_turn=tokens.AvgOutputPerTurn(),
            )

        # Restore cost
        cost = fb.Cost()
        if cost:
            self._cost = CostData(
                total_cost_microdollars=cost.TotalCostMicrodollars(),
                reasoning_cost=cost.ReasoningCost(),
                generation_cost=cost.GenerationCost(),
                embedding_cost=cost.EmbeddingCost(),
                tool_cost=cost.ToolCost(),
                avg_cost_per_turn=cost.AvgCostPerTurn(),
            )

        # Restore latency
        latency = fb.Latency()
        if latency:
            self._latency = LatencyData(
                p50_ms=latency.P50Ms(),
                p90_ms=latency.P90Ms(),
                p95_ms=latency.P95Ms(),
                p99_ms=latency.P99Ms(),
                min_ms=latency.MinMs(),
                max_ms=latency.MaxMs(),
                model_latency_p50_ms=latency.ModelLatencyP50Ms(),
                retrieval_latency_p50_ms=latency.RetrievalLatencyP50Ms(),
                tool_latency_p50_ms=latency.ToolLatencyP50Ms(),
                orchestration_latency_p50_ms=latency.OrchestrationLatencyP50Ms(),
            )

        # Restore turn timings
        self._turn_timings.clear()
        for i in range(fb.TurnTimingsLength()):
            timing = fb.TurnTimings(i)
            if timing:
                self._turn_timings.append(
                    TurnTimingData(
                        turn_number=timing.TurnNumber(),
                        duration_ms=timing.DurationMs(),
                        token_count=timing.TokenCount(),
                        had_error=timing.HadError(),
                        had_tool_call=timing.HadToolCall(),
                    )
                )

        # Restore errors
        errors = fb.Errors()
        if errors:
            error_msg = errors.LastErrorMessage()
            self._errors = ErrorData(
                total_errors=errors.TotalErrors(),
                timeout_errors=errors.TimeoutErrors(),
                rate_limit_errors=errors.RateLimitErrors(),
                model_errors=errors.ModelErrors(),
                tool_errors=errors.ToolErrors(),
                validation_errors=errors.ValidationErrors(),
                last_error_turn=errors.LastErrorTurn(),
                last_error_message=error_msg.decode() if error_msg else "",
                error_rate=errors.ErrorRate(),
            )

        # Restore summary
        summary = fb.Summary()
        if summary:
            self._summary = SummaryData(
                avg_latency_ms=summary.AvgLatencyMs(),
                error_rate=summary.ErrorRate(),
                cost_per_turn=summary.CostPerTurn(),
                avg_response_length=summary.AvgResponseLength(),
                tool_call_rate=summary.ToolCallRate(),
                latency_sla_met=summary.LatencySlaMet(),
                budget_sla_met=summary.BudgetSlaMet(),
            )

        # Restore metadata
        self._sample_count = fb.SampleCount()

        # Restore header metadata
        header = fb.Header()
        if header:
            self._last_updated_ms = header.LastUpdatedMs()

        # Invalidate cache
        self._cached_flatbuffer = None

    # -------------------------------------------------------------------------
    # Apply (MutationGuard pattern)
    # -------------------------------------------------------------------------

    def apply(self, operation: str, args: dict[str, Any]) -> Any:
        """
        Apply mutation operation.

        Supported operations:
        - record_tokens
        - record_cost
        - record_latency
        - record_turn
        - record_error
        - set_budget_sla_met
        - evict_partial
        - clear

        Args:
            operation: Operation name
            args: Operation arguments

        Returns:
            Operation result
        """
        if operation == "record_tokens":
            self.record_tokens(
                input_tokens=args.get("input_tokens", 0),
                output_tokens=args.get("output_tokens", 0),
                reasoning_tokens=args.get("reasoning_tokens", 0),
                generation_tokens=args.get("generation_tokens", 0),
                embedding_tokens=args.get("embedding_tokens", 0),
            )
            return None

        if operation == "record_cost":
            self.record_cost(
                cost_microdollars=args.get("cost_microdollars", 0),
                reasoning_cost=args.get("reasoning_cost", 0),
                generation_cost=args.get("generation_cost", 0),
                embedding_cost=args.get("embedding_cost", 0),
                tool_cost=args.get("tool_cost", 0),
            )
            return None

        if operation == "record_latency":
            self.record_latency(
                duration_ms=args.get("duration_ms", 0),
                model_latency_ms=args.get("model_latency_ms", 0),
                retrieval_latency_ms=args.get("retrieval_latency_ms", 0),
                tool_latency_ms=args.get("tool_latency_ms", 0),
                orchestration_latency_ms=args.get("orchestration_latency_ms", 0),
            )
            return None

        if operation == "record_turn":
            self.record_turn(
                turn_number=args.get("turn_number", 0),
                duration_ms=args.get("duration_ms", 0),
                token_count=args.get("token_count", 0),
                had_error=args.get("had_error", False),
                had_tool_call=args.get("had_tool_call", False),
            )
            return None

        if operation == "record_error":
            error_type = args.get("error_type", ErrorType.OTHER)
            if isinstance(error_type, int):
                error_type = ErrorType(error_type)
            self.record_error(
                error_type=error_type,
                turn_number=args.get("turn_number", 0),
                message=args.get("message", ""),
            )
            return None

        if operation == "set_budget_sla_met":
            self.set_budget_sla_met(args.get("met", True))
            return None

        if operation == "evict_partial":
            return self.evict_partial(target_kb=args.get("target_kb", 0.5))

        if operation == "clear":
            self.clear()
            return None

        raise ValueError(f"Unknown operation: {operation}")

    # -------------------------------------------------------------------------
    # Magic Methods
    # -------------------------------------------------------------------------

    def __repr__(self) -> str:
        """Return string representation."""
        return (
            f"TelemetrySection(turns={self._turn_count}, "
            f"tokens={self._tokens.total_tokens}, "
            f"cost=${self.get_total_cost_usd():.4f}, "
            f"p95={self._latency.p95_ms}ms, "
            f"errors={self._errors.total_errors})"
        )

    def __len__(self) -> int:
        """Return turn timing count."""
        return len(self._turn_timings)


# =============================================================================
# Factory
# =============================================================================


def create_telemetry_section() -> TelemetrySection:
    """Create new TelemetrySection."""
    return TelemetrySection()
    return TelemetrySection()
