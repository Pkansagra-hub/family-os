"""
TemporalParser — Convert UltraBERT temporal_json to Unix timestamps.

UltraBERT Temporal Head (P02) provides labeled entities like:
    {"entities": [{"text": "tomorrow at 3pm", "label": "TIME"}]}

This parser converts those text labels into Unix millisecond timestamps
for storage in st_prospective.target_date.

Handles relative dates (tomorrow, next week) and absolute dates.
Does NOT re-run NER - uses existing UltraBERT output from st_hipp_events.

Spec Reference:
    - INTENT_INGRESS_MATRIX_IMPLEMENTATION_PLAN.md Phase 6
    - P02 Pipeline (temporal head output format)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import List, Optional


class TemporalLabel(str, Enum):
    """Temporal entity labels from UltraBERT."""

    DATE_REL = "DATE_REL"  # Relative date: tomorrow, next week
    TIME_REL = "TIME_REL"  # Relative time: in an hour, in 30 minutes
    DATE_ABS = "DATE_ABS"  # Absolute date: January 15, 2025
    TIME_ABS = "TIME_ABS"  # Absolute time: 3:00 PM
    TIME = "TIME"  # Generic time reference
    DATE = "DATE"  # Generic date reference
    DURATION = "DURATION"  # Duration: for 2 hours


@dataclass
class TemporalEntity:
    """Parsed temporal entity from UltraBERT output."""

    text: str
    label: str
    start: Optional[int] = None  # Character offset in original text
    end: Optional[int] = None


@dataclass
class ParseResult:
    """Result of temporal parsing."""

    timestamp_ms: Optional[int]  # Unix ms timestamp
    entity: Optional[TemporalEntity]  # Source entity
    confidence: float  # Parsing confidence [0.0, 1.0]
    parse_method: str  # Method used (relative, absolute, pattern)


class TemporalParser:
    """
    Parses temporal expressions to Unix ms timestamps.

    Converts UltraBERT temporal_json output to actual timestamps
    for storage in st_prospective.target_date.

    Supports:
        - Relative dates: tomorrow, next week, next Monday
        - Relative times: in an hour, in 30 minutes
        - Absolute times: 3pm, 15:00, 3:30 PM
        - Combined: tomorrow at 3pm, next Monday at 10am
    """

    # Relative date patterns
    RELATIVE_DATE_PATTERNS = {
        r"\btomorrow\b": lambda ref: ref + timedelta(days=1),
        r"\btoday\b": lambda ref: ref,
        r"\byesterday\b": lambda ref: ref - timedelta(days=1),
        r"\bnext\s+week\b": lambda ref: ref + timedelta(weeks=1),
        r"\bnext\s+month\b": lambda ref: ref + timedelta(days=30),
        r"\bthis\s+weekend\b": lambda ref: ref + timedelta(days=(5 - ref.weekday()) % 7),
        r"\bnext\s+monday\b": lambda ref: ref + timedelta(days=(7 - ref.weekday()) % 7 or 7),
        r"\bnext\s+tuesday\b": lambda ref: ref + timedelta(days=(8 - ref.weekday()) % 7 or 7),
        r"\bnext\s+wednesday\b": lambda ref: ref + timedelta(days=(9 - ref.weekday()) % 7 or 7),
        r"\bnext\s+thursday\b": lambda ref: ref + timedelta(days=(10 - ref.weekday()) % 7 or 7),
        r"\bnext\s+friday\b": lambda ref: ref + timedelta(days=(11 - ref.weekday()) % 7 or 7),
        r"\bnext\s+saturday\b": lambda ref: ref + timedelta(days=(12 - ref.weekday()) % 7 or 7),
        r"\bnext\s+sunday\b": lambda ref: ref + timedelta(days=(13 - ref.weekday()) % 7 or 7),
    }

    # Relative time patterns
    RELATIVE_TIME_PATTERNS = {
        r"\bin\s+an?\s+hour\b": lambda ref: ref + timedelta(hours=1),
        r"\bin\s+(\d+)\s+hour": lambda ref, m: ref + timedelta(hours=int(m.group(1))),
        r"\bin\s+(\d+)\s+minute": lambda ref, m: ref + timedelta(minutes=int(m.group(1))),
        r"\bin\s+half\s+an?\s+hour\b": lambda ref: ref + timedelta(minutes=30),
        r"\bin\s+(\d+)\s+day": lambda ref, m: ref + timedelta(days=int(m.group(1))),
        r"\bin\s+(\d+)\s+week": lambda ref, m: ref + timedelta(weeks=int(m.group(1))),
    }

    def __init__(self):
        """Initialize the temporal parser."""
        # Compile patterns for efficiency
        self._date_patterns = [
            (re.compile(p, re.IGNORECASE), fn) for p, fn in self.RELATIVE_DATE_PATTERNS.items()
        ]
        self._time_patterns = [
            (re.compile(p, re.IGNORECASE), fn) for p, fn in self.RELATIVE_TIME_PATTERNS.items()
        ]
        # Time extraction pattern: 3pm, 3:30pm, 15:00
        self._time_extract = re.compile(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", re.IGNORECASE)

    def parse_temporal_json(
        self,
        temporal_json: str,
        reference_time: int,
    ) -> Optional[int]:
        """
        Parse temporal_json and return target timestamp.

        Args:
            temporal_json: JSON string from st_hipp_events.temporal_json
            reference_time: Reference time in ms (REQUIRED - event observation time)

        Returns:
            Unix ms timestamp or None if no parseable date
        """
        if not temporal_json:
            return None

        try:
            data = json.loads(temporal_json)
        except json.JSONDecodeError:
            return None

        # UltraBERT temporal format: {"entities": [{"text": "tomorrow", "label": "DATE_REL"}]}
        entities = data.get("entities", [])
        if not entities:
            return None

        # Find first temporal entity
        for entity in entities:
            label = entity.get("label", "")
            text = entity.get("text", "")

            if label in (
                "DATE_REL",
                "TIME_REL",
                "DATE_ABS",
                "TIME_ABS",
                "TIME",
                "DATE",
            ):
                result = self._parse_temporal_text(text, reference_time)
                if result is not None:
                    return result

        return None

    def parse_temporal_json_full(
        self,
        temporal_json: str,
        reference_time: int,
    ) -> ParseResult:
        """
        Parse temporal_json with full result details.

        Args:
            temporal_json: JSON string from st_hipp_events.temporal_json
            reference_time: Reference time in ms (REQUIRED - event observation time)

        Returns:
            ParseResult with timestamp, source entity, and confidence
        """
        if not temporal_json:
            return ParseResult(
                timestamp_ms=None,
                entity=None,
                confidence=0.0,
                parse_method="none",
            )

        try:
            data = json.loads(temporal_json)
        except json.JSONDecodeError:
            return ParseResult(
                timestamp_ms=None,
                entity=None,
                confidence=0.0,
                parse_method="json_error",
            )

        entities = data.get("entities", [])
        if not entities:
            return ParseResult(
                timestamp_ms=None,
                entity=None,
                confidence=0.0,
                parse_method="no_entities",
            )

        # Parse all entities and return best result
        results: List[ParseResult] = []

        for entity_data in entities:
            label = entity_data.get("label", "")
            text = entity_data.get("text", "")

            entity = TemporalEntity(
                text=text,
                label=label,
                start=entity_data.get("start"),
                end=entity_data.get("end"),
            )

            if label in (
                "DATE_REL",
                "TIME_REL",
                "DATE_ABS",
                "TIME_ABS",
                "TIME",
                "DATE",
            ):
                timestamp = self._parse_temporal_text(text, reference_time)
                if timestamp is not None:
                    # Determine confidence based on label specificity
                    confidence = 0.9 if label.endswith("_REL") or label.endswith("_ABS") else 0.7
                    results.append(
                        ParseResult(
                            timestamp_ms=timestamp,
                            entity=entity,
                            confidence=confidence,
                            parse_method="pattern_match",
                        )
                    )

        if results:
            # Return highest confidence result
            return max(results, key=lambda r: r.confidence)

        return ParseResult(
            timestamp_ms=None,
            entity=None,
            confidence=0.0,
            parse_method="no_match",
        )

    def _parse_temporal_text(
        self,
        text: str,
        ref_time: int,
    ) -> Optional[int]:
        """
        Parse natural language temporal expression.

        Args:
            text: Temporal expression text
            ref_time: Reference time in ms (REQUIRED - event observation time)

        Returns:
            Unix ms timestamp or None
        """
        ref = datetime.fromtimestamp(ref_time / 1000)
        text_lower = text.lower().strip()

        # Try relative date patterns
        target_date = self._try_relative_date(text_lower, ref)

        # Try relative time patterns
        if target_date is None:
            result = self._try_relative_time(text_lower, ref)
            if result is not None:
                return int(result.timestamp() * 1000)

        # If we have a date, apply any time component
        if target_date is not None:
            return self._apply_time(target_date, text_lower)

        # Try absolute time only (for today)
        time_result = self._try_absolute_time(text_lower, ref)
        if time_result is not None:
            return int(time_result.timestamp() * 1000)

        return None

    def _try_relative_date(
        self,
        text: str,
        ref: datetime,
    ) -> Optional[datetime]:
        """Try to match relative date patterns."""
        for pattern, fn in self._date_patterns:
            if pattern.search(text):
                return fn(ref)
        return None

    def _try_relative_time(
        self,
        text: str,
        ref: datetime,
    ) -> Optional[datetime]:
        """Try to match relative time patterns."""
        for pattern, fn in self._time_patterns:
            match = pattern.search(text)
            if match:
                # Check if function expects match groups
                import inspect

                sig = inspect.signature(fn)
                if len(sig.parameters) > 1:
                    return fn(ref, match)
                else:
                    return fn(ref)
        return None

    def _try_absolute_time(
        self,
        text: str,
        ref: datetime,
    ) -> Optional[datetime]:
        """
        Try to parse absolute time reference.

        Handles: 3pm, 3:30pm, 15:00, 3:00 PM
        """
        match = self._time_extract.search(text)
        if not match:
            return None

        hour = int(match.group(1))
        minute = int(match.group(2) or 0)
        meridiem = match.group(3)

        # Convert to 24-hour format
        if meridiem:
            if meridiem.lower() == "pm" and hour < 12:
                hour += 12
            elif meridiem.lower() == "am" and hour == 12:
                hour = 0

        # Validate hour
        if hour > 23:
            return None

        return ref.replace(hour=hour, minute=minute, second=0, microsecond=0)

    def _apply_time(self, date: datetime, text: str) -> int:
        """
        Apply time component to a date if specified.

        Args:
            date: Base date
            text: Original text that may contain time

        Returns:
            Unix ms timestamp
        """
        match = self._time_extract.search(text)
        if match:
            hour = int(match.group(1))
            minute = int(match.group(2) or 0)
            meridiem = match.group(3)

            if meridiem:
                if meridiem.lower() == "pm" and hour < 12:
                    hour += 12
                elif meridiem.lower() == "am" and hour == 12:
                    hour = 0

            # Validate and apply
            if hour <= 23:
                date = date.replace(hour=hour, minute=minute, second=0, microsecond=0)

        return int(date.timestamp() * 1000)


def create_temporal_parser() -> TemporalParser:
    """Factory function to create TemporalParser instance."""
    return TemporalParser()


def parse_temporal_expression(
    temporal_json: str,
    reference_time: int,
) -> Optional[int]:
    """
    Convenience function to parse temporal expression.

    Args:
        temporal_json: JSON string from st_hipp_events.temporal_json
        reference_time: Reference time in ms (REQUIRED - event observation time)

    Returns:
        Unix ms timestamp or None
    """
    parser = TemporalParser()
    return parser.parse_temporal_json(temporal_json, reference_time)
