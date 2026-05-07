"""Reformulation detector — pipeline P03 ("REFORMULATION").

Recognises user re-asking-the-same-question turns: same intent, different
phrasing, often after a bot answer that didn't satisfy. Detection is
similarity-based, not regex, because the user is by definition rephrasing.

Algorithm: token-set Jaccard similarity between the current user
utterance and the most recent prior user utterance recorded in
:class:`ConversationContext`. A score in (lo, hi) returns a
:class:`ReformulationSignal`; outside that band the turn is either too
similar (verbatim repeat — separate signal class outside this milestone)
or too different (a new topic).

Token-set similarity is a deliberate, dependency-free approximation;
swapping in a real embedding cosine ("st_embedding(prev) · st_embedding(now)")
is a one-line replacement at :meth:`_similarity` and does not change
the public API.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from k1.concierge.feedback.context import ConversationContext


_TOKEN = re.compile(r"[A-Za-z0-9']+")
_STOP = frozenset(
    {
        "a",
        "an",
        "the",
        "is",
        "are",
        "was",
        "were",
        "do",
        "did",
        "does",
        "i",
        "you",
        "we",
        "they",
        "he",
        "she",
        "it",
        "what",
        "when",
        "who",
        "where",
        "why",
        "how",
        "to",
        "of",
        "and",
        "or",
        "but",
        "in",
        "on",
        "at",
        "for",
        "with",
        "about",
        "from",
        "by",
        "this",
        "that",
    }
)


@dataclass(frozen=True)
class ReformulationSignal:
    """Detector output for a rephrased re-ask."""

    pipeline_id: str = "P03"
    signal_class: str = "IMPLICIT"
    feedback_type: str = "reformulation"
    similarity: float = 0.0
    prior_utterance: str = ""
    raw_text: str = ""
    confidence: float = 0.0
    target_response_id: str | None = None
    target_event_ids: tuple[str, ...] = ()


class ReformulationDetector:
    """Detect query reformulations against prior user utterance.

    Caller invariants:
      * Pass the same :class:`ConversationContext` instance across turns
        so ``last_user_message`` is populated.
      * After detection, update ``context.last_user_message`` to the
        current utterance for the next turn.

    Tunables: ``similarity_low`` and ``similarity_high`` bound the
    "rephrasing" band. Defaults are conservative; adjust per A/B.
    """

    def __init__(
        self,
        *,
        similarity_low: float = 0.30,
        similarity_high: float = 0.85,
    ) -> None:
        if not 0.0 <= similarity_low < similarity_high <= 1.0:
            raise ValueError("require 0 <= similarity_low < similarity_high <= 1")
        self._lo = similarity_low
        self._hi = similarity_high

    def detect(
        self,
        utterance: str,
        *,
        context: "ConversationContext | None" = None,
    ) -> ReformulationSignal | None:
        if not utterance or not utterance.strip():
            return None
        if context is None or not context.last_user_message:
            return None

        prior = context.last_user_message
        score = self._similarity(prior, utterance)
        if not (self._lo < score < self._hi):
            return None

        # Confidence peaks at the band centre and falls off toward edges.
        centre = 0.5 * (self._lo + self._hi)
        spread = 0.5 * (self._hi - self._lo)
        # 1.0 at centre, 0.0 at the band edges, clipped non-negative.
        confidence = max(0.0, 1.0 - abs(score - centre) / spread)

        return ReformulationSignal(
            similarity=score,
            prior_utterance=prior,
            raw_text=utterance,
            confidence=round(confidence, 4),
            target_response_id=context.response_id,
            target_event_ids=tuple(context.grounded_event_ids),
        )

    @staticmethod
    def _similarity(prev: str, curr: str) -> float:
        a = {t.lower() for t in _TOKEN.findall(prev) if t.lower() not in _STOP}
        b = {t.lower() for t in _TOKEN.findall(curr) if t.lower() not in _STOP}
        if not a or not b:
            return 0.0
        return len(a & b) / len(a | b)


__all__ = ["ReformulationDetector", "ReformulationSignal"]
