"""
k1.concierge.protocols.delivery_strategy -- Conversational Delivery Strategy Engine.

OPP-8: Natural Flow Delivery.

The existing WeavePolicy answers WHEN to deliver (IMMEDIATE/BATCH/DEFER/
DIGEST/SUPPRESS).  This module answers HOW to deliver -- selecting the
presentation mode that matches the conversational context.

Problem:
    The current system funnels every async result through the same WEAVE
    prompt mode.  But natural conversation requires different presentation
    strategies:
      - User was waiting for this specific result -> present directly
      - User is mid-conversation about something else -> weave naturally
      - Result isn't related to current topic -> inject silently or defer
      - Simple confirmation -> one-liner, not a full narrative
      - Multiple low-priority results -> summarize in a digest

Design:
    Three kernel-level primitives compose to produce a DeliveryStrategy:

    1. ResultClassification -- WHAT kind of result arrived.
       Determined from the task dispatch trace (was user explicitly
       waiting?) and result metadata (urgency, domain, expiry).

    2. ConversationFlowSignal -- WHERE the conversation is right now.
       Topic match score, conversation depth, natural pause detection.

    3. DeliveryMode -- HOW to present.
       DIRECT_PRESENT, CONVERSATIONAL_WEAVE, CONTEXTUAL_INJECT,
       BRIEF_NOTIFY, DEFERRED_QUEUE.

    The DeliveryStrategyEngine combines these with the existing
    WeaveDecision (WHEN) to produce the final DeliveryStrategy.

Integration:
    DeliveryStrategy.delivery_mode determines the Front LLM prompt mode:
      DIRECT_PRESENT      -> PRESENT prompt mode (result is the focus)
      CONVERSATIONAL_WEAVE -> WEAVE prompt mode (result woven into chat)
      CONTEXTUAL_INJECT   -> STANDARD prompt mode (result in async_context)
      BRIEF_NOTIFY        -> PRESENT prompt mode + brief=True flag
      DEFERRED_QUEUE      -> No LLM call; result stored for later
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any

logger = logging.getLogger(__name__)


# =====================================================================
# Result Classification -- WHAT kind of result
# =====================================================================


class ResultClassification(IntEnum):
    """Classifies an incoming task result by its relationship to
    the user's conversational state.

    Values:
        AWAITED        -- User explicitly asked for this. The dispatch
                          was triggered by the user's most recent intent
                          and no topic change has occurred since.
        FOLLOW_UP      -- Result from a chained/dependent task. The user
                          didn't explicitly ask for THIS result, but it's
                          part of a sequence they initiated.
        BACKGROUND     -- Speculative, prefetched, or low-priority task.
                          User may not know this was running.
        TIME_SENSITIVE -- Result has urgency or a real-world deadline
                          (booking about to expire, appointment reminder).
        INFORMATIONAL  -- Status update or FYI. Useful but not urgent.
    """

    AWAITED = 0
    FOLLOW_UP = 1
    BACKGROUND = 2
    TIME_SENSITIVE = 3
    INFORMATIONAL = 4


def classify_result(
    result: dict[str, Any],
    *,
    active_dispatch_task_ids: frozenset[str] | None = None,
    current_turn: int = 0,
    dispatch_turn: int = 0,
    has_expiry: bool = False,
    is_chained: bool = False,
) -> ResultClassification:
    """Classify an incoming result based on dispatch context.

    Args:
        result:                    The task result dict.
        active_dispatch_task_ids:  Task IDs from the user's most recent
                                   dispatch (from scoreboard / FSM state).
        current_turn:              Current conversation turn number.
        dispatch_turn:             Turn when this task was dispatched.
        has_expiry:                True if result has a real-world deadline.
        is_chained:                True if this task depends_on another task.

    Returns:
        ResultClassification enum value.
    """
    task_id = result.get("task_id", "")
    urgency = result.get("urgency", "normal")

    # Time-sensitive overrides everything
    if has_expiry or urgency in ("critical", "urgent"):
        return ResultClassification.TIME_SENSITIVE

    # Awaited: task was explicitly dispatched by user's recent intent
    if active_dispatch_task_ids and task_id in active_dispatch_task_ids:
        # But if many turns have passed, it's more like a background result
        turn_age = current_turn - dispatch_turn
        if turn_age <= 3:
            return ResultClassification.AWAITED

    # Chained task
    if is_chained:
        return ResultClassification.FOLLOW_UP

    # Low urgency or old dispatch
    if urgency == "low":
        return ResultClassification.INFORMATIONAL

    return ResultClassification.BACKGROUND


# =====================================================================
# Conversation Flow Signal -- WHERE the conversation is
# =====================================================================


@dataclass(frozen=True)
class ConversationFlowSignal:
    """Snapshot of the conversational state for delivery decisions.

    Collected alongside WeaveSignal but focused on topic/flow rather
    than timing/urgency mechanics.

    Attributes:
        topic_match_score:     0.0-1.0. How closely the result's domain
                               matches the user's current conversation
                               topic. 1.0 = exact match (user asked about
                               hotels, hotel booking result arrived).
        conversation_depth:    Number of consecutive turns on the same
                               topic. Deep (>5) means user is focused;
                               interruptions feel more disruptive.
        is_natural_pause:      True if the last turn was a topic shift,
                               conversation lull, or explicit "what else?"
                               This is the ideal moment for delivery.
        user_awaiting_result:  True if the user's last message indicates
                               they're waiting ("any update?", silence
                               after dispatch, "how's that going?").
        last_user_intent:      The classified intent from Phase 1 for
                               the most recent user input. Used to check
                               if user asked about pending results.
        turns_since_dispatch:  How many turns since the most recent
                               task dispatch. More turns = less awaited.
    """

    topic_match_score: float = 0.0
    conversation_depth: int = 0
    is_natural_pause: bool = False
    user_awaiting_result: bool = False
    last_user_intent: str = ""
    turns_since_dispatch: int = 0

    @classmethod
    def from_session_state(
        cls,
        *,
        ss: Any = None,
        result_domain: str = "",
        current_turn: int = 0,
        dispatch_turn: int = 0,
    ) -> ConversationFlowSignal:
        """Build from session state sections.

        Reads scoreboard (current topic, intent), narrative (topic
        shifts), and beliefs (domain context) to compute flow signals.

        Args:
            ss:              SessionState instance.
            result_domain:   Domain tag of the arriving result.
            current_turn:    Current turn number.
            dispatch_turn:   Turn when this task was dispatched.

        Returns:
            Frozen ConversationFlowSignal snapshot.
        """
        topic_score = 0.0
        depth = 0
        is_pause = False
        awaiting = False
        last_intent = ""
        turns_since = current_turn - dispatch_turn

        if ss is None:
            return cls(turns_since_dispatch=max(0, turns_since))

        # Read scoreboard for current topic/intent
        scoreboard = _read_section(ss, "scoreboard")
        if scoreboard:
            current_domain = scoreboard.get("primary_domain", "")
            last_intent = scoreboard.get("last_intent", "")

            # Topic match: exact domain match = 1.0, partial = 0.5
            if result_domain and current_domain:
                if result_domain == current_domain:
                    topic_score = 1.0
                elif result_domain in current_domain or current_domain in result_domain:
                    topic_score = 0.5

            # Detect "awaiting" patterns
            if last_intent in (
                "status_check",
                "follow_up",
                "what_happened",
                "any_update",
            ):
                awaiting = True

        # Read narrative for conversation depth and topic shifts
        narrative = _read_section(ss, "narrative_active")
        if narrative:
            depth = narrative.get("topic_depth", 0)
            recent_shift = narrative.get("recent_topic_shift", False)
            if recent_shift:
                is_pause = True

        # User silence after dispatch with no new topic = awaiting
        if turns_since <= 1 and not last_intent:
            awaiting = True

        return cls(
            topic_match_score=round(topic_score, 2),
            conversation_depth=depth,
            is_natural_pause=is_pause,
            user_awaiting_result=awaiting,
            last_user_intent=last_intent,
            turns_since_dispatch=max(0, turns_since),
        )


# =====================================================================
# Delivery Mode -- HOW to present
# =====================================================================


class DeliveryMode(IntEnum):
    """Presentation strategy for delivering a result to the user.

    Values:
        DIRECT_PRESENT       -- Result IS the focus. User was waiting.
                                Maps to PRESENT prompt mode.
                                Example: "Here are your flight options."

        CONVERSATIONAL_WEAVE -- Result arrives mid-conversation.
                                Maps to WEAVE prompt mode.
                                Example: "By the way, your hotel search
                                came back while we were chatting..."

        CONTEXTUAL_INJECT    -- Don't present explicitly. Silently add
                                to the next turn's context so the LLM
                                can reference it if relevant.
                                Maps to STANDARD mode + async_context.
                                Example: (no explicit delivery -- LLM
                                might say "Oh, and I got your results"
                                naturally if the topic comes up.)

        BRIEF_NOTIFY         -- One-line confirmation, no narrative.
                                Maps to PRESENT mode + brief=True.
                                Example: "Your booking is confirmed."

        DEFERRED_QUEUE       -- Don't deliver now. Store for later.
                                Delivered on: next natural pause, explicit
                                user ask, or session end summary.
                                No LLM call triggered.
    """

    DIRECT_PRESENT = 0
    CONVERSATIONAL_WEAVE = 1
    CONTEXTUAL_INJECT = 2
    BRIEF_NOTIFY = 3
    DEFERRED_QUEUE = 4


# =====================================================================
# Delivery Strategy -- composite decision
# =====================================================================


@dataclass(frozen=True)
class DeliveryStrategy:
    """Complete delivery decision combining WHEN + HOW.

    Produced by DeliveryStrategyEngine.decide().  Consumed by the FSM
    controller to determine both timing and presentation.

    Attributes:
        delivery_mode:      HOW to present the result.
        result_class:       WHAT kind of result this is.
        reasoning:          Human-readable decision explanation.
        topic_relevant:     True if result matches current topic.
        prompt_mode_hint:   Suggested prompt mode string for the Front
                            LLM ("PRESENT", "WEAVE", "STANDARD").
        brief:              True if the presentation should be minimal
                            (one-liner rather than full narrative).
        inject_as_context:  True if result should be added to next
                            turn's async_results_context silently.
    """

    delivery_mode: DeliveryMode = DeliveryMode.CONVERSATIONAL_WEAVE
    result_class: ResultClassification = ResultClassification.BACKGROUND
    reasoning: str = ""
    topic_relevant: bool = False
    prompt_mode_hint: str = "WEAVE"
    brief: bool = False
    inject_as_context: bool = False


# =====================================================================
# Delivery Strategy Engine -- decision logic
# =====================================================================


@dataclass
class DeliveryStrategyConfig:
    """Tunable knobs for the delivery strategy engine.

    Attributes:
        deep_conversation_threshold: Turn count on same topic above
            which results should avoid interrupting.
        topic_match_weave_threshold: Minimum topic_match_score for
            CONVERSATIONAL_WEAVE (below this, CONTEXTUAL_INJECT).
        max_deferred_results: Maximum results to hold in deferred queue
            before forcing a BRIEF_NOTIFY digest.
        natural_pause_inject_all: If True, deliver all deferred results
            when a natural pause is detected.
    """

    deep_conversation_threshold: int = 5
    topic_match_weave_threshold: float = 0.3
    max_deferred_results: int = 5
    natural_pause_inject_all: bool = True


class DeliveryStrategyEngine:
    """Maps (result_class, flow_signal, weave_decision) -> DeliveryStrategy.

    This is the conversational layer that sits between the mechanical
    WeavePolicy (WHEN) and the Front LLM (HOW).  It ensures that
    results are presented in the way that feels most natural for the
    current conversational context.

    Priority-ordered rule table (first match wins):

    Rule  Condition                                         Mode
    ----  ------------------------------------------------  -------------------
    D1    AWAITED + user_awaiting + LISTENING/idle           DIRECT_PRESENT
    D2    AWAITED + COMPANIONING + topic_match > 0.3        CONVERSATIONAL_WEAVE
    D3    AWAITED + COMPANIONING + topic_match <= 0.3       DIRECT_PRESENT
    D4    TIME_SENSITIVE + not suppress_all                  BRIEF_NOTIFY
    D5    FOLLOW_UP + topic_match >= 0.5                    CONVERSATIONAL_WEAVE
    D6    FOLLOW_UP + natural_pause                         BRIEF_NOTIFY
    D7    FOLLOW_UP + deep_conversation                     DEFERRED_QUEUE
    D8    BACKGROUND + natural_pause                        CONTEXTUAL_INJECT
    D9    BACKGROUND + deep_conversation                    DEFERRED_QUEUE
    D10   BACKGROUND + topic_match >= 0.5                   CONTEXTUAL_INJECT
    D11   INFORMATIONAL + natural_pause                     BRIEF_NOTIFY
    D12   INFORMATIONAL                                     DEFERRED_QUEUE
    D13   default                                           CONVERSATIONAL_WEAVE
    """

    __slots__ = ("_cfg",)

    def __init__(self, config: DeliveryStrategyConfig | None = None) -> None:
        self._cfg = config or DeliveryStrategyConfig()

    def decide(
        self,
        result_class: ResultClassification,
        flow_signal: ConversationFlowSignal,
        *,
        weave_decision: Any = None,
        fsm_state: str = "",
        emotional_gate: str = "open",
    ) -> DeliveryStrategy:
        """Evaluate the delivery rule table.

        Args:
            result_class:    Classification of the incoming result.
            flow_signal:     Current conversation flow signal.
            weave_decision:  WeaveDecision from WeavePolicy (optional).
                             Used to respect SUPPRESS decisions.
            fsm_state:       Current FSM state name.
            emotional_gate:  Emotional gate from WeaveSignal.

        Returns:
            DeliveryStrategy with delivery_mode and metadata.
        """
        # Respect SUPPRESS from WeavePolicy
        if weave_decision is not None and _is_suppress(weave_decision):
            return DeliveryStrategy(
                delivery_mode=DeliveryMode.DEFERRED_QUEUE,
                result_class=result_class,
                reasoning="WeavePolicy SUPPRESS -> DEFERRED_QUEUE",
                prompt_mode_hint="NONE",
            )

        # Respect suppress_all_non_safety emotional gate
        if emotional_gate == "suppress_all_non_safety":
            if result_class != ResultClassification.TIME_SENSITIVE:
                return DeliveryStrategy(
                    delivery_mode=DeliveryMode.DEFERRED_QUEUE,
                    result_class=result_class,
                    reasoning="emotional_gate=suppress_all + not time_sensitive -> DEFERRED_QUEUE",
                    prompt_mode_hint="NONE",
                )

        is_idle = fsm_state in ("LISTENING", "")
        is_companioning = fsm_state == "COMPANIONING"
        is_deep = flow_signal.conversation_depth > self._cfg.deep_conversation_threshold
        topic_match = flow_signal.topic_match_score
        is_pause = flow_signal.is_natural_pause
        awaiting = flow_signal.user_awaiting_result

        # --- D1: AWAITED + user waiting + idle -> just show it ---
        if result_class == ResultClassification.AWAITED and awaiting and is_idle:
            return DeliveryStrategy(
                delivery_mode=DeliveryMode.DIRECT_PRESENT,
                result_class=result_class,
                reasoning="D1: AWAITED + user_awaiting + LISTENING -> DIRECT_PRESENT",
                topic_relevant=True,
                prompt_mode_hint="PRESENT",
            )

        # --- D2: AWAITED + chatting + topic matches -> weave ---
        if (
            result_class == ResultClassification.AWAITED
            and is_companioning
            and topic_match > self._cfg.topic_match_weave_threshold
        ):
            return DeliveryStrategy(
                delivery_mode=DeliveryMode.CONVERSATIONAL_WEAVE,
                result_class=result_class,
                reasoning=f"D2: AWAITED + COMPANIONING + topic_match={topic_match:.2f} -> WEAVE",
                topic_relevant=True,
                prompt_mode_hint="WEAVE",
            )

        # --- D3: AWAITED + chatting + different topic -> present directly ---
        if result_class == ResultClassification.AWAITED and is_companioning:
            return DeliveryStrategy(
                delivery_mode=DeliveryMode.DIRECT_PRESENT,
                result_class=result_class,
                reasoning=f"D3: AWAITED + COMPANIONING + topic_match={topic_match:.2f} -> DIRECT_PRESENT",
                topic_relevant=False,
                prompt_mode_hint="PRESENT",
            )

        # --- D1b: AWAITED + idle (not explicitly awaiting) -> present ---
        if result_class == ResultClassification.AWAITED and is_idle:
            return DeliveryStrategy(
                delivery_mode=DeliveryMode.DIRECT_PRESENT,
                result_class=result_class,
                reasoning="D1b: AWAITED + LISTENING -> DIRECT_PRESENT",
                topic_relevant=True,
                prompt_mode_hint="PRESENT",
            )

        # --- D4: TIME_SENSITIVE -> brief notify ---
        if result_class == ResultClassification.TIME_SENSITIVE:
            return DeliveryStrategy(
                delivery_mode=DeliveryMode.BRIEF_NOTIFY,
                result_class=result_class,
                reasoning="D4: TIME_SENSITIVE -> BRIEF_NOTIFY",
                topic_relevant=topic_match > 0.3,
                prompt_mode_hint="PRESENT",
                brief=True,
            )

        # --- D5: FOLLOW_UP + topic matches -> weave ---
        if result_class == ResultClassification.FOLLOW_UP and topic_match >= 0.5:
            return DeliveryStrategy(
                delivery_mode=DeliveryMode.CONVERSATIONAL_WEAVE,
                result_class=result_class,
                reasoning=f"D5: FOLLOW_UP + topic_match={topic_match:.2f} -> WEAVE",
                topic_relevant=True,
                prompt_mode_hint="WEAVE",
            )

        # --- D6: FOLLOW_UP + natural pause -> brief ---
        if result_class == ResultClassification.FOLLOW_UP and is_pause:
            return DeliveryStrategy(
                delivery_mode=DeliveryMode.BRIEF_NOTIFY,
                result_class=result_class,
                reasoning="D6: FOLLOW_UP + natural_pause -> BRIEF_NOTIFY",
                topic_relevant=False,
                prompt_mode_hint="PRESENT",
                brief=True,
            )

        # --- D7: FOLLOW_UP + deep conversation -> defer ---
        if result_class == ResultClassification.FOLLOW_UP and is_deep:
            return DeliveryStrategy(
                delivery_mode=DeliveryMode.DEFERRED_QUEUE,
                result_class=result_class,
                reasoning=f"D7: FOLLOW_UP + depth={flow_signal.conversation_depth} -> DEFERRED_QUEUE",
                prompt_mode_hint="NONE",
            )

        # --- D8: BACKGROUND + natural pause -> silent inject ---
        if result_class == ResultClassification.BACKGROUND and is_pause:
            return DeliveryStrategy(
                delivery_mode=DeliveryMode.CONTEXTUAL_INJECT,
                result_class=result_class,
                reasoning="D8: BACKGROUND + natural_pause -> CONTEXTUAL_INJECT",
                prompt_mode_hint="STANDARD",
                inject_as_context=True,
            )

        # --- D9: BACKGROUND + deep conversation -> defer ---
        if result_class == ResultClassification.BACKGROUND and is_deep:
            return DeliveryStrategy(
                delivery_mode=DeliveryMode.DEFERRED_QUEUE,
                result_class=result_class,
                reasoning=f"D9: BACKGROUND + depth={flow_signal.conversation_depth} -> DEFERRED_QUEUE",
                prompt_mode_hint="NONE",
            )

        # --- D10: BACKGROUND + topic matches -> silent inject ---
        if result_class == ResultClassification.BACKGROUND and topic_match >= 0.5:
            return DeliveryStrategy(
                delivery_mode=DeliveryMode.CONTEXTUAL_INJECT,
                result_class=result_class,
                reasoning=f"D10: BACKGROUND + topic_match={topic_match:.2f} -> CONTEXTUAL_INJECT",
                topic_relevant=True,
                prompt_mode_hint="STANDARD",
                inject_as_context=True,
            )

        # --- D11: INFORMATIONAL + pause -> brief ---
        if result_class == ResultClassification.INFORMATIONAL and is_pause:
            return DeliveryStrategy(
                delivery_mode=DeliveryMode.BRIEF_NOTIFY,
                result_class=result_class,
                reasoning="D11: INFORMATIONAL + natural_pause -> BRIEF_NOTIFY",
                prompt_mode_hint="PRESENT",
                brief=True,
            )

        # --- D12: INFORMATIONAL -> defer ---
        if result_class == ResultClassification.INFORMATIONAL:
            return DeliveryStrategy(
                delivery_mode=DeliveryMode.DEFERRED_QUEUE,
                result_class=result_class,
                reasoning="D12: INFORMATIONAL -> DEFERRED_QUEUE",
                prompt_mode_hint="NONE",
            )

        # --- D13: default -> weave ---
        return DeliveryStrategy(
            delivery_mode=DeliveryMode.CONVERSATIONAL_WEAVE,
            result_class=result_class,
            reasoning="D13: default -> CONVERSATIONAL_WEAVE",
            prompt_mode_hint="WEAVE",
        )

    def on_natural_pause(
        self,
        deferred_results: list[dict[str, Any]],
    ) -> list[DeliveryStrategy]:
        """Re-evaluate deferred results when a natural pause occurs.

        Called by the FSM when a topic shift, explicit "what else?",
        or idle threshold is detected. Returns delivery strategies
        for any deferred results that should now be presented.

        Args:
            deferred_results: List of result dicts in the deferred queue.

        Returns:
            List of DeliveryStrategy for results to deliver now.
            Empty list if nothing should be delivered.
        """
        if not deferred_results:
            return []

        strategies: list[DeliveryStrategy] = []

        if len(deferred_results) == 1:
            strategies.append(
                DeliveryStrategy(
                    delivery_mode=DeliveryMode.BRIEF_NOTIFY,
                    result_class=ResultClassification.BACKGROUND,
                    reasoning="natural_pause: 1 deferred result -> BRIEF_NOTIFY",
                    prompt_mode_hint="PRESENT",
                    brief=True,
                )
            )
        elif len(deferred_results) <= 3:
            # Few results: brief notify each
            for _ in deferred_results:
                strategies.append(
                    DeliveryStrategy(
                        delivery_mode=DeliveryMode.BRIEF_NOTIFY,
                        result_class=ResultClassification.BACKGROUND,
                        reasoning="natural_pause: <=3 deferred -> BRIEF_NOTIFY each",
                        prompt_mode_hint="PRESENT",
                        brief=True,
                    )
                )
        else:
            # Many results: contextual inject as a digest
            strategies.append(
                DeliveryStrategy(
                    delivery_mode=DeliveryMode.CONTEXTUAL_INJECT,
                    result_class=ResultClassification.INFORMATIONAL,
                    reasoning=f"natural_pause: {len(deferred_results)} deferred -> CONTEXTUAL_INJECT digest",
                    prompt_mode_hint="STANDARD",
                    inject_as_context=True,
                )
            )

        return strategies


# =====================================================================
# Helpers
# =====================================================================


def _read_section(ss: Any, name: str) -> dict[str, Any]:
    """Read a session state section safely."""
    if ss is None:
        return {}
    section = None
    if hasattr(ss, "get_section"):
        section = ss.get_section(name)
    elif hasattr(ss, "sections"):
        section = ss.sections.get(name)
    if section is None:
        return {}
    if hasattr(section, "to_dict"):
        return section.to_dict()
    if isinstance(section, dict):
        return section
    return {}


def _is_suppress(weave_decision: Any) -> bool:
    """Check if a WeaveDecision value means SUPPRESS."""
    if isinstance(weave_decision, int):
        return weave_decision == 4  # WeaveDecision.SUPPRESS
    if hasattr(weave_decision, "name"):
        return weave_decision.name == "SUPPRESS"
    return False
