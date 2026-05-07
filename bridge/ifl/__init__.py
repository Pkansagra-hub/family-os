"""bridge/ifl — Inter-Family Link runtime tier (MS-5 placeholder).

The IFL tier hosts per-adapter MCP servers (one child process per
registered adapter) plus the IFL adapter registry. This package is
intentionally a placeholder in MS-5 PR#1: the gateway, MCP process
manager, and credential vault all live in :mod:`bridge.connector`,
because they are reused by every IFL adapter.

PR#2+ of MS-5 lands the first concrete adapter (Google Calendar,
read-only) and the adapter registry persistence in this package.

Layering rule (CI-enforced via ``bridge_not_imported_from_kernels``):
    K0 / K1 must NOT import this package directly. They reach IFL only
    via :class:`bridge.ports.IConnectorGatewayPort`.
"""
