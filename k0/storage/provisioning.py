"""Provisioning ledger adapter used by the Minimal Gate."""

from __future__ import annotations

import sqlite3
import threading
from collections import OrderedDict
from contextlib import contextmanager
from dataclasses import dataclass, replace
from typing import Iterable, Iterator

from k0.uow.connection_pool import connection_scope


@dataclass(slots=True)
class ProvisionedDevice:
    """Represents a provisioned device binding (without key material)."""

    device_id: str
    tenant_id: str
    space_id: str
    mls_group_id: str
    provisioned_ts: str


@dataclass(slots=True)
class DeviceKey:
    """Represents a device verification key with rotation lifecycle state."""

    device_id: str
    key_version: str
    verify_key: str
    key_state: str  # PENDING, ACTIVE, ROTATING, REVOKED
    registered_ts: str
    activated_ts: str | None = None
    rotated_ts: str | None = None
    revoked_ts: str | None = None
    grace_expires_ts: str | None = None
    revocation_reason: str | None = None


@contextmanager
def _resolve_connection(
    connection: sqlite3.Connection | None,
) -> Iterator[sqlite3.Connection]:
    if connection is not None:
        yield connection
        return

    with connection_scope() as pooled_connection:
        yield pooled_connection
        pooled_connection.commit()


class _LRUCache:
    """Thread-safe LRU cache keyed by (tenant, space, device)."""

    def __init__(self, capacity: int) -> None:
        if capacity <= 0:
            msg = "cache_size must be greater than zero"
            raise ValueError(msg)
        self._capacity = capacity
        self._entries: OrderedDict[tuple[str, str, str], ProvisionedDevice] = (
            OrderedDict()
        )
        self._lock = threading.RLock()

    def get(self, key: tuple[str, str, str]) -> ProvisionedDevice | None:
        with self._lock:
            try:
                value = self._entries[key]
            except KeyError:
                return None
            self._entries.move_to_end(key)
            return value

    def put(self, key: tuple[str, str, str], value: ProvisionedDevice) -> None:
        with self._lock:
            self._entries[key] = value
            self._entries.move_to_end(key)
            while len(self._entries) > self._capacity:
                self._entries.popitem(last=False)

    def invalidate_device(self, device_id: str) -> None:
        with self._lock:
            keys_to_remove = [
                key
                for key, record in self._entries.items()
                if record.device_id == device_id
            ]
            for key in keys_to_remove:
                self._entries.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


class _DeviceKeyCache:
    """Thread-safe LRU cache for device verification keys."""

    def __init__(self, capacity: int) -> None:
        if capacity <= 0:
            msg = "key_cache_size must be greater than zero"
            raise ValueError(msg)
        self._capacity = capacity
        self._entries: OrderedDict[str, tuple[DeviceKey, ...]] = OrderedDict()
        self._lock = threading.RLock()

    def get(self, device_id: str) -> list[DeviceKey] | None:
        with self._lock:
            cached = self._entries.get(device_id)
            if cached is None:
                return None
            self._entries.move_to_end(device_id)
            return list(cached)

    def put(self, device_id: str, keys: list[DeviceKey]) -> None:
        with self._lock:
            self._entries[device_id] = tuple(keys)
            self._entries.move_to_end(device_id)
            while len(self._entries) > self._capacity:
                self._entries.popitem(last=False)

    def invalidate(self, device_id: str) -> None:
        with self._lock:
            self._entries.pop(device_id, None)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


class ProvisioningLedger:
    """Persistence adapter and cache for provisioned device records."""

    def __init__(
        self,
        *,
        cache_size: int = 512,
        key_cache_size: int = 512,
    ) -> None:
        self._cache = _LRUCache(cache_size)
        self._key_cache = _DeviceKeyCache(key_cache_size)

    def register(
        self,
        device: ProvisionedDevice,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> ProvisionedDevice:
        """Register a device binding in the provisioning store.

        Note: This method only registers device bindings (tenant/space/mls_group).
        To add verification keys, use `add_key()` method separately.
        """
        with _resolve_connection(connection) as conn:
            conn.execute(
                (
                    "INSERT INTO st_devices (device_id, tenant_id, space_id, mls_group_id, provisioned_ts) "
                    "VALUES (?, ?, ?, ?, ?) "
                    "ON CONFLICT(device_id) DO UPDATE SET tenant_id=excluded.tenant_id, space_id=excluded.space_id, "
                    "mls_group_id=excluded.mls_group_id, provisioned_ts=excluded.provisioned_ts"
                ),
                (
                    device.device_id,
                    device.tenant_id,
                    device.space_id,
                    device.mls_group_id,
                    device.provisioned_ts,
                ),
            )
        self._cache.invalidate_device(device.device_id)
        self._key_cache.invalidate(device.device_id)
        return device

    def add_key(
        self,
        key: DeviceKey,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> DeviceKey:
        """Add or update a verification key for a device."""
        normalized_key = key.verify_key.strip()
        if not normalized_key:
            raise ValueError("verify_key must not be empty")

        stored = replace(key, verify_key=normalized_key)
        with _resolve_connection(connection) as conn:
            conn.execute(
                (
                    "INSERT INTO st_device_keys "
                    "(device_id, key_version, verify_key, key_state, registered_ts, "
                    "activated_ts, rotated_ts, revoked_ts, grace_expires_ts, revocation_reason) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(device_id, key_version) DO UPDATE SET "
                    "verify_key=excluded.verify_key, key_state=excluded.key_state, "
                    "activated_ts=excluded.activated_ts, rotated_ts=excluded.rotated_ts, "
                    "revoked_ts=excluded.revoked_ts, grace_expires_ts=excluded.grace_expires_ts, "
                    "revocation_reason=excluded.revocation_reason"
                ),
                (
                    stored.device_id,
                    stored.key_version,
                    stored.verify_key,
                    stored.key_state,
                    stored.registered_ts,
                    stored.activated_ts,
                    stored.rotated_ts,
                    stored.revoked_ts,
                    stored.grace_expires_ts,
                    stored.revocation_reason,
                ),
            )
        self._cache.invalidate_device(stored.device_id)
        self._key_cache.invalidate(stored.device_id)
        return stored

    def seed(
        self,
        devices: Iterable[ProvisionedDevice],
        *,
        connection: sqlite3.Connection | None = None,
    ) -> None:
        """Seed device bindings (for backward compatibility and testing)."""
        with _resolve_connection(connection) as conn:
            for device in devices:
                self.register(device, connection=conn)

    def lookup(
        self,
        tenant_id: str,
        space_id: str,
        device_id: str,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> ProvisionedDevice | None:
        """Lookup device provisioning bindings."""
        key = (tenant_id, space_id, device_id)
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        with _resolve_connection(connection) as conn:
            row = conn.execute(
                (
                    "SELECT device_id, tenant_id, space_id, mls_group_id, provisioned_ts "
                    "FROM st_devices WHERE device_id=?"
                ),
                (device_id,),
            ).fetchone()

        if row is None:
            return None

        record = ProvisionedDevice(
            device_id=row["device_id"],
            tenant_id=row["tenant_id"],
            space_id=row["space_id"],
            mls_group_id=row["mls_group_id"],
            provisioned_ts=row["provisioned_ts"],
        )

        if record.tenant_id != tenant_id or record.space_id != space_id:
            return record

        self._cache.put(key, record)
        return record

    def get_keys(
        self,
        device_id: str,
        *,
        states: list[str] | None = None,
        connection: sqlite3.Connection | None = None,
    ) -> list[DeviceKey]:
        """Retrieve verification keys for a device, optionally filtered by state.

        Args:
            device_id: Device identifier to query keys for
            states: Optional list of key_state values to filter by (e.g., ['ACTIVE', 'ROTATING'])
            connection: Optional database connection

        Returns:
            List of DeviceKey records matching the criteria, sorted by activated_ts DESC
        """
        cached_keys = self._key_cache.get(device_id)
        if cached_keys is None:
            cached_keys = self._load_keys(device_id, connection=connection)
            self._key_cache.put(device_id, cached_keys)

        if not states:
            return list(cached_keys)

        normalized = {state.strip().upper() for state in states}
        return [key for key in cached_keys if key.key_state.upper() in normalized]

    def _load_keys(
        self,
        device_id: str,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> list[DeviceKey]:
        with _resolve_connection(connection) as conn:
            rows = conn.execute(
                (
                    "SELECT device_id, key_version, verify_key, key_state, registered_ts, "
                    "activated_ts, rotated_ts, revoked_ts, grace_expires_ts, revocation_reason "
                    "FROM st_device_keys WHERE device_id=? "
                    "ORDER BY activated_ts DESC, registered_ts DESC"
                ),
                (device_id,),
            ).fetchall()

        return [
            DeviceKey(
                device_id=row["device_id"],
                key_version=row["key_version"],
                verify_key=row["verify_key"],
                key_state=row["key_state"],
                registered_ts=row["registered_ts"],
                activated_ts=row["activated_ts"],
                rotated_ts=row["rotated_ts"],
                revoked_ts=row["revoked_ts"],
                grace_expires_ts=row["grace_expires_ts"],
                revocation_reason=row["revocation_reason"],
            )
            for row in rows
        ]

    def clear_cache(self) -> None:
        """Remove all cached provisioning records."""

        self._cache.clear()
        self._key_cache.clear()


__all__ = [
    "DeviceKey",
    "ProvisionedDevice",
    "ProvisioningLedger",
]
