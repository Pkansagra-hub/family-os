"""
k1.concierge.experience.narrative_weaver -- NarrativeWeaver stub.

Weaves narrative threads across turns for coherent storytelling.

V2 Design Ref: Section 12.3.3

Fire cadence: every 20th turn_end (enforced by ExperienceLayer.tick()).
Budget: 10 ms.
Reads: conversation history, memory recalls.
Writes: NarrativeContext emitted on bus.

Pluggability:
  - Future: multi-thread narrative tracking, salience decay,
    thread resumption suggestions, story arc detection.
  - Integration: DynamicPromptBuilder reads NarrativeContext
    for session_goal computation in Session Trajectory.
    NarrativeWeaver's weave_suggestion can influence Front's
    update_narrative() tool calls by providing thread context.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class NarrativeContext:
    """Output of NarrativeWeaver. Consumed by DynamicPromptBuilder Session Trajectory."""

    active_threads: list[str] = field(default_factory=list)
    thread_salience: dict[str, float] = field(default_factory=dict)
    weave_suggestion: str = ""  # Suggested narrative connection for next response


class NarrativeWeaver:
    """Weaves narrative threads across turns for coherent storytelling.

    Fire cadence: every 20th turn_end.
    Budget: 10 ms.
    Reads: conversation history, memory recalls.
    Writes: NarrativeContext emitted on bus.

    Pluggability:
      - Future: multi-thread narrative tracking, salience decay,
        thread resumption suggestions, story arc detection.
      - Integration: DynamicPromptBuilder reads NarrativeContext
        for session_goal computation in Session Trajectory.
        NarrativeWeaver's weave_suggestion can influence Front's
        update_narrative() tool calls by providing thread context.
    """

    async def weave(
        self,
        conversation_history: list[dict],
        memory_recalls: list[dict],
    ) -> NarrativeContext:
        """Heuristic narrative thread extraction (M6 E6.1).

        Conservative defensive heuristic -- 10ms budget, no LLM.

        Activation criteria: at least 2 entries in `conversation_history`
        carry an explicit narrative signal (`thread`, `topic`, or `intent`
        key).  Trivial / unstructured input falls through to defaults so
        callers can rely on `result.active_threads == []` as "no signal".

        Returns top-5 threads ranked by frequency, with normalized
        salience and a `weave_suggestion` pointing at the dominant thread.
        """
        if not isinstance(conversation_history, list):
            return NarrativeContext()

        counts: dict[str, int] = {}
        for entry in conversation_history:
            if not isinstance(entry, dict):
                continue
            key = entry.get("thread") or entry.get("topic") or entry.get("intent")
            if isinstance(key, str) and key:
                counts[key] = counts.get(key, 0) + 1

        if len(counts) < 1 or sum(counts.values()) < 2:
            # Not enough narrative signal -- defer.
            return NarrativeContext()

        # Top-5 by frequency
        threads = sorted(counts.keys(), key=lambda k: -counts[k])[:5]
        total = float(sum(counts[k] for k in threads)) or 1.0
        salience = {k: counts[k] / total for k in threads}
        suggestion = f"Continue thread: {threads[0]}" if threads else ""
        return NarrativeContext(
            active_threads=threads,
            thread_salience=salience,
            weave_suggestion=suggestion,
        )
