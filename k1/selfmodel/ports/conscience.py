"""``IConsciencePort`` -- digest-only access to the conscience (M10.E1.I2).

Downstream consumers (the policy gate, audit log, observability
sinks) frequently need only a single question answered:
"is this social act forbidden / must-ask for this actor right now?"

Recomposing a full :class:`SituationFrame` for that is wasteful and
couples the consumer to every input the composer needs (relations,
visibility, freshness, ...). This port hands back a
:class:`ConscienceDigest` directly.

A digest is per ``(actor_id, T_ms, device_id)`` tuple because:

* ``actor_id`` selects the conscience role.
* ``T_ms`` lets the implementation decide whether a cached digest is
  still fresh.
* ``device_id`` allows per-device overrides (e.g. a kiosk in the
  living room may have stricter ``must_ask`` than a personal phone).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from k1.selfmodel.contracts.conscience import ConscienceDigest

__all__ = ["IConsciencePort"]


@runtime_checkable
class IConsciencePort(Protocol):
    """Read-only conscience digest accessor."""

    def get_digest(
        self,
        actor_id: str,
        *,
        T_ms: int,
        device_id: str | None = None,
    ) -> ConscienceDigest:
        """Return the conscience digest applicable to the actor.

        Implementations MUST be side-effect free and SHOULD be cheap
        enough to call in the policy gate's hot path. An empty
        :class:`ConscienceDigest` is a valid (default-allow) return
        value.
        """
        ...
