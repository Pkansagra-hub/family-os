"""Tests for scripts.pseudo_k0.connector_host."""

from __future__ import annotations

from typing import Any, Dict

import pytest

from scripts.pseudo_k0.connector_host import (
    ConnectorHost,
    ConnectorNotFound,
    DuplicateHandler,
    IMCPHandler,
)


class _EchoHandler:
    adapter_id = "echo"
    action = "ping"

    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"echoed": params}


class TestRegister:
    def test_register_handler_instance(self) -> None:
        host = ConnectorHost()
        host.register(_EchoHandler())
        assert host.has("echo", "ping")
        assert host.list_handlers() == [("echo", "ping")]

    def test_register_fn(self) -> None:
        host = ConnectorHost()

        async def fn(params: Dict[str, Any]) -> Dict[str, Any]:
            return {"ok": True}

        host.register_fn("a", "b", fn)
        assert host.has("a", "b")

    def test_register_duplicate_raises(self) -> None:
        host = ConnectorHost()
        host.register(_EchoHandler())
        with pytest.raises(DuplicateHandler):
            host.register(_EchoHandler())

    def test_register_fn_duplicate_raises(self) -> None:
        host = ConnectorHost()

        async def fn(params: Dict[str, Any]) -> Dict[str, Any]:
            return {}

        host.register_fn("x", "y", fn)
        with pytest.raises(DuplicateHandler):
            host.register_fn("x", "y", fn)

    def test_handler_satisfies_protocol(self) -> None:
        assert isinstance(_EchoHandler(), IMCPHandler)


class TestUnregister:
    def test_unregister_present(self) -> None:
        host = ConnectorHost()
        host.register(_EchoHandler())
        assert host.unregister("echo", "ping") is True
        assert not host.has("echo", "ping")

    def test_unregister_absent(self) -> None:
        host = ConnectorHost()
        assert host.unregister("missing", "noop") is False


class TestDispatch:
    @pytest.mark.asyncio
    async def test_dispatch_invokes_handler(self) -> None:
        host = ConnectorHost()
        host.register(_EchoHandler())
        out = await host.dispatch("echo", "ping", {"x": 1})
        assert out == {"echoed": {"x": 1}}

    @pytest.mark.asyncio
    async def test_dispatch_unknown_raises(self) -> None:
        host = ConnectorHost()
        with pytest.raises(ConnectorNotFound):
            await host.dispatch("nope", "noop", {})

    @pytest.mark.asyncio
    async def test_dispatch_non_dict_result_raises(self) -> None:
        host = ConnectorHost()

        async def bad(params: Dict[str, Any]) -> Any:
            return "not a dict"

        host.register_fn("bad", "act", bad)
        with pytest.raises(TypeError):
            await host.dispatch("bad", "act", {})
