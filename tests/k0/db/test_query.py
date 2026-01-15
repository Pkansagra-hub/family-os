"""Unit tests for k0.db.query module."""

from __future__ import annotations

from k0.db.query import QueryBuilder, convert_sqlite_query, convert_sqlite_upsert


class TestQueryBuilder:
    """Tests for QueryBuilder fluent interface."""

    def test_select_all(self):
        """SELECT * FROM table."""
        query, params = QueryBuilder().select().from_table("users").build()
        assert query == "SELECT * FROM users"
        assert params == []

    def test_select_columns(self):
        """SELECT specific columns."""
        query, params = QueryBuilder().select("id", "name", "email").from_table("users").build()
        assert query == "SELECT id, name, email FROM users"
        assert params == []

    def test_select_distinct(self):
        """SELECT DISTINCT columns."""
        query, params = QueryBuilder().select_distinct("status").from_table("orders").build()
        assert query == "SELECT DISTINCT status FROM orders"
        assert params == []

    def test_where_single(self):
        """Single WHERE clause."""
        query, params = (
            QueryBuilder().select().from_table("users").where("status = ?", "active").build()
        )
        assert query == "SELECT * FROM users WHERE status = $1"
        assert params == ["active"]

    def test_where_multiple_and(self):
        """Multiple WHERE clauses ANDed together."""
        query, params = (
            QueryBuilder()
            .select()
            .from_table("users")
            .where("status = ?", "active")
            .where("age > ?", 18)
            .build()
        )
        assert query == "SELECT * FROM users WHERE status = $1 AND age > $2"
        assert params == ["active", 18]

    def test_where_or(self):
        """OR WHERE clause."""
        query, params = (
            QueryBuilder()
            .select()
            .from_table("users")
            .where("status = ?", "active")
            .or_where("role = ?", "admin")
            .build()
        )
        assert query == "SELECT * FROM users WHERE status = $1 OR role = $2"
        assert params == ["active", "admin"]

    def test_where_in(self):
        """WHERE column IN (...)."""
        query, params = (
            QueryBuilder().select().from_table("users").where_in("id", [1, 2, 3]).build()
        )
        assert query == "SELECT * FROM users WHERE id IN ($1, $2, $3)"
        assert params == [1, 2, 3]

    def test_where_in_empty(self):
        """WHERE IN with empty list."""
        query, params = QueryBuilder().select().from_table("users").where_in("id", []).build()
        # Empty IN should result in false condition
        assert "1 = 0" in query

    def test_insert(self):
        """INSERT statement."""
        query, params = (
            QueryBuilder().insert("users", name="alice", email="alice@example.com").build()
        )
        assert "INSERT INTO users" in query
        assert "VALUES ($1, $2)" in query
        assert params == ["alice", "alice@example.com"]

    def test_insert_returning(self):
        """INSERT with RETURNING."""
        query, params = QueryBuilder().insert("users", name="alice").returning("id").build()
        assert "RETURNING id" in query

    def test_update(self):
        """UPDATE statement."""
        query, params = (
            QueryBuilder()
            .update("users")
            .set(name="bob", status="inactive")
            .where("id = ?", 1)
            .build()
        )
        assert "UPDATE users SET" in query
        assert "WHERE id = $3" in query
        assert "bob" in params
        assert "inactive" in params
        assert 1 in params

    def test_delete(self):
        """DELETE statement."""
        query, params = QueryBuilder().delete("users").where("id = ?", 1).build()
        assert query == "DELETE FROM users WHERE id = $1"
        assert params == [1]

    def test_on_conflict_do_nothing(self):
        """ON CONFLICT DO NOTHING."""
        query, params = (
            QueryBuilder().insert("users", name="alice").on_conflict("name", "DO NOTHING").build()
        )
        assert "ON CONFLICT (name) DO NOTHING" in query

    def test_on_conflict_update(self):
        """ON CONFLICT DO UPDATE SET."""
        query, params = (
            QueryBuilder()
            .insert("users", name="alice", status="new")
            .on_conflict_update("name", status="existing")
            .build()
        )
        assert "ON CONFLICT (name) DO UPDATE SET status = $3" in query
        assert params == ["alice", "new", "existing"]

    def test_join(self):
        """INNER JOIN."""
        query, params = (
            QueryBuilder()
            .select("u.id", "o.total")
            .from_table("users", "u")
            .join("orders o", "u.id = o.user_id")
            .build()
        )
        assert "FROM users AS u" in query
        assert "INNER JOIN orders o ON u.id = o.user_id" in query

    def test_left_join(self):
        """LEFT JOIN."""
        query, params = (
            QueryBuilder()
            .select()
            .from_table("users")
            .left_join("orders", "users.id = orders.user_id")
            .build()
        )
        assert "LEFT JOIN orders ON" in query

    def test_order_by(self):
        """ORDER BY clause."""
        query, params = (
            QueryBuilder().select().from_table("users").order_by("created_at", desc=True).build()
        )
        assert "ORDER BY created_at DESC" in query

    def test_limit_offset(self):
        """LIMIT and OFFSET."""
        query, params = QueryBuilder().select().from_table("users").limit(10).offset(20).build()
        assert "LIMIT 10" in query
        assert "OFFSET 20" in query

    def test_group_by_having(self):
        """GROUP BY with HAVING."""
        query, params = (
            QueryBuilder()
            .select("status", "COUNT(*)")
            .from_table("users")
            .group_by("status")
            .having("COUNT(*) > ?", 5)
            .build()
        )
        assert "GROUP BY status" in query
        assert "HAVING COUNT(*) > $1" in query

    def test_for_update(self):
        """FOR UPDATE clause."""
        query, params = (
            QueryBuilder().select().from_table("users").where("id = ?", 1).for_update().build()
        )
        assert "FOR UPDATE" in query

    def test_for_update_skip_locked(self):
        """FOR UPDATE SKIP LOCKED."""
        query, params = (
            QueryBuilder().select().from_table("users").for_update(skip_locked=True).build()
        )
        assert "FOR UPDATE SKIP LOCKED" in query

    def test_raw(self):
        """Raw SQL with parameters."""
        query, params = (
            QueryBuilder()
            .raw("SELECT * FROM users WHERE status = ? AND role = ?", "active", "admin")
            .build()
        )
        assert query == "SELECT * FROM users WHERE status = $1 AND role = $2"
        assert params == ["active", "admin"]


class TestConvertSqliteQuery:
    """Tests for SQLite to PostgreSQL query conversion."""

    def test_simple_conversion(self):
        """Convert ? to $N."""
        sql, params = convert_sqlite_query(
            "SELECT * FROM t WHERE a=? AND b=?",
            (1, 2),
        )
        assert sql == "SELECT * FROM t WHERE a=$1 AND b=$2"
        assert params == [1, 2]

    def test_no_params(self):
        """Query without parameters."""
        sql, params = convert_sqlite_query("SELECT * FROM users", ())
        assert sql == "SELECT * FROM users"
        assert params == []

    def test_single_param(self):
        """Query with single parameter."""
        sql, params = convert_sqlite_query("SELECT * FROM users WHERE id=?", (42,))
        assert sql == "SELECT * FROM users WHERE id=$1"
        assert params == [42]

    def test_list_params(self):
        """Works with list params too."""
        sql, params = convert_sqlite_query(
            "SELECT * FROM t WHERE a=?",
            [1],
        )
        assert sql == "SELECT * FROM t WHERE a=$1"
        assert params == [1]


class TestConvertSqliteUpsert:
    """Tests for SQLite INSERT OR REPLACE conversion."""

    def test_basic_upsert(self):
        """Convert to ON CONFLICT DO UPDATE."""
        sql = convert_sqlite_upsert(
            "users",
            ["id", "name", "email"],
            "id",
        )
        assert "INSERT INTO users (id, name, email)" in sql
        assert "VALUES ($1, $2, $3)" in sql
        assert "ON CONFLICT (id) DO UPDATE SET" in sql
        assert "name = EXCLUDED.name" in sql
        assert "email = EXCLUDED.email" in sql

    def test_upsert_specific_columns(self):
        """Update only specific columns on conflict."""
        sql = convert_sqlite_upsert(
            "users",
            ["id", "name", "email", "status"],
            "id",
            update_columns=["status"],
        )
        assert "ON CONFLICT (id) DO UPDATE SET status = EXCLUDED.status" in sql
        assert "name = EXCLUDED.name" not in sql

    def test_upsert_do_nothing(self):
        """Empty update columns = DO NOTHING."""
        sql = convert_sqlite_upsert(
            "users",
            ["id", "name"],
            "id",
            update_columns=[],
        )
        assert "ON CONFLICT (id) DO NOTHING" in sql
