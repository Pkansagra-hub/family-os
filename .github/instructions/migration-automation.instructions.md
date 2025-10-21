# Migration Automation Instructions

These steps codify how we build and validate schema migrations driven by `contracts/storage/storage.manifest.yaml`. Follow them whenever the manifest or migration tooling changes.

## 1. Prepare the Environment
- Ensure dependencies from `requirements.txt` are installed and you can run `python -m ward`.
- Clear manifest caches before comparisons: `ManifestRegistry.clear_cache()` is invoked automatically by the generator, but call it manually when diffing inside a REPL.

## 2. Generate a Migration Plan
1. Stage an on-disk copy of the baseline manifest (from `main` or production tag).
2. Apply your schema changes to `contracts/storage/storage.manifest.yaml`.
3. Run the generator:
   ```powershell
   cd d:\FamilyOS_POC
   python -m storage.migrations.generate --from <path-to-baseline-manifest.yaml> --to contracts/storage/storage.manifest.yaml --output storage/migrations/generated --description "<summary of change>"
   ```
4. Inspect console output to confirm the SQL preview matches the intended changes.
5. Review the emitted module in `storage/migrations/generated/`. It should expose a `PLAN` with ordered `CreateTable`, `AddColumn`, and `CreateIndex` operations only.

## 3. Validate the Plan
- Import the generated module in a Python shell to verify `PLAN.sql_preview()` contains the expected DDL.
- If the generator reports "No migration operations detected", re-check that the candidate manifest differs from the baseline.

## 4. Apply Against a Test Database
- Use the migration model directly for dry runs:
  ```python
  from storage.migrations.generated.YYYYMMDDHHMMSS_slug import PLAN
  from storage.migrations.model import MigrationContext
  import sqlite3

  conn = sqlite3.connect(":memory:")
  PLAN.apply(MigrationContext(database_path=":memory:", connection=conn))
  ```
- Confirm the table or column set is as expected via `PRAGMA table_info(<table>)` and `PRAGMA index_list(<table>)` queries.

## 5. Run Ward Coverage
Execute the migration-focused suite after every change:
```powershell
cd d:\FamilyOS_POC
python -m ward test --path Tests/storage/test_migrations.py
```
All tests must pass; they exercise both generator output and in-place upgrades on temporary SQLite databases.

## 6. Commit Checklist
- Generated migration module stored under `storage/migrations/generated/`.
- Updated manifests and code are included in the same commit.
- Ward tests pass locally (provide the command output in the PR description).
- No sleep-based simulations or mock stand-ins appear in production code (per zero-tolerance policy).

## 7. Copilot Prompt Notes
- Always read this file plus `.github/copilot-instructions.md` before editing migration tooling.
- Prefer real SQLite operations in tests—no mocks or artificial delays.
- When unsure about schema diffs, call `storage.migrations.planner.plan_sqlite_migration` with explicit `ManifestRegistry` instances.

Following this playbook keeps manifest drift under control and guarantees migrations stay deterministic across tiers.
