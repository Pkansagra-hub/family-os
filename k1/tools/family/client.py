"""
k1.tools.family.client -- Thin async HTTP client for the family-tool REST layer.

Each adapter exposes three JSON endpoints (served by
:func:`k1.tools.family.routes.build_router`):

* ``GET /manifest?role=<role>``  -> UI manifest dict.
* ``GET /llm_specs``             -> OpenAI-compatible tools array.
* ``POST /<action_name>``        -> dispatch an action.

:class:`FamilyToolClient` wraps these with:

* **Manifest caching** -- per ``(base_url, role)`` with a configurable TTL
  (default 300 s).  LLM orchestration paths call ``get_manifest`` many times
  per request; the cache keeps latency flat after the first hit.

* **Dispatch helper** -- ``call(action, params, ctx)`` POST to
  ``/<action>`` and return the response dict unchanged.  No
  serialisation beyond JSON; the caller owns the context dict shape.

* **Header injection** -- every request carries an ``X-Idem-Key`` header
  built from the supplied idempotency key (write actions) so the adapter's
  ``IdemService`` deduplicates retries.

Plan reference: ``docs/plans/KERNEL_BOOTUP_PLAN.md`` §E15.7.
"""

from __future__ import annotations

import time
from typing import Any, Optional

import httpx

# ---------------------------------------------------------------------------
# Manifest TTL cache
# ---------------------------------------------------------------------------

# Cache entry: (manifest_dict, expires_at_monotonic)
_CacheEntry = tuple[Any, float]
_ManifestCache = dict[tuple[str, Optional[str]], _CacheEntry]

DEFAULT_MANIFEST_TTL: int = 300  # seconds


class FamilyToolClient:
    """Async HTTP client for a single family-tool adapter endpoint.

    Parameters
    ----------
    base_url:
        Root URL of the adapter, e.g. ``http://localhost:8000/family/calendar``.
        Must NOT have a trailing slash.
    manifest_ttl:
        Cache lifetime for manifests in seconds (default 300 s).
    http_client:
        Optional pre-configured :class:`httpx.AsyncClient`.  When omitted a
        new default client is created.  Providing one allows the caller to
        set custom timeouts, cert verification, or a mock transport.
    """

    __slots__ = ("_base_url", "_manifest_ttl", "_http", "_cache")

    def __init__(
        self,
        base_url: str,
        *,
        manifest_ttl: int = DEFAULT_MANIFEST_TTL,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._manifest_ttl = manifest_ttl
        self._http: httpx.AsyncClient = http_client or httpx.AsyncClient()
        self._cache: _ManifestCache = {}

    # ------------------------------------------------------------------
    # Manifest (cached)
    # ------------------------------------------------------------------

    async def get_manifest(self, role: Optional[str] = None) -> dict[str, Any]:
        """Return the UI manifest for this adapter, filtered by ``role``.

        Results are cached per ``(base_url, role)`` for up to
        :attr:`manifest_ttl` seconds.  Pass ``role=None`` to get the
        full unfiltered manifest.
        """
        cache_key = (self._base_url, role)
        entry = self._cache.get(cache_key)
        now = time.monotonic()

        if entry is not None:
            manifest, expires = entry
            if now < expires:
                return manifest

        params: dict[str, str] = {}
        if role is not None:
            params["role"] = role

        response = await self._http.get(
            f"{self._base_url}/manifest",
            params=params,
        )
        response.raise_for_status()
        manifest = response.json()

        self._cache[cache_key] = (manifest, now + self._manifest_ttl)
        return manifest

    def invalidate_manifest_cache(self, role: Optional[str] = None) -> None:
        """Evict the cached manifest for the given role (or all if ``role`` is None)."""
        if role is None:
            self._cache.clear()
        else:
            self._cache.pop((self._base_url, role), None)

    # ------------------------------------------------------------------
    # LLM specs (not cached -- caller can cache if desired)
    # ------------------------------------------------------------------

    async def get_llm_specs(self) -> list[dict[str, Any]]:
        """Return the OpenAI-compatible tools array for this adapter."""
        response = await self._http.get(f"{self._base_url}/llm_specs")
        response.raise_for_status()
        return response.json()

    # ------------------------------------------------------------------
    # Action dispatch
    # ------------------------------------------------------------------

    async def call(
        self,
        action: str,
        params: dict[str, Any],
        *,
        idem_key: Optional[str] = None,
    ) -> dict[str, Any]:
        """POST ``params`` to ``/<action>`` and return the response dict.

        Parameters
        ----------
        action:
            Action name as declared in the ``ToolDefinition``, e.g.
            ``"create_event"``.
        params:
            Payload forwarded as JSON body.  Typically includes
            ``user_id``, ``space_id``, ``trace_id``, and action fields.
        idem_key:
            When provided, injected as ``X-Idem-Key`` header so the
            adapter's :class:`IdemService` can deduplicate retries.
        """
        headers: dict[str, str] = {}
        if idem_key is not None:
            headers["X-Idem-Key"] = idem_key

        response = await self._http.post(
            f"{self._base_url}/{action}",
            json=params,
            headers=headers,
        )
        response.raise_for_status()
        return response.json()

    # ------------------------------------------------------------------
    # Context manager support
    # ------------------------------------------------------------------

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        await self._http.aclose()

    async def __aenter__(self) -> "FamilyToolClient":
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.aclose()
