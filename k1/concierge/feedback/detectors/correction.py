"""Correction detector — pipeline P02 ("CORRECTION").

Identifies user utterances that explicitly correct a prior bot answer
or a stored memory. Pattern coverage matches the FEEDBACK.md K1 detector
contract:

* Direct contradiction:  "no, I actually had tea, not coffee"
* Time correction:       "that was Tuesday not Wednesday"
* Identity correction:   "actually that was Sarah, not Rachel"
* Magnitude correction:  "no, it was 3 not 5"

The detector emits a :class:`CorrectionSignal` whose ``original_content``
is sourced from the bot's last response (when available via
:class:`ConversationContext`) and whose ``corrected_content`` is the
user-supplied substring. Confidence is regex-strength weighted.

P02 payload shape mirrors ``k0/feedback/payloads.py::CorrectionPayload``
(extra=forbid, no schema drift). The detector returns a dataclass; the
emitter shapes it into the wire envelope.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from k1.concierge.feedback.context import ConversationContext


# Ordered: stronger / more explicit patterns first, so the first match
# wins and confidence reflects pattern strength.
_PATTERNS: tuple[tuple[re.Pattern[str], float], ...] = (
    # "no, it was X, not Y" / "actually it was X not Y"
    (
        re.compile(
            r"(?:^|[\s,;.])(?:no|actually|wait)\b[\s,]*"
            r"(?:it|that|this|i|we|he|she|they)?\s*(?:was|were|had|did|am|are|is)?\s*"
            r"(?P<corrected>[^,.;]{1,80}?)\s*[,]?\s*not\s+(?P<original>[^,.;?!]{1,80})",
            re.IGNORECASE,
        ),
        0.92,
    ),
    # "X, not Y" mid-sentence
    (
        re.compile(
            r"(?P<corrected>[^,.;]{2,80}?)\s*,\s*not\s+(?P<original>[^,.;?!]{1,80})",
            re.IGNORECASE,
        ),
        0.78,
    ),
    # "that's wrong" / "you got it wrong" — corrects without alt content
    (
        re.compile(
            r"\b(?:that(?:'s| is) (?:wrong|incorrect|not right)"
            r"|you (?:got|have) (?:it|that) wrong"
            r"|that's not (?:right|correct|true))\b",
            re.IGNORECASE,
        ),
        0.70,
    ),
    # "I never said/did X" — explicit denial
    (
        re.compile(
            r"\bI\s+never\s+(?:said|did|told|mentioned)\s+(?P<denied>[^,.;?!]{1,80})",
            re.IGNORECASE,
        ),
        0.65,
    ),
)


@dataclass(frozen=True)
class CorrectionSignal:
    """Detector output for a single user-correction utterance."""

    pipeline_id: str = "P02"
    signal_class: str = "CORRECTION"
    feedback_type: str = "correction"
    original_content: str | None = None
    corrected_content: str | None = None
    raw_text: str = ""
    confidence: float = 0.0
    matched_pattern_index: int = -1
    correction_target: str = "memory"  # "memory" | "response"
    target_event_id: str | None = None
    spans: tuple[tuple[int, int], ...] = field(default_factory=tuple)


class CorrectionDetector:
    """Stateless regex-based correction detector.

    Use :meth:`detect` per user utterance. Returns ``None`` when no
    correction pattern matches; the emitter then skips the ``feedback.envelope.v1``
    publish for that turn (no spurious traffic).
    """

    def detect(
        self,
        utterance: str,
        *,
        context: "ConversationContext | None" = None,
    ) -> CorrectionSignal | None:
        """Return a typed signal or ``None`` if no correction is present."""
        if not utterance or not utterance.strip():
            return None

        for idx, (pattern, base_confidence) in enumerate(_PATTERNS):
            match = pattern.search(utterance)
            if match is None:
                continue

            groupdict = match.groupdict()
            corrected = (groupdict.get("corrected") or "").strip() or None
            original = (groupdict.get("original") or groupdict.get("denied") or "").strip() or None

            # Prefer the bot's last response as ``original`` if the
            # pattern didn't capture an explicit prior value.
            if original is None and context is not None and context.last_bot_response:
                original = context.last_bot_response

            target_event_id = (
                context.grounded_event_ids[0]
                if context is not None and context.grounded_event_ids
                else None
            )
            target_kind = "memory" if target_event_id else "response"

            return CorrectionSignal(
                original_content=original,
                corrected_content=corrected or utterance.strip(),
                raw_text=utterance,
                confidence=base_confidence,
                matched_pattern_index=idx,
                correction_target=target_kind,
                target_event_id=target_event_id,
                spans=((match.start(), match.end()),),
            )
        return None


__all__ = ["CorrectionDetector", "CorrectionSignal"]
