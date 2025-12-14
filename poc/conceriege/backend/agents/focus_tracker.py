"""
Conversation Focus Tracker - Prevents context switching during discussions.

TOPIC 5: PROACTIVITY TIMING

This module implements rule-based focus tracking to prevent the agent from
interrupting user conversations with proactive findings at inappropriate times.

Key Features:
- Tracks conversation focus state (reactive, proactive, insight_thread)
- Detects user curiosity and sustains insight discussions for 3 turns
- Prevents interrupting long messages or questions
- Detects resolution/closure markers to release focus lock
- Ultra-fast rule-based operation (<5ms)

Not LLM-based - uses fast pattern matching for real-time responsiveness.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Optional


@dataclass
class FocusState:
    """Tracks current conversation focus state"""

    current_focus: Literal["reactive", "proactive", "insight_thread"]
    """What mode are we in: normal chat, about to inject finding, or discussing insight"""

    locked_insight_id: Optional[str] = None
    """ID of the locked insight (for tracking which finding is being discussed)"""

    insight_turn_count: int = 0
    """How many turns into the insight discussion (max 3)"""

    last_insight_message: Optional[str] = None
    """The last proactive insight we shared (to continue discussion about it)"""

    last_update: Optional[datetime] = None
    """When focus state last changed"""

    # NEW: Floor control & consent tracking
    last_inject_ts: Optional[float] = None
    """Timestamp of last proactive injection (for cooldown)"""

    cooldown_secs: int = 30
    """Minimum seconds between proactive injections"""

    topic_of_last_inject: Optional[str] = None
    """Topic of last injection (for alignment check)"""

    has_permission: bool = False
    """User granted permission for next proactive injection"""

    user_typing: bool = False
    """User is currently typing (don't interrupt)"""


class ConversationFocusTracker:
    """
    Rule-based focus tracker for preventing context switching.

    ULTRA-FAST: All operations <5ms using string matching and counters.
    NOT LLM-based for responsiveness.

    Prevents:
    ❌ Interrupting long user messages with findings
    ❌ Interrupting user questions with findings
    ❌ Switching topics during insight discussion
    ❌ Abandoning insights too early

    Enables:
    ✅ Natural insight discussion continuation
    ✅ Safe proactive findings injection
    ✅ Graceful insight closure when user satisfied
    """

    def __init__(self):
        """Initialize focus tracker with reactive state"""
        self.state = FocusState(current_focus="reactive", last_update=datetime.now())

        # RULE-BASED: Curiosity patterns that indicate user interest in insight
        self.curiosity_markers = [
            # Explicit interest
            "oh really",
            "really?",
            "seriously?",
            "no way",
            "wow",
            "interesting",
            # Doubt/verification
            "are you sure",
            "how do you know",
            "how'd you find that",
            "where'd you get that",
            # General curiosity
            "what",
            "why",
            "how",
            "huh",
            "wait",
            "hold on",
            "tell me more",
            "more",
            "and",
        ]

        # RULE-BASED: Closure/resolution patterns indicating discussion end
        self.resolution_markers = [
            # Explicit resolution
            "got it",
            "got it thanks",
            "thanks",
            "thank you",
            "okay",
            "ok",
            "cool",
            "good to know",
            "makes sense",
            # Acceptance/agreement
            "yeah",
            "yep",
            "right",
            "sure",
            "agree",
            "true",
            # Dismissal/satisfaction
            "alright",
            "fine",
            "whatever",
            "fine with me",
            "that's fine",
            "let's move on",
            "anyway",
        ]

    def determine_focus(
        self, user_message: str, has_pending_proactive: bool
    ) -> Literal["continue_insight_thread", "inject_proactive", "reactive"]:
        """
        RULE-BASED focus determination (ultra-fast).

        Uses pattern matching to decide:
        - "continue_insight_thread": Stay focused on recent insight
        - "inject_proactive": Safe to inject new finding
        - "reactive": Normal conversation mode

        Args:
            user_message: User's latest message
            has_pending_proactive: Whether we have completed background analyses

        Returns:
            Focus determination for this turn
        """
        message_lower = user_message.lower()
        word_count = len(user_message.split())

        # ===================================================================
        # If already in insight thread, determine continuation or closure
        # ===================================================================
        if self.state.current_focus == "insight_thread":
            # Check for closure markers (user satisfied)
            if any(marker in message_lower for marker in self.resolution_markers):
                self._release_lock()
                return "reactive"

            # Check for curiosity continuation (user wants more)
            if any(marker in message_lower for marker in self.curiosity_markers):
                self.state.insight_turn_count += 1
                return "continue_insight_thread"

            # Continue for max 3 turns without explicit marker
            if self.state.insight_turn_count < 3:
                self.state.insight_turn_count += 1
                return "continue_insight_thread"
            else:
                # Max turns reached, release lock
                self._release_lock()
                return "reactive"

        # ===================================================================
        # If not in insight thread, check if user got curious about last insight
        # ===================================================================
        if self.state.last_insight_message and any(
            marker in message_lower for marker in self.curiosity_markers
        ):
            # User is curious! Lock into insight discussion
            self.state.current_focus = "insight_thread"
            self.state.insight_turn_count = 1
            return "continue_insight_thread"

        # ===================================================================
        # Check if safe to inject proactive finding
        # ===================================================================
        if has_pending_proactive:
            # DON'T interrupt if user sent long message (thinking/explaining)
            if word_count > 10:
                return "reactive"

            # DON'T interrupt if user asked a question
            if "?" in user_message:
                return "reactive"

            # DON'T interrupt if user just shared something important
            if any(
                keyword in message_lower
                for keyword in ["just", "happened", "experienced", "noticed", "found"]
            ):
                return "reactive"

            # Safe to inject!
            return "inject_proactive"

        # Default: normal reactive conversation
        return "reactive"

    def track_insight_injection(self, insight_message: str, topic: Optional[str] = None):
        """
        Track that we just injected a proactive insight.

        Called after we inject a finding so we can track it for potential
        continuation if user gets curious.

        Args:
            insight_message: The insight message we just sent
            topic: Topic of the insight (for alignment tracking)
        """
        import time

        self.state.last_insight_message = insight_message
        self.state.current_focus = "proactive"
        self.state.insight_turn_count = 0
        self.state.last_update = datetime.now()
        self.state.last_inject_ts = time.time()
        self.state.topic_of_last_inject = topic
        self.state.has_permission = False  # Reset permission after injection

    def can_inject(
        self,
        curr_topic: Optional[str],
        now: float,
        has_explicit_permission: bool = False,
    ) -> bool:
        """
        Check if we can inject proactive findings with consent & cooldown.

        NEW: Floor control - respects user's conversational space
        - Don't interrupt if user is typing
        - Cooldown between injections (30s default)
        - Topic alignment (don't switch topics abruptly)
        - Permission required (explicit or implicit)

        Args:
            curr_topic: Current conversation topic
            now: Current timestamp (seconds since epoch)
            has_explicit_permission: User explicitly said "yes" / "tell me"

        Returns:
            True if safe to inject, False otherwise
        """
        # Don't interrupt typing
        if self.state.user_typing:
            return False

        # Check cooldown
        if self.state.last_inject_ts:
            elapsed = now - self.state.last_inject_ts
            if elapsed < self.state.cooldown_secs:
                return False

        # Check topic alignment (don't switch topics abruptly)
        if self.state.topic_of_last_inject and curr_topic:
            if curr_topic != self.state.topic_of_last_inject:
                # Different topic - need explicit permission
                if not has_explicit_permission:
                    return False

        # Need permission (explicit or implicit from context)
        return has_explicit_permission or self.state.has_permission

    def detect_permission(self, message: str) -> bool:
        """
        Detect if user is granting permission for proactive injection.

        Permission markers: "yes", "tell me", "go ahead", "sure", "okay"

        Args:
            message: User message to check

        Returns:
            True if permission detected
        """
        message_lower = message.lower()
        permission_markers = [
            "yes",
            "yeah",
            "yep",
            "sure",
            "okay",
            "ok",
            "tell me",
            "go ahead",
            "what did you find",
            "show me",
            "let me know",
            "share it",
        ]

        return any(marker in message_lower for marker in permission_markers)

    def grant_permission(self):
        """Grant permission for next proactive injection"""
        self.state.has_permission = True

    def set_user_typing(self, is_typing: bool):
        """Update user typing status (for floor control)"""
        self.state.user_typing = is_typing

    def _release_lock(self):
        """Release focus lock and return to reactive mode"""
        self.state.current_focus = "reactive"
        self.state.locked_insight_id = None
        self.state.insight_turn_count = 0
        self.state.last_update = datetime.now()
