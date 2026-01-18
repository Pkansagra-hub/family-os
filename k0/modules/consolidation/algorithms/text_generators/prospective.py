"""
ProspectiveTextGenerator — GAP-001 Milestone 2

Generates embeddable text for st_prospective (prospective memory) records.
Intentions represent future plans, goals, and commitments.

GAP Reference: GAP_001_CROSS_LAYER_VECTOR_LINKING.md §4
Milestone: GAP_001_MILESTONE_2_SUMMARY_GENERATOR.md Issue 2.6

Template: "Intention: {action} by {deadline}. Context: {conditions}"

Strategy: TEMPLATE (intentions are already structured)

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


class ProspectiveTextGenerator(EmbeddingTextGenerator):
    """
    Generate embedding text for st_prospective (prospective memory) records.

    Intentions capture future-oriented memory:
    - Planned action or goal
    - Deadline or target date
    - Triggering conditions
    - Priority and importance
    - Associated reminders

    Template:
        "Intention: {action} by {deadline}. Context: {conditions}"

    Example Output:
        "Intention: Call mom for her birthday by March 15.
        Context: After work, before dinner. Priority: high"
    """

    @property
    def layer(self) -> str:
        return "st_prospective"

    def generate(
        self,
        record_data: Dict[str, Any],
        source_texts: Optional[List[str]] = None,
    ) -> GeneratedText:
        """
        Generate embedding text for an intention record.

        Args:
            record_data: Intention columns including:
                - intention_id: Intention identifier
                - family_id: Family context
                - action: What needs to be done
                - description: Optional detailed description
                - deadline_ts: Target timestamp (milliseconds)
                - conditions: Triggering conditions
                - priority: Priority level (high, medium, low)
                - status: Current status (pending, completed, etc.)
                - reminders: Associated reminders
            source_texts: Original texts expressing the intention

        Returns:
            GeneratedText with embedding_text and source_texts_json
        """
        texts = source_texts or []
        record_id = str(record_data.get("intention_id", ""))

        # Get action description - accept 'action', 'description', or 'intention_description' (DB)
        action = (
            record_data.get("action")
            or record_data.get("description")
            or record_data.get("intention_description")
            or "Unnamed intention"
        )

        # Build deadline string
        deadline = self._build_deadline(record_data)

        # Build conditions string
        conditions = self._build_conditions(record_data)

        # Build priority string
        priority = self._build_priority(record_data)

        # Build status string
        status = self._build_status(record_data)

        # Assemble using template
        parts = [f"Intention: {action}"]

        if deadline:
            parts[0] += f" by {deadline}"

        context_parts = []
        if conditions:
            context_parts.append(conditions)
        if priority:
            context_parts.append(f"Priority: {priority}")
        if status:
            context_parts.append(f"Status: {status}")

        if context_parts:
            parts.append(f"Context: {'. '.join(context_parts)}")

        embedding_text = ". ".join(parts)
        embedding_text = self._truncate(self._clean_text(embedding_text))

        return GeneratedText(
            embedding_text=embedding_text,
            source_texts_json=self._source_texts_to_json(texts),
            strategy_used=TextGenerationStrategy.TEMPLATE,
            layer=self.layer,
            record_id=record_id,
        )

    def _build_deadline(self, record_data: Dict[str, Any]) -> str:
        """Build deadline string from timestamp."""
        # Accept 'deadline_ts', 'target_date' (expected), or 'trigger_time_ms' (schema)
        deadline_ts = (
            record_data.get("deadline_ts")
            or record_data.get("target_date")
            or record_data.get("trigger_time_ms")
        )

        if not deadline_ts:
            return ""

        try:
            if isinstance(deadline_ts, (int, float)):
                # Assume milliseconds
                deadline_dt = datetime.fromtimestamp(deadline_ts / 1000, tz=timezone.utc)
            elif isinstance(deadline_ts, str):
                # Try parsing ISO format
                deadline_dt = datetime.fromisoformat(deadline_ts.replace("Z", "+00:00"))
            else:
                return ""

            # Format as human-readable date
            now = datetime.now(timezone.utc)
            days_until = (deadline_dt - now).days

            if days_until < 0:
                return f"{deadline_dt.strftime('%B %d')} (overdue)"
            elif days_until == 0:
                return "today"
            elif days_until == 1:
                return "tomorrow"
            elif days_until < 7:
                return deadline_dt.strftime("%A")  # Day name
            else:
                return deadline_dt.strftime("%B %d")  # Month Day

        except (TypeError, ValueError, OSError):
            return ""

    def _build_conditions(self, record_data: Dict[str, Any]) -> str:
        """Build triggering conditions string."""
        conditions = self._parse_json_field(record_data, "conditions")

        if isinstance(conditions, list) and conditions:
            condition_strs = [str(c) for c in conditions[:3] if c]
            if condition_strs:
                return ", ".join(condition_strs)

        elif isinstance(conditions, dict):
            # Try to extract readable conditions
            when = conditions.get("when", "")
            where = conditions.get("where", "")
            trigger = conditions.get("trigger", "")

            parts = [p for p in [when, where, trigger] if p]
            if parts:
                return ", ".join(parts)

        return ""

    def _build_priority(self, record_data: Dict[str, Any]) -> str:
        """Build priority string."""
        priority = record_data.get("priority", "")

        if priority:
            return str(priority).lower()

        # Infer from importance score if available
        importance = record_data.get("importance")
        if importance is not None:
            try:
                imp_val = float(importance)
                if imp_val >= 0.8:
                    return "high"
                elif imp_val >= 0.5:
                    return "medium"
                else:
                    return "low"
            except (TypeError, ValueError):
                pass

        return ""

    def _build_status(self, record_data: Dict[str, Any]) -> str:
        """Build status string."""
        status = record_data.get("status", "")

        if status:
            status_lower = str(status).lower()
            if status_lower in ("pending", "active", "open"):
                return "pending"
            elif status_lower in ("completed", "done", "finished"):
                return "completed"
            elif status_lower in ("cancelled", "canceled", "dropped"):
                return "cancelled"
            return status_lower

        return ""
