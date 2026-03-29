"""Phase 2: Proxy Ground Truth Labeling.

Assigns proxy importance tiers to events using safety_familyos + hub_routing
as weak supervision signals. These are NOT perfect labels -- they are
directional proxies sufficient for weight research.

Tier hierarchy (6 levels):
  CRITICAL > HIGH > MEDIUM_HIGH > MEDIUM > LOW_MEDIUM > LOW
"""

from __future__ import annotations

from typing import Any, Dict

# Ordered from highest to lowest for comparison
TIER_ORDER = {
    "CRITICAL": 6,
    "HIGH": 5,
    "MEDIUM_HIGH": 4,
    "MEDIUM": 3,
    "LOW_MEDIUM": 2,
    "LOW": 1,
}


def assign_proxy_tier(event: Dict[str, Any]) -> str:
    """Assign a proxy importance tier from safety + hub_routing signals.

    Rules (evaluated top-down, first match wins):
      CRITICAL:    safety = CRISIS
      HIGH:        safety = RED
                   OR (safety = AMBER AND EMO AND very_negative sentiment)
      MEDIUM_HIGH: EMO + REL + MEM all true
      MEDIUM:      EMO + (REL or MEM)
      LOW_MEDIUM:  EMO only AND sentiment != neutral
      LOW:         everything else
    """
    tasks = event.get("tasks", {})
    routing = event.get("hub_routing", {})

    safety = tasks.get("safety_familyos", "GREEN")
    sentiment = tasks.get("sentiment", "neutral")
    emo = routing.get("EMO", False)
    rel = routing.get("REL", False)
    mem = routing.get("MEM", False)
    task = routing.get("TASK", False)
    emotion_count = len(tasks.get("emotions", []))

    # --- CRITICAL ---
    if safety == "CRISIS":
        return "CRITICAL"

    # --- HIGH ---
    if safety == "RED":
        return "HIGH"
    if safety == "AMBER" and emo and sentiment == "very_negative":
        return "HIGH"

    # --- MEDIUM_HIGH ---
    # Triple-routed: emotional + relational + memory-worthy
    if emo and rel and mem:
        return "MEDIUM_HIGH"

    # Highly emotional AMBER events (not very_negative, but still flagged)
    if safety == "AMBER" and emo and emotion_count >= 4:
        return "MEDIUM_HIGH"

    # --- MEDIUM ---
    # Dual-routed: emotional + one context signal
    if emo and (rel or mem):
        return "MEDIUM"

    # TASK + emotional (planning with feelings)
    if emo and task:
        return "MEDIUM"

    # --- LOW_MEDIUM ---
    # Emotional only, non-neutral
    if emo and sentiment != "neutral":
        return "LOW_MEDIUM"

    # MEM-routed but not emotional (memory recall / query)
    if mem and not emo:
        return "LOW_MEDIUM"

    # --- LOW ---
    return "LOW"
