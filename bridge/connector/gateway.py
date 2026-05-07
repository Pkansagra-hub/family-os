"""ConnectorGateway — concrete impl of :class:`IConnectorGatewayPort`.

Wires the three pipeline stages and the adapter registry behind a single
async surface that K1 fabric and bridge clients call into.

Pipeline:
    invoke(...) →
        TokenVerifier.verify(caller, manifest)  # stage 1
        AdapterVerifier.verify(manifest)        # stage 2 (cached)
        RequestRouter.dispatch(...)             # stage 3 → MCP child
"""

from __future__ import annotations

from typing import Any

from bridge.ports.connector_gateway_protocol import (
    AdapterStatus,
)
from bridge.ports.connector_gateway_protocol import ConnectorResult as LegacyConnectorResult

from .adapter_verifier import AdapterVerifier, CABundleAdapterVerifier
from .contracts import (
    AdapterHealth,
    ConnectorCaller,
    ConnectorResult,
    InvalidAdapterSignatureError,
    ToolDescriptor,
    UnknownAdapterError,
)
from .credential_vault import CredentialVault, InMemoryCredentialVault
from .mcp_process_manager import MCPProcessManager, SkeletonMCPProcessManager
from .request_router import DefaultRequestRouter, RequestRouter
from .token_verifier import PermissiveTokenVerifier, TokenVerifier


class ConnectorGateway:
    """Concrete implementation of :class:`IConnectorGatewayPort`.

    Construction is keyword-only; every collaborator can be replaced
    for tests. Sane defaults are provided so production wiring is::

        gateway = ConnectorGateway(
            manifest_registry={...},
            process_manager=process_manager,
            credential_vault=vault,
        )
    """

    def __init__(
        self,
        *,
        manifest_registry: dict[str, dict[str, Any]] | None = None,
        process_manager: MCPProcessManager | None = None,
        credential_vault: CredentialVault | None = None,
        token_verifier: TokenVerifier | None = None,
        adapter_verifier: AdapterVerifier | None = None,
        request_router: RequestRouter | None = None,
    ) -> None:
        self._registry: dict[str, dict[str, Any]] = dict(manifest_registry or {})
        self._process_manager: MCPProcessManager = process_manager or SkeletonMCPProcessManager()
        self._credential_vault: CredentialVault = credential_vault or InMemoryCredentialVault()
        self._token_verifier: TokenVerifier = token_verifier or PermissiveTokenVerifier()
        self._adapter_verifier: AdapterVerifier = adapter_verifier or CABundleAdapterVerifier()
        self._router: RequestRouter = request_router or DefaultRequestRouter(
            process_manager=self._process_manager
        )
        # Cache: adapter_id -> True once stage-2 has approved it. Cleared
        # automatically if `register` is called again for the same id.
        self._verified: set[str] = set()

    # -- Registration ------------------------------------------------------

    def register(self, *, adapter_id: str, manifest: dict[str, Any]) -> None:
        """Register an adapter manifest after Ed25519 verification.

        Raises :class:`InvalidAdapterSignatureError` on failure (caller
        sees this at boot/registration time, never on hot path).
        """
        self._adapter_verifier.verify(manifest)  # raises on failure
        self._registry[adapter_id] = manifest
        self._verified.add(adapter_id)

    def unregister(self, *, adapter_id: str) -> None:
        """Drop a registration. Idempotent."""
        self._registry.pop(adapter_id, None)
        self._verified.discard(adapter_id)

    @property
    def credential_vault(self) -> CredentialVault:
        """Expose the vault for the MCP Process Manager to fetch secrets
        at ``mcp/initialize`` time (D17)."""
        return self._credential_vault

    # -- IConnectorGatewayPort: MS-5 surface -------------------------------

    async def invoke(
        self,
        *,
        adapter_id: str,
        tool: str,
        args: dict[str, Any],
        caller: ConnectorCaller,
    ) -> ConnectorResult:
        manifest = self._registry.get(adapter_id)
        if manifest is None:
            raise UnknownAdapterError(f"adapter not registered: {adapter_id!r}")

        # Stage 1 — token verification.
        await self._token_verifier.verify(caller, manifest)

        # Stage 2 — manifest signature verification (cached after first OK).
        if adapter_id not in self._verified:
            try:
                self._adapter_verifier.verify(manifest)
            except InvalidAdapterSignatureError:
                raise
            self._verified.add(adapter_id)

        # Stage 3 — dispatch to MCP child.
        return await self._router.dispatch(
            adapter_id=adapter_id,
            tool=tool,
            args=args,
            caller=caller,
            manifest=manifest,
        )

    async def list_tools(self, *, adapter_id: str) -> list[ToolDescriptor]:
        if adapter_id not in self._registry:
            raise UnknownAdapterError(f"adapter not registered: {adapter_id!r}")
        return await self._process_manager.list_tools(adapter_id=adapter_id)

    async def health(self, *, adapter_id: str) -> AdapterHealth:
        if adapter_id not in self._registry:
            return AdapterHealth(adapter_id=adapter_id, state="unknown")
        return await self._process_manager.health(adapter_id=adapter_id)

    # -- IConnectorGatewayPort: legacy surface -----------------------------

    async def execute(
        self,
        adapter_id: str,
        action: str,
        params: dict[str, Any],
        *,
        trace_id: str = "",
        timeout_ms: int = 0,
    ) -> LegacyConnectorResult:
        """Legacy alias for :meth:`invoke` — kept for pre-MS-5 callers.

        Translates the result back into the legacy
        :class:`bridge.ports.connector_gateway_protocol.ConnectorResult`.
        """
        del timeout_ms  # honoured by the router/PM in PR#2
        caller = ConnectorCaller(
            session_id="",
            tenant_id="",
            trace_id=trace_id,
        )
        result = await self.invoke(
            adapter_id=adapter_id,
            tool=action,
            args=params,
            caller=caller,
        )
        return LegacyConnectorResult(
            success=result.success,
            data=result.data,
            error_code=result.error_code,
            error_message=result.error_message,
            adapter_id=result.adapter_id,
            latency_ms=result.latency_ms,
        )

    async def list_adapters(self) -> list[AdapterStatus]:
        """Legacy adapter listing — derives from registry + per-adapter health."""
        out: list[AdapterStatus] = []
        for adapter_id, manifest in self._registry.items():
            h = await self.health(adapter_id=adapter_id)
            out.append(
                AdapterStatus(
                    adapter_id=adapter_id,
                    category=str(manifest.get("category", "")),
                    connected=h.state in {"ready", "starting"},
                    healthy=h.state == "ready",
                    last_heartbeat_ms=h.last_ping_ms,
                    capabilities=list(manifest.get("capabilities", [])),
                )
            )
        return out


__all__ = ["ConnectorGateway"]
