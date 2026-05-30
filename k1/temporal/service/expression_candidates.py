"""Temporal expression candidate helpers."""

from __future__ import annotations

from k1.temporal.types import CandidateSpan


def normalize_candidate_text(text: str) -> str:
    """Normalize a candidate without regex or prompt scraping."""

    cleaned = text.replace("_", " ").replace("-", " ").strip().lower()
    return " ".join(cleaned.split())


def ensure_candidate(value: str | CandidateSpan, *, locale: str = "en-US") -> CandidateSpan:
    if isinstance(value, CandidateSpan):
        return value
    return CandidateSpan(text=value, locale=locale)


__all__ = ["ensure_candidate", "normalize_candidate_text"]
