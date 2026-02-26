"""
poc.k1_poc.task.classifier -- Intent classification and dispatch building.

V2 Design Ref: Section 8.4 (Bundled Intents)
V2 Design Ref: Section 8.5 (Chained Tasks)

Front decides the intent classification based on linguistic cues and
semantic dependency analysis:

    SINGLE:   One intent, one dispatch.
    BUNDLED:  Multiple independent intents in one dispatch (intents[]).
              "Book hotel AND search restaurants" -- no data dependency.
    CHAINED:  Multiple dependent intents, separate dispatches with depends_on.
              "Book hotel THEN find restaurants near it" -- second needs first's result.

Decision protocol (V2 Section 8.4 table):
    | User pattern                                | Classification |
    |---------------------------------------------|----------------|
    | "Find me hotels in Napa"                    | SINGLE         |
    | "Book hotel AND search restaurants"          | BUNDLED        |
    | "Book hotel THEN find restaurants near it"   | CHAINED        |
    | "Book hotel, search restaurants, remind me"  | BUNDLED        |
    | "Book hotel, then use confirmation for spa"  | CHAINED        |

build_dispatches() creates the appropriate TaskDispatch(es) based on
the classification:
    SINGLE/BUNDLED -> 1 TaskDispatch with all intents
    CHAINED        -> N TaskDispatches, each with 1 intent, linked via depends_on
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any

from poc.k1_poc.task.complexity import ComplexityTier
from poc.k1_poc.task.dispatch import TaskDispatch
from poc.k1_poc.task.intent import TaskIntent

logger = logging.getLogger(__name__)


class IntentClassification(str, Enum):
    """How Front classified the user's intents for dispatch.

    SINGLE:   One intent, one dispatch.
    BUNDLED:  Multiple independent intents, one dispatch with intents[].
    CHAINED:  Multiple dependent intents, separate dispatches with depends_on.
    """

    SINGLE = "single"
    BUNDLED = "bundled"
    CHAINED = "chained"


def classify_intents(intents: list[TaskIntent]) -> IntentClassification:
    """Classify a list of intents for dispatch strategy.

    Rules (V2 Section 8.4 / 8.5):
        - 0-1 intents -> SINGLE
        - 2+ intents, none have $ref params -> BUNDLED (independent)
        - 2+ intents, any has $ref params -> CHAINED (dependent)

    In the POC, Front's LLM decides the classification and passes
    structured intents to dispatch_task.  This function validates
    the LLM's decision.

    Args:
        intents: List of TaskIntents extracted from user message.

    Returns:
        IntentClassification enum value.
    """
    if len(intents) <= 1:
        classification = IntentClassification.SINGLE
    elif any(i.has_refs() for i in intents):
        classification = IntentClassification.CHAINED
    else:
        classification = IntentClassification.BUNDLED

    logger.debug(
        "classify_intents: count=%d, classification=%s",
        len(intents),
        classification.value,
    )
    return classification


def build_dispatches(
    intents: list[TaskIntent],
    classification: IntentClassification,
    tier: ComplexityTier = ComplexityTier.MEDIUM,
    reference_context: dict[str, str] | None = None,
    safety_band: str = "AMBER",
    context_snapshot: dict[str, Any] | None = None,
) -> list[TaskDispatch]:
    """Build TaskDispatch(es) from classified intents.

    SINGLE/BUNDLED: Returns one TaskDispatch with all intents.
    CHAINED: Returns N TaskDispatches, each with one intent, linked
             via depends_on forming a sequential chain.

    Args:
        intents:           Classified intents from the user.
        classification:    How the intents were classified.
        tier:              Complexity tier (from Front's analysis).
        reference_context: Front-resolved pronoun mappings.
        safety_band:       Safety band at dispatch time.
        context_snapshot:  SS sections at dispatch time.

    Returns:
        List of TaskDispatch objects to publish on the bus.
    """
    if classification in (IntentClassification.SINGLE, IntentClassification.BUNDLED):
        dispatches = [
            TaskDispatch(
                intents=intents,
                tier=tier,
                reference_context=reference_context,
                safety_band=safety_band,
                context_snapshot=context_snapshot,
            )
        ]
        logger.debug(
            "build_dispatches: classification=%s, intents=%d -> 1 dispatch (task=%s)",
            classification.value,
            len(intents),
            dispatches[0].task_id,
        )
        return dispatches

    # CHAINED: one dispatch per intent, linked sequentially
    # V2 Section 8.5: only first dispatch gets context_snapshot and reference_context
    dispatches: list[TaskDispatch] = []
    prev_task_id: str | None = None

    for intent in intents:
        td = TaskDispatch(
            intents=[intent],
            tier=tier,
            depends_on=prev_task_id,
            reference_context=reference_context if prev_task_id is None else None,
            safety_band=safety_band,
            context_snapshot=context_snapshot if prev_task_id is None else None,
        )
        dispatches.append(td)
        prev_task_id = td.task_id

    logger.debug(
        "build_dispatches: classification=chained, intents=%d -> %d dispatches (chain=%s)",
        len(intents),
        len(dispatches),
        " -> ".join(d.task_id for d in dispatches),
    )
    return dispatches
