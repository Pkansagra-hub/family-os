"""Selfmodel observability metrics — typed wrapper around MetricsCollector.

Defines every metric name from
``docs/whiteboard/SERVICE_DESIGN_SELF_MODEL.md`` §5.5 and exposes a
small, intent-revealing API so service code never builds metric
strings inline.

The class is **fail-soft**: when no collector is wired (``None``) every
emitter is a cheap no-op. This means tests + tooling that don't set up
a collector still run unchanged.
"""

from __future__ import annotations

import logging
from typing import Optional

__all__ = ["SelfModelMetrics"]

logger = logging.getLogger(__name__)


class SelfModelMetrics:
    """Typed metric emitters for the ``k1.selfmodel`` package."""

    __slots__ = ("_c",)

    # --- Metric names (single source of truth) ------------------------
    M_COMPOSER_BUILD_MS = "selfmodel.composer.build_ms"
    M_COMPOSER_FAILURE = "selfmodel.composer.failure"
    M_COMPOSER_FRAME = "selfmodel.composer.frame_built"

    M_POLICY_DECISION = "selfmodel.policy.decision"
    M_POLICY_FAILURE = "selfmodel.policy.failure"
    M_POLICY_EVAL_MS = "selfmodel.policy.evaluate_ms"

    M_AMENDMENT_TRANSITION = "selfmodel.amendment.transition"
    M_AMENDMENT_INVALID_TRANSITION = "selfmodel.amendment.invalid_transition"

    M_CAPSULE_BUILD_MS = "selfmodel.capsule.build_ms"
    M_CAPSULE_BYTES = "selfmodel.capsule.size_bytes"
    M_CAPSULE_FAILURE = "selfmodel.capsule.failure"

    M_CITATION_PACK_SIZE = "selfmodel.citation.pack_size"
    M_CITATION_BUILD_MS = "selfmodel.citation.build_ms"

    M_BRIDGE_SUBMIT = "selfmodel.bridge.submit"
    M_BRIDGE_SUBMIT_FAILURE = "selfmodel.bridge.submit_failure"
    M_BRIDGE_SSE_EVENT = "selfmodel.bridge.sse_event"
    M_BRIDGE_SSE_RECONNECT = "selfmodel.bridge.sse_reconnect"

    M_INVARIANT_VIOLATION = "selfmodel.invariant.violation"

    def __init__(self, collector: Optional[object] = None) -> None:
        # Duck-type the collector so we can also accept None / a stub.
        self._c = collector

    # ------------------------------------------------------------------
    # Composer
    # ------------------------------------------------------------------
    def composer_build_ms(self, ms: float, *, situation_kind: str) -> None:
        self._observe(self.M_COMPOSER_BUILD_MS, ms, {"situation_kind": situation_kind})
        self._inc(self.M_COMPOSER_FRAME, {"situation_kind": situation_kind})

    def composer_failure(self, *, situation_kind: str, error: str) -> None:
        self._inc(self.M_COMPOSER_FAILURE, {"situation_kind": situation_kind, "error": error})

    # ------------------------------------------------------------------
    # Policy
    # ------------------------------------------------------------------
    def policy_decision(self, *, decision: str, reason: str, risk_class: str) -> None:
        self._inc(
            self.M_POLICY_DECISION,
            {"decision": decision, "reason": reason, "risk_class": risk_class},
        )

    def policy_evaluate_ms(self, ms: float, *, decision: str) -> None:
        self._observe(self.M_POLICY_EVAL_MS, ms, {"decision": decision})

    def policy_failure(self, *, error: str) -> None:
        self._inc(self.M_POLICY_FAILURE, {"error": error})

    # ------------------------------------------------------------------
    # Amendments
    # ------------------------------------------------------------------
    def amendment_transition(self, *, from_state: str, to_state: str) -> None:
        self._inc(
            self.M_AMENDMENT_TRANSITION,
            {"from": from_state, "to": to_state},
        )

    def amendment_invalid_transition(self, *, from_state: str, attempted: str) -> None:
        self._inc(
            self.M_AMENDMENT_INVALID_TRANSITION,
            {"from": from_state, "attempted": attempted},
        )

    # ------------------------------------------------------------------
    # Capsule
    # ------------------------------------------------------------------
    def capsule_build_ms(self, ms: float) -> None:
        self._observe(self.M_CAPSULE_BUILD_MS, ms, {})

    def capsule_bytes(self, size: int) -> None:
        self._observe(self.M_CAPSULE_BYTES, float(size), {})

    def capsule_failure(self, *, error: str) -> None:
        self._inc(self.M_CAPSULE_FAILURE, {"error": error})

    # ------------------------------------------------------------------
    # Citation
    # ------------------------------------------------------------------
    def citation_pack(self, *, size: int, build_ms: float) -> None:
        self._observe(self.M_CITATION_PACK_SIZE, float(size), {})
        self._observe(self.M_CITATION_BUILD_MS, build_ms, {})

    # ------------------------------------------------------------------
    # Bridge
    # ------------------------------------------------------------------
    def bridge_submit(self, *, topic: str, band: str) -> None:
        self._inc(self.M_BRIDGE_SUBMIT, {"topic": topic, "band": band})

    def bridge_submit_failure(self, *, topic: str, error: str) -> None:
        self._inc(self.M_BRIDGE_SUBMIT_FAILURE, {"topic": topic, "error": error})

    def bridge_sse_event(self, *, topic: str) -> None:
        self._inc(self.M_BRIDGE_SSE_EVENT, {"topic": topic})

    def bridge_sse_reconnect(self) -> None:
        self._inc(self.M_BRIDGE_SSE_RECONNECT, {})

    # ------------------------------------------------------------------
    # Invariants
    # ------------------------------------------------------------------
    def invariant_violation(self, *, code: str, detail: str = "") -> None:
        # Always log loudly — invariant violations are CI gates.
        logger.error("SELFMODEL INVARIANT VIOLATION code=%s detail=%s", code, detail)
        self._inc(self.M_INVARIANT_VIOLATION, {"code": code})

    # ------------------------------------------------------------------
    # Internal — fail-soft duck-typed dispatch.
    # ------------------------------------------------------------------
    def _inc(self, name: str, labels: dict) -> None:
        c = self._c
        if c is None:
            return
        try:
            c.increment(name, labels=labels)
        except Exception:
            logger.exception("metric increment failed name=%s", name)

    def _observe(self, name: str, value: float, labels: dict) -> None:
        c = self._c
        if c is None:
            return
        try:
            c.observe(name, labels=labels, value=value)
        except Exception:
            logger.exception("metric observe failed name=%s", name)
