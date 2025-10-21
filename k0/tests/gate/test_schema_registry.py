from __future__ import annotations

from typing import Any

from ward import test  # type: ignore[attr-defined]

from k0.gate.schema_registry import SchemaRecord, SchemaRegistry
from k0.uow.connection_pool import shutdown_pool
from tests.storage.fixtures import sqlite_runtime  # type: ignore[misc]


@test("schema registry lifecycle enforces N/N+1 policy and caches results")
def _(sqlite_runtime: Any = sqlite_runtime) -> None:
    registry = SchemaRegistry()

    uri = "schema://memory/topic"
    v1 = SchemaRecord(uri=uri, version="1.0.0", sha256="a" * 64, status="REGISTERED")
    v2 = SchemaRecord(uri=uri, version="2.0.0", sha256="b" * 64, status="REGISTERED")
    v3 = SchemaRecord(uri=uri, version="3.0.0", sha256="c" * 64, status="REGISTERED")

    registry.register(v1)
    registry.promote(uri, v1.version)
    assert registry.get(uri, v1.version).status == "ACTIVE"

    registry.register(v2)
    registry.promote(uri, v2.version)
    assert registry.get(uri, v2.version).status == "ACTIVE"
    assert registry.get(uri, v1.version).status == "DEPRECATED"

    registry.register(v3)
    registry.promote(uri, v3.version)
    assert registry.get(uri, v3.version).status == "ACTIVE"
    assert registry.get(uri, v2.version).status == "DEPRECATED"
    assert registry.get(uri, v1.version).status == "BLOCKED"

    registry.block(
        uri, v2.version, operator_id="test_operator", reason="test block operation"
    )
    assert registry.get(uri, v2.version).status == "BLOCKED"

    registry.load()
    shutdown_pool()

    cached = registry.get(uri, v3.version)
    assert cached.status == "ACTIVE"

    records = registry.records_for_uri(uri)
    statuses = {record.version: record.status for record in records}
    assert statuses == {
        v1.version: "BLOCKED",
        v2.version: "BLOCKED",
        v3.version: "ACTIVE",
    }
