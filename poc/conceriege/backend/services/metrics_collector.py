"""
Metrics Collector Service

Tracks performance metrics for conversation turns, LLM calls, and specialist operations.
Provides statistical analysis (P50/P95/P99) and summary reports.

Research basis:
- Performance monitoring best practices (Beyer et al. 2016 - SRE Book)
- Latency percentile tracking (Dean & Barroso 2013 - The Tail at Scale)
"""

import statistics
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class LLMMetrics:
    """Metrics for LLM API calls."""

    total_calls: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    cache_hits: int = 0
    cache_misses: int = 0
    latencies: List[float] = field(default_factory=list)

    @property
    def avg_latency_ms(self) -> float:
        """Calculate average latency."""
        return statistics.mean(self.latencies) if self.latencies else 0.0

    @property
    def cache_hit_rate(self) -> float:
        """Calculate cache hit rate."""
        total = self.cache_hits + self.cache_misses
        return (self.cache_hits / total * 100) if total > 0 else 0.0

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "total_calls": self.total_calls,
            "total_tokens": self.total_tokens,
            "total_cost_usd": round(self.total_cost_usd, 4),
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "avg_latency_ms": round(self.avg_latency_ms, 2),
            "cache_hit_rate": round(self.cache_hit_rate, 2),
        }


@dataclass
class SpecialistMetrics:
    """Metrics for specialist agent operations."""

    total_calls: int = 0
    durations: List[float] = field(default_factory=list)

    @property
    def avg_duration_ms(self) -> float:
        """Calculate average duration."""
        return statistics.mean(self.durations) if self.durations else 0.0

    @property
    def p95_duration_ms(self) -> float:
        """Calculate P95 duration."""
        if not self.durations:
            return 0.0
        sorted_durations = sorted(self.durations)
        index = int(len(sorted_durations) * 0.95)
        return sorted_durations[index] if index < len(sorted_durations) else sorted_durations[-1]

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "total_calls": self.total_calls,
            "avg_duration_ms": round(self.avg_duration_ms, 2),
            "p95_duration_ms": round(self.p95_duration_ms, 2),
        }


@dataclass
class TurnMetrics:
    """Metrics for conversation turns."""

    total_turns: int = 0
    latencies: List[float] = field(default_factory=list)
    budget_exceeded_count: int = 0

    @property
    def avg_latency_ms(self) -> float:
        """Calculate average latency."""
        return statistics.mean(self.latencies) if self.latencies else 0.0

    @property
    def p50_latency_ms(self) -> float:
        """Calculate P50 (median) latency."""
        return statistics.median(self.latencies) if self.latencies else 0.0

    @property
    def p95_latency_ms(self) -> float:
        """Calculate P95 latency."""
        if not self.latencies:
            return 0.0
        sorted_latencies = sorted(self.latencies)
        index = int(len(sorted_latencies) * 0.95)
        return sorted_latencies[index] if index < len(sorted_latencies) else sorted_latencies[-1]

    @property
    def p99_latency_ms(self) -> float:
        """Calculate P99 latency."""
        if not self.latencies:
            return 0.0
        sorted_latencies = sorted(self.latencies)
        index = int(len(sorted_latencies) * 0.99)
        return sorted_latencies[index] if index < len(sorted_latencies) else sorted_latencies[-1]

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "total_turns": self.total_turns,
            "avg_latency_ms": round(self.avg_latency_ms, 2),
            "p50_latency_ms": round(self.p50_latency_ms, 2),
            "p95_latency_ms": round(self.p95_latency_ms, 2),
            "p99_latency_ms": round(self.p99_latency_ms, 2),
            "budget_exceeded_count": self.budget_exceeded_count,
        }


@dataclass
class ProactiveMetrics:
    """Metrics for proactive prompts."""

    prompts_sent: int = 0
    user_responses: int = 0

    @property
    def response_rate(self) -> float:
        """Calculate user response rate."""
        return (self.user_responses / self.prompts_sent * 100) if self.prompts_sent > 0 else 0.0

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "prompts_sent": self.prompts_sent,
            "user_responses": self.user_responses,
            "response_rate": round(self.response_rate, 2),
        }


class MetricsCollector:
    """
    Collects and tracks performance metrics for the Concierge system.

    Tracks:
    - LLM API calls (latency, tokens, cost, cache hits)
    - Specialist operations (duration, P95)
    - Conversation turns (E2E latency, P50/P95/P99)
    - Proactive prompts (sent, responses, response rate)

    Attributes:
        latency_budget_ms: Maximum allowed latency per turn (default: 1500ms)
        _llm_metrics: Metrics for LLM operations by operation type
        _specialist_metrics: Metrics for specialist operations by type
        _turn_metrics: Metrics for conversation turns
        _proactive_metrics: Metrics for proactive prompts
    """

    def __init__(self, latency_budget_ms: int = 1500):
        """
        Initialize metrics collector.

        Args:
            latency_budget_ms: Maximum allowed latency per turn
        """
        self.latency_budget_ms = latency_budget_ms

        # Metrics storage
        self._llm_metrics: Dict[str, LLMMetrics] = {}
        self._specialist_metrics: Dict[str, SpecialistMetrics] = {}
        self._turn_metrics = TurnMetrics()
        self._proactive_metrics = ProactiveMetrics()

    def record_llm_call(
        self,
        operation: str,
        model: str,
        latency_ms: float,
        tokens: int,
        cost_usd: float,
        cache_hit: bool = False,
    ) -> None:
        """
        Record LLM API call metrics.

        Args:
            operation: Operation type (e.g., "intent_classification", "empathy_generation")
            model: Model used (e.g., "gpt-4o-mini")
            latency_ms: Call latency in milliseconds
            tokens: Number of tokens used
            cost_usd: Cost in USD
            cache_hit: Whether this was a cache hit
        """
        # Get or create metrics for this operation
        if operation not in self._llm_metrics:
            self._llm_metrics[operation] = LLMMetrics()

        metrics = self._llm_metrics[operation]

        # Update metrics
        metrics.total_calls += 1
        metrics.total_tokens += tokens
        metrics.total_cost_usd += cost_usd
        metrics.latencies.append(latency_ms)

        if cache_hit:
            metrics.cache_hits += 1
        else:
            metrics.cache_misses += 1

    def record_specialist_duration(self, specialist_type: str, duration_ms: float) -> None:
        """
        Record specialist operation duration.

        Args:
            specialist_type: Type of specialist (e.g., "nutritionist", "psychiatrist")
            duration_ms: Operation duration in milliseconds
        """
        # Get or create metrics for this specialist
        if specialist_type not in self._specialist_metrics:
            self._specialist_metrics[specialist_type] = SpecialistMetrics()

        metrics = self._specialist_metrics[specialist_type]

        # Update metrics
        metrics.total_calls += 1
        metrics.durations.append(duration_ms)

    def record_turn_latency(self, total_ms: float) -> None:
        """
        Record end-to-end conversation turn latency.

        Args:
            total_ms: Total turn latency in milliseconds
        """
        self._turn_metrics.total_turns += 1
        self._turn_metrics.latencies.append(total_ms)

        # Check if budget exceeded
        if total_ms > self.latency_budget_ms:
            self._turn_metrics.budget_exceeded_count += 1

    def record_proactive_prompt(self, user_responded: bool = False) -> None:
        """
        Record proactive prompt sent.

        Args:
            user_responded: Whether user responded to the prompt
        """
        self._proactive_metrics.prompts_sent += 1

        if user_responded:
            self._proactive_metrics.user_responses += 1

    def get_metrics(self) -> dict:
        """
        Get all collected metrics.

        Returns:
            Dictionary with all metrics organized by category
        """
        return {
            "llm": {op: metrics.to_dict() for op, metrics in self._llm_metrics.items()},
            "specialist": {
                sp: metrics.to_dict() for sp, metrics in self._specialist_metrics.items()
            },
            "turns": self._turn_metrics.to_dict(),
            "proactive": self._proactive_metrics.to_dict(),
        }

    def get_summary(self) -> dict:
        """
        Get high-level summary with key statistics.

        Returns:
            Dictionary with summary statistics
        """
        # Calculate total LLM metrics
        total_llm_calls = sum(m.total_calls for m in self._llm_metrics.values())
        total_llm_cost = sum(m.total_cost_usd for m in self._llm_metrics.values())
        total_llm_tokens = sum(m.total_tokens for m in self._llm_metrics.values())

        # Calculate average cache hit rate
        total_cache_hits = sum(m.cache_hits for m in self._llm_metrics.values())
        total_cache_misses = sum(m.cache_misses for m in self._llm_metrics.values())
        total_cache_requests = total_cache_hits + total_cache_misses
        overall_cache_hit_rate = (
            (total_cache_hits / total_cache_requests * 100) if total_cache_requests > 0 else 0.0
        )

        # Calculate total specialist calls
        total_specialist_calls = sum(m.total_calls for m in self._specialist_metrics.values())

        return {
            "llm_summary": {
                "total_calls": total_llm_calls,
                "total_tokens": total_llm_tokens,
                "total_cost_usd": round(total_llm_cost, 4),
                "cache_hit_rate": round(overall_cache_hit_rate, 2),
            },
            "specialist_summary": {"total_calls": total_specialist_calls},
            "turn_summary": {
                "total_turns": self._turn_metrics.total_turns,
                "p50_latency_ms": round(self._turn_metrics.p50_latency_ms, 2),
                "p95_latency_ms": round(self._turn_metrics.p95_latency_ms, 2),
                "p99_latency_ms": round(self._turn_metrics.p99_latency_ms, 2),
                "budget_exceeded_count": self._turn_metrics.budget_exceeded_count,
                "budget_exceeded_rate": round(
                    (
                        (
                            self._turn_metrics.budget_exceeded_count
                            / self._turn_metrics.total_turns
                            * 100
                        )
                        if self._turn_metrics.total_turns > 0
                        else 0.0
                    ),
                    2,
                ),
            },
            "proactive_summary": {
                "prompts_sent": self._proactive_metrics.prompts_sent,
                "response_rate": round(self._proactive_metrics.response_rate, 2),
            },
        }

    def export_prometheus(self) -> str:
        """
        Export metrics in Prometheus format.

        Returns:
            Prometheus-formatted metrics string
        """
        lines = []

        # LLM metrics
        for operation, metrics in self._llm_metrics.items():
            lines.append(f"# HELP llm_calls_total Total LLM calls for {operation}")
            lines.append("# TYPE llm_calls_total counter")
            lines.append(f'llm_calls_total{{operation="{operation}"}} {metrics.total_calls}')

            lines.append(f"# HELP llm_tokens_total Total tokens used for {operation}")
            lines.append("# TYPE llm_tokens_total counter")
            lines.append(f'llm_tokens_total{{operation="{operation}"}} {metrics.total_tokens}')

            lines.append(f"# HELP llm_cost_usd_total Total cost in USD for {operation}")
            lines.append("# TYPE llm_cost_usd_total counter")
            lines.append(
                f'llm_cost_usd_total{{operation="{operation}"}} {metrics.total_cost_usd:.4f}'
            )

            lines.append(f"# HELP llm_latency_ms Average latency for {operation}")
            lines.append("# TYPE llm_latency_ms gauge")
            lines.append(f'llm_latency_ms{{operation="{operation}"}} {metrics.avg_latency_ms:.2f}')

        # Specialist metrics
        for specialist, metrics in self._specialist_metrics.items():
            lines.append(f"# HELP specialist_calls_total Total calls for {specialist}")
            lines.append("# TYPE specialist_calls_total counter")
            lines.append(
                f'specialist_calls_total{{specialist="{specialist}"}} {metrics.total_calls}'
            )

            lines.append(f"# HELP specialist_duration_ms Average duration for {specialist}")
            lines.append("# TYPE specialist_duration_ms gauge")
            lines.append(
                f'specialist_duration_ms{{specialist="{specialist}"}} {metrics.avg_duration_ms:.2f}'
            )

            lines.append(f"# HELP specialist_p95_duration_ms P95 duration for {specialist}")
            lines.append("# TYPE specialist_p95_duration_ms gauge")
            lines.append(
                f'specialist_p95_duration_ms{{specialist="{specialist}"}} {metrics.p95_duration_ms:.2f}'
            )

        # Turn metrics
        lines.append("# HELP turn_total Total conversation turns")
        lines.append("# TYPE turn_total counter")
        lines.append(f"turn_total {self._turn_metrics.total_turns}")

        lines.append("# HELP turn_latency_p50_ms P50 turn latency")
        lines.append("# TYPE turn_latency_p50_ms gauge")
        lines.append(f"turn_latency_p50_ms {self._turn_metrics.p50_latency_ms:.2f}")

        lines.append("# HELP turn_latency_p95_ms P95 turn latency")
        lines.append("# TYPE turn_latency_p95_ms gauge")
        lines.append(f"turn_latency_p95_ms {self._turn_metrics.p95_latency_ms:.2f}")

        lines.append("# HELP turn_latency_p99_ms P99 turn latency")
        lines.append("# TYPE turn_latency_p99_ms gauge")
        lines.append(f"turn_latency_p99_ms {self._turn_metrics.p99_latency_ms:.2f}")

        # Proactive metrics
        lines.append("# HELP proactive_prompts_sent_total Total proactive prompts sent")
        lines.append("# TYPE proactive_prompts_sent_total counter")
        lines.append(f"proactive_prompts_sent_total {self._proactive_metrics.prompts_sent}")

        lines.append("# HELP proactive_response_rate User response rate to proactive prompts")
        lines.append("# TYPE proactive_response_rate gauge")
        lines.append(f"proactive_response_rate {self._proactive_metrics.response_rate:.2f}")

        return "\n".join(lines)

    def reset(self) -> None:
        """Reset all metrics (useful for testing)."""
        self._llm_metrics.clear()
        self._specialist_metrics.clear()
        self._turn_metrics = TurnMetrics()
        self._proactive_metrics = ProactiveMetrics()


# Singleton instance for easy access across the application
_collector_instance: Optional[MetricsCollector] = None


def get_metrics_collector(latency_budget_ms: int = 1500) -> MetricsCollector:
    """
    Get singleton metrics collector instance.

    Args:
        latency_budget_ms: Maximum allowed latency (only used on first call)

    Returns:
        MetricsCollector singleton instance
    """
    global _collector_instance
    if _collector_instance is None:
        _collector_instance = MetricsCollector(latency_budget_ms=latency_budget_ms)
    return _collector_instance


def reset_metrics_collector() -> None:
    """
    Reset singleton instance (useful for testing).
    """
    global _collector_instance
    _collector_instance = None
