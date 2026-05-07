"""
RawExtraction dataclass and PromptLoader utility.

RawExtraction is the mutable intermediate between LLM output parsing
and ExtractionValidator. NOT frozen -- the validator may mutate fields
(truncate text, resolve participants, strip location under RED band).

PromptLoader reads prompt templates from extraction/prompts/ directory.
Cached after first load for session lifetime.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class RawExtraction:
    """Mutable intermediate between LLM parse and validation.

    NOT frozen -- ExtractionValidator may:
      - Truncate text to 50 words (MW-04)
      - Replace participants with PersonResolution results
      - Strip location under RED band
    """

    # Core content
    text: str = ""
    topics: List[str] = field(default_factory=list)
    categories: List[str] = field(default_factory=list)
    activity_type: Optional[str] = None

    # Participants (natural names -- not yet resolved)
    participants: List[str] = field(default_factory=list)
    social_context: Optional[str] = None
    social_intimacy: Optional[str] = None

    # Location
    location_name: Optional[str] = None
    location_type: Optional[str] = None

    # Emotion
    sentiment_label: str = "neutral"
    emotion_tags: List[str] = field(default_factory=list)
    affect: Optional[Dict[str, float]] = None

    # Temporal
    temporal_links: List[Dict[str, object]] = field(default_factory=list)
    temporal_orientation: str = "PAST"

    # Cognitive dimensions
    source_type: str = "user_stated"
    novelty: str = "EXPECTED"
    elaboration_depth: str = "MENTION"
    intent_type: Optional[str] = None
    identity_domains: List[str] = field(default_factory=list)
    confidence: float = 0.0

    # Narrative
    narrative: Optional[Dict[str, object]] = None

    # v2.2 correction signals
    correction_signal: bool = False
    contradiction_signal: bool = False
    supersedes_concept: Optional[str] = None
    correction_source: Optional[str] = None

    # Metadata (injected from context, not LLM output)
    session_id: str = ""
    conversation_turn: int = 0
    extraction_sequence: int = 0
    trace_id: str = ""


class PromptLoader:
    """Load prompt templates from the extraction/prompts/ directory.

    Templates are markdown files with the system prompt text.
    Loaded once at agent creation, cached for session lifetime.
    """

    __slots__ = ("_dir", "_cache")

    def __init__(self, prompts_dir: Path) -> None:
        self._dir = prompts_dir
        self._cache: Dict[str, str] = {}

    def load(self, name: str) -> str:
        """Load a named prompt template. Cached after first load."""
        if name not in self._cache:
            path = self._dir / f"{name}.md"
            self._cache[name] = path.read_text(encoding="utf-8")
        return self._cache[name]
