# K0 Automation Enhancement Plan

> **Status**: In Progress (Started: 2025-11-01)
> **Owner**: Architecture Team
> **Reviewers**: Security, Operations, Product
> **ADR Reference**: Pending (will be created as ADR-0XX upon completion)

---

## Executive Summary

This plan restructures the `k0/automation/` directory to align with K0's microkernel architecture principles and production-grade operational standards. The initiative removes architectural violations (remediation logic that belongs in user-space), adds missing kernel-critical automation (contract compatibility, performance regression detection), and establishes automation as a first-class development practice.

**Timeline**: 6-8 weeks across 7 milestones
**Impact**: Improved developer velocity, reduced production risk, automated contract governance
**Risk**: Low (incremental PRs, comprehensive testing, CI gating)

---

## Current State Assessment

### Strengths ✅

- **Solid foundation**: `migrate.py`, `lint_schemas.py`, `compute_contract_checksums.py` are production-ready
- **Contract discipline**: VERSION registry, JSON Schema validation, OpenAPI/AsyncAPI specs
- **Security posture**: `verify_security_telemetry.py` enforces 100% threat scenario coverage

### Critical Gaps ❌

1. **Architectural violations**: Remediation logic (`remediation_actions.py`, `remediation_service.py`) violates microkernel separation (belongs in user-space P04 tier)
2. **Manual toil**: Dashboard/alert management, chaos testing, performance validation are manual processes
3. **Missing CI automation**: No contract compatibility checks, no performance regression detection
4. **Developer friction**: No hot-reload tooling, manual service restarts slow iteration

### Technical Debt 🔧

- `generate_chaos_report.py`: Basic Ward output parsing vs comprehensive chaos framework
- `test_service.ps1`: PowerShell script mixing concerns; superseded by Ward integration tests
- `test_webhook_payload.json`: Orphaned test fixture; should live in `tests/fixtures/`

---

## Architecture Principles

### Microkernel Purity

**K0 is a microkernel**—it provides four ABIs (Command, Query, SSE, Observability) and delegates all higher-order concerns to user-space services.

- ✅ **Correct**: K0 emits `infra.remediation.required` SSE events → P04 remediation service consumes and acts
- ❌ **Violation**: K0 directly executes `sudo iptables`, `docker-compose restart`, `kill -9` operations

### Automation as Infrastructure

**Principle**: All operational tasks (migrations, contract validation, performance checks) must be:

1. **Deterministic**: Same inputs → same outputs (checksums, reproducible builds)
2. **CI-gated**: Blocking checks prevent regressions from reaching production
3. **Observable**: Automation emits telemetry and artifacts for audit trails

### Developer Experience

**Principle**: Minimize friction for kernel developers:

- Hot-reload tooling (config changes without restart)
- Pre-commit hooks (fast local validation)
- Clear error messages with remediation steps

---

## Milestones & Deliverables

### Milestone A — Immediate Cleanup & Safety (Week 0)

**Epic A.1 — Automation Hygiene**

#### Issue A.1.1: Remove Architectural Violations *(Priority: P0 - Urgent)*

**Files to remove**:

- `k0/automation/remediation_actions.py` (2,091 lines)
- `k0/automation/remediation_service.py` (1,847 lines)
- `k0/automation/generate_chaos_report.py` (412 lines)
- `k0/automation/test_service.ps1` (187 lines)
- `k0/automation/test_webhook_payload.json` (34 lines)

**Total deletion**: ~4,571 lines of technical debt

**Rationale**:

1. **Remediation logic violates separation of concerns**
   - K0 should emit SSE events (`infra.remediation.required`, `infra.alert.fired`)
   - Dedicated remediation service (P04 tier) consumes events and executes actions
   - Keeps kernel pure, makes remediation pluggable/testable

2. **Security concerns**
   - Direct `sudo iptables` calls violate least-privilege
   - Hard-coded Docker paths break portability
   - `kill -9` operations are forceful vs graceful

3. **Manual chaos testing incomplete**
   - Basic Ward output parsing vs automated chaos framework
   - Will be superseded by `chaos_scheduler.py` in Milestone E

**Migration path**:

- Archive files to `k0/automation/_archived/deprecated-2025-11-01/`
- Create `docs/architecture/decisions/0XX-remediation-service-separation.md` (ADR)
- Update `k0/README.md` to document SSE-based remediation pattern
- Add to CHANGELOG.md with deprecation notice

**Acceptance criteria**:

- [ ] Files moved to `_archived/` directory
- [ ] ADR drafted and linked in docs
- [ ] CHANGELOG entry added
- [ ] CI passes (no references to deleted files)
- [ ] MCP memory entry created linking ADR and decision rationale

**Estimated effort**: 4 hours
**Risk**: Low (no production dependencies on these files)

---

### Milestone B — Core Automation Reliability (Weeks 1–2)

#### Epic B.1 — Migration Hardening

**Issue B.1.1: Add Rollback Support to `migrate.py`** *(Priority: P0 - Urgent)*

**Current state**: `k0/automation/migrate.py` supports forward migrations only
**Gap**: No rollback capability (documented in Issue 9.3.3 as missing feature)

**Enhancement**:

```python
# New functions to add
def rollback_migration(
    database_path: Path,
    target_version: str,
    *,
    dry_run: bool = False,
) -> list[MigrationResult]:
    """Rollback to target version by unapplying migrations in reverse order."""

def generate_rollback_script(
    migration_path: Path
) -> str:
    """Auto-generate DOWN migration from UP migration (best-effort)."""
```

**Features**:

1. **Rollback command**: `python -m k0.automation.migrate --rollback --target=<version>`
2. **Dry-run validation**: `--dry-run` mode shows rollback plan without executing
3. **Migration telemetry**: Emit Prometheus metrics (`k0_migration_duration_seconds`, `k0_migration_rollback_total`)
4. **Rollback script generation**: Auto-generate DOWN scripts from UP scripts (DDL reversal)

**Acceptance criteria**:

- [ ] Migrations can be rolled back to target version
- [ ] Dry-run mode validates rollback without execution
- [ ] Telemetry emitted for rollback operations
- [ ] Ward tests cover rollback success/failure scenarios
- [ ] Documentation updated in `k0/README.md` and `docs/development/runbooks/migrations.md`

**Estimated effort**: 12 hours
**Risk**: Medium (requires careful DDL reversal logic; manual rollback scripts may be needed for complex migrations)

---

#### Epic B.2 — Contract Governance

**Issue B.2.1: Implement `contract_compatibility_checker.py`** *(Priority: P0 - Urgent)*

**Problem**: Breaking contract changes can be merged without detection, violating K0's N/N+1 schema compatibility policy.

**Solution**: Automated SemVer enforcement and breaking change detection.

**Features**:

1. **Breaking change detection**:
   - Field removal: `properties.fieldName` deleted
   - Type changes: `"type": "string"` → `"type": "integer"`
   - Required field addition: `required` array expanded
   - Enum value removal: `enum` array contracted

2. **SemVer enforcement**:
   - Breaking change → require MAJOR version bump
   - Backward-compatible addition → require MINOR version bump
   - Documentation/fix → require PATCH version bump

3. **N/N+1 validation**:
   - Ensure at most 2 active versions (current + next)
   - Validate Schema Registry status transitions (REGISTERED → ACTIVE → DEPRECATED → BLOCKED)

4. **CI integration**:
   - Pre-merge check: `python -m k0.automation.contract_compatibility_checker --check`
   - Fail CI if breaking changes detected without version bump
   - Generate human-readable report with remediation steps

**Module structure**:

```python
# k0/automation/contract_compatibility_checker.py

from dataclasses import dataclass
from enum import Enum

class ChangeType(Enum):
    BREAKING = "breaking"
    COMPATIBLE = "compatible"
    PATCH = "patch"

@dataclass
class SchemaChange:
    change_type: ChangeType
    path: str  # JSONPath to changed field
    old_value: Any
    new_value: Any
    description: str

def detect_changes(
    old_schema: dict,
    new_schema: dict,
) -> list[SchemaChange]:
    """Detect all changes between schema versions."""

def classify_change_severity(
    changes: list[SchemaChange]
) -> ChangeType:
    """Determine if changes are breaking, compatible, or patch-level."""

def validate_version_bump(
    old_version: str,
    new_version: str,
    change_severity: ChangeType,
) -> bool:
    """Ensure version bump matches change severity (SemVer)."""

def generate_compatibility_report(
    changes: list[SchemaChange],
    version_check: bool,
) -> str:
    """Generate human-readable report for CI artifacts."""
```

**CI workflow integration**:

```yaml
# .github/workflows/contracts-ci.yml
- name: Check contract compatibility
  run: |
    python -m k0.automation.contract_compatibility_checker \
      --base-ref=origin/main \
      --head-ref=HEAD \
      --fail-on-breaking
```

**Acceptance criteria**:

- [ ] Detects breaking changes in JSON Schema, OpenAPI, AsyncAPI
- [ ] Enforces SemVer version bump rules
- [ ] Validates N/N+1 compatibility policy
- [ ] Generates CI-friendly report with remediation steps
- [ ] Ward tests cover all change types (breaking/compatible/patch)
- [ ] CI integration blocks PRs with contract violations

**Estimated effort**: 20 hours
**Risk**: Medium (requires robust JSON Schema diffing; edge cases in nested schemas)

---

### Milestone C — Contract & Docs Tooling (Weeks 2–3)

#### Epic C.1 — Schema & Docs Coverage

**Issue C.1.1: Enhance `lint_schemas.py`** *(Priority: P1 - High)*

**Current limitations**:

- Only validates JSON Schema files
- Does not validate FlatBuffers schemas (`.fbs`)
- Does not detect orphaned schemas (unreferenced in OpenAPI/AsyncAPI)

**Enhancements**:

1. **FlatBuffers validation**:
   - Parse `.fbs` files in `k0/contracts/flatbuffers/`
   - Validate schema structure and type references
   - Ensure generated Python files are up-to-date

2. **Cross-reference validation**:
   - Detect orphaned schemas (not referenced in any spec)
   - Validate all `$ref` pointers resolve correctly
   - Check schema versions match between specs and Schema Registry

3. **Comprehensive reporting**:
   - Group errors by severity (error, warning, info)
   - Provide file/line numbers for easy navigation
   - Suggest fixes (e.g., "Add $ref to openapi.k0.yaml")

**Example output**:

```
[SchemaLint] Validating contracts...

❌ ERROR: Breaking schema change detected
  File: k0/contracts/jsonschema/envelope.schema.json
  Issue: Field 'payload_sha256' changed type from 'string' to 'integer'
  Fix: Revert type change or bump major version

⚠️  WARNING: Orphaned schema detected
  File: k0/contracts/jsonschema/unused_schema.json
  Issue: Schema not referenced in any OpenAPI/AsyncAPI spec
  Fix: Remove file or add $ref in openapi.k0.yaml

✅ 15 schemas validated, 2 issues found
```

**Acceptance criteria**:

- [ ] Validates FlatBuffers schemas (`.fbs` files)
- [ ] Detects orphaned/unreferenced schemas
- [ ] Resolves all `$ref` pointers across files
- [ ] Grouped error reporting by severity
- [ ] Ward tests cover FlatBuffers validation and orphan detection
- [ ] CI integration as pre-merge check

**Estimated effort**: 16 hours
**Risk**: Medium (FlatBuffers parsing requires external tooling; may need `flatc` binary)

---

**Issue C.1.2: Enhance `generate_api_docs.py`** *(Priority: P1 - High)*

**Current limitations**:

- AsyncAPI rendered as raw JSON dump (not human-friendly)
- No Postman collection generation
- PDF timestamps non-deterministic (causes git churn)

**Enhancements**:

1. **AsyncAPI visual rendering**:
   - Use AsyncAPI HTML template (similar to ReDoc for OpenAPI)
   - Render channels, message schemas, and examples
   - Interactive navigation with search

2. **Postman collection generation**:
   - Auto-generate Postman collection from OpenAPI spec
   - Include example requests from `k0/contracts/jsonschema/examples/`
   - Export to `docs/api/postman/K0_Ports_Collection.json`

3. **Deterministic PDF generation**:
   - Fix timestamp to static value (e.g., `2024-01-01T00:00:00Z`)
   - Consistent font embedding and layout
   - Prevents unnecessary git diffs on every run

**Module enhancements**:

```python
# k0/automation/generate_api_docs.py

def _render_asyncapi_html(spec: Dict[str, Any]) -> str:
    """Render AsyncAPI spec using HTML template (not raw JSON)."""
    # Use asyncapi-react or similar for rich rendering

def _generate_postman_collection(openapi_spec: Dict[str, Any]) -> Dict[str, Any]:
    """Convert OpenAPI spec to Postman Collection v2.1 format."""

def _ensure_deterministic_pdf(pdf_bytes: bytes) -> bytes:
    """Strip timestamps and ensure consistent PDF metadata."""
```

**Acceptance criteria**:

- [ ] AsyncAPI rendered as interactive HTML (not JSON dump)
- [ ] Postman collection auto-generated from OpenAPI spec
- [ ] PDF generation is deterministic (no timestamp churn)
- [ ] `--check` mode validates docs are up-to-date (CI integration)
- [ ] Ward tests cover Postman collection generation
- [ ] Documentation updated in `k0/README.md`

**Estimated effort**: 14 hours
**Risk**: Low (libraries exist for AsyncAPI rendering and Postman collection generation)

---

### Milestone D — Observability Automation (Weeks 3–4)

#### Epic D.1 — Telemetry as Code

**Issue D.1.1: Add `telemetry_renderer.py`** *(Priority: P1 - High)*

**Problem**: Manual dashboard/alert management causes drift (documented in Issue 8.1.1).

**Solution**: Codify Grafana dashboards and Prometheus alert rules from SLO definitions.

**Features**:

1. **Dashboard generation from SLOs**:
   - SLO definitions in `k0/telemetry/slo_definitions.yaml`
   - Jsonnet templates in `k0/telemetry/mixins/`
   - Generated dashboards in `k0/telemetry/generated/dashboards/*.json` (single source of truth)
   - Deployment copies artifacts to `k0/deploy/generated/` for docker-compose mounts

2. **Alert rule generation**:
   - Prometheus recording rules derived from SLOs
   - Alert thresholds (warning/critical) per SLO
   - Generated rules in `k0/telemetry/generated/rules/*.yaml` (single source of truth)
   - Deployment copies artifacts to `k0/deploy/generated/rules/` for Prometheus scraping

3. **Deterministic rendering**:
   - Checksum-based drift detection
   - Reproducible builds (no timestamps in outputs)
   - CI validation with `promtool check rules`

4. **Preview stack integration**:
   - Grafana provisioning manifests
   - Datasource configuration
   - Dashboard auto-import on stack startup

**Module structure**:

```python
# k0/automation/telemetry_renderer.py

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any

@dataclass
class SLODefinition:
    name: str
    metric: str
    target_percentile: float  # e.g., 0.95 for P95
    target_value: float  # e.g., 150.0 for 150ms
    unit: str  # "ms", "count", "percent"

def load_slo_definitions(path: Path) -> list[SLODefinition]:
    """Load SLO definitions from YAML."""

def generate_dashboard(
    slos: list[SLODefinition],
    template: str = "default",
) -> Dict[str, Any]:
    """Generate Grafana dashboard JSON from SLO definitions."""

def generate_alert_rules(
    slos: list[SLODefinition],
) -> str:
    """Generate Prometheus alert rules YAML from SLOs."""

def render_all(
    output_dir: Path,
    *,
    check_mode: bool = False,
) -> bool:
    """Render all dashboards and rules; return True if changes detected."""
```

**SLO definition example**:

```yaml
# k0/telemetry/slo_definitions.yaml
slos:
  - name: command_submit_latency
    metric: k0_command_submit_duration_seconds
    target_percentile: 0.95
    target_value: 0.150  # 150ms
    unit: seconds
    alert_thresholds:
      warning: 0.200  # 200ms
      critical: 0.400  # 400ms

  - name: query_recall_latency
    metric: k0_query_recall_duration_seconds
    target_percentile: 0.95
    target_value: 0.250  # 250ms
    unit: seconds
    alert_thresholds:
      warning: 0.350
      critical: 0.600
```

**CI integration**:

```yaml
# .github/workflows/telemetry-ci.yml
- name: Check telemetry artifacts are up-to-date
  run: |
    python -m k0.automation.telemetry_renderer --check
    promtool check rules k0/telemetry/generated/rules/*.yaml
```

**Acceptance criteria**:

- [ ] Dashboards render deterministically from SLO definitions
- [ ] Alert rules generated and validated with `promtool`
- [ ] Grafana preview stack auto-imports dashboards
- [ ] `--check` mode validates no drift (CI integration)
- [ ] Ward tests cover SLO parsing and rendering
- [ ] Documentation in `docs/development/runbooks/slo-dashboard.md`

**Consolidation Strategy** (Single Source of Truth):

**Problem**: Currently have two telemetry artifact stores:

- `k0/telemetry/generated/` — Tool output (where rendering happens)
- `k0/deploy/generated/` — Deployment stage (docker-compose mounts)

**Solution**: Single source of truth with automated sync:

1. `telemetry_renderer.py` outputs to `k0/telemetry/generated/` only
2. Deployment script (`k0/deploy/k0.ps1`) syncs artifacts: `k0/telemetry/generated/* → k0/deploy/generated/`
3. docker-compose.yml mounts `k0/deploy/generated/` (deployment-local artifacts)
4. `k0/deploy/telemetry/` remains static configs (prometheus.yml, alertmanager.yml, grafana provisioning)

**Implementation**:

- Add `--sync-to-deploy` flag to `telemetry_renderer.py` for automation
- Update `k0/deploy/k0.ps1` to run sync on every `up` command
- Document artifact lifecycle in `k0/automation/README.md` and `k0/deploy/readme.md`

**Result**:

- No manual copying needed
- Single authoritative SLO definitions file (`k0/telemetry/slo_definitions.yaml`)
- Deploy stage always in sync with source
- CI validation uses `k0/telemetry/generated/` paths only

**Estimated effort**: 24 hours (includes consolidation + sync automation)
**Risk**: Medium (Jsonnet learning curve; dashboard JSON schema complexity)

---

### Milestone E — Performance & Chaos (Weeks 4–6)

#### Epic E.1 — Performance Regression Protection

**Issue E.1.1: Add `performance_regression_detector.py`** *(Priority: P2)*

**Problem**: Manual performance validation is error-prone; no automated regression detection.

**Solution**: CI-integrated performance baseline comparison.

**Features**:

1. **Baseline management**:
   - Store baselines in `k0/perf/baselines/<git-sha>.json`
   - Compare current run against main branch baseline
   - Detect regressions (>10% degradation triggers CI failure)

2. **Workload integration**:
   - Run `k0/perf/profiles/small.py`, `balanced.py`, `large.py`
   - Collect P50/P95/P99 latency, throughput, error rate
   - Generate flamegraphs for regressions

3. **CI reporting**:
   - Artifact comparison report (Markdown table)
   - Link to flamegraphs for deep dives
   - Actionable remediation steps

**Module structure**:

```python
# k0/automation/performance_regression_detector.py

@dataclass
class PerformanceBaseline:
    git_sha: str
    timestamp: str
    metrics: Dict[str, Dict[str, float]]  # workload -> {p50, p95, p99}

def run_performance_suite(
    profiles: list[str],
) -> PerformanceBaseline:
    """Run performance profiles and collect metrics."""

def load_baseline(git_sha: str = "main") -> PerformanceBaseline:
    """Load baseline from baselines/<git-sha>.json."""

def detect_regressions(
    current: PerformanceBaseline,
    baseline: PerformanceBaseline,
    threshold: float = 0.10,  # 10% degradation
) -> list[str]:
    """Compare baselines and return list of regressions."""

def generate_report(
    current: PerformanceBaseline,
    baseline: PerformanceBaseline,
    regressions: list[str],
) -> str:
    """Generate Markdown comparison report."""
```

**CI workflow**:

```yaml
# .github/workflows/performance-ci.yml (optional; non-blocking initially)
- name: Performance regression check
  run: |
    python -m k0.automation.performance_regression_detector \
      --baseline=main \
      --threshold=0.10 \
      --fail-on-regression
  continue-on-error: true  # Non-blocking initially
```

**Acceptance criteria**:

- [ ] Baselines stored and versioned by git SHA
- [ ] Regressions detected with configurable threshold
- [ ] Markdown report generated with remediation steps
- [ ] CI integration (optional non-blocking stage)
- [ ] Ward tests cover regression detection logic
- [ ] Documentation in `docs/development/runbooks/performance-testing.md`

**Estimated effort**: 18 hours
**Risk**: Medium (requires Ward integration with perf profiles; flamegraph generation tooling)

---

#### Epic E.2 — Chaos Automation

**Issue E.2.1: Add `chaos_scheduler.py`** *(Priority: P2)*

**Problem**: Manual chaos testing is incomplete (per `k0/plan.md`); `generate_chaos_report.py` is basic.

**Solution**: Automated, reproducible chaos experiments integrated with Ward.

**Features**:

1. **Chaos profiles**:
   - Mild: 5% fsync failures, 0.5x scheduler capacity
   - Moderate: 10% fsync failures, 0.3x scheduler capacity, 50ms network latency
   - Aggressive: 20% fsync failures, 0.2x scheduler capacity, 100ms network latency

2. **Fault injection**:
   - WAL fsync failures (via `k0/chaos/` hooks)
   - Scheduler stress (W-DRR queue overflow)
   - Network latency injection (SSE connection delays)
   - Telemetry outages (OTLP endpoint failures)

3. **Recovery validation**:
   - Assert correctness invariants (replay parity, receipt consistency)
   - Measure recovery time (MTTR)
   - Validate SSE reconnection and cursor recovery

4. **Automated reporting**:
   - JSON report with fault timeline, recovery metrics
   - CI artifact upload for inspection
   - Pass/fail based on invariant violations

**Module structure**:

```python
# k0/automation/chaos_scheduler.py

@dataclass
class ChaosProfile:
    name: str
    fsync_fail_rate: float
    scheduler_multiplier: float
    network_latency_ms: int
    telemetry_outage_rate: float

PROFILES = {
    "mild": ChaosProfile("mild", 0.05, 0.5, 0, 0.0),
    "moderate": ChaosProfile("moderate", 0.10, 0.3, 50, 0.1),
    "aggressive": ChaosProfile("aggressive", 0.20, 0.2, 100, 0.2),
}

def run_chaos_experiment(
    profile: ChaosProfile,
    duration_seconds: int = 300,
) -> ChaosReport:
    """Run chaos experiment with fault injection."""

def validate_recovery(
    report: ChaosReport,
) -> list[str]:
    """Validate correctness invariants post-chaos."""

def generate_chaos_report(
    report: ChaosReport,
    violations: list[str],
) -> str:
    """Generate JSON report with fault timeline and recovery metrics."""
```

**CI workflow**:

```yaml
# .github/workflows/chaos-ci.yml (non-blocking smoke test)
- name: Chaos smoke test (mild profile)
  run: |
    python -m k0.automation.chaos_scheduler \
      --profile=mild \
      --duration=60 \
      --output=chaos-report.json
  continue-on-error: true  # Non-blocking initially
```

**Acceptance criteria**:

- [ ] Reproducible chaos experiments with 3 profiles
- [ ] Fault injection via `k0/chaos/` hooks
- [ ] Recovery validation against correctness invariants
- [ ] JSON report with fault timeline and metrics
- [ ] CI integration (non-blocking smoke test)
- [ ] Ward tests cover fault injection and recovery
- [ ] Documentation in `docs/development/runbooks/chaos-testing.md`

**Estimated effort**: 22 hours
**Risk**: High (chaos injection requires deep integration with K0 internals; Ward test stability concerns)

---

### Milestone F — Developer Productivity (Weeks 2–4, parallel track)

#### Epic F.1 — Developer Tools

**Issue F.1.1: Add `hot_reload_watcher.py`** *(Priority: P2)*

**Problem**: Developer iteration requires manual `docker-compose restart` (~10s downtime).

**Solution**: File-watch tool for config hot-reload and orchestrated code restarts.

**Features**:

1. **Config hot-reload** (graceful, no downtime):
   - Watch `k0/config/*.yaml`, `k0/contracts/policy/*.yml`
   - Send SIGHUP to K0 process (triggers config reload)
   - Validate new config before reload

2. **Code restart** (orchestrated, minimal downtime):
   - Watch `k0/**/*.py` (excluding tests)
   - Graceful shutdown (drain requests)
   - Restart with health check polling
   - Report status in terminal UI

3. **Cross-platform support**:
   - PowerShell-friendly (Windows dev environment)
   - Works with Docker and local processes
   - Configurable watch paths and exclusions

**Module structure**:

```python
# k0/automation/hot_reload_watcher.py

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class K0ReloadHandler(FileSystemEventHandler):
    def on_modified(self, event):
        if event.src_path.endswith(('.yaml', '.yml')):
            self._handle_config_change(event.src_path)
        elif event.src_path.endswith('.py'):
            self._handle_code_change(event.src_path)

    def _handle_config_change(self, path: str):
        """Send SIGHUP for graceful config reload."""

    def _handle_code_change(self, path: str):
        """Orchestrate graceful restart with health check."""

def watch(
    watch_dirs: list[str],
    *,
    container_name: str = "k0-kernel",
) -> None:
    """Start file watcher with terminal UI."""
```

**Terminal UI example**:

```
K0 Hot Reload Watcher
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Watching: k0/config/, k0/contracts/, k0/**/*.py
Container: k0-kernel

[12:34:56] Config change detected: k0/config/kernel.yaml
[12:34:56] Validating config...
[12:34:56] ✅ Config valid, sending SIGHUP
[12:34:57] ✅ Config reloaded (no restart needed)

[12:45:12] Code change detected: k0/ports/command.py
[12:45:12] Orchestrating restart...
[12:45:13] ⏳ Draining requests (2s grace period)...
[12:45:15] ⏳ Restarting container...
[12:45:18] ⏳ Waiting for health check...
[12:45:20] ✅ Restart complete (8s downtime)

Press Ctrl+C to stop watching.
```

**Acceptance criteria**:

- [ ] Config changes trigger SIGHUP (no restart)
- [ ] Code changes trigger orchestrated restart with health check
- [ ] Cross-platform support (PowerShell + POSIX shells)
- [ ] Terminal UI shows real-time status
- [ ] Configurable watch paths via CLI args
- [ ] Documentation in `k0/automation/README.md`

**Estimated effort**: 12 hours
**Risk**: Low (watchdog library is mature; Docker orchestration is straightforward)

---

### Milestone G — CI / Tests / Docs / PRs (Ongoing)

#### Epic G.1 — CI & Test Integration

**Issue G.1.1: Update CI Workflows** *(Priority: P1 - High)*

**Objective**: Wire new automation tools into pre-merge checks.

**CI workflow updates**:

```yaml
# .github/workflows/contracts-ci.yml (enhanced)
name: Contract Validation

on:
  pull_request:
    paths:
      - 'k0/contracts/**'
      - 'k0/automation/**'

jobs:
  validate-contracts:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
        with:
          fetch-depth: 0  # Need full history for compatibility check

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.12'

      - name: Install dependencies
        run: pip install -r k0/automation/requirements.txt

      - name: Lint schemas
        run: python -m k0.automation.lint_schemas

      - name: Check contract compatibility
        run: |
          python -m k0.automation.contract_compatibility_checker \
            --base-ref=origin/main \
            --head-ref=HEAD \
            --fail-on-breaking

      - name: Verify docs sync
        run: python -m k0.automation.verify_docs_sync

      - name: Generate API docs (check mode)
        run: python -m k0.automation.generate_api_docs --check

      - name: Validate contract checksums
        run: python -m k0.automation.compute_contract_checksums --check
```

```yaml
# .github/workflows/telemetry-ci.yml (new)
name: Telemetry Validation

on:
  pull_request:
    paths:
      - 'k0/telemetry/**'
      - 'k0/obs/**'

jobs:
  validate-telemetry:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.12'

      - name: Install dependencies
        run: |
          pip install -r k0/automation/requirements.txt
          # Install promtool
          wget https://github.com/prometheus/prometheus/releases/download/v2.45.0/prometheus-2.45.0.linux-amd64.tar.gz
          tar xvfz prometheus-2.45.0.linux-amd64.tar.gz
          sudo mv prometheus-2.45.0.linux-amd64/promtool /usr/local/bin/

      - name: Render telemetry artifacts (check mode)
        run: python -m k0.automation.telemetry_renderer --check

      - name: Validate Prometheus rules
        run: promtool check rules k0/telemetry/generated/rules/*.yaml

      - name: Verify security telemetry
        run: python -m k0.automation.verify_security_telemetry
```

**Acceptance criteria**:

- [ ] Contract validation runs on every PR touching `k0/contracts/`
- [ ] Telemetry validation runs on PR touching `k0/telemetry/`
- [ ] Performance smoke test (optional, non-blocking)
- [ ] Chaos smoke test (optional, non-blocking)
- [ ] CI failures have actionable error messages

**Estimated effort**: 8 hours
**Risk**: Low (GitHub Actions syntax is straightforward)

---

**Issue G.1.2: Tests, Runbooks, Documentation** *(Priority: P1 - High)*

**Test coverage requirements**:

1. **Ward/pytest tests for new tools**:
   - `tests/automation/test_contract_compatibility_checker.py`
   - `tests/automation/test_telemetry_renderer.py`
   - `tests/automation/test_performance_regression_detector.py`
   - `tests/automation/test_chaos_scheduler.py`
   - Coverage target: >80% line coverage

2. **Integration tests**:
   - End-to-end workflow tests (e.g., migrate → rollback → migrate)
   - CI smoke tests for each automation tool

**Documentation deliverables**:

1. **`k0/automation/README.md`** (new):
   - Overview of automation philosophy
   - Tool descriptions and usage examples
   - Development workflow with hot-reload
   - CI integration guide

2. **Runbook updates**:
   - `docs/development/runbooks/migrations.md` (enhanced with rollback)
   - `docs/development/runbooks/contract-governance.md` (new)
   - `docs/development/runbooks/performance-testing.md` (new)
   - `docs/development/runbooks/chaos-testing.md` (new)
   - `docs/development/runbooks/slo-dashboard.md` (enhanced)

3. **ADRs**:
   - `docs/architecture/decisions/0XX-remediation-service-separation.md`
   - `docs/architecture/decisions/0XX-automation-as-infrastructure.md`
   - `docs/architecture/decisions/0XX-telemetry-as-code.md`

4. **CHANGELOG.md updates**:
   - Entry for each milestone with breaking changes noted
   - Deprecation notices for removed files

**Acceptance criteria**:

- [ ] All new tools have >80% test coverage
- [ ] `k0/automation/README.md` documents all tools
- [ ] Runbooks updated with step-by-step instructions
- [ ] ADRs drafted and reviewed
- [ ] CHANGELOG entries added

**Estimated effort**: 16 hours
**Risk**: Low (documentation and testing; no production impact)

---

**Issue G.1.3: Open PRs, Review, Merge** *(Priority: P0 - Urgent)*

**PR strategy**: Small, incremental PRs for easy review.

**PR sequence**:

1. **PR #1: Remove deprecated automation** (Milestone A)
   - Archive remediation/chaos files
   - Update CHANGELOG and README
   - ADR for remediation service separation

2. **PR #2: Add rollback to migrate.py** (Milestone B.1)
   - Rollback support
   - Tests and documentation

3. **PR #3: Add contract compatibility checker** (Milestone B.2)
   - New tool + CI integration
   - Tests and runbook

4. **PR #4: Enhance lint_schemas and generate_api_docs** (Milestone C)
   - FlatBuffers validation
   - AsyncAPI rendering
   - Postman collection

5. **PR #5: Add telemetry_renderer** (Milestone D)
   - Dashboard/alert generation
   - CI integration

6. **PR #6: Add performance/chaos tools** (Milestone E)
   - Performance regression detector
   - Chaos scheduler
   - Non-blocking CI integration

7. **PR #7: Add hot_reload_watcher** (Milestone F)
   - Developer productivity tool
   - Documentation

8. **PR #8: Final CI/docs/tests** (Milestone G)
   - CI workflow updates
   - Comprehensive documentation
   - Test coverage

**PR template checklist**:

- [ ] Linked to issue number
- [ ] ADR referenced (if applicable)
- [ ] Tests added/updated (>80% coverage)
- [ ] Documentation updated
- [ ] CHANGELOG entry added
- [ ] CI passes
- [ ] MCP memory entry created
- [ ] Reviewers assigned (Architecture, Security, Ops)

**Acceptance criteria**:

- [ ] All PRs created and linked to issues
- [ ] Reviewers assigned per CODEOWNERS
- [ ] Merge plan documented
- [ ] MCP memory entries created for each PR

**Estimated effort**: 12 hours (PR preparation and coordination)
**Risk**: Low (incremental merges; rollback plan available)

---

## Risk Management

### High-Risk Items

1. **Chaos scheduler integration** (Issue E.2.1)
   - **Risk**: Fault injection may destabilize Ward test runs
   - **Mitigation**: Start with mild profile; non-blocking CI stage; extensive local testing

2. **Contract compatibility checker edge cases** (Issue B.2.1)
   - **Risk**: Complex nested schemas may have unhandled diff scenarios
   - **Mitigation**: Start with simple schemas; iterate on feedback; manual review gate initially

### Medium-Risk Items

3. **Migration rollback logic** (Issue B.1.1)
   - **Risk**: DDL reversal may be incomplete for complex migrations
   - **Mitigation**: Manual rollback scripts for complex cases; dry-run validation

4. **Telemetry renderer Jsonnet complexity** (Issue D.1.1)
   - **Risk**: Dashboard JSON schema is complex; Jsonnet learning curve
   - **Mitigation**: Start with simple dashboards; leverage Grafonnet library; iterate

### Low-Risk Items

5. **Hot-reload watcher** (Issue F.1.1)
   - **Risk**: File watcher may miss events on some platforms
   - **Mitigation**: Use mature watchdog library; test on Windows/Linux/macOS

---

## Success Metrics

### Developer Velocity

- **Hot-reload adoption**: >80% of kernel devs use hot-reload watcher
- **Iteration time**: Reduced from ~30s (manual restart) to ~5s (config reload)

### Contract Governance

- **Breaking changes blocked**: 100% of breaking contract changes blocked at PR stage
- **Schema drift**: Zero drift between contracts and implementation

### Operational Excellence

- **Dashboard drift**: Zero manual dashboard edits (all codified)
- **Alert coverage**: 100% of SLOs have corresponding alerts
- **Performance regressions**: Zero regressions reaching main branch

### Automation Health

- **CI stability**: <1% flake rate on automation checks
- **Test coverage**: >80% coverage for all automation tools
- **Documentation completeness**: 100% of tools documented with runbooks

---

## Timeline & Resource Allocation

### Sprint Plan (2-week sprints)

- **Sprint 1 (Weeks 0-1)**: Milestone A + B.1 (cleanup + migrate rollback)
- **Sprint 2 (Weeks 2-3)**: Milestone B.2 + C (contract checker + schema/docs)
- **Sprint 3 (Weeks 4-5)**: Milestone D + F (telemetry + hot-reload)
- **Sprint 4 (Weeks 6-7)**: Milestone E (performance + chaos)
- **Sprint 5 (Week 8)**: Milestone G (CI finalization + docs)

### Resource Allocation

- **Primary**: 1 senior engineer (full-time)
- **Review**: Architecture (2-4 hrs/week), Security (2 hrs/week), Ops (2 hrs/week)
- **Total effort**: ~180 hours (4.5 weeks at 40 hrs/week + review overhead)

---

## Appendix

### File Structure (After Completion)

```
k0/automation/
├── README.md                              ➕ NEW (automation guide)
├── requirements.txt                       ✅ UPDATED (new dependencies)
│
├── # Contract Management
├── compute_contract_checksums.py          ✅ KEEP (no changes)
├── lint_schemas.py                        ✅ ENHANCED (FlatBuffers + $ref)
├── contract_compatibility_checker.py      ➕ NEW (SemVer enforcement)
│
├── # Documentation Generation
├── generate_api_docs.py                   ✅ ENHANCED (AsyncAPI + Postman)
├── verify_docs_sync.py                    ✅ ENHANCED (extended validation)
│
├── # Database & Schema
├── migrate.py                             ✅ ENHANCED (rollback support)
├── migrations/                            ✅ KEEP (migration scripts)
│
├── # Security & Compliance
├── verify_security_telemetry.py           ✅ KEEP (no changes)
│
├── # Observability
├── telemetry_renderer.py                  ➕ NEW (dashboard/alert gen)
│
├── # Performance & Chaos
├── performance_regression_detector.py     ➕ NEW (CI perf checks)
├── chaos_scheduler.py                     ➕ NEW (automated chaos)
│
├── # Developer Tools
├── hot_reload_watcher.py                  ➕ NEW (dev productivity)
│
└── # Archived/Deprecated
    └── _archived/
        └── deprecated-2025-11-01/
            ├── remediation_actions.py     ❌ ARCHIVED
            ├── remediation_service.py     ❌ ARCHIVED
            ├── generate_chaos_report.py   ❌ ARCHIVED
            ├── test_service.ps1           ❌ ARCHIVED
            └── test_webhook_payload.json  ❌ ARCHIVED
```

### Dependencies (requirements.txt additions)

```txt
# Existing dependencies
jsonschema>=4.17.0
pyyaml>=6.0
prometheus-client>=0.16.0

# New dependencies for enhancements
watchdog>=3.0.0              # hot_reload_watcher
deepdiff>=6.0.0              # contract_compatibility_checker
semver>=3.0.0                # SemVer validation
jinja2>=3.1.0                # Template rendering
requests>=2.31.0             # API docs generation
asyncapi-html-template       # AsyncAPI rendering (or similar)
```

### References

- **K0 README**: `k0/README.md` (kernel architecture, ports, contracts)
- **K0 Plan**: `k0/plan.md` (implementation roadmap, issues 8.1.1-8.1.3)
- **Copilot Instructions**: `.github/copilot-instructions.md` (5-step gated workflow)
- **Service Design**: `.github/instructions/service-design.instructions.md`
- **Architecture Governance**: `.github/instructions/architecture-governance.instructions.md`
- **Issue 9.3.3**: `docs/development/issue-9.3.3-architecture-program-review.md` (v1.0.0-rc release scope)

---

**Status**: Plan finalized, ready for execution
**Next Action**: Execute Milestone A (remove deprecated automation files)
**MCP Memory Entry**: Pending (will be created upon PR merge)
