"""``FabricRiskCatalog`` — fabric-backed risk catalog adapter (M9.E1.I2).

Implements :class:`k1.selfmodel.ports.risk_catalog.IRiskCatalogPort`
by querying fabric's :class:`CapabilityRegistry` for the per-capability
``risk_class`` and ``social_act`` declared in each tool/agent/workflow
contract.

Fallback chain:

1. Fabric registry lookup via ``registry.lookup(name)``. If the
   contract has a non-default ``risk_class``, it wins.
2. Legacy in-process map from
   :mod:`k1.selfmodel.contracts.risk_class_registry`. Kept as a
   transitional shim until every YAML contract carries explicit
   ``risk_class`` (M9.E1.I3 deletes this fallback).
3. Fail-closed default :data:`RiskClass.SAFETY_SENSITIVE`.

The adapter is intentionally read-only and side-effect free. It emits
a single warning per unknown capability (mirroring the legacy
registry's behaviour).
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Optional

from k1.selfmodel.contracts.policy import RiskClass
from k1.selfmodel.contracts.risk_class_registry import (
    FAIL_CLOSED_DEFAULT,
    RISK_CLASS_BY_TOOL,
)
from k1.selfmodel.events.topics import TOPIC_RISK_FALLBACK
from k1.selfmodel.ports.risk_catalog import IRiskCatalogPort

__all__ = ["FabricRiskCatalog", "StaticRiskCatalog"]

logger = logging.getLogger(__name__)


def _publish_fallback(bus: Any, capability_name: str, source: str) -> None:
    """Best-effort one-shot bus emit on risk fallback (M12.E2.I3).

    Caller is responsible for deduping via its ``_warned`` lockset; this
    helper just attempts the publish and swallows transport errors so a
    misconfigured bus never breaks the catalog hot path.
    """
    if bus is None:
        return
    payload = {
        "capability_name": capability_name,
        "fallback_risk_class": FAIL_CLOSED_DEFAULT.value,
        "source": source,
    }
    try:
        publish = getattr(bus, "publish", None)
        if publish is None:
            return
        publish(TOPIC_RISK_FALLBACK, payload)
    except Exception:  # pragma: no cover - defensive
        logger.debug(
            "risk_fallback_publish_failed capability=%s",
            capability_name,
            exc_info=True,
        )


# Map fabric YAML strings → RiskClass enum members.
_RISK_BY_STRING: dict[str, RiskClass] = {
    "low": RiskClass.LOW,
    "medium": RiskClass.MEDIUM,
    "high": RiskClass.HIGH,
    "safety_sensitive": RiskClass.SAFETY_SENSITIVE,
}


def _coerce_risk_class(value: Any) -> RiskClass | None:
    """Best-effort coercion from a YAML/string/enum value to RiskClass."""
    if isinstance(value, RiskClass):
        return value
    if isinstance(value, str):
        return _RISK_BY_STRING.get(value.strip().lower())
    return None


class FabricRiskCatalog(IRiskCatalogPort):
    """Production adapter — queries fabric's CapabilityRegistry."""

    __slots__ = ("_registry", "_lock", "_warned", "_bus")

    def __init__(self, registry: Any, *, bus: Any = None) -> None:
        """Args:
        registry: fabric ``CapabilityRegistry`` (any object with a
            ``lookup(name) -> contract | None`` method). We type it as
            ``Any`` to avoid pulling fabric into selfmodel's import
            graph at module-load time.
        bus: optional event bus. When supplied, fallback to
            ``FAIL_CLOSED_DEFAULT`` publishes a one-shot
            ``k1.selfmodel.risk.fallback.v1`` event per capability
            (M12.E2.I3).
        """
        if registry is None:
            raise ValueError("registry is required")
        self._registry = registry
        self._lock = threading.Lock()
        self._warned: set[str] = set()
        self._bus = bus

    # ------------------------------------------------------------------
    def get_risk(self, capability_name: str) -> RiskClass:
        if not isinstance(capability_name, str) or not capability_name:
            return FAIL_CLOSED_DEFAULT

        contract = self._lookup(capability_name)
        if contract is not None:
            declared = _coerce_risk_class(getattr(contract, "risk_class", None))
            # Treat "safety_sensitive" as the YAML default sentinel; if a
            # contract explicitly opts into safety_sensitive that's still
            # the right answer.
            if declared is not None:
                return declared

        legacy = RISK_CLASS_BY_TOOL.get(capability_name)
        if legacy is not None:
            return legacy

        with self._lock:
            if capability_name not in self._warned:
                self._warned.add(capability_name)
                logger.warning(
                    "fabric_risk_catalog_unknown capability=%s -> fail_closed=%s",
                    capability_name,
                    FAIL_CLOSED_DEFAULT.value,
                )
                _publish_fallback(self._bus, capability_name, "fabric")
        return FAIL_CLOSED_DEFAULT

    # ------------------------------------------------------------------
    def get_social_act(self, capability_name: str) -> Optional[str]:
        if not isinstance(capability_name, str) or not capability_name:
            return None
        contract = self._lookup(capability_name)
        if contract is None:
            return None
        act = getattr(contract, "social_act", None)
        if isinstance(act, str) and act:
            return act
        return None

    # ------------------------------------------------------------------
    def _lookup(self, name: str) -> Any | None:
        try:
            return self._registry.lookup(name)
        except Exception:  # pragma: no cover - defensive
            logger.debug(
                "fabric_risk_catalog_lookup_failed capability=%s",
                name,
                exc_info=True,
            )
            return None


class StaticRiskCatalog(IRiskCatalogPort):
    """Test/legacy adapter — pure dict lookup, no fabric dependency.

    Backed by :data:`RISK_CLASS_BY_TOOL`. Equivalent to calling
    ``get_risk_class(name)`` directly. Useful for unit tests and as a
    drop-in for environments where fabric isn't booted.
    """

    __slots__ = ("_extra", "_lock", "_warned", "_bus")

    def __init__(
        self,
        *,
        extra: dict[str, RiskClass] | None = None,
        bus: Any = None,
    ) -> None:
        self._extra: dict[str, RiskClass] = dict(extra or {})
        self._lock = threading.Lock()
        self._warned: set[str] = set()
        self._bus = bus

    def get_risk(self, capability_name: str) -> RiskClass:
        if not isinstance(capability_name, str) or not capability_name:
            return FAIL_CLOSED_DEFAULT
        risk = self._extra.get(capability_name) or RISK_CLASS_BY_TOOL.get(capability_name)
        if risk is not None:
            return risk
        with self._lock:
            if capability_name not in self._warned:
                self._warned.add(capability_name)
                logger.warning(
                    "static_risk_catalog_unknown capability=%s -> fail_closed=%s",
                    capability_name,
                    FAIL_CLOSED_DEFAULT.value,
                )
                _publish_fallback(self._bus, capability_name, "static")
        return FAIL_CLOSED_DEFAULT

    def get_social_act(self, capability_name: str) -> Optional[str]:  # noqa: ARG002
        # Static catalog has no fabric metadata to consult.
        return None
