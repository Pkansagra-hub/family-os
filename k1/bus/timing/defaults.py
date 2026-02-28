"""
k1.bus.timing.defaults -- Default topic-prefix to DeliveryMode mapping.

These defaults encode the K1 cognitive architecture's ordering requirements:

    STRICT topics (correctness-critical, must arrive in order):
        - k1.capability     Agent capability negotiation
        - k1.orchestration  Multi-phase coordination
        - k1.planner        Plan sketch -> expand -> verify -> commit
        - k1.hil            Human-in-the-loop decisions
        - k1.response       Final responses to users
        - k1.session        Session state transitions
        - k1.agent          Agent state deltas (delta sub-topic)
        - k1.internal       Internal bus mechanics (weave batching)
        - k1.tool           Tool execution lifecycle events

    RELAXED topics (order-preferred but not critical):
        - k1.affect         Emotional/affect state updates
        - k1.constraint     Constraint propagation
        - k1.proactive      Proactive suggestions
        - k1.workflow       Workflow step events

    BEST_EFFORT topics (fire-and-forget, droppable):
        - k1.k0.sse         SSE bridge events from K0
        - k1.fabric.learning Learning loop feedback

The default for any unmatched prefix is RELAXED.

Usage::

    from k1.bus.timing.defaults import default_timing_config, DEFAULT_RULES

    config = default_timing_config()
"""

from __future__ import annotations

from k1.bus.envelope import DeliveryMode
from k1.bus.timing.timing_config import TimingConfig

# -----------------------------------------------------------------------
# Default prefix -> DeliveryMode rules
# -----------------------------------------------------------------------

DEFAULT_RULES: dict[str, DeliveryMode] = {
    # STRICT: correctness-critical ordering
    "k1.capability": DeliveryMode.STRICT,
    "k1.orchestration": DeliveryMode.STRICT,
    "k1.planner": DeliveryMode.STRICT,
    "k1.hil": DeliveryMode.STRICT,
    "k1.hitl": DeliveryMode.STRICT,
    "k1.response": DeliveryMode.STRICT,
    "k1.session": DeliveryMode.STRICT,
    "k1.agent": DeliveryMode.STRICT,
    "k1.internal": DeliveryMode.STRICT,
    "k1.tool": DeliveryMode.STRICT,
    "k1.arbiter": DeliveryMode.STRICT,
    "k1.backpool": DeliveryMode.STRICT,
    # RELAXED: order-preferred
    "k1.affect": DeliveryMode.RELAXED,
    "k1.constraint": DeliveryMode.RELAXED,
    "k1.proactive": DeliveryMode.RELAXED,
    "k1.workflow": DeliveryMode.RELAXED,
    # BEST_EFFORT: fire-and-forget
    "k1.k0.sse": DeliveryMode.BEST_EFFORT,
    "k1.fabric.learning": DeliveryMode.BEST_EFFORT,
}

DEFAULT_MODE = DeliveryMode.RELAXED


def default_timing_config() -> TimingConfig:
    """
    Create a TimingConfig with the standard K1 prefix rules.

    Returns:
        TimingConfig populated with DEFAULT_RULES and RELAXED default.
    """
    return TimingConfig(rules=DEFAULT_RULES, default=DEFAULT_MODE)
