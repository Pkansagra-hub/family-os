"""Query builder utilities for PostgreSQL.

Part of Milestone 1.2.2 - Issue 1.2.2.1: Create Base Query Builder.

This module provides:
- QueryBuilder: Fluent query builder with PostgreSQL $N parameter style
- convert_sqlite_query: Convert SQLite ? params to PostgreSQL $N style
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class QueryBuilder:
    """Fluent query builder with PostgreSQL $N parameter style.

    Builds SQL queries with proper $1, $2, ... parameter placeholders
    for asyncpg. Supports common SQL clauses and PostgreSQL-specific
    features like RETURNING and ON CONFLICT.

    Usage:
        query, params = (
            QueryBuilder()
            .select("id", "name", "email")
            .from_table("users")
            .where("status = ?", "active")
            .where("created_at > ?", some_date)
            .order_by("created_at", desc=True)
            .limit(10)
            .build()
        )
        # query: "SELECT id, name, email FROM users WHERE status = $1 AND created_at > $2 ORDER BY created_at DESC LIMIT 10"
        # params: ["active", some_date]
    """

    _parts: list[str] = field(default_factory=list)
    _params: list[Any] = field(default_factory=list)
    _param_index: int = field(default=0)

    def select(self, *columns: str) -> QueryBuilder:
        """Add SELECT clause.

        Args:
            *columns: Column names to select. If empty, selects *.

        Returns:
            Self for chaining
        """
        cols = ", ".join(columns) if columns else "*"
        self._parts.append(f"SELECT {cols}")
        return self

    def select_distinct(self, *columns: str) -> QueryBuilder:
        """Add SELECT DISTINCT clause.

        Args:
            *columns: Column names to select

        Returns:
            Self for chaining
        """
        cols = ", ".join(columns) if columns else "*"
        self._parts.append(f"SELECT DISTINCT {cols}")
        return self

    def from_table(self, table: str, alias: str | None = None) -> QueryBuilder:
        """Add FROM clause.

        Args:
            table: Table name
            alias: Optional table alias

        Returns:
            Self for chaining
        """
        if alias:
            self._parts.append(f"FROM {table} AS {alias}")
        else:
            self._parts.append(f"FROM {table}")
        return self

    def join(
        self,
        table: str,
        condition: str,
        join_type: str = "INNER",
    ) -> QueryBuilder:
        """Add JOIN clause.

        Args:
            table: Table to join
            condition: Join condition (e.g., "t1.id = t2.fk_id")
            join_type: JOIN, LEFT JOIN, RIGHT JOIN, etc.

        Returns:
            Self for chaining
        """
        self._parts.append(f"{join_type} JOIN {table} ON {condition}")
        return self

    def left_join(self, table: str, condition: str) -> QueryBuilder:
        """Add LEFT JOIN clause."""
        return self.join(table, condition, "LEFT")

    def right_join(self, table: str, condition: str) -> QueryBuilder:
        """Add RIGHT JOIN clause."""
        return self.join(table, condition, "RIGHT")

    def where(self, condition: str, *values: Any) -> QueryBuilder:
        """Add WHERE clause with parameters.

        Use ? as placeholder for values. Multiple calls are ANDed together.

        Args:
            condition: Condition with ? placeholders
            *values: Values for placeholders

        Returns:
            Self for chaining
        """
        formatted = self._format_params(condition, values)
        if any(p.startswith("WHERE") for p in self._parts):
            self._parts.append(f"AND {formatted}")
        else:
            self._parts.append(f"WHERE {formatted}")
        return self

    def or_where(self, condition: str, *values: Any) -> QueryBuilder:
        """Add OR WHERE clause with parameters.

        Args:
            condition: Condition with ? placeholders
            *values: Values for placeholders

        Returns:
            Self for chaining
        """
        formatted = self._format_params(condition, values)
        if any(p.startswith("WHERE") for p in self._parts):
            self._parts.append(f"OR {formatted}")
        else:
            self._parts.append(f"WHERE {formatted}")
        return self

    def where_in(self, column: str, values: list[Any]) -> QueryBuilder:
        """Add WHERE column IN (...) clause.

        Args:
            column: Column name
            values: List of values

        Returns:
            Self for chaining
        """
        if not values:
            # Empty IN clause - always false
            return self.where("1 = 0")

        placeholders = ", ".join(f"${self._next_param(v)}" for v in values)
        if any(p.startswith("WHERE") for p in self._parts):
            self._parts.append(f"AND {column} IN ({placeholders})")
        else:
            self._parts.append(f"WHERE {column} IN ({placeholders})")
        return self

    def insert(self, table: str, **columns: Any) -> QueryBuilder:
        """Build INSERT statement.

        Args:
            table: Table name
            **columns: Column name/value pairs

        Returns:
            Self for chaining
        """
        cols = ", ".join(columns.keys())
        placeholders = ", ".join(f"${self._next_param(v)}" for v in columns.values())
        self._parts.append(f"INSERT INTO {table} ({cols}) VALUES ({placeholders})")
        return self

    def insert_columns(self, table: str, columns: list[str]) -> QueryBuilder:
        """Start INSERT with column names (for multi-row inserts).

        Args:
            table: Table name
            columns: List of column names

        Returns:
            Self for chaining
        """
        cols = ", ".join(columns)
        self._parts.append(f"INSERT INTO {table} ({cols})")
        return self

    def values(self, *row_values: Any) -> QueryBuilder:
        """Add VALUES clause for insert.

        Args:
            *row_values: Values for one row

        Returns:
            Self for chaining
        """
        placeholders = ", ".join(f"${self._next_param(v)}" for v in row_values)
        # Check if we already have a VALUES clause
        if any("VALUES" in p for p in self._parts):
            # Append to existing VALUES
            self._parts.append(f", ({placeholders})")
        else:
            self._parts.append(f"VALUES ({placeholders})")
        return self

    def update(self, table: str) -> QueryBuilder:
        """Start UPDATE statement.

        Args:
            table: Table name

        Returns:
            Self for chaining
        """
        self._parts.append(f"UPDATE {table}")
        return self

    def set(self, **columns: Any) -> QueryBuilder:
        """Add SET clause for UPDATE.

        Args:
            **columns: Column name/value pairs

        Returns:
            Self for chaining
        """
        sets = ", ".join(f"{k} = ${self._next_param(v)}" for k, v in columns.items())
        self._parts.append(f"SET {sets}")
        return self

    def delete(self, table: str) -> QueryBuilder:
        """Start DELETE statement.

        Args:
            table: Table name

        Returns:
            Self for chaining
        """
        self._parts.append(f"DELETE FROM {table}")
        return self

    def returning(self, *columns: str) -> QueryBuilder:
        """Add RETURNING clause (PostgreSQL-specific).

        Args:
            *columns: Column names to return. If empty, returns *.

        Returns:
            Self for chaining
        """
        cols = ", ".join(columns) if columns else "*"
        self._parts.append(f"RETURNING {cols}")
        return self

    def on_conflict(
        self,
        columns: str | list[str],
        action: str = "DO NOTHING",
    ) -> QueryBuilder:
        """Add ON CONFLICT clause for upsert (PostgreSQL-specific).

        Args:
            columns: Conflict column(s)
            action: DO NOTHING or DO UPDATE SET ...

        Returns:
            Self for chaining
        """
        if isinstance(columns, list):
            cols = ", ".join(columns)
        else:
            cols = columns
        self._parts.append(f"ON CONFLICT ({cols}) {action}")
        return self

    def on_conflict_update(
        self,
        columns: str | list[str],
        **update_columns: Any,
    ) -> QueryBuilder:
        """Add ON CONFLICT ... DO UPDATE SET clause.

        Args:
            columns: Conflict column(s)
            **update_columns: Columns to update with values

        Returns:
            Self for chaining
        """
        if isinstance(columns, list):
            cols = ", ".join(columns)
        else:
            cols = columns

        sets = ", ".join(f"{k} = ${self._next_param(v)}" for k, v in update_columns.items())
        self._parts.append(f"ON CONFLICT ({cols}) DO UPDATE SET {sets}")
        return self

    def group_by(self, *columns: str) -> QueryBuilder:
        """Add GROUP BY clause.

        Args:
            *columns: Column names to group by

        Returns:
            Self for chaining
        """
        cols = ", ".join(columns)
        self._parts.append(f"GROUP BY {cols}")
        return self

    def having(self, condition: str, *values: Any) -> QueryBuilder:
        """Add HAVING clause.

        Args:
            condition: Condition with ? placeholders
            *values: Values for placeholders

        Returns:
            Self for chaining
        """
        formatted = self._format_params(condition, values)
        self._parts.append(f"HAVING {formatted}")
        return self

    def order_by(self, *columns: str, desc: bool = False) -> QueryBuilder:
        """Add ORDER BY clause.

        Args:
            *columns: Column names to order by
            desc: If True, order descending

        Returns:
            Self for chaining
        """
        direction = "DESC" if desc else "ASC"
        cols = ", ".join(f"{c} {direction}" for c in columns)
        self._parts.append(f"ORDER BY {cols}")
        return self

    def order_by_expr(self, *expressions: str) -> QueryBuilder:
        """Add ORDER BY with raw expressions.

        Args:
            *expressions: Raw ORDER BY expressions like "name ASC", "id DESC"

        Returns:
            Self for chaining
        """
        self._parts.append(f"ORDER BY {', '.join(expressions)}")
        return self

    def limit(self, n: int) -> QueryBuilder:
        """Add LIMIT clause.

        Args:
            n: Maximum rows to return

        Returns:
            Self for chaining
        """
        self._parts.append(f"LIMIT {n}")
        return self

    def offset(self, n: int) -> QueryBuilder:
        """Add OFFSET clause.

        Args:
            n: Rows to skip

        Returns:
            Self for chaining
        """
        self._parts.append(f"OFFSET {n}")
        return self

    def for_update(self, *, skip_locked: bool = False) -> QueryBuilder:
        """Add FOR UPDATE clause (row locking).

        Args:
            skip_locked: If True, skip locked rows

        Returns:
            Self for chaining
        """
        if skip_locked:
            self._parts.append("FOR UPDATE SKIP LOCKED")
        else:
            self._parts.append("FOR UPDATE")
        return self

    def raw(self, sql: str, *values: Any) -> QueryBuilder:
        """Add raw SQL with optional parameters.

        Args:
            sql: Raw SQL with ? placeholders
            *values: Values for placeholders

        Returns:
            Self for chaining
        """
        formatted = self._format_params(sql, values)
        self._parts.append(formatted)
        return self

    def _next_param(self, value: Any) -> int:
        """Add parameter and return its index."""
        self._param_index += 1
        self._params.append(value)
        return self._param_index

    def _format_params(self, template: str, values: tuple[Any, ...]) -> str:
        """Replace ? placeholders with $N style."""
        result = template
        for value in values:
            idx = self._next_param(value)
            result = result.replace("?", f"${idx}", 1)
        return result

    def build(self) -> tuple[str, list[Any]]:
        """Return the query string and parameters.

        Returns:
            Tuple of (SQL string, parameter list)
        """
        return " ".join(self._parts), self._params

    def __str__(self) -> str:
        """Return query string for debugging."""
        return " ".join(self._parts)


def convert_sqlite_query(sql: str, params: tuple | list = ()) -> tuple[str, list]:
    """Convert SQLite ? params to PostgreSQL $N style.

    This is a compatibility function for migrating existing SQLite queries
    to PostgreSQL without rewriting them.

    Args:
        sql: SQL with ? placeholders
        params: Tuple or list of parameter values

    Returns:
        Tuple of (converted_sql, params_list)

    Example:
        >>> convert_sqlite_query("SELECT * FROM t WHERE a=? AND b=?", (1, 2))
        ("SELECT * FROM t WHERE a=$1 AND b=$2", [1, 2])
    """
    result = sql
    for i, _ in enumerate(params, start=1):
        result = result.replace("?", f"${i}", 1)
    return result, list(params)


def convert_sqlite_upsert(
    table: str,
    columns: list[str],
    conflict_column: str,
    update_columns: list[str] | None = None,
) -> str:
    """Convert SQLite INSERT OR REPLACE to PostgreSQL ON CONFLICT.

    SQLite: INSERT OR REPLACE INTO t (...) VALUES (...)
    PostgreSQL: INSERT INTO t (...) VALUES (...) ON CONFLICT (pk) DO UPDATE SET ...

    Args:
        table: Table name
        columns: All column names
        conflict_column: Primary key or unique column
        update_columns: Columns to update on conflict (default: all except conflict)

    Returns:
        PostgreSQL upsert SQL template with $N placeholders
    """
    if update_columns is None:
        update_columns = [c for c in columns if c != conflict_column]

    cols = ", ".join(columns)
    placeholders = ", ".join(f"${i}" for i in range(1, len(columns) + 1))

    if update_columns:
        updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in update_columns)
        conflict_action = f"DO UPDATE SET {updates}"
    else:
        conflict_action = "DO NOTHING"

    return f"INSERT INTO {table} ({cols}) VALUES ({placeholders}) ON CONFLICT ({conflict_column}) {conflict_action}"


__all__ = [
    "QueryBuilder",
    "convert_sqlite_query",
    "convert_sqlite_upsert",
]
