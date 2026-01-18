# Governance Scanner Extension Plan

**Status**: Planning
**Created**: 2025-12-31
**Owner**: K0 Architecture Team
**Target**: Complete sync coverage for all k0_architecture_master.md registries

---

## Executive Summary

Currently, the governance sync tool (`governance/k0/scripts/sync.py`) scans **5 of 14 Parts** in the master document. This plan extends coverage to scan **all registered categories** for complete architecture drift detection.

### Current State

| Part | Category | Has Scanner? | Source Location |
|------|----------|--------------|-----------------|
| Part 2 | Pipelines | ✅ Yes | `k0/pipelines/` |
| Part 3 | Modules | ✅ Yes | `k0/modules/` |
| Part 4 | Events | ✅ Yes | `k0/contracts/**/*.yaml`, emit() calls |
| Part 7 | Syscalls | ✅ Yes | `k0/kernel/syscalls.py` |
| Part 11 | ADRs | ✅ Yes | `docs/architecture/decisions-K0/` |
| Part 5 | Contracts | ❌ No | `k0/contracts/` |
| Part 6 | Storage Tables | ❌ No | `k0/db/alembic/versions/` |
| Part 6 | Migrations | ❌ No | `k0/db/alembic/versions/` |
| Part 6 | Indexes | ❌ No | `k0/db/alembic/versions/` |
| Part 7 | Capabilities | ❌ No | `k0/kernel/syscalls.py`, `k0/fabric/` |
| Part 8 | Fabric Providers | ❌ No | `k0/fabric/core_capabilities.v1.yaml` |
| Part 9 | Scheduler Tasks | ❌ No | `k0/scheduler/` |
| Part 9 | Background Workers | ❌ No | `k0/workers/` |
| Part 9 | Kernel Hooks | ❌ No | `k0/kernel/lifecycle.py` |
| Part 10 | Metrics | ❌ No | `k0/obs/` |
| Part 10 | Dashboards | ❌ No | `k0/obs/dashboards/` |
| Part 10 | Alerts | ❌ No | `k0/obs/alerts/` |
| Part 13 | Config Keys | ❌ No | `k0/config/*.yaml` |
| Part 13 | Feature Flags | ❌ No | `k0/config/features.yaml` |
| Part 13 | Environment Vars | ❌ No | `.env.example`, code scan |

---

## Milestone Structure

```
M0: Governance Foundation Complete (Current)
    └── 5 scanners operational

M1: Storage & Contract Scanners (Foundation)
    └── Epic 1.1: Storage Scanner
    └── Epic 1.2: Contract Scanner

M2: Capability & Security Scanners (Security)
    └── Epic 2.1: Capability Scanner
    └── Epic 2.2: Fabric Scanner

M3: Operational Scanners (Observability)
    └── Epic 3.1: Scheduler Scanner
    └── Epic 3.2: Metrics Scanner
    └── Epic 3.3: Config Scanner

M4: Full Governance Coverage (Complete)
    └── Epic 4.1: Kernel Hooks Scanner
    └── Epic 4.2: Final Integration
```

---

# Milestone 1: Storage & Contract Scanners (Foundation)

**Goal**: Ensure database schema and interface contracts are governed
**Target**: 2 new scanners, 4 new categories scanned
**Priority**: HIGH - Foundation for all other components

---

## Epic 1.1 — Storage Scanner

**Objective**: Scan Alembic migrations and validate against Part 6 registry

### Issue 1.1.1: Create storage_scanner.py base

**Description**: Create scanner that extracts table definitions from Alembic migrations

**Source Location**: `k0/db/alembic/versions/*.py`

**Extract**:

- Table name (from `op.create_table()` or class name)
- Column definitions
- Migration file path
- Applied status (from alembic_version table)

**Deliverables**:

- [ ] `governance/k0/scripts/storage_scanner.py`
- [ ] `StorageTableInfo` dataclass
- [ ] `scan_tables()` function
- [ ] `diff_with_master()` function

**Acceptance Criteria**:

```
python -m governance.k0.scripts.storage_scanner
# Output: List of 25+ tables from migrations
```

### Issue 1.1.2: Create migration_scanner.py

**Description**: Scan migration files and validate sequence

**Extract**:

- Migration ID (0001, 0002, etc.)
- File name
- Creates tables list
- Adds indexes list
- Revision dependencies

**Deliverables**:

- [ ] Migration extraction logic in storage_scanner.py
- [ ] `MigrationInfo` dataclass
- [ ] Sequence validation (no gaps)

### Issue 1.1.3: Create index_scanner.py

**Description**: Extract index definitions from migrations

**Extract**:

- Index name (idx_*)
- Table it belongs to
- Columns indexed
- Index type (BTREE, HNSW, GIN)
- Partial index condition

**Deliverables**:

- [ ] `IndexInfo` dataclass
- [ ] `scan_indexes()` function
- [ ] Parse `op.create_index()` calls

### Issue 1.1.4: Integrate storage scanner into sync.py

**Description**: Add storage checks to main sync orchestrator

**Deliverables**:

- [ ] `check_storage()` function in sync.py
- [ ] `check_migrations()` function in sync.py
- [ ] `check_indexes()` function in sync.py
- [ ] Update `run_all_checks()` to include storage (3 new categories)
- [ ] Update summary output

**Acceptance Criteria**:

```
python -m governance.k0.scripts.sync --report

Category        Scanned    Registered   Planning   Status
------------------------------------------------------------------------------------------
...existing 5 categories...
Tables          25         40           15         OK      # NEW
Migrations      26         26           0          OK      # NEW
Indexes         67         67           0          OK      # NEW
```

---

## Epic 1.2 — Contract Scanner

**Objective**: Scan YAML contracts and validate against Part 5 registry

### Issue 1.2.1: Create contract_scanner.py base

**Description**: Create scanner that extracts contract definitions from YAML files

**Source Locations**:

- `k0/contracts/modules/*.yaml` (Module contracts)
- `k0/contracts/pipelines/*.yaml` (Pipeline contracts)
- `k0/contracts/schemas/*.json` (Event schemas)

**Extract**:

- Contract name
- Module/Pipeline ID it governs
- Version
- Input/Output types
- File path

**Deliverables**:

- [ ] `governance/k0/scripts/contract_scanner.py`
- [ ] `ContractInfo` dataclass
- [ ] `scan_module_contracts()` function
- [ ] `scan_pipeline_contracts()` function
- [ ] `scan_event_schemas()` function

### Issue 1.2.2: Contract version validation

**Description**: Validate contract versions match code

**Checks**:

- Version in YAML matches registry
- No orphan contracts (file exists but not registered)
- No missing contracts (registered but file missing)

**Deliverables**:

- [ ] `diff_with_master()` function
- [ ] Version mismatch detection

### Issue 1.2.3: Integrate contract scanner into sync.py

**Description**: Add contract checks to main sync orchestrator

**Deliverables**:

- [ ] `check_module_contracts()` function
- [ ] `check_pipeline_contracts()` function
- [ ] `check_event_schemas()` function
- [ ] Update `run_all_checks()` (3 new categories)

**Acceptance Criteria**:

```
Category           Scanned    Registered   Planning   Status
------------------------------------------------------------------------------------------
ModuleContracts    23         31           8          OK      # NEW
PipelineContracts  2          3            1          OK      # NEW
EventSchemas       5          26           18         OK      # NEW
```

---

# Milestone 2: Capability & Security Scanners

**Goal**: Ensure capability grants and security boundaries are governed
**Target**: 2 new scanners, 2 new categories
**Priority**: HIGH - Security critical

---

## Epic 2.1 — Capability Scanner

**Objective**: Scan capability grants and validate against Part 7.2 registry

### Issue 2.1.1: Create capability_scanner.py

**Description**: Extract capability grants from syscalls and fabric

**Source Locations**:

- `k0/kernel/syscalls.py` - `_require_cap()` calls
- `k0/fabric/core_capabilities.v1.yaml` - Fabric grants

**Extract**:

- Capability name (e.g., `st_hipp_events.write`)
- Granted to component (P02, M16, etc.)
- Grant type (Storage, API, Index)
- Status (Active, Planned, Deprecated)

**Deliverables**:

- [ ] `governance/k0/scripts/capability_scanner.py`
- [ ] `CapabilityInfo` dataclass
- [ ] `scan_capability_checks()` - from _require_cap() calls
- [ ] `scan_capability_grants()` - from Part 7.2 registry

### Issue 2.1.2: Grant matrix validation

**Description**: Validate every _require_cap() has matching grant

**Checks**:

- Every capability checked in code has grant entry
- No unused grants (grant exists but never checked)
- Component assignments match

**Deliverables**:

- [ ] `validate_grant_matrix()` function
- [ ] Security report for ungoverned capabilities

### Issue 2.1.3: Integrate capability scanner

**Deliverables**:

- [ ] `check_capabilities()` function in sync.py
- [ ] Update `run_all_checks()`

---

## Epic 2.2 — Fabric Scanner

**Objective**: Scan fabric providers and validate against Part 8 registry

### Issue 2.2.1: Create fabric_scanner.py

**Description**: Extract fabric provider registrations

**Source Location**: `k0/fabric/core_capabilities.v1.yaml`

**Extract**:

- Provider ID (FAB-001, etc.)
- Capability name
- Handler function
- Module/Pipeline providing
- Resolution strategy
- Priority

**Deliverables**:

- [ ] `governance/k0/scripts/fabric_scanner.py`
- [ ] `FabricProviderInfo` dataclass
- [ ] `scan_fabric_providers()` function

### Issue 2.2.2: Integrate fabric scanner

**Deliverables**:

- [ ] `check_fabric()` function in sync.py
- [ ] Update `run_all_checks()`

---

# Milestone 3: Operational Scanners

**Goal**: Ensure scheduled tasks, metrics, and config are governed
**Target**: 3 new scanners, 6 new categories
**Priority**: MEDIUM - Operational reliability

---

## Epic 3.1 — Scheduler Scanner

**Objective**: Scan scheduled tasks, workers, kernel hooks (Part 9)

### Issue 3.1.1: Create scheduler_scanner.py

**Description**: Extract scheduled task definitions

**Source Locations**:

- `k0/scheduler/*.py` - Scheduler definitions
- `k0/workers/*.py` - Background workers
- `k0/kernel/lifecycle.py` - Kernel hooks

**Extract for Scheduled Tasks**:

- Task ID
- Schedule (cron/interval)
- Handler function
- Pipeline triggered
- Status

**Extract for Workers**:

- Worker ID
- Process type (async/thread/process)
- Queue consumed
- Status

**Extract for Kernel Hooks**:

- Hook ID
- Hook type (startup/shutdown)
- Order
- Handler function
- Status

**Deliverables**:

- [ ] `governance/k0/scripts/scheduler_scanner.py`
- [ ] `ScheduledTaskInfo` dataclass
- [ ] `BackgroundWorkerInfo` dataclass
- [ ] `KernelHookInfo` dataclass
- [ ] `scan_scheduled_tasks()` function
- [ ] `scan_background_workers()` function
- [ ] `scan_kernel_hooks()` function

### Issue 3.1.2: Integrate scheduler scanner

**Deliverables**:

- [ ] `check_scheduled_tasks()` function
- [ ] `check_workers()` function
- [ ] `check_kernel_hooks()` function
- [ ] Update `run_all_checks()` (3 new categories)

---

## Epic 3.2 — Metrics Scanner

**Objective**: Scan observability definitions (Part 10)

### Issue 3.2.1: Create metrics_scanner.py

**Description**: Extract metrics, dashboards, alerts

**Source Locations**:

- `k0/obs/metrics/*.py` - Metric definitions
- `k0/obs/dashboards/*.json` - Dashboard configs
- `k0/obs/alerts/*.yaml` - Alert rules

**Extract for Metrics**:

- Metric name
- Type (counter, gauge, histogram)
- Labels
- Component emitting

**Extract for Dashboards**:

- Dashboard ID
- Title
- Metrics referenced
- Last updated

**Extract for Alerts**:

- Alert name
- Condition
- Severity
- Runbook link

**Deliverables**:

- [ ] `governance/k0/scripts/metrics_scanner.py`
- [ ] `MetricInfo` dataclass
- [ ] `DashboardInfo` dataclass
- [ ] `AlertInfo` dataclass
- [ ] `scan_metrics()`, `scan_dashboards()`, `scan_alerts()`

### Issue 3.2.2: Integrate metrics scanner

**Deliverables**:

- [ ] `check_metrics()` function
- [ ] `check_dashboards()` function
- [ ] `check_alerts()` function
- [ ] Update `run_all_checks()` (3 new categories)

---

## Epic 3.3 — Config Scanner

**Objective**: Scan configuration keys and env vars (Part 13)

### Issue 3.3.1: Create config_scanner.py

**Description**: Extract config keys and environment variables

**Source Locations**:

- `k0/config/*.yaml` - Config files
- `k0/config/features.yaml` - Feature flags
- `.env.example` - Environment variables
- Code scan for `os.getenv()` calls

**Extract for Config Keys**:

- Key path (e.g., `k0.storage.pool_size`)
- Type (int, str, bool)
- Default value
- Config file source

**Extract for Feature Flags**:

- Flag name
- Default state
- Description
- Affected modules

**Extract for Environment Variables**:

- Variable name
- Required/Optional
- Default value
- Description

**Deliverables**:

- [ ] `governance/k0/scripts/config_scanner.py`
- [ ] `ConfigKeyInfo` dataclass
- [ ] `FeatureFlagInfo` dataclass
- [ ] `EnvVarInfo` dataclass
- [ ] `scan_config_keys()`, `scan_feature_flags()`, `scan_env_vars()`

### Issue 3.3.2: Integrate config scanner

**Deliverables**:

- [ ] `check_config_keys()` function
- [ ] `check_feature_flags()` function
- [ ] `check_env_vars()` function
- [ ] Update `run_all_checks()` (3 new categories)

---

# Milestone 4: Full Governance Coverage

**Goal**: Complete integration and enforcement
**Target**: Full sync coverage, CI integration option

---

## Epic 4.1 — Final Integration

### Issue 4.1.1: Update sync.py summary

**Description**: Update sync output to show all categories

**Target Output**:

```
======================================================================
SYNC STATUS SUMMARY
======================================================================

Note: Registered includes Planning items (not checked for code presence)

Category           Scanned    Registered   Planning   Missing(M)   Missing(C)   Status
------------------------------------------------------------------------------------------
Syscalls           19         19           0          0            0            OK
Pipelines          2          20           18         0            0            OK
Modules            22         24           2          0            0            OK
ADRs               40         42           3          0            0            OK
Events             49         66           17         0            0            OK
Tables             25         40           15         0            0            OK
Migrations         26         26           0          0            0            OK
Indexes            67         67           0          0            0            OK
ModuleContracts    23         31           8          0            0            OK
PipelineContracts  2          3            1          0            0            OK
EventSchemas       5          26           18         0            0            OK
Capabilities       27         27           0          0            0            OK
FabricProviders    18         18           0          0            0            OK
ScheduledTasks     6          6            0          0            0            OK
Workers            11         11           0          0            0            OK
KernelHooks        20         20           0          0            0            OK
Metrics            50         50           0          0            0            OK
Dashboards         10         10           0          0            0            OK
Alerts             25         25           0          0            0            OK
ConfigKeys         72         72           0          0            0            OK
FeatureFlags       5          5            0          0            0            OK
EnvVars            35         35           0          0            0            OK
------------------------------------------------------------------------------------------
OVERALL                                                                         SYNCED
```

### Issue 4.1.2: Update Part 1 Dashboard Auto-generation

**Description**: Auto-update Part 1 counts from scanner results

**Deliverables**:

- [ ] `--update-dashboard` flag
- [ ] Auto-update counts in Part 1.1

### Issue 4.1.3: Documentation update

**Description**: Update governance README with full scanner list

**Deliverables**:

- [ ] Update `governance/k0/scripts/README.md`
- [ ] Add scanner usage examples
- [ ] Add troubleshooting guide

---

## Epic 4.2 — CI Integration (Optional)

### Issue 4.2.1: CI check mode

**Description**: Add CI-friendly check mode

**Deliverables**:

- [ ] `--ci` flag for machine-readable output
- [ ] Exit code 1 on drift
- [ ] JSON output option

### Issue 4.2.2: GitHub Actions workflow

**Description**: Add governance check to CI

**Deliverables**:

- [ ] `.github/workflows/governance-check.yml`
- [ ] PR comment with drift summary
- [ ] Block merge on drift (optional)

---

# Summary: Scanner Inventory

| Scanner | Source | Categories | Part | Priority |
|---------|--------|------------|------|----------|
| `syscall_scanner.py` | ✅ EXISTS | Syscalls | 7 | - |
| `pipeline_scanner.py` | ✅ EXISTS | Pipelines | 2 | - |
| `module_scanner.py` | ✅ EXISTS | Modules | 3 | - |
| `event_scanner.py` | ✅ EXISTS | Events | 4 | - |
| `adr_scanner.py` | ✅ EXISTS | ADRs | 11 | - |
| `storage_scanner.py` | 🆕 NEW | Tables, Migrations, Indexes | 6 | M1 |
| `contract_scanner.py` | 🆕 NEW | Module/Pipeline/Schema Contracts | 5 | M1 |
| `capability_scanner.py` | 🆕 NEW | Capabilities | 7 | M2 |
| `fabric_scanner.py` | 🆕 NEW | Fabric Providers | 8 | M2 |
| `scheduler_scanner.py` | 🆕 NEW | Tasks, Workers, Hooks | 9 | M3 |
| `metrics_scanner.py` | 🆕 NEW | Metrics, Dashboards, Alerts | 10 | M3 |
| `config_scanner.py` | 🆕 NEW | Config Keys, Flags, Env Vars | 13 | M3 |

**Total**: 12 scanners (5 existing + 7 new)
**Categories**: 22 total (5 existing + 17 new)

---

# Timeline Estimate

| Milestone | Epics | Issues | Est. Effort | Dependency |
|-----------|-------|--------|-------------|------------|
| M1 | 2 | 7 | 3-4 days | None |
| M2 | 2 | 4 | 2-3 days | M1 |
| M3 | 3 | 6 | 3-4 days | M1 |
| M4 | 2 | 5 | 2-3 days | M1, M2, M3 |
| **Total** | **9** | **22** | **10-14 days** | |

---

# Acceptance Criteria (Full Plan)

**Governance is complete when**:

1. ✅ `python -m governance.k0.scripts.sync --report` scans ALL 22 categories
2. ✅ Status shows "SYNCED" for all categories
3. ✅ Planning items are excluded from drift detection (existing behavior)
4. ✅ Each scanner has `scan_*()` and `diff_with_master()` functions
5. ✅ Governance README documents all scanners
6. ✅ Part 1 dashboard can be auto-updated from scanner results

---

# Next Steps

1. **Approve this plan** - Review and confirm priority order
2. **Start M1** - Storage and Contract scanners (foundation)
3. **Iterate** - Each epic can be executed independently

**Question**: Should we start with Epic 1.1 (Storage Scanner) or Epic 1.2 (Contract Scanner)?
