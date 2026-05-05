"""Unit tests for ``sqlite_migrations`` (M3.E4.I2)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from k1.selfmodel.adapters.sqlite_migrations import (
    Migration,
    apply_migrations,
    current_user_version,
    discover_migrations,
)


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(":memory:", isolation_level=None)
    return c


# ---------------------------------------------------------------------
# discover_migrations
# ---------------------------------------------------------------------
def test_discover_migrations_from_package() -> None:
    found = discover_migrations()
    assert len(found) >= 1
    assert found[0].name == "0001_initial.sql"
    assert found[0].target_version == 1


def test_discover_migrations_from_directory(tmp_path: Path) -> None:
    (tmp_path / "0001_a.sql").write_text("CREATE TABLE t1 (x INT);")
    (tmp_path / "0002_b.sql").write_text("CREATE TABLE t2 (y INT);")
    (tmp_path / "README.md").write_text("ignored")
    found = discover_migrations(tmp_path)
    assert tuple(m.target_version for m in found) == (1, 2)


def test_discover_migrations_rejects_gap(tmp_path: Path) -> None:
    (tmp_path / "0001_a.sql").write_text("CREATE TABLE t1 (x INT);")
    (tmp_path / "0003_c.sql").write_text("CREATE TABLE t3 (z INT);")
    with pytest.raises(RuntimeError):
        discover_migrations(tmp_path)


def test_discover_migrations_rejects_zero_start(tmp_path: Path) -> None:
    (tmp_path / "0000_zero.sql").write_text("CREATE TABLE z (x INT);")
    with pytest.raises(RuntimeError):
        discover_migrations(tmp_path)


# ---------------------------------------------------------------------
# apply_migrations
# ---------------------------------------------------------------------
def test_apply_migrations_lifts_user_version() -> None:
    c = _conn()
    apply_migrations(c)
    assert current_user_version(c) >= 1


def test_apply_migrations_idempotent() -> None:
    c = _conn()
    apply_migrations(c)
    v1 = current_user_version(c)
    apply_migrations(c)  # second call: no-op
    assert current_user_version(c) == v1


def test_apply_migrations_skips_already_applied() -> None:
    c = _conn()
    migs = (
        Migration(target_version=1, name="0001_a.sql", sql="CREATE TABLE t1 (x INT);"),
        Migration(target_version=2, name="0002_b.sql", sql="CREATE TABLE t2 (y INT);"),
    )
    apply_migrations(c, migrations=migs[:1])
    assert current_user_version(c) == 1
    apply_migrations(c, migrations=migs)
    assert current_user_version(c) == 2
    rows = c.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('t1','t2')"
    ).fetchall()
    assert {r[0] for r in rows} == {"t1", "t2"}


def test_apply_migrations_rolls_back_on_error() -> None:
    c = _conn()
    bad = (
        Migration(
            target_version=1,
            name="0001_bad.sql",
            sql="CREATE TABLE t1 (x INT); CREATE TABLE t1 (x INT);",
        ),
    )
    with pytest.raises(sqlite3.Error):
        apply_migrations(c, migrations=bad)
    assert current_user_version(c) == 0


def test_apply_migrations_rejects_gap_at_runtime() -> None:
    c = _conn()
    migs = (Migration(target_version=2, name="0002_skip.sql", sql="CREATE TABLE t2 (y INT);"),)
    with pytest.raises(RuntimeError):
        apply_migrations(c, migrations=migs)


def test_apply_migrations_returns_current_version_when_no_migrations() -> None:
    c = _conn()
    assert apply_migrations(c, migrations=()) == 0
