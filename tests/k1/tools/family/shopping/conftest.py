"""Shared fixtures for the Shopping adapter tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from k1.tools.family.base import WriteContext
from k1.tools.family.events import EventEmitter
from k1.tools.family.idem import IdempotencyStore
from k1.tools.family.policy import default_policy
from k1.tools.family.shopping.service import ShoppingToolService
from k1.tools.family.storage import K1FamilyStore
from tests.k1.tools.family._stubs import RecordingSsePublisher


@pytest.fixture()
def svc(tmp_path: Path):
    store = K1FamilyStore(str(tmp_path / "shopping.db"))
    pub = RecordingSsePublisher()
    emitter = EventEmitter(pub)
    idem = IdempotencyStore(store.conn)
    service = ShoppingToolService(store.conn, emitter, default_policy(), idem)
    try:
        yield service, pub, store
    finally:
        store.close()


def make_ctx(
    *,
    user_id: str = "parent1",
    space_id: str = "h1",
    role: str = "parent",
    band: str = "GREEN",
    idem_key: str | None = None,
) -> WriteContext:
    return WriteContext(
        user_id=user_id,
        space_id=space_id,
        trace_id=f"trace-{user_id}",
        role=role,  # type: ignore[arg-type]
        band=band,  # type: ignore[arg-type]
        idempotency_key=idem_key,
    )
