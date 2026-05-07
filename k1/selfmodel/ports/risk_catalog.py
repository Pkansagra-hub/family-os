"""``IRiskCatalogPort`` — selfmodel's view of fabric risk metadata (M9.E1.I2).

The constitution must not embed the names of fabric tools
(``send_message``, ``set_medication``, ...). Instead, each fabric
capability declares its own ``RiskClass`` and ``social_act`` binding
in its YAML contract; selfmodel queries them through this port at
evaluation time.

Adapters:

* :class:`k1.selfmodel.adapters.fabric_risk_catalog.FabricRiskCatalog`
  — production adapter; queries fabric's :class:`CapabilityRegistry`
  with a fail-closed legacy fallback to
  :mod:`k1.selfmodel.contracts.risk_class_registry`.

The port is intentionally tiny — selfmodel only needs to know
"how risky is this capability?" and "what social act does it
manifest?". Anything richer (latency, cost, side-effects) is fabric's
own concern and stays inside fabric.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from k1.selfmodel.contracts.policy import RiskClass

__all__ = ["IRiskCatalogPort"]


@runtime_checkable
class IRiskCatalogPort(Protocol):
    """Read-only access to per-capability risk + social-act metadata."""

    def get_risk(self, capability_name: str) -> RiskClass:
        """Return the declared risk class for ``capability_name``.

        Implementations MUST fail-closed: an unknown capability returns
        :data:`RiskClass.SAFETY_SENSITIVE`. Implementations MAY emit a
        single warning per unknown name.
        """
        ...

    def get_social_act(self, capability_name: str) -> str | None:
        """Return the declared social act id for ``capability_name``.

        ``None`` = capability is infrastructure-only (no social
        binding); the conscience never gates such calls and they fall
        through on their declared risk alone.
        """
        ...
