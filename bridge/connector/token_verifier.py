"""Stage 1 of the IFL gateway pipeline: TokenVerifier.

The verifier inspects ``ConnectorCaller.capability_token`` and the
manifest's ``signing.ca_id`` to decide whether the call is authorised.

For MS-5 PR#1 the verifier is intentionally permissive: it accepts any
non-empty token unless the manifest declares ``capability_required``.
Real capability-token issuance + scope enforcement is a v1.x concern
that lands once K1 fabric ships its capability-token issuer (out of
scope for MS-5).
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from .contracts import ConnectorCaller, TokenDeniedError


@runtime_checkable
class TokenVerifier(Protocol):
    """Protocol for the gateway's first stage."""

    async def verify(self, caller: ConnectorCaller, manifest: dict[str, Any]) -> None:
        """Raise :class:`TokenDeniedError` if the caller is not authorised."""
        ...  # pragma: no cover


class PermissiveTokenVerifier:
    """Default MS-5 verifier.

    Accepts any caller whose ``capability_token`` is non-empty when the
    manifest declares ``capability_required`` truthy. Otherwise accepts
    every caller.

    Replace with a real verifier (signed JWT, SPIFFE, etc.) in v1.x.
    """

    async def verify(self, caller: ConnectorCaller, manifest: dict[str, Any]) -> None:
        cap_required = bool(manifest.get("capability_required"))
        if cap_required and not caller.capability_token:
            raise TokenDeniedError(
                "manifest requires capability_token but caller did not supply one"
            )


__all__ = ["PermissiveTokenVerifier", "TokenVerifier"]
