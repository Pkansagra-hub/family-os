"""OAuth helper for the Google Calendar IFL adapter (MS-5 PR#4).

A *minimal* RFC 6749 §6 refresh-token flow against
``https://oauth2.googleapis.com/token``. Production code paths run
this exactly once per adapter start to bootstrap an access token
which is then carried in subsequent Google Calendar API calls.

This module is deliberately stateless and dependency-light: it only
imports ``httpx`` (already a transitive dep through fastmcp). No
caching, no retry, no token-refresh coordination — those concerns
live in the credential vault layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"


@dataclass(frozen=True, slots=True)
class AccessToken:
    """Short-lived bearer token returned by Google's token endpoint."""

    access_token: str
    expires_in: int
    token_type: str = "Bearer"
    scope: str | None = None


class OAuthError(RuntimeError):
    """Raised when the token endpoint returns a non-2xx response.

    The error message intentionally does **not** include the
    request body or the refresh token — those values are secrets.
    """


def exchange_refresh_token(
    *,
    refresh_token: str,
    client_id: str,
    client_secret: str,
    http_post: Any | None = None,
    token_url: str = GOOGLE_TOKEN_URL,
) -> AccessToken:
    """Exchange a refresh token for an access token.

    The actual HTTP POST is delegated to ``http_post`` (signature:
    ``(url: str, data: Mapping[str, str]) -> Mapping[str, Any]``) so
    tests can inject a deterministic fake without spinning up an
    HTTP server. When ``http_post`` is ``None`` the function lazily
    imports :mod:`httpx`.
    """
    if not refresh_token:
        raise ValueError("refresh_token must not be empty")
    if not client_id or not client_secret:
        raise ValueError("client_id and client_secret must be non-empty")
    payload = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
        "client_secret": client_secret,
    }
    if http_post is None:
        import httpx  # local import — keeps cold-start cheap

        def _real_post(url: str, data: dict[str, str]) -> dict[str, Any]:
            response = httpx.post(url, data=data, timeout=10.0)
            if response.status_code >= 400:
                raise OAuthError(f"token endpoint returned HTTP {response.status_code}")
            return response.json()

        http_post = _real_post
    body = http_post(token_url, payload)
    if not isinstance(body, dict) or "access_token" not in body:
        raise OAuthError("token endpoint returned malformed response")
    return AccessToken(
        access_token=str(body["access_token"]),
        expires_in=int(body.get("expires_in", 3600)),
        token_type=str(body.get("token_type", "Bearer")),
        scope=body.get("scope"),
    )
