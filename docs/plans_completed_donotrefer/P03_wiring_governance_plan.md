# P03 Wiring Governance & Version Tracking Plan

**Status**: Draft
**Created**: 2025-01-17
**Owner**: Architecture Team
**Related Pipelines**: P03 (Memory Consolidation), P01 (Recall)

---

## Executive Summary

This plan addresses a critical governance gap: **we have 167 Python files for P03 (89 algorithms + 78 pipeline components) but no automated way to verify they are actually wired together and working**.

### The Problem

1. **Orphan Risk**: Files may exist but never be imported or used
2. **No Version Tracking**: Changes to files are not tracked with checksums
3. **No Dependency Graph**: Cannot visualize which phases use which algorithms
4. **Manual Verification**: Currently requires manual code review to find broken wiring
5. **Governance Blind Spot**: Master document tracks file counts but not connection status

### The Solution

Build automated tooling to:

- Detect orphan files (created but never imported)
- Track file versions with SHA256 checksums
- Generate phase-wise dependency graphs
- Integrate wiring checks into existing `sync.py` governance

---

## Current State Analysis

### File Inventory

| Location | Purpose | File Count | Tracked? | Wiring Verified? |
|----------|---------|------------|----------|------------------|
| `k0/modules/consolidation/` | Reusable algorithms | 89 | Yes (3.4) | NO |
| `k0/pipelines/p03/` | Pipeline orchestration | 78 | Yes (3.5) | NO |
| `k0/modules/recall/` | P01 recall modules | 4 | Yes (3.1) | NO |
| **Total** | | **171** | Partial | **NO** |

### Known Risks

1. **Algorithm files not imported**: A developer creates `algorithms/new_algo.py` but forgets to import it in a phase
2. **Dead code accumulation**: Refactoring leaves old files that are no longer used
3. **Import path errors**: Typos in import statements break wiring silently
4. **Version drift**: Files change but VERSION tracking doesn't exist
5. **Test coverage gaps**: Tests may mock imports, hiding real wiring issues

### Existing Governance Scripts

| Script | Purpose | Covers P03? |
|--------|---------|-------------|
| `sync.py` | Master orchestrator | Partial (counts only) |
| `module_scanner.py` | Scan module contracts | No (contracts only) |
| `pipeline_scanner.py` | Scan pipeline contracts | No (contracts only) |
| `version_scanner.py` | Track config versions | No (config only) |
| `generate_checksums.py` | Contract checksums | No (contracts only) |

**Gap**: No script scans actual Python file imports or generates wiring graphs.

---

## Technical Design

### Architecture Overview

```
                    ┌─────────────────────────────────────────┐
                    │         sync.py (Master Orchestrator)    │
                    └─────────────────┬───────────────────────┘
                                      │
          ┌───────────────────────────┼───────────────────────────┐
          ▼                           ▼                           ▼
┌─────────────────┐         ┌─────────────────┐         ┌─────────────────┐
│ module_scanner  │         │ pipeline_scanner│         │ p03_wiring_     │
│ (existing)      │         │ (existing)      │         │ scanner (NEW)   │
└─────────────────┘         └─────────────────┘         └────────┬────────┘
                                                                  │
                    ┌─────────────────────────────────────────────┤
                    ▼                                             ▼
          ┌─────────────────┐                           ┌─────────────────┐
          │ p03_version_    │                           │ Import Graph    │
          │ manager (NEW)   │                           │ Builder (NEW)   │
          └────────┬────────┘                           └────────┬────────┘
                   │                                             │
                   ▼                                             ▼
          ┌─────────────────┐                           ┌─────────────────┐
          │ VERSION.yaml    │                           │ Wiring Report   │
          │ (checksums)     │                           │ (orphan detect) │
          └─────────────────┘                           └─────────────────┘
```

### New Scripts

#### 1. `p03_wiring_scanner.py`

**Purpose**: Analyze Python import statements to build dependency graph

**Key Functions**:

```python
def scan_p03_pipeline_files() -> list[FileInfo]:
    """Scan all 78 files in k0/pipelines/p03/"""

def scan_consolidation_algorithm_files() -> list[FileInfo]:
    """Scan all 89 files in k0/modules/consolidation/"""

def build_import_graph() -> dict[str, list[str]]:
    """AST parse each file, extract 'from k0...' imports"""

def find_orphan_files() -> list[str]:
    """Files in consolidation/ never imported by anything"""

def generate_phase_dependency_map() -> dict[str, list[str]]:
    """Map: r0 -> [batch_selector, gap_auto_resolver, ...]"""

def generate_wiring_report() -> WiringReport:
    """Comprehensive report with orphans, coverage, graph"""
```

**Output Format**:

```python
@dataclass
class WiringReport:
    total_pipeline_files: int      # 78
    total_algorithm_files: int     # 89
    wired_pipeline_files: int      # Files that import something
    wired_algorithm_files: int     # Files imported by something
    orphan_files: list[str]        # Never imported
    phase_dependencies: dict       # r0 -> [algos], r1 -> [algos]
    coverage_percent: float        # 91.5%
```

#### 2. `p03_version_manager.py`

**Purpose**: Track file versions with SHA256 checksums

**Key Functions**:

```python
def generate_version_file(target_dir: Path) -> None:
    """Create VERSION.yaml with all file checksums"""

def check_version_integrity(version_file: Path) -> list[str]:
    """Return list of files that changed since VERSION was generated"""

def bump_version(target_dir: Path, bump_type: str) -> None:
    """Bump major/minor/patch and regenerate checksums"""

def generate_changelog(old_version: Path, new_version: Path) -> str:
    """Diff two VERSION files, list changed files"""
```

**VERSION.yaml Format**:

```yaml
# Auto-generated by p03_version_manager.py
# DO NOT EDIT MANUALLY

metadata:
  version: 0.2.0
  generated: 2025-01-17T10:30:00Z
  generator: governance.k0.scripts.p03_version_manager
  total_files: 78

files:
  phases/r0_batch_selector.py:
    version: 1.0.0
    sha256: a1b2c3d4e5f6...
    lines: 245
    last_modified: 2025-01-15

  phases/r1_importance_scorer.py:
    version: 1.0.0
    sha256: f6e5d4c3b2a1...
    lines: 312
    last_modified: 2025-01-15

  ops/circuit_breaker.py:
    version: 1.0.0
    sha256: 1a2b3c4d5e6f...
    lines: 89
    last_modified: 2025-01-10
```

### Integration with sync.py

Add new check function:

```python
def check_p03_wiring() -> SyncReport:
    """Check P03 pipeline files are properly wired."""
    from governance.k0.scripts.p03_wiring_scanner import generate_wiring_report

    report = generate_wiring_report()

    return SyncReport(
        category="P03 Wiring",
        scanned_count=report.total_algorithm_files + report.total_pipeline_files,
        registered_count=report.wired_algorithm_files + report.wired_pipeline_files,
        missing_in_master=report.orphan_files,  # Orphans = governance drift
        missing_in_code=[],
        status_mismatches=[],
        is_curated=False,  # Orphans ARE drift - must be fixed
    )
```

### Generated Artifacts

#### 1. `docs/pipelines/p03_dependency_graph.md`

Auto-generated markdown showing phase-to-algorithm mapping:

```markdown
# P03 Dependency Graph

> Auto-generated: 2025-01-17 by `p03_wiring_scanner.py`

## Summary

| Metric | Value |
|--------|-------|
| Pipeline Files | 78 |
| Algorithm Files | 89 |
| Wired (Pipeline) | 72 |
| Wired (Algorithm) | 81 |
| Orphan Files | 14 |
| Coverage | 91.6% |

## Phase Dependencies

### R0: Batch Selection

**File**: `k0/pipelines/p03/phases/r0_batch_selector.py`

| Import | Target | Status |
|--------|--------|--------|
| `from k0.modules.consolidation.batch_selector` | batch_selector.py | ✅ |
| `from k0.modules.consolidation.gap_auto_resolver` | gap_auto_resolver.py | ✅ |
| `from k0.modules.consolidation.staging.manifest_validator` | staging/manifest_validator.py | ✅ |

### R1: Importance Scoring
...

## Orphan Analysis

### Algorithm Files Not Imported Anywhere

| File | Created | Recommendation |
|------|---------|----------------|
| `algorithms/legacy_scorer.py` | 2024-12-01 | DELETE or wire to R1 |
| `algorithms/experimental_cluster.py` | 2025-01-05 | Wire to R2 or move to poc/ |

### Pipeline Files Not Importing Anything

| File | Created | Recommendation |
|------|---------|----------------|
| `ops/unused_helper.py` | 2024-11-20 | DELETE or document purpose |
```

#### 2. `k0/contracts/p03_wiring.v1.yaml`

Machine-readable wiring contract:

```yaml
apiVersion: k0.contracts/v1
kind: PipelineWiring
metadata:
  name: p03-consolidation-wiring
  version: 1.0.0
  generated: 2025-01-17

spec:
  phases:
    r0:
      file: k0/pipelines/p03/phases/r0_batch_selector.py
      imports:
        - module: k0.modules.consolidation.batch_selector
          classes: [BatchSelector, BatchConfig]
        - module: k0.modules.consolidation.gap_auto_resolver
          classes: [GapAutoResolver]
      status: wired

    r1:
      file: k0/pipelines/p03/phases/r1_importance_scorer.py
      imports:
        - module: k0.modules.consolidation.algorithms.importance_scorer
          classes: [ImportanceScorer]
      status: wired

  orphans:
    algorithms:
      - path: k0/modules/consolidation/algorithms/legacy_scorer.py
        reason: "No imports found in any phase"
        action_required: "Wire to phase or delete"

  coverage:
    pipeline_files: 92.3%
    algorithm_files: 91.0%
    total: 91.6%
```

---

## Milestones, Epics & Issues

### Milestone 1: Foundation (Week 1)

**Goal**: Create core scanning infrastructure

#### Epic 1.1: P03 Wiring Scanner

| Issue | Title | Priority | Estimate | Dependencies |
|-------|-------|----------|----------|--------------|
| #101 | Create `p03_wiring_scanner.py` base structure | P0 | 2h | - |
| #102 | Implement `scan_p03_pipeline_files()` | P0 | 1h | #101 |
| #103 | Implement `scan_consolidation_algorithm_files()` | P0 | 1h | #101 |
| #104 | Implement AST-based import parser | P0 | 3h | #101 |
| #105 | Implement `build_import_graph()` | P0 | 2h | #104 |
| #106 | Implement `find_orphan_files()` | P0 | 1h | #105 |
| #107 | Add unit tests for wiring scanner | P1 | 2h | #102-#106 |

**Epic 1.1 Total**: 12 hours

#### Epic 1.2: Initial Baseline

| Issue | Title | Priority | Estimate | Dependencies |
|-------|-------|----------|----------|--------------|
| #108 | Run scanner, document baseline orphan count | P0 | 1h | #106 |
| #109 | Create tracking issue for each orphan file | P1 | 2h | #108 |
| #110 | Triage orphans: delete vs wire vs document | P1 | 2h | #109 |

**Epic 1.2 Total**: 5 hours

---

### Milestone 2: Version Tracking (Week 2)

**Goal**: Add checksum-based version tracking

#### Epic 2.1: Version Manager

| Issue | Title | Priority | Estimate | Dependencies |
|-------|-------|----------|----------|--------------|
| #201 | Create `p03_version_manager.py` base structure | P1 | 2h | - |
| #202 | Implement `generate_version_file()` | P1 | 2h | #201 |
| #203 | Implement `check_version_integrity()` | P1 | 2h | #202 |
| #204 | Implement `bump_version()` command | P2 | 1h | #202 |
| #205 | Implement `generate_changelog()` | P2 | 2h | #202 |
| #206 | Add unit tests for version manager | P1 | 2h | #201-#205 |

**Epic 2.1 Total**: 11 hours

#### Epic 2.2: VERSION File Generation

| Issue | Title | Priority | Estimate | Dependencies |
|-------|-------|----------|----------|--------------|
| #207 | Generate `k0/pipelines/p03/VERSION.yaml` | P1 | 0.5h | #202 |
| #208 | Generate `k0/modules/consolidation/VERSION.yaml` | P1 | 0.5h | #202 |
| #209 | Add VERSION files to .gitignore exclusion | P2 | 0.5h | #207, #208 |
| #210 | Document VERSION workflow in CONTRIBUTING.md | P2 | 1h | #207, #208 |

**Epic 2.2 Total**: 2.5 hours

---

### Milestone 3: Sync Integration (Week 2-3)

**Goal**: Integrate wiring checks into governance sync

#### Epic 3.1: Sync.py Integration

| Issue | Title | Priority | Estimate | Dependencies |
|-------|-------|----------|----------|--------------|
| #301 | Add `check_p03_wiring()` to sync.py | P0 | 2h | #106 |
| #302 | Add `--p03` flag for P03-specific report | P1 | 1h | #301 |
| #303 | Add wiring coverage to sync summary output | P1 | 1h | #301 |
| #304 | Update sync.py README with P03 commands | P2 | 1h | #301-#303 |

**Epic 3.1 Total**: 5 hours

#### Epic 3.2: CI Integration (Optional)

| Issue | Title | Priority | Estimate | Dependencies |
|-------|-------|----------|----------|--------------|
| #305 | Add wiring check to PR validation workflow | P2 | 2h | #301 |
| #306 | Create GitHub Action for orphan detection | P2 | 2h | #305 |
| #307 | Add status badge for wiring coverage | P3 | 1h | #306 |

**Epic 3.2 Total**: 5 hours

---

### Milestone 4: Documentation & Artifacts (Week 3)

**Goal**: Generate dependency graph documentation

#### Epic 4.1: Dependency Graph Generation

| Issue | Title | Priority | Estimate | Dependencies |
|-------|-------|----------|----------|--------------|
| #401 | Implement `generate_phase_dependency_map()` | P1 | 2h | #105 |
| #402 | Implement markdown report generator | P1 | 2h | #401 |
| #403 | Generate `docs/pipelines/p03_dependency_graph.md` | P1 | 1h | #402 |
| #404 | Add Mermaid diagram generation | P2 | 2h | #401 |

**Epic 4.1 Total**: 7 hours

#### Epic 4.2: Contract Artifact

| Issue | Title | Priority | Estimate | Dependencies |
|-------|-------|----------|----------|--------------|
| #405 | Design `p03_wiring.v1.yaml` schema | P2 | 1h | - |
| #406 | Implement YAML wiring contract generator | P2 | 2h | #405, #401 |
| #407 | Generate initial `k0/contracts/p03_wiring.v1.yaml` | P2 | 0.5h | #406 |
| #408 | Add wiring contract to contract registry | P2 | 0.5h | #407 |

**Epic 4.2 Total**: 4 hours

---

### Milestone 5: Master Document Update (Week 3)

**Goal**: Add wiring status to governance master

#### Epic 5.1: Section 3.6 Addition

| Issue | Title | Priority | Estimate | Dependencies |
|-------|-------|----------|----------|--------------|
| #501 | Add Section 3.6 "P03 Wiring Status" template | P1 | 1h | - |
| #502 | Auto-generate wiring table from scanner | P1 | 1h | #301, #501 |
| #503 | Add orphan tracking table to Section 3.6 | P1 | 1h | #502 |
| #504 | Update TOC with Section 3.6 | P2 | 0.5h | #501 |
| #505 | Update dashboard with wiring coverage row | P2 | 0.5h | #502 |

**Epic 5.1 Total**: 4 hours

---

## Summary

### Timeline

| Milestone | Duration | Issues | Total Hours |
|-----------|----------|--------|-------------|
| M1: Foundation | Week 1 | 10 | 17h |
| M2: Version Tracking | Week 2 | 10 | 13.5h |
| M3: Sync Integration | Week 2-3 | 7 | 10h |
| M4: Documentation | Week 3 | 8 | 11h |
| M5: Master Update | Week 3 | 5 | 4h |
| **Total** | **3 weeks** | **40** | **55.5h** |

### Priority Distribution

| Priority | Issue Count | Hours |
|----------|-------------|-------|
| P0 (Critical) | 8 | 14h |
| P1 (High) | 18 | 26h |
| P2 (Medium) | 11 | 12.5h |
| P3 (Low) | 3 | 3h |

### Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Orphan Detection | 100% accuracy | Compare manual audit vs scanner |
| Wiring Coverage | >95% | (wired files / total files) |
| Version Tracking | 100% files | All 167 files have checksums |
| Sync Integration | Pass | `sync.py --check` includes P03 |
| Documentation | Complete | Dependency graph auto-generated |

---

## Appendix A: File Counts Reference

### P03 Pipeline (`k0/pipelines/p03/`)

| Directory | Files | Purpose |
|-----------|-------|---------|
| `phases/` | 9 | Phase orchestrators (r0-r8) |
| `ops/` | 22 | Operational utilities |
| `qos/` | 8 | Quality of service |
| `security/` | 8 | Privacy and audit |
| `feedback/` | 4 | Feedback loop |
| `learning/` | 3 | Learning integration |
| `maintenance/` | 1 | Cleanup utilities |
| `api/` | 1 | API endpoints |
| `cache/` | 1 | Caching |
| Root | 21 | Core pipeline files |
| **Total** | **78** | |

### Consolidation Algorithms (`k0/modules/consolidation/`)

| Directory | Files | Purpose |
|-----------|-------|---------|
| Root | 2 | Entry points |
| `algorithms/` | 45 | Core algorithms |
| `algorithms/text_generators/` | 7 | Text generation |
| `dream/` | 6 | Dream exploration |
| `emission/` | 2 | Event emission |
| `staging/` | 13 | Coordination |
| `truth_writer/` | 7 | Truth layer ops |
| `truth_writer/layers/` | 7 | Layer writers |
| **Total** | **89** | |

---

## Appendix B: Command Reference

### After Implementation

```bash
# Check P03 wiring status
python -m governance.k0.scripts.sync --p03

# Generate wiring report
python -m governance.k0.scripts.p03_wiring_scanner --report

# Find orphan files
python -m governance.k0.scripts.p03_wiring_scanner --orphans

# Generate dependency graph
python -m governance.k0.scripts.p03_wiring_scanner --graph > docs/pipelines/p03_dependency_graph.md

# Check version integrity
python -m governance.k0.scripts.p03_version_manager --check

# Bump version after changes
python -m governance.k0.scripts.p03_version_manager --bump minor

# Generate VERSION files
python -m governance.k0.scripts.p03_version_manager --generate k0/pipelines/p03
python -m governance.k0.scripts.p03_version_manager --generate k0/modules/consolidation
```

---

## Appendix C: Related Documents

| Document | Purpose |
|----------|---------|
| `governance/k0/k0_architecture_master.md` | Master governance registry |
| `docs/pipelines/P03_consolidation_dossier_v2.md` | P03 pipeline specification |
| `governance/k0/scripts/README.md` | Scanner script documentation |
| `.github/copilot-instructions.md` | Development workflow rules |
