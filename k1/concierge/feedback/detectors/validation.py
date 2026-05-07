"""Validation detector — pipeline P08 ("VALIDATION").

Captures explicit positive/negative validation of the bot's last
response: "yes that's right", "thanks!", "no that's wrong" (when
no replacement value is offered, otherwise correction wins).

Returns a typed :class:`ValidationSignal` that the emitter shapes into
the P08 wire payload (mirrors ``k0/feedback/payloads.py::ValidationPayload``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from k1.concierge.feedback.context import ConversationContext


_POSITIVE = re.compile(
    r"\b(?:yes(?:[,.! ]|$)|yep|yeah|right|correct|exactly|"
    r"that's (?:right|correct|true|spot on)|"
    r"you (?:got|have) (?:it|that) (?:right|correct)|"
    r"thanks?(?:[,.! ]|$)|thank you|good catch|nice|perfect)\b",
    re.IGNORECASE,
)

# Negative without an alternative ("no" / "wrong" / "incorrect" alone).
# CorrectionDetector consumes utterances that supply replacement content.
_NEGATIVE = re.compile(
    r"\b(?:no(?:[,.! ]|$)|nope|wrong|incorrect|"
    r"that's (?:wrong|incorrect|not (?:right|correct|true))|"
    r"you (?:got|have) (?:it|that) wrong|not (?:quite|really))\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ValidationSignal:
    """Validation outcome for the previous bot turn."""

    pipeline_id: str = "P08"
    signal_class: str = "VALIDATION"
    feedback_type: str = "validation"
    polarity: str = "positive"  # "positive" | "negative"
    raw_text: str = ""
    confidence: float = 0.0
    target_response_id: str | None = None
    target_event_ids: tuple[str, ...] = ()


class ValidationDetector:
    """Detect explicit yes/no validation of the previous bot response.

    Usage: call :meth:`detect` per user utterance. Returns ``None`` when
    no validation pattern matches; otherwise the polarity is "positive"
    or "negative". Negative-without-replacement is the boundary against
    :class:`CorrectionDetector`: if the user offers a replacement value
    you should run :class:`CorrectionDetector` first and skip validation.
    """

    def detect(
        self,
        utterance: str,
        *,
        context: "ConversationContext | None" = None,
    ) -> ValidationSignal | None:
        if not utterance or not utterance.strip():
            return None

        positive = _POSITIVE.search(utterance)
        negative = _NEGATIVE.search(utterance)

        if positive is None and negative is None:
            return None

        # Prefer the more confident match by relative position; "no, that's right"
        # should weight toward 'right' (positive). Tie-break: longer match wins.
        if positive is not None and negative is not None:
            polarity = (
                "positive"
                if (positive.end() - positive.start()) >= (negative.end() - negative.start())
                else "negative"
            )
            confidence = 0.55  # ambiguous turn
        elif positive is not None:
            polarity, confidence = "positive", 0.85
        else:
            polarity, confidence = "negative", 0.80

        target_response_id = context.response_id if context is not None else None
        target_event_ids = (
            tuple(context.grounded_event_ids)
            if context is not None and context.grounded_event_ids
            else ()
        )

        return ValidationSignal(
            polarity=polarity,
            raw_text=utterance,
            confidence=confidence,
            target_response_id=target_response_id,
            target_event_ids=target_event_ids,
        )


__all__ = ["ValidationDetector", "ValidationSignal"]
