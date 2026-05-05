"""``ISituationFramePort`` — compose ``S(actor) ∩ F ∩ C`` at ``(T, D)``.

The SituationFrame is the only object the rest of K1 consumes from
``k1.selfmodel``. Implementation lands in M1
(``service/situation_composer.py``).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from k1.selfmodel.contracts.situation import SituationFrame

__all__ = ["ISituationFramePort"]


@runtime_checkable
class ISituationFramePort(Protocol):
    """Compose the triple intersection at a specific ``(T, D, situation)``."""

    def compose(
        self,
        actor_id: str,
        T_ms: int,
        device_id: str,
        situation_kind: str,
    ) -> SituationFrame:
        """Build the SituationFrame.

        ``situation_kind`` is one of S1..S13 from the V0 Family
        Operating Design (whiteboard).
        """
        ...
