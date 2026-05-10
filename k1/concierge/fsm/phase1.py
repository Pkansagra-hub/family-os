"""
k1.concierge.fsm.phase1 -- Phase 1 (UltraBERT) integration & TurnLock sequencing.

V2 Design Ref: Section 4 (Phase 1 deterministic writes before Front LLM),
               Section 5 (TurnLock, Write-then-Refine pattern)

Phase 1 runs FIRST in every turn, BEFORE the Front LLM starts. It performs
deterministic classification (no LLM call) and writes to 3 SS sections:

  | Section        | What Phase 1 Writes                              |
  |----------------|--------------------------------------------------|
  | scoreboard     | intents[], entities[], salience_map{}             |
  | affective_now  | primary_emotion, confidence, valence, arousal     |
  | control        | intent_classification, domain_context, safety_band|

Sequential ordering guarantee (TurnLock from V2 Section 5):
  user.input arrives
    |
  TurnLock.acquire()                    # FSM acquires turn lock
    |
  Phase 1: UltraBERT classification     # Deterministic, ~22ms
    - Write scoreboard (intents, entities, salience)
    - Write affective_now (emotion)
    - Write control (intent, domain, safety)
    |
  TurnLock.release()                    # Phase 1 writes committed
    |
  Front LLM starts                      # Reads Phase 1 values from SS

Why this ordering matters: Front LLM reads scoreboard (QUD, intents),
affective_now (emotion for tone matching), and control (safety band) from
SS. If Phase 1 writes are NOT committed before Front reads, Front gets
stale values from the previous turn.

Write-then-Refine pattern (V2 Section 5):
  Phase 1 sets initial values. Front LLM may refine via cognitive tools:
    - scoreboard: Front extends via update_scoreboard() (does not replace)
    - affective_now: Front overrides via refine_affect() (if confidence > 0.8)
    - control: Front reads but does NOT write control directly
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Phase1Result
# ---------------------------------------------------------------------------


class Phase1Result:
    """Result of Phase 1 (UltraBERT) deterministic classification.

    Carries all classification outputs that Phase 1 writes to SessionState.
    The FSM uses this to write to scoreboard, affective_now, and control
    sections BEFORE the Front LLM starts.
    """

    __slots__ = (
        "intents",
        "entities",
        "salience_map",
        "primary_emotion",
        "emotion_confidence",
        "valence",
        "arousal",
        "intent_classification",
        "domain_context",
        "safety_band",
        # P3.4a: complexity_tier removed; tier derivation moved to dispatch_task.
        "temporal_expressions",
        "relations",
        "_degraded",
    )

    def __init__(
        self,
        intents: list[str] | None = None,
        entities: list[dict[str, Any]] | None = None,
        salience_map: dict[str, float] | None = None,
        primary_emotion: str = "neutral",
        emotion_confidence: float = 0.5,
        valence: float = 0.0,
        arousal: float = 0.0,
        intent_classification: str = "general",
        domain_context: str = "general",
        safety_band: str = "GREEN",
        temporal_expressions: list[dict[str, Any]] | None = None,
        relations: list[str] | None = None,
    ) -> None:
        self.intents = intents or []
        self.entities = entities or []
        self.salience_map = salience_map or {}
        self.primary_emotion = primary_emotion
        self.emotion_confidence = emotion_confidence
        self.valence = valence
        self.arousal = arousal
        self.intent_classification = intent_classification
        self.domain_context = domain_context
        self.safety_band = safety_band
        self.temporal_expressions = temporal_expressions or []
        self.relations = relations or []
        self._degraded = False

    def to_metadata(self) -> dict[str, Any]:
        """Convert to metadata dict for TypedHistoryEntry attachment.

        Phase 1 classification results are attached to the "user"
        TypedHistoryEntry as metadata (V2 Section 5). DynamicPromptBuilder
        (M09) uses this to construct the Session Trajectory view.
        """
        return {
            "intent": self.intent_classification,
            "emotion": self.primary_emotion,
            "emotion_confidence": self.emotion_confidence,
            "entities": self.entities,
            "safety_band": self.safety_band,
            "domain": self.domain_context,
            # P3.4a: complexity_tier removed.
            "temporal_expressions": self.temporal_expressions,
            "relations": self.relations,
        }


# ---------------------------------------------------------------------------
# Phase1Pipeline protocol
# ---------------------------------------------------------------------------


class Phase1Pipeline(Protocol):
    """Protocol for Phase 1 (UltraBERT) classification pipeline.

    Phase 1 is deterministic (~22ms). It does NOT call an LLM.
    It classifies the user's raw input text and produces:
      - Intent classification (what the user wants)
      - Entity extraction (named entities, dates, numbers)
      - Salience scoring (which parts of the message matter most)
      - Emotion classification (primary emotion, valence, arousal)
      - Domain context (travel, health, finance, etc.)
      - Safety band (GREEN/AMBER/RED)
      # P3.4a: complexity_tier removed; tier derivation moved to dispatch_task.
    """

    def classify(self, text: str) -> Phase1Result:
        """Classify user input text.

        Args:
            text: Raw user input text.

        Returns:
            Phase1Result with all classification outputs.
        """
        ...


# ---------------------------------------------------------------------------
# StubPhase1Pipeline (POC placeholder)
# ---------------------------------------------------------------------------


class StubPhase1Pipeline:
    """Stub Phase 1 pipeline for the POC.

    Returns default/neutral classifications. The real UltraBERT pipeline
    would perform transformer-based classification here.

    This stub is sufficient for the POC because:
      1. Front LLM refines Phase 1 values via cognitive tools anyway.
      2. The FSM transition logic does not depend on Phase 1 content.
      3. The architecture (TurnLock sequencing) is validated by the stub.
    """

    def __init__(self) -> None:
        self._call_count = 0
        self._last_text: str = ""
        self._last_result: Phase1Result | None = None
        logger.info("StubPhase1Pipeline initialized (keyword-based classification)")

    @property
    def call_count(self) -> int:
        """Number of times classify() has been called."""
        return self._call_count

    @property
    def last_text(self) -> str:
        """The last text classified."""
        return self._last_text

    @property
    def last_result(self) -> Phase1Result | None:
        """The result of the last classification."""
        return self._last_result

    def classify(self, text: str) -> Phase1Result:
        """Classify user input text with stub defaults.

        Returns neutral values for all fields. The stub performs basic
        keyword matching for domain and intent to make tests more realistic.
        """
        self._call_count += 1
        self._last_text = text
        lower = text.lower()

        # Basic keyword-based classification (POC only)
        domain = "general"
        intent = "general"

        if any(w in lower for w in ("hotel", "flight", "travel", "book", "trip")):
            domain = "travel"
            intent = "booking"
        elif any(w in lower for w in ("doctor", "dentist", "health", "appointment")):
            domain = "health"
            intent = "scheduling"
        elif any(w in lower for w in ("weather", "forecast")):
            domain = "information"
            intent = "query"
        elif any(w in lower for w in ("cancel", "stop", "nevermind")):
            intent = "cancel"
        elif any(w in lower for w in ("hi", "hello", "hey")):
            intent = "greeting"

        result = Phase1Result(
            intents=[intent],
            entities=[],
            salience_map={},
            primary_emotion="neutral",
            emotion_confidence=0.5,
            valence=0.0,
            arousal=0.0,
            intent_classification=intent,
            domain_context=domain,
            safety_band="GREEN",
        )

        self._last_result = result
        logger.debug(
            "StubPhase1: classified '%s' -> intent=%s, domain=%s, safety=%s",
            text[:50],
            intent,
            domain,
            result.safety_band,
        )
        return result


# ---------------------------------------------------------------------------
# KeywordPhase1Pipeline (richer keyword baseline for production fallback)
# ---------------------------------------------------------------------------

# Domain → keywords. Used by KeywordPhase1Pipeline when UltraBERT is
# unavailable. ~200 keywords across home/finance/health/calendar/travel
# plus greeting/cancel/safety lexicons. Multi-domain matches surface
# multiple intents in Phase1Result.intents[].
_KEYWORD_DOMAINS: dict[str, tuple[str, ...]] = {
    "home": (
        "home",
        "house",
        "apartment",
        "kitchen",
        "living room",
        "bedroom",
        "bathroom",
        "garage",
        "garden",
        "yard",
        "lawn",
        "driveway",
        "vacuum",
        "dishwasher",
        "laundry",
        "dishes",
        "sweep",
        "mop",
        "clean",
        "tidy",
        "fridge",
        "refrigerator",
        "oven",
        "stove",
        "thermostat",
        "heater",
        "ac",
        "air conditioner",
        "lights",
        "lamp",
        "outlet",
        "plug",
        "switch",
        "wifi",
        "router",
        "doorbell",
        "lock",
        "alarm",
        "smoke detector",
        "trash",
        "recycling",
        "groceries",
        "shopping list",
        "household",
        "chore",
        "repair",
        "plumber",
        "electrician",
        "leaking",
        "broken",
    ),
    "finance": (
        "money",
        "cash",
        "bank",
        "account",
        "deposit",
        "withdraw",
        "transfer",
        "wire",
        "balance",
        "statement",
        "credit card",
        "debit card",
        "loan",
        "mortgage",
        "rent",
        "bill",
        "invoice",
        "payment",
        "pay",
        "paid",
        "owe",
        "debt",
        "interest",
        "apr",
        "savings",
        "investment",
        "stock",
        "share",
        "portfolio",
        "dividend",
        "tax",
        "irs",
        "refund",
        "deduction",
        "salary",
        "paycheck",
        "income",
        "expense",
        "budget",
        "spending",
        "subscription",
        "venmo",
        "paypal",
        "zelle",
        "transaction",
        "fee",
        "charge",
        "insurance",
        "premium",
        "claim",
        "401k",
        "ira",
        "retirement",
    ),
    "health": (
        "doctor",
        "dentist",
        "physician",
        "specialist",
        "clinic",
        "hospital",
        "er",
        "emergency",
        "ambulance",
        "urgent care",
        "appointment",
        "checkup",
        "exam",
        "physical",
        "blood test",
        "x-ray",
        "mri",
        "scan",
        "biopsy",
        "surgery",
        "operation",
        "prescription",
        "pharmacy",
        "refill",
        "medication",
        "med",
        "pill",
        "dose",
        "dosage",
        "antibiotic",
        "vaccine",
        "shot",
        "flu",
        "cold",
        "fever",
        "cough",
        "headache",
        "migraine",
        "pain",
        "ache",
        "sore",
        "injury",
        "hurt",
        "wound",
        "rash",
        "allergy",
        "asthma",
        "diabetes",
        "blood pressure",
        "cholesterol",
        "therapy",
        "therapist",
        "counselor",
        "mental health",
        "anxiety",
        "depression",
        "sleep",
        "insomnia",
        "diet",
        "nutrition",
        "exercise",
        "workout",
        "gym",
        "yoga",
    ),
    "calendar": (
        "calendar",
        "schedule",
        "reschedule",
        "appointment",
        "meeting",
        "event",
        "remind",
        "reminder",
        "alarm",
        "wake up",
        "today",
        "tomorrow",
        "tonight",
        "morning",
        "afternoon",
        "evening",
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
        "weekend",
        "weekday",
        "next week",
        "this week",
        "last week",
        "next month",
        "this month",
        "january",
        "february",
        "march",
        "april",
        "may",
        "june",
        "july",
        "august",
        "september",
        "october",
        "november",
        "december",
        "noon",
        "midnight",
        "am",
        "pm",
        "deadline",
        "due date",
        "agenda",
        "rsvp",
        "invite",
        "invitation",
        "birthday",
        "anniversary",
        "holiday",
        "vacation day",
    ),
    "travel": (
        "hotel",
        "flight",
        "airline",
        "airport",
        "boarding pass",
        "passport",
        "visa",
        "tsa",
        "luggage",
        "baggage",
        "suitcase",
        "carry on",
        "trip",
        "travel",
        "vacation",
        "holiday",
        "getaway",
        "cruise",
        "resort",
        "airbnb",
        "booking",
        "reservation",
        "itinerary",
        "destination",
        "departure",
        "arrival",
        "layover",
        "rental car",
        "uber",
        "lyft",
        "taxi",
        "train",
        "subway",
        "tour",
        "sightseeing",
        "tourist",
    ),
}

_GREETING_KEYWORDS: tuple[str, ...] = (
    "hi",
    "hello",
    "hey",
    "hiya",
    "good morning",
    "good afternoon",
    "good evening",
    "howdy",
    "yo",
    "greetings",
)
_CANCEL_KEYWORDS: tuple[str, ...] = (
    "cancel",
    "stop",
    "nevermind",
    "never mind",
    "abort",
    "scratch that",
    "forget it",
    "drop it",
    "quit",
)
_RED_SAFETY_KEYWORDS: tuple[str, ...] = (
    "suicide",
    "kill myself",
    "self harm",
    "self-harm",
    "overdose",
    "abuse",
    "violence",
)
_AMBER_SAFETY_KEYWORDS: tuple[str, ...] = (
    "emergency",
    "er ",
    "911",
    "ambulance",
    "bleeding",
    "chest pain",
    "stroke",
    "heart attack",
    "unconscious",
)


class KeywordPhase1Pipeline:
    """Richer deterministic Phase 1 baseline (production fallback).

    Used when the UltraBERT adapter is unavailable. Compared to
    ``StubPhase1Pipeline``, this:
      * Covers home / finance / health / calendar / travel domains
        (~200 keywords total).
      * Detects bundled multi-domain requests by populating
        ``intents[]`` with one entry per matched domain.
      * Performs a coarse safety-band sweep (RED on self-harm,
        AMBER on emergencies, GREEN otherwise).

    Same shape as ``Phase1Pipeline`` -- drop-in replacement.
    """

    __slots__ = ("_call_count", "_last_text", "_last_result")

    def __init__(self) -> None:
        self._call_count = 0
        self._last_text: str = ""
        self._last_result: Phase1Result | None = None
        logger.info(
            "KeywordPhase1Pipeline initialized " "(richer keyword baseline; UltraBERT fallback)"
        )

    @property
    def call_count(self) -> int:
        return self._call_count

    @property
    def last_text(self) -> str:
        return self._last_text

    @property
    def last_result(self) -> Phase1Result | None:
        return self._last_result

    @staticmethod
    def _matches_any(lower: str, kws: tuple[str, ...]) -> bool:
        return any(kw in lower for kw in kws)

    def classify(self, text: str) -> Phase1Result:
        self._call_count += 1
        self._last_text = text
        lower = text.lower()

        # Detect domains with at least one keyword hit.
        matched_domains: list[str] = []
        for domain, kws in _KEYWORD_DOMAINS.items():
            if self._matches_any(lower, kws):
                matched_domains.append(domain)

        # Greeting / cancel intents are independent of domain.
        is_greeting = self._matches_any(lower, _GREETING_KEYWORDS)
        is_cancel = self._matches_any(lower, _CANCEL_KEYWORDS)

        # Build intents[] -- multi-domain hits surface multiple entries
        # (downstream uses len(intents) >= 2 as the BUNDLED signal).
        intents: list[str] = []
        if is_cancel:
            intents.append("cancel")
        if is_greeting and not intents:
            intents.append("greeting")
        for d in matched_domains:
            intents.append(self._domain_intent(d))
        if not intents:
            intents.append("general")

        primary_domain = matched_domains[0] if matched_domains else "general"
        primary_intent = intents[0]

        # Safety band sweep.
        if self._matches_any(lower, _RED_SAFETY_KEYWORDS):
            safety_band = "RED"
        elif self._matches_any(lower, _AMBER_SAFETY_KEYWORDS):
            safety_band = "AMBER"
        else:
            safety_band = "GREEN"

        result = Phase1Result(
            intents=intents,
            entities=[],
            salience_map={},
            primary_emotion="neutral",
            emotion_confidence=0.5,
            valence=0.0,
            arousal=0.0,
            intent_classification=primary_intent,
            domain_context=primary_domain,
            safety_band=safety_band,
        )
        self._last_result = result
        logger.debug(
            "KeywordPhase1: '%s' -> intents=%s, domain=%s, safety=%s",
            text[:50],
            intents,
            primary_domain,
            safety_band,
        )
        return result

    @staticmethod
    def _domain_intent(domain: str) -> str:
        # Map a matched domain to a coarse-grained intent label.
        return {
            "home": "home_task",
            "finance": "finance_task",
            "health": "health_task",
            "calendar": "calendar_task",
            "travel": "booking",
        }.get(domain, "general")


# ---------------------------------------------------------------------------
# TurnLock
# ---------------------------------------------------------------------------


class TurnLock:
    """Sequencing gate ensuring Phase 1 completes before Front LLM starts.

    The TurnLock guarantees:
      1. Phase 1 writes are committed to SS before Front reads them.
      2. Only one classification runs at a time (no concurrent Phase 1s).
      3. Front LLM cannot start until the lock is released.

    Implementation: Simple boolean flag (not asyncio.Lock) because the POC
    is synchronous within a single turn. Production would use asyncio.Lock
    for true concurrent protection.
    """

    def __init__(self) -> None:
        self._held = False
        self._holder: str = ""
        self._acquire_count: int = 0

    @property
    def is_held(self) -> bool:
        """True if the lock is currently held."""
        return self._held

    @property
    def holder(self) -> str:
        """Name of the current lock holder (for debugging)."""
        return self._holder

    @property
    def acquire_count(self) -> int:
        """Total number of times the lock has been acquired."""
        return self._acquire_count

    def acquire(self, holder: str = "phase1") -> bool:
        """Acquire the turn lock.

        Args:
            holder: Name of the acquirer (for debugging).

        Returns:
            True if acquired, False if already held.
        """
        if self._held:
            logger.warning(
                "TurnLock: already held by '%s', cannot acquire for '%s'",
                self._holder,
                holder,
            )
            return False
        self._held = True
        self._holder = holder
        self._acquire_count += 1
        logger.debug("TurnLock: acquired by '%s'", holder)
        return True

    def release(self) -> bool:
        """Release the turn lock.

        Returns:
            True if released, False if not held.
        """
        if not self._held:
            logger.warning("TurnLock: release called but not held")
            return False
        holder = self._holder
        self._held = False
        self._holder = ""
        logger.debug("TurnLock: released by '%s'", holder)
        return True

    def reset(self) -> None:
        """Force-reset the lock (for testing/teardown)."""
        self._held = False
        self._holder = ""
