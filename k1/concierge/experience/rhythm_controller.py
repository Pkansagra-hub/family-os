"""
k1.concierge.experience.rhythm_controller -- RhythmController + ResponseStyleAdapter.

Controls pacing and rhythm of responses, and adapts to the user's
communication style (verbosity, message length, conversational pattern).

V2 Design Ref: Section 12.3.6
Whiteboard: docs/whiteboard/whiteboard_experience_layer.md

Fire cadence: every output (before delivery to user).
Budget: 0.5 ms (counters and running averages).
Reads: turn timing, user cadence patterns, conversation_history.
Writes: TimingParams applied to output delivery pipeline.
        ResponseStyle stored on self.last_response_style for bootstrap to read.

ResponseStyleAdapter logic:
  - Learns user's communication preferences from conversation data.
  - Short messages (<30 chars avg) -> concise responses.
  - Long messages (>100 chars avg) -> detailed responses.
  - Rapid-fire pattern (many messages within short gaps) -> conversational bursts.
  - Adapts verbosity_level 0.0-1.0 to shape LLM prompt guidance.
  - Zero latency added: shapes WHAT the LLM generates, not WHEN it delivers.

All methods are SYNC (not async) -- timing calculations must be
fast (<1ms) with no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TimingParams:
    """Output of RhythmController. Applied by delivery pipeline before streaming."""

    pre_delay_ms: int = 0  # Pause before response
    inter_chunk_ms: int = 0  # Pause between streaming chunks
    typing_indicator: bool = False  # Show typing indicator
    beat_pattern: str = "steady"  # "steady" | "syncopated" | "accelerating"


@dataclass
class ResponseStyle:
    """User communication style learned from conversation patterns.

    Computed by RhythmController each tick from user_cadence and
    conversation_history. Written to SS by bootstrap for
    DynamicPromptBuilder to consume as advisory prompt hints.
    """

    response_length_preference: str = "balanced"  # "concise" | "balanced" | "detailed"
    message_style: str = "single_complete"  # "single_complete" | "conversational_bursts"
    verbosity_level: float = 0.5  # 0.0 (terse) to 1.0 (verbose)


# Thresholds for response length preference
_SHORT_MSG_THRESHOLD = 30  # chars
_LONG_MSG_THRESHOLD = 100  # chars

# Threshold for burst detection: if avg gap between user messages
# is under this value, user prefers quick back-and-forth
_BURST_GAP_THRESHOLD_MS = 5000  # 5 seconds


def _compute_response_style(
    user_cadence: dict,
    conversation_history: list[dict],
) -> ResponseStyle:
    """Compute ResponseStyle from user conversation patterns.

    Args:
        user_cadence: Dict with avg_gap_ms, last_gap_ms, sample_count
            (from _build_experience_context).
        conversation_history: List of TypedHistoryEntry dicts with
            turn_number, entry_type, text, timestamp_ms, source.

    Returns:
        ResponseStyle reflecting user's communication preferences.
    """
    # Extract user messages from conversation history
    user_texts = [
        e.get("text", "")
        for e in conversation_history
        if e.get("source") == "user" and e.get("text")
    ]

    if not user_texts:
        return ResponseStyle()

    # Average user message length
    avg_len = sum(len(t) for t in user_texts) / len(user_texts)

    # Response length preference from message length
    if avg_len < _SHORT_MSG_THRESHOLD:
        length_pref = "concise"
        verbosity = 0.3
    elif avg_len > _LONG_MSG_THRESHOLD:
        length_pref = "detailed"
        verbosity = 0.7
    else:
        length_pref = "balanced"
        # Linear interpolation between 0.3 and 0.7
        verbosity = 0.3 + 0.4 * (avg_len - _SHORT_MSG_THRESHOLD) / (
            _LONG_MSG_THRESHOLD - _SHORT_MSG_THRESHOLD
        )

    # Message style from cadence (rapid-fire vs composed)
    msg_style = "single_complete"
    avg_gap = user_cadence.get("avg_gap_ms", 0)
    if avg_gap > 0 and avg_gap < _BURST_GAP_THRESHOLD_MS:
        sample_count = user_cadence.get("sample_count", 0)
        if sample_count >= 2:
            msg_style = "conversational_bursts"
            # Burst users prefer even more concise responses
            verbosity = max(0.2, verbosity - 0.1)

    return ResponseStyle(
        response_length_preference=length_pref,
        message_style=msg_style,
        verbosity_level=round(verbosity, 3),
    )


class RhythmController:
    """Controls pacing and adapts to user communication style.

    Fire cadence: every output.
    Budget: 0.5 ms.

    Computes ResponseStyle from user_cadence and stores it on
    self.last_response_style for bootstrap to read after tick().
    TimingParams remain at defaults (delivery timing deferred).
    """

    def __init__(self) -> None:
        self.last_response_style: ResponseStyle = ResponseStyle()

    def get_pattern(
        self,
        turn_count: int,
        user_cadence: dict,
    ) -> TimingParams:
        """Compute timing params and update response style.

        Args:
            turn_count: Current turn number.
            user_cadence: Dict with avg_gap_ms, last_gap_ms, sample_count,
                and optionally conversation_history for style computation.

        Returns:
            TimingParams (delivery timing, currently defaults).
        """
        # Extract conversation_history if passed through user_cadence
        # (bootstrap puts it in the context, layer passes user_cadence subset)
        conv_history = (
            user_cadence.pop("_conversation_history", []) if isinstance(user_cadence, dict) else []
        )
        self.last_response_style = _compute_response_style(user_cadence, conv_history)
        return TimingParams()

    def get_beat(self, output_length: int) -> str:
        return "steady"

    def adjust_timing(
        self,
        current: TimingParams,
        feedback: dict,
    ) -> TimingParams:
        return current
