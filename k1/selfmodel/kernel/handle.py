"""``SelfModelHandle`` — per-session bind for ``k1.selfmodel``.

M5.E3.I3: Constructed once per session in ``KernelService.create_session``
at phase **P3.5** (after P3 per-session Fabric, before P4 Concierge).

The handle holds:

* A reference to the shared :class:`SelfModelServiceBundle`.
* Per-session identity (``session_id``, ``actor_id``, ``device_id``).
* A pre-built :class:`ConciergePolicyGate` already wired to the
  bundle's evaluator + composer (frame_provider).
* A pre-built :class:`GroundingCapsuleRenderer` that calls the bundle's
  composer with the session's ``(actor_id, device_id, situation_kind)``.

The handle exposes an ``install_into_session`` method that:

1. Installs the gate as step-0 on the front + back :class:`ToolDispatcher`
   instances.
2. Wraps ``ToolContext.recall_fn`` for both contexts with a
   :class:`RecallCitationWrapper` (no-op when the original is ``None``).
3. Stores the renderer so the caller (kernel) can attach it to the
   prompt builder pipeline at call time.

``uninstall_from_session`` reverses every step so destroy flows leave
no dangling references. Both calls are idempotent.

This module performs **no business logic** — it only wires existing
M0–M4 components into the per-session containers.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from k1.selfmodel.adapters.concierge_policy_gate import ConciergePolicyGate
from k1.selfmodel.adapters.grounding_capsule_renderer import GroundingCapsuleRenderer
from k1.selfmodel.adapters.recall_citation_wrapper import RecallCitationWrapper
from k1.selfmodel.contracts.situation import SituationFrame
from k1.selfmodel.kernel.bootstrap import SelfModelServiceBundle

if TYPE_CHECKING:  # pragma: no cover
    from k1.concierge.tools.dispatcher import ToolDispatcher
    from k1.concierge.tools.implementations import ToolContext

logger = logging.getLogger(__name__)

__all__ = [
    "SelfModelHandle",
    "build_self_model_handle",
    "DEFAULT_SITUATION_KIND",
]

#: Fallback ``situation_kind`` when no caller-supplied value is on hand.
#: ``caregiver_context_briefing`` (S12) is the broadest read-only V0
#: situation; using it for the always-on prompt capsule keeps the
#: composer producing a non-empty frame for every session.
DEFAULT_SITUATION_KIND = "caregiver_context_briefing"


@dataclass
class SelfModelHandle:
    """Per-session selfmodel wiring.

    Reverse-cleanup is the responsibility of
    :meth:`uninstall_from_session` so destroy flows can drop the
    wrapper safely.
    """

    bundle: SelfModelServiceBundle
    session_id: str
    actor_id: str
    device_id: str
    situation_kind: str = DEFAULT_SITUATION_KIND
    gate: ConciergePolicyGate | None = None
    renderer: GroundingCapsuleRenderer | None = None
    # Internal: track installed dispatchers so uninstall is precise.
    _installed_dispatchers: list["ToolDispatcher"] = field(default_factory=list, repr=False)
    # Internal: track contexts whose recall_fn we replaced, with the
    # original callback so we can restore on uninstall.
    _wrapped_contexts: list[tuple["ToolContext", Any]] = field(default_factory=list, repr=False)

    # ------------------------------------------------------------------
    # Public surface
    # ------------------------------------------------------------------
    def install_into_session(
        self,
        *,
        front_dispatcher: "ToolDispatcher | None" = None,
        back_dispatcher: "ToolDispatcher | None" = None,
        front_ctx: "ToolContext | None" = None,
        back_ctx: "ToolContext | None" = None,
    ) -> None:
        """Wire the gate + recall wrapper into the per-session components.

        Idempotent: calling twice with the same dispatchers/contexts is
        a no-op (``set_policy_gate`` overwrites; the recall wrapper is
        skipped if already wrapped on this handle).
        """
        if self.gate is None:
            return  # nothing to install

        # ── Install gate as step-0 on every dispatcher ────────────
        for dispatcher in (front_dispatcher, back_dispatcher):
            if dispatcher is None:
                continue
            setter = getattr(dispatcher, "set_policy_gate", None)
            if not callable(setter):
                logger.warning(
                    "SelfModelHandle.install: dispatcher %r has no set_policy_gate",
                    type(dispatcher).__name__,
                )
                continue
            setter(self.gate.evaluate)
            if dispatcher not in self._installed_dispatchers:
                self._installed_dispatchers.append(dispatcher)

        # ── Wrap recall_fn on every ToolContext ────────────────────
        for ctx in (front_ctx, back_ctx):
            if ctx is None:
                continue
            inner = getattr(ctx, "recall_fn", None)
            if inner is None:
                # Nothing to wrap — leave the field None so the
                # baseline empty-result shim keeps working.
                continue
            if isinstance(inner, RecallCitationWrapper):
                continue  # already wired by a previous install call
            wrapper = RecallCitationWrapper(
                inner=inner,
                actor_id=self.actor_id,
                builder=self.bundle.citation_builder,
            )
            ctx.recall_fn = wrapper
            self._wrapped_contexts.append((ctx, inner))

    def uninstall_from_session(self) -> None:
        """Reverse every step performed by :meth:`install_into_session`.

        Safe to call multiple times. Used by ``destroy_session`` so
        destroyed sessions release their selfmodel hooks.
        """
        for dispatcher in self._installed_dispatchers:
            try:
                dispatcher.set_policy_gate(None)
            except Exception:  # pragma: no cover
                logger.warning("uninstall: clear_policy_gate failed", exc_info=True)
        self._installed_dispatchers.clear()

        for ctx, original in self._wrapped_contexts:
            try:
                ctx.recall_fn = original
            except Exception:  # pragma: no cover
                logger.warning("uninstall: recall_fn restore failed", exc_info=True)
        self._wrapped_contexts.clear()

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------
    def render_capsule(self) -> Any:
        """Return ``GroundingCapsule | None`` from the bound renderer."""
        if self.renderer is None:
            return None
        return self.renderer.render()

    def current_frame(self) -> SituationFrame:
        """Compose the current ``SituationFrame`` for this session."""
        return self.bundle.composer.compose(
            self.actor_id,
            int(time.time() * 1000),
            self.device_id,
            self.situation_kind,
        )


def _build_frame_provider(
    bundle: SelfModelServiceBundle,
    *,
    actor_id: str,
    device_id: str,
    situation_kind: str,
    clock_ms: Callable[[], int],
) -> Callable[[Any], SituationFrame]:
    """Return a frame-provider closure suitable for the policy gate.

    The gate's ``frame_provider`` callable receives the ``ToolCallResult``
    (which we ignore at this layer — a tool call uses the same situation
    binding as the rest of the session). Composer reads the live store
    each call so freshness changes propagate without re-binding.
    """

    def _provider(_tool_call: Any) -> SituationFrame:
        return bundle.composer.compose(actor_id, int(clock_ms()), device_id, situation_kind)

    return _provider


def build_self_model_handle(
    bundle: SelfModelServiceBundle,
    *,
    session_id: str,
    actor_id: str,
    device_id: str = "",
    situation_kind: str = DEFAULT_SITUATION_KIND,
    hil_service: Any | None = None,
    clock_ms: Callable[[], int] | None = None,
    bus: Any | None = None,
    current_tier_fn: Callable[[], int] | None = None,
    trace_id_fn: Callable[[], str] | None = None,
    approval_timeout_ms: int = 120_000,
) -> SelfModelHandle:
    """Construct a per-session :class:`SelfModelHandle`.

    Wires:

    * :class:`ConciergePolicyGate` against the bundle's evaluator,
      using a frame_provider that closes over ``(actor_id, device_id,
      situation_kind)``.
    * :class:`GroundingCapsuleRenderer` against the bundle's capsule
      builder + the same frame closure.
    """
    if not session_id:
        raise ValueError("session_id is required")
    if not actor_id:
        raise ValueError("actor_id is required")

    _clock = clock_ms or (lambda: int(time.time() * 1000))
    frame_provider = _build_frame_provider(
        bundle,
        actor_id=actor_id,
        device_id=device_id,
        situation_kind=situation_kind,
        clock_ms=_clock,
    )

    gate = ConciergePolicyGate(
        actor_id=actor_id,
        frame_provider=frame_provider,
        hil_service=hil_service,
        evaluator=bundle.evaluator,
        bus=bus,
        current_tier_fn=current_tier_fn,
        trace_id_fn=trace_id_fn,
        approval_timeout_ms=approval_timeout_ms,
    )

    # Renderer drives the prompt builder; same frame closure but
    # needs the no-arg shape ``Callable[[], SituationFrame]`` so we
    # adapt with a thin lambda that ignores the gate's tool_call slot.
    renderer = GroundingCapsuleRenderer(
        builder=bundle.capsule_builder,
        frame_provider=lambda: frame_provider(None),
    )

    return SelfModelHandle(
        bundle=bundle,
        session_id=session_id,
        actor_id=actor_id,
        device_id=device_id,
        situation_kind=situation_kind,
        gate=gate,
        renderer=renderer,
    )
