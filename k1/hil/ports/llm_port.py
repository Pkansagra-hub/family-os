"""HIL-local ILLMPort (E1.M1.7).

The HIL service uses an LLM only to synthesize a natural-language
question for the user from a structured context. All other LLM uses
remain in their original subsystems.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ILLMPort(Protocol):
    """Best-effort LLM access for question synthesis."""

    async def synthesize_question(
        self,
        *,
        context: dict[str, Any],
        max_tokens: int = 300,
        trace_id: str | None = None,
    ) -> str | None:
        """Return a natural-language question, or None on any failure.

        The HIL service treats `None` as "fall back to pre_formed_question
        or empty string"; it MUST NOT raise. Implementations should catch
        their own errors and return None.
        """
        ...
