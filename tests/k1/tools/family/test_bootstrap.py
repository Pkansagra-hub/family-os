"""Tests for ``bootstrap_family_tools`` (§E15.0.10)."""

from __future__ import annotations

from pathlib import Path

from k1.fabric.core.registry import CapabilityRegistry
from k1.tools.family.bootstrap import bootstrap_family_tools
from tests.k1.tools.family._stubs import DemoToolService


class _FakeFabric:
    """Minimal duck-typed stand-in for the Fabric used in bootstrap()."""

    def __init__(self) -> None:
        self.capability_registry = CapabilityRegistry()


def test_bootstrap_without_fabric(tmp_path: Path) -> None:
    bundle = bootstrap_family_tools(
        fabric=None,
        db_path=str(tmp_path / "k.db"),
        service_classes=[DemoToolService],
    )
    try:
        assert bundle.tool_registry.adapter_ids() == ["demo"]
        # NativeToolProvider enumerates capabilities from the registry.
        caps = bundle.native_provider.capabilities()
        assert "tool.execute.demo.echo" in caps
        assert "tool.read.demo.adults_only" in caps
        assert "tool.execute.demo.record_write" in caps
    finally:
        bundle.close()


def test_bootstrap_registers_with_fabric_capability_registry(tmp_path: Path) -> None:
    fab = _FakeFabric()
    bundle = bootstrap_family_tools(
        fabric=fab,
        db_path=str(tmp_path / "k.db"),
        service_classes=[DemoToolService],
    )
    try:
        names = [c.name for c in fab.capability_registry.list_all()]
        assert "tool.execute.demo.echo" in names
        assert "tool.read.demo.adults_only" in names
    finally:
        bundle.close()
