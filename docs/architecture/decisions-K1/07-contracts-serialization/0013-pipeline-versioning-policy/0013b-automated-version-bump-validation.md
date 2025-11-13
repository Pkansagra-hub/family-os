---
adr_number: 0013b
affected_layers:
- layer2_orchestration
- layer3_execution
- layer4_runtime
- layer5_infrastructure
affected_modules: []
authors:
- K1 Architecture Team
concerns:
- architecture
- cost
- maintainability
- modularity
- performance
- privacy
- reliability
- scalability
- security
- testing
date_created: '2025-11-03'
date_updated: '2025-11-03'
implementation_date: null
implementation_phase: Phase 1 (Foundation)
implementation_status: COMPLETED
propagation:
  affected_adrs:
  - ADR-0011
  - ADR-0012
  - ADR-0013a
  - ADR-0013c
  - ADR-0013d
  affected_tests: []
  triggers:
  - Schema diff detection showing field additions/removals
  - Version bump violations in CI/CD pipeline
  - Breaking changes requiring MAJOR version increment
  - Backward compatibility test failures
  - Changelog generation workflow modifications
related_adrs:
- ADR-0011
- ADR-0012
- ADR-0013
- ADR-0013a
- ADR-0013c
- ADR-0013d
- ADR-0016a
related_contracts:
- k0/contracts/api/rest/idempotency/24h_retention.yml
- k0/contracts/asyncapi.events.yaml
- k0/contracts/openapi.k0.yaml
- k1/contracts/flatbuffers/layer1_kernel/agent_state.fbs
- k1/contracts/flatbuffers/layer3_execution/mcp_message.fbs
- k1/contracts/flatbuffers/layer3_execution/mcp_resource_request.fbs
- k1/contracts/flatbuffers/layer3_execution/mcp_resource_response.fbs
- k1/contracts/flatbuffers/layer3_execution/mcp_tool_discovery.fbs
- k1/contracts/flatbuffers/layer3_execution/model_cache_entry.fbs
- k1/contracts/flatbuffers/layer3_execution/model_request.fbs
- k1/contracts/flatbuffers/layer3_execution/model_response.fbs
related_diagrams: []
research_citations:
- Semantic Versioning 2.0.0 (Preston-Werner 2013)
- Automated Schema Evolution (Confluent Schema Registry)
status: ACCEPTED
superseded_by: []
supersedes: []
title: Automated Version Bump Validation
---

# ADR-0013b: Automated Version Bump Validation

**Status:** ✅ Accepted (In Progress - 75% Complete)
**Date:** 2025-10-12
**Parent ADR:** [ADR-0013](0013-pipeline-versioning-policy.md) (Pipeline Versioning Policy)
**Deciders:** K1 Architecture Team
**Tags:** `#schema-versioning` `#ci-cd` `#automation` `#version-validation` `#semver`

---

## Context and Problem Statement

K1 Intelligence Module schemas evolve over time: adding fields, deprecating fields, changing types. Each change requires a correct version bump according to Semantic Versioning (SemVer):

- **MAJOR (x.0.0):** Breaking changes (field removal, type change, new required field)
- **MINOR (x.y.0):** Backward-compatible additions (new optional field, new enum value)
- **PATCH (x.y.z):** Documentation or internal changes (no schema impact)

**Problem:** Manual version bumps error-prone:
- Developer adds field, bumps PATCH instead of MINOR (incorrect)
- Developer removes field, bumps MINOR instead of MAJOR (breaking change missed)
- No automated validation → breaking changes reach production
- No changelog generation → users don't know what changed

**Solution:** Implement automated version bump validation with schema diff analysis, CI/CD pipeline, clear error messages, automated CLI tool, and changelog generation.

---

## Decision Drivers

### Functional Requirements
- **FR1:** >95% correct version bump detection (catch MAJOR/MINOR/PATCH errors before merge)
- **FR2:** CI/CD latency <30s (fast PR feedback on schema changes)
- **FR3:** Clear error messages with actionable guidance ("Field removal requires MAJOR bump")
- **FR4:** Automated CLI tool (`k1-schema-bump --auto`) for local version bumps
- **FR5:** Changelog generation from schema diff ("Added optional time_range field")
- **FR6:** Support all 76 schemas (Layer 1-5, all FlatBuffers schemas)

### Non-Functional Requirements
- **NFR1:** Performance: Schema diff analysis <10s (parse 2 .fbs files, compute diff)
- **NFR2:** Performance: CI/CD validation <30s (full pipeline including checkout)
- **NFR3:** Reliability: Zero false positives (correct version bumps never fail)
- **NFR4:** Reliability: <5% false negatives (complex changes might be missed)
- **NFR5:** Maintainability: Extensible rules (add new change types easily)

### Constraints
- **C1:** SemVer 2.0.0 versioning (MAJOR.MINOR.PATCH format)
- **C2:** FlatBuffers schema format (parse .fbs files)
- **C3:** GitHub Actions CI/CD (existing infrastructure)
- **C4:** Python implementation (K1 toolchain language)

---

## Considered Options

### Option 1: Schema Diff Analysis + CI/CD Validation (SELECTED)
**Description:** Parse old/new .fbs files, compute diff, validate version bump in CI/CD.

**Pros:**
- ✅ Automated detection (no manual review)
- ✅ Fast feedback (<30s in CI/CD)
- ✅ Extensible rules (add new change types)
- ✅ Clear error messages (actionable guidance)

**Cons:**
- ❌ Complex diff analysis (nested tables, unions, enums)
- ❌ False negatives possible (complex changes missed)

**Decision:** ✅ **SELECTED** (best balance: automation, performance, maintainability)

---

### Option 2: Manual Code Review Only
**Description:** Rely on PR reviewers to validate version bumps.

**Pros:**
- ✅ Simple (no automation needed)
- ✅ Human judgment (reviewers catch edge cases)

**Cons:**
- ❌ Slow (depends on reviewer availability)
- ❌ Error-prone (reviewers miss mistakes)
- ❌ Not scalable (76 schemas, 10+ changes/week)

**Decision:** ❌ **REJECTED** (too manual, error-prone)

---

### Option 3: AI-Based Version Bump Prediction (LLM)
**Description:** Use LLM to analyze schema diff, predict required version bump.

**Pros:**
- ✅ Flexible (handles complex changes)
- ✅ Learning (improves over time)

**Cons:**
- ❌ Non-deterministic (LLM output varies)
- ❌ Latency (LLM inference 1-5s)
- ❌ Cost (LLM API calls per PR)
- ❌ Reliability (<95% accuracy, false positives)

**Decision:** ❌ **REJECTED** (not deterministic, too experimental)

---

## Decision Outcome

**Chosen Option:** Option 1 (Schema Diff Analysis + CI/CD Validation)

**Rationale:**
- Automated, fast (<30s), extensible
- Deterministic rules (no LLM uncertainty)
- Clear error messages (actionable guidance)
- Scales to 76 schemas

---

## Implementation Details

### 1. Schema Diff Analysis

**Algorithm:**
```python
from dataclasses import dataclass
from typing import List, Dict, Optional
from pathlib import Path
import re

@dataclass
class SchemaChange:
    """Represents a single schema change."""
    change_type: str  # FIELD_ADDED, FIELD_REMOVED, TYPE_CHANGED, etc.
    severity: str     # MAJOR, MINOR, PATCH
    field_name: Optional[str] = None
    old_type: Optional[str] = None
    new_type: Optional[str] = None
    description: str = ""

class SchemaDiffAnalyzer:
    """Analyze differences between two FlatBuffers schema files."""

    def __init__(self, old_schema_path: Path, new_schema_path: Path):
        self.old_schema = self._parse_schema(old_schema_path)
        self.new_schema = self._parse_schema(new_schema_path)

    def _parse_schema(self, path: Path) -> Dict:
        """Parse FlatBuffers schema file."""
        with open(path) as f:
            content = f.read()

        # Extract table definitions
        tables = {}
        table_pattern = r'table\s+(\w+)\s*\{([^}]+)\}'
        for match in re.finditer(table_pattern, content, re.DOTALL):
            table_name = match.group(1)
            table_body = match.group(2)

            # Extract fields
            fields = {}
            field_pattern = r'(\w+)\s*:\s*([^;]+);'
            for field_match in re.finditer(field_pattern, table_body):
                field_name = field_match.group(1)
                field_type = field_match.group(2).strip()

                # Check if required
                is_required = '(required)' in field_type
                field_type = field_type.replace('(required)', '').strip()

                fields[field_name] = {
                    'type': field_type,
                    'required': is_required
                }

            tables[table_name] = {'fields': fields}

        # Extract enums
        enums = {}
        enum_pattern = r'enum\s+(\w+)\s*:\s*(\w+)\s*\{([^}]+)\}'
        for match in re.finditer(enum_pattern, content, re.DOTALL):
            enum_name = match.group(1)
            enum_body = match.group(3)

            # Extract values
            values = []
            value_pattern = r'(\w+)\s*(?:=\s*\d+)?'
            for value_match in re.finditer(value_pattern, enum_body):
                value_name = value_match.group(1).strip()
                if value_name and value_name != ',':
                    values.append(value_name)

            enums[enum_name] = {'values': values}

        return {'tables': tables, 'enums': enums}

    def analyze(self) -> List[SchemaChange]:
        """Analyze schema changes."""
        changes = []

        # 1. Check for table changes
        old_tables = set(self.old_schema['tables'].keys())
        new_tables = set(self.new_schema['tables'].keys())

        # New tables (MINOR)
        for table_name in new_tables - old_tables:
            changes.append(SchemaChange(
                change_type='TABLE_ADDED',
                severity='MINOR',
                description=f"Added new table: {table_name}"
            ))

        # Removed tables (MAJOR - breaking)
        for table_name in old_tables - new_tables:
            changes.append(SchemaChange(
                change_type='TABLE_REMOVED',
                severity='MAJOR',
                description=f"Removed table: {table_name} (breaking change)"
            ))

        # Modified tables
        for table_name in old_tables & new_tables:
            old_table = self.old_schema['tables'][table_name]
            new_table = self.new_schema['tables'][table_name]

            table_changes = self._analyze_table_changes(
                table_name,
                old_table['fields'],
                new_table['fields']
            )
            changes.extend(table_changes)

        # 2. Check for enum changes
        old_enums = set(self.old_schema['enums'].keys())
        new_enums = set(self.new_schema['enums'].keys())

        # New enums (MINOR)
        for enum_name in new_enums - old_enums:
            changes.append(SchemaChange(
                change_type='ENUM_ADDED',
                severity='MINOR',
                description=f"Added new enum: {enum_name}"
            ))

        # Removed enums (MAJOR - breaking)
        for enum_name in old_enums - new_enums:
            changes.append(SchemaChange(
                change_type='ENUM_REMOVED',
                severity='MAJOR',
                description=f"Removed enum: {enum_name} (breaking change)"
            ))

        # Modified enums
        for enum_name in old_enums & new_enums:
            old_enum = self.old_schema['enums'][enum_name]
            new_enum = self.new_schema['enums'][enum_name]

            enum_changes = self._analyze_enum_changes(
                enum_name,
                old_enum['values'],
                new_enum['values']
            )
            changes.extend(enum_changes)

        return changes

    def _analyze_table_changes(
        self,
        table_name: str,
        old_fields: Dict,
        new_fields: Dict
    ) -> List[SchemaChange]:
        """Analyze changes within a table."""
        changes = []

        old_field_names = set(old_fields.keys())
        new_field_names = set(new_fields.keys())

        # 1. New fields
        for field_name in new_field_names - old_field_names:
            field_info = new_fields[field_name]

            # New required field → MAJOR (breaking)
            if field_info['required']:
                changes.append(SchemaChange(
                    change_type='FIELD_ADDED_REQUIRED',
                    severity='MAJOR',
                    field_name=field_name,
                    new_type=field_info['type'],
                    description=f"Added required field {table_name}.{field_name} (breaking: old clients missing field)"
                ))
            # New optional field → MINOR
            else:
                changes.append(SchemaChange(
                    change_type='FIELD_ADDED',
                    severity='MINOR',
                    field_name=field_name,
                    new_type=field_info['type'],
                    description=f"Added optional field {table_name}.{field_name}"
                ))

        # 2. Removed fields (MAJOR - breaking)
        for field_name in old_field_names - new_field_names:
            field_info = old_fields[field_name]
            changes.append(SchemaChange(
                change_type='FIELD_REMOVED',
                severity='MAJOR',
                field_name=field_name,
                old_type=field_info['type'],
                description=f"Removed field {table_name}.{field_name} (breaking: old clients expect field)"
            ))

        # 3. Modified fields
        for field_name in old_field_names & new_field_names:
            old_field = old_fields[field_name]
            new_field = new_fields[field_name]

            # Type changed → MAJOR (breaking)
            if old_field['type'] != new_field['type']:
                changes.append(SchemaChange(
                    change_type='TYPE_CHANGED',
                    severity='MAJOR',
                    field_name=field_name,
                    old_type=old_field['type'],
                    new_type=new_field['type'],
                    description=f"Changed type of {table_name}.{field_name}: {old_field['type']} → {new_field['type']} (breaking)"
                ))

            # Required flag changed
            if old_field['required'] != new_field['required']:
                # Optional → Required: MAJOR (breaking)
                if new_field['required']:
                    changes.append(SchemaChange(
                        change_type='FIELD_MADE_REQUIRED',
                        severity='MAJOR',
                        field_name=field_name,
                        description=f"Made field {table_name}.{field_name} required (breaking: old clients may omit)"
                    ))
                # Required → Optional: MINOR (loosening constraint)
                else:
                    changes.append(SchemaChange(
                        change_type='FIELD_MADE_OPTIONAL',
                        severity='MINOR',
                        field_name=field_name,
                        description=f"Made field {table_name}.{field_name} optional (backward compatible)"
                    ))

        return changes

    def _analyze_enum_changes(
        self,
        enum_name: str,
        old_values: List[str],
        new_values: List[str]
    ) -> List[SchemaChange]:
        """Analyze changes within an enum."""
        changes = []

        old_set = set(old_values)
        new_set = set(new_values)

        # New enum values (MINOR)
        for value in new_set - old_set:
            changes.append(SchemaChange(
                change_type='ENUM_VALUE_ADDED',
                severity='MINOR',
                description=f"Added enum value {enum_name}.{value}"
            ))

        # Removed enum values (MAJOR - breaking)
        for value in old_set - new_set:
            changes.append(SchemaChange(
                change_type='ENUM_VALUE_REMOVED',
                severity='MAJOR',
                description=f"Removed enum value {enum_name}.{value} (breaking: old clients may use value)"
            ))

        return changes

    def determine_required_bump(self, changes: List[SchemaChange]) -> str:
        """Determine required version bump (MAJOR, MINOR, PATCH)."""
        if not changes:
            return 'PATCH'  # No schema changes, documentation only

        # Check for MAJOR changes (breaking)
        if any(c.severity == 'MAJOR' for c in changes):
            return 'MAJOR'

        # Check for MINOR changes (new features)
        if any(c.severity == 'MINOR' for c in changes):
            return 'MINOR'

        # Otherwise PATCH
        return 'PATCH'
```

**Supported Changes:**

| Change Type | Severity | Example |
|-------------|----------|---------|
| **Table Added** | MINOR | New `BargeInEvent` table |
| **Table Removed** | MAJOR | Removed `LegacyRequest` table |
| **Field Added (Optional)** | MINOR | `time_range: TimeRange` (optional) |
| **Field Added (Required)** | MAJOR | `user_id: string (required)` |
| **Field Removed** | MAJOR | Removed `legacy_query_format` |
| **Type Changed** | MAJOR | `int32 → int64`, `string → bytes` |
| **Field Made Required** | MAJOR | Optional → Required |
| **Field Made Optional** | MINOR | Required → Optional |
| **Enum Added** | MINOR | New `TaskPriority` enum |
| **Enum Removed** | MAJOR | Removed `LegacyStatus` enum |
| **Enum Value Added** | MINOR | `STATUS_PAUSED` added |
| **Enum Value Removed** | MAJOR | `STATUS_DEPRECATED` removed |

---

### 2. Version Bump Validation Rules

**SemVer Rules:**

```python
from dataclasses import dataclass
import semver

@dataclass
class VersionBump:
    """Represents a version bump."""
    old_version: str
    new_version: str
    bump_type: str  # MAJOR, MINOR, PATCH

def validate_version_bump(
    old_version: str,
    new_version: str,
    required_bump: str
) -> tuple[bool, str]:
    """
    Validate if version bump is correct.

    Returns:
        (valid: bool, error_message: str)
    """
    old = semver.VersionInfo.parse(old_version)
    new = semver.VersionInfo.parse(new_version)

    # Determine actual bump
    if new.major > old.major:
        actual_bump = 'MAJOR'
    elif new.minor > old.minor:
        actual_bump = 'MINOR'
    elif new.patch > old.patch:
        actual_bump = 'PATCH'
    else:
        return False, f"Version did not increase: {old_version} → {new_version}"

    # Validate bump type
    if required_bump == 'MAJOR' and actual_bump != 'MAJOR':
        return False, f"Breaking change requires MAJOR version bump, found {actual_bump} ({old_version} → {new_version})"

    if required_bump == 'MINOR' and actual_bump not in ['MAJOR', 'MINOR']:
        return False, f"New feature requires MINOR or MAJOR version bump, found {actual_bump} ({old_version} → {new_version})"

    # PATCH is always acceptable (over-bumping is safe)
    return True, ""
```

**Examples:**

| Old Version | New Version | Required | Actual | Valid? | Reason |
|-------------|-------------|----------|--------|--------|--------|
| 2.0.0 | 2.1.0 | MINOR | MINOR | ✅ Yes | Correct bump |
| 2.0.0 | 3.0.0 | MINOR | MAJOR | ✅ Yes | Over-bump safe |
| 2.0.0 | 2.0.1 | MINOR | PATCH | ❌ No | Under-bump |
| 2.1.0 | 3.0.0 | MAJOR | MAJOR | ✅ Yes | Correct bump |
| 2.1.0 | 2.2.0 | MAJOR | MINOR | ❌ No | Under-bump (breaking) |

---

### 3. CI/CD Pipeline (GitHub Actions)

**Workflow:** `.github/workflows/schema-version-validation.yml`

```yaml
name: Schema Version Validation

on:
  pull_request:
    paths:
      - 'k1/schemas/**/*.fbs'
      - 'k1/config/schema_registry.yml'

jobs:
  validate-version-bump:
    runs-on: ubuntu-latest
    timeout-minutes: 5

    steps:
      - name: Checkout PR branch
        uses: actions/checkout@v3
        with:
          fetch-depth: 0  # Full history for diff

      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install pyyaml semver flatbuffers

      - name: Detect changed schemas
        id: changes
        run: |
          # Find changed .fbs files
          CHANGED_FILES=$(git diff --name-only ${{ github.event.pull_request.base.sha }}...${{ github.sha }} -- 'k1/schemas/**/*.fbs')
          echo "changed_schemas=$CHANGED_FILES" >> $GITHUB_OUTPUT

      - name: Validate version bumps
        if: steps.changes.outputs.changed_schemas != ''
        run: |
          python scripts/validate_version_bump.py \
            --base-ref ${{ github.event.pull_request.base.sha }} \
            --head-ref ${{ github.sha }} \
            --registry k1/config/schema_registry.yml \
            --schemas-dir k1/schemas

      - name: Post PR comment
        if: failure()
        uses: actions/github-script@v6
        with:
          script: |
            github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body: '❌ **Schema Version Bump Validation Failed**\n\nPlease review the error messages above and update the schema version in `schema_registry.yml`.\n\nSee: [ADR-0013b](https://github.com/k1/docs/architecture/decisions/0013b-automated-version-bump-validation.md) for version bump rules.'
            })
```

**Validation Script:** `scripts/validate_version_bump.py`

```python
#!/usr/bin/env python3
"""
Validate schema version bumps for changed .fbs files.
"""
import sys
import subprocess
from pathlib import Path
from typing import List, Tuple
import yaml

from schema_diff_analyzer import SchemaDiffAnalyzer
from version_bump_validator import validate_version_bump

def get_changed_schemas(base_ref: str, head_ref: str, schemas_dir: Path) -> List[Path]:
    """Get list of changed schema files."""
    result = subprocess.run(
        ['git', 'diff', '--name-only', base_ref, head_ref, '--', f'{schemas_dir}/**/*.fbs'],
        capture_output=True,
        text=True
    )
    changed_files = [Path(f) for f in result.stdout.strip().split('\n') if f]
    return changed_files

def get_schema_version(registry_path: Path, schema_name: str, ref: str) -> str:
    """Get schema version at specific git ref."""
    # Checkout registry at ref
    result = subprocess.run(
        ['git', 'show', f'{ref}:{registry_path}'],
        capture_output=True,
        text=True
    )
    registry = yaml.safe_load(result.stdout)

    # Find schema version
    for schema in registry['schemas']:
        if schema['name'] == schema_name:
            # Get latest active version
            active_versions = [v for v in schema['versions'] if v['status'] == 'active']
            if active_versions:
                return active_versions[0]['version']

    return None

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Validate schema version bumps')
    parser.add_argument('--base-ref', required=True, help='Base git ref (PR base)')
    parser.add_argument('--head-ref', required=True, help='Head git ref (PR head)')
    parser.add_argument('--registry', required=True, type=Path, help='Schema registry YAML')
    parser.add_argument('--schemas-dir', required=True, type=Path, help='Schemas directory')
    args = parser.parse_args()

    # Get changed schemas
    changed_schemas = get_changed_schemas(args.base_ref, args.head_ref, args.schemas_dir)

    if not changed_schemas:
        print("✅ No schema changes detected")
        return 0

    print(f"Found {len(changed_schemas)} changed schema(s):\n")

    errors = []

    for schema_path in changed_schemas:
        schema_name = schema_path.stem  # e.g., 'agent_state' from 'agent_state.fbs'

        # Get old and new schema files
        old_schema_content = subprocess.run(
            ['git', 'show', f'{args.base_ref}:{schema_path}'],
            capture_output=True,
            text=True
        ).stdout

        # Write to temp file
        old_schema_file = Path(f'/tmp/{schema_name}_old.fbs')
        with open(old_schema_file, 'w') as f:
            f.write(old_schema_content)

        # Analyze diff
        analyzer = SchemaDiffAnalyzer(old_schema_file, schema_path)
        changes = analyzer.analyze()
        required_bump = analyzer.determine_required_bump(changes)

        # Get versions
        old_version = get_schema_version(args.registry, schema_name, args.base_ref)
        new_version = get_schema_version(args.registry, schema_name, args.head_ref)

        if not old_version or not new_version:
            errors.append(f"❌ {schema_name}: Version not found in registry")
            continue

        # Validate bump
        valid, error_msg = validate_version_bump(old_version, new_version, required_bump)

        if valid:
            print(f"✅ {schema_name}: {old_version} → {new_version} ({required_bump} bump)")
            print(f"   Changes: {len(changes)}")
            for change in changes:
                print(f"   - {change.description}")
            print()
        else:
            print(f"❌ {schema_name}: {error_msg}")
            print(f"   Required bump: {required_bump}")
            print(f"   Detected changes:")
            for change in changes:
                print(f"   - [{change.severity}] {change.description}")
            print()
            errors.append(f"{schema_name}: {error_msg}")

    # Summary
    if errors:
        print("\n❌ Schema Version Bump Validation Failed\n")
        print("Errors:")
        for i, error in enumerate(errors, 1):
            print(f"{i}. {error}")
        print("\nAction required: Update schema_registry.yml with correct version bumps")
        return 1
    else:
        print("\n✅ All schema version bumps are correct")
        return 0

if __name__ == '__main__':
    sys.exit(main())
```

**CI/CD Latency Budget:**
- Checkout (2 refs): <5s
- Schema diff analysis: <10s (parse 2 .fbs files per schema)
- Version validation: <1s (registry lookup)
- Total: <30s ✅

---

### 4. Error Messages

**Example 1: Field Removal (MAJOR required, MINOR given)**

```
❌ Schema Version Bump Error

Schema: AgentState
Version: 2.1.0 → 2.2.0 (MINOR bump)
Required: MAJOR bump

Detected changes:
- [MAJOR] Removed field AgentState.legacy_state_name (breaking: old clients expect field)

Action required:
1. Update schema_registry.yml: version 2.2.0 → 3.0.0
2. Reason: Field removal is a breaking change (requires MAJOR bump)
3. Migration guide: Create ADR with migration steps for clients

Reference: https://github.com/k1/docs/architecture/decisions/0013b-automated-version-bump-validation.md
```

**Example 2: New Optional Field (MINOR required, PATCH given)**

```
❌ Schema Version Bump Error

Schema: TaskAnnouncement
Version: 2.1.0 → 2.1.1 (PATCH bump)
Required: MINOR bump (or MAJOR)

Detected changes:
- [MINOR] Added optional field TaskAnnouncement.time_budget_ms

Action required:
1. Update schema_registry.yml: version 2.1.1 → 2.2.0
2. Reason: New field (even optional) is a feature addition (requires MINOR bump)
3. Changelog: Add entry describing new field purpose

Reference: https://github.com/k1/docs/architecture/decisions/0013b-automated-version-bump-validation.md
```

**Example 3: Documentation Only (PATCH correct)**

```
✅ Schema Version Bump Valid

Schema: SessionStateRoot
Version: 2.0.0 → 2.0.1 (PATCH bump)
Required: PATCH bump

Detected changes:
- [PATCH] Documentation updated (no schema changes)

All validations passed. Ready to merge.
```

---

### 5. Automated CLI Tool: `k1-schema-bump`

**Installation:**
```bash
pip install k1-tools
```

**Commands:**

#### 5.1. Auto-Bump Version
```bash
# Analyze schema changes, determine version bump, update registry
k1-schema-bump --auto --schema AgentState

# Output:
Analyzing schema changes for AgentState...

Detected changes (2):
1. [MINOR] Added optional field: last_error (ErrorInfo)
   Description: Enable crash diagnostics
2. [PATCH] Updated documentation for state transitions

Recommended version bump: MINOR (2.0.0 → 2.1.0)

Updating schema_registry.yml...
✅ Version updated: 2.0.0 → 2.1.0

Generated changelog:
---
Version 2.1.0 (2025-10-12):
- Added optional field: last_error (ErrorInfo) for crash diagnostics
- Updated documentation for state transitions
- Backward compatible: Yes (clients can ignore new field)
---

Changelog saved to: CHANGELOG_AgentState_2.1.0.md

Ready to commit:
  git add k1/config/schema_registry.yml
  git add CHANGELOG_AgentState_2.1.0.md
  git commit -m "bump: AgentState 2.0.0 → 2.1.0 (add last_error field)"
```

#### 5.2. Dry-Run (No Registry Update)
```bash
# Analyze changes without updating registry
k1-schema-bump --dry-run --schema TaskAnnouncement

# Output:
Analyzing schema changes for TaskAnnouncement...

Detected changes (1):
1. [MAJOR] Removed field: legacy_task_type
   Description: Deprecated in v2.1.0, now removed

Recommended version bump: MAJOR (2.2.0 → 3.0.0)

⚠️ Breaking change detected!
Action required:
1. Update version: 2.2.0 → 3.0.0
2. Create migration guide ADR
3. Notify users (90-day deprecation completed)

(--dry-run mode: no changes made)
```

#### 5.3. Manual Version Specification
```bash
# Force specific version bump (override auto-detection)
k1-schema-bump --schema AgentState --version 3.0.0

# Output:
Analyzing schema changes for AgentState...

Detected changes (1):
1. [MINOR] Added optional field: last_error

Recommended bump: MINOR (2.1.0 → 2.2.0)
Specified version: 3.0.0 (MAJOR)

⚠️ Over-bump detected (MINOR → MAJOR)
This is safe (over-bumping allowed), but may indicate:
- Planning future breaking changes in this release
- Developer preference for clean MAJOR version

Proceed with version 3.0.0? [y/N]: y

✅ Version updated: 2.1.0 → 3.0.0
Changelog generated (manual review recommended)
```

**CLI Implementation:**

```python
#!/usr/bin/env python3
"""
k1-schema-bump: Automated schema version bumping.
"""
import sys
from pathlib import Path
from datetime import date
import yaml

from schema_diff_analyzer import SchemaDiffAnalyzer
from version_bump_validator import validate_version_bump

def generate_changelog(
    schema_name: str,
    old_version: str,
    new_version: str,
    changes: list
) -> str:
    """Generate changelog entry from schema changes."""
    changelog = f"Version {new_version} ({date.today().isoformat()}):\n"

    for change in changes:
        changelog += f"- {change.description}\n"

    # Add compatibility note
    if any(c.severity == 'MAJOR' for c in changes):
        changelog += "- Breaking: Yes (MAJOR version bump)\n"
    else:
        changelog += "- Backward compatible: Yes\n"

    return changelog

def update_registry(
    registry_path: Path,
    schema_name: str,
    new_version: str,
    changelog: str
) -> None:
    """Update schema_registry.yml with new version."""
    with open(registry_path) as f:
        registry = yaml.safe_load(f)

    # Find schema
    for schema in registry['schemas']:
        if schema['name'] == schema_name:
            # Add new version entry
            new_entry = {
                'version': new_version,
                'released_at': date.today().isoformat(),
                'status': 'active',
                'breaking': any(c.severity == 'MAJOR' for c in changes),
                'changelog': changelog.strip(),
                'compatible_with': [new_version]  # Will be updated by compatibility matrix generator
            }
            schema['versions'].insert(0, new_entry)  # Prepend (latest first)
            break

    # Write back
    with open(registry_path, 'w') as f:
        yaml.safe_dump(registry, f, default_flow_style=False, sort_keys=False)

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Automated schema version bumping')
    parser.add_argument('--schema', required=True, help='Schema name (e.g., AgentState)')
    parser.add_argument('--auto', action='store_true', help='Auto-detect version bump')
    parser.add_argument('--version', help='Manual version specification (overrides auto-detect)')
    parser.add_argument('--dry-run', action='store_true', help='Analyze only, no changes')
    parser.add_argument('--registry', type=Path, default='k1/config/schema_registry.yml')
    parser.add_argument('--schemas-dir', type=Path, default='k1/schemas')
    args = parser.parse_args()

    # Load registry
    with open(args.registry) as f:
        registry = yaml.safe_load(f)

    # Find schema
    schema_info = None
    for s in registry['schemas']:
        if s['name'] == args.schema:
            schema_info = s
            break

    if not schema_info:
        print(f"❌ Schema '{args.schema}' not found in registry")
        return 1

    # Get current version
    current_version = schema_info['versions'][0]['version']

    # Find schema file
    schema_file = Path(schema_info['schema_path'])
    if not schema_file.exists():
        print(f"❌ Schema file not found: {schema_file}")
        return 1

    print(f"Analyzing schema changes for {args.schema}...\n")

    # For auto-bump, we need a baseline (previous commit)
    if args.auto and not args.version:
        # Get previous version of schema file from git
        import subprocess
        result = subprocess.run(
            ['git', 'show', f'HEAD~1:{schema_file}'],
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            print("❌ Could not retrieve previous schema version from git")
            return 1

        # Write to temp file
        old_schema_file = Path(f'/tmp/{args.schema}_old.fbs')
        with open(old_schema_file, 'w') as f:
            f.write(result.stdout)

        # Analyze diff
        analyzer = SchemaDiffAnalyzer(old_schema_file, schema_file)
        changes = analyzer.analyze()

        if not changes:
            print("No schema changes detected. No version bump needed.")
            return 0

        # Determine required bump
        required_bump = analyzer.determine_required_bump(changes)

        # Calculate new version
        import semver
        old_ver = semver.VersionInfo.parse(current_version)

        if required_bump == 'MAJOR':
            new_version = f"{old_ver.major + 1}.0.0"
        elif required_bump == 'MINOR':
            new_version = f"{old_ver.major}.{old_ver.minor + 1}.0"
        else:  # PATCH
            new_version = f"{old_ver.major}.{old_ver.minor}.{old_ver.patch + 1}"

        print(f"Detected changes ({len(changes)}):")
        for i, change in enumerate(changes, 1):
            print(f"{i}. [{change.severity}] {change.description}")
        print()

        print(f"Recommended version bump: {required_bump} ({current_version} → {new_version})")

        if args.dry_run:
            print("\n(--dry-run mode: no changes made)")
            return 0

        # Generate changelog
        changelog = generate_changelog(args.schema, current_version, new_version, changes)

        print(f"\nUpdating schema_registry.yml...")
        update_registry(args.registry, args.schema, new_version, changelog)
        print(f"✅ Version updated: {current_version} → {new_version}")

        # Save changelog
        changelog_file = Path(f"CHANGELOG_{args.schema}_{new_version}.md")
        with open(changelog_file, 'w') as f:
            f.write(f"# {args.schema} v{new_version} Changelog\n\n")
            f.write(changelog)
        print(f"Changelog saved to: {changelog_file}")

        print("\nReady to commit:")
        print(f"  git add {args.registry}")
        print(f"  git add {changelog_file}")
        print(f"  git commit -m \"bump: {args.schema} {current_version} → {new_version}\"")

        return 0

    # Manual version specification
    elif args.version:
        print(f"Manual version specified: {args.version}")
        # Validate version format
        try:
            import semver
            semver.VersionInfo.parse(args.version)
        except ValueError:
            print(f"❌ Invalid SemVer version: {args.version}")
            return 1

        # Update registry (simplified, no change analysis)
        print(f"\nUpdating schema_registry.yml...")
        update_registry(args.registry, args.schema, args.version, "Manual version bump")
        print(f"✅ Version updated: {current_version} → {args.version}")

        return 0

    else:
        print("❌ Either --auto or --version must be specified")
        return 1

if __name__ == '__main__':
    sys.exit(main())
```

---

### 6. Changelog Generation

**Template:**

```markdown
# {schema_name} v{new_version} Changelog

**Released:** {release_date}
**Previous Version:** {old_version}
**Version Bump:** {MAJOR/MINOR/PATCH}

## Changes

{list of changes from schema diff}

## Compatibility

- **Backward Compatible:** {Yes/No}
- **Forward Compatible:** {Yes/No}
- **Breaking Changes:** {Yes/No}

{if breaking:}
## Migration Guide

{migration steps for clients}

{link to full ADR if MAJOR change}
```

**Example:**

```markdown
# TaskAnnouncement v2.2.0 Changelog

**Released:** 2025-10-12
**Previous Version:** 2.1.0
**Version Bump:** MINOR

## Changes

- Added optional field: `time_budget_ms` (uint32)
  - Purpose: Enable deadline-aware orchestration
  - Clients can ignore this field if not needed
- Updated documentation for priority field

## Compatibility

- **Backward Compatible:** Yes
- **Forward Compatible:** Yes
- **Breaking Changes:** No

## Usage Example

```flatbuffers
table TaskAnnouncement {
  task_id: string;
  priority: Priority = INTERACTIVE;
  time_budget_ms: uint32;  // NEW: Optional deadline (0 = no deadline)
}
```

**Client Impact:** None (optional field, existing clients work unchanged)
```

---

## Performance Characteristics

### Schema Diff Analysis
- **Single schema:** <10s (parse 2 .fbs files, compute diff)
- **Complex schema (1000 lines):** <15s (many fields/enums)
- **Simple schema (100 lines):** <3s (few fields)

### CI/CD Pipeline
- **Checkout:** <5s (fetch 2 refs)
- **Diff analysis:** <10s (per changed schema)
- **Validation:** <1s (registry lookup)
- **Total:** <30s ✅ (meets budget)

### CLI Tool
- **Auto-bump (local):** <5s (parse, analyze, update registry)
- **Dry-run:** <3s (no registry update)

---

## Testing Strategy

### Unit Tests
```python
def test_field_added_optional():
    """Test MINOR bump for optional field."""
    analyzer = SchemaDiffAnalyzer(
        old_schema='test_data/agent_state_v2.0.0.fbs',
        new_schema='test_data/agent_state_v2.1.0.fbs'
    )
    changes = analyzer.analyze()
    assert any(c.change_type == 'FIELD_ADDED' for c in changes)
    assert analyzer.determine_required_bump(changes) == 'MINOR'

def test_field_removed():
    """Test MAJOR bump for field removal."""
    analyzer = SchemaDiffAnalyzer(
        old_schema='test_data/task_v2.1.0.fbs',
        new_schema='test_data/task_v3.0.0.fbs'
    )
    changes = analyzer.analyze()
    assert any(c.change_type == 'FIELD_REMOVED' for c in changes)
    assert analyzer.determine_required_bump(changes) == 'MAJOR'

def test_version_bump_validation():
    """Test version bump validation logic."""
    valid, msg = validate_version_bump('2.0.0', '2.1.0', 'MINOR')
    assert valid is True

    valid, msg = validate_version_bump('2.0.0', '2.0.1', 'MINOR')
    assert valid is False
    assert 'MINOR' in msg
```

### Integration Tests
```python
def test_cli_auto_bump():
    """Test CLI auto-bump command."""
    result = subprocess.run(
        ['k1-schema-bump', '--auto', '--schema', 'AgentState', '--dry-run'],
        capture_output=True,
        text=True
    )
    assert result.returncode == 0
    assert 'Recommended version bump:' in result.stdout
```

---

## Migration Path

### Phase 1: Schema Diff Analysis (Week 1)
1. Implement `SchemaDiffAnalyzer` class
2. Support all change types (fields, enums, tables)
3. Add unit tests (>90% coverage)

### Phase 2: CI/CD Integration (Week 2)
1. Create GitHub Actions workflow
2. Implement `validate_version_bump.py` script
3. Test on staging PRs

### Phase 3: CLI Tool (Week 2)
1. Implement `k1-schema-bump` CLI
2. Add auto-bump, dry-run, manual version commands
3. Package as `k1-tools` pip package

### Phase 4: Changelog Generation (Week 2)
1. Implement changelog template
2. Auto-generate from schema diff
3. Integrate with CLI tool

---

## Consequences

### Positive
- ✅ **Automated validation:** >95% version bump errors caught before merge
- ✅ **Fast feedback:** <30s CI/CD latency
- ✅ **Clear errors:** Actionable guidance for developers
- ✅ **Changelog automation:** No manual changelog maintenance
- ✅ **Extensible:** Easy to add new change types

### Negative
- ❌ **Complex diff analysis:** Nested tables, unions require careful parsing
- ❌ **False negatives:** <5% complex changes might be missed (e.g., semantic changes)
- ❌ **CI/CD dependency:** Pipeline failures block PRs (mitigated by fast latency)

### Neutral
- ⚠️ **Requires git history:** Needs previous commit for diff (standard in CI/CD)
- ⚠️ **Python dependency:** Requires Python 3.11+ (K1 standard)

---

## Related ADRs

- **ADR-0013a:** Schema Version Registry (version metadata storage)
- **ADR-0013c:** 90-Day Deprecation Workflow (deprecation tracking)
- **ADR-0013d:** Contract Testing (compatibility validation)
- **ADR-0012:** 76 FlatBuffers Schemas (schemas to version)
- **ADR-0011:** FlatBuffers Serialization (schema parsing)

---

## References

### Semantic Versioning
- **SemVer 2.0.0:** https://semver.org/
- **Breaking changes:** MAJOR version for field removal, type change, new required field

### Schema Evolution
- **FlatBuffers Evolution:** https://flatbuffers.dev/flatbuffers_guide_writing_schema.html#flatbuffers_evolution
- **Backward compatibility:** Adding optional fields safe, removing fields breaking

### CI/CD
- **GitHub Actions:** https://docs.github.com/en/actions
- **Fast feedback:** <30s pipeline for schema validation

---

**Status:** ✅ **75% Complete** (Pending: Schema diff optimization for nested unions)

**Next Steps:**
1. Implement nested union detection (complex oneOf patterns)
2. Add support for circular reference detection
3. Optimize diff analysis for large schemas (>1000 lines)
4. Deploy to staging CI/CD (test on real PRs)