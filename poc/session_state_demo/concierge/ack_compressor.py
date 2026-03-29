"""
ACK Compressor
==============

Fix 4: ACKING must compress state meaningfully.

BAD ACK: "I've noted that information."
GOOD ACK: "Got it - Sonoma, two nights starting Saturday, relaxing vibe, under $1500"

The ACK must:
1. Restate what CHANGED this turn (not everything)
2. Signal PROGRESS toward the goal
3. Never be empty/meaningless filler

Format: "[ACK] {what_changed} -> {progress_signal}"
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from poc.session_state_demo.anniversary_demo.plan import PlanController

logger = logging.getLogger(__name__)


@dataclass
class StateChange:
    """A single state change to acknowledge."""

    category: str  # beliefs, persona, plan, booking, etc.
    description: str  # What changed
    importance: float  # 0-1, higher = more important to mention


@dataclass
class CompressedAck:
    """A compressed acknowledgment."""

    summary: str  # The compressed ACK text
    changes: List[StateChange]  # What changed
    progress_signal: str  # Progress toward goal


class AckCompressor:
    """
    Compresses turn state into meaningful acknowledgments.

    This is NOT about being verbose - it's about being MEANINGFUL.
    Every ACK should tell the user what changed and where we are.
    """

    def __init__(self, plan_controller: Optional["PlanController"] = None):
        self._plan_controller = plan_controller

    def compress(
        self,
        user_input: str,
        tool_calls: List[Dict[str, Any]],
        beliefs_added: Optional[List[Dict[str, Any]]] = None,
        persona_updated: Optional[Dict[str, Any]] = None,
        plan_changes: Optional[Dict[str, Any]] = None,
    ) -> CompressedAck:
        """
        Compress turn state into a meaningful ACK.

        Args:
            user_input: What the user said
            tool_calls: Tools that were called
            beliefs_added: New beliefs added this turn
            persona_updated: Persona changes this turn
            plan_changes: Plan changes this turn

        Returns:
            CompressedAck with summary and changes
        """
        changes: List[StateChange] = []

        # Extract changes from tool calls
        for call in tool_calls or []:
            tool_name = call.get("name", "")
            args = call.get("args", {})

            if tool_name == "add_belief":
                changes.append(
                    StateChange(
                        category="belief",
                        description=f"{args.get('subject')} {args.get('predicate')} {args.get('object')}",
                        importance=0.8,
                    )
                )

            elif tool_name == "update_persona":
                changes.append(
                    StateChange(
                        category="preference",
                        description=f"{args.get('trait')}: {args.get('value')}",
                        importance=0.7,
                    )
                )

            elif "book" in tool_name:
                changes.append(
                    StateChange(
                        category="booking",
                        description=f"Booked {tool_name.replace('book_', '')}",
                        importance=1.0,  # Bookings are high importance
                    )
                )

            elif "search" in tool_name:
                changes.append(
                    StateChange(
                        category="search",
                        description=f"Searched for {args.get('query', args.get('location', 'options'))}",
                        importance=0.6,
                    )
                )

            elif tool_name == "spawn_agent":
                agent_type = args.get("agent_type", "")
                task_type = args.get("task_type", "")
                changes.append(
                    StateChange(
                        category="agent",
                        description=f"Started {agent_type} for {task_type}",
                        importance=0.5,
                    )
                )

        # Add explicit belief/persona changes if provided
        for belief in beliefs_added or []:
            changes.append(
                StateChange(
                    category="belief",
                    description=str(belief),
                    importance=0.8,
                )
            )

        if persona_updated:
            for trait, value in persona_updated.items():
                changes.append(
                    StateChange(
                        category="preference",
                        description=f"{trait}: {value}",
                        importance=0.7,
                    )
                )

        # Build progress signal from plan
        progress_signal = self._build_progress_signal()

        # Build summary
        summary = self._build_summary(changes, progress_signal)

        return CompressedAck(
            summary=summary,
            changes=changes,
            progress_signal=progress_signal,
        )

    def _build_progress_signal(self) -> str:
        """Build progress signal from plan state."""
        if not self._plan_controller:
            return ""

        plan = self._plan_controller.plan

        # Get completion stats
        pct = plan.completion_percent
        pending = plan.open_items

        if pct == 0:
            return "Just getting started"
        elif pct < 50:
            open_names = [item.category for item in pending[:2]]
            return f"Still need: {', '.join(open_names)}"
        elif pct < 100:
            open_names = [item.category for item in pending]
            return f"Almost there - {', '.join(open_names)} left"
        else:
            return "All set!"

    def _build_summary(
        self,
        changes: List[StateChange],
        progress_signal: str,
    ) -> str:
        """Build the compressed ACK summary."""
        if not changes:
            return "Got it."

        # Sort by importance
        changes = sorted(changes, key=lambda c: c.importance, reverse=True)

        # Take top 3 changes
        top_changes = changes[:3]

        # Build parts
        parts = []

        # High importance items get full mention
        for change in top_changes:
            if change.importance >= 0.8:
                parts.append(change.description)
            elif change.importance >= 0.5:
                parts.append(change.category)

        if not parts:
            return "Got it."

        # Combine
        summary = "Got it - " + ", ".join(parts)

        # Add progress signal if available
        if progress_signal:
            summary += f". {progress_signal}."

        return summary

    def compress_for_prompt(
        self,
        changes: List[StateChange],
        progress_signal: str,
    ) -> str:
        """
        Compress for injection into LLM prompt.

        This tells the LLM what to emphasize in its response.
        """
        if not changes:
            return ""

        lines = ["ACK GUIDANCE (incorporate into response):"]

        # High importance changes must be acknowledged
        high_importance = [c for c in changes if c.importance >= 0.8]
        if high_importance:
            lines.append("MUST acknowledge:")
            for change in high_importance:
                lines.append(f"  - {change.description}")

        # Medium importance can be mentioned
        medium_importance = [c for c in changes if 0.5 <= c.importance < 0.8]
        if medium_importance:
            lines.append("Consider mentioning:")
            for change in medium_importance:
                lines.append(f"  - {change.category}")

        # Progress signal
        if progress_signal:
            lines.append(f"Progress: {progress_signal}")

        return "\n".join(lines)


def create_ack_compressor(
    plan_controller: Optional["PlanController"] = None,
) -> AckCompressor:
    """Create an ACK compressor."""
    return AckCompressor(plan_controller=plan_controller)
