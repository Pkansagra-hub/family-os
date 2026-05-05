"""M13.E4 — DPB capsule survives compression.

The grounding capsule (M4 ``[grounding]`` block + the conscience /
self / preferences payload) is appended LAST in the DynamicPromptBuilder
assembly pipeline. The legacy ``_compress_prompt`` did naive head-cut
truncation, which dropped the capsule entirely whenever the assembled
prompt exceeded the token budget — destroying the only authoritative
source of conscience refusal in one pass.

These tests pin the new behaviour:

  1. Below budget → prompt unchanged.
  2. Above budget WITH a ``[grounding]`` capsule → capsule preserved
     verbatim at the tail; only the head is truncated; a structured
     ``capsule_truncated.v1`` warning is emitted.
  3. Above budget WITHOUT a capsule → legacy tail-cut still applies.
  4. Capsule alone exceeds budget → capsule preserved (over-budget
     warning emitted) rather than silently dropped.
"""

from __future__ import annotations

import logging

import pytest

from k1.concierge.prompt.builder import DynamicPromptBuilder


class _StubBuilder(DynamicPromptBuilder):
    """Subclass that exposes the two budget properties as overridable
    instance attributes for test purposes."""

    def __init__(self, max_context_tokens: int = 100, chars_per_token: int = 4) -> None:
        # Skip the real __init__; we only need the compress method.
        self._mct = max_context_tokens
        self._cpt = chars_per_token

    @property
    def _max_context_tokens(self) -> int:  # type: ignore[override]
        return self._mct

    @property
    def _chars_per_token(self) -> int:  # type: ignore[override]
        return self._cpt


@pytest.fixture
def builder() -> _StubBuilder:
    return _StubBuilder(max_context_tokens=100, chars_per_token=4)  # → 400 chars


def test_below_budget_returns_unchanged(builder: _StubBuilder) -> None:
    prompt = "head\n\n[grounding]\nshort capsule body"
    assert builder._compress_prompt(prompt) == prompt


def test_capsule_preserved_when_head_exceeds_budget(
    builder: _StubBuilder, caplog: pytest.LogCaptureFixture
) -> None:
    capsule = (
        "[grounding]\n"
        "[conscience]\nforbidden:\n  - tool.execute.prescribe_medication\n"
        "[self]\nname: Alice\n"
    )
    head = "X" * 800  # forces >400-char compression
    prompt = head + "\n\n" + capsule

    with caplog.at_level(logging.WARNING):
        compressed = builder._compress_prompt(prompt)

    # Capsule MUST appear verbatim at the end.
    assert compressed.endswith(capsule)
    # The conscience block must survive intact.
    assert "tool.execute.prescribe_medication" in compressed
    # Compression must respect (approximately) the budget.
    assert len(compressed) <= builder._max_context_tokens * builder._chars_per_token + len(capsule)
    # Structured telemetry was emitted.
    assert any("capsule_truncated.v1" in r.getMessage() for r in caplog.records)


def test_no_capsule_falls_back_to_legacy_tail_cut(builder: _StubBuilder) -> None:
    prompt = "Y" * 1000  # no [grounding] marker
    compressed = builder._compress_prompt(prompt)
    target = builder._max_context_tokens * builder._chars_per_token
    assert compressed.startswith("Y" * target)
    assert "[Context truncated for budget]" in compressed
    assert "capsule preserved" not in compressed


def test_capsule_alone_exceeds_budget_is_still_preserved(
    caplog: pytest.LogCaptureFixture,
) -> None:
    builder = _StubBuilder(max_context_tokens=10, chars_per_token=4)  # → 40 chars
    capsule = "[grounding]\n" + ("Z" * 200)  # 200+ chars, well over 40
    prompt = "head\n\n" + capsule

    with caplog.at_level(logging.WARNING):
        compressed = builder._compress_prompt(prompt)

    # The whole capsule survives even if it overflows the budget.
    assert compressed == capsule
    assert any("capsule_only_overflow" in r.getMessage() for r in caplog.records)
