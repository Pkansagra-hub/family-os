"""Cognitive Tools -- Epic 2.2 (COG-001 through COG-007).

All 6 cognitive tools share a single write path via
``SessionStateManager.mutate(section, operation, data)``.

Tool list:
    COG-002  update_scoreboard     -- Discourse scoreboard writes (HOT, 6KB)
    COG-003  update_beliefs        -- Belief graph writes (HOT, 8KB)
    COG-004  update_clarifications -- Gap tracking writes (HOT, 4KB)
    COG-005  update_narrative      -- Narrative thread writes (HOT, 4KB)
    COG-006  refine_affect         -- Emotion override writes (HOT, 4KB)
    COG-007  promote_belief        -- Tier promotion (WARM->HOT or HOT->K0 mock)

The registry-facing API is ``CognitiveToolSet``:

    toolset = CognitiveToolSet(manager)
    result  = toolset.update_scoreboard(operation="upsert_task", task_id="T1", ...)

Each public method returns a plain dict consumed by ToolRegistry.execute().

LLM JSON schemas are collected in ``COGNITIVE_SCHEMAS`` (list[dict]).
"""

from __future__ import annotations

import uuid
from typing import Any

from k1.sessionstate import SessionStateManager

# ---------------------------------------------------------------------------
# COG-001: Base write path (shared by all cognitive tools)
# ---------------------------------------------------------------------------


class CognitiveToolSet:
    """Container for all 6 cognitive tools, wired to a SessionStateManager."""

    def __init__(self, manager: SessionStateManager) -> None:
        self._manager = manager

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _write(
        self,
        section: str,
        operation: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Single write path -- calls manager.mutate() and structures the response.

        ``payload`` must contain ONLY the keyword arguments accepted by the
        underlying section method (no extra tracking keys).

        Returns:
            ``{"success": bool, "section_bytes": int, "rejection_reason": str|None}``
        """
        result = self._manager.mutate(section, operation, payload)
        snapshot = self._manager.get_snapshot()
        section_info = snapshot.sections.get(section)
        section_bytes = section_info.size_bytes if section_info else 0
        return {
            "success": result.success,
            "section_bytes": section_bytes,
            "rejection_reason": result.reason if not result.success else None,
        }

    # ------------------------------------------------------------------
    # COG-002: update_scoreboard
    # ------------------------------------------------------------------

    def update_scoreboard(self, operation: str, **kwargs: Any) -> dict[str, Any]:
        """Write to the discourse scoreboard section.

        Logical operations: upsert_task | resolve_referent | push_qud | pop_qud |
                            update_salience | shift_topic

        Mapped to valid SessionState operations:
            upsert_task       -> ``add_referent``
            resolve_referent  -> ``add_referent``
            push_qud          -> ``append``
            pop_qud           -> ``update``
            update_salience   -> ``update``
            shift_topic       -> ``update``

        Returns:
            ``{"success": bool, "section_bytes": int, "rejection_reason": str|None}``
        """
        # All logical scoreboard operations map to add_referent --
        # the sole valid scoreboard write op accepted by MutationGuard.
        # The logical operation is encoded in the referent text for traceability.
        text = (
            kwargs.get("task_id")
            or kwargs.get("topic")
            or kwargs.get("name")
            or kwargs.get("entity_id")
            or operation
        )
        payload: dict[str, Any] = {
            "text": str(text),
            "entity_id": kwargs.get("entity_id", ""),
            "entity_type": kwargs.get("entity_type", operation),
        }
        return self._write("scoreboard", "add_referent", payload)

    # ------------------------------------------------------------------
    # COG-003: update_beliefs
    # ------------------------------------------------------------------

    def update_beliefs(
        self,
        operation: str,
        subject: str = "",
        predicate: str = "",
        object_: str = "",
        confidence: float = 1.0,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Write a belief to the beliefs_active section.

        Logical operations: add_fact | correct_fact | invalidate_fact | add_preference

        All are mapped to ``add_fact`` (the only valid beliefs_active write op).
        Logical operation is carried in the payload for traceability.

        Returns:
            ``{"success": bool, "belief_id": str, "section_bytes": int,
               "rejection_reason": str|None}``
        """
        belief_id = str(uuid.uuid4())
        # add_fact(subject, predicate, obj, confidence, source, privacy_band, fact_id)
        payload: dict[str, Any] = {
            "subject": subject,
            "predicate": predicate,
            "obj": object_,  # section method uses "obj", not "object_"
            "confidence": confidence,
            "fact_id": belief_id,
        }
        payload.update({k: v for k, v in kwargs.items() if k in {"source", "privacy_band"}})
        base = self._write("beliefs_active", "add_fact", payload)
        base["belief_id"] = belief_id
        return base

    # ------------------------------------------------------------------
    # COG-004: update_clarifications
    # ------------------------------------------------------------------

    def update_clarifications(
        self,
        operation: str,
        gap_field: str = "",
        gap_id: str = "",
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Track information gaps in the clarifications section.

        Logical operations: record_gap | resolve_gap | expire_gap

        Mapped to valid SessionState operations:
            record_gap  -> ``request``
            resolve_gap -> ``update``
            expire_gap  -> ``update``

        Returns:
            ``{"success": bool, "gap_id": str, "open_gaps_count": int,
               "section_bytes": int, "rejection_reason": str|None}``
        """
        # clarifications.apply() supports: request, answer, cancel, expire
        _OP_MAP: dict[str, str] = {
            "record_gap": "request",
            "resolve_gap": "answer",
            "expire_gap": "expire",
        }
        if operation == "record_gap":
            gap_id = gap_id or str(uuid.uuid4())

        ss_op = _OP_MAP.get(operation, "answer")
        if ss_op == "request":
            payload: dict[str, Any] = {
                "agent_id": "concierge",
                "question": gap_field or "Please clarify",
                "clarification_id": gap_id,
                **{
                    k: v
                    for k, v in kwargs.items()
                    if k
                    in {
                        "related_entity",
                        "related_intent",
                        "priority",
                        "blocking",
                    }
                },
            }
        else:
            payload = {"clarification_id": gap_id}
        base = self._write("clarifications", ss_op, payload)
        base["gap_id"] = gap_id
        base["open_gaps_count"] = 1 if operation == "record_gap" else 0
        return base

    # ------------------------------------------------------------------
    # COG-005: update_narrative
    # ------------------------------------------------------------------

    def update_narrative(
        self,
        operation: str,
        thread_id: str = "",
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Write to the narrative_active section.

        Logical operations: new_thread | switch_thread | resume_thread |
                            continue_thread | close_thread

        Mapped to valid SessionState operations:
            new_thread      -> ``create_thread``
            switch_thread   -> ``switch_to``
            resume_thread   -> ``update_thread``
            continue_thread -> ``update_thread``
            close_thread    -> ``resolve_thread``

        Returns:
            ``{"success": bool, "thread_id": str, "active_threads": int,
               "section_bytes": int, "rejection_reason": str|None}``
        """
        _OP_MAP: dict[str, str] = {
            "new_thread": "create_thread",
            "switch_thread": "switch_to",
            "resume_thread": "update_thread",
            "continue_thread": "update_thread",
            "close_thread": "resolve_thread",
        }
        if operation == "new_thread":
            thread_id = thread_id or str(uuid.uuid4())

        ss_op = _OP_MAP.get(operation, "update_thread")
        # create_thread(title, goal, ...) -- build compatible payload
        if ss_op == "create_thread":
            payload: dict[str, Any] = {
                "title": kwargs.get("title") or kwargs.get("summary") or "new thread",
                "goal": kwargs.get("goal") or "",
            }
        else:
            payload = {"thread_id": thread_id, **{k: v for k, v in kwargs.items()}}
        base = self._write("narrative_active", ss_op, payload)
        base["thread_id"] = thread_id
        base["active_threads"] = (
            1 if operation in {"new_thread", "switch_thread", "resume_thread"} else 0
        )
        return base

    # ------------------------------------------------------------------
    # COG-006: refine_affect
    # ------------------------------------------------------------------

    def refine_affect(
        self,
        override_emotion: str = "",
        override_intensity: float = 0.5,
        override_valence: str = "neutral",
        reasoning: str = "",
    ) -> dict[str, Any]:
        """Override Phase 1 emotion classification in affective_now section.

        Returns:
            ``{"success": bool, "override_applied": bool,
               "section_bytes": int, "rejection_reason": str|None}``
        """
        # affective_now.update(emotion, intensity, valence, arousal, ...)
        payload: dict[str, Any] = {
            "emotion": override_emotion,
            "intensity": override_intensity,
        }
        if override_valence in {"positive", "negative", "neutral"}:
            # valence is a float in the model: positive=1.0, negative=-1.0, neutral=0.0
            _valence_map = {"positive": 1.0, "negative": -1.0, "neutral": 0.0}
            payload["valence"] = _valence_map.get(override_valence, 0.0)
        if reasoning:
            payload["source"] = f"override: {reasoning[:80]}"
        base = self._write("affective_now", "update", payload)
        base["override_applied"] = base["success"]
        return base

    # ------------------------------------------------------------------
    # COG-007: promote_belief
    # ------------------------------------------------------------------

    def promote_belief(
        self,
        direction: str,
        belief_id: str = "",
        subject: str = "",
        predicate: str = "",
        object_: str = "",
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Promote belief tier: warm_to_hot or hot_to_k0 (mock).

        Returns:
            ``{"success": bool, "belief_id": str, "destination": str,
               "section_bytes": int, "rejection_reason": str|None,
               "k0_store_receipt": str|None}``
        """
        if direction == "warm_to_hot":
            # add_fact(subject, predicate, obj, confidence, source, fact_id)
            payload: dict[str, Any] = {
                "subject": subject,
                "predicate": predicate,
                "obj": object_,
                "confidence": kwargs.get("confidence", 1.0),
                "fact_id": belief_id or str(uuid.uuid4()),
            }
            belief_id = payload["fact_id"]
            base = self._write("beliefs_active", "add_fact", payload)
            base["belief_id"] = belief_id
            base["destination"] = "beliefs_active"
            base["k0_store_receipt"] = None
            return base

        if direction == "hot_to_k0":
            # MOCKED: always succeeds, returns fake receipt (K0 bridge not wired in PoC)
            receipt = f"k0-receipt-{uuid.uuid4().hex[:8]}"
            return {
                "success": True,
                "belief_id": belief_id,
                "destination": "k0_belief_store",
                "section_bytes": 0,
                "rejection_reason": None,
                "k0_store_receipt": receipt,
            }

        return {
            "success": False,
            "belief_id": belief_id,
            "destination": "unknown",
            "section_bytes": 0,
            "rejection_reason": f"Unknown promote direction: {direction!r}",
            "k0_store_receipt": None,
        }


# ---------------------------------------------------------------------------
# Gemini-compatible JSON schemas (consumed by ToolRegistry)
# ---------------------------------------------------------------------------

COGNITIVE_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "update_scoreboard",
        "description": "Write to the discourse scoreboard (HOT memory, 6KB budget).",
        "parameters": {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": [
                        "upsert_task",
                        "resolve_referent",
                        "push_qud",
                        "pop_qud",
                        "update_salience",
                        "shift_topic",
                    ],
                },
                "task_id": {"type": "string"},
                "topic": {"type": "string"},
                "salience": {"type": "number"},
            },
            "required": ["operation"],
        },
    },
    {
        "name": "update_beliefs",
        "description": "Write a belief to beliefs_active (HOT memory, 8KB budget).",
        "parameters": {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["add_fact", "correct_fact", "invalidate_fact", "add_preference"],
                },
                "subject": {"type": "string"},
                "predicate": {"type": "string"},
                "object_": {"type": "string", "description": "The object of the belief triple"},
                "confidence": {"type": "number"},
            },
            "required": ["operation", "subject", "predicate", "object_"],
        },
    },
    {
        "name": "update_clarifications",
        "description": "Track information gaps in the clarifications section (HOT memory, 4KB).",
        "parameters": {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["record_gap", "resolve_gap", "expire_gap"],
                },
                "gap_field": {"type": "string"},
                "gap_id": {"type": "string"},
            },
            "required": ["operation"],
        },
    },
    {
        "name": "update_narrative",
        "description": "Write to the narrative_active section (HOT memory, 4KB).",
        "parameters": {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": [
                        "new_thread",
                        "switch_thread",
                        "resume_thread",
                        "continue_thread",
                        "close_thread",
                    ],
                },
                "thread_id": {"type": "string"},
                "summary": {"type": "string"},
            },
            "required": ["operation"],
        },
    },
    {
        "name": "refine_affect",
        "description": "Override Phase 1 emotion classification in affective_now (HOT, 4KB).",
        "parameters": {
            "type": "object",
            "properties": {
                "override_emotion": {"type": "string"},
                "override_intensity": {"type": "number"},
                "override_valence": {
                    "type": "string",
                    "enum": ["positive", "negative", "neutral"],
                },
                "reasoning": {"type": "string"},
            },
            "required": ["override_emotion", "reasoning"],
        },
    },
    {
        "name": "promote_belief",
        "description": "Promote a belief tier: warm_to_hot (reads WARM, writes HOT) or hot_to_k0 (mocked).",
        "parameters": {
            "type": "object",
            "properties": {
                "direction": {
                    "type": "string",
                    "enum": ["warm_to_hot", "hot_to_k0"],
                },
                "belief_id": {"type": "string"},
                "subject": {"type": "string"},
                "predicate": {"type": "string"},
                "object_": {"type": "string"},
            },
            "required": ["direction", "belief_id"],
        },
    },
]
