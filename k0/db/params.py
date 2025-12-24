"""Parameter binding utilities for PostgreSQL.

Part of Milestone 1.2.2 - Issue 1.2.2.3: Create Parameter Binding Utilities.

This module provides:
- bind_params: Convert parameters to PostgreSQL-compatible types
- named_to_positional: Convert :name style params to $N positional
- bulk_params: Prepare parameters for bulk insert
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence


def bind_params(*args: Any) -> list[Any]:
    """Convert parameters to PostgreSQL-compatible types.

    Handles:
    - UUID objects: passed through (asyncpg handles natively)
    - datetime: ensures timezone aware (UTC if naive)
    - dict/list: passed through for JSONB columns
    - None: NULL
    - bytes: passthrough for BYTEA
    - bool: PostgreSQL BOOLEAN

    Args:
        *args: Parameter values

    Returns:
        List of converted parameter values
    """
    return [_convert_param(arg) for arg in args]


def _convert_param(value: Any) -> Any:
    """Convert a single parameter value to PostgreSQL-compatible type."""
    if value is None:
        return None

    if isinstance(value, uuid.UUID):
        # asyncpg handles UUID natively
        return value

    if isinstance(value, datetime):
        # Ensure timezone-aware
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    if isinstance(value, (dict, list)):
        # For JSONB columns - asyncpg handles this natively
        return value

    if isinstance(value, bytes):
        # BYTEA - passthrough
        return value

    if isinstance(value, bool):
        # PostgreSQL BOOLEAN
        return value

    # Default: return as-is
    return value


def named_to_positional(
    sql: str,
    params: Mapping[str, Any],
) -> tuple[str, list[Any]]:
    """Convert :name style params to $N positional.

    SQLAlchemy and some ORMs use :name style parameters.
    asyncpg requires $N positional parameters.

    Args:
        sql: SQL with :name placeholders
        params: Dict of name -> value

    Returns:
        Tuple of (converted_sql, ordered_params)

    Example:
        >>> named_to_positional(
        ...     "SELECT * FROM t WHERE a=:foo AND b=:bar",
        ...     {"foo": 1, "bar": 2}
        ... )
        ("SELECT * FROM t WHERE a=$1 AND b=$2", [1, 2])

    Raises:
        KeyError: If a named parameter is not found in params
    """
    result_params: list[Any] = []
    param_index = 0

    # Match :name patterns (but not ::type casts like ::text)
    pattern = re.compile(r"(?<!:):([a-zA-Z_][a-zA-Z0-9_]*)")

    def replace_param(match: re.Match) -> str:
        nonlocal param_index
        name = match.group(1)
        if name not in params:
            raise KeyError(f"Missing parameter: {name}")
        param_index += 1
        result_params.append(_convert_param(params[name]))
        return f"${param_index}"

    result_sql = pattern.sub(replace_param, sql)
    return result_sql, result_params


def dict_to_positional(
    sql: str,
    params: Mapping[str, Any],
) -> tuple[str, list[Any]]:
    """Convert %(name)s style params to $N positional.

    psycopg2 and some libraries use %(name)s style parameters.
    asyncpg requires $N positional parameters.

    Args:
        sql: SQL with %(name)s placeholders
        params: Dict of name -> value

    Returns:
        Tuple of (converted_sql, ordered_params)

    Example:
        >>> dict_to_positional(
        ...     "SELECT * FROM t WHERE a=%(foo)s AND b=%(bar)s",
        ...     {"foo": 1, "bar": 2}
        ... )
        ("SELECT * FROM t WHERE a=$1 AND b=$2", [1, 2])
    """
    result_params: list[Any] = []
    param_index = 0

    # Match %(name)s patterns
    pattern = re.compile(r"%\(([a-zA-Z_][a-zA-Z0-9_]*)\)s")

    def replace_param(match: re.Match) -> str:
        nonlocal param_index
        name = match.group(1)
        if name not in params:
            raise KeyError(f"Missing parameter: {name}")
        param_index += 1
        result_params.append(_convert_param(params[name]))
        return f"${param_index}"

    result_sql = pattern.sub(replace_param, sql)
    return result_sql, result_params


def bulk_params(
    rows: Sequence[Mapping[str, Any]],
    columns: Sequence[str],
) -> list[tuple]:
    """Prepare parameters for bulk insert.

    Extracts values from row dicts in column order for use
    with executemany or copy_records_to_table.

    Args:
        rows: Sequence of row dicts
        columns: Column names in order

    Returns:
        List of tuples for executemany

    Example:
        >>> bulk_params(
        ...     [{"a": 1, "b": 2}, {"a": 3, "b": 4}],
        ...     ["a", "b"]
        ... )
        [(1, 2), (3, 4)]
    """
    result = []
    for row in rows:
        values = tuple(_convert_param(row.get(col)) for col in columns)
        result.append(values)
    return result


def jsonb_param(value: Any) -> str:
    """Serialize value to JSON string for JSONB columns.

    Use when you need explicit JSON serialization rather than
    relying on asyncpg's automatic handling.

    Args:
        value: Value to serialize

    Returns:
        JSON string
    """
    return json.dumps(value)


def array_param(values: Sequence[Any], pg_type: str = "text") -> str:
    """Format values as PostgreSQL array literal.

    Args:
        values: Sequence of values
        pg_type: PostgreSQL element type

    Returns:
        PostgreSQL array literal string
    """
    if not values:
        return f"ARRAY[]::{pg_type}[]"

    # Convert values to strings
    str_values = []
    for v in values:
        if v is None:
            str_values.append("NULL")
        elif isinstance(v, str):
            # Escape quotes
            escaped = v.replace("'", "''")
            str_values.append(f"'{escaped}'")
        elif isinstance(v, bool):
            str_values.append("true" if v else "false")
        else:
            str_values.append(str(v))

    return f"ARRAY[{', '.join(str_values)}]::{pg_type}[]"


__all__ = [
    "array_param",
    "bind_params",
    "bulk_params",
    "dict_to_positional",
    "jsonb_param",
    "named_to_positional",
]
