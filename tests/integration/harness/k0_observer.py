"""K0 PG observation helpers for partition isolation / journey tests.

Direct ``docker exec psql`` queries against the live K0 ``k0_kernel``
database. Used by Epic 7.2 partition isolation tests and Epic 7.3
user journey tests to *verify* that a publish actually committed in
the right partition (tenant_id / space_id / device_id).

Why ``docker exec`` and not asyncpg? Same reason the device
provisioner uses it: the local PG port may be firewalled, and ``psql``
inside ``k0-postgres`` is the same path the K0 deploy scripts already
use, so there is one less transport to debug.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass

DEFAULT_PG_CONTAINER = "k0-postgres"
DEFAULT_PG_USER = "k0user"
DEFAULT_PG_DB = "k0_kernel"


class ObserverError(RuntimeError):
    """Raised when a ``docker exec psql`` observation query fails."""


def _exec_psql(sql: str) -> str:
    pg_container = os.environ.get("K0_PG_CONTAINER", DEFAULT_PG_CONTAINER)
    pg_user = os.environ.get("K0_PG_USER", DEFAULT_PG_USER)
    pg_db = os.environ.get("K0_PG_DB", DEFAULT_PG_DB)
    cp = subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            pg_container,
            "psql",
            "-U",
            pg_user,
            "-d",
            pg_db,
            "-tA",
            "-v",
            "ON_ERROR_STOP=1",
            "-c",
            sql,
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )
    if cp.returncode != 0:
        raise ObserverError(f"psql failed (rc={cp.returncode}): {cp.stderr.strip()}\nSQL: {sql}")
    return cp.stdout.strip()


@dataclass(frozen=True)
class PartitionView:
    tenant_id: str
    space_id: str
    receipts: int
    devices: tuple[str, ...]


def count_receipts(
    *,
    tenant_id: str | None = None,
    space_id: str | None = None,
    device_id: str | None = None,
) -> int:
    """Return the number of ``st_receipts`` rows matching all filters.

    ``None`` filters are omitted (so passing nothing returns the total).
    """
    where: list[str] = []
    if tenant_id is not None:
        where.append(f"tenant_id = '{tenant_id}'")
    if space_id is not None:
        where.append(f"space_id = '{space_id}'")
    if device_id is not None:
        where.append(f"device_id = '{device_id}'")
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    out = _exec_psql(f"SELECT count(*) FROM st_receipts{clause}")
    return int(out or "0")


def list_receipt_device_ids(*, space_id: str) -> tuple[str, ...]:
    """Return the distinct ``device_id`` values present in ``st_receipts``
    for the given ``space_id``.

    Used to assert that no foreign device's writes leaked into a space.
    """
    out = _exec_psql(f"SELECT DISTINCT device_id FROM st_receipts WHERE space_id = '{space_id}'")
    if not out:
        return ()
    return tuple(line.strip() for line in out.splitlines() if line.strip())


def partition_view(*, tenant_id: str, space_id: str) -> PartitionView:
    """Snapshot the receipts partition for one (tenant, space) pair."""
    return PartitionView(
        tenant_id=tenant_id,
        space_id=space_id,
        receipts=count_receipts(tenant_id=tenant_id, space_id=space_id),
        devices=list_receipt_device_ids(space_id=space_id),
    )


def list_wal_positions_for_space(space_id: str) -> tuple[int, ...]:
    """Return ``wal_pos`` values for ``space_id`` in ascending wal order."""
    out = _exec_psql(
        f"SELECT wal_pos FROM st_receipts WHERE space_id = '{space_id}' " "ORDER BY wal_pos ASC"
    )
    if not out:
        return ()
    return tuple(int(line.strip()) for line in out.splitlines() if line.strip())


def latest_receipt_for_device(device_id: str) -> dict[str, str] | None:
    """Return the most recent ``st_receipts`` row for ``device_id``,
    or ``None`` if no receipts exist.
    """
    out = _exec_psql(
        "SELECT receipt_id || '|' || tenant_id || '|' || space_id || '|' || "
        "device_id || '|' || commit_ts || '|' || wal_pos "
        f"FROM st_receipts WHERE device_id = '{device_id}' "
        "ORDER BY wal_pos DESC LIMIT 1"
    )
    if not out:
        return None
    parts = out.split("|")
    if len(parts) != 6:
        return None
    return {
        "receipt_id": parts[0],
        "tenant_id": parts[1],
        "space_id": parts[2],
        "device_id": parts[3],
        "commit_ts": parts[4],
        "wal_pos": parts[5],
    }
