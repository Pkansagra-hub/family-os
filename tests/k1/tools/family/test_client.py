"""Tests for FamilyToolClient (§E15.7)."""

from __future__ import annotations

import time
from typing import Any

import httpx
import pytest

from k1.tools.family.client import DEFAULT_MANIFEST_TTL, FamilyToolClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MANIFEST = {
    "adapter_id": "calendar",
    "version": "1.0.0",
    "actions": [{"name": "create_event", "kind": "write"}],
}

_LLM_SPECS = [
    {
        "name": "calendar.create_event",
        "capability_name": "tool.execute.calendar.create_event",
        "kind": "write",
        "description": "Create an event.",
        "parameters": {
            "type": "object",
            "properties": {"title": {"type": "string"}},
            "required": ["title"],
        },
        "output_schema": {},
        "examples": [],
    }
]


def _make_transport(*responses: tuple[int, Any]) -> httpx.MockTransport:
    """Build a mock transport that returns ``responses`` in order."""
    queue = list(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        status, body = queue.pop(0)
        return httpx.Response(status, json=body)

    return httpx.MockTransport(handler)


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestFamilyToolClientConstruction:
    def test_default_ttl(self) -> None:
        client = FamilyToolClient("http://localhost:8000/family/calendar")
        assert client._manifest_ttl == DEFAULT_MANIFEST_TTL

    def test_custom_ttl(self) -> None:
        client = FamilyToolClient("http://localhost:8000", manifest_ttl=60)
        assert client._manifest_ttl == 60

    def test_trailing_slash_stripped(self) -> None:
        client = FamilyToolClient("http://localhost:8000/")
        assert client._base_url == "http://localhost:8000"


# ---------------------------------------------------------------------------
# get_manifest (caching)
# ---------------------------------------------------------------------------


class TestGetManifest:
    async def test_returns_manifest(self) -> None:
        transport = _make_transport((200, _MANIFEST))
        http = httpx.AsyncClient(transport=transport, base_url="http://test")
        client = FamilyToolClient("http://test/family/calendar", http_client=http)
        manifest = await client.get_manifest(role="parent")
        assert manifest["adapter_id"] == "calendar"

    async def test_cache_hit_no_second_request(self) -> None:
        """Second call with same role must not issue a new HTTP request."""
        calls: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(str(request.url))
            return httpx.Response(200, json=_MANIFEST)

        transport = httpx.MockTransport(handler)
        http = httpx.AsyncClient(transport=transport)
        client = FamilyToolClient("http://test/family/calendar", http_client=http)

        await client.get_manifest(role="parent")
        await client.get_manifest(role="parent")

        assert len(calls) == 1

    async def test_different_roles_are_separate_cache_keys(self) -> None:
        calls: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(str(request.url))
            return httpx.Response(200, json=_MANIFEST)

        transport = httpx.MockTransport(handler)
        http = httpx.AsyncClient(transport=transport)
        client = FamilyToolClient("http://test/family/calendar", http_client=http)

        await client.get_manifest(role="parent")
        await client.get_manifest(role="child")

        assert len(calls) == 2

    async def test_cache_miss_after_invalidation(self) -> None:
        calls: list[int] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(1)
            return httpx.Response(200, json=_MANIFEST)

        transport = httpx.MockTransport(handler)
        http = httpx.AsyncClient(transport=transport)
        client = FamilyToolClient("http://test/family/calendar", http_client=http)

        await client.get_manifest(role="parent")
        client.invalidate_manifest_cache(role="parent")
        await client.get_manifest(role="parent")

        assert len(calls) == 2

    async def test_invalidate_all_clears_all_roles(self) -> None:
        calls: list[int] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(1)
            return httpx.Response(200, json=_MANIFEST)

        transport = httpx.MockTransport(handler)
        http = httpx.AsyncClient(transport=transport)
        client = FamilyToolClient("http://test/family/calendar", http_client=http)

        await client.get_manifest(role="parent")
        await client.get_manifest(role="child")
        client.invalidate_manifest_cache()  # no role = clear all
        await client.get_manifest(role="parent")
        await client.get_manifest(role="child")

        assert len(calls) == 4

    async def test_expired_entry_refetched(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[int] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(1)
            return httpx.Response(200, json=_MANIFEST)

        transport = httpx.MockTransport(handler)
        http = httpx.AsyncClient(transport=transport)
        client = FamilyToolClient("http://test/family/calendar", manifest_ttl=1, http_client=http)

        await client.get_manifest(role="parent")

        # Fast-forward monotonic clock past TTL.
        original = time.monotonic
        monkeypatch.setattr(time, "monotonic", lambda: original() + 2)

        await client.get_manifest(role="parent")

        assert len(calls) == 2


# ---------------------------------------------------------------------------
# get_llm_specs
# ---------------------------------------------------------------------------


class TestGetLlmSpecs:
    async def test_returns_list(self) -> None:
        transport = _make_transport((200, _LLM_SPECS))
        http = httpx.AsyncClient(transport=transport)
        client = FamilyToolClient("http://test/family/calendar", http_client=http)
        specs = await client.get_llm_specs()
        assert isinstance(specs, list)
        assert specs[0]["name"] == "calendar.create_event"


# ---------------------------------------------------------------------------
# call (dispatch)
# ---------------------------------------------------------------------------


class TestCall:
    async def test_posts_to_correct_path(self) -> None:
        paths: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            paths.append(request.url.path)
            return httpx.Response(200, json={"success": True})

        transport = httpx.MockTransport(handler)
        http = httpx.AsyncClient(transport=transport)
        client = FamilyToolClient("http://test/family/calendar", http_client=http)
        result = await client.call("create_event", {"title": "Dentist"})

        assert paths == ["/family/calendar/create_event"]
        assert result["success"] is True

    async def test_idem_key_header_injected(self) -> None:
        headers_seen: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            headers_seen.update(dict(request.headers))
            return httpx.Response(200, json={"success": True})

        transport = httpx.MockTransport(handler)
        http = httpx.AsyncClient(transport=transport)
        client = FamilyToolClient("http://test/family/calendar", http_client=http)
        await client.call("create_event", {}, idem_key="abc-123")

        assert headers_seen.get("x-idem-key") == "abc-123"

    async def test_no_idem_key_header_when_omitted(self) -> None:
        headers_seen: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            headers_seen.update(dict(request.headers))
            return httpx.Response(200, json={"ok": True})

        transport = httpx.MockTransport(handler)
        http = httpx.AsyncClient(transport=transport)
        client = FamilyToolClient("http://test/family/calendar", http_client=http)
        await client.call("list_events", {})

        assert "x-idem-key" not in headers_seen


# ---------------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------------


class TestContextManager:
    async def test_async_context_manager(self) -> None:
        transport = _make_transport((200, _MANIFEST))
        http = httpx.AsyncClient(transport=transport)
        async with FamilyToolClient("http://test/family/calendar", http_client=http) as client:
            manifest = await client.get_manifest()
        assert manifest["adapter_id"] == "calendar"
