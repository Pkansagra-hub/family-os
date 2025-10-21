"""Redaction obligation helpers.

Future milestones will persist obligation outcomes alongside receipts and
surface advisory events for downstream services. The current scaffold only
captures the API surface.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(slots=True)
class RedactionDirective:
    obligation: str
    target: str
    fields: Iterable[str]


def apply_redactions(body: dict[str, object], directives: Iterable[RedactionDirective]) -> dict[str, object]:
    """Apply redaction directives to the provided body.

    The function returns a shallow copy so callers can retain the original
    payload for audit purposes.
    """

    _ = (body, directives)
    raise NotImplementedError("Redaction handling is not yet implemented")
