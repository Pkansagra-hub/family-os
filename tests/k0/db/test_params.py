"""Unit tests for k0.db.params module."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from k0.db.params import (
    bind_params,
    bulk_params,
    dict_to_positional,
    named_to_positional,
)


class TestBindParams:
    """Tests for bind_params type conversion."""

    def test_none(self):
        """None passes through."""
        result = bind_params(None)
        assert result == [None]

    def test_uuid(self):
        """UUID passes through."""
        u = uuid.uuid4()
        result = bind_params(u)
        assert result == [u]

    def test_datetime_naive(self):
        """Naive datetime gets UTC timezone."""
        dt = datetime(2024, 1, 15, 10, 30, 0)
        result = bind_params(dt)
        assert result[0].tzinfo == timezone.utc

    def test_datetime_aware(self):
        """Aware datetime passes through."""
        dt = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        result = bind_params(dt)
        assert result == [dt]

    def test_dict(self):
        """Dict passes through for JSONB."""
        d = {"key": "value"}
        result = bind_params(d)
        assert result == [d]

    def test_list(self):
        """List passes through for JSONB arrays."""
        lst = [1, 2, 3]
        result = bind_params(lst)
        assert result == [lst]

    def test_bytes(self):
        """Bytes pass through for BYTEA."""
        b = b"binary data"
        result = bind_params(b)
        assert result == [b]

    def test_bool(self):
        """Boolean passes through."""
        result = bind_params(True, False)
        assert result == [True, False]

    def test_multiple(self):
        """Multiple params."""
        result = bind_params("string", 42, 3.14)
        assert result == ["string", 42, 3.14]


class TestNamedToPositional:
    """Tests for :name to $N conversion."""

    def test_simple(self):
        """Simple named params."""
        sql, params = named_to_positional(
            "SELECT * FROM t WHERE a=:foo AND b=:bar",
            {"foo": 1, "bar": 2},
        )
        assert sql == "SELECT * FROM t WHERE a=$1 AND b=$2"
        assert params == [1, 2]

    def test_no_params(self):
        """No named params."""
        sql, params = named_to_positional("SELECT * FROM users", {})
        assert sql == "SELECT * FROM users"
        assert params == []

    def test_type_cast_preserved(self):
        """::type casts are not treated as params."""
        sql, params = named_to_positional(
            "SELECT value::text FROM t WHERE id=:id",
            {"id": 1},
        )
        assert "::text" in sql
        assert sql == "SELECT value::text FROM t WHERE id=$1"

    def test_missing_param_raises(self):
        """Missing param raises KeyError."""
        try:
            named_to_positional("SELECT * FROM t WHERE id=:id", {})
            assert False, "Should have raised KeyError"
        except KeyError as e:
            assert "id" in str(e)


class TestDictToPositional:
    """Tests for %(name)s to $N conversion."""

    def test_simple(self):
        """Simple dict params."""
        sql, params = dict_to_positional(
            "SELECT * FROM t WHERE a=%(foo)s AND b=%(bar)s",
            {"foo": 1, "bar": 2},
        )
        assert sql == "SELECT * FROM t WHERE a=$1 AND b=$2"
        assert params == [1, 2]

    def test_missing_param_raises(self):
        """Missing param raises KeyError."""
        try:
            dict_to_positional("SELECT * FROM t WHERE id=%(id)s", {})
            assert False, "Should have raised KeyError"
        except KeyError as e:
            assert "id" in str(e)


class TestBulkParams:
    """Tests for bulk insert parameter preparation."""

    def test_basic(self):
        """Basic bulk params."""
        rows = [
            {"a": 1, "b": 2},
            {"a": 3, "b": 4},
        ]
        result = bulk_params(rows, ["a", "b"])
        assert result == [(1, 2), (3, 4)]

    def test_missing_column(self):
        """Missing column returns None."""
        rows = [{"a": 1}]
        result = bulk_params(rows, ["a", "b"])
        assert result == [(1, None)]

    def test_type_conversion(self):
        """Values are type-converted."""
        dt = datetime(2024, 1, 15)
        rows = [{"ts": dt}]
        result = bulk_params(rows, ["ts"])
        # Naive datetime should get UTC timezone
        assert result[0][0].tzinfo == timezone.utc
