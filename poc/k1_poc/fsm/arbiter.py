"""
poc.k1_poc.fsm.arbiter -- Conversation Arbiter (M5 E5.1)
=========================================================

Replaces the keyword-based InterruptClassifier with a context-aware
arbitration layer that classifies user input against inflight work.

Decision table (priority order, first match wins):
  1. RED safety band -> CANCEL all
  2. Cancel intent + inflight tasks -> CANCEL (targeted or all)
  3. Cancel intent + no inflight -> PARALLEL_NEW
  4. Domain+entity overlap above threshold + inflight -> MODIFY_INFLIGHT
  5. Defer pattern match + inflight -> DEFER
  6. Inflight tasks present -> PARALLEL_NEW
  7. No inflight tasks -> PARALLEL_NEW

The Arbiter runs synchronously in the FSM controller (no LLM call).
All decisions are deterministic: same inputs = same output.

V3 Design Ref: WB 3.B, WB 8.3, WB 13.5
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from poc.k1_poc.config import ArbiterConfig, get_config
from poc.k1_poc.fsm.phase1 import Phase1Result

logger = logging.getLogger(__name__)


# =========================================================================
# 5.1.1 -- ArbiterDecision enum and ArbiterResult dataclass
# =========================================================================


class ArbiterDecision(str, Enum):
    """Four possible routing decisions from the Conversation Arbiter."""

    CANCEL = "cancel"
    MODIFY_INFLIGHT = "modify_inflight"
    PARALLEL_NEW = "parallel_new"
    DEFER = "defer"


@dataclass
class ArbiterResult:
    """Structured output from ConversationArbiter.classify().

    Carries the routing decision plus all context needed by the FSM
    to execute the decision without re-examining the input.
    """

    decision: ArbiterDecision
    confidence: float
    target_task_id: str | None
    modification_params: dict[str, Any] | None
    routing_metadata: dict[str, Any]
    phase1: Phase1Result

    def to_dict(self) -> dict[str, Any]:
        """JSON-serializable dict for ledger/observability."""
        return {
            "decision": self.decision.value,
            "confidence": self.confidence,
            "target_task_id": self.target_task_id,
            "modification_params": self.modification_params,
            "routing_metadata": self.routing_metadata,
            "phase1": self.phase1.to_metadata(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ArbiterResult:
        """Reconstruct from dict (round-trip support)."""
        phase1_meta = data.get("phase1", {})
        phase1 = Phase1Result(
            intent_classification=phase1_meta.get("intent", "general"),
            domain_context=phase1_meta.get("domain", "general"),
            safety_band=phase1_meta.get("safety_band", "GREEN"),
            primary_emotion=phase1_meta.get("emotion", "neutral"),
            emotion_confidence=phase1_meta.get("emotion_confidence", 0.5),
            entities=phase1_meta.get("entities", []),
        )
        return cls(
            decision=ArbiterDecision(data["decision"]),
            confidence=data.get("confidence", 0.0),
            target_task_id=data.get("target_task_id"),
            modification_params=data.get("modification_params"),
            routing_metadata=data.get("routing_metadata", {}),
            phase1=phase1,
        )


# =========================================================================
# 5.1.2 -- InflightContext snapshot from runtime state
# =========================================================================


@dataclass
class InflightTask:
    """Snapshot of a single inflight task for Arbiter consumption."""

    task_id: str
    action: str
    domain: str
    status: str
    progress_pct: float
    dispatch_turn: int
    pending_hil: bool
    entities: list[str] = field(default_factory=list)


@dataclass
class InflightContext:
    """Read-only snapshot of all inflight work at the moment of user input.

    M7 E7.5.6: Extended with BackPool capacity fields so the arbiter
    can make pool-aware routing decisions (e.g. downgrade PARALLEL_NEW
    to DEFER when pool is full).
    """

    tasks: list[InflightTask]
    pending_results: int
    cancelled_task_ids: set[str]
    fsm_state: str
    current_turn: int
    active_device_id: str | None = None
    # M7 E7.5.6: BackPool capacity awareness
    pool_active_workers: int = 0
    pool_size: int = 0
    pool_available: int = 0
    lease_deadlines: dict[str, int] = field(default_factory=dict)


def build_inflight_context(
    *,
    ss: Any,
    suspension_manager: Any,
    cancel_handler: Any,
    turn_state: Any,
    current_turn: int,
    device_id: str | None = None,
    back_pool: Any | None = None,
) -> InflightContext:
    """Build InflightContext snapshot from M4-bound SS sections.

    Reads task_state from SS (not TaskBridge internal), control overlay
    from SS (not ControlExtension internal), suspension state from
    SuspensionManager.

    M7 E7.5.6: Reads BackPool state for pool-aware arbiter decisions.

    Args:
        ss: SessionStateManager (primary data source, post-M4)
        suspension_manager: M3 SuspensionManager
        cancel_handler: CancellationHandler
        turn_state: FSMTurnState (for pending_results count)
        current_turn: Current turn number
        device_id: Active device ID (M5 5.4.1)
        back_pool: Optional BackPool for capacity awareness (M7 E7.5.6)

    Returns:
        Read-only InflightContext snapshot.
    """
    tasks: list[InflightTask] = []

    # Read from M4-bound SS task_state section
    task_section = None
    if ss is not None:
        try:
            task_section = ss.get_section("task_state")
        except Exception:
            pass

    if task_section is not None:
        try:
            active = task_section.get_active()
            for entry in active:
                task_id = getattr(entry, "task_id", "")
                # M6 E6.5.3: Read pending_hil from TaskStateEntry
                # (HILSubTask-backed) instead of SuspensionManager._contexts.
                entry_pending_hil = getattr(entry, "pending_hil", False)
                tasks.append(
                    InflightTask(
                        task_id=task_id,
                        action=getattr(entry, "action", ""),
                        domain=getattr(entry, "domain", "general"),
                        status=getattr(entry, "status", "unknown"),
                        progress_pct=getattr(entry, "progress_pct", 0.0),
                        dispatch_turn=getattr(entry, "dispatch_turn", 0),
                        pending_hil=entry_pending_hil,
                        entities=getattr(entry, "entities", []),
                    )
                )
        except Exception:
            logger.debug("build_inflight_context: failed to read task_state", exc_info=True)

    # Also add suspended tasks not already in the active list
    if suspension_manager is not None:
        active_ids = {t.task_id for t in tasks}
        for task_id in list(getattr(suspension_manager, "_active", {})):
            if task_id not in active_ids:
                tasks.append(
                    InflightTask(
                        task_id=task_id,
                        action="",
                        domain="general",
                        status="suspended",
                        progress_pct=0.0,
                        dispatch_turn=0,
                        pending_hil=True,
                    )
                )

    # Read FSM state from M4-bound control overlay
    fsm_state = "UNKNOWN"
    if ss is not None:
        try:
            control = ss.get_section("control")
            if control is not None:
                meta = control.get_metadata()
                overlay = meta.get("fsm_overlay", {})
                fsm_state = overlay.get("fsm_state", "UNKNOWN")
        except Exception:
            pass

    # Pending results from FSMTurnState
    pending = 0
    if turn_state is not None:
        pending = getattr(turn_state, "pending_result_count", 0)
        if callable(pending):
            pending = pending()

    # Cancelled tasks
    cancelled: set[str] = set()
    if cancel_handler is not None:
        cancelled = set(getattr(cancel_handler, "_cancelled_tasks", set()))

    # M7 E7.5.6: Read BackPool state for capacity-aware arbiter decisions
    pool_active = 0
    pool_size = 0
    pool_avail = 0
    lease_deadlines: dict[str, int] = {}
    if back_pool is not None:
        try:
            state = back_pool.get_pool_state()
            pool_active = state.get("active", 0)
            pool_size = state.get("size", 0)
            pool_avail = state.get("available", 0)
            # Collect lease deadlines from active workers
            for worker in back_pool.get_active_workers():
                if worker.lease is not None:
                    lease_deadlines[worker.task_id] = worker.lease.expires_at_ns
        except Exception:
            logger.debug("build_inflight_context: failed to read BackPool state", exc_info=True)

    return InflightContext(
        tasks=tasks,
        pending_results=pending,
        cancelled_task_ids=cancelled,
        fsm_state=fsm_state,
        current_turn=current_turn,
        active_device_id=device_id,
        pool_active_workers=pool_active,
        pool_size=pool_size,
        pool_available=pool_avail,
        lease_deadlines=lease_deadlines,
    )


# =========================================================================
# 5.1.4 -- Intent-vs-inflight similarity scoring
# =========================================================================

# Domain relationship map for fuzzy matching (POC heuristic).
# Production replaces with UltraBERT cosine similarity.
_RELATED_DOMAINS: dict[str, set[str]] = {
    "travel": {"booking", "flight", "hotel", "transportation", "vacation"},
    "booking": {"travel", "hotel", "flight", "reservation"},
    "health": {"medical", "wellness", "fitness", "nutrition"},
    "medical": {"health", "wellness", "doctor"},
    "finance": {"banking", "payment", "budgeting", "investment"},
    "banking": {"finance", "payment"},
    "food": {"dining", "restaurant", "cooking", "recipe", "nutrition"},
    "dining": {"food", "restaurant"},
}


# =========================================================================
# OPP-2 -- Recency Bias Decay (generalized kernel primitive)
# =========================================================================


def _apply_recency_decay(
    raw_score: float,
    dispatch_turn: int,
    current_turn: int,
    decay_per_turn: float | None = None,
) -> float:
    """Apply recency decay to an overlap score.

    Older inflight tasks produce weaker overlap signals. This prevents
    the arbiter from treating a 10-turn-old task the same as one
    dispatched last turn.

    Args:
        raw_score:      Undecayed overlap score (0.0 - 1.0).
        dispatch_turn:  Turn when the task was dispatched.
        current_turn:   Current conversation turn.
        decay_per_turn: Decay factor per turn. None = read from config.

    Returns:
        Decayed score, clamped to [0.0, 1.0].
    """
    if decay_per_turn is None:
        try:
            decay_per_turn = get_config().arbiter.recency_decay_per_turn
        except Exception:
            decay_per_turn = 0.15

    age = max(0, current_turn - dispatch_turn)
    if age == 0:
        return raw_score

    decayed = raw_score * (1.0 - decay_per_turn) ** age
    return max(0.0, min(1.0, decayed))


def is_short_input(text: str, threshold: int | None = None) -> bool:
    """Check if user input is too short for reliable overlap scoring.

    Short inputs like "ok", "yes", "sure" should not trigger
    MODIFY_INFLIGHT because they lack semantic content for reliable
    domain/entity matching.

    Args:
        text:      Raw user input.
        threshold: Word count threshold. None = read from config.

    Returns:
        True if input has fewer words than threshold.
    """
    if threshold is None:
        try:
            threshold = get_config().arbiter.short_input_word_threshold
        except Exception:
            threshold = 3

    words = text.strip().split()
    return len(words) < threshold


def domain_overlap(phase1: Phase1Result, inflight: InflightContext) -> float:
    """Score [0.0, 1.0] how much the new input's domain matches inflight tasks.

    POC: exact string match = 1.0, related domain = 0.5, else 0.0.
    OPP-2: Recency decay -- older tasks get lower overlap scores.
    Production: cosine similarity on UltraBERT domain embeddings.
    """
    if not inflight.tasks:
        return 0.0

    input_domain = (phase1.domain_context or "").lower().strip()
    if not input_domain or input_domain == "general":
        return 0.0

    best = 0.0
    related = _RELATED_DOMAINS.get(input_domain, set())

    for task in inflight.tasks:
        task_domain = (task.domain or "").lower().strip()
        if not task_domain or task_domain == "general":
            continue

        raw_score = 0.0
        if input_domain == task_domain:
            raw_score = 1.0
        elif task_domain in related:
            raw_score = 0.5
        else:
            task_related = _RELATED_DOMAINS.get(task_domain, set())
            if input_domain in task_related:
                raw_score = 0.5

        if raw_score > 0.0:
            decayed = _apply_recency_decay(raw_score, task.dispatch_turn, inflight.current_turn)
            best = max(best, decayed)

    return best


def entity_overlap(phase1: Phase1Result, inflight: InflightContext) -> float:
    """Score [0.0, 1.0] how much the new input's entities match inflight tasks.

    POC: Jaccard coefficient on entity text sets.
    OPP-2: Per-task Jaccard with recency decay, take best score.
    Production: entity-linking via NER model.
    """
    if not inflight.tasks:
        return 0.0

    # Extract entity text from Phase1Result
    input_entities: set[str] = set()
    for ent in phase1.entities:
        if isinstance(ent, dict):
            text = ent.get("text", ent.get("name", ""))
        elif isinstance(ent, str):
            text = ent
        else:
            continue
        if text:
            input_entities.add(text.lower().strip())

    if not input_entities:
        return 0.0

    best = 0.0
    for task in inflight.tasks:
        task_entities: set[str] = set()
        for ent_text in task.entities:
            if ent_text:
                task_entities.add(ent_text.lower().strip())

        if not task_entities:
            continue

        intersection = input_entities & task_entities
        union = input_entities | task_entities
        raw_jaccard = len(intersection) / len(union) if union else 0.0

        if raw_jaccard > 0.0:
            decayed = _apply_recency_decay(raw_jaccard, task.dispatch_turn, inflight.current_turn)
            best = max(best, decayed)

    return best


# =========================================================================
# 5.1.3 -- ConversationArbiter.classify() with decision table
# =========================================================================

# Default defer/cancel keyword sets. Runtime reads from config.
_DEFAULT_DEFER_KEYWORDS: frozenset[str] = frozenset(
    {
        "ok",
        "okay",
        "sure",
        "keep going",
        "i'll wait",
        "no rush",
        "take your time",
        "sounds good",
        "got it",
        "alright",
        "fine",
        "go ahead",
        "continue",
        "carry on",
    }
)

_DEFAULT_CANCEL_KEYWORDS: frozenset[str] = frozenset(
    {
        "cancel",
        "stop",
        "abort",
        "nevermind",
        "never mind",
        "don't bother",
        "forget it",
        "skip it",
        "call it off",
    }
)

_CANCEL_ALL_KEYWORDS: frozenset[str] = frozenset(
    {
        "cancel everything",
        "stop all",
        "cancel all",
        "stop everything",
        "abort all",
        "abort everything",
    }
)


class ConversationArbiter:
    """Context-aware intent arbiter replacing keyword-based InterruptClassifier.

    Runs synchronously (no LLM call). Receives Phase1Result and
    InflightContext, returns deterministic ArbiterResult.

    The decision table is evaluated in strict priority order (safety first).
    """

    def __init__(self, config: ArbiterConfig | None = None) -> None:
        self._config = config or get_config().arbiter
        self._classify_count: int = 0
        self._last_result: ArbiterResult | None = None

        # Load keywords from config with fallbacks
        self._defer_keywords = frozenset(
            getattr(self._config, "defer_keywords", None) or _DEFAULT_DEFER_KEYWORDS
        )
        self._cancel_keywords = frozenset(
            getattr(self._config, "cancel_keywords", None) or _DEFAULT_CANCEL_KEYWORDS
        )

        logger.info(
            "ConversationArbiter initialized "
            "(domain_thresh=%.2f, entity_thresh=%.2f, "
            "cancel_kw=%d, defer_kw=%d)",
            self._config.domain_overlap_threshold,
            self._config.entity_overlap_threshold,
            len(self._cancel_keywords),
            len(self._defer_keywords),
        )

    @property
    def classify_count(self) -> int:
        """Number of classifications performed."""
        return self._classify_count

    @property
    def last_result(self) -> ArbiterResult | None:
        """Last classification result."""
        return self._last_result

    def classify(
        self,
        text: str,
        phase1: Phase1Result,
        inflight: InflightContext,
    ) -> ArbiterResult:
        """Classify user input against inflight context.

        Decision table (priority order, first match wins):
          1. RED safety band -> CANCEL all
          2. Cancel intent + inflight -> CANCEL (targeted or all)
          3. Cancel intent + no inflight -> PARALLEL_NEW
          4. Domain+entity overlap thresholds met + inflight -> MODIFY_INFLIGHT
          5. Defer pattern + inflight -> DEFER
          6. Inflight present -> PARALLEL_NEW
          7. No inflight -> PARALLEL_NEW

        Args:
            text: Raw user input text.
            phase1: Phase 1 classification result.
            inflight: Snapshot of all inflight work.

        Returns:
            Deterministic ArbiterResult.
        """
        self._classify_count += 1
        lower = text.lower().strip()
        has_inflight = len(inflight.tasks) > 0

        # Compute metadata once for all paths
        d_overlap = domain_overlap(phase1, inflight) if has_inflight else 0.0
        e_overlap = entity_overlap(phase1, inflight) if has_inflight else 0.0

        # OPP-2: Short input penalty -- reduce confidence of overlap-based
        # decisions when input is too short for reliable matching
        short_input = is_short_input(text)
        if short_input and has_inflight:
            d_overlap *= 0.5
            e_overlap *= 0.5

        routing_metadata = {
            "intent_class": phase1.intent_classification,
            "domain_overlap_score": round(d_overlap, 3),
            "entity_overlap_score": round(e_overlap, 3),
            "safety_band": phase1.safety_band,
            "inflight_task_count": len(inflight.tasks),
            "pending_result_count": inflight.pending_results,
        }

        # --- Priority 1: Safety override ---
        if phase1.safety_band == "RED":
            result = self._make_result(
                decision=ArbiterDecision.CANCEL,
                confidence=1.0,
                target_task_id=None,  # Cancel ALL
                phase1=phase1,
                routing_metadata=routing_metadata,
                reason="safety_red",
            )
            self._last_result = result
            return result

        # --- Priority 2: Cancel intent + inflight tasks ---
        is_cancel = self._detect_cancel_intent(lower, phase1)
        if is_cancel and has_inflight:
            cancel_all = self._detect_cancel_all(lower)
            target = (
                None
                if cancel_all
                else self._select_cancel_target(
                    lower,
                    phase1,
                    inflight,
                )
            )
            result = self._make_result(
                decision=ArbiterDecision.CANCEL,
                confidence=0.9 if target else 0.85,
                target_task_id=target,
                phase1=phase1,
                routing_metadata=routing_metadata,
                reason="cancel_intent",
            )
            self._last_result = result
            return result

        # --- Priority 3: Cancel intent + no inflight ---
        if is_cancel and not has_inflight:
            result = self._make_result(
                decision=ArbiterDecision.PARALLEL_NEW,
                confidence=0.7,
                phase1=phase1,
                routing_metadata=routing_metadata,
                reason="cancel_no_inflight",
            )
            self._last_result = result
            return result

        # --- Priority 4: Modify inflight (domain+entity overlap) ---
        if (
            has_inflight
            and d_overlap >= self._config.domain_overlap_threshold
            and e_overlap >= self._config.entity_overlap_threshold
        ):
            target = self._select_modify_target(phase1, inflight)
            result = self._make_result(
                decision=ArbiterDecision.MODIFY_INFLIGHT,
                confidence=min(d_overlap, e_overlap),
                target_task_id=target,
                modification_params=self._extract_modification_params(text, phase1),
                phase1=phase1,
                routing_metadata=routing_metadata,
                reason="domain_entity_overlap",
            )
            self._last_result = result
            return result

        # --- Priority 5: Defer pattern + inflight ---
        if has_inflight and self._detect_defer_intent(lower):
            result = self._make_result(
                decision=ArbiterDecision.DEFER,
                confidence=0.8,
                phase1=phase1,
                routing_metadata=routing_metadata,
                reason="defer_pattern",
            )
            self._last_result = result
            return result

        # --- Priority 6/7: Parallel new (default) ---
        result = self._make_result(
            decision=ArbiterDecision.PARALLEL_NEW,
            confidence=0.9 if not has_inflight else 0.75,
            phase1=phase1,
            routing_metadata=routing_metadata,
            reason="default_parallel",
        )
        self._last_result = result
        return result

    # -----------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------

    def _detect_cancel_intent(self, lower: str, phase1: Phase1Result) -> bool:
        """Check if user input expresses cancel intent."""
        if phase1.intent_classification == "cancel":
            return True
        for kw in self._cancel_keywords:
            if kw in lower:
                return True
        return False

    @staticmethod
    def _detect_cancel_all(lower: str) -> bool:
        """Check if user wants to cancel ALL inflight tasks."""
        for kw in _CANCEL_ALL_KEYWORDS:
            if kw in lower:
                return True
        return False

    def _detect_defer_intent(self, lower: str) -> bool:
        """Check if user input matches defer patterns."""
        for kw in self._defer_keywords:
            if lower == kw or lower.startswith(kw + " ") or lower.endswith(" " + kw):
                return True
        # Also match if the entire input is a defer keyword (exact match)
        if lower in self._defer_keywords:
            return True
        return False

    @staticmethod
    def _select_cancel_target(
        lower: str,
        phase1: Phase1Result,
        inflight: InflightContext,
    ) -> str | None:
        """Select which inflight task to cancel.

        Returns:
            task_id of the target task, or None to cancel all.
        """
        if len(inflight.tasks) == 1:
            return inflight.tasks[0].task_id

        # Try to match by domain/entity overlap
        best_task: InflightTask | None = None
        best_score = 0.0
        for task in inflight.tasks:
            # Simple: check if task action keywords appear in user text
            score = 0.0
            if task.action and task.action.lower() in lower:
                score += 1.0
            if task.domain and task.domain.lower() in lower:
                score += 0.5
            for ent in task.entities:
                if ent.lower() in lower:
                    score += 0.3
            if score > best_score:
                best_score = score
                best_task = task

        if best_task and best_score > 0:
            return best_task.task_id

        # Fallback: cancel highest-progress task
        if inflight.tasks:
            by_progress = sorted(inflight.tasks, key=lambda t: t.progress_pct, reverse=True)
            return by_progress[0].task_id

        return None

    @staticmethod
    def _select_modify_target(
        phase1: Phase1Result,
        inflight: InflightContext,
    ) -> str | None:
        """Select which inflight task to modify based on overlap."""
        if len(inflight.tasks) == 1:
            return inflight.tasks[0].task_id

        input_domain = (phase1.domain_context or "").lower()
        for task in inflight.tasks:
            if (task.domain or "").lower() == input_domain:
                return task.task_id

        # Fallback: first task
        return inflight.tasks[0].task_id if inflight.tasks else None

    @staticmethod
    def _extract_modification_params(text: str, phase1: Phase1Result) -> dict[str, Any]:
        """Extract parameter modifications from user text.

        POC: returns entities and raw text. Production: structured NER extraction.
        """
        params: dict[str, Any] = {"raw_text": text}
        for ent in phase1.entities:
            if isinstance(ent, dict):
                etype = ent.get("type", "unknown")
                evalue = ent.get("text", ent.get("value", ""))
                if etype and evalue:
                    params[etype] = evalue
        return params

    @staticmethod
    def _make_result(
        *,
        decision: ArbiterDecision,
        confidence: float,
        phase1: Phase1Result,
        routing_metadata: dict[str, Any],
        reason: str,
        target_task_id: str | None = None,
        modification_params: dict[str, Any] | None = None,
    ) -> ArbiterResult:
        """Build ArbiterResult and log."""
        routing_metadata["arbiter_reason"] = reason
        logger.debug(
            "Arbiter: %s (conf=%.2f, target=%s, reason=%s)",
            decision.value,
            confidence,
            target_task_id or "all/none",
            reason,
        )
        return ArbiterResult(
            decision=decision,
            confidence=confidence,
            target_task_id=target_task_id,
            modification_params=modification_params,
            routing_metadata=routing_metadata,
            phase1=phase1,
        )

    # -----------------------------------------------------------------
    # M5 E5.4.2: Multi-device conflict resolution
    # -----------------------------------------------------------------

    # Precedence table (lower number = higher priority):
    #   1. Cancel/stop
    #   2. Safety-critical (RED band)
    #   3. HITL response (links to suspended task)
    #   4. Modify inflight
    #   5. New request (PARALLEL_NEW)
    #   6. Defer

    _DECISION_PRIORITY: dict[ArbiterDecision, int] = {
        ArbiterDecision.CANCEL: 1,
        ArbiterDecision.MODIFY_INFLIGHT: 4,
        ArbiterDecision.PARALLEL_NEW: 5,
        ArbiterDecision.DEFER: 6,
    }

    def resolve_device_conflict(
        self,
        current_input: ArbiterResult,
        queued_inputs: list[tuple[str, ArbiterResult]],
    ) -> list[ArbiterResult]:
        """Return inputs in precedence order (highest priority first).

        M5 E5.4.2: Deterministic resolution for multi-device conflicts.
        Safety-critical (RED band) inputs get priority 2 regardless of
        their ArbiterDecision. Same-priority inputs resolve by recency
        (last timestamp wins -- the later item in queued_inputs).

        Args:
            current_input: The most recent ArbiterResult.
            queued_inputs: List of (device_id, ArbiterResult) pairs for
                other pending inputs.

        Returns:
            All inputs sorted by precedence (highest priority first).
        """
        all_items: list[tuple[int, int, ArbiterResult]] = []

        def _priority(result: ArbiterResult) -> int:
            # Safety-critical override: RED band always gets priority 2
            if result.phase1.safety_band == "RED":
                return 2
            return self._DECISION_PRIORITY.get(result.decision, 5)

        # Add current input (index 0 = most recent)
        all_items.append((_priority(current_input), 0, current_input))

        # Add queued inputs (higher index = older)
        for idx, (device_id, result) in enumerate(queued_inputs, start=1):
            all_items.append((_priority(result), idx, result))

        # Sort by (priority ASC, index ASC) -- lower priority number first,
        # ties broken by recency (lower index = more recent)
        all_items.sort(key=lambda item: (item[0], item[1]))

        return [item[2] for item in all_items]

    # -----------------------------------------------------------------
    # M5 E5.4.3: High-impact conflict detection
    # -----------------------------------------------------------------

    def detect_high_impact_conflict(
        self,
        result_a: ArbiterResult,
        device_a: str,
        result_b: ArbiterResult,
        device_b: str,
    ) -> bool:
        """Check if two device inputs create a high-impact conflict.

        A conflict exists when:
        - Different devices (device_a != device_b)
        - At least one input is high-impact (safety band or action type)
        - The decisions are contradictory (e.g., one books, one cancels)

        Args:
            result_a: First device's ArbiterResult.
            device_a: First device ID.
            result_b: Second device's ArbiterResult.
            device_b: Second device ID.

        Returns:
            True if confirmation is required.
        """
        if device_a == device_b:
            return False

        if not self._config.high_impact_confirmation_required:
            return False

        high_impact_actions = set(
            getattr(self._config, "high_impact_actions", [])
            or ["booking", "payment", "deletion", "send_message"]
        )

        a_is_high = (
            result_a.phase1.safety_band == "RED"
            or result_a.phase1.intent_classification in high_impact_actions
        )
        b_is_high = (
            result_b.phase1.safety_band == "RED"
            or result_b.phase1.intent_classification in high_impact_actions
        )

        if not (a_is_high or b_is_high):
            return False

        # Contradictory: one cancels while the other proceeds, or both
        # are high-impact but different actions
        a_is_cancel = result_a.decision == ArbiterDecision.CANCEL
        b_is_cancel = result_b.decision == ArbiterDecision.CANCEL

        if a_is_cancel != b_is_cancel:
            return True  # One cancels, one proceeds -- conflict

        if a_is_high and b_is_high:
            # Both high-impact, different intents
            if result_a.phase1.intent_classification != result_b.phase1.intent_classification:
                return True

        return False

    def build_conflict_clarification(
        self,
        result_a: ArbiterResult,
        device_a: str,
        result_b: ArbiterResult,
        device_b: str,
    ) -> dict[str, Any]:
        """Build a system-generated clarification for a device conflict.

        M5 E5.4.3: When high-impact conflicts are detected, both inputs
        are deferred and a clarification is generated for the user to resolve.

        Returns:
            Dict suitable for update_clarifications tool / writer port.
        """
        action_a = result_a.phase1.intent_classification or "unknown action"
        action_b = result_b.phase1.intent_classification or "unknown action"
        return {
            "question": (
                f"I received conflicting requests from two devices. "
                f"Device {device_a} wants to '{action_a}', "
                f"while device {device_b} wants to '{action_b}'. "
                f"Which should I proceed with?"
            ),
            "options": [
                {"label": f"Proceed with {action_a} (device {device_a})", "value": "device_a"},
                {"label": f"Proceed with {action_b} (device {device_b})", "value": "device_b"},
                {"label": "Cancel both", "value": "cancel_both"},
            ],
            "is_blocking": True,
            "priority": "URGENT",
            "source": "arbiter_device_conflict",
            "device_a": device_a,
            "device_b": device_b,
        }
