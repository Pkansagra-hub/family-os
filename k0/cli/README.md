# CLI Module

## Overview

The **cli** module provides `k0ctl`, the administrative command-line interface for orchestrating the K0 kernel runtime. It serves as the unified control surface for operational tasks including server management, database migrations, device provisioning, schema registry operations, key rotation, snapshots, replay, and dead-letter queue management.

## Purpose

- **Server Management**: Start the embedded FastAPI/ASGI server with configurable parameters
- **Database Operations**: Apply schema migrations, create snapshots, replay WAL events
- **Device Lifecycle**: Provision devices with verification keys and manage key rotation
- **Schema Registry**: Register, promote, block, and audit schema versions
- **Observability**: DLQ inspection, snapshot creation, and operational diagnostics
- **Configuration**: Override kernel settings via YAML config or command-line flags

## Architecture

The CLI is built on Python's `argparse` with a subcommand architecture. Each command integrates with specific K0 subsystems:

```
k0ctl → Command Parser → Subsystem Integration
                ↓
        [serve, migrate, provision, schema, key, snapshot, replay, dlq]
```

## Commands

### 1. `serve` - Run FastAPI Server

Start the kernel's FastAPI/ASGI server with Uvicorn.

**Usage:**

```bash
k0ctl serve [--host HOST] [--port PORT] [--log-level LEVEL] [--graceful-timeout SECONDS]
```

**Options:**

- `--host` - Bind address (default from config: `server.host`)
- `--port` - Bind port (default from config: `server.port`)
- `--log-level` - Log verbosity: critical, error, warning, info, debug, trace
- `--graceful-timeout` - Shutdown timeout in seconds

**Example:**

```bash
k0ctl --config config/kernel.yaml serve --host 0.0.0.0 --port 8080 --log-level debug
```

### 2. `migrate` - Apply Database Migrations

Apply SQL schema migrations to the storage layer.

**Usage:**

```bash
k0ctl migrate [--database PATH] [--migrations-dir PATH] [--dry-run]
```

**Options:**

- `--database` - Override database path (default from config)
- `--migrations-dir` - Path to SQL migrations (default: `k0/contracts/sql/migrations`)
- `--dry-run` - Preview migrations without applying changes

**Example:**

```bash
k0ctl migrate --database k0_runtime.sqlite3 --dry-run
k0ctl migrate  # Apply pending migrations
```

### 3. `provision` - Register Device Binding

Provision a device in the ledger with initial verification key.

**Usage:**

```bash
k0ctl provision --tenant TENANT --space SPACE --device DEVICE --mls-group GROUP \
                --key-version VERSION --verify-key KEY [--ts TIMESTAMP] [--database PATH]
```

**Options:**

- `--tenant` - Tenant identifier (required)
- `--space` - Space identifier (required)
- `--device` - Device identifier (required)
- `--mls-group` - MLS group ID (required)
- `--key-version` - Key version string (required)
- `--verify-key` - URL-safe base64 public verification key (required)
- `--ts` - ISO 8601 timestamp (defaults to current UTC)
- `--database` - Override database path

**Example:**

```bash
k0ctl provision --tenant tenant_123 --space space_456 --device device_789 \
                --mls-group mls_abc --key-version v1 --verify-key "base64key=="
```

### 4. `schema` - Schema Registry Management

Manage schema lifecycle (register, promote, block, audit).

#### 4.1 `schema register` - Register Schema Version

**Usage:**

```bash
k0ctl schema register --uri URI --version VERSION --sha256 DIGEST [--status STATUS] [--activate]
```

**Options:**

- `--uri` - Schema URI (e.g., `envelope.schema.json`)
- `--version` - Semantic version (e.g., `1.0.0`)
- `--sha256` - Canonical payload digest
- `--status` - Initial status: REGISTERED (default) or ACTIVE
- `--activate` - Promote to ACTIVE immediately after registration

#### 4.2 `schema promote` - Promote to ACTIVE

**Usage:**

```bash
k0ctl schema promote --uri URI --version VERSION
```

#### 4.3 `schema block` - Emergency Block

**Usage:**

```bash
k0ctl schema block --uri URI --version VERSION --operator OPERATOR --reason REASON
```

**Options:**

- `--operator` - Operator ID/email (audit trail requirement)
- `--reason` - Justification for block (audit trail requirement)

#### 4.4 `schema audit` - View Audit Trail

**Usage:**

```bash
k0ctl schema audit [--uri URI] [--version VERSION] [--status STATUS]
```

**Example:**

```bash
k0ctl schema register --uri envelope.schema.json --version 1.1.0 --sha256 abc123 --activate
k0ctl schema audit --uri envelope.schema.json
k0ctl schema block --uri envelope.schema.json --version 1.0.0 --operator admin@example.com --reason "Security vulnerability"
```

### 5. `key` - Key Rotation Management

Manage device verification keys with rotation support (ADR-001).

#### 5.1 `key add` - Register New Key

**Usage:**

```bash
k0ctl key add --device DEVICE --key-version VERSION --verify-key KEY [--state STATE] [--ts TIMESTAMP]
```

**Options:**

- `--device` - Device identifier
- `--key-version` - Version identifier for key
- `--verify-key` - URL-safe base64 public key
- `--state` - Initial state: PENDING (default) or ACTIVE
- `--ts` - Registration timestamp (ISO 8601)

#### 5.2 `key activate` - Activate Key with Grace Window

**Usage:**

```bash
k0ctl key activate --device DEVICE --key-version VERSION [--grace-hours HOURS]
```

**Behavior:**

- Transitions specified key to ACTIVE
- Moves existing ACTIVE keys to ROTATING with grace expiry
- Grace window defaults to `settings.security.key_rotation_grace_window_hours`

#### 5.3 `key revoke` - Revoke Key Immediately

**Usage:**

```bash
k0ctl key revoke --device DEVICE --key-version VERSION --reason REASON
```

**Options:**

- `--reason` - Revocation justification (audit trail requirement)

#### 5.4 `key list` - List Device Keys

**Usage:**

```bash
k0ctl key list --device DEVICE [--state STATE]
```

**Options:**

- `--state` - Filter by state: PENDING, ACTIVE, ROTATING, REVOKED, ALL (default)

#### 5.5 `key expire-grace` - Transition Expired ROTATING Keys

**Usage:**

```bash
k0ctl key expire-grace [--dry-run]
```

**Behavior:**

- Finds ROTATING keys past grace_expires_ts
- Transitions them to REVOKED with reason "Grace window expired"

**Example:**

```bash
# Add pending key
k0ctl key add --device device_123 --key-version v2 --verify-key "newkey=="

# Activate new key (old ACTIVE keys → ROTATING with 72h grace)
k0ctl key activate --device device_123 --key-version v2 --grace-hours 72

# List all keys
k0ctl key list --device device_123

# Revoke compromised key
k0ctl key revoke --device device_123 --key-version v1 --reason "Security incident"

# Expire grace windows
k0ctl key expire-grace --dry-run  # Preview
k0ctl key expire-grace             # Execute
```

### 6. `snapshot` - WAL Snapshot Management

Create snapshots with BEGIN/COMMIT WAL markers.

#### 6.1 `snapshot create` - Create Snapshot

**Usage:**

```bash
k0ctl snapshot create [--output-dir DIR] [--snapshot-id ID] [--dry-run]
```

**Options:**

- `--output-dir` - Directory for artifacts (default: `./snapshots`)
- `--snapshot-id` - Custom snapshot identifier (defaults to autogenerated)
- `--dry-run` - Plan without writing artifacts or WAL markers

**Example:**

```bash
k0ctl snapshot create --output-dir /backups/snapshots --dry-run
k0ctl snapshot create --output-dir /backups/snapshots --snapshot-id snapshot_2024_01_15
```

### 7. `replay` - WAL Replay & Validation

Replay WAL entries to validate parity with projected state.

**Usage:**

```bash
k0ctl replay [--from-pos POSITION] [--tenant TENANT] [--space SPACE] [--dry-run]
```

**Options:**

- `--from-pos` - Replay entries with WAL position > value (default: 0)
- `--tenant` - Restrict replay to tenant identifier
- `--space` - Restrict replay to space identifier
- `--dry-run` - Validate parity without mutating state

**Example:**

```bash
k0ctl replay --from-pos 1000 --tenant tenant_123 --dry-run
k0ctl replay --from-pos 5000  # Execute replay
```

### 8. `dlq` - Dead-Letter Queue Management

Inspect and manage failed outbox entries.

#### 8.1 `dlq list` - List DLQ Entries

**Usage:**

```bash
k0ctl dlq list [--limit N] [--state STATE] [--tenant TENANT] [--space SPACE] [--driver DRIVER]
```

**Options:**

- `--limit` - Max entries to display (default: 20)
- `--state` - Filter by state: PENDING (default), REQUEUED, QUARANTINED, ALL
- `--tenant` - Restrict to tenant identifier
- `--space` - Restrict to space identifier
- `--driver` - Restrict to driver alias

#### 8.2 `dlq requeue` - Requeue Entry

**Usage:**

```bash
k0ctl dlq requeue --id ID [--requeue-seq SEQ]
```

**Options:**

- `--id` - Dead-letter entry identifier (required)
- `--requeue-seq` - Override requeue sequence (defaults to entry's value + 1)

#### 8.3 `dlq purge` - Quarantine Entry

**Usage:**

```bash
k0ctl dlq purge --id ID
```

**Example:**

```bash
# List pending failures
k0ctl dlq list --limit 50 --state PENDING

# Requeue specific entry
k0ctl dlq requeue --id 42

# Quarantine unrecoverable entry
k0ctl dlq purge --id 43
```

## Global Options

**`--config PATH`**

Path to kernel YAML configuration file (defaults to `config/kernel.yaml`).

**`--set KEY=VALUE`**

Override configuration values using dotted paths. Can be repeated.

**Examples:**

```bash
k0ctl --config config/prod.yaml --set server.port=9090 --set telemetry.metrics_namespace=k0_prod serve
k0ctl --set database.path=test.sqlite3 migrate
```

## Configuration Integration

The CLI loads settings from:

1. Default config file (`config/kernel.yaml`)
2. Custom config via `--config`
3. Overrides via `--set` (highest priority)

Settings are parsed into `KernelSettings` (Pydantic model) with validation.

## Entry Point

The CLI is invoked via:

```bash
python -m k0.cli.k0ctl [command] [options]
```

Or via entry point (if installed):

```bash
k0ctl [command] [options]
```

## Implementation Details

### Functions

**`build_parser()`**

Constructs the `argparse.ArgumentParser` with all subcommands and options.

**`main(argv, serve_runner)`**

- Parses arguments
- Loads kernel settings with overrides
- Configures structured logging
- Routes to command handler
- Returns exit code (0=success, 1=usage error, 2=runtime error, 3=validation failure)

**Command Handlers:**

- `_default_serve_runner()` - Start kernel server
- `_handle_schema_command()` - Schema registry operations
- `_handle_key_command()` - Key rotation lifecycle
- `_handle_snapshot_command()` - Snapshot creation
- `_handle_replay_command()` - WAL replay
- `_handle_dlq_command()` - DLQ management
- `_provision_device()` - Device provisioning

### Helpers

- `_compose_overrides()` - Parse `--set` flags into nested dict
- `_resolve_serve_options()` - Merge CLI args with config
- `_resolve_timestamp()` - Parse ISO 8601 timestamps or default to now
- `_get_database_path()` - Extract database path from settings
- `_log_schema_state()` - Display schema registry state
- `_log_dead_letter()` - Format DLQ entry for logging

## Integration Points

### With Kernel Runtime

```python
from k0.kernel.main import run as run_kernel
from k0.kernel.config import KernelSettings

settings = KernelSettings.load(config_path="config/kernel.yaml")
run_kernel(settings, host="0.0.0.0", port=8080)
```

### With Storage Layer

```python
from k0.uow.connection_pool import configure_pool, connection_scope
from k0.storage.provisioning import ProvisioningLedger

configure_pool(database_path)
ledger = ProvisioningLedger()
ledger.register(device)
```

### With Schema Registry

```python
from k0.gate.schema_registry import SchemaRegistry, SchemaRecord

registry = SchemaRegistry()
registry.load()
registry.register(SchemaRecord(uri="schema.json", version="1.0.0", sha256="..."))
```

### With Observability

```python
from k0.obs import MetricsExporter, ObservabilityEmitter, configure_structured_logging

configure_structured_logging(level="INFO", force=True)
metrics = MetricsExporter(namespace="k0")
```

## Error Handling

- **Exit Code 0**: Success
- **Exit Code 1**: Usage error (missing required arguments, invalid command)
- **Exit Code 2**: Runtime error (migration failure, provisioning error, database error)
- **Exit Code 3**: Validation failure (replay parity failures)

Errors are logged via structured logging with context (command, parameters, exception details).

## Testing

See `tests/k0/cli/` for:

- Command parsing validation
- Configuration override logic
- Integration with subsystems (mocked or real)
- Error handling scenarios

## Related Modules

- **k0.kernel**: Runtime server and settings
- **k0.automation.migrate**: SQL migration engine
- **k0.gate.schema_registry**: Schema lifecycle management
- **k0.storage**: Provisioning, snapshots, DLQ, outbox
- **k0.uow**: Connection pooling
- **k0.obs**: Structured logging, metrics, tracing
- **k0.qos**: Scheduler (indirectly via kernel)
