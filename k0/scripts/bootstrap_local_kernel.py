#!/usr/bin/env python3
"""Bootstrap the local kernel database with schemas and provisioning state."""

from __future__ import annotations

import argparse
import logging
from datetime import datetime, timezone
from pathlib import Path

from k0.automation.migrate import MigrationError, apply_migrations
from k0.gate.schema_registry import SchemaRecord, SchemaRegistry
from k0.local.dev_profile import default_profile, signing_key_for, verify_key_b64
from k0.local.env import coerce_path, get_env_value, load_env_overrides
from k0.storage.provisioning import DeviceKey, ProvisionedDevice, ProvisioningLedger
from k0.uow.connection_pool import configure_pool, connection_scope, shutdown_pool

logger = logging.getLogger(__name__)
REPO_ROOT = Path(__file__).resolve().parents[1]
COMPOSE_DATA_DIR = (
    REPO_ROOT / "k0/deployment/compose/generated/local-single-node/data"
).resolve()


def _resolve_default_db_path() -> Path:
    env_db_path = get_env_value("K0_DB_PATH")
    if env_db_path:
        return coerce_path(env_db_path)
    return (COMPOSE_DATA_DIR / "k0_kernel.db").resolve()


DEFAULT_DB_PATH = _resolve_default_db_path()


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )


def _apply_migrations(database_path: Path) -> None:
    try:
        results = apply_migrations(database_path)
    except MigrationError as exc:  # pragma: no cover - defensive guard
        logger.error("Migration failed: %s", exc)
        raise SystemExit(2) from exc

    applied = sum(1 for result in results if result.action == "applied")
    pending = sum(1 for result in results if result.action == "pending")
    logger.info(
        "Database migrations complete (applied=%d, pending=%d) --> %s",
        applied,
        pending,
        database_path,
    )


def _ensure_profile_state(database_path: Path) -> None:
    profile = default_profile()
    logger.info(
        "Using profile tenant=%s space=%s device=%s",
        profile.tenant_id,
        profile.space_id,
        profile.device_id,
    )
    configure_pool(database_path)
    logger.debug("Connection pool configured for %s", database_path)

    try:
        registry = SchemaRegistry()
        ledger = ProvisioningLedger()

        now_ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        verify_key = verify_key_b64(profile)
        signing_key = signing_key_for(profile)

        with connection_scope() as conn:
            registry.upsert(
                SchemaRecord(
                    uri=profile.schema_uri,
                    version=profile.schema_version,
                    sha256=profile.schema_sha,
                    status="ACTIVE",
                ),
                connection=conn,
            )

            ledger.register(
                ProvisionedDevice(
                    device_id=profile.device_id,
                    tenant_id=profile.tenant_id,
                    space_id=profile.space_id,
                    mls_group_id=profile.mls_group_id,
                    provisioned_ts=now_ts,
                ),
                connection=conn,
            )

            ledger.add_key(
                DeviceKey(
                    device_id=profile.device_id,
                    key_version=profile.key_version,
                    verify_key=verify_key,
                    key_state="ACTIVE",
                    registered_ts=now_ts,
                    activated_ts=now_ts,
                ),
                connection=conn,
            )

            conn.commit()

        logger.info(
            "Provisioned device %s (tenant=%s space=%s) with key version %s",
            profile.device_id,
            profile.tenant_id,
            profile.space_id,
            profile.key_version,
        )
        logger.debug("Signing key seed (hex) %s", profile.signing_key_seed_hex)
        logger.info(
            "Verification key (base64url) %s",
            verify_key,
        )
        logger.debug("Signing public key %s", signing_key.verify_key.encode().hex())
    finally:
        shutdown_pool()
        logger.debug("Connection pool shut down")


def bootstrap(database_path: Path) -> None:
    logger.info("Bootstrapping local kernel database at %s", database_path)
    overrides = load_env_overrides()
    if overrides:
        logger.debug("Loaded %d environment overrides", len(overrides))
    database_path.parent.mkdir(parents=True, exist_ok=True)

    _apply_migrations(database_path)
    _ensure_profile_state(database_path)

    logger.info("Bootstrap complete. Kernel command path is ready for traffic.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Seed local kernel database with provisioning and schema state",
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_DB_PATH,
        help="Path to the kernel SQLite database (defaults to local single-node bundle)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    _configure_logging(args.verbose)
    database_path = coerce_path(str(args.database))

    try:
        bootstrap(database_path)
    except SystemExit:
        raise
    except Exception as exc:  # pragma: no cover - defensive guard
        logger.exception("Bootstrap failed: %s", exc)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
