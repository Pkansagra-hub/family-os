"""HTTP helpers for K0 query/observe routes.

Thin wrappers over ``/k0/query.recall`` and ``/k0/obs.emit`` for the
journey tests in :mod:`tests.integration.journeys`. Sends a guest role
in ``policy.abac.roles`` because the running K0 dev manifest only
exposes the ``admin``/``device``/``guest`` roles (with ``allow_topics: ["*"]``
on guest), not the production ``coordinator``/``security`` roles.
"""

from __future__ import annotations

from typing import Any

import httpx


async def query_recall(
    *,
    k0_base_url: str,
    tenant_id: str,
    space_id: str,
    selectors: list[dict[str, Any]] | None = None,
    roles: list[str] | None = None,
    max_latency_ms: int = 200,
    fail_fast: bool = False,
) -> dict[str, Any]:
    """POST ``/k0/query.recall`` and return ``{"http_status", "body"}``.

    ``selectors`` defaults to a single semantic selector with no ``query``
    string — that selector is admitted but returns ``status=no_query``
    items, which is the safe "round-trip proven" mode in the dev container.
    """
    body = {
        "selectors": selectors or [{"type": "semantic", "topic": "integration", "limit": 5}],
        "space_id": space_id,
        "tenant_id": tenant_id,
        "policy": {"abac": {"roles": roles or ["guest"]}},
        "max_latency_ms": max_latency_ms,
        "fail_fast": fail_fast,
    }
    url = f"{k0_base_url.rstrip('/')}/k0/query.recall"
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(url, json=body)
    try:
        data = response.json()
    except Exception:  # noqa: BLE001
        data = {"raw_text": response.text}
    return {"http_status": response.status_code, "body": data}


async def obs_emit_metrics(
    *,
    k0_base_url: str,
    snapshot: str,
    source: str = "harness",
) -> dict[str, Any]:
    """POST ``/k0/obs.emit`` (kind=metrics) and return ``{"http_status", "body"}``.

    A 204 No Content is the success contract — body is then ``{}``.
    """
    payload = {
        "kind": "metrics",
        "body": {"snapshot": snapshot, "source": source},
    }
    url = f"{k0_base_url.rstrip('/')}/k0/obs.emit"
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(url, json=payload)
    if response.status_code == 204 or not response.content:
        data: dict[str, Any] = {}
    else:
        try:
            data = response.json()
        except Exception:  # noqa: BLE001
            data = {"raw_text": response.text}
    return {"http_status": response.status_code, "body": data}
