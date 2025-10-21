from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Dict, Iterable, Mapping, Sequence, Tuple

from ward import test  # type: ignore[import]

REPO_ROOT = Path(__file__).resolve().parents[2]
STORAGE_SQL_PATH = REPO_ROOT / "k0" / "contracts" / "sql" / "storage.sql"
BASELINE_MIGRATION_PATH = (
    REPO_ROOT / "k0" / "contracts" / "sql" / "migrations" / "0001_baseline.sql"
)


def _read_sql(path: Path) -> str:
    return path.read_text()


def _open_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


ColumnRecord = Tuple[str, str, bool, str | None, int]
IndexRecord = Tuple[bool, Tuple[str, ...]]
TableSnapshot = Dict[str, Dict[str, object]]


def _capture_schema(conn: sqlite3.Connection) -> TableSnapshot:
    schema: TableSnapshot = {}
    table_rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    for table_row in table_rows:
        table_name = table_row["name"]
        column_rows = conn.execute(f"PRAGMA table_info('{table_name}')").fetchall()
        columns: Tuple[ColumnRecord, ...] = tuple(
            (
                col["name"],
                col["type"],
                bool(col["notnull"]),
                col["dflt_value"],
                col["pk"],
            )
            for col in column_rows
        )

        index_rows = conn.execute(f"PRAGMA index_list('{table_name}')").fetchall()
        indexes: Dict[str, IndexRecord] = {}
        for idx in index_rows:
            index_name = idx["name"]
            if index_name.startswith("sqlite_"):
                continue
            index_info_rows = conn.execute(
                f"PRAGMA index_info('{index_name}')"
            ).fetchall()
            columns_in_index = tuple(info["name"] for info in index_info_rows)
            indexes[index_name] = (bool(idx["unique"]), columns_in_index)

        schema[table_name] = {
            "columns": columns,
            "indexes": indexes,
        }

    return schema


def _schema_from_script(sql_script: str) -> TableSnapshot:
    conn = _open_connection()
    try:
        conn.executescript(sql_script)
        return _capture_schema(conn)
    finally:
        conn.close()


EXPECTED_COLUMNS: Mapping[str, Sequence[str]] = {
    "idem_ledger": (
        "idem_key",
        "receipt_id",
        "first_seen_ts",
        "state",
        "expiry_ts",
    ),
    "schema_registry": (
        "schema_uri",
        "version",
        "sha256",
        "status",
        "operator_id",
        "blocked_ts",
        "blocked_reason",
        "unblocked_ts",
    ),
    "st_devices": (
        "device_id",
        "tenant_id",
        "space_id",
        "mls_group_id",
        "provisioned_ts",
    ),
    "st_device_keys": (
        "device_id",
        "key_version",
        "verify_key",
        "key_state",
        "registered_ts",
        "activated_ts",
        "rotated_ts",
        "revoked_ts",
        "grace_expires_ts",
        "revocation_reason",
    ),
    "st_dlq": (
        "id",
        "wal_pos",
        "tenant_id",
        "space_id",
        "driver",
        "op_kind",
        "fingerprint",
        "payload",
        "reason",
        "retries",
        "requeue_seq",
        "first_failure_ts",
        "last_failure_ts",
        "state",
    ),
    "st_offsets": (
        "subscriber_id",
        "topic",
        "space_id",
        "tenant_id",
        "offset",
        "updated_ts",
    ),
    "st_outbox": (
        "id",
        "wal_pos",
        "tenant_id",
        "space_id",
        "driver",
        "op_kind",
        "payload",
        "fingerprint",
        "requeue_seq",
        "retries",
        "last_error",
    ),
    "st_receipts": (
        "receipt_id",
        "idem_key",
        "wal_pos",
        "commit_ts",
        "tenant_id",
        "space_id",
        "device_id",
        "mls_group_id",
        "key_version",
        "device_sig",
    ),
    "st_wal": (
        "pos",
        "tenant_id",
        "space_id",
        "topic",
        "envelope_json",
        "body",
        "payload_sha256",
        "schema_uri",
        "schema_version",
        "idem_key",
        "device_id",
        "commit_ts",
    ),
}

EXPECTED_PRIMARY_KEYS: Mapping[str, Sequence[str]] = {
    "idem_ledger": ("idem_key",),
    "schema_registry": ("schema_uri", "version"),
    "st_devices": ("device_id",),
    "st_device_keys": ("device_id", "key_version"),
    "st_dlq": ("id",),
    "st_offsets": ("subscriber_id", "topic", "space_id", "tenant_id"),
    "st_outbox": ("id",),
    "st_receipts": ("receipt_id",),
    "st_wal": ("pos",),
}

EXPECTED_NOTNULL: Mapping[str, Iterable[str]] = {
    "idem_ledger": ("idem_key", "receipt_id", "first_seen_ts", "state"),
    "schema_registry": ("schema_uri", "version", "sha256", "status"),
    "st_devices": (
        "device_id",
        "tenant_id",
        "space_id",
        "mls_group_id",
        "provisioned_ts",
    ),
    "st_device_keys": (
        "device_id",
        "key_version",
        "verify_key",
        "key_state",
        "registered_ts",
    ),
    "st_dlq": (
        "id",
        "tenant_id",
        "space_id",
        "driver",
        "op_kind",
        "fingerprint",
        "payload",
        "reason",
        "retries",
        "requeue_seq",
        "first_failure_ts",
        "last_failure_ts",
        "state",
    ),
    "st_offsets": (
        "subscriber_id",
        "topic",
        "space_id",
        "tenant_id",
        "offset",
        "updated_ts",
    ),
    "st_outbox": (
        "id",
        "wal_pos",
        "tenant_id",
        "space_id",
        "driver",
        "op_kind",
        "payload",
        "fingerprint",
        "requeue_seq",
        "retries",
    ),
    "st_receipts": (
        "receipt_id",
        "idem_key",
        "wal_pos",
        "commit_ts",
        "tenant_id",
        "space_id",
        "device_id",
        "mls_group_id",
        "key_version",
        "device_sig",
    ),
    "st_wal": (
        "pos",
        "tenant_id",
        "space_id",
        "topic",
        "envelope_json",
        "schema_uri",
        "schema_version",
        "device_id",
        "commit_ts",
    ),
}

EXPECTED_INDEXES: Mapping[str, Mapping[str, IndexRecord]] = {
    "schema_registry": {},
    "idem_ledger": {},
    "st_devices": {},
    "st_device_keys": {"idx_device_keys_state": (False, ("device_id", "key_state"))},
    "st_dlq": {
        "idx_dlq_space": (False, ("space_id", "first_failure_ts")),
    },
    "st_offsets": {},
    "st_outbox": {
        "idx_outbox_space": (False, ("space_id", "requeue_seq", "id")),
        "uq_outbox_idem": (
            True,
            ("tenant_id", "space_id", "driver", "fingerprint", "requeue_seq"),
        ),
    },
    "st_receipts": {
        "idx_receipts_space": (False, ("space_id", "wal_pos")),
        "idx_receipts_walpos": (False, ("wal_pos",)),
    },
    "st_wal": {
        "idx_wal_space_pos": (False, ("space_id", "pos")),
        "idx_wal_tenant_topic": (False, ("tenant_id", "topic", "pos")),
    },
}


@test("storage.sql creates the canonical SQLite schema with expected constraints")
def storage_sql_instantiate_schema() -> None:
    schema = _schema_from_script(_read_sql(STORAGE_SQL_PATH))

    assert set(schema.keys()) == set(EXPECTED_COLUMNS.keys())

    for table_name, table_info in schema.items():
        columns: Tuple[ColumnRecord, ...] = table_info["columns"]  # type: ignore[assignment]
        column_names = tuple(column[0] for column in columns)
        assert column_names == tuple(
            EXPECTED_COLUMNS[table_name]
        ), f"Column mismatch for {table_name}: expected {EXPECTED_COLUMNS[table_name]}, got {column_names}"

        expected_pk = tuple(EXPECTED_PRIMARY_KEYS[table_name])
        actual_pk = tuple(
            column[0]
            for column in sorted(columns, key=lambda col: col[4])
            if column[4] > 0
        )
        assert (
            actual_pk == expected_pk
        ), f"Primary key mismatch for {table_name}: expected {expected_pk}, got {actual_pk}"

        required_columns = set(EXPECTED_NOTNULL[table_name])
        for column in columns:
            name, _, notnull, _, pk = column
            is_not_null = notnull or pk > 0
            if name in required_columns:
                assert is_not_null, f"Column {name} in {table_name} should be NOT NULL"
            else:
                assert not notnull, f"Column {name} in {table_name} should allow NULL"

        expected_indexes = EXPECTED_INDEXES[table_name]
        actual_indexes: Mapping[str, IndexRecord] = table_info["indexes"]  # type: ignore[index]
        assert (
            actual_indexes == expected_indexes
        ), f"Index mismatch for {table_name}: expected {expected_indexes}, got {actual_indexes}"
        assert (
            "idx_outbox_fingerprint_space" not in actual_indexes
        ), "Deprecated index should not exist"


@test("baseline migration yields the same schema as storage.sql")
def baseline_migration_matches_contract() -> None:
    storage_schema = _schema_from_script(_read_sql(STORAGE_SQL_PATH))
    migration_schema = _schema_from_script(_read_sql(BASELINE_MIGRATION_PATH))

    assert (
        migration_schema == storage_schema
    ), "Baseline migration is out of sync with storage.sql"
