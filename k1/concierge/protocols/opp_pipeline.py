"""
k1.concierge.protocols.opp_pipeline -- OPP Kernel Primitives Integration Pipeline.

Wires all 8 OPP (Opportunity Pattern) primitives into the FSM controller's
event lifecycle.  The controller calls set_opp_pipeline(pipeline) and the
pipeline inserts itself at the correct lifecycle hooks.

The 8 primitives and their hook points:

    OPP-1 Paced Delivery       -> on_weave_flush()
    OPP-2 Recency Bias Decay   -> on_classify() (arbiter integration)
    OPP-3 Affect Hard Caps     -> on_pre_llm_call()
    OPP-4 Trust Accumulator    -> on_hitl_outcome(), on_pre_invoke()
    OPP-5 Proactive Scheduler  -> on_idle_tick()
    OPP-6 Episodic Compression -> on_pre_prompt_build()
    OPP-7 Dynamic Identity     -> on_pre_prompt_build()
    OPP-8 Natural Flow Delivery-> on_task_complete()

Lifecycle hook call sites in ConciergeController:

    user.input.v1 received:
        Phase1 -> on_classify() [OPP-2]
        Front prompt build -> on_pre_prompt_build() [OPP-6, OPP-7]
        Front LLM call -> on_pre_llm_call() [OPP-3]

    task.complete.v1 received:
        Result classification -> on_task_complete() [OPP-8]
        WeavePolicy.decide() -> uses OPP-8's DeliveryStrategy
        Weave flush -> on_weave_flush() [OPP-1]

    task.suspended.v1 / HITL resolution:
        Outcome recorded -> on_hitl_outcome() [OPP-4]
        Pre-invoke check -> on_pre_invoke() [OPP-4]

    Idle tick (1s timer):
        Proactive check -> on_idle_tick() [OPP-5]

Design:
    The pipeline is a single object with hook methods.  Each hook
    receives the minimal context it needs and returns an enriched
    result.  The controller does NOT need to know about individual
    OPP primitives -- it only calls pipeline hooks.

    All primitives are optional.  If a primitive is None (not configured),
    the hook is a no-op passthrough.  This allows incremental wiring.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# =====================================================================
# Pipeline configuration
# =====================================================================


@dataclass
class OppPipelineConfig:
    """Master knobs for enabling/disabling individual OPP primitives.

    All primitives default to enabled.  Set to False to disable a
    primitive without removing it from the pipeline.
    """

    enable_paced_delivery: bool = True  # OPP-1
    enable_recency_decay: bool = True  # OPP-2
    enable_affect_hard_caps: bool = True  # OPP-3
    enable_trust_accumulator: bool = True  # OPP-4
    enable_proactive_scheduler: bool = True  # OPP-5
    enable_episodic_compression: bool = True  # OPP-6
    enable_dynamic_identity: bool = True  # OPP-7
    enable_delivery_strategy: bool = True  # OPP-8


# =====================================================================
# Hook result dataclasses
# =====================================================================


@dataclass
class ClassifyEnrichment:
    """Result of on_classify() -- enriches Phase 1 classification.

    Attributes:
        recency_decay_applied: True if recency decay was applied to
            arbiter overlap scores.
        short_input_penalty: True if short-input penalty was applied.
        original_d_overlap: Domain overlap before decay.
        decayed_d_overlap:  Domain overlap after decay.
    """

    recency_decay_applied: bool = False
    short_input_penalty: bool = False
    original_d_overlap: float = 0.0
    decayed_d_overlap: float = 0.0


@dataclass
class PromptEnrichment:
    """Result of on_pre_prompt_build() -- injects OPP context into prompt.

    Attributes:
        compressed_context:  Episodic compression output (OPP-6).
                             If non-empty, replaces raw history turns.
        identity_block:      Dynamic identity prompt block (OPP-7).
                             Injected into IDENTITY prompt section.
        episodes_used:       Number of compressed episodes generated.
        recent_turns_kept:   Number of verbatim recent turns preserved.
    """

    compressed_context: str = ""
    identity_block: str = ""
    episodes_used: int = 0
    recent_turns_kept: int = 0


@dataclass
class LlmParamOverrides:
    """Result of on_pre_llm_call() -- affect hard cap enforcement (OPP-3).

    Attributes:
        max_response_tokens: Hard cap on response tokens (None = no cap).
        vocabulary_tier:     "simple" | "standard" | "rich".
        tool_budget_override: Max tools per iteration (None = no override).
        affect_band_applied: The affect band that triggered these caps.
    """

    max_response_tokens: int | None = None
    vocabulary_tier: str = "standard"
    tool_budget_override: int | None = None
    affect_band_applied: str = ""


@dataclass
class DeliveryDecision:
    """Result of on_task_complete() -- delivery strategy (OPP-8).

    Attributes:
        delivery_mode:     DeliveryMode enum name string.
        prompt_mode_hint:  Suggested prompt mode for Front LLM.
        brief:             True for one-liner presentation.
        inject_as_context: True to silently add to next turn's context.
        reasoning:         Human-readable decision explanation.
        result_class:      ResultClassification enum name string.
    """

    delivery_mode: str = "CONVERSATIONAL_WEAVE"
    prompt_mode_hint: str = "WEAVE"
    brief: bool = False
    inject_as_context: bool = False
    reasoning: str = ""
    result_class: str = "BACKGROUND"


@dataclass
class TrustGate:
    """Result of on_pre_invoke() -- trust check before capability invocation.

    Attributes:
        auto_approved:     True if trust is high enough to skip HITL.
        trust_level:       Current trust score (0.0-1.0).
        dynamic_max_rounds: Adjusted max HITL rounds for this trust level.
        gate_reasoning:    Why the gate decided approve/deny.
    """

    auto_approved: bool = False
    trust_level: float = 0.5
    dynamic_max_rounds: int = 2
    gate_reasoning: str = ""


@dataclass
class ProactiveTriggerResult:
    """Result of on_idle_tick() -- proactive scheduler check (OPP-5).

    Attributes:
        should_trigger: True if a proactive message should be sent.
        trigger_type:   Type of trigger (WAIT_STATUS, PROGRESS_UPDATE, etc).
        trigger_reason: Human-readable explanation.
    """

    should_trigger: bool = False
    trigger_type: str = ""
    trigger_reason: str = ""


@dataclass
class PacingResult:
    """Result of on_weave_flush() -- pacing plan for batch delivery (OPP-1).

    Attributes:
        use_pacing:          True if pacing should be applied.
        strategy:            PacingStrategy name.
        group_count:         Number of delivery groups.
        inter_group_delay_ms: Delay between groups.
    """

    use_pacing: bool = False
    strategy: str = "NONE"
    group_count: int = 1
    inter_group_delay_ms: list[int] = field(default_factory=lambda: [0])


# =====================================================================
# OPP Pipeline
# =====================================================================


class OppPipeline:
    """Wires all 8 OPP primitives into FSM controller lifecycle hooks.

    Usage::

        from k1.concierge.protocols.opp_pipeline import OppPipeline, OppPipelineConfig
        pipeline = OppPipeline(OppPipelineConfig())

        # Attach primitives (all optional -- None = disabled)
        pipeline.set_trust_accumulator(trust_accum)
        pipeline.set_proactive_scheduler(proactive_sched)
        pipeline.set_episodic_compressor(episodic_comp)
        pipeline.set_dynamic_identity(dynamic_id)
        pipeline.set_delivery_engine(delivery_engine)

        # Wire to controller
        controller.set_opp_pipeline(pipeline)

    The controller calls hooks at the right lifecycle points.
    Each hook is a no-op if the relevant primitive is not attached
    or not enabled in config.
    """

    __slots__ = (
        "_cfg",
        "_trust_accumulator",
        "_proactive_scheduler",
        "_episodic_compressor",
        "_dynamic_identity",
        "_delivery_engine",
    )

    def __init__(self, config: OppPipelineConfig | None = None) -> None:
        self._cfg = config or OppPipelineConfig()
        self._trust_accumulator: Any | None = None
        self._proactive_scheduler: Any | None = None
        self._episodic_compressor: Any | None = None
        self._dynamic_identity: Any | None = None
        self._delivery_engine: Any | None = None
        logger.info("OppPipeline: initialized with config=%s", self._cfg)

    # -----------------------------------------------------------------
    # Primitive attachment (all optional)
    # -----------------------------------------------------------------

    def set_trust_accumulator(self, accum: Any) -> None:
        """Attach TrustAccumulator (OPP-4)."""
        self._trust_accumulator = accum
        logger.info("OppPipeline: TrustAccumulator attached")

    def set_proactive_scheduler(self, sched: Any) -> None:
        """Attach ProactiveScheduler (OPP-5)."""
        self._proactive_scheduler = sched
        logger.info("OppPipeline: ProactiveScheduler attached")

    def set_episodic_compressor(self, comp: Any) -> None:
        """Attach EpisodicCompressor (OPP-6)."""
        self._episodic_compressor = comp
        logger.info("OppPipeline: EpisodicCompressor attached")

    def set_dynamic_identity(self, identity: Any) -> None:
        """Attach DynamicIdentityContext (OPP-7)."""
        self._dynamic_identity = identity
        logger.info("OppPipeline: DynamicIdentityContext attached")

    def set_delivery_engine(self, engine: Any) -> None:
        """Attach DeliveryStrategyEngine (OPP-8)."""
        self._delivery_engine = engine
        logger.info("OppPipeline: DeliveryStrategyEngine attached")

    @property
    def config(self) -> OppPipelineConfig:
        """Current pipeline configuration."""
        return self._cfg

    # -----------------------------------------------------------------
    # Hook: on_classify (Phase 1 enrichment) -- OPP-2
    # -----------------------------------------------------------------

    def on_classify(
        self,
        *,
        user_text: str,
        current_turn: int,
        tasks: list[dict[str, Any]] | None = None,
        arbiter_config: Any = None,
    ) -> ClassifyEnrichment:
        """Enrich Phase 1 classification with recency bias decay (OPP-2).

        Called after UltraBERT classification, before Front LLM dispatch.
        Applies exponential decay to domain/entity overlap scores in the
        arbiter and penalizes short inputs.

        OPP-2 is applied inline by the arbiter itself (it reads config
        knobs: recency_decay_per_turn, short_input_word_threshold).
        This hook reports whether the adjustments were applied, for
        observability and auditing.

        Args:
            user_text:      Raw user input text.
            current_turn:   Current conversation turn number.
            tasks:          Active task dispatches with dispatch_turn.
            arbiter_config: ArbiterConfig with OPP-2 knobs.

        Returns:
            ClassifyEnrichment with decay/penalty flags.
        """
        if not self._cfg.enable_recency_decay:
            return ClassifyEnrichment()

        from k1.concierge.fsm.arbiter import is_short_input

        decay_per_turn = 0.15
        threshold = 3
        if arbiter_config is not None:
            decay_per_turn = getattr(arbiter_config, "recency_decay_per_turn", 0.15)
            threshold = getattr(arbiter_config, "short_input_word_threshold", 3)

        short = is_short_input(user_text, threshold)
        has_tasks = bool(tasks)

        return ClassifyEnrichment(
            recency_decay_applied=has_tasks,
            short_input_penalty=short,
        )

    # -----------------------------------------------------------------
    # Hook: on_pre_prompt_build -- OPP-6 + OPP-7
    # -----------------------------------------------------------------

    def on_pre_prompt_build(
        self,
        *,
        turns: list[dict[str, Any]] | None = None,
        affect_band: str = "neutral",
        active_domains: list[str] | None = None,
        active_user_id: str = "",
        active_user_name: str = "",
    ) -> PromptEnrichment:
        """Enrich prompt context with compressed history and dynamic identity.

        Called by the Front handler's DynamicPromptBuilder before
        assembling the final prompt.  Returns text blocks that the
        builder injects into the appropriate prompt sections.

        OPP-6 (Episodic Compression):
            If conversation has enough turns, compresses old segments
            into CompressedEpisode summaries and returns a compressed
            context string.  The builder uses this instead of raw turns.

        OPP-7 (Dynamic Identity):
            Computes an IdentitySnapshot for the current turn and
            returns a prompt block that overrides the static IDENTITY
            section.  Role, formality, and attunement adapt per-turn.

        Args:
            turns:            List of conversation turn dicts (from SS).
            affect_band:      Current affect band string.
            active_domains:   Domains detected in recent turns.
            active_user_id:   Current user identifier.
            active_user_name: Current user display name.

        Returns:
            PromptEnrichment with compressed_context and identity_block.
        """
        result = PromptEnrichment()

        # --- OPP-6: Episodic Compression ---
        if (
            self._cfg.enable_episodic_compression
            and self._episodic_compressor is not None
            and turns
        ):
            try:
                comp = self._episodic_compressor
                episodes, recent = comp.compress_all(turns)
                if episodes:
                    result.compressed_context = comp.build_compressed_context(episodes, recent)
                    result.episodes_used = len(episodes)
                    result.recent_turns_kept = len(recent)
                    logger.debug(
                        "OppPipeline.on_pre_prompt_build: compressed %d episodes, "
                        "%d recent turns kept",
                        len(episodes),
                        len(recent),
                    )
            except Exception:
                logger.warning(
                    "OppPipeline: EpisodicCompressor failed, using raw turns",
                    exc_info=True,
                )

        # --- OPP-7: Dynamic Identity ---
        if self._cfg.enable_dynamic_identity and self._dynamic_identity is not None:
            try:
                snapshot = self._dynamic_identity.compute(
                    affect_band=affect_band,
                    domain=(active_domains or [""])[0] if active_domains else "",
                    user_id=active_user_id,
                    user_name=active_user_name,
                )
                if hasattr(snapshot, "to_prompt_block"):
                    result.identity_block = snapshot.to_prompt_block()
                    logger.debug(
                        "OppPipeline.on_pre_prompt_build: identity role=%s formality=%.2f",
                        snapshot.conversational_role,
                        snapshot.formality_level,
                    )
            except Exception:
                logger.warning(
                    "OppPipeline: DynamicIdentityContext failed, using static identity",
                    exc_info=True,
                )

        return result

    # -----------------------------------------------------------------
    # Hook: on_pre_llm_call -- OPP-3
    # -----------------------------------------------------------------

    def on_pre_llm_call(
        self,
        *,
        affect_band: str = "neutral",
        current_llm_params: dict[str, Any] | None = None,
    ) -> LlmParamOverrides:
        """Apply affect hard constraints to LLM generation parameters.

        Called just before the ReAct loop invokes the LLM.  Returns
        parameter overrides that the caller applies to the model call.

        OPP-3 reads the affect band and returns per-band caps on
        max_response_tokens, vocabulary_tier, and tool_budget.

        Args:
            affect_band:       Current affect band string.
            current_llm_params: Current LLM params (for reference).

        Returns:
            LlmParamOverrides with hard caps.
        """
        if not self._cfg.enable_affect_hard_caps:
            return LlmParamOverrides()

        try:
            from k1.concierge.prompt.affect import AFFECT_MODIFIERS, apply_affect_hard_constraints

            modifiers = AFFECT_MODIFIERS.get(affect_band)
            if modifiers is None:
                return LlmParamOverrides(affect_band_applied=affect_band)

            # Build a params dict and let the enforcer cap it
            params = dict(current_llm_params) if current_llm_params else {}
            capped = apply_affect_hard_constraints(modifiers, params)

            return LlmParamOverrides(
                max_response_tokens=modifiers.max_response_tokens,
                vocabulary_tier=modifiers.vocabulary_tier,
                tool_budget_override=modifiers.tool_budget_override,
                affect_band_applied=affect_band,
            )
        except Exception:
            logger.warning(
                "OppPipeline: affect hard caps failed, using defaults",
                exc_info=True,
            )
            return LlmParamOverrides()

    # -----------------------------------------------------------------
    # Hook: on_task_complete -- OPP-8
    # -----------------------------------------------------------------

    def on_task_complete(
        self,
        *,
        result: dict[str, Any],
        fsm_state: str = "",
        active_dispatch_task_ids: frozenset[str] | None = None,
        current_turn: int = 0,
        dispatch_turn: int = 0,
        has_expiry: bool = False,
        is_chained: bool = False,
        ss: Any = None,
        result_domain: str = "",
        emotional_gate: str = "open",
        weave_decision: Any = None,
    ) -> DeliveryDecision:
        """Determine HOW to deliver a completed task result (OPP-8).

        Called by the controller after WeavePolicy decides WHEN.
        Classifies the result, reads conversation flow, and selects
        the delivery mode.

        Args:
            result:                    Task result dict.
            fsm_state:                 Current FSM state name.
            active_dispatch_task_ids:  IDs from user's recent dispatch.
            current_turn:              Current turn number.
            dispatch_turn:             Turn when task was dispatched.
            has_expiry:                True if result has deadline.
            is_chained:                True if depends_on another task.
            ss:                        SessionState for flow signal.
            result_domain:             Domain of the result.
            emotional_gate:            Emotional gate from WeaveSignal.
            weave_decision:            WeaveDecision from WeavePolicy.

        Returns:
            DeliveryDecision with delivery_mode and metadata.
        """
        if not self._cfg.enable_delivery_strategy or self._delivery_engine is None:
            return DeliveryDecision()

        try:
            from k1.concierge.protocols.delivery_strategy import (
                ConversationFlowSignal,
                classify_result,
            )

            # Step 1: Classify the result
            result_class = classify_result(
                result,
                active_dispatch_task_ids=active_dispatch_task_ids,
                current_turn=current_turn,
                dispatch_turn=dispatch_turn,
                has_expiry=has_expiry,
                is_chained=is_chained,
            )

            # Step 2: Read conversation flow
            flow = ConversationFlowSignal.from_session_state(
                ss=ss,
                result_domain=result_domain,
                current_turn=current_turn,
                dispatch_turn=dispatch_turn,
            )

            # Step 3: Decide delivery strategy
            strategy = self._delivery_engine.decide(
                result_class,
                flow,
                weave_decision=weave_decision,
                fsm_state=fsm_state,
                emotional_gate=emotional_gate,
            )

            logger.info(
                "OppPipeline.on_task_complete: result_class=%s delivery_mode=%s reasoning=%s",
                result_class.name,
                strategy.delivery_mode.name,
                strategy.reasoning,
            )

            return DeliveryDecision(
                delivery_mode=strategy.delivery_mode.name,
                prompt_mode_hint=strategy.prompt_mode_hint,
                brief=strategy.brief,
                inject_as_context=strategy.inject_as_context,
                reasoning=strategy.reasoning,
                result_class=result_class.name,
            )
        except Exception:
            logger.warning(
                "OppPipeline: delivery strategy failed, falling back to WEAVE",
                exc_info=True,
            )
            return DeliveryDecision()

    # -----------------------------------------------------------------
    # Hook: on_hitl_outcome -- OPP-4
    # -----------------------------------------------------------------

    def on_hitl_outcome(
        self,
        *,
        event_type: str,
        task_id: str = "",
    ) -> None:
        """Record a HITL outcome in the trust accumulator (OPP-4).

        Called when the user approves, rejects, cancels, modifies,
        or a timeout occurs on a HITL interaction.

        Args:
            event_type: One of APPROVE, REJECT, CANCEL, MODIFY,
                        AUTO_SUCCESS, TIMEOUT.
            task_id:    The task that triggered the HITL flow.
        """
        if not self._cfg.enable_trust_accumulator or self._trust_accumulator is None:
            return

        try:
            self._trust_accumulator.record_outcome(event_type)
            logger.debug(
                "OppPipeline.on_hitl_outcome: recorded %s for task %s, " "trust=%.3f",
                event_type,
                task_id,
                self._trust_accumulator.trust_score,
            )
        except Exception:
            logger.warning(
                "OppPipeline: TrustAccumulator.record_outcome failed",
                exc_info=True,
            )

    # -----------------------------------------------------------------
    # Hook: on_pre_invoke -- OPP-4
    # -----------------------------------------------------------------

    def on_pre_invoke(
        self,
        *,
        risk_level: float = 0.5,
        base_max_rounds: int = 2,
    ) -> TrustGate:
        """Check trust level before capability invocation (OPP-4).

        Called by the FSM or L2 enforcer before a side-effect
        capability is invoked.  If trust is high enough and risk is
        low, the HITL approval step can be skipped.

        Args:
            risk_level:      Estimated risk (0.0-1.0) of this action.
            base_max_rounds: Default max HITL rounds without trust.

        Returns:
            TrustGate with auto_approved flag and dynamic max rounds.
        """
        if not self._cfg.enable_trust_accumulator or self._trust_accumulator is None:
            return TrustGate(dynamic_max_rounds=base_max_rounds)

        try:
            risk_str = "low" if risk_level < 0.3 else ("medium" if risk_level < 0.7 else "high")
            auto = self._trust_accumulator.should_auto_approve(risk_str)
            dynamic_rounds = self._trust_accumulator.get_dynamic_max_rounds(base_max_rounds)
            level = self._trust_accumulator.trust_score

            gate_reason = (
                f"trust={level:.3f}, risk={risk_level:.2f}, "
                f"auto_approved={auto}, rounds={dynamic_rounds}"
            )

            return TrustGate(
                auto_approved=auto,
                trust_level=level,
                dynamic_max_rounds=dynamic_rounds,
                gate_reasoning=gate_reason,
            )
        except Exception:
            logger.warning(
                "OppPipeline: TrustAccumulator gate check failed",
                exc_info=True,
            )
            return TrustGate(dynamic_max_rounds=base_max_rounds)

    # -----------------------------------------------------------------
    # Hook: on_idle_tick -- OPP-5
    # -----------------------------------------------------------------

    def on_idle_tick(
        self,
        *,
        fsm_state: str = "",
        user_idle_ms: int = 0,
        affect_band: str = "neutral",
        active_task_count: int = 0,
        session_turn_count: int = 0,
    ) -> ProactiveTriggerResult:
        """Check if a proactive message should be sent (OPP-5).

        Called by the FSM's 1-second idle timer.  If the scheduler
        determines a proactive message is appropriate, the controller
        emits a proactive fill event.

        Args:
            fsm_state:          Current FSM state name.
            user_idle_ms:       Milliseconds since last user input.
            affect_band:        Current affect band.
            active_task_count:  Number of in-flight tasks.
            session_turn_count: Total turns in this session.

        Returns:
            ProactiveTriggerResult with should_trigger flag.
        """
        if not self._cfg.enable_proactive_scheduler or self._proactive_scheduler is None:
            return ProactiveTriggerResult()

        try:
            trigger = self._proactive_scheduler.evaluate(
                fsm_state=fsm_state,
                user_idle_ms=user_idle_ms,
                affect_band=affect_band,
                active_task_count=active_task_count,
                session_turn_count=session_turn_count,
            )

            if trigger is not None:
                return ProactiveTriggerResult(
                    should_trigger=True,
                    trigger_type=(
                        trigger.trigger_type.name
                        if hasattr(trigger.trigger_type, "name")
                        else str(trigger.trigger_type)
                    ),
                    trigger_reason=(
                        trigger.reason if hasattr(trigger, "reason") else "proactive trigger"
                    ),
                )

            return ProactiveTriggerResult()
        except Exception:
            logger.warning(
                "OppPipeline: ProactiveScheduler.evaluate failed",
                exc_info=True,
            )
            return ProactiveTriggerResult()

    # -----------------------------------------------------------------
    # Hook: on_weave_flush -- OPP-1
    # -----------------------------------------------------------------

    def on_weave_flush(
        self,
        *,
        results: list[dict[str, Any]],
        batch_count: int = 1,
    ) -> PacingResult:
        """Compute a pacing plan for batch result delivery (OPP-1).

        Called when the WeaveBatcher is about to flush results.
        Returns a PacingResult that tells the batcher whether to
        use paced delivery and with what strategy.

        Args:
            results:     The batched results about to be flushed.
            batch_count: How many results in this batch.

        Returns:
            PacingResult with pacing strategy and delays.
        """
        if not self._cfg.enable_paced_delivery or batch_count <= 1:
            return PacingResult()

        try:
            from k1.concierge.protocols.weave_policy import PacingStrategy, compute_pacing_plan

            # Choose strategy based on batch size
            if batch_count >= 4:
                strategy = PacingStrategy.PRIORITY_CASCADE
            elif batch_count >= 2:
                # Check if results span multiple domains
                domains = {r.get("domain", "unknown") for r in results}
                strategy = (
                    PacingStrategy.GROUP_BY_DOMAIN if len(domains) > 1 else PacingStrategy.STAGGER
                )
            else:
                return PacingResult()

            plan = compute_pacing_plan(results, strategy)

            return PacingResult(
                use_pacing=plan.strategy != PacingStrategy.NONE,
                strategy=plan.strategy.name,
                group_count=len(plan.groups),
                inter_group_delay_ms=plan.inter_group_delay_ms,
            )
        except Exception:
            logger.warning(
                "OppPipeline: pacing plan computation failed",
                exc_info=True,
            )
            return PacingResult()

    # -----------------------------------------------------------------
    # Hook: on_natural_pause -- OPP-8 deferred drain
    # -----------------------------------------------------------------

    def on_natural_pause(
        self,
        *,
        deferred_results: list[dict[str, Any]],
    ) -> list[DeliveryDecision]:
        """Re-evaluate deferred results when a natural pause occurs.

        Called by the FSM when it detects a topic shift, explicit
        "what else?", or extended idle.  Returns delivery decisions
        for any deferred results that should now be presented.

        Args:
            deferred_results: Results in the deferred queue.

        Returns:
            List of DeliveryDecision for results to deliver now.
        """
        if not self._cfg.enable_delivery_strategy or self._delivery_engine is None:
            return []

        try:
            strategies = self._delivery_engine.on_natural_pause(deferred_results)
            return [
                DeliveryDecision(
                    delivery_mode=s.delivery_mode.name,
                    prompt_mode_hint=s.prompt_mode_hint,
                    brief=s.brief,
                    inject_as_context=s.inject_as_context,
                    reasoning=s.reasoning,
                    result_class=s.result_class.name,
                )
                for s in strategies
            ]
        except Exception:
            logger.warning(
                "OppPipeline: on_natural_pause failed",
                exc_info=True,
            )
            return []

    # -----------------------------------------------------------------
    # Diagnostics
    # -----------------------------------------------------------------

    def status(self) -> dict[str, Any]:
        """Return attachment status of all primitives for diagnostics."""
        return {
            "opp1_paced_delivery": self._cfg.enable_paced_delivery,
            "opp2_recency_decay": self._cfg.enable_recency_decay,
            "opp3_affect_hard_caps": self._cfg.enable_affect_hard_caps,
            "opp4_trust_accumulator": (
                self._cfg.enable_trust_accumulator and self._trust_accumulator is not None
            ),
            "opp5_proactive_scheduler": (
                self._cfg.enable_proactive_scheduler and self._proactive_scheduler is not None
            ),
            "opp6_episodic_compression": (
                self._cfg.enable_episodic_compression and self._episodic_compressor is not None
            ),
            "opp7_dynamic_identity": (
                self._cfg.enable_dynamic_identity and self._dynamic_identity is not None
            ),
            "opp8_delivery_strategy": (
                self._cfg.enable_delivery_strategy and self._delivery_engine is not None
            ),
            "trust_level": (
                self._trust_accumulator.trust_score
                if self._trust_accumulator is not None
                and hasattr(self._trust_accumulator, "trust_score")
                else None
            ),
        }
