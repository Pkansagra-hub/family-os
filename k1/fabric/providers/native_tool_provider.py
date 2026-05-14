"""
k1.fabric.providers.native_tool_provider -- in-process K1-native tool provider.

``NativeToolProvider`` is the Fabric ``CapabilityProvider`` implementation
that backs every family-tool capability registered through
``k1.fabric.manifest_translator``.  It is the single, unified hand-off
from the Fabric pipeline into the family-tool runtime
(``k1.tools.family.*``).

Routing
-------
Every family-tool capability follows the canonical naming scheme:

* ``tool.read.<adapter_id>.<action_name>``
* ``tool.execute.<adapter_id>.<action_name>``

``NativeToolProvider._execute`` parses that name, looks up the matching
``IToolService`` via the injected ``IToolRegistryReader``, builds a
``WriteContext`` from the request + session state, and dispatches to
``service.dispatch(action_name, params, ctx)``.

The provider does **not** know about specific adapters -- adding a new
family tool requires zero changes here; the adapter author publishes a
``ToolDefinition``, registers it via ``manifest_translator``, and the
runtime resolves through this provider unchanged.  This is the
"generalized kernel-inbuilt apps" path called out in M15 R-3.

References
----------
* docs/plans/KERNEL_BOOTUP_PLAN.md §E15.-1 -- proof-of-path acceptance.
* docs/plans/KERNEL_BOOTUP_PLAN.md §E15.0.7 -- provider replaces the
  M14-era ``_ServiceHandler`` / ``ConnectorHost``.
* Plan invariant R-7 P10 -- no ``bridge.*`` imports from
  ``k1.tools.family.*``; this provider also avoids them.
"""

from __future__ import annotations

import inspect
import logging
from typing import Any, List, Optional

from k1.fabric.providers.base_provider import (
    BaseProvider,
    ProviderExecutionError,
)
from k1.fabric.types import (
    CapabilityRequest,
    CapabilityResult,
    ExecutionContext,
    ProviderConfig,
    ProviderHealth,
    ProviderStatus,
)
from k1.tools.family.base import WriteContext
from k1.tools.family.ports import IToolRegistryReader, IToolService

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants -- shared with manifest_translator
# ---------------------------------------------------------------------------

_CAPABILITY_PREFIXES: tuple[str, ...] = ("tool.read.", "tool.execute.")


# ---------------------------------------------------------------------------
# Capability name parsing
# ---------------------------------------------------------------------------


def _parse_capability_name(name: str) -> tuple[str, str]:
    """Return ``(adapter_id, action_name)`` for a family-tool capability.

    Raises ``ProviderExecutionError`` with a non-retriable error code if
    the name does not follow the family-tool convention.
    """

    for prefix in _CAPABILITY_PREFIXES:
        if name.startswith(prefix):
            tail = name[len(prefix) :]
            parts = tail.split(".")
            if len(parts) != 2 or not parts[0] or not parts[1]:
                raise ProviderExecutionError(
                    provider_id="k1_native_tools",
                    message=(
                        f"capability_name {name!r} must follow "
                        f"'<prefix>.<adapter_id>.<action_name>'"
                    ),
                    retriable=False,
                    error_code="invalid_capability_name",
                )
            return parts[0], parts[1]

    raise ProviderExecutionError(
        provider_id="k1_native_tools",
        message=(
            f"capability_name {name!r} is not a family-tool capability "
            f"(expected one of {list(_CAPABILITY_PREFIXES)})"
        ),
        retriable=False,
        error_code="invalid_capability_name",
    )


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------


class NativeToolProvider(BaseProvider):
    """In-process provider for every K1-native family-tool capability."""

    __slots__ = ("_registry", "_default_user_id", "_default_space_id")

    def __init__(
        self,
        config: ProviderConfig,
        *,
        registry: IToolRegistryReader,
        default_user_id: str = "system",
        default_space_id: str = "",
    ) -> None:
        """
        Args
        ----
        config:
            Provider configuration.  ``config.provider_id`` is expected
            to be ``"k1_native_tools"`` (see ``manifest_translator``)
            but is not enforced -- multiple instances can be wired for
            isolation / tests.
        registry:
            Lookup over registered ``IToolService`` instances.  Required.
        default_user_id:
            Fallback identity used when an inbound ``CapabilityRequest``
            does not carry an explicit ``caller_id``.  Useful for
            background / system-initiated invocations.
        """

        if registry is None:
            raise ValueError("NativeToolProvider requires a non-None registry.")
        super().__init__(config)
        self._registry: IToolRegistryReader = registry
        self._default_user_id: str = default_user_id
        self._default_space_id: str = default_space_id

    # ------------------------------------------------------------------ #
    # CapabilityProvider surface
    # ------------------------------------------------------------------ #

    def capabilities(self) -> List[str]:
        """Return capability names this provider currently handles.

        Discovered dynamically from every registered service's
        ``ToolDefinition``.  This is the source of truth used by Fabric
        health/diagnostic surfaces.
        """

        out: list[str] = []
        for adapter_id in self._registry.adapter_ids():
            svc = self._registry.get_service(adapter_id)
            if svc is None:  # pragma: no cover -- transient race
                continue
            definition = svc.DEFINITION
            for action in definition.actions:
                prefix = "tool.read" if action.kind == "read" else "tool.execute"
                out.append(f"{prefix}.{definition.adapter_id}.{action.name}")
        return out

    async def health_check(self) -> ProviderHealth:
        """Native provider is healthy iff at least one service is registered."""

        adapters = self._registry.adapter_ids()
        if not adapters:
            return ProviderHealth(
                provider_id=self.provider_id,
                status=ProviderStatus.DEGRADED.value,
                error="No family-tool services registered.",
            )
        return ProviderHealth(
            provider_id=self.provider_id,
            status=ProviderStatus.HEALTHY.value,
        )

    # ------------------------------------------------------------------ #
    # Dispatch
    # ------------------------------------------------------------------ #

    async def _execute(
        self,
        request: CapabilityRequest,
        context: ExecutionContext,
        trace_id: str,
    ) -> CapabilityResult:
        adapter_id, action_name = _parse_capability_name(request.capability_name)

        service: Optional[IToolService] = self._registry.get_service(adapter_id)
        if service is None:
            return CapabilityResult.failure_result(
                request_id=request.request_id,
                error_code="adapter_not_found",
                error_message=f"No family-tool service registered for adapter {adapter_id!r}",
                retriable=False,
                provider_id=self.provider_id,
                trace_id=trace_id,
            )

        definition = service.DEFINITION
        action = definition.find_action(action_name)
        if action is None:
            return CapabilityResult.failure_result(
                request_id=request.request_id,
                error_code="action_not_found",
                error_message=(f"Adapter {adapter_id!r} does not declare action {action_name!r}"),
                retriable=False,
                provider_id=self.provider_id,
                trace_id=trace_id,
            )

        ctx = self._build_write_context(request, context, trace_id)

        try:
            dispatch_result = service.dispatch(action_name, dict(request.params), ctx)
            if inspect.isawaitable(dispatch_result):
                data = await dispatch_result
            else:
                # Defensive: accept sync services even though the protocol is async.
                data = dispatch_result
        except ProviderExecutionError:
            # Let BaseProvider.execute() translate this to a failure_result.
            raise
        except Exception as exc:
            logger.exception(
                "[%s] family-tool dispatch failed: adapter=%s action=%s",
                self.provider_id,
                adapter_id,
                action_name,
            )
            raise ProviderExecutionError(
                provider_id=self.provider_id,
                message=f"{type(exc).__name__}: {exc}",
                retriable=False,
                error_code="dispatch_failed",
            ) from exc

        if not isinstance(data, dict):
            raise ProviderExecutionError(
                provider_id=self.provider_id,
                message=(
                    f"family-tool dispatch for {adapter_id}.{action_name} returned "
                    f"{type(data).__name__}; expected dict"
                ),
                retriable=False,
                error_code="invalid_result",
            )

        return CapabilityResult.success_result(
            request_id=request.request_id,
            data=data,
            provider_id=self.provider_id,
            trace_id=trace_id,
        )

    # ------------------------------------------------------------------ #
    # WriteContext construction
    # ------------------------------------------------------------------ #

    def _build_write_context(
        self,
        request: CapabilityRequest,
        context: ExecutionContext,
        trace_id: str,
    ) -> WriteContext:
        """Build a ``WriteContext`` from the Fabric request + session frame.

        Resolution order for each field:

        * ``user_id``        -- ``request.caller_id`` > ``request.caller`` > default.
        * ``session_id``     -- ``request.session_id`` (empty -> ``None``).
        * ``trace_id``       -- explicit trace_id arg (Fabric authoritative).
        * ``role``           -- ``session_sections["control"]["role"]`` or "member".
        * ``band``           -- ``request.safety_band`` (already band-string).
        * ``idempotency_key`` -- ``request.params["idempotency_key"]`` if present.
        """

        control: dict[str, Any] = {}
        sections = context.session_sections or {}
        raw_control = sections.get("control")
        if isinstance(raw_control, dict):
            control = raw_control

        role_raw = control.get("role")
        role = (
            role_raw
            if role_raw in ("parent", "child", "guardian", "elder", "system", "guest")
            else "parent"
        )

        band_raw = request.safety_band or control.get("band") or "GREEN"
        band = band_raw if band_raw in ("GREEN", "AMBER", "RED", "CRISIS") else "GREEN"

        user_id = request.caller_id or request.caller or self._default_user_id

        # space_id: caller frame > control section > provider default ("" if unset).
        space_id_raw = control.get("space_id")
        if not isinstance(space_id_raw, str) or not space_id_raw:
            space_id_raw = self._default_space_id

        # face: Fabric requests originate from the LLM/planner pipeline; default "llm"
        # when not provided.  Adapter authors building synthetic requests can override
        # via control["face"].
        face_raw = control.get("face")
        face = face_raw if face_raw in ("llm", "ui", "voice", "scheduler", "system") else "llm"

        idempotency_key: Optional[str] = None
        if isinstance(request.params, dict):
            key = request.params.get("idempotency_key")
            if isinstance(key, str) and key:
                idempotency_key = key

        return WriteContext(
            user_id=user_id,
            space_id=space_id_raw,
            session_id=request.session_id or None,
            trace_id=trace_id,
            role=role,
            face=face,
            band=band,
            idempotency_key=idempotency_key,
        )


# ---------------------------------------------------------------------------
# In-process registry helper
# ---------------------------------------------------------------------------


class InMemoryToolRegistry:
    """Minimal ``IToolRegistryReader`` implementation for boot + tests.

    Production boot (§E15.0.10) uses this as the canonical implementation
    -- every family adapter is constructed at startup, the service is
    registered here, and the registry is passed to ``NativeToolProvider``.
    """

    __slots__ = ("_by_id",)

    def __init__(self) -> None:
        self._by_id: dict[str, IToolService] = {}

    # IToolRegistryReader -------------------------------------------------- #

    def get_service(self, adapter_id: str) -> Optional[IToolService]:
        return self._by_id.get(adapter_id)

    def adapter_ids(self) -> List[str]:
        return sorted(self._by_id.keys())

    # Mutation ------------------------------------------------------------- #

    def register(self, service: IToolService) -> None:
        """Register ``service`` under ``service.DEFINITION.adapter_id``."""

        definition = service.DEFINITION
        adapter_id = definition.adapter_id
        if adapter_id in self._by_id:
            raise ValueError(f"family-tool adapter {adapter_id!r} already registered")
        self._by_id[adapter_id] = service
