"""Grounding capsule dataclasses.

A ``GroundingCapsule`` is the prompt-safe block injected by the prompt
builder before the system_prompt is finalized. Builder logic lives in
``k1.selfmodel.service.capsule_builder`` (M4).

M7 additions:
    * ``self_block``         — typed actor identity (replaces actor_block role)
    * ``preferences_block``  — preferences map
    * ``hobbies_block``      — hobbies/likes/dislikes
    * ``goals_block``        — active goals
    * ``routines_block``     — routines + habits
    * ``space_graph_block``  — space graph members (read from space view)
    * ``context_block``      — situation/device/communication style
    * ``conscience_block``   — forbidden + must_ask social acts (M6)

The legacy ``actor_block`` / ``family_block`` / ``rules_block`` /
``capabilities_block`` fields are kept for back-compat (M9 removal).
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "GroundingCapsule",
]


@dataclass(frozen=True)
class GroundingCapsule:
    """Prompt-safe representation of the SituationFrame.

    All fields are pre-rendered strings. Size cap and BLACK redaction
    are enforced by the builder.
    """

    # Legacy blocks (M0-M5).
    actor_block: str = ""
    family_block: str = ""
    rules_block: str = ""
    capabilities_block: str = ""  # DEPRECATED M6 — use conscience_block
    freshness_footer: str = ""
    rendered_at_ms: int = 0

    # M7 typed user-content blocks.
    self_block: str = ""
    preferences_block: str = ""
    hobbies_block: str = ""
    goals_block: str = ""
    routines_block: str = ""
    space_graph_block: str = ""
    context_block: str = ""

    # M6 conscience block.
    conscience_block: str = ""

    def as_prompt_text(self) -> str:
        """Concatenate the blocks into a single prompt-ready string.

        Ordering (M7):

            1. ``self_block`` (or legacy ``actor_block`` fallback)
            2. ``preferences_block``
            3. ``hobbies_block``
            4. ``goals_block``
            5. ``routines_block``
            6. ``space_graph_block`` (or legacy ``family_block`` fallback)
            7. ``context_block``
            8. ``conscience_block`` (or legacy ``rules`` + ``capabilities``)
            9. ``freshness_footer``

        Empty blocks are skipped so the capsule never carries blank
        sections.
        """
        ordered = [
            self.self_block or self.actor_block,
            self.preferences_block,
            self.hobbies_block,
            self.goals_block,
            self.routines_block,
            self.space_graph_block or self.family_block,
            self.context_block,
            self.conscience_block or self.rules_block,
            # Legacy capabilities block kept only when conscience is empty.
            "" if self.conscience_block else self.capabilities_block,
            self.freshness_footer,
        ]
        return "\n".join(p for p in ordered if p)
