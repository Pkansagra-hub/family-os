"""
ProceduralTextGenerator — GAP-001 Milestone 2

Generates embeddable text for st_procedural (procedural memory) records.
Routines represent learned sequences of actions and behaviors.

GAP Reference: GAP_001_CROSS_LAYER_VECTOR_LINKING.md §4
Milestone: GAP_001_MILESTONE_2_SUMMARY_GENERATOR.md Issue 2.4

Template: "Routine: {routine_name}. Steps: {steps}. Frequency: {frequency}"

Strategy: TEMPLATE (routines are already structured)

TIMESTAMP CONVENTION: All timestamps use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from k0.modules.consolidation.algorithms.embedding_text_generator import (
    EmbeddingTextGenerator,
    GeneratedText,
    TextGenerationStrategy,
)


class ProceduralTextGenerator(EmbeddingTextGenerator):
    """
    Generate embedding text for st_procedural (procedural memory) records.

    Routines represent action sequences:
    - Routine name and purpose
    - Ordered steps/actions
    - Frequency of execution
    - Typical duration
    - Associated triggers/cues

    Template:
        "Routine: {routine_name}. Steps: {steps}. Frequency: {frequency}"

    Example Output:
        "Routine: Morning coffee. Steps: Grind beans, heat water,
        prepare pour-over, wait 4 minutes. Frequency: daily, 7am"
    """

    @property
    def layer(self) -> str:
        return "st_procedural"

    def generate(
        self,
        record_data: Dict[str, Any],
        source_texts: Optional[List[str]] = None,
    ) -> GeneratedText:
        """
        Generate embedding text for a routine record.

        Args:
            record_data: Routine columns including:
                - routine_id: Routine identifier
                - family_id: Family context
                - routine_name: Name of the routine
                - description: Optional description
                - steps: Ordered list of steps
                - frequency: How often (daily, weekly, etc.)
                - typical_duration: Average duration in minutes
                - triggers: What initiates the routine
            source_texts: Original texts describing routine instances

        Returns:
            GeneratedText with embedding_text and source_texts_json
        """
        texts = source_texts or []
        record_id = str(record_data.get("routine_id", ""))

        # Get routine name
        routine_name = record_data.get("routine_name", "")
        if not routine_name:
            routine_name = record_data.get("name", "Unnamed routine")

        # Get description if available
        description = record_data.get("description", "")

        # Build steps string
        steps = self._build_steps(record_data)

        # Build frequency string
        frequency = self._build_frequency(record_data)

        # Build triggers string
        triggers = self._build_triggers(record_data)

        # Assemble using template
        parts = [f"Routine: {routine_name}"]

        if description:
            parts[0] += f" - {description}"

        if steps:
            parts.append(f"Steps: {steps}")

        if frequency:
            parts.append(f"Frequency: {frequency}")

        if triggers:
            parts.append(f"Triggers: {triggers}")

        embedding_text = ". ".join(parts)
        embedding_text = self._truncate(self._clean_text(embedding_text))

        return GeneratedText(
            embedding_text=embedding_text,
            source_texts_json=self._source_texts_to_json(texts),
            strategy_used=TextGenerationStrategy.TEMPLATE,
            layer=self.layer,
            record_id=record_id,
        )

    def _build_steps(self, record_data: Dict[str, Any]) -> str:
        """Build steps string from record data."""
        # Accept both 'steps' (expected) and 'action_sequence_json' (schema)
        steps = self._parse_json_field(record_data, "steps")
        if not steps:
            steps = self._parse_json_field(record_data, "action_sequence_json")

        if isinstance(steps, list):
            step_strs = []
            for i, step in enumerate(steps[:6]):  # Limit to 6 steps
                if isinstance(step, dict):
                    step_str = step.get("action") or step.get("description") or step.get("name", "")
                    if step_str:
                        step_strs.append(str(step_str))
                elif isinstance(step, str):
                    step_strs.append(step)

            if step_strs:
                return ", ".join(step_strs)

        return ""

    def _build_frequency(self, record_data: Dict[str, Any]) -> str:
        """Build frequency string."""
        frequency = record_data.get("frequency", "")
        typical_time = record_data.get("typical_time", "")
        typical_duration = record_data.get("typical_duration")

        parts = []

        if frequency:
            parts.append(str(frequency))

        if typical_time:
            parts.append(str(typical_time))

        if typical_duration and isinstance(typical_duration, (int, float)):
            if typical_duration >= 60:
                parts.append(f"{int(typical_duration // 60)}h duration")
            else:
                parts.append(f"{int(typical_duration)}min duration")

        return ", ".join(parts)

    def _build_triggers(self, record_data: Dict[str, Any]) -> str:
        """Build triggers string."""
        # Accept both 'triggers' (expected) and 'trigger_conditions_json' (schema)
        triggers = self._parse_json_field(record_data, "triggers")
        if not triggers:
            triggers = self._parse_json_field(record_data, "trigger_conditions_json")

        if isinstance(triggers, list) and triggers:
            trigger_strs = []
            for t in triggers[:3]:
                if isinstance(t, dict):
                    t_str = t.get("cue") or t.get("trigger") or t.get("name", "")
                    if t_str:
                        trigger_strs.append(str(t_str))
                elif isinstance(t, str):
                    trigger_strs.append(t)
            return ", ".join(trigger_strs)

        return ""
