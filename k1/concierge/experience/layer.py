"""
k1.concierge.experience.layer -- ExperienceLayer orchestrator.

Orchestrates all experience components with correct fire cadence.

V2 Design Ref: Section 12.4

Called by FSM after every turn_end. Fires components at their
defined cadence, respects the EP skip rule (Section 5), and
returns envelopes for the bus.

Pluggability contract:
  - Adding a new component: add instance variable, add cadence
    check in tick(), add output to envelopes dict. No other
    changes needed.
  - Replacing an algorithm: swap the component class. The
    ExperienceLayer does not know or care about the algorithm --
    it only calls the method and collects the output.
"""

from __future__ import annotations

import logging

from k1.concierge.config import get_config
from k1.concierge.experience.affective_mirror import AffectiveMirror
from k1.concierge.experience.anticipatory_responder import AnticipatoryResponder
from k1.concierge.experience.emotional_processor import EmotionalProcessor
from k1.concierge.experience.narrative_weaver import NarrativeWeaver
from k1.concierge.experience.proactive_agent import ProactiveAgent
from k1.concierge.experience.rhythm_controller import RhythmController

logger = logging.getLogger(__name__)


class ExperienceLayer:
    """Orchestrates all experience components.

    Called by FSM after every turn_end.
    Fires components at their defined cadence.
    Returns dict of typed outputs for bus emission.

    Pluggability contract:
      - Adding a new component: add instance variable, add cadence
        check in tick(), add output to envelopes dict. No other
        changes needed -- DynamicPromptBuilder reads from SS sections,
        bus consumers subscribe to topics.
      - Replacing an algorithm: swap the component class. The
        ExperienceLayer does not know or care about the algorithm --
        it only calls the method and collects the output.
    """

    def __init__(self) -> None:
        self.emotional_processor = EmotionalProcessor()
        self.affective_mirror = AffectiveMirror()
        self.narrative_weaver = NarrativeWeaver()
        self.anticipatory_responder = AnticipatoryResponder()
        self.proactive_agent = ProactiveAgent()
        self.rhythm_controller = RhythmController()
        self.turn_count = 0
        logger.info(
            "ExperienceLayer initialized (6 components: EP, AM, NW, AR, PA, RC)",
        )

    async def tick(self, fsm_state: str, context: dict) -> dict:
        """Called by FSM after every turn_end.

        Args:
            fsm_state: Current FSM state (Section 4).
            context: Dict with keys from Session State + turn metadata.
                Expected keys:
                  - turn_transcript: str (current turn text)
                  - affect_history: list[dict] (recent affect states)
                  - front_refine_affect_confidence: float (0.0 if not called)
                  - conversation_history: list[dict]
                  - memory_recalls: list[dict]
                  - task_state: dict
                  - user_patterns: dict
                  - wait_duration_ms: int (0 if not waiting)
                  - persona: dict
                  - user_cadence: dict

        Returns:
            Dict of component name -> typed output. Bus emitter
            publishes each as the appropriate topic.
        """
        self.turn_count += 1
        logger.debug(
            "ExperienceLayer.tick: turn=%d fsm_state=%s",
            self.turn_count,
            fsm_state,
        )
        envelopes: dict = {}
        _exp_cfg = get_config().experience

        # ---- EmotionalProcessor: every Nth turn ----
        # EP skip rule (Section 5, ITEM #17):
        #   If Front's refine_affect() was called this turn with
        #   confidence > threshold, skip EP write to affective_now.
        #   Front's correction is higher quality than EP's trajectory
        #   computation. One rule, one definition -- Section 5 owns it.
        front_affect_confidence = context.get("front_refine_affect_confidence", 0.0)
        if (
            self.turn_count % _exp_cfg.emotional_processor_cadence == 0
            and front_affect_confidence <= _exp_cfg.ep_skip_confidence_threshold
        ):
            trajectory = await self.emotional_processor.process(
                context.get("turn_transcript", ""),
                context.get("affect_history", []),
            )
            envelopes["emotional"] = trajectory

            # AffectiveMirror: fires immediately after EmotionalProcessor.
            # Chained -- not independent cadence.
            tone = await self.affective_mirror.mirror(
                trajectory.__dict__,
                context.get("persona", {}),
            )
            envelopes["tone"] = tone

        # ---- NarrativeWeaver: every Nth turn ----
        if self.turn_count % _exp_cfg.narrative_weaver_cadence == 0:
            narrative = await self.narrative_weaver.weave(
                context.get("conversation_history", []),
                context.get("memory_recalls", []),
            )
            envelopes["narrative"] = narrative

        # ---- AnticipatoryResponder: every Nth turn ----
        if self.turn_count % _exp_cfg.anticipatory_responder_cadence == 0:
            anticipation = await self.anticipatory_responder.anticipate(
                context.get("task_state", {}),
                context.get("user_patterns", {}),
            )
            envelopes["anticipation"] = anticipation

        # ---- ProactiveAgent: COMPANIONING + long wait ----
        # Only fires when Back is executing a task and the user
        # has been waiting > threshold. FSM routes the fill
        # to Front for presentation.
        if fsm_state == "COMPANIONING":
            wait_ms = context.get("wait_duration_ms", 0)
            if wait_ms > _exp_cfg.proactive_wait_threshold_ms:
                fill = await self.proactive_agent.generate_fill(
                    context.get("task_state", {}),
                    wait_ms,
                )
                envelopes["fill"] = fill

        # ---- RhythmController: every output ----
        # Always fires. Provides timing parameters for the
        # delivery pipeline to apply before streaming.
        timing = self.rhythm_controller.get_pattern(
            self.turn_count,
            context.get("user_cadence", {}),
        )
        envelopes["timing"] = timing

        logger.debug(
            "ExperienceLayer.tick: turn=%d fired=%s",
            self.turn_count,
            list(envelopes.keys()),
        )
        return envelopes
