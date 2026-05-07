"""bridge/connector — IFL Connector Gateway tier (MS-5).

The connector tier owns:
    * :class:`ConnectorGateway` — the concrete impl of
      :class:`bridge.ports.IConnectorGatewayPort`.
    * Three-stage security pipeline: ``TokenVerifier`` →
      ``AdapterVerifier`` → ``RequestRouter``.
    * MCP child-process supervision (``MCPProcessManager``).
    * Per-adapter credential storage (``CredentialVault``).
    * Typed boundary objects (:mod:`bridge.connector.contracts`).

Layering: this tier sits *below* ``bridge/ifl/`` (the runtime that hosts
adapter manifests + per-adapter MCP servers) and *above*
``bridge/ports/`` (Protocols only). The ``bridge_not_imported_from_kernels``
CI gate forbids K0/K1 from importing anything in this package directly;
they must go through the port.
"""

from __future__ import annotations

from .adapter_verifier import AdapterVerifier, CABundleAdapterVerifier
from .contracts import (
    AdapterHealth,
    AdapterQuarantinedError,
    ConnectorCaller,
    ConnectorGatewayError,
    ConnectorResult,
    InvalidAdapterSignatureError,
    OfflineAdapterError,
    TokenDeniedError,
    ToolDescriptor,
    UnknownAdapterError,
)
from .credential_vault import (
    CredentialNotFoundError,
    CredentialVault,
    InMemoryCredentialVault,
    VaultHealth,
    VaultRecord,
)
from .gateway import ConnectorGateway
from .mcp_child import MCPChild
from .mcp_process_manager import MCPProcessManager, SkeletonMCPProcessManager
from .real_mcp_process_manager import RealMCPProcessManager
from .request_router import DefaultRequestRouter, RequestRouter
from .token_verifier import PermissiveTokenVerifier, TokenVerifier

__all__ = [
    "AdapterHealth",
    "AdapterQuarantinedError",
    "AdapterVerifier",
    "CABundleAdapterVerifier",
    "ConnectorCaller",
    "ConnectorGateway",
    "ConnectorGatewayError",
    "ConnectorResult",
    "CredentialNotFoundError",
    "CredentialVault",
    "DefaultRequestRouter",
    "InMemoryCredentialVault",
    "InvalidAdapterSignatureError",
    "MCPChild",
    "MCPProcessManager",
    "OfflineAdapterError",
    "PermissiveTokenVerifier",
    "RealMCPProcessManager",
    "RequestRouter",
    "SkeletonMCPProcessManager",
    "TokenDeniedError",
    "TokenVerifier",
    "ToolDescriptor",
    "UnknownAdapterError",
    "VaultHealth",
    "VaultRecord",
]
