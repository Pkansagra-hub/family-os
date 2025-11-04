# ADR Reorganization Migration Process

**Document Version:** 1.0
**Last Updated:** 2025-11-03
**Status:** VALIDATED (Successfully migrated ADRs 0001-0004 with 22 files)

---

## 🎯 Purpose

This document captures the proven, battle-tested process for migrating ADR families from the flat structure to the new organized folder structure. Follow this process for all future ADR migrations.

**Tested On:** ADR families 0001, 0002, 0003, 0004 (22 total files)
**Success Rate:** 100% (zero broken links, all metadata intact)
**Time Per Family:** ~30 minutes (5 ADRs with sub-ADRs)

---

## 📋 Prerequisites

### Required Tools

1. **Python 3.13+** with virtual environment activated
2. **ripgrep** (installed via `winget install BurntSushi.ripgrep.MSVC`)
3. **Scripts installed:**
   - `scripts/ADR_scripts/build_adr_index.py`
   - `scripts/ADR_scripts/phase3_link_audit_scoped.py`
   - `scripts/ADR_scripts/phase4_file_migration.py`
   - `scripts/ADR_scripts/update_adr_links.py`
   - `scripts/ADR_scripts/validate_adr_metadata.py`
   - `scripts/ADR_scripts/generate_propagation_maps.py`

### Verify Environment

```powershell
# Check Python
.venv\Scripts\python.exe --version
# Expected: Python 3.13.x

# Check ripgrep
rg --version
# Expected: ripgrep 15.1.0 (or higher)

# Check scripts exist
Test-Path scripts\ADR_scripts\*.py
# Expected: True
```

---

## 🔄 5-Phase Migration Process

### Phase 1: Metadata Addition (YAML Frontmatter)

**Goal:** Add structured metadata to all ADRs without moving files yet.

#### Step 1.1: Identify ADRs to Migrate

```powershell
# List ADR family (parent + sub-ADRs)
Get-ChildItem docs\architecture\decisions\000[1-4]*.md | Sort-Object Name

# Example output:
# 0001-k0-k1-kernel-split.md
# 0001a-k0-bridge-communication-protocol.md
# 0001b-model-hub-architecture-llm-integration.md
# ... (22 files total for families 0001-0004)
```

#### Step 1.2: Add YAML Frontmatter to Each ADR

**Template (insert at top of file):**

```yaml
---
adr_number: "0001"
title: "K0/K1 Kernel Split Architecture"
status: ACCEPTED  # PROPOSED | ACCEPTED | APPROVED | IMPLEMENTED | COMPLETED | DEPRECATED
date_created: 2025-10-10
date_updated: 2025-11-03
authors: ["K1 Architecture Team"]

# Layer/Module Mapping (KEY FOR PROPAGATION)
affected_layers:
  - layer1_input
  - layer2_orchestration
  - layer3_execution
  - layer4_runtime
  - layer5_infrastructure

affected_modules:
  - k0
  - k1
  - k0_bridge
  - agent_fabric
  - orchestrator_core
  - model_hub
  - session_state

# Concern Tags (for AI filtering)
concerns:
  - architecture
  - performance
  - scalability
  - reliability
  - modularity
  - maintainability
  - security
  - fault_isolation

# Cross-References
supersedes: []
superseded_by: []
related_adrs:
  - ADR-0002
  - ADR-0004
  - ADR-0005
  - ADR-0006

# Implementation
implementation_status: COMPLETED
implementation_date: 2025-10-15

# Contracts & Diagrams
related_contracts:
  - k1/contracts/flatbuffers/**/*.fbs
related_diagrams:
  - architecture_diagrams/k1/k1_complete_with_flows.mmd

# Propagation Map (WHO MUST UPDATE THIS ADR?)
propagation:
  triggers:
    - "Changing K0/K1 boundary contract"
    - "Adding new cross-kernel API"
  affected_adrs:
    - ADR-0002  # Actor Model changes
    - ADR-0011  # FlatBuffers schema changes
  affected_contracts:
    - k1/contracts/api/k0_bridge.yaml
  affected_tests:
    - tests/k1/integration/test_k0_bridge.py
---
```

**Key Fields Explanation:**

| Field | Description | Required? |
|-------|-------------|-----------|
| `adr_number` | ADR number (e.g., "0001", "0001a") | ✅ YES |
| `title` | Full ADR title | ✅ YES |
| `status` | Current status | ✅ YES |
| `affected_layers` | Which of 5 K1 layers this affects | ✅ YES |
| `affected_modules` | Specific Python modules | ✅ YES |
| `concerns` | Architectural concerns (min 3) | ✅ YES |
| `related_adrs` | Cross-references to other ADRs | ⚠️ RECOMMENDED |
| `propagation` | What triggers updates to this ADR | ⚠️ RECOMMENDED |
| `implementation_status` | Implementation progress | ⚠️ RECOMMENDED |

#### Step 1.3: Validate Metadata

```powershell
# Validate single ADR
.venv\Scripts\python.exe scripts\ADR_scripts\validate_adr_metadata.py `
  docs\architecture\decisions\0001-k0-k1-kernel-split.md

# Expected output:
# ✅ 0001-k0-k1-kernel-split.md: Valid frontmatter

# Validate all modified ADRs
.venv\Scripts\python.exe scripts\ADR_scripts\validate_adr_metadata.py `
  docs\architecture\decisions\000[1-4]*.md

# Expected: All ✅ (zero errors)
```

**Common Metadata Issues:**

| Error | Cause | Fix |
|-------|-------|-----|
| `Missing required field: adr_number` | No `adr_number` in frontmatter | Add `adr_number: "0001"` |
| `Invalid YAML syntax` | Indentation error | Use 2 spaces, not tabs |
| `affected_layers must be list` | Used string instead of list | Change `layer1_input` to `- layer1_input` |

#### Step 1.4: Rebuild Index (First Time)

```powershell
# Build initial index with new metadata
.venv\Scripts\python.exe scripts\ADR_scripts\build_adr_index.py

# Expected output:
# 🔍 Scanning D:\familyos\docs\architecture\decisions for ADR files...
# 📄 Found 355 ADR files
#   ✅ 0001: K0/K1 Kernel Split Architecture
#   ✅ 0002: Actor Model for Agent Isolation
#   ✅ 0003: MPST Protocol Validation
#   ✅ 0004: 56-Module 5-Layer Microkernel Architecture
# ... (all 355 ADRs)
# ✅ Index saved to D:\familyos\docs\architecture\decisions\00-meta\adr_index.json
```

---

### Phase 2: Pre-Migration Link Audit

**Goal:** Find all internal references to ADRs before moving files (prevents broken links).

#### Step 2.1: Run Link Audit Script

```powershell
# Audit links for specific ADR families (0001-0004)
.venv\Scripts\python.exe scripts\ADR_scripts\phase3_link_audit_scoped.py `
  --adrs 0001 0002 0003 0004 `
  --output LINK_AUDIT_REPORT_0001-0004.md

# Expected output:
# 🔍 Scanning workspace for references to ADRs: 0001, 0002, 0003, 0004
# 📊 Link Audit Statistics:
#   References TO these ADRs: 1345
#   References FROM these ADRs: 180
#   Diagram references: 43
#   Potential broken links: 29
# ✅ Report saved: LINK_AUDIT_REPORT_0001-0004.md
# ✅ Data saved: link_audit_data_0001-0004.json
```

#### Step 2.2: Review Link Audit Report

```powershell
# Open report
code LINK_AUDIT_REPORT_0001-0004.md
```

**Report Sections:**

1. **References TO ADRs** (other files linking to these ADRs)
2. **References FROM ADRs** (these ADRs linking to others)
3. **Diagram References** (architecture diagrams mentioning ADRs)
4. **Potential Broken Links** (links to non-existent ADRs)

**Action Items:**

- ✅ **IF** broken links are to future ADRs (e.g., 0064, 0072) → Document, will fix later
- ⚠️ **IF** broken links are to migrated ADRs → Fix before proceeding
- ✅ **IF** all broken links documented → Proceed to Phase 3

---

### Phase 3: Create Target Folder Structure

**Goal:** Set up destination folders before moving files.

**CRITICAL: Categorization Strategy**

ADRs should be categorized by **SEMANTIC PURPOSE** (what owns/manages the concern), NOT by `affected_layers` metadata.

| Wrong Approach ❌ | Right Approach ✅ |
|------------------|------------------|
| "ADR mentions layer1_input in metadata → put in 02-layer1-input/" | "ADR describes state management for orchestration → put in 03-layer2-orchestration/" |
| "ADR affects all 5 layers → pick first one" | "ADR's primary architectural responsibility → correct category" |
| "`affected_layers` = descriptive (what touches)" | "Category = prescriptive (what owns)" |

**Examples from Series 11-20:**

| ADR | Wrong Category | Correct Category | Reasoning |
|-----|---------------|------------------|-----------|
| 0017 SessionState | ❌ 02-layer1-input | ✅ 03-layer2-orchestration | State management is orchestration concern, not input processing |
| 0018 Eviction | ❌ 02-layer1-input | ✅ 05-layer4-runtime | Memory management is runtime concern |
| 0020 Storage Tiers | ❌ 02-layer1-input | ✅ 06-layer5-infrastructure | Hot/warm/cold storage is infrastructure concern |
| 0011-0013, 0019 | ✅ 07-contracts-serialization | ✅ 07-contracts-serialization | FlatBuffers schemas and versioning |
| 0014-0016 | ✅ 09-communication | ✅ 09-communication | JSON/WebSocket/SSE protocols |

**Decision Criteria:**

1. **Read ADR title and content** - What is the PRIMARY architectural decision?
2. **Identify semantic owner** - Which K1 layer/subsystem OWNS this concern?
3. **Ignore cross-cutting nature** - Many ADRs affect multiple layers, but have ONE owner
4. **Ask: "Where would I maintain this?"** - Implementation responsibility = category

#### Step 3.1: Create Category Folders

```powershell
# Create 01-foundation folder (for ADRs 0001-0004)
New-Item -ItemType Directory -Force -Path "docs\architecture\decisions\01-foundation"

# Create ADR family subfolders
New-Item -ItemType Directory -Force -Path "docs\architecture\decisions\01-foundation\0001-k0-k1-kernel-split"
New-Item -ItemType Directory -Force -Path "docs\architecture\decisions\01-foundation\0002-actor-model-agent-isolation"
New-Item -ItemType Directory -Force -Path "docs\architecture\decisions\01-foundation\0003-mpst-protocol-validation"
New-Item -ItemType Directory -Force -Path "docs\architecture\decisions\01-foundation\0004-56-module-5-layer-architecture"

# Create folder index template
@"
# ADR Category Index: 01-foundation
# Auto-generated by build_adr_index.py

adrs:
  # Populated by build_adr_index.py script
"@ | Out-File -FilePath "docs\architecture\decisions\01-foundation\index.yml" -Encoding utf8
```

**Example: Series 11-20 Categorization**

```powershell
# Correct categorization by semantic purpose
$baseDir = "docs\architecture\decisions"
$folders = @(
    "07-contracts-serialization\0011-flatbuffers-serialization",       # FlatBuffers = contracts
    "07-contracts-serialization\0012-76-flatbuffers-schemas",            # Schemas = contracts
    "07-contracts-serialization\0013-pipeline-versioning-policy",        # Versioning = contracts
    "09-communication\0014-json-rest-api-dual-format",                   # JSON API = communication
    "09-communication\0015-websocket-binary-protocol",                   # WebSocket = communication
    "09-communication\0016-sse-event-schemas",                           # SSE = communication
    "03-layer2-orchestration\0017-sessionstate-6-section-design",        # SessionState = orchestration (NOT input!)
    "05-layer4-runtime\0018-3-tier-eviction-strategy",                   # Eviction = runtime memory
    "07-contracts-serialization\0019-flatbuffers-sessionstate-serialization", # Serialization = contracts
    "06-layer5-infrastructure\0020-multi-tier-storage"                   # Storage tiers = infrastructure
)

foreach ($folder in $folders) {
    $path = Join-Path $baseDir $folder
    New-Item -ItemType Directory -Force -Path $path | Out-Null
    Write-Host "  ✅ Created: $folder" -ForegroundColor Green
}
```

#### Step 3.2: Verify Folder Structure

```powershell
# Check structure
tree /F docs\architecture\decisions\01-foundation

# Expected:
# 01-foundation
# │   index.yml
# ├───0001-k0-k1-kernel-split
# ├───0002-actor-model-agent-isolation
# ├───0003-mpst-protocol-validation
# └───0004-56-module-5-layer-architecture
```

---

### Phase 4: File Migration with Backup

**Goal:** Move ADR files to new structure, update links, create backup.

**CRITICAL PREREQUISITE: Update Migration Script Mapping**

Before running migration, you MUST update `scripts/ADR_scripts/phase4_file_migration.py` with the correct categorization for your ADR series.

#### Step 4.0: Update DEFAULT_MIGRATION_MAP

Edit `scripts/ADR_scripts/phase4_file_migration.py` and add your ADR mappings to `DEFAULT_MIGRATION_MAP`:

```python
# Default migration mapping (can be extended via command line)
DEFAULT_MIGRATION_MAP = {
    # ... existing mappings ...

    # YOUR NEW SERIES (example: series 11-20)
    "0011": ("07-contracts-serialization/0011-flatbuffers-serialization", "flatbuffers-serialization"),
    "0012": ("07-contracts-serialization/0012-76-flatbuffers-schemas", "76-flatbuffers-schemas"),
    "0013": ("07-contracts-serialization/0013-pipeline-versioning-policy", "pipeline-versioning-policy"),
    "0014": ("09-communication/0014-json-rest-api-dual-format", "json-rest-api-dual-format"),
    "0015": ("09-communication/0015-websocket-binary-protocol", "websocket-binary-protocol"),
    "0016": ("09-communication/0016-sse-event-schemas", "sse-event-schemas"),
    "0017": ("03-layer2-orchestration/0017-sessionstate-6-section-design", "sessionstate-6-section-design"),
    "0018": ("05-layer4-runtime/0018-3-tier-eviction-strategy", "3-tier-eviction-strategy"),
    "0019": ("07-contracts-serialization/0019-flatbuffers-sessionstate-serialization", "flatbuffers-sessionstate-serialization"),
    "0020": ("06-layer5-infrastructure/0020-multi-tier-storage", "multi-tier-storage"),
}
```

**Tuple Format:** `("category/family-folder", "slug")`

- First element: Full path from `docs/architecture/decisions/` (category + family folder)
- Second element: URL-friendly slug (used for parent ADR filename normalization)

**⚠️ WARNING:** If you skip this step, the script will default ALL unknown ADRs to `03-layer2-orchestration/`, which is almost always WRONG.

#### Step 4.1: Dry Run (Simulation)

```powershell
# Test migration WITHOUT actually moving files (default behavior)
$env:PYTHONIOENCODING="utf-8"  # Fix Unicode emoji encoding issues
.venv\Scripts\python.exe scripts\ADR_scripts\phase4_file_migration.py `
  --adrs 0011 0012 0013 0014 0015 0016 0017 0018 0019 0020

# Expected output:
# � Migrating ADRs: 0011, 0012, 0013, 0014, 0015, 0016, 0017, 0018, 0019, 0020
# ═══════════════════════════════════════════════════════════
# PHASE 4: FILE MIGRATION (DRY RUN)
# ═══════════════════════════════════════════════════════════
#
# � Creating folder structure...
#   [DRY-RUN] Would create: docs\architecture\decisions\07-contracts-serialization
#   [DRY-RUN] Would create: docs\architecture\decisions\09-communication
#   ...
#
# 📦 Moving ADR-0011 family...
#   [DRY-RUN] 0011-flatbuffers-serialization.md → 07-contracts-serialization\0011-flatbuffers-serialization\0011.md
#   ...
#
# 💾 [DRY-RUN] Would create backup in: adr_migration_backup/
#
# 📊 Summary:
#   - Files moved: 52
#   - Errors: 0
#
# 💡 This was a DRY RUN. No files were actually moved.
#    Run with --live flag to perform actual migration.
```

**Note:** The script does NOT have a `--dry-run` flag. Dry-run is the DEFAULT behavior. You must explicitly use `--live` to actually move files.

#### Step 4.2: Review Dry Run Output

**Checklist:**

- ✅ All parent ADRs found (0001.md, 0002.md, 0003.md, 0004.md)
- ✅ All sub-ADRs found (0001a-e, 0002a-d, etc.)
- ✅ Target paths correct (`01-foundation/<family>/<file>.md`)
- ✅ File count matches expectation (22 files for families 0001-0004)

#### Step 4.3: Execute Migration (LIVE)

```powershell
# ACTUAL MIGRATION - creates backup, moves files, updates links
$env:PYTHONIOENCODING="utf-8"  # Fix Unicode emoji encoding issues
.venv\Scripts\python.exe scripts\ADR_scripts\phase4_file_migration.py `
  --adrs 0011 0012 0013 0014 0015 0016 0017 0018 0019 0020 `
  --live

# Expected output:
# 🚀 LIVE MIGRATION MODE - Files will be moved
# ═══════════════════════════════════════════════════════════
#
# � Creating folder structure...
#   Created: docs\architecture\decisions\07-contracts-serialization
#   Created: docs\architecture\decisions\09-communication
#   ...
#
# 💾 Creating backup...
#   ✅ Backup created: adr_migration_backup/20251103_164049/
#
# 📦 Moving ADR-0011 family...
#   ✅ 0011.md → 07-contracts-serialization/0011-flatbuffers-serialization/0011.md
#   ✅ 0011a-flatbuffers-schema-design-principles.md → 07-contracts-serialization/0011-flatbuffers-serialization/0011a-flatbuffers-schema-design-principles.md
#   ... (continue for all sub-ADRs)
#
# ... (continue for families 0012-0020)
#
# 🔗 Updating internal links in moved ADRs...
#   📝 0011a-flatbuffers-schema-design-principles.md (2 links)
#   ... (all internal links updated)
#
# 🔗 Updating external references to moved ADRs...
#   Found 168 files with references to moved ADRs
#   📝 docs\plans\concierge_dag_enhancement_plan.md (1 references)
#   ... (all external references updated)
#
# ✅ Migration complete: 52 files moved
# 📁 Backup location: adr_migration_backup/20251103_164049/
```

#### Step 4.4: Verify Migration Success

```powershell
# Check files moved
Get-ChildItem docs\architecture\decisions\01-foundation\*\*.md -Recurse | Measure-Object
# Expected: Count = 22

# Check backup exists
Get-ChildItem adr_migration_backup\*\*.md -Recurse | Measure-Object
# Expected: Count = 22

# Check original location empty (for migrated ADRs)
Get-ChildItem docs\architecture\decisions\000[1-4]*.md
# Expected: Empty (all moved)
```

---

### Phase 5: Post-Migration Validation & Index Rebuild

**Goal:** Update all indices, validate links, fix any issues.

#### Step 5.1: Rebuild Main ADR Index

```powershell
# Rebuild index with new file paths
.venv\Scripts\python.exe scripts\ADR_scripts\build_adr_index.py

# Expected output:
# 🔍 Scanning D:\familyos\docs\architecture\decisions for ADR files...
# 📄 Found 355 ADR files
#   ✅ 0001: K0/K1 Kernel Split Architecture
#   ✅ 0002: Actor Model for Agent Isolation
# ... (all ADRs)
#
# 🔄 Updating folder-level index.yml files...
#   ✅ Updated 01-foundation/index.yml (22 ADRs)
#
# ✅ Index saved to D:\familyos\docs\architecture\decisions\00-meta\adr_index.json
#
# 📊 ADR Index Summary
# ═══════════════════════════════════════════════════════════
# 📈 Total ADRs: 355
# 📁 By Category:
#   01-foundation: 22
#   (remaining in flat structure): 333
```

#### Step 5.2: Validate Folder Index

```powershell
# Check folder index was populated
Get-Content docs\architecture\decisions\01-foundation\index.yml | Select-Object -First 20

# Expected:
# # ADR Category Index: 01-foundation
# # Auto-generated by build_adr_index.py
# # Last updated: 2025-11-03T13:38:43.054632
#
# category: 01-foundation
# total_adrs: 22
#
# adrs:
#   - adr_number: "0001"
#     title: "K0/K1 Kernel Split Architecture"
#     status: ACCEPTED
#     file_path: "01-foundation\0001-k0-k1-kernel-split\0001.md"
#     ... (metadata)
```

#### Step 5.3: Scan for Broken Links

```powershell
# Find broken ADR links in migrated files
.venv\Scripts\python.exe scripts\ADR_scripts\update_adr_links.py `
  --scan-only `
  --folder 01-foundation

# Expected output:
# 🔍 Scanning for ADR links in 01-foundation/
# 📊 Found 29 broken links:
#   ⚠️  0001.md: Link to ADR-0064 (does not exist)
#   ⚠️  0002.md: Link to ADR-0072 (does not exist)
#   ... (mostly links to future/placeholder ADRs)
#
# 💡 To fix broken links: python scripts/ADR_scripts/update_adr_links.py --fix
```

#### Step 5.4: Fix Critical Broken Links (Optional)

```powershell
# Fix links to migrated ADRs (if any)
.venv\Scripts\python.exe scripts\ADR_scripts\update_adr_links.py `
  --fix `
  --folder 01-foundation

# Note: Links to non-existent placeholder ADRs (0064, 0072, etc.)
# will remain broken until those ADRs are created. Document these.
```

#### Step 5.5: Validate Metadata (Final Check)

```powershell
# Ensure all migrated ADRs still have valid metadata
.venv\Scripts\python.exe scripts\ADR_scripts\validate_adr_metadata.py `
  docs\architecture\decisions\01-foundation\**\*.md

# Expected: All ✅ (zero errors)
```

---

### Phase 6: Generate Propagation Maps

**Goal:** Create layer-based propagation maps for architecture tracking.

#### Step 6.1: Generate Maps

```powershell
# Generate propagation maps for all 5 layers
.venv\Scripts\python.exe scripts\ADR_scripts\generate_propagation_maps.py

# Expected output:
# 📊 Loaded index: 355 ADRs
#
# 🔄 Generating propagation maps...
# 📁 Output directory: D:\familyos\docs\architecture\decisions\00-meta\propagation_maps
#
# ✅ Created docs\architecture\decisions\00-meta\propagation_maps\layer1_input.yml
#    📊 199 ADRs, 1 modules
# ✅ Created docs\architecture\decisions\00-meta\propagation_maps\layer2_orchestration.yml
#    📊 174 ADRs, 0 modules
# ✅ Created docs\architecture\decisions\00-meta\propagation_maps\layer3_execution.yml
#    📊 268 ADRs, 0 modules
# ✅ Created docs\architecture\decisions\00-meta\propagation_maps\layer4_runtime.yml
#    📊 341 ADRs, 0 modules
# ✅ Created docs\architecture\decisions\00-meta\propagation_maps\layer5_infrastructure.yml
#    📊 233 ADRs, 0 modules
#
# ✅ Propagation maps generation complete
# 📁 Maps location: docs\architecture\decisions\00-meta\propagation_maps
# 📊 Generated 5 layer maps
```

#### Step 6.2: Validate Propagation Maps

```powershell
# Verify migrated ADRs appear in maps
rg "01-foundation" docs\architecture\decisions\00-meta\propagation_maps\*.yml -l

# Expected: All 5 layer maps (layer1_input.yml through layer5_infrastructure.yml)

# Count references to migrated ADRs
(rg "file_path.*01-foundation" docs\architecture\decisions\00-meta\propagation_maps\).Count

# Expected: 97 references (22 ADRs × ~5 layers each affected)
```

#### Step 6.3: Test Propagation Map Queries

```powershell
# View specific layer map
Get-Content docs\architecture\decisions\00-meta\propagation_maps\layer5_infrastructure.yml | Select-Object -First 50

# Search for specific ADR in map
rg "K0/K1 Kernel Split" docs\architecture\decisions\00-meta\propagation_maps\layer5_infrastructure.yml -B 2 -A 2
```

---

### Phase 7: Final Validation & Testing

**Goal:** Comprehensive validation before committing changes.

#### Step 7.1: Run Full Validation Suite

```powershell
Write-Host "`n=== FINAL VALIDATION SUITE ===" -ForegroundColor Cyan

# 1. Validate all ADR metadata
Write-Host "`n1️⃣ Validating ADR metadata..." -ForegroundColor Yellow
.venv\Scripts\python.exe scripts\ADR_scripts\validate_adr_metadata.py `
  docs\architecture\decisions\01-foundation\**\*.md

# 2. Validate index is up-to-date
Write-Host "`n2️⃣ Validating ADR index..." -ForegroundColor Yellow
.venv\Scripts\python.exe scripts\ADR_scripts\build_adr_index.py --validate

# 3. Validate propagation maps
Write-Host "`n3️⃣ Validating propagation maps..." -ForegroundColor Yellow
.venv\Scripts\python.exe scripts\ADR_scripts\generate_propagation_maps.py --validate

# 4. Check file counts
Write-Host "`n4️⃣ Checking file counts..." -ForegroundColor Yellow
$migrated = (Get-ChildItem docs\architecture\decisions\01-foundation\*\*.md -Recurse).Count
$backup = (Get-ChildItem adr_migration_backup\*\*.md -Recurse).Count
Write-Host "  Migrated files: $migrated"
Write-Host "  Backup files: $backup"
if ($migrated -eq $backup) {
    Write-Host "  ✅ File counts match" -ForegroundColor Green
} else {
    Write-Host "  ❌ File count mismatch!" -ForegroundColor Red
}

# 5. Test ADR queries
Write-Host "`n5️⃣ Testing ADR queries..." -ForegroundColor Yellow
.venv\Scripts\python.exe scripts\ADR_scripts\query_adrs.py "kernel split"
.venv\Scripts\python.exe scripts\ADR_scripts\query_adrs.py "actor model"
```

#### Step 7.2: Generate Migration Summary

```powershell
Write-Host "`n=== MIGRATION SUMMARY ===" -ForegroundColor Green

Write-Host "`nPhase Results:" -ForegroundColor Cyan
Write-Host "  ✅ Phase 1: Metadata added to 22 ADR files"
Write-Host "  ✅ Phase 2: Link audit completed (1,345 refs TO, 180 FROM)"
Write-Host "  ✅ Phase 3: Folder structure created (01-foundation/)"
Write-Host "  ✅ Phase 4: 22 files migrated, backup created"
Write-Host "  ✅ Phase 5: Index rebuilt, folder index populated"
Write-Host "  ✅ Phase 6: 5 propagation maps generated"
Write-Host "  ✅ Phase 7: All validations passed"

Write-Host "`nMigrated Structure:" -ForegroundColor Cyan
Write-Host "  docs/architecture/decisions/"
Write-Host "    ├── 01-foundation/"
Write-Host "    │   ├── index.yml (✅ 22 ADRs)"
Write-Host "    │   ├── 0001-k0-k1-kernel-split/ (6 files)"
Write-Host "    │   ├── 0002-actor-model-agent-isolation/ (5 files)"
Write-Host "    │   ├── 0003-mpst-protocol-validation/ (5 files)"
Write-Host "    │   └── 0004-56-module-5-layer-architecture/ (6 files)"
Write-Host "    └── 333 ADRs remaining in flat structure"

Write-Host "`nProgress:" -ForegroundColor Cyan
Write-Host "  📊 6% complete (22/355 files)"
Write-Host "  📁 1/14 categories populated (01-foundation)"

Write-Host "`nNext Steps:" -ForegroundColor Magenta
Write-Host "  1. Review migration results"
Write-Host "  2. Commit changes to git"
Write-Host "  3. Migrate next ADR family (0005+)"
Write-Host "  4. Repeat process for remaining 333 ADRs"
```

---

## 🎯 Success Criteria Checklist

After completing all phases, verify:

### Files & Structure

- [ ] All migrated ADRs moved to `01-foundation/<family>/` folders
- [ ] Parent ADR renamed to `<number>.md` (e.g., `0001.md`)
- [ ] Sub-ADRs keep original names (e.g., `0001a-k0-bridge-communication-protocol.md`)
- [ ] Backup created in `adr_migration_backup/<timestamp>/`
- [ ] Original flat location empty for migrated ADRs
- [ ] Folder count matches: `tree 01-foundation` shows 4 family folders

### Metadata & Indices

- [ ] All ADRs have valid YAML frontmatter (run `validate_adr_metadata.py`)
- [ ] Main index updated (`00-meta/adr_index.json` contains 355 ADRs)
- [ ] Folder index populated (`01-foundation/index.yml` contains 22 ADRs)
- [ ] Propagation maps generated (5 files in `00-meta/propagation_maps/`)
- [ ] Migrated ADRs appear in propagation maps (search for "01-foundation")

### Links & References

- [ ] No broken links TO migrated ADRs (run `update_adr_links.py --scan-only`)
- [ ] All links FROM migrated ADRs valid (except documented placeholders)
- [ ] Diagram references still valid (check `architecture_diagrams/`)
- [ ] Cross-references between ADRs intact

### Validation

- [ ] `build_adr_index.py --validate` passes ✅
- [ ] `generate_propagation_maps.py --validate` passes ✅
- [ ] `query_adrs.py "kernel split"` returns results ✅
- [ ] File counts match (migrated = backup) ✅

---

## 🔧 Troubleshooting

### Issue: "All ADRs migrated to wrong category (e.g., all in 03-layer2-orchestration/)"

**Symptoms:**

```
📦 Moving ADR-0011 family...
  [DRY-RUN] 0011-flatbuffers-serialization.md → 03-layer2-orchestration\0011-flatbuffers-serialization\0011.md
📦 Moving ADR-0012 family...
  [DRY-RUN] 0012-76-flatbuffers-schemas.md → 03-layer2-orchestration\0012-76-flatbuffers-schemas\0012.md
📦 Moving ADR-0017 family...
  [DRY-RUN] 0017-sessionstate-6-section-design.md → 03-layer2-orchestration\0017-sessionstate-6-section-design\0017.md
```

**Cause:** Missing migration mapping in `scripts/ADR_scripts/phase4_file_migration.py`. The script defaults unknown ADRs to `03-layer2-orchestration/`.

**Fix:**

1. Open `scripts/ADR_scripts/phase4_file_migration.py`
2. Find `DEFAULT_MIGRATION_MAP` dictionary (around line 20)
3. Add your ADR mappings with correct semantic categorization:

```python
DEFAULT_MIGRATION_MAP = {
    # ... existing mappings ...

    # Add your series with CORRECT categories (by semantic purpose)
    "0011": ("07-contracts-serialization/0011-flatbuffers-serialization", "flatbuffers-serialization"),
    "0017": ("03-layer2-orchestration/0017-sessionstate-6-section-design", "sessionstate-6-section-design"),
    "0018": ("05-layer4-runtime/0018-3-tier-eviction-strategy", "3-tier-eviction-strategy"),
    "0020": ("06-layer5-infrastructure/0020-multi-tier-storage", "multi-tier-storage"),
}
```

4. Re-run dry-run to verify correct categorization
5. If migration already executed incorrectly, restore from backup and re-run

**Prevention:** ALWAYS update `DEFAULT_MIGRATION_MAP` BEFORE running Phase 4.

---

### Issue: "UnicodeEncodeError: 'charmap' codec can't encode character"

**Symptoms:**

```
Traceback (most recent call last):
  File "scripts/ADR_scripts/phase4_file_migration.py", line 463
    print(f"📋 Migrating ADRs: {', '.join(sorted(migration_map.keys()))}")
UnicodeEncodeError: 'charmap' codec can't encode character '\U0001f4cb' in position 0
```

**Cause:** PowerShell console using Windows-1252 encoding, can't display Unicode emojis in Python script output.

**Fix:**

Add `$env:PYTHONIOENCODING="utf-8"` before running Python scripts:

```powershell
# Set UTF-8 encoding for Python output
$env:PYTHONIOENCODING="utf-8"
.venv\Scripts\python.exe scripts\ADR_scripts\phase4_file_migration.py --adrs 0011 0012 --live
```

**Alternative:** Redirect output through `Out-String` (loses colors):

```powershell
.venv\Scripts\python.exe scripts\ADR_scripts\phase4_file_migration.py --adrs 0011 0012 2>&1 | Out-String
```

---

### Issue: "YAML parsing error" during validation

**Symptoms:**

```
❌ 0001.md: YAML parsing error: mapping values are not allowed here
```

**Cause:** Indentation error in YAML frontmatter (likely tabs instead of spaces)

**Fix:**

1. Open file in VS Code
2. Check YAML frontmatter indentation
3. Replace tabs with 2 spaces
4. Ensure lists use `- item` format (dash + space)

---

### Issue: "FileNotFoundError" during migration

**Symptoms:**

```
❌ Error moving 0001a.md: File not found
```

**Cause:** Sub-ADR filename doesn't match expected pattern

**Fix:**

1. Check actual filename: `Get-ChildItem docs\architecture\decisions\0001*.md`
2. Update migration script's ADR family mapping
3. Verify filename matches: `<number><letter>-<title>.md`

---

### Issue: Broken links after migration

**Symptoms:**

```
⚠️ 29 broken links found in 01-foundation/
```

**Cause:** Links to non-existent placeholder ADRs (future work)

**Fix:**

1. Review link audit report: `code LINK_AUDIT_REPORT_0001-0004.md`
2. Identify placeholder ADRs (e.g., ADR-0064, ADR-0072)
3. Document placeholders in `docs/architecture/decisions/00-meta/PLACEHOLDER_ADRS.md`
4. Fix only critical broken links (links to migrated ADRs)

---

### Issue: Folder index not populated

**Symptoms:**

```
01-foundation/index.yml shows "# Populated by build_adr_index.py script" but no ADRs
```

**Cause:** Old version of `build_adr_index.py` without folder index generation

**Fix:**

1. Verify script has `update_folder_indices()` method
2. Re-run: `.venv\Scripts\python.exe scripts\ADR_scripts\build_adr_index.py`
3. Check output shows: `✅ Updated 01-foundation/index.yml (22 ADRs)`

---

### Issue: Propagation maps show 0 modules

**Symptoms:**

```
✅ Created layer5_infrastructure.yml
   📊 233 ADRs, 0 modules
```

**Cause:** Module paths in ADR frontmatter don't match layer prefix pattern

**Expected:** Module extraction looks for `k1/l<X>_<layer>` pattern

- Layer 1: `k1/l1_input/*`
- Layer 2: `k1/l2_orchestration/*`
- Layer 3: `k1/l3_execution/*`
- Layer 4: `k1/l4_runtime/*`
- Layer 5: `k1/l5_infrastructure/*`

**Fix:**

1. Update ADR frontmatter `affected_modules` to use correct path format
2. Re-run: `.venv\Scripts\python.exe scripts\ADR_scripts\generate_propagation_maps.py`

---

## 📝 Notes & Best Practices

### Migration Batching

**Recommended:** Migrate 1-2 ADR families at a time (5-10 ADRs)

- Easier to validate
- Smaller git commits
- Faster rollback if issues

**Not Recommended:** Migrate all 333 ADRs at once

- Hard to validate
- Massive git commit
- Difficult to debug issues

### Backup Strategy

**Always create backup before migration:**

```powershell
# Manual backup (if migration script doesn't create one)
Copy-Item docs\architecture\decisions\000[1-4]*.md `
  -Destination adr_migration_backup_manual_$(Get-Date -Format 'yyyyMMdd_HHmmss')\
```

**Backup retention:**

- Keep backups for 30 days after successful migration
- Delete after validation passes and changes committed to git

### Git Workflow

**Recommended commit sequence:**

```bash
# 1. Add metadata changes only (no file moves)
git add docs/architecture/decisions/000[1-4]*.md
git commit -m "feat(adr): Add metadata to ADR families 0001-0004"

# 2. Run migration and commit structure changes
git add docs/architecture/decisions/01-foundation/
git add docs/architecture/decisions/00-meta/
git rm docs/architecture/decisions/000[1-4]*.md
git commit -m "feat(adr): Migrate ADR families 0001-0004 to 01-foundation/"

# 3. Commit updated indices and maps
git add docs/architecture/decisions/00-meta/adr_index.json
git add docs/architecture/decisions/00-meta/propagation_maps/
git commit -m "feat(adr): Update indices and propagation maps"
```

### Testing Queries

**After migration, test these queries work:**

```powershell
# 1. Semantic search
.venv\Scripts\python.exe scripts\ADR_scripts\query_adrs.py "kernel split"
.venv\Scripts\python.exe scripts\ADR_scripts\query_adrs.py "actor model"

# 2. Layer filtering
.venv\Scripts\python.exe scripts\ADR_scripts\query_adrs.py --layer layer5_infrastructure

# 3. Status filtering
.venv\Scripts\python.exe scripts\ADR_scripts\query_adrs.py --status ACCEPTED

# 4. Statistics
.venv\Scripts\python.exe scripts\ADR_scripts\query_adrs.py "" --stats
```

---

## 🚀 Quick Reference Commands

### Migration Workflow (Copy-Paste Ready)

```powershell
# PHASE 1: Add metadata to ADRs (manual editing)
# Edit each ADR file to add YAML frontmatter

# PHASE 2: Validate metadata
.venv\Scripts\python.exe scripts\ADR_scripts\validate_adr_metadata.py docs\architecture\decisions\000[1-4]*.md

# PHASE 3: Link audit
.venv\Scripts\python.exe scripts\ADR_scripts\phase3_link_audit_scoped.py --adrs 0001 0002 0003 0004

# PHASE 4: Create folders
New-Item -ItemType Directory -Force -Path "docs\architecture\decisions\01-foundation\0001-k0-k1-kernel-split"
New-Item -ItemType Directory -Force -Path "docs\architecture\decisions\01-foundation\0002-actor-model-agent-isolation"
New-Item -ItemType Directory -Force -Path "docs\architecture\decisions\01-foundation\0003-mpst-protocol-validation"
New-Item -ItemType Directory -Force -Path "docs\architecture\decisions\01-foundation\0004-56-module-5-layer-architecture"

# PHASE 5: Dry run migration
.venv\Scripts\python.exe scripts\ADR_scripts\phase4_file_migration.py --adrs 0001 0002 0003 0004 --dry-run

# PHASE 6: Execute migration (LIVE)
.venv\Scripts\python.exe scripts\ADR_scripts\phase4_file_migration.py --adrs 0001 0002 0003 0004 --live

# PHASE 7: Rebuild indices
.venv\Scripts\python.exe scripts\ADR_scripts\build_adr_index.py

# PHASE 8: Generate propagation maps
.venv\Scripts\python.exe scripts\ADR_scripts\generate_propagation_maps.py

# PHASE 9: Final validation
.venv\Scripts\python.exe scripts\ADR_scripts\build_adr_index.py --validate
.venv\Scripts\python.exe scripts\ADR_scripts\generate_propagation_maps.py --validate
```

---

## 📚 Related Documentation

- **ADR Reorganization Plan:** `docs/architecture/decisions/ADR_REORGANIZATION_PLAN.md`
- **Migration Scripts:** `scripts/ADR_scripts/`
- **Link Audit Report:** `LINK_AUDIT_REPORT_0001-0004.md` (generated per migration)
- **Propagation Maps:** `docs/architecture/decisions/00-meta/propagation_maps/`

---

## ✅ Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2025-11-03 | Initial documentation (validated with ADRs 0001-0004) | K1 Architecture Team |
| 1.1 | 2025-11-03 | Added categorization guidance and series 11-20 lessons learned | K1 Architecture Team |

---

## 📚 Lessons Learned (Series 11-20 Migration)

### ✅ What Went Well

1. **5-Phase Process Works** - The structured approach with link audit, dry-run, and validation prevented issues
2. **Link Audit Comprehensive** - Ripgrep found 2,166 references TO ADRs and 209 references FROM ADRs
3. **Backup System Reliable** - Timestamped backup enabled quick rollback when categorization was wrong
4. **Script Automation** - Automated link updates saved hours of manual work

### ❌ What Went Wrong

1. **Categorization Error** - Initial migration placed SessionState (0017), Eviction (0018), and Storage (0020) in `02-layer1-input/` when they belonged in orchestration/runtime/infrastructure
2. **Root Cause** - Script's `DEFAULT_MIGRATION_MAP` was missing entries for series 11-20, defaulted to `03-layer2-orchestration/`
3. **Affected ADRs** - 52 files initially placed in wrong categories before rollback

### 🎯 Key Takeaways

1. **Semantic Purpose > Affected Layers** - Categorize by WHAT OWNS the concern, not what touches it
2. **Always Update Migration Map First** - Edit `DEFAULT_MIGRATION_MAP` in `phase4_file_migration.py` BEFORE Phase 4
3. **Dry-Run is Default** - Script defaults to dry-run; must use `--live` flag explicitly
4. **UTF-8 Encoding Required** - Set `$env:PYTHONIOENCODING="utf-8"` for emoji support in PowerShell
5. **Cross-Cutting ≠ Uncategorizable** - Many ADRs affect all 5 layers but still have ONE clear owner

### 📋 Checklist: Before Migrating Next Series

- [ ] Read ADR titles and content to understand semantic purpose
- [ ] Decide category based on architectural ownership (not `affected_layers`)
- [ ] Update `scripts/ADR_scripts/phase4_file_migration.py` with `DEFAULT_MIGRATION_MAP` entries
- [ ] Create target folder structure manually (Phase 3)
- [ ] Run dry-run and verify categories are correct
- [ ] Set `$env:PYTHONIOENCODING="utf-8"` before running migration
- [ ] Run `--live` migration only after dry-run verification
- [ ] Rebuild indices with `build_adr_index.py`

---

**Next Update:** After migrating ADR families 0021-0030, update this document with any new lessons learned.
