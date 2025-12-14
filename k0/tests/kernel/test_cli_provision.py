from __future__ import annotations

import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory

from ward import test  # type: ignore[attr-defined]

from k0.cli.k0ctl import main
from k0.tests.storage.fixtures import STORAGE_SQL_PATH  # type: ignore[misc]


@test("k0ctl provision command seeds the provisioning ledger")
def _() -> None:
    with TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "kernel.sqlite3"
        connection = sqlite3.connect(db_path)
        try:
            connection.executescript(STORAGE_SQL_PATH.read_text())
            connection.commit()
        finally:
            connection.close()

        exit_code = main(
            [
                "--set",
                f'database.path="{db_path.as_posix()}"',
                "provision",
                "--tenant",
                "tenant-cli",
                "--space",
                "space-cli",
                "--device",
                "device-cli",
                "--mls-group",
                "mls-cli",
                "--key-version",
                "v1",
                "--verify-key",
                "dGV2aWNlLWNsaS12ZXJpZnkta2V5",
                "--ts",
                "2025-09-28T15:00:00+00:00",
            ]
        )
        assert exit_code == 0

        verification = sqlite3.connect(db_path)
        try:
            verification.row_factory = sqlite3.Row
            # Query device binding
            device_row = verification.execute(
                (
                    "SELECT tenant_id, space_id, mls_group_id, provisioned_ts "
                    "FROM st_devices WHERE device_id=?"
                ),
                ("device-cli",),
            ).fetchone()
            # Query device key
            key_row = verification.execute(
                (
                    "SELECT key_version, verify_key, key_state "
                    "FROM st_device_keys WHERE device_id=? AND key_state='ACTIVE'"
                ),
                ("device-cli",),
            ).fetchone()
        finally:
            verification.close()

        assert device_row is not None
        assert device_row["tenant_id"] == "tenant-cli"
        assert device_row["space_id"] == "space-cli"
        assert device_row["mls_group_id"] == "mls-cli"
        assert device_row["provisioned_ts"] == "2025-09-28T15:00:00+00:00"

        assert key_row is not None
        assert key_row["key_version"] == "v1"
        assert key_row["verify_key"] == "dGV2aWNlLWNsaS12ZXJpZnkta2V5"
        assert key_row["key_state"] == "ACTIVE"

