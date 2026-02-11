"""
k1.bus.timing -- Deadline-agnostic ordering enforcement package.

Provides:
    TimingConfig         Topic-prefix to DeliveryMode resolution
    TimingChain          Causal + sequence ordering enforcement engine
    TimingStats          Observable timing chain statistics
    default_timing_config   Default K1 prefix rules factory
    DEFAULT_RULES        Raw default prefix -> DeliveryMode map
    DEFAULT_MODE         Fallback mode for unmatched prefixes
"""

from k1.bus.timing.defaults import DEFAULT_MODE, DEFAULT_RULES, default_timing_config
from k1.bus.timing.timing_chain import TimingChain, TimingStats
from k1.bus.timing.timing_config import TimingConfig

__all__ = [
    "TimingConfig",
    "TimingChain",
    "TimingStats",
    "default_timing_config",
    "DEFAULT_RULES",
    "DEFAULT_MODE",
]
