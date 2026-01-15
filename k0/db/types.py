"""PostgreSQL type converters for K0 kernel.

Part of Milestone 1.2.1 - Issue 1.2.1.3: Create PostgreSQL Type Converters.

This module provides type conversion utilities for PostgreSQL:
- JSON/JSONB codec registration
- UUID TEXT ↔ native UUID conversion
- Timestamp TEXT ↔ datetime conversion
- Record → dict helpers
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import asyncpg


async def setup_type_codecs(conn: asyncpg.Connection) -> None:
    """Register custom type codecs on a connection.

    Called automatically when connections are created.
    Handles JSON, UUID, and timestamp conversions.

    Args:
        conn: asyncpg connection to configure
    """
    # JSON codec - use built-in Python json
    await conn.set_type_codec(
        "json",
        encoder=json.dumps,
        decoder=json.loads,
        schema="pg_catalog",
    )
    # JSONB codec - same handling
    await conn.set_type_codec(
        "jsonb",
        encoder=json.dumps,
        decoder=json.loads,
        schema="pg_catalog",
    )


def text_to_uuid(value: str | None) -> uuid.UUID | None:
    """Convert SQLite TEXT UUID to Python UUID.

    SQLite stores UUIDs as TEXT strings like:
    "550e8400-e29b-41d4-a716-446655440000"

    Args:
        value: UUID string or None

    Returns:
        Python UUID object or None
    """
    if value is None:
        return None
    return uuid.UUID(value)


def uuid_to_text(value: uuid.UUID | None) -> str | None:
    """Convert Python UUID to PostgreSQL-compatible format.

    PostgreSQL native UUID type accepts string format.

    Args:
        value: Python UUID or None

    Returns:
        UUID string or None
    """
    if value is None:
        return None
    return str(value)


def text_to_timestamp(value: str | datetime | None) -> datetime | None:
    """Convert SQLite ISO8601 TEXT to Python datetime.

    SQLite stores timestamps as: "2024-01-15T10:30:00.000000Z"
    PostgreSQL returns native datetime objects.

    Handles both string format (from SQLite) and datetime (from PostgreSQL).

    Args:
        value: ISO8601 string, datetime, or None

    Returns:
        Timezone-aware datetime or None
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        # Already a datetime (from PostgreSQL)
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    # Parse ISO8601 format from SQLite
    # Handle both "Z" suffix and "+00:00" format
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


def timestamp_to_text(value: datetime | None) -> str | None:
    """Convert Python datetime to ISO8601 TEXT for compatibility.

    Ensures timezone is set to UTC before formatting.

    Args:
        value: datetime or None

    Returns:
        ISO8601 formatted string or None
    """
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def timestamp_now() -> datetime:
    """Get current UTC timestamp.

    Returns:
        Current time as timezone-aware datetime in UTC
    """
    return datetime.now(timezone.utc)


def bytes_to_bytea(value: bytes | None) -> bytes | None:
    """Convert Python bytes to PostgreSQL BYTEA (passthrough).

    Both asyncpg and PostgreSQL handle bytes natively.

    Args:
        value: bytes or None

    Returns:
        Same bytes or None
    """
    return value


def record_to_dict(record: asyncpg.Record) -> dict[str, Any]:
    """Convert asyncpg Record to dictionary.

    Args:
        record: asyncpg Record object

    Returns:
        Dictionary with column names as keys
    """
    return dict(record)


def records_to_dicts(records: list[asyncpg.Record]) -> list[dict[str, Any]]:
    """Convert list of asyncpg Records to list of dictionaries.

    Args:
        records: List of asyncpg Record objects

    Returns:
        List of dictionaries with column names as keys
    """
    return [dict(r) for r in records]


def ensure_uuid(value: str | uuid.UUID | None) -> uuid.UUID | None:
    """Ensure value is a UUID object.

    Handles both string and UUID inputs for flexibility.

    Args:
        value: UUID string, UUID object, or None

    Returns:
        UUID object or None
    """
    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(value)


def ensure_timestamp(value: str | datetime | None) -> datetime | None:
    """Ensure value is a timezone-aware datetime.

    Handles both string and datetime inputs for flexibility.

    Args:
        value: ISO8601 string, datetime, or None

    Returns:
        Timezone-aware datetime or None
    """
    return text_to_timestamp(value)


__all__ = [
    "bytes_to_bytea",
    "ensure_timestamp",
    "ensure_uuid",
    "record_to_dict",
    "records_to_dicts",
    "setup_type_codecs",
    "text_to_timestamp",
    "text_to_uuid",
    "timestamp_now",
    "timestamp_to_text",
    "uuid_to_text",
]
