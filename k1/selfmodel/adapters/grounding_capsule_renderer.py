"""Adapter: renders a ``GroundingCapsule`` for the concierge prompt builder.

Lives on the K1-side of the seam. Holds a reference to the
``GroundingCapsuleBuilder`` and the per-session ``SituationFrame``
provider so the prompt builder only ever sees a pre-rendered string.

Wiring contract (M5 P3.5):

    capsule_builder = GroundingCapsuleBuilder()
    renderer = GroundingCapsuleRenderer(
        builder=capsule_builder,
        frame_provider=lambda: composer.compose(actor_id, T=now_ms(), D=device, situation_kind="..."),
    )
    prompt_builder.build(..., grounding_capsule=renderer.render())

Feature flag is enforced at call site (kernel/session bootstrap). The
adapter itself has no flag because being constructed *is* the opt-in.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, Optional

from k1.selfmodel.contracts.capsule import GroundingCapsule
from k1.selfmodel.contracts.situation import SituationFrame
from k1.selfmodel.events.topics import TOPIC_CAPSULE_UNKNOWN_ACTOR
from k1.selfmodel.service.capsule_builder import GroundingCapsuleBuilder

__all__ = ["GroundingCapsuleRenderer"]

logger = logging.getLogger(__name__)


class GroundingCapsuleRenderer:
    """Renders a :class:`GroundingCapsule` on demand for the prompt builder.

    The renderer is **fail-soft**: any exception from the frame
    provider or the builder is logged and ``render()`` returns
    ``None`` so the prompt builder skips the capsule stage. The Front
    LLM call must never crash because the selfmodel slice is briefly
    unavailable.
    """

    __slots__ = ("_builder", "_frame_provider", "_bus")

    def __init__(
        self,
        *,
        builder: GroundingCapsuleBuilder,
        frame_provider: Callable[[], SituationFrame],
        bus: Any | None = None,  # M15.E1.I3 — optional event sink
    ) -> None:
        if builder is None:
            raise ValueError("builder is required")
        if frame_provider is None or not callable(frame_provider):
            raise ValueError("frame_provider must be callable")
        self._builder = builder
        self._frame_provider = frame_provider
        self._bus = bus

    def render(self) -> Optional[GroundingCapsule]:
        """Compose a frame and render the capsule.

        Returns ``None`` (and logs) on any failure so that prompt
        construction stays alive. Callers MUST tolerate ``None``.
        """
        try:
            frame = self._frame_provider()
            logger.debug(
                "GroundingCapsuleRenderer  frame ok actor=%s self_view=%s",
                getattr(frame, "actor_id", "?"),
                getattr(frame, "self_view", None) is not None,
            )
        except Exception as exc:  # noqa: BLE001
            # M15.E1.I3 — surface UnknownActorError on the bus so
            # observability tooling sees that the capsule was skipped
            # because of a missing actor (vs. an internal crash).
            cls_name = type(exc).__name__
            if cls_name == "UnknownActorError":
                logger.warning(
                    "GroundingCapsuleRenderer  unknown actor (%s); skipping capsule",
                    exc,
                )
                self._emit_unknown_actor(str(exc))
            else:
                logger.exception(
                    "GroundingCapsuleRenderer  frame_provider failed; skipping capsule"
                )
            return None
        try:
            capsule = self._builder.build(frame)
            logger.debug(
                "GroundingCapsuleRenderer  capsule ok self_block=%r",
                bool(getattr(capsule, "self_block", "")),
            )
            return capsule
        except Exception:
            logger.exception("GroundingCapsuleRenderer  builder failed; skipping capsule")
            return None

    # ------------------------------------------------------------------
    def _emit_unknown_actor(self, detail: str) -> None:
        if self._bus is None:
            return
        payload = {"reason": "unknown_actor", "detail": detail}
        try:
            self._bus.publish(TOPIC_CAPSULE_UNKNOWN_ACTOR, payload)
        except Exception:  # noqa: BLE001
            logger.debug(
                "GroundingCapsuleRenderer  bus.publish unknown_actor failed",
                exc_info=True,
            )
