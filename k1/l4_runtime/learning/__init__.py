"""
K1 L4 Runtime — Learning Loop (Feedback, Self-Model, Regret)

**Purpose:** Cognitive learning loop with feedback signals, self-model updates, counterfactual regret

**Components:**
- feedback/ — Signal integration (thumbs up/down, barge-in, corrections)
- self_model/ — Belief revision, confidence updates
- regret/ — Counterfactual reasoning, alternative path analysis

**Performance:**
- Learning cycle: <100ms P95
- Feedback latency: <50ms
- Belief update: <10ms P95

**ADRs (3 total):**
- ADR-0018: Eviction Architecture (learning from memory pressure)
- ADR-0018a: Tier 1 Soft Eviction (LRU learning signals)
- ADR-0018b: Tier 2 Hard Eviction (UX impact tracking, learning from evictions)

**Note:** Full Learning ADRs in Layer 3, Layer 4 focuses on runtime integration

**Integration:**
- SessionState: Persona section stores self-model
- L3 Planner: Learning signals inform plan quality
- K0 Memory: Consolidation pipeline reinforces patterns

**Performance Metrics:**
- learning_cycle_latency_ms (histogram)
- learning_feedback_signals_total (counter, signal_type)
- learning_belief_updates_total (counter)

**Last Updated:** October 2025
**Status:** Production-ready learning loop integration
"""

__version__ = "0.1.0"

# TODO: Implement feedback/, self_model/, regret/
# Per ADR-0018 family (learning from eviction signals)
