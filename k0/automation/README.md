# K0 Automation Infrastructure

> **Philosophy**: Automation must be deterministic, observable, CI-gated, and developer-friendly.

---

## Overview

This directory contains K0's automation tooling for infrastructure-as-code patterns:

- **Contract Governance**: Automatic schema validation, breaking change detection, SemVer enforcement
- **Database Operations**: Migration management, rollback support, data integrity validation
- **Documentation**: API docs generation, specification rendering, cross-reference validation
- **Security & Compliance**: Threat scenario verification, telemetry coverage validation
- **Observability**: Dashboard generation, alert rule synthesis, SLO-driven monitoring

---

## Current Tools

### Contract Management ✅

#### `compute_contract_checksums.py`
Maintains a registry of contract versions with SHA256 checksums.

**Usage**:
```bash
python -m k0.automation.compute_contract_checksums --registry VERSION --check
```

**Features**:
- Deterministic contract versioning
- Prevents accidental contract changes
- CI integration for pre-merge validation

---

#### `lint_schemas.py`
Validates JSON Schema, OpenAPI, and AsyncAPI specifications with orphan detection and cross-reference validation.

**Usage**:
```bash
# Basic validation
python -m k0.automation.lint_schemas

# With orphan detection (default enabled)
python -m k0.automation.lint_schemas --check-orphans

# CI mode: fail on any errors or warnings
python -m k0.automation.lint_schemas --check

# Verbose diagnostics
python -m k0.automation.lint_schemas --verbose

# Custom paths
python -m k0.automation.lint_schemas --schema-dir k0/contracts/jsonschema --openapi k0/contracts/openapi.k0.yaml
```

**Features**:
- ✅ JSON Schema validation (draft-7 compliance)
- ✅ OpenAPI 3.1.0 validation
- ✅ AsyncAPI 2.6.0 validation
- ✅ **Orphan detection**: Identifies unreferenced schemas in jsonschema/ directory
- ✅ **Cross-reference validation**: Resolves internal (#/) and file (./) `$ref` pointers
- ✅ **Severity grouping**: Organizes errors by ERROR/WARNING/INFO levels
- ✅ **Fix suggestions**: Actionable remediation steps for each error
- ✅ 25 comprehensive tests (100% passing)

**Exit Codes**:
- `0` — All schemas valid
- `1` — Validation errors found (or warnings in `--check` mode)

**Current K0 Contracts Status**:
- 11 JSON schemas in `k0/contracts/jsonschema/`
- All schemas referenced in OpenAPI or AsyncAPI
- 0 orphaned schemas detected
- All references resolve successfully

**Design Notes** (Milestone C.1.1):
- Orphan detection works with both real project structure and test fixtures
- Cross-reference validation supports both internal (#/path) and file (./jsonschema/schema.json) references
- ValidationMessage class provides structured error reporting for CI integration
- Severity grouping enables progressive error handling (fail on ERROR only, warn on WARNING)

**Test Coverage**: 25 tests

- ValidationMessage class: Creation, formatting, equality testing
- Orphan detection: No orphans, with orphans, all orphans scenarios
- Cross-reference validation: Valid YAML, invalid YAML, missing internal references
- Severity grouping: Empty, single severity, mixed severities
- Integration tests: Valid contracts, errors+warnings, orphan toggle
- Real YAML/JSON parsing (no mocking)

---

### Database Operations ✅

#### `migrate.py`
Applies database migrations with checksums, rollback support, and telemetry.

**Usage**:
```bash
# Apply forward migrations
python -m k0.automation.migrate --database-path k0_runtime.sqlite3

# Dry-run validation (no database changes)
python -m k0.automation.migrate --database-path k0_runtime.sqlite3 --dry-run

# Rollback to target version
python -m k0.automation.migrate --database-path k0_runtime.sqlite3 --rollback --target-version=0001_baseline

# Dry-run rollback (validate plan without executing)
python -m k0.automation.migrate --database-path k0_runtime.sqlite3 --rollback --target-version=0001_baseline --dry-run
```

**Features**:
- **Forward migrations**: Deterministic execution (checksums prevent corruption), atomic transactions, migration telemetry (Prometheus metrics)
- **Rollback support** ✨ NEW (Milestone B.1):
  - Rollback to any target version: `--rollback --target-version=<version>`
  - Dry-run validation: `--dry-run` shows rollback plan without executing
  - Auto-generated rollback scripts: DDL reversal for CREATE/DROP/ALTER (best-effort)
  - Rollback telemetry: `k0_migration_rollback_total` counter tracks rollback operations
  - Reverse order execution: Migrations rolled back newest-first to respect dependencies
- **Telemetry** ✨ ENHANCED:
  - `k0_migration_duration_seconds` — Histogram of forward/rollback duration
  - `k0_migration_rollback_total` — Counter of rollback operations
  - `k0_migration_status` — Gauge of last operation status (1=success, 0=pending, -1=error)

**Programmatic Usage**:
```python
from pathlib import Path
from k0.automation.migrate import apply_migrations, rollback_migration

# Apply migrations
results = apply_migrations(Path("mydb.db"), dry_run=False)

# Rollback to version 0001
results = rollback_migration(
    Path("mydb.db"),
    target_version="0001_baseline",
    dry_run=False,
)

# Each MigrationResult includes:
# - version: Migration version ID
# - action: "applied", "rolled_back", "skipped", or "pending"
# - checksum: SHA256 of migration script
# - duration_seconds: Time taken (for applied/rolled_back)
# - rollback_script: Auto-generated DOWN script (for rollbacks)
```

**Test Coverage**: 27 comprehensive Ward tests covering:
- Forward migration application and idempotency
- Rollback single and multiple migrations
- Dry-run validation (no-op mode)
- Rollback script generation for CREATE TABLE/INDEX/TRIGGER/ALTER
- Error handling (checksum mismatch, missing versions, cascade constraints)
- Integration scenarios (forward → rollback → reapply cycles)
- Performance baselines (< 1s for typical operations)

**Design Notes**:
- Rollback scripts are auto-generated best-effort; review carefully for complex migrations
- Foreign keys disabled during rollback to prevent cascade issues
- Migration statements reversed in order (newest first) for dependency safety
- Schema_migrations catalog tracks all versions for audit trail

---

### Documentation Generation ✅

#### `generate_api_docs.py`
Generates interactive API documentation from OpenAPI and AsyncAPI specs with Postman collection export.

**Usage**:
```bash
# Generate all docs (HTML, PDF, Postman)
python -m k0.automation.generate_api_docs

# Validate docs are up-to-date
python -m k0.automation.generate_api_docs --check
```

**Outputs**:

- `docs/api/openapi.html` — ReDoc-rendered OpenAPI 3.1.0 specification
- `docs/api/asyncapi.html` — Interactive AsyncAPI 2.6.0 with dark theme UI ✨ NEW (C.1.2)
- `docs/api/openapi.pdf` — PDF export with deterministic timestamps ✨ NEW (C.1.2)
- `docs/api/asyncapi.pdf` — AsyncAPI PDF export with deterministic timestamps ✨ NEW (C.1.2)
- `docs/api/postman/K0_Ports_Collection.json` — Postman v2.1.0 collection ✨ NEW (C.1.2)

**Features** (Milestone C.1.2 ✅ COMPLETE):

- ✅ **AsyncAPI Interactive HTML**: Custom-rendered with channels browser, message viewer, schema explorer (not raw JSON dump)
- ✅ **Postman Collection Auto-Generation**: Converts OpenAPI paths → Postman request items with {{baseUrl}} variables
- ✅ **Deterministic PDF Generation**: Static timestamps (2024-01-01) prevent git churn from dynamic creation dates
- ✅ **Example Integration**: Loads JSON examples from `k0/contracts/jsonschema/examples/` for Postman request bodies
- ✅ **CI Mode**: `--check` validates docs are current without generation (fast pre-commit check)

**Implementation Notes**:

- AsyncAPI HTML includes: Metadata display, channel browser (collapsible list), message schemas with descriptions, dark theme (Tailwind-inspired CSS)
- Postman collection includes: All 11 K0 ports as request items, POST/GET methods with headers, base URL variable configuration for local/staging/prod
- PDFs use fpdf2 with static creation date (`CreationDate: D:20240101000000Z`) for reproducibility
- 21 comprehensive tests covering AsyncAPI rendering, Postman generation, PDF determinism, example loading

**Test Coverage**: 21 tests (100% passing)

- AsyncAPI HTML rendering: Basic spec, multiple channels, not JSON dump, description handling
- OpenAPI HTML rendering: ReDoc integration
- Postman collection: Basic generation, multiple endpoints, base URL variable, example loading
- Deterministic PDFs: Byte-identical output, static timestamps, reproducible across runs
- Example file loading: Empty directory, with files, invalid JSON handling
- Summary line generation: OpenAPI and AsyncAPI formats
- Integration: All files created, check mode validation, idempotent generation

**Related ADRs**:

- ADR-0014: JSON REST API (dual format support: OpenAPI + AsyncAPI)
- ADR-0007: Contract-driven development (schema-first design)

---

#### `verify_docs_sync.py`

Validates documentation consistency between code, storage schema, and API contracts.

**Usage**:

```bash
python -m k0.automation.verify_docs_sync --storage-schema-path k0/storage.sql
```

**Validations**:

- README storage schema matches actual database schema
- API docs reflect current OpenAPI spec
- Contract examples are valid against schemas

**Planned Enhancements** (Milestone C.1):

- Code example validation (snippets match actual code)
- ADR cross-reference checking
- Architecture diagram reference validation

---

### Security & Compliance ✅

#### `verify_security_telemetry.py`

Ensures 100% telemetry coverage for threat scenarios.

**Usage**:

```bash
python -m k0.automation.verify_security_telemetry --telemetry-config k0/telemetry/security_scenarios.yaml
```

**Features**:

- Maps threat scenarios to telemetry events
- Validates coverage is 100% (no blind spots)
- Enforces metric emission standards

---

### Observability & Monitoring ✅

#### `telemetry_renderer.py` (Milestone D.1.1) ✨ NEW

Codifies Grafana dashboards and Prometheus alert rules from SLO definitions. Prevents manual drift and enables deterministic rendering.

**Usage**:

```bash
# Generate dashboards and alert rules from SLO definitions
python -m k0.automation.telemetry_renderer

# Validate artifacts are up-to-date (CI mode)
python -m k0.automation.telemetry_renderer --check

# Verbose output for debugging
python -m k0.automation.telemetry_renderer --verbose
```

**Features** (Milestone D.1.1 ✅ COMPLETE):

- ✅ **SLO-driven rendering**: Loads 13 SLO definitions from `k0/telemetry/slo_definitions.yaml`
- ✅ **Grafana dashboard generation**: Creates deterministic JSON dashboards (one stat panel per SLO)
- ✅ **Prometheus alert rules**: Generates warning/critical alert rules with PromQL expressions
- ✅ **Deterministic rendering**: Checksum-based drift detection (same input → identical output)
- ✅ **--check mode**: Validates artifacts without writing (CI integration)
- ✅ **Color scheme**: macOS-inspired theming (#34C759 success, #FF9F0A warning, #FF3B30 critical)
- ✅ **28 comprehensive tests** (100% passing) covering:
  - SLO definition parsing and validation
  - Dashboard generation with multi-panel layout
  - Alert rule generation with correct PromQL expressions
  - Deterministic checksum verification
  - Drift detection in check mode
  - Idempotent rendering (same output on reruns)

**SLO Definitions** (`k0/telemetry/slo_definitions.yaml`):

13 K0 SLOs including:

- **api_availability** (99.9% target, warning/critical thresholds)
- **command_submit_latency** (P95 100ms target)
- **uow_commit_latency** (P95 50ms target)
- **query_execute_latency** (P95 50ms target)
- **wal_lag** (replication lag 60s target)
- **wal_replica_lag** (standby lag 10s target)
- **outbox_backlog** (pending messages 10k target)
- **replay_throughput** (1000 events/s target)
- **scheduler_quorum** (>= 3 members)
- **zone_health** (100% zones operational)
- **sse_active_subscriptions** (saturation indicator)
- **sse_subscribe_rate** (throughput indicator)
- **bus_dispatch_latency** (P95 10ms target)

**Generated Artifacts**:

- `k0/telemetry/generated/dashboards/k0_slo_dashboard.json` — Grafana dashboard JSON (v10+)
- `k0/telemetry/generated/rules/slo_alerts.yaml` — Prometheus alert rules (validated with promtool)
- Checksum manifests for drift detection

**CI Integration**:

```yaml
# .github/workflows/telemetry-ci.yml
- name: Check telemetry artifacts are up-to-date
  run: |
    python -m k0.automation.telemetry_renderer --check
    promtool check rules k0/telemetry/generated/rules/*.yaml
```

**Design Notes**:

- **No external dependencies**: Uses only stdlib (pathlib, json, yaml), no Jsonnet complexity
- **Extensible SLO format**: YAML definitions support target_percentile (for latency), unit, thresholds
- **Alert expression building**: PromQL expressions generated per metric type (latency, availability, count)
- **Deterministic by design**: Sort keys in JSON/YAML, fixed checksums, no timestamps
- **Drift detection**: File comparison using checksums; --check mode raises on changes

**Related ADRs**:

- ADR-0014: JSON REST API (dual format support: OpenAPI + AsyncAPI)
- ADR-0010: Observability & Monitoring (SLO-driven operations)
- ADR-0002: Deterministic Builds (no timestamps in artifacts)

---

## Planned Tools (Milestones B–F)

### Milestone B — Core Reliability

#### `contract_compatibility_checker.py` (Issue B.2.1) ✅ COMPLETE

Detects breaking changes and enforces SemVer versioning.

**Usage**:

```bash
# Check compatibility between branches
python -m k0.automation.contract_compatibility_checker \
  --base-ref origin/main --head-ref HEAD --fail-on-breaking

# Check single file with versions
python -m k0.automation.contract_compatibility_checker \
  --schema-file k0/contracts/jsonschema/envelope.schema.json \
  --old-version 1.0.0 --new-version 1.1.0
```

**Features**:

- ✅ Breaking change detection (field removal, type changes, enum contraction, required field addition)
- ✅ SemVer enforcement (MAJOR/MINOR/PATCH bumps)
- ✅ N/N+1 compatibility validation (same MAJOR = compatible, different MAJOR = breaking)
- ✅ Git-based schema diffing (efficient PR checking)
- ✅ Human-readable reports with remediation recommendations
- ✅ 27 comprehensive tests covering all change types
- ⏳ CI integration (requires `.github/workflows/contracts-ci.yml` update)

**Design Notes**:

- Recursive JSON schema diffing for nested property detection
- Supports JSON Schema, OpenAPI (YAML), AsyncAPI formats
- Adds `cognitive_trace_id` for observability/tracing
- Based on ADR-0013 (Pipeline Versioning), ADR-0013a (Schema Registry), ADR-0013d (Contract Testing)

**Test Coverage**: 27 tests (100% passing)

- Breaking change detection: Field removal, type changes, required addition, enum removal
- Compatible change detection: Optional field addition, enum addition
- SemVer validation: All version bump combinations
- Report generation: Empty, breaking, compatible changes with recommendations
- Integration tests: Realistic envelope/error schema scenarios

---

### Milestone D — Observability

#### `telemetry_renderer.py` (Issue D.1.1)

Generates Grafana dashboards and Prometheus alert rules from SLO definitions.

**Planned Features**:

- Dashboard generation from `k0/telemetry/slo_definitions.yaml`
- Alert rule synthesis with warning/critical thresholds
- Deterministic rendering (reproducible builds)
- Grafana provisioning manifests

---

### Milestone E — Performance & Chaos

#### `performance_regression_detector.py` (Issue E.1.1)

Detects performance regressions in CI.

**Planned Features**:

- Baseline comparison (main branch vs current PR)
- Configurable thresholds (default 10% degradation)
- Flamegraph generation for deep dives
- CI artifact reporting

---

#### `chaos_scheduler.py` (Issue E.2.1)

Automated chaos experiments with fault injection.

**Planned Features**:

- Chaos profiles: mild, moderate, aggressive
- Fault injection: fsync failures, scheduler stress, network latency
- Recovery validation against correctness invariants
- Integrated Ward test execution

---

### Milestone F — Developer Productivity

#### `hot_reload_watcher.py` (Issue F.1.1)

File-watch tool for config hot-reload and orchestrated code restarts.

**Planned Features**:

- Config hot-reload via SIGHUP (zero downtime)
- Code restart orchestration (graceful drain + health check)
- Cross-platform support (PowerShell-friendly)
- Terminal UI with real-time status

---

## Architecture Principles

### 1. Deterministic Execution

All automation must be idempotent and produce identical outputs for identical inputs.

**Practices**:

- Use checksums for contract versioning
- Avoid timestamps in generated artifacts
- Use fixed random seeds for testing

### 2. Observable

Automation emits Prometheus metrics and structured logs.

**Metrics**:

- `k0_migration_duration_seconds` — Migration execution time
- `k0_schema_validation_errors_total` — Linting failures
- `k0_contract_breaking_changes_detected_total` — Breaking change count

### 3. CI-Gated

Breaking operations are enforced at PR stage.

**Gates**:

- Contract breaking changes → PR blocked
- Migration dry-run failures → PR blocked
- Documentation drift → Warning (non-blocking initially)

### 4. Developer-Friendly

Automation supports local development with fast feedback loops.

**Practices**:

- Pre-commit hooks for schema validation
- Hot-reload tooling for rapid iteration
- Clear error messages with remediation steps

---

## CI Integration

### Contract Validation (`contracts-ci.yml`)

Runs on PRs touching `k0/contracts/`:

```bash
python -m k0.automation.lint_schemas
python -m k0.automation.contract_compatibility_checker --base-ref=origin/main
python -m k0.automation.compute_contract_checksums --check
```

### Documentation Sync (`docs-ci.yml`)

Runs on PRs touching `k0/`, `docs/`, or `k0/contracts/`:

```bash
python -m k0.automation.verify_docs_sync
python -m k0.automation.generate_api_docs --check
```

### Security Telemetry (`security-ci.yml`)

Runs on all PRs:

```bash
python -m k0.automation.verify_security_telemetry
```

---

## Deprecations

The following files have been archived to `k0/automation/_archived/deprecated-2025-11-01/`:

- `remediation_actions.py` — K0 no longer executes privileged operations (microkernel purity)
- `remediation_service.py` — Remediation is now user-space concern consuming SSE events
- `generate_chaos_report.py` — Superseded by integrated `chaos_scheduler.py`
- `test_service.ps1` — Covered by Ward integration tests
- `test_webhook_payload.json` — Orphaned test fixture

**See**: `docs/architecture/decisions/0121-remediation-service-separation.md` for rationale.

---

## Running Locally

### Install Dependencies

```bash
pip install -r k0/automation/requirements.txt
```

### Lint Schemas

```bash
python -m k0.automation.lint_schemas --schemas-path k0/contracts/jsonschema
```

### Check Documentation Sync

```bash
python -m k0.automation.verify_docs_sync
```

### Generate API Docs

```bash
python -m k0.automation.generate_api_docs --output-dir docs/api/
```

### Run Migrations (Development)

```bash
# Create test database
python -m k0.automation.migrate --database-path test.sqlite3 --migrations-dir k0/automation/migrations

# Dry-run (no changes)
python -m k0.automation.migrate --database-path test.sqlite3 --dry-run
```

---

## References

- **K0 README**: `k0/README.md` (kernel architecture and ports)
- **K0 Plan**: `k0/plan.md` (implementation roadmap)
- **ADR-0121**: `docs/architecture/decisions/0121-remediation-service-separation.md`
- **Enhancement Plan**: `k0/automation/plan.md` (milestones A–G for 2025)

---

**Last Updated**: 2025-11-01
**Status**: Active development (Milestones A–G underway)
