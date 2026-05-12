"""Tests for ``IdempotencyStore`` and ``K1FamilyStore``."""

from __future__ import annotations

import time
from pathlib import Path

from k1.tools.family.idem import IdempotencyStore
from k1.tools.family.storage import K1FamilyStore


def test_store_opens_and_creates_db(tmp_path: Path) -> None:
    db_path = tmp_path / "k1f.db"
    store = K1FamilyStore(str(db_path))
    try:
        assert db_path.exists()
        # WAL pragma takes effect: confirm we can run a write+read.
        store.conn.execute("CREATE TABLE t (x INT)")
        store.conn.execute("INSERT INTO t VALUES (1)")
        row = store.conn.execute("SELECT x FROM t").fetchone()
        assert row["x"] == 1
    finally:
        store.close()


def test_store_close_is_idempotent(tmp_path: Path) -> None:
    store = K1FamilyStore(str(tmp_path / "k.db"))
    store.close()
    store.close()  # must not raise


def test_idempotency_lookup_record_roundtrip(tmp_path: Path) -> None:
    store = K1FamilyStore(str(tmp_path / "k.db"))
    try:
        idem = IdempotencyStore(store.conn)
        assert idem.lookup("calendar", "create_event", "k1", "h1") is None
        idem.record("calendar", "create_event", "k1", "h1", "ok", {"id": "e1", "success": True})
        cached = idem.lookup("calendar", "create_event", "k1", "h1")
        assert cached is not None
        assert cached["status"] == "ok"
        assert cached["result"] == {"id": "e1", "success": True}
    finally:
        store.close()


def test_idempotency_keyed_by_space(tmp_path: Path) -> None:
    store = K1FamilyStore(str(tmp_path / "k.db"))
    try:
        idem = IdempotencyStore(store.conn)
        idem.record("calendar", "create_event", "k1", "hA", "ok", {"r": "A"})
        idem.record("calendar", "create_event", "k1", "hB", "ok", {"r": "B"})
        assert idem.lookup("calendar", "create_event", "k1", "hA")["result"] == {"r": "A"}
        assert idem.lookup("calendar", "create_event", "k1", "hB")["result"] == {"r": "B"}
    finally:
        store.close()


def test_idempotency_overwrite_after_ttl(tmp_path: Path, monkeypatch) -> None:
    store = K1FamilyStore(str(tmp_path / "k.db"))
    try:
        import k1.tools.family.idem as idem_module

        monkeypatch.setattr(idem_module, "_TTL_S", 0)  # immediately stale
        idem = IdempotencyStore(store.conn)
        idem.record("calendar", "create_event", "k1", "h1", "ok", {"r": 1})
        time.sleep(0.01)
        # Past TTL: lookup returns None even though row still exists.
        assert idem.lookup("calendar", "create_event", "k1", "h1") is None
        # Re-record overwrites the stale row.
        idem.record("calendar", "create_event", "k1", "h1", "ok", {"r": 2})
        # With TTL=0 lookup remains None; that's expected with the monkeypatched TTL.
        # Restore TTL to verify the new row replaces the old.
        monkeypatch.setattr(idem_module, "_TTL_S", 24 * 3600)
        cached = idem.lookup("calendar", "create_event", "k1", "h1")
        assert cached is not None
        assert cached["result"] == {"r": 2}
    finally:
        store.close()
