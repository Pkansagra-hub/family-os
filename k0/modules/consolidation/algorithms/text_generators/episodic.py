"""
EpisodicTextGenerator — GAP-001 Milestone 2

Generates embeddable text for st_epi (episodic memory) records.
Episodes contain temporal and contextual information about events.

GAP Reference: GAP_001_CROSS_LAYER_VECTOR_LINKING.md §4
Milestone: GAP_001_MILESTONE_2_SUMMARY_GENERATOR.md Issue 2.2

Template: "{temporal_context} episode: {summary}. Context: {location}, {participants}"

Strategies:
    - ≤3 events → CONCATENATE source texts
    - 4-5 events → TEXTRANK to select key sentences
    - >5 events → NARRATIVE_ARC (first + peak + last)

TIMESTAMP CONVENTION: All timestamps use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from k0.modules.consolidation.algorithms.embedding_text_generator import (
    EmbeddingTextGenerator,
    GeneratedText,
    TextGenerationStrategy,
)
from k0.modules.consolidation.algorithms.text_generators.textrank import (
    narrative_arc_summarize,
    textrank_summarize,
)


class EpisodicTextGenerator(EmbeddingTextGenerator):
    """
    Generate embedding text for st_epi (episodic memory) records.

    Episodes represent time-bounded experiences with context:
    - Temporal information (when, duration)
    - Location information (where)
    - Participants (who)
    - Event summaries (what happened)

    Template:
        "{temporal_context} episode: {summary}. Context: {location}, {participants}"

    Example Output:
        "Friday evening episode: Had dinner with mom, ordered Thai food,
        talked about her garden. Context: Thai Orchid restaurant, with mom"
    """

    @property
    def layer(self) -> str:
        return "st_epi"

    def generate(
        self,
        record_data: Dict[str, Any],
        source_texts: Optional[List[str]] = None,
    ) -> GeneratedText:
        """
        Generate embedding text for an episode record.

        Args:
            record_data: Episode columns including:
                - episode_id: Episode identifier
                - family_id: Family context
                - summary: Optional pre-computed summary
                - start_ts: Start timestamp (milliseconds)
                - end_ts: End timestamp (milliseconds)
                - location_json: Location metadata
                - participants: List of participant IDs
                - emotion_scores: Optional emotion intensity per event
            source_texts: Original event texts from which episode was derived

        Returns:
            GeneratedText with embedding_text and source_texts_json
        """
        texts = source_texts or []
        record_id = str(record_data.get("episode_id", ""))

        # Determine strategy based on number of source texts
        strategy = self._select_strategy(len(texts))

        # Generate summary from source texts
        summary = self._generate_summary(record_data, texts, strategy)

        # Build temporal context
        temporal_context = self._build_temporal_context(record_data)

        # Build location context
        location = self._build_location_context(record_data)

        # Build participants context
        participants = self._build_participants_context(record_data)

        # Assemble final text using template
        parts = [f"{temporal_context} episode"]

        if summary:
            parts[0] += f": {summary}"

        context_parts = []
        if location:
            context_parts.append(location)
        if participants:
            context_parts.append(participants)

        if context_parts:
            parts.append(f"Context: {', '.join(context_parts)}")

        embedding_text = ". ".join(parts)
        embedding_text = self._truncate(self._clean_text(embedding_text))

        return GeneratedText(
            embedding_text=embedding_text,
            source_texts_json=self._source_texts_to_json(texts),
            strategy_used=strategy,
            layer=self.layer,
            record_id=record_id,
        )

    def _select_strategy(self, num_texts: int) -> TextGenerationStrategy:
        """Select generation strategy based on number of source texts."""
        if num_texts <= 3:
            return TextGenerationStrategy.CONCATENATE
        elif num_texts <= self.TEXTRANK_THRESHOLD:
            return TextGenerationStrategy.TEXTRANK
        else:
            return TextGenerationStrategy.NARRATIVE_ARC

    def _generate_summary(
        self,
        record_data: Dict[str, Any],
        texts: List[str],
        strategy: TextGenerationStrategy,
    ) -> str:
        """Generate summary text based on strategy."""
        # Check if pre-computed summary exists (try both field names)
        existing_summary = record_data.get("summary") or record_data.get("episode_summary")
        if existing_summary and isinstance(existing_summary, str):
            return existing_summary

        if not texts:
            return ""

        if strategy == TextGenerationStrategy.CONCATENATE:
            return self._concatenate_texts(texts, separator="; ")

        elif strategy == TextGenerationStrategy.TEXTRANK:
            top_sentences = textrank_summarize(texts, top_k=3)
            return self._concatenate_texts(top_sentences, separator="; ")

        elif strategy == TextGenerationStrategy.NARRATIVE_ARC:
            emotion_scores = self._parse_json_field(record_data, "emotion_scores")
            arc_sentences = narrative_arc_summarize(
                texts,
                emotion_scores=emotion_scores if isinstance(emotion_scores, list) else None,
            )
            return self._concatenate_texts(arc_sentences, separator="; ")

        return self._concatenate_texts(texts[:3], separator="; ")

    def _build_temporal_context(self, record_data: Dict[str, Any]) -> str:
        """Build temporal context string from timestamps."""
        # Accept both expected and schema field names
        start_ts = (
            record_data.get("start_ts")
            or record_data.get("start_time_utc")
            or record_data.get("started_at_ms")
        )
        end_ts = (
            record_data.get("end_ts")
            or record_data.get("end_time_utc")
            or record_data.get("ended_at_ms")
        )

        if not start_ts:
            return "An"

        try:
            # Convert milliseconds to datetime
            start_dt = datetime.fromtimestamp(start_ts / 1000, tz=timezone.utc)

            # Get day of week and time of day
            day_name = start_dt.strftime("%A")  # e.g., "Friday"
            hour = start_dt.hour

            if 5 <= hour < 12:
                time_of_day = "morning"
            elif 12 <= hour < 17:
                time_of_day = "afternoon"
            elif 17 <= hour < 21:
                time_of_day = "evening"
            else:
                time_of_day = "night"

            # Calculate duration if end_ts available
            duration_str = ""
            if end_ts and end_ts > start_ts:
                duration_mins = (end_ts - start_ts) / 60000  # ms to minutes
                if duration_mins >= 120:  # 2+ hours
                    hours = int(duration_mins // 60)
                    duration_str = f" ({hours}h)"
                elif duration_mins >= 60:
                    mins = int(duration_mins % 60)
                    duration_str = f" (1h {mins}min)" if mins else " (1h)"
                elif duration_mins >= 5:  # Skip tiny durations
                    duration_str = f" ({int(duration_mins)}min)"
                # Skip durations < 5 minutes - not meaningful

            return f"{day_name} {time_of_day}{duration_str}"

        except (TypeError, ValueError, OSError):
            return "An"

    def _build_location_context(self, record_data: Dict[str, Any]) -> str:
        """Build location context from location_json or primary_location."""
        # Try schema field first (primary_location is a string)
        primary_location = record_data.get("primary_location")
        if primary_location and isinstance(primary_location, str):
            return primary_location

        # Fall back to location_json (nested object)
        location = self._parse_json_field(record_data, "location_json", default={})

        if isinstance(location, dict):
            # Try common location field names
            for key in ["name", "place_name", "location", "venue", "address"]:
                if key in location and location[key]:
                    return str(location[key])

        return ""

    def _build_participants_context(self, record_data: Dict[str, Any]) -> str:
        """Build participants context string."""
        # Try both field names (participants vs participants_json)
        participants = self._parse_json_field(record_data, "participants")
        if not participants:
            participants = self._parse_json_field(record_data, "participants_json")

        if not participants:
            return ""

        if isinstance(participants, list):
            # Filter out empty/None values
            names = [str(p) for p in participants if p]
            if not names:
                return ""
            if len(names) == 1:
                return f"with {names[0]}"
            elif len(names) == 2:
                return f"with {names[0]} and {names[1]}"
            elif len(names) <= 5:
                # List all participants for small groups
                return f"with {', '.join(names[:-1])}, and {names[-1]}"
            else:
                # Only summarize for large groups
                return f"with {', '.join(names[:3])}, and {len(names) - 3} others"

        return ""
