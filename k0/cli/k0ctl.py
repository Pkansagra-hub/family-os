"""Administrative CLI for orchestrating the K0 kernel runtime."""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, MutableMapping, Sequence, cast

import yaml

from ..automation.migrate import MigrationError, MigrationResult, apply_migrations
from ..gate.schema_registry import SchemaRecord, SchemaRegistry
from ..kernel.config import KernelSettings
from ..kernel.main import run as run_kernel
from ..obs import MetricsExporter, ObservabilityEmitter, configure_structured_logging
from ..storage import SnapshotError, SnapshotScheduler
from ..storage.dlq import DeadLetter, DeadLetterQueue
from ..storage.outbox import OutboxEntry, OutboxStore
from ..storage.provisioning import DeviceKey, ProvisionedDevice, ProvisioningLedger
from ..storage.replayer import Replayer, ReplayError
from ..uow.connection_pool import configure_pool, connection_scope, shutdown_pool

logger = logging.getLogger(__name__)

ServeRunner = Callable[[KernelSettings, "ServeOptions"], int | None]


@dataclass(frozen=True)
class ServeOptions:
    """Resolved runtime parameters for the embedded Uvicorn server."""

    host: str
    port: int
    log_level: str
    timeout_graceful_shutdown: float


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="K0 kernel control surface")
    parser.add_argument(
        "--config",
        dest="config",
        type=Path,
        default=None,
        help="Path to the kernel YAML configuration file (defaults to config/kernel.yaml)",
    )
    parser.add_argument(
        "--set",
        dest="overrides",
        action="append",
        default=None,
        metavar="KEY=VALUE",
        help=(
            "Override configuration values using dotted paths (e.g. --set "
            "server.port=9090)."
        ),
    )

    subparsers = parser.add_subparsers(dest="command")

    serve_parser = subparsers.add_parser(
        "serve",
        help="Run the kernel's FastAPI/ASGI server",
    )
    serve_parser.add_argument("--host", dest="host", help="Override bind host")
    serve_parser.add_argument(
        "--port",
        dest="port",
        type=int,
        help="Override bind port",
    )
    serve_parser.add_argument(
        "--log-level",
        dest="log_level",
        choices=["critical", "error", "warning", "info", "debug", "trace"],
        help="Override server log level",
    )
    serve_parser.add_argument(
        "--graceful-timeout",
        dest="graceful_timeout",
        type=float,
        help="Override graceful shutdown timeout in seconds",
    )

    migrate_parser = subparsers.add_parser(
        "migrate", help="Apply storage schema migrations to the database"
    )
    migrate_parser.add_argument(
        "--database",
        dest="database",
        type=Path,
        help="Override the database path (defaults to settings.database.path)",
    )
    migrate_parser.add_argument(
        "--migrations-dir",
        dest="migrations_dir",
        type=Path,
        help="Path to the migrations directory (defaults to k0/contracts/sql/migrations)",
    )
    migrate_parser.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        help="Preview migrations without applying changes",
    )

    provision_parser = subparsers.add_parser(
        "provision",
        help="Register a device binding in the provisioning ledger",
    )
    provision_parser.add_argument(
        "--tenant",
        dest="tenant_id",
        required=True,
        help="Tenant identifier bound to the device",
    )
    provision_parser.add_argument(
        "--space",
        dest="space_id",
        required=True,
        help="Space identifier bound to the device",
    )
    provision_parser.add_argument(
        "--device",
        dest="device_id",
        required=True,
        help="Device identifier to provision",
    )
    provision_parser.add_argument(
        "--mls-group",
        dest="mls_group_id",
        required=True,
        help="MLS group identifier associated with the device",
    )
    provision_parser.add_argument(
        "--key-version",
        dest="key_version",
        required=True,
        help="Active key version bound to the device",
    )
    provision_parser.add_argument(
        "--verify-key",
        dest="verify_key",
        required=True,
        help="URL-safe base64 public verification key for the device",
    )
    provision_parser.add_argument(
        "--ts",
        dest="provisioned_ts",
        default=None,
        help="Provisioning timestamp (ISO 8601, defaults to current UTC time)",
    )
    provision_parser.add_argument(
        "--database",
        dest="database",
        type=Path,
        help="Override the database path (defaults to settings.database.path)",
    )

    schema_parser = subparsers.add_parser(
        "schema",
        help="Manage schema registry lifecycle",
    )
    schema_parser.add_argument(
        "--database",
        dest="database",
        type=Path,
        help="Override the database path (defaults to settings.database.path)",
    )
    schema_subparsers = schema_parser.add_subparsers(dest="schema_command")

    register_parser = schema_subparsers.add_parser(
        "register",
        help="Register a schema version",
    )
    register_parser.add_argument(
        "--uri",
        dest="uri",
        required=True,
        help="Schema URI to register",
    )
    register_parser.add_argument(
        "--version",
        dest="version",
        required=True,
        help="Semantic version for the schema",
    )
    register_parser.add_argument(
        "--sha256",
        dest="sha256",
        required=True,
        help="Canonical schema payload digest",
    )
    register_parser.add_argument(
        "--status",
        dest="status",
        choices=["REGISTERED", "ACTIVE"],
        default="REGISTERED",
        help="Initial status for the schema (defaults to REGISTERED)",
    )
    register_parser.add_argument(
        "--activate",
        dest="activate",
        action="store_true",
        help="Promote the version to ACTIVE after registration",
    )

    promote_parser = schema_subparsers.add_parser(
        "promote",
        help="Promote a schema version to ACTIVE",
    )
    promote_parser.add_argument(
        "--uri",
        dest="uri",
        required=True,
        help="Schema URI to promote",
    )
    promote_parser.add_argument(
        "--version",
        dest="version",
        required=True,
        help="Version to promote",
    )

    block_parser = schema_subparsers.add_parser(
        "block",
        help="Block a schema version with audit trail",
    )
    block_parser.add_argument(
        "--uri",
        dest="uri",
        required=True,
        help="Schema URI to block",
    )
    block_parser.add_argument(
        "--version",
        dest="version",
        required=True,
        help="Version to block",
    )
    block_parser.add_argument(
        "--operator",
        dest="operator_id",
        required=True,
        help="Operator ID/email performing the block (required for audit trail)",
    )
    block_parser.add_argument(
        "--reason",
        dest="reason",
        required=True,
        help="Justification for emergency block (required for audit trail)",
    )

    # Schema audit command (ADR 002)
    audit_parser = schema_subparsers.add_parser(
        "audit",
        help="View schema registry audit trail",
    )
    audit_parser.add_argument(
        "--uri",
        dest="uri",
        default=None,
        help="Filter by schema URI (optional)",
    )
    audit_parser.add_argument(
        "--version",
        dest="version",
        default=None,
        help="Filter by version (requires --uri)",
    )
    audit_parser.add_argument(
        "--status",
        dest="status",
        default=None,
        choices=["REGISTERED", "ACTIVE", "DEPRECATED", "BLOCKED"],
        help="Filter by status (optional)",
    )
    audit_parser.add_argument(
        "--database",
        dest="database",
        type=Path,
        help="Override the database path (defaults to settings.database.path)",
    )

    # Key management commands (ADR 001: Key Rotation)
    key_parser = subparsers.add_parser(
        "key",
        help="Manage device verification keys with rotation support",
    )
    key_parser.add_argument(
        "--database",
        dest="database",
        type=Path,
        help="Override the database path (defaults to settings.database.path)",
    )
    key_subparsers = key_parser.add_subparsers(dest="key_command")

    add_key_parser = key_subparsers.add_parser(
        "add",
        help="Register a new verification key for a device",
    )
    add_key_parser.add_argument(
        "--device",
        dest="device_id",
        required=True,
        help="Device identifier to add key for",
    )
    add_key_parser.add_argument(
        "--key-version",
        dest="key_version",
        required=True,
        help="Version identifier for the new key",
    )
    add_key_parser.add_argument(
        "--verify-key",
        dest="verify_key",
        required=True,
        help="URL-safe base64 public verification key",
    )
    add_key_parser.add_argument(
        "--state",
        dest="key_state",
        choices=["PENDING", "ACTIVE"],
        default="PENDING",
        help="Initial state for the key (default: PENDING)",
    )
    add_key_parser.add_argument(
        "--ts",
        dest="registered_ts",
        default=None,
        help="Registration timestamp (ISO 8601, defaults to current UTC time)",
    )

    activate_key_parser = key_subparsers.add_parser(
        "activate",
        help="Activate a key and transition old ACTIVE keys to ROTATING",
    )
    activate_key_parser.add_argument(
        "--device",
        dest="device_id",
        required=True,
        help="Device identifier",
    )
    activate_key_parser.add_argument(
        "--key-version",
        dest="key_version",
        required=True,
        help="Key version to activate",
    )
    activate_key_parser.add_argument(
        "--grace-hours",
        dest="grace_hours",
        type=int,
        default=None,
        help="Grace window hours for old keys (overrides config default)",
    )

    revoke_key_parser = key_subparsers.add_parser(
        "revoke",
        help="Revoke a key immediately (security incident)",
    )
    revoke_key_parser.add_argument(
        "--device",
        dest="device_id",
        required=True,
        help="Device identifier",
    )
    revoke_key_parser.add_argument(
        "--key-version",
        dest="key_version",
        required=True,
        help="Key version to revoke",
    )
    revoke_key_parser.add_argument(
        "--reason",
        dest="revocation_reason",
        required=True,
        help="Reason for revocation (required for audit trail)",
    )

    list_keys_parser = key_subparsers.add_parser(
        "list",
        help="List all keys for a device",
    )
    list_keys_parser.add_argument(
        "--device",
        dest="device_id",
        required=True,
        help="Device identifier",
    )
    list_keys_parser.add_argument(
        "--state",
        dest="key_state",
        choices=["PENDING", "ACTIVE", "ROTATING", "REVOKED", "ALL"],
        default="ALL",
        help="Filter by key state (default: ALL)",
    )

    expire_grace_parser = key_subparsers.add_parser(
        "expire-grace",
        help="Transition expired ROTATING keys to REVOKED",
    )
    expire_grace_parser.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        help="Preview which keys would be expired without making changes",
    )

    snapshot_parser = subparsers.add_parser(
        "snapshot",
        help="Manage WAL snapshots",
    )
    snapshot_parser.add_argument(
        "--database",
        dest="database",
        type=Path,
        help="Override the database path (defaults to settings.database.path)",
    )
    snapshot_subparsers = snapshot_parser.add_subparsers(dest="snapshot_command")

    snapshot_create_parser = snapshot_subparsers.add_parser(
        "create",
        help="Create a snapshot and emit WAL markers",
    )
    snapshot_create_parser.add_argument(
        "--output-dir",
        dest="output_dir",
        type=Path,
        default=Path("snapshots"),
        help="Directory where snapshot artifacts will be written (default: ./snapshots)",
    )
    snapshot_create_parser.add_argument(
        "--snapshot-id",
        dest="snapshot_id",
        default=None,
        help="Optional snapshot identifier (defaults to autogenerated)",
    )
    snapshot_create_parser.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        help="Plan snapshot without writing artifacts or WAL markers",
    )

    replay_parser = subparsers.add_parser(
        "replay",
        help="Replay WAL entries and validate parity",
    )
    replay_parser.add_argument(
        "--database",
        dest="database",
        type=Path,
        help="Override the database path (defaults to settings.database.path)",
    )
    replay_parser.add_argument(
        "--from-pos",
        dest="from_position",
        type=int,
        default=0,
        help="Replay entries with WAL position greater than this value (default: 0)",
    )
    replay_parser.add_argument(
        "--tenant",
        dest="tenant_id",
        default=None,
        help="Restrict replay to a tenant identifier",
    )
    replay_parser.add_argument(
        "--space",
        dest="space_id",
        default=None,
        help="Restrict replay to a space identifier",
    )
    replay_parser.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        help="Validate parity without mutating state",
    )

    dlq_parser = subparsers.add_parser(
        "dlq",
        help="Inspect and manage the dead-letter queue",
    )
    dlq_parser.add_argument(
        "--database",
        dest="database",
        type=Path,
        help="Override the database path (defaults to settings.database.path)",
    )
    dlq_subparsers = dlq_parser.add_subparsers(dest="dlq_command")

    dlq_list_parser = dlq_subparsers.add_parser(
        "list",
        help="List dead-letter entries matching optional filters",
    )
    dlq_list_parser.add_argument(
        "--limit",
        dest="limit",
        type=int,
        default=20,
        help="Maximum number of entries to display (default: 20)",
    )
    dlq_list_parser.add_argument(
        "--state",
        dest="state",
        choices=["PENDING", "REQUEUED", "QUARANTINED", "ALL"],
        default="PENDING",
        help="Filter by DLQ state (default: PENDING)",
    )
    dlq_list_parser.add_argument(
        "--tenant",
        dest="tenant",
        default=None,
        help="Restrict results to a tenant identifier",
    )
    dlq_list_parser.add_argument(
        "--space",
        dest="space",
        default=None,
        help="Restrict results to a space identifier",
    )
    dlq_list_parser.add_argument(
        "--driver",
        dest="driver",
        default=None,
        help="Restrict results to a driver alias",
    )

    dlq_requeue_parser = dlq_subparsers.add_parser(
        "requeue",
        help="Requeue a dead-letter entry back into the outbox",
    )
    dlq_requeue_parser.add_argument(
        "--id",
        dest="letter_id",
        type=int,
        required=True,
        help="Identifier of the dead-letter entry to requeue",
    )
    dlq_requeue_parser.add_argument(
        "--requeue-seq",
        dest="requeue_seq",
        type=int,
        default=None,
        help=(
            "Optional override for the requeue sequence; defaults to the DLQ entry's value + 1"
        ),
    )

    dlq_purge_parser = dlq_subparsers.add_parser(
        "purge",
        help="Mark a dead-letter entry as quarantined",
    )
    dlq_purge_parser.add_argument(
        "--id",
        dest="letter_id",
        type=int,
        required=True,
        help="Identifier of the dead-letter entry to quarantine",
    )

    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    serve_runner: ServeRunner | None = None,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    configure_structured_logging(level="INFO", force=True)

    try:
        overrides = _compose_overrides(args.overrides or [])
    except ValueError as exc:
        logger.error("Invalid override: %s", exc)
        return 2

    try:
        settings = KernelSettings.load(
            config_path=args.config,
            overrides=overrides or None,
        )
    except Exception as exc:  # pragma: no cover - defensive guard
        logger.error("Failed to load kernel configuration: %s", exc)
        return 2

    # Cast settings to Any to avoid static analyzers interpreting nested models as FieldInfo
    configure_structured_logging(
        level=cast(Any, settings).server.log_level,
        sensitive_keys=cast(Any, settings).telemetry.log_sensitive_keys,
        mask=cast(Any, settings).telemetry.log_mask,
        force=True,
    )

    if args.command is None:
        parser.print_help()
        return 1

    if args.command == "serve":
        options = _resolve_serve_options(args, settings)
        configure_structured_logging(
            level=options.log_level,
            sensitive_keys=settings.telemetry.log_sensitive_keys,
            mask=settings.telemetry.log_mask,
            force=True,
        )
        runner = serve_runner or _default_serve_runner
        result = runner(settings, options)
        return int(result) if result is not None else 0

    if args.command == "migrate":
        database_path = args.database or _get_database_path(settings)
        migrations_dir = args.migrations_dir
        try:
            results = apply_migrations(
                database_path,
                migrations_path=migrations_dir,
                dry_run=getattr(args, "dry_run", False),
                logger=logger,
            )
        except MigrationError as exc:
            logger.error("Migration failed: %s", exc)
            return 2

        _report_migration_results(
            results,
            dry_run=getattr(args, "dry_run", False),
        )
        return 0

    if args.command == "schema":
        if getattr(args, "schema_command", None) is None:
            parser.print_help()
            return 1
        database_path = args.database or _get_database_path(settings)
        return _handle_schema_command(database_path, args)

    if args.command == "provision":
        database_path = args.database or _get_database_path(settings)
        timestamp = _resolve_timestamp(args.provisioned_ts)
        try:
            _provision_device(
                database_path,
                settings=settings,
                tenant_id=args.tenant_id,
                space_id=args.space_id,
                device_id=args.device_id,
                mls_group_id=args.mls_group_id,
                key_version=args.key_version,
                verify_key=args.verify_key,
                provisioned_ts=timestamp,
            )
        except Exception as exc:  # pragma: no cover - defensive guard
            logger.error("Provisioning failed: %s", exc)
            return 2
        logger.info(
            "Provisioned device %s for tenant %s space %s with key version %s",
            args.device_id,
            args.tenant_id,
            args.space_id,
            args.key_version,
        )
        return 0

    if args.command == "key":
        if getattr(args, "key_command", None) is None:
            logger.error("`key` requires a sub-command")
            return 1
        database_path = args.database or _get_database_path(settings)
        return _handle_key_command(database_path, args, settings=settings)

    if args.command == "snapshot":
        if getattr(args, "snapshot_command", None) is None:
            logger.error("`snapshot` requires a sub-command")
            return 1
        database_path = args.database or _get_database_path(settings)
        return _handle_snapshot_command(
            database_path,
            args,
            settings=settings,
        )

    if args.command == "replay":
        database_path = args.database or _get_database_path(settings)
        return _handle_replay_command(
            database_path,
            args,
            settings=settings,
        )

    if args.command == "dlq":
        if getattr(args, "dlq_command", None) is None:
            logger.error("`dlq` requires a sub-command")
            return 1
        database_path = args.database or _get_database_path(settings)
        return _handle_dlq_command(database_path, args)

    logger.error("`%s` command is not implemented yet", args.command)
    return 2


def _resolve_serve_options(
    args: argparse.Namespace, settings: KernelSettings
) -> ServeOptions:
    server_settings = settings.server
    host = args.host or server_settings.host
    port = args.port or server_settings.port
    log_level = (args.log_level or server_settings.log_level).lower()
    timeout = (
        args.graceful_timeout
        if args.graceful_timeout is not None
        else server_settings.timeout_graceful_shutdown
    )
    return ServeOptions(
        host=host,
        port=port,
        log_level=log_level,
        timeout_graceful_shutdown=timeout,
    )


def _default_serve_runner(settings: KernelSettings, options: ServeOptions) -> int:
    run_kernel(
        settings=settings,
        host=options.host,
        port=options.port,
        log_level=options.log_level,
        timeout_graceful_shutdown=options.timeout_graceful_shutdown,
    )
    return 0


def _get_database_path(settings: KernelSettings) -> Path:
    """Helper to access settings.database.path while avoiding static type errors.

    Some static analyzers see `settings.database` as a pydantic FieldInfo rather than
    the resolved settings model; we cast to Any to satisfy type checking.
    """
    return cast(Any, settings).database.path  # type: ignore[attr-defined]


def _compose_overrides(pairs: Sequence[str]) -> dict[str, Any]:
    overrides: dict[str, Any] = {}
    for pair in pairs:
        path, value = _parse_override_pair(pair)
        _assign_nested_override(overrides, path, value)
    return overrides


def _parse_override_pair(raw: str) -> tuple[list[str], Any]:
    key, sep, value = raw.partition("=")
    if not raw.strip():
        raise ValueError("Override values must be non-empty")
    if not sep:
        raise ValueError("Override must be in KEY=VALUE form")
    path = [segment.strip() for segment in key.split(".") if segment.strip()]
    if not path:
        raise ValueError("Override key must not be empty")
    return path, _coerce_override_value(value)


def _assign_nested_override(
    target: MutableMapping[str, Any],
    path: Sequence[str],
    value: Any,
) -> None:
    current: MutableMapping[str, Any] = target
    for key in path[:-1]:
        existing = current.get(key)
        if existing is None or not isinstance(existing, MutableMapping):
            next_level: dict[str, Any] = {}
            current[key] = next_level
            current = next_level
        else:
            current = cast(MutableMapping[str, Any], existing)
    current[path[-1]] = value


def _coerce_override_value(raw: str) -> Any:
    stripped = raw.strip()
    if not stripped:
        return ""
    try:
        value = yaml.safe_load(stripped)
    except (yaml.YAMLError, ValueError):
        return stripped
    return stripped if value is None else value


def _report_migration_results(
    results: Sequence[MigrationResult],
    *,
    dry_run: bool,
) -> None:
    pending = 0
    applied = 0

    for result in results:
        if result.action == "applied":
            applied += 1
            logger.info("Applied migration %s", result.version)
        elif result.action == "skipped":
            logger.info("Skipping migration %s (already applied)", result.version)
        elif result.action == "pending":
            pending += 1
            logger.info("Pending migration %s", result.version)

    if dry_run:
        logger.info("Dry run complete: %d migration(s) pending", pending)
    elif applied == 0:
        logger.info("Database already up to date; no migrations applied.")


def _provision_device(
    database_path: Path,
    *,
    settings: KernelSettings,
    tenant_id: str,
    space_id: str,
    device_id: str,
    mls_group_id: str,
    key_version: str,
    verify_key: str,
    provisioned_ts: str,
) -> None:
    """Provision a device with initial key (backward compatible with new schema)."""
    configure_pool(database_path)
    ledger = ProvisioningLedger()
    try:
        # Register device bindings
        ledger.register(
            ProvisionedDevice(
                device_id=device_id,
                tenant_id=tenant_id,
                space_id=space_id,
                mls_group_id=mls_group_id,
                provisioned_ts=provisioned_ts,
            )
        )
        # Add initial key in ACTIVE state
        ledger.add_key(
            DeviceKey(
                device_id=device_id,
                key_version=key_version,
                verify_key=verify_key,
                key_state="ACTIVE",
                registered_ts=provisioned_ts,
                activated_ts=provisioned_ts,
            )
        )
    finally:
        shutdown_pool()


def _handle_key_command(
    database_path: Path,
    args: argparse.Namespace,
    *,
    settings: KernelSettings,
) -> int:
    """Handle key management subcommands."""
    configure_pool(database_path)
    ledger = ProvisioningLedger()
    try:
        command = args.key_command

        if command == "add":
            timestamp = _resolve_timestamp(args.registered_ts)
            key = DeviceKey(
                device_id=args.device_id,
                key_version=args.key_version,
                verify_key=args.verify_key,
                key_state=args.key_state,
                registered_ts=timestamp,
                activated_ts=timestamp if args.key_state == "ACTIVE" else None,
            )
            ledger.add_key(key)
            logger.info(
                "Added key version %s for device %s (state=%s)",
                args.key_version,
                args.device_id,
                args.key_state,
            )
            return 0

        if command == "activate":
            # Calculate grace window expiry
            grace_hours = (
                args.grace_hours or settings.security.key_rotation_grace_window_hours
            )
            if grace_hours > settings.security.key_rotation_max_grace_hours:
                logger.error(
                    "Grace window %d hours exceeds maximum %d hours",
                    grace_hours,
                    settings.security.key_rotation_max_grace_hours,
                )
                return 2

            from datetime import datetime, timedelta, timezone

            activated_ts = datetime.now(timezone.utc)
            grace_expires_ts = activated_ts + timedelta(hours=grace_hours)

            # Get the key to activate
            keys = ledger.get_keys(args.device_id)
            target_key = next(
                (k for k in keys if k.key_version == args.key_version), None
            )
            if target_key is None:
                logger.error(
                    "Key version %s not found for device %s",
                    args.key_version,
                    args.device_id,
                )
                return 2

            if target_key.key_state == "REVOKED":
                logger.error(
                    "Cannot activate revoked key version %s",
                    args.key_version,
                )
                return 2

            with connection_scope() as conn:
                # Transition all ACTIVE keys to ROTATING with grace window
                active_keys = [k for k in keys if k.key_state == "ACTIVE"]
                for old_key in active_keys:
                    rotated = replace(
                        old_key,
                        key_state="ROTATING",
                        rotated_ts=activated_ts.isoformat(timespec="seconds"),
                        grace_expires_ts=grace_expires_ts.isoformat(timespec="seconds"),
                    )
                    ledger.add_key(rotated, connection=conn)
                    logger.info(
                        "Transitioned key version %s to ROTATING (grace expires: %s)",
                        old_key.key_version,
                        grace_expires_ts.isoformat(timespec="seconds"),
                    )

                # Activate the new key
                activated = replace(
                    target_key,
                    key_state="ACTIVE",
                    activated_ts=activated_ts.isoformat(timespec="seconds"),
                )
                ledger.add_key(activated, connection=conn)
                conn.commit()

            logger.info(
                "Activated key version %s for device %s",
                args.key_version,
                args.device_id,
            )
            return 0

        if command == "revoke":
            keys = ledger.get_keys(args.device_id)
            target_key = next(
                (k for k in keys if k.key_version == args.key_version), None
            )
            if target_key is None:
                logger.error(
                    "Key version %s not found for device %s",
                    args.key_version,
                    args.device_id,
                )
                return 2

            from datetime import datetime, timezone

            revoked_ts = datetime.now(timezone.utc).isoformat(timespec="seconds")

            revoked = replace(
                target_key,
                key_state="REVOKED",
                revoked_ts=revoked_ts,
                revocation_reason=args.revocation_reason,
            )
            ledger.add_key(revoked)
            logger.warning(
                "REVOKED key version %s for device %s (reason: %s)",
                args.key_version,
                args.device_id,
                args.revocation_reason,
            )
            return 0

        if command == "list":
            states = None if args.key_state == "ALL" else [args.key_state]
            keys = ledger.get_keys(args.device_id, states=states)

            if not keys:
                logger.info("No keys found for device %s", args.device_id)
                return 0

            logger.info("Keys for device %s:", args.device_id)
            for key in keys:
                grace_info = (
                    f" grace_expires={key.grace_expires_ts}"
                    if key.grace_expires_ts
                    else ""
                )
                revoke_info = (
                    f" reason={key.revocation_reason}" if key.revocation_reason else ""
                )
                logger.info(
                    "  • %s [%s] registered=%s activated=%s%s%s",
                    key.key_version,
                    key.key_state,
                    key.registered_ts,
                    key.activated_ts or "-",
                    grace_info,
                    revoke_info,
                )
            return 0

        if command == "expire-grace":
            from datetime import datetime, timezone

            now_ts = datetime.now(timezone.utc).isoformat(timespec="seconds")

            # Query all ROTATING keys
            with connection_scope() as conn:
                rows = conn.execute(
                    "SELECT device_id, key_version, grace_expires_ts FROM st_device_keys "
                    "WHERE key_state='ROTATING' AND grace_expires_ts IS NOT NULL AND grace_expires_ts < ?",
                    (now_ts,),
                ).fetchall()

                if not rows:
                    logger.info("No expired ROTATING keys found")
                    return 0

                expired_count = len(rows)
                logger.info("Found %d expired ROTATING key(s)", expired_count)

                if args.dry_run:
                    for row in rows:
                        logger.info(
                            "  [DRY-RUN] Would expire: device=%s key_version=%s grace_expired=%s",
                            row["device_id"],
                            row["key_version"],
                            row["grace_expires_ts"],
                        )
                    return 0

                # Transition expired keys to REVOKED
                for row in rows:
                    keys = ledger.get_keys(row["device_id"])
                    target_key = next(
                        (k for k in keys if k.key_version == row["key_version"]), None
                    )
                    if target_key:
                        revoked = replace(
                            target_key,
                            key_state="REVOKED",
                            revoked_ts=now_ts,
                            revocation_reason="Grace window expired",
                        )
                        ledger.add_key(revoked, connection=conn)
                        logger.info(
                            "Expired key: device=%s key_version=%s",
                            row["device_id"],
                            row["key_version"],
                        )
                conn.commit()

            logger.info("Expired %d ROTATING key(s)", expired_count)
            return 0

        logger.error("`key %s` command is not implemented yet", command)
        return 2
    except (KeyError, ValueError) as exc:
        logger.error("Key command failed: %s", exc)
        return 2
    finally:
        shutdown_pool()


def _handle_schema_command(
    database_path: Path,
    args: argparse.Namespace,
) -> int:
    configure_pool(database_path)
    registry = SchemaRegistry()
    try:
        registry.load()
        command = args.schema_command
        if command == "register":
            record = SchemaRecord(
                uri=args.uri,
                version=args.version,
                sha256=args.sha256,
                status=args.status,
            )
            stored = registry.register(record)
            logger.info(
                "Registered schema %s@%s with status %s",
                stored.uri,
                stored.version,
                stored.status,
            )
            if args.activate or stored.status == "ACTIVE":
                stored = registry.promote(stored.uri, stored.version)
                logger.info(
                    "Promoted schema %s@%s to ACTIVE",
                    stored.uri,
                    stored.version,
                )
            _log_schema_state(registry, stored.uri)
            return 0

        if command == "promote":
            promoted = registry.promote(args.uri, args.version)
            logger.info(
                "Promoted schema %s@%s to ACTIVE",
                promoted.uri,
                promoted.version,
            )
            _log_schema_state(registry, promoted.uri)
            return 0

        if command == "block":
            blocked = registry.block(
                args.uri,
                args.version,
                operator_id=args.operator_id,
                reason=args.reason,
            )
            logger.warning(
                "BLOCKED schema %s@%s (operator=%s, reason=%s)",
                blocked.uri,
                blocked.version,
                blocked.operator_id,
                blocked.blocked_reason,
            )
            _log_schema_state(registry, blocked.uri)
            return 0

        if command == "audit":
            records = registry.get_audit_trail(
                uri=args.uri,
                version=args.version,
                status=args.status,
            )

            if not records:
                logger.info("No matching schema records found")
                return 0

            logger.info("Schema Audit Trail")
            logger.info("=" * 60)

            for record in records:
                logger.info("")
                logger.info("URI: %s", record.uri)
                logger.info("Version: %s", record.version)
                logger.info("Status: %s", record.status)
                logger.info("SHA256: %s", record.sha256)

                if record.operator_id:
                    logger.info("")
                    logger.info("Audit Metadata:")
                    logger.info("  Operator: %s", record.operator_id)
                    logger.info(
                        "  Blocked At: %s", record.blocked_ts or "(not blocked)"
                    )
                    logger.info("  Reason: %s", record.blocked_reason or "(no reason)")
                    logger.info("  Unblocked At: %s", record.unblocked_ts or "(never)")
                else:
                    logger.info("  (No audit trail - schema never blocked)")

                logger.info("-" * 60)

            return 0

        logger.error("`schema %s` command is not implemented yet", command)
        return 2
    except (KeyError, ValueError) as exc:
        logger.error("Schema command failed: %s", exc)
        return 2
    finally:
        shutdown_pool()


def _log_schema_state(registry: SchemaRegistry, uri: str) -> None:
    records = sorted(
        registry.records_for_uri(uri),
        key=lambda record: record.version,
    )
    if not records:
        logger.info("No schema records registered for %s", uri)
        return
    logger.info("Current registry state for %s:", uri)
    for record in records:
        logger.info("  • %s@%s -> %s", record.uri, record.version, record.status)


def _resolve_timestamp(raw: str | None) -> str:
    if raw is None:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")
    value = raw.strip()
    if not value:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:  # pragma: no cover - defensive guard
        raise ValueError(f"Invalid ISO-8601 timestamp: {value}") from exc
    return value


def _build_operational_instrumentation(
    settings: KernelSettings,
) -> tuple[MetricsExporter, ObservabilityEmitter]:
    emitter = ObservabilityEmitter()
    metrics = MetricsExporter(
        namespace=settings.telemetry.metrics_namespace,
        observability_emitter=emitter,
    )
    return metrics, emitter


def _handle_snapshot_command(
    database_path: Path,
    args: argparse.Namespace,
    *,
    settings: KernelSettings,
) -> int:
    if getattr(args, "snapshot_command", None) != "create":
        logger.error(
            "`snapshot %s` command is not implemented yet",
            args.snapshot_command,
        )
        return 2

    metrics, observability = _build_operational_instrumentation(settings)
    scheduler = SnapshotScheduler(
        database_path=database_path,
        metrics=metrics,
        observability=observability,
    )

    try:
        manifest = scheduler.create_snapshot(
            output_dir=args.output_dir,
            snapshot_id=args.snapshot_id,
            dry_run=args.dry_run,
        )
    except SnapshotError as exc:
        logger.error("Snapshot creation failed: %s", exc)
        return 2

    if args.dry_run:
        logger.info(
            "Dry-run snapshot planned at watermark %s (snapshot_id=%s)",
            manifest.watermark,
            manifest.snapshot_id,
        )
        return 0

    logger.info(
        "Snapshot %s captured at watermark %s (begin=%s commit=%s)",
        manifest.snapshot_id,
        manifest.watermark,
        manifest.begin_position,
        manifest.commit_position,
    )
    if manifest.artifact_path:
        logger.info(
            "Snapshot artifact stored at %s",
            manifest.artifact_path.as_posix(),
        )
    if manifest.manifest_path:
        logger.info(
            "Snapshot manifest stored at %s",
            manifest.manifest_path.as_posix(),
        )
    return 0


def _handle_replay_command(
    database_path: Path,
    args: argparse.Namespace,
    *,
    settings: KernelSettings,
) -> int:
    metrics, observability = _build_operational_instrumentation(settings)
    registry = SchemaRegistry()
    replayer = Replayer(
        schema_registry=registry,
        metrics=metrics,
        observability=observability,
    )

    configure_pool(database_path)
    try:
        result = replayer.run(
            from_position=args.from_position,
            tenant_id=args.tenant_id,
            space_id=args.space_id,
            dry_run=args.dry_run,
        )
    except ReplayError as exc:
        logger.error("Replay failed: %s", exc)
        return 2
    finally:
        shutdown_pool()

    logger.info(
        "Replay scanned %s event(s) up to position %s in %.3fs",
        result.processed,
        result.last_position if result.last_position is not None else "-",
        result.duration_seconds,
    )

    if result.parity_failures > 0:
        logger.error(
            "Replay completed with %s parity failure(s)",
            result.parity_failures,
        )
        return 3 if not args.dry_run else 0

    return 0


def _handle_dlq_command(
    database_path: Path,
    args: argparse.Namespace,
) -> int:
    configure_pool(database_path)
    queue = DeadLetterQueue()
    outbox_store = OutboxStore()
    try:
        command = args.dlq_command
        if command == "list":
            limit = args.limit
            if limit <= 0:
                logger.error("limit must be greater than zero")
                return 2
            state = args.state.upper() if args.state else None
            letters = queue.list_pending(
                limit=limit,
                state=state,
                tenant_id=args.tenant,
                space_id=args.space,
                driver=args.driver,
            )
            if not letters:
                logger.info("No dead-letter entries matched the query")
                return 0
            for letter in letters:
                _log_dead_letter(letter)
            return 0

        if command == "requeue":
            letter = queue.get(args.letter_id)
            if letter is None:
                logger.error("Dead-letter entry %s not found", args.letter_id)
                return 2
            if letter.id is None:
                logger.error(
                    "Dead-letter entry %s is missing an identifier",
                    args.letter_id,
                )
                return 2
            if letter.state == "REQUEUED":
                logger.info(
                    "Dead-letter entry %s already marked as REQUEUED",
                    args.letter_id,
                )
                return 0
            if letter.state == "QUARANTINED":
                logger.error(
                    "Dead-letter entry %s is quarantined and cannot be requeued",
                    args.letter_id,
                )
                return 2
            if letter.wal_pos is None:
                logger.error(
                    "Dead-letter entry %s is missing wal_pos; requeue requires an origin watermark",
                    args.letter_id,
                )
                return 2
            new_seq = args.requeue_seq
            if new_seq is None:
                new_seq = letter.requeue_seq + 1
            if new_seq < 0:
                logger.error("requeue_seq must be greater than or equal to zero")
                return 2
            with connection_scope() as connection:
                outbox_store.enqueue(
                    OutboxEntry(
                        id=None,
                        wal_pos=letter.wal_pos,
                        tenant_id=letter.tenant_id,
                        space_id=letter.space_id,
                        driver=letter.driver,
                        op_kind=letter.op_kind,
                        payload=letter.payload,
                        fingerprint=letter.fingerprint,
                        requeue_seq=new_seq,
                        retries=0,
                        last_error=letter.reason,
                    ),
                    connection=connection,
                )
                queue.mark_requeued(
                    letter.id,
                    requeue_seq=new_seq,
                    connection=connection,
                )
                connection.commit()
            logger.info(
                "Requeued dead-letter entry %s for driver %s with requeue_seq=%s",
                letter.id,
                letter.driver,
                new_seq,
            )
            return 0

        if command == "purge":
            if not queue.purge(args.letter_id):
                logger.error("Dead-letter entry %s not found", args.letter_id)
                return 2
            logger.info(
                "Marked dead-letter entry %s as QUARANTINED",
                args.letter_id,
            )
            return 0

        logger.error("`dlq %s` command is not implemented yet", command)
        return 2
    finally:
        shutdown_pool()


def _log_dead_letter(letter: DeadLetter) -> None:
    logger.info(
        "DLQ entry %s [%s] tenant=%s space=%s driver=%s op=%s retries=%s requeue_seq=%s wal_pos=%s first_failure=%s last_failure=%s fingerprint=%s reason=%s payload_bytes=%s",
        letter.id,
        letter.state,
        letter.tenant_id,
        letter.space_id,
        letter.driver,
        letter.op_kind,
        letter.retries,
        letter.requeue_seq,
        letter.wal_pos if letter.wal_pos is not None else "-",
        letter.first_failure_ts,
        letter.last_failure_ts,
        letter.fingerprint,
        letter.reason,
        len(letter.payload),
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
