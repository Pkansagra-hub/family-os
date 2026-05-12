"""Tests for ``ToolRegistry`` (§E15.0.7)."""

from __future__ import annotations

from pathlib import Path

import pytest

from k1.tools.family.events import EventEmitter
from k1.tools.family.registry import ToolRegistry
from k1.tools.family.storage import K1FamilyStore
from tests.k1.tools.family._stubs import DemoToolService, RecordingSsePublisher


@pytest.fixture()
def registry(tmp_path: Path):
    store = K1FamilyStore(str(tmp_path / "k.db"))
    emitter = EventEmitter(RecordingSsePublisher())
    reg = ToolRegistry(store.conn, emitter, fabric=None)
    try:
        yield reg
    finally:
        store.close()


def test_register_class_returns_instance(registry: ToolRegistry) -> None:
    svc = registry.register_class(DemoToolService)
    assert svc.adapter_id == "demo"
    assert registry.adapter_ids() == ["demo"]


def test_double_register_rejected(registry: ToolRegistry) -> None:
    registry.register_class(DemoToolService)
    with pytest.raises(ValueError):
        registry.register_class(DemoToolService)


def test_get_service_returns_registered(registry: ToolRegistry) -> None:
    registry.register_class(DemoToolService)
    assert registry.get_service("demo") is not None
    assert registry.get_service("none") is None


def test_register_all(registry: ToolRegistry) -> None:
    services = registry.register_all([DemoToolService])
    assert len(services) == 1
    assert services[0].adapter_id == "demo"
