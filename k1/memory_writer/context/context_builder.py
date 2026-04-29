"""
ContextBuilder -- Assembles ExtractionContext from SS snapshot + TurnCompletePayload.

Uses context_assembly.py for temporal/spatial resolution.
Falls back gracefully if sections are missing.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from k1.memory_writer.config import MWConfig
from k1.memory_writer.context_assembly import assemble_temporal_spatial
from k1.memory_writer.events import TurnCompletePayload
from k1.memory_writer.types import Affect, CompressedTurn, ExtractionContext


class ContextBuilder:
    """Assembles ExtractionContext from SS snapshot + TurnCompletePayload.

    Every filter-passed turn gets the full SS snapshot.
    SessionState is the accumulator — history_active holds
    10-25 recent turns. We read ALL of them.
    """

    __slots__ = ("_config",)

    def __init__(self, config: MWConfig) -> None:
        self._config = config

    def build(
        self,
        snapshot: Dict[str, Any],
        payload: TurnCompletePayload,
    ) -> ExtractionContext:
        """Build ExtractionContext from snapshot and payload."""
        beliefs = snapshot.get("beliefs_active", {})
        if not isinstance(beliefs, dict):
            beliefs = {}
        ts_fields = assemble_temporal_spatial(payload, beliefs)

        current_turn, recent_turns, tool_calls = self._extract_history(snapshot, payload)

        current_affect = self._extract_affect(snapshot.get("affective_now"))
        baseline_affect = self._extract_affect(snapshot.get("affective_baseline"))

        active_topics, topic_salience = self._extract_topics(snapshot.get("scoreboard"))

        active_narrative = snapshot.get("narrative_active")
        if not isinstance(active_narrative, dict):
            active_narrative = None

        control_context = snapshot.get("control", {}) or {}
        persona_context = snapshot.get("persona", {}) or {}
        device_context = snapshot.get("ifl", {}) or {}

        active_persons = self._extract_persons(beliefs)

        task = snapshot.get("task_state", {}) or {}
        active_goals = task.get("active_goals", []) if isinstance(task, dict) else []

        meta = snapshot.get("meta", {}) or {}
        session_id = (
            meta.get("session_id", payload.session_id)
            if isinstance(meta, dict)
            else payload.session_id
        )

        return ExtractionContext(
            current_turn=current_turn,
            recent_turns=recent_turns,
            active_persons=active_persons,
            current_affect=current_affect,
            baseline_affect=baseline_affect,
            active_narrative=active_narrative,
            active_topics=active_topics,
            topic_salience=topic_salience,
            active_goals=active_goals,
            control_context=control_context,
            device_context=device_context,
            persona_context=persona_context,
            session_id=session_id,
            conversation_turn=payload.turn_number,
            tool_calls_per_turn=tool_calls,
            **ts_fields,
        )

    @staticmethod
    def _extract_history(
        snapshot: Dict[str, Any],
        payload: TurnCompletePayload,
    ) -> Tuple[CompressedTurn, List[CompressedTurn], Dict[int, List[Dict[str, Any]]]]:
        """Extract full conversation window from history_active.

        For every Turn in ``history_active.turns`` we emit a *pair* of
        :class:`CompressedTurn` rows: one with ``role="user"`` carrying
        ``user_message`` and one with ``role="assistant"`` carrying
        ``assistant_response``. This restores the dialogue the
        WriterAgent needs -- previously only the user side was loaded
        and the assistant response was silently dropped, leaving the
        LLM to extract atoms from a user-only monologue.

        Empty assistant responses are skipped so the prompt isn't
        polluted with blank turns.
        """
        history = snapshot.get("history_active", {})
        turns_raw = history.get("turns", []) if isinstance(history, dict) else []

        current_turn = CompressedTurn(
            turn_id=payload.turn_id,
            role="user",
            text=payload.user_message,
            timestamp_ms=payload.timestamp_ms,
            turn_number=payload.turn_number,
        )

        recent_turns: List[CompressedTurn] = []
        tool_calls: Dict[int, List[Dict[str, Any]]] = {}

        for t in turns_raw:
            if isinstance(t, dict):
                tid = t.get("turn_id", "")
                user_text = t.get("user_message", "")
                assistant_text = t.get("assistant_response", "")
                ts = t.get("timestamp_ms", 0)
                tn = t.get("turn_number", 0)
            else:
                tid = getattr(t, "turn_id", "")
                user_text = getattr(t, "user_message", "")
                assistant_text = getattr(t, "assistant_response", "")
                ts = getattr(t, "timestamp_ms", 0)
                tn = getattr(t, "turn_number", 0)

            if user_text:
                recent_turns.append(
                    CompressedTurn(
                        turn_id=tid,
                        role="user",
                        text=user_text,
                        timestamp_ms=ts,
                        turn_number=tn,
                    )
                )
            if assistant_text:
                recent_turns.append(
                    CompressedTurn(
                        turn_id=f"{tid}:a" if tid else "",
                        role="assistant",
                        text=assistant_text,
                        timestamp_ms=ts,
                        turn_number=tn,
                    )
                )

            tc = ContextBuilder._extract_tool_calls_from_turn(t)
            if tc:
                tool_calls[tn] = tc

        return current_turn, recent_turns, tool_calls

    @staticmethod
    def _extract_tool_calls_from_turn(turn: Any) -> List[Dict[str, Any]]:
        """Extract tool_calls from Turn metadata or sub-entries."""
        result: List[Dict[str, Any]] = []
        if isinstance(turn, dict):
            meta = turn.get("metadata", {})
            if isinstance(meta, dict):
                tc = meta.get("tool_calls", [])
                if tc:
                    result.extend(tc)
            for entry in turn.get("sub_entries", []):
                if isinstance(entry, dict):
                    entry_meta = entry.get("metadata", {})
                    if isinstance(entry_meta, dict):
                        tc = entry_meta.get("tool_calls", [])
                        if tc:
                            result.extend(tc)
        else:
            meta = getattr(turn, "metadata", None)
            if isinstance(meta, dict):
                tc = meta.get("tool_calls", [])
                if tc:
                    result.extend(tc)
            elif meta and hasattr(meta, "__dict__"):
                tc = getattr(meta, "tool_calls", None) or []
                if tc:
                    result.extend(tc)
            for entry in getattr(turn, "sub_entries", []):
                entry_meta = getattr(entry, "metadata", {})
                if isinstance(entry_meta, dict):
                    tc = entry_meta.get("tool_calls", [])
                    if tc:
                        result.extend(tc)
        return result

    @staticmethod
    def _extract_affect(section: Any) -> Optional[Affect]:
        if not section or not isinstance(section, dict):
            return None
        dims = section.get("dimensions", section)
        if isinstance(dims, dict):
            return Affect(
                valence=float(dims.get("valence", 0.0)),
                arousal=float(dims.get("arousal", 0.0)),
                dominance=float(dims.get("dominance", 0.5)),
            )
        return None

    @staticmethod
    def _extract_topics(
        scoreboard: Any,
    ) -> Tuple[List[str], Dict[str, float]]:
        if not scoreboard or not isinstance(scoreboard, dict):
            return [], {}
        topics: List[str] = []
        salience: Dict[str, float] = {}
        for t in scoreboard.get("topic_stack", []):
            if isinstance(t, dict):
                name = t.get("name", "")
                if name:
                    topics.append(name)
                    salience[name] = float(t.get("salience", 0.0))
        return topics, salience

    @staticmethod
    def _extract_persons(beliefs: Dict[str, Any]) -> Dict[str, Any]:
        if not beliefs or not isinstance(beliefs, dict):
            return {}
        entities = beliefs.get("mentioned_entities", [])
        persons: Dict[str, Any] = {}
        for e in entities:
            if isinstance(e, dict) and e.get("type") == "PERSON":
                name = e.get("display_name", "")
                pid = e.get("person_id", "")
                if name:
                    persons[name] = {
                        "person_id": pid,
                        "type": "PERSON",
                        "confidence": e.get("confidence", 1.0),
                    }
        return persons
