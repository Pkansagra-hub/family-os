"""
k1.concierge.experience.anticipatory_responder -- AnticipatoryResponder stub.

Pre-computes likely next user requests based on patterns.

V2 Design Ref: Section 12.3.4

Fire cadence: every 30th turn_end (enforced by ExperienceLayer.tick()).
Budget: 15 ms.
Reads: task state, user behavior patterns (from SS + memory).
Writes: Anticipation emitted on bus.

Pluggability:
  - Future: intent prediction models, sequential pattern mining,
    context-aware capability pre-warming.
  - Integration (prompt): DynamicPromptBuilder injects
    suggested_prompt_hint into Front's prompt when confidence > 0.5.
  - Integration (ReAct loop): pre_fetch_capabilities list is passed
    to ToolDispatcher to pre-warm Fabric connections for predicted
    capabilities.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Anticipation:
    """Output of AnticipatoryResponder. Two integration points:
    1. DynamicPromptBuilder: inject anticipation hint into prompt
    2. ReAct loop: pre-warm predicted tool schemas (future)
    """

    predicted_intent: str = ""  # What user likely wants next
    confidence: float = 0.0  # 0.0 = no prediction (stub)
    pre_fetch_capabilities: list[str] = field(default_factory=list)
    suggested_prompt_hint: str = ""  # Optional hint injected into Front prompt


class AnticipatoryResponder:
    """Pre-computes likely next user requests based on patterns.

    Fire cadence: every 30th turn_end.
    Budget: 15 ms.
    Reads: task state, user behavior patterns (from SS + memory).
    Writes: Anticipation emitted on bus.

    Pluggability:
      - Future: intent prediction models, sequential pattern mining,
        context-aware capability pre-warming.
      - Integration (prompt): DynamicPromptBuilder injects
        suggested_prompt_hint into Front's prompt when confidence > 0.5.
        This lets the LLM proactively offer the predicted next step.
      - Integration (ReAct loop): pre_fetch_capabilities list is passed
        to ToolDispatcher to pre-warm Fabric connections for predicted
        capabilities. This reduces latency if the prediction is correct.
        No wasted work if incorrect -- pre-warming is speculative only.
    """

    async def anticipate(
        self,
        task_state: dict,
        user_patterns: dict,
    ) -> Anticipation:
        """Heuristic intent prediction (M6 E6.1).

        Conservative -- no LLM, no external IO, 15ms budget.

        Activation criteria: `user_patterns["recent_intents"]` is a list
        with at least 2 string entries.  Confidence is derived from the
        repetition rate of the most-recent intent.  Lacking signal,
        returns defaults (`Anticipation()`).

        Optional `user_patterns["capabilities_for_intent"]` is a dict
        mapping intent -> list[str] of capabilities to pre-warm.
        """
        if not isinstance(user_patterns, dict):
            return Anticipation()

        intents = user_patterns.get("recent_intents")
        if not isinstance(intents, list) or len(intents) < 2:
            return Anticipation()

        last = intents[-1]
        if not isinstance(last, str) or not last:
            return Anticipation()

        repeats = sum(1 for i in intents if i == last)
        confidence = float(min(0.9, repeats / max(1, len(intents))))

        cap_map = user_patterns.get("capabilities_for_intent")
        capabilities: list[str] = []
        if isinstance(cap_map, dict):
            raw = cap_map.get(last)
            if isinstance(raw, list):
                capabilities = [c for c in raw if isinstance(c, str)]

        return Anticipation(
            predicted_intent=last,
            confidence=confidence,
            pre_fetch_capabilities=capabilities,
            suggested_prompt_hint=f"User may want '{last}' next",
        )
