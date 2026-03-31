"""
k1.concierge.prompt.clarify_depth -- Clarification depth tracking.

V2 Design Ref: Section 6.1 (Clarification Depth Tracking)

When Front enters CLARIFY_ASK mode, it tracks how many times it has asked
about the SAME gap. Each depth level changes the clarification strategy,
escalating from open question -> specific options -> best guess + proceed.

This prevents the "20 questions" anti-pattern where the system keeps
re-asking without making progress.

Exports:
  - ClarificationDepthState: Mutable tracker for per-gap depth
  - CLARIFY_DEPTH_BLOCKS: Depth -> prompt injection text
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field as dataclass_field

from k1.concierge.config import get_config


@dataclass
class ClarificationDepthState:
    """Tracks how many times the system has asked for clarification
    on the SAME gap without getting a usable answer.

    Depth escalation strategy (V2 Design Doc Section 6.1):
        depth 0: Open question ("When are you thinking of going?")
        depth 1: Specific options ("This week, next week, or a specific date?")
        depth 2: Best guess and proceed ("I'll assume next weekend -- I can
                 change it if that's not right.")

    After depth 2, the system STOPS asking and proceeds with its best guess.

    Attributes:
        field: The gap field name (e.g. "dates", "budget", "hotel_name").
        depth: Current clarification depth (0=first ask, 1=re-ask, 2=final).
        previous_questions: Questions already asked for this gap.
        max_depth: After this depth, pick best option or escalate.
    """

    field: str = ""
    depth: int = 0
    previous_questions: list[str] = dataclass_field(default_factory=list)
    max_depth: int = 2

    def __post_init__(self) -> None:
        """Apply config override for max_depth if not explicitly set."""
        if self.max_depth == 2:  # default sentinel
            self.max_depth = get_config().prompt.max_clarify_depth

    def increment(self) -> None:
        """Increment depth after an unhelpful user response."""
        if self.depth < self.max_depth:
            self.depth += 1

    def should_guess(self) -> bool:
        """Return True if we've exhausted clarification attempts."""
        return self.depth >= self.max_depth

    def reset(self) -> None:
        """Reset when gap is resolved or a new gap is targeted."""
        self.depth = 0
        self.field = ""
        self.previous_questions.clear()

    @property
    def last_question(self) -> str:
        """Return the most recent question asked, or empty string."""
        return self.previous_questions[-1] if self.previous_questions else ""

    def to_dict(self) -> dict:
        """Serialize for ss.clarifications storage."""
        return {
            "field": self.field,
            "depth": self.depth,
            "previous_questions": list(self.previous_questions),
            "max_depth": self.max_depth,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ClarificationDepthState:
        """Deserialize from ss.clarifications storage."""
        return cls(
            field=data.get("field", ""),
            depth=data.get("depth", 0),
            previous_questions=data.get("previous_questions", []),
            max_depth=data.get("max_depth", 2),
        )


# =========================================================================
# CLARIFY_DEPTH_BLOCKS -- Depth -> prompt injection text
# =========================================================================
# Injected into the prompt by DynamicPromptBuilder when mode == CLARIFY_ASK.
# Authoritative text from V2 Design Doc Section 6.1.

CLARIFY_DEPTH_BLOCKS: dict[int, str] = {
    0: (
        "== CLARIFICATION: FIRST ASK ==\n"
        "You're asking about this for the first time.\n"
        "- Ask ONE question. Not two. Not three.\n"
        "- Phrase it naturally, as if you're curious.\n"
        "- Do NOT offer options yet -- let the user answer freely.\n"
    ),
    1: (
        "== CLARIFICATION: SECOND ASK ==\n"
        'You asked about "{field}" before and the answer was incomplete.\n'
        'Previous question: "{previous_question}"\n'
        "- Be more specific this time.\n"
        "- Offer 2-3 concrete options if possible.\n"
        '- Reference what they DID say: "You mentioned X -- did you mean...?"\n'
    ),
    2: (
        "== CLARIFICATION: FINAL ATTEMPT ==\n"
        'You\'ve asked about "{field}" twice already. Do NOT ask again.\n'
        "- State your BEST GUESS based on context (beliefs, history, recall).\n"
        "- Proceed with that assumption.\n"
        '- Add: "Let me know if you had something different in mind."\n'
        "- If no reasonable guess is possible, dispatch anyway and let\n"
        "  the Worker request clarification through HITL.\n"
    ),
}


def get_clarify_depth_block(
    depth: int,
    field_name: str = "",
    previous_question: str = "",
) -> str:
    """Return the depth-appropriate clarification strategy block.

    For depth 1 and 2, the block contains {field} and {previous_question}
    placeholders that get interpolated with actual values.

    Args:
        depth: Current clarification depth (0, 1, or 2).
        field_name: Gap field name (e.g. "dates", "budget").
        previous_question: The last question asked about this field.

    Returns:
        Formatted prompt block string with placeholders resolved.
    """
    template = CLARIFY_DEPTH_BLOCKS.get(depth, CLARIFY_DEPTH_BLOCKS[0])
    if depth >= 1:
        return template.format(
            field=field_name,
            previous_question=previous_question,
        )
    return template


class ClarificationTracker:
    """Manages ClarificationDepthState for all active gaps.

    Reads from and writes to ss.clarifications section. Used by
    DynamicPromptBuilder when mode == CLARIFY_ASK.

    V2 Design Doc Section 6.1 (Clarification Depth Tracking).

    Usage:
        tracker = ClarificationTracker()
        tracker.load_from_dict(ss_clarifications_dict)
        depth = tracker.get_depth("dates")
        block = tracker.get_prompt_block("dates")
        tracker.record_question("dates", "When are you thinking of going?")
        updated = tracker.to_dict()  # persist back to SS
    """

    def __init__(self) -> None:
        self._states: dict[str, ClarificationDepthState] = {}

    def load_from_dict(self, data: dict[str, list[dict]] | None) -> None:
        """Load depth states from serialized SS clarifications.

        Args:
            data: Dict with "depth_states" key containing list of
                serialized ClarificationDepthState dicts. None is
                handled gracefully (no-op).
        """
        if not data:
            return
        for entry in data.get("depth_states", []):
            state = ClarificationDepthState.from_dict(entry)
            self._states[state.field] = state

    def get_depth(self, field: str) -> int:
        """Get current depth for a gap field. 0 if never asked."""
        state = self._states.get(field)
        return state.depth if state else 0

    def get_state(self, field: str) -> ClarificationDepthState:
        """Get or create depth state for a gap field.

        Returns the existing state if tracked, or creates a new
        depth-0 state for the field.
        """
        if field not in self._states:
            self._states[field] = ClarificationDepthState(field=field)
        return self._states[field]

    def record_question(self, field: str, question: str) -> None:
        """Record that a clarification question was asked for this field.

        Increments depth and stores the question in previous_questions.

        Args:
            field: Gap field name (e.g. "dates").
            question: The clarification question that was asked.
        """
        state = self.get_state(field)
        state.previous_questions.append(question)
        state.increment()

    def is_exhausted(self, field: str) -> bool:
        """Check if re-asks are exhausted for this field.

        Returns True if depth >= max_depth, meaning the system should
        proceed with a best guess instead of asking again.
        """
        state = self._states.get(field)
        return state.should_guess() if state else False

    def get_prompt_block(self, field: str) -> str:
        """Get the depth-appropriate prompt block for a gap field.

        Returns the formatted CLARIFY_DEPTH_BLOCK with field name
        and previous question placeholders resolved.
        """
        state = self.get_state(field)
        return get_clarify_depth_block(
            depth=state.depth,
            field_name=state.field,
            previous_question=state.last_question,
        )

    @property
    def active_fields(self) -> list[str]:
        """Return list of fields currently being tracked."""
        return list(self._states.keys())

    def to_dict(self) -> dict[str, list[dict]]:
        """Serialize all depth states for SS persistence.

        Returns:
            Dict with "depth_states" key containing serialized entries.
        """
        return {
            "depth_states": [s.to_dict() for s in self._states.values()],
        }
