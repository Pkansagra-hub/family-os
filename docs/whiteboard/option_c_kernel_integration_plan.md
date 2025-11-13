# Option C: K0 Kernel Integration Plan

**Purpose:** Integrate Migration 0004 (Future-Proof enhancements) into K0 kernel code

**Migration DDL:** `k0/contracts/sql/migrations/0004_future_proof_enhancements.sql`

**Status:** ⚠️ SCHEMA ONLY - Kernel code integration REQUIRED

---

## 🎯 Implementation Roadmap

### Phase 1: Critical Path (Blocks Release)

#### **1. FTS5 Memory Tables Integration** ⚠️ CRITICAL

**Problem:** Tables exist (`st_epi_fts`, `st_hipp_fts`) but nothing populates them

**Files to Create/Update:**

- [ ] `k0/storage/fts5_indexer.py` - NEW FILE

  ```python
  class FTS5Indexer:
      def index_episodic(self, event_id: str, text: str, summary: str, tags: list, ...):
          """Insert into st_epi_fts"""

      def index_hippocampus(self, event_id: str, text: str, topics: list, ...):
          """Insert into st_hipp_fts"""

      def remove_from_index(self, table: str, event_id: str):
          """Delete from FTS5 when memory deleted"""
  ```

- [ ] `k0/hippocampus/writer.py` - UPDATE

  ```python
  # After writing to st_hipp_store
  fts5_indexer.index_hippocampus(
      event_id=event.event_id,
      text=event.text,
      topics=event.topics,
      categories=event.categories,
      ...
  )
  ```

- [ ] `k0/storage/sqlite.py` - UPDATE (episodic memory writes)

  ```python
  # After writing to st_epi
  fts5_indexer.index_episodic(
      event_id=event_id,
      text=event.text,
      summary=event.summary,
      tags=event.tags,
      ...
  )
  ```

- [ ] `k0/query/fts5.py` - UPDATE (add memory table queries)

  ```python
  def search_episodic(self, query: str, limit: int = 20) -> list[str]:
      """Search st_epi_fts, return event_ids"""
      SELECT event_id FROM st_epi_fts WHERE st_epi_fts MATCH ? LIMIT ?

  def search_hippocampus(self, query: str, limit: int = 20) -> list[str]:
      """Search st_hipp_fts, return event_ids"""
      SELECT event_id FROM st_hipp_fts WHERE st_hipp_fts MATCH ? LIMIT ?
  ```

**Testing:**

- [ ] `tests/k0/integration/test_fts5_memory_indexing.py`
- [ ] Verify: Write memory → FTS5 indexed → Search returns results

**Performance Target:** <10ms P95 for keyword search across 100K+ memories

---

#### **2. WAL Envelope Traceability** ⚠️ CRITICAL

**Problem:** `envelope_id`, `content_type`, `encryption_scheme` columns exist but never populated

**Files to Update:**

- [ ] `k0/gate/minimal_gate.py` - UPDATE (extract envelope_id from JSON)

  ```python
  # Parse envelope_json to extract envelope_id
  envelope = json.loads(envelope_json)
  envelope_id = envelope.get("envelope_id") or envelope.get("id")
  content_type = envelope.get("content_type", "application/json")
  encryption_scheme = envelope.get("encryption_scheme", "none")

  # Pass to WAL writer
  wal_writer.write(
      envelope_json=envelope_json,
      envelope_id=envelope_id,  # NEW
      content_type=content_type,  # NEW
      encryption_scheme=encryption_scheme,  # NEW
      ...
  )
  ```

- [ ] `k0/storage/` (WAL writer) - UPDATE

  ```python
  INSERT INTO st_wal (
      ...,
      envelope_id,       # NEW
      content_type,      # NEW
      encryption_scheme  # NEW
  ) VALUES (?, ?, ?, ...)
  ```

- [ ] `k0/telemetry/` - UPDATE (use envelope_id for distributed tracing)

  ```python
  # OpenTelemetry span context
  span.set_attribute("k0.envelope_id", envelope_id)
  span.set_attribute("k0.wal_pos", wal_pos)
  ```

**Testing:**

- [ ] `tests/k0/integration/test_wal_envelope_traceability.py`
- [ ] Verify: Envelope written → envelope_id indexed → Traceable across K0/K1

**Performance Target:** <1ms overhead for envelope_id extraction

---

#### **3. Outbox/DLQ Backoff State** ⚠️ CRITICAL

**Problem:** `next_attempt_ts`, `backoff_exp`, `status` columns exist but retry logic still uses old `requeue_seq`

**Files to Update:**

- [ ] `k0/outbox/scheduler.py` - UPDATE `RetryScheduler`

  ```python
  @dataclass(frozen=True)
  class RetryDecision:
      action: str  # "retry" or "quarantine"
      retries: int
      requeue_seq: int  # DEPRECATED - keep for backward compat
      next_attempt_ts: str  # NEW - ISO8601 timestamp
      backoff_exp: int  # NEW - Exponent for 2^n backoff
      status: str  # NEW - PENDING/PROCESSING/FAILED/DEAD

  def decide(self, entry: OutboxEntry) -> RetryDecision:
      next_retry = entry.retries + 1
      if next_retry >= self._max_attempts:
          return RetryDecision(
              action="quarantine",
              status="DEAD",
              next_attempt_ts=None,
              ...
          )

      # Exponential backoff: 2^backoff_exp seconds
      backoff_exp = min(next_retry, 6)  # Cap at 2^6 = 64 seconds
      next_attempt = datetime.now(timezone.utc) + timedelta(seconds=2**backoff_exp)

      return RetryDecision(
          action="retry",
          status="PENDING",
          next_attempt_ts=next_attempt.isoformat(),
          backoff_exp=backoff_exp,
          retries=next_retry,
          ...
      )
  ```

- [ ] `k0/outbox/worker.py` - UPDATE `OutboxWorker`

  ```python
  def process_driver(self, alias: str, *, limit: Optional[int] = None) -> None:
      # OLD: dequeue_batch(alias, limit)
      # NEW: dequeue_ready_batch(alias, limit) - only fetch WHERE next_attempt_ts < NOW()
      entries = self._outbox_store.dequeue_ready_batch(alias, limit=batch_limit)
      ...
  ```

- [ ] `k0/storage/outbox.py` - UPDATE `OutboxStore`

  ```python
  def dequeue_ready_batch(self, driver: str, *, limit: int = 128) -> list[OutboxEntry]:
      """Fetch entries WHERE next_attempt_ts IS NULL OR next_attempt_ts <= NOW()"""
      SELECT * FROM st_outbox
      WHERE driver = ?
        AND status = 'PENDING'
        AND (next_attempt_ts IS NULL OR next_attempt_ts <= ?)
      ORDER BY id
      LIMIT ?
  ```

- [ ] `k0/storage/dlq.py` - UPDATE (same pattern for st_dlq)

**Testing:**

- [ ] `tests/k0/integration/test_outbox_exponential_backoff.py`
- [ ] Verify: Failed entry → next_attempt_ts set → Not retried until time elapsed

**Performance Target:** <5ms P95 for retry eligibility query (indexed next_attempt_ts)

---

### Phase 2: Production Enhancements (Post-Launch)

#### **4. ACL Policy Engine**

**Problem:** `st_acl` table exists but no enforcement

**Files to Create:**

- [ ] `k0/policy/acl_enforcer.py` - NEW FILE

  ```python
  class ACLEnforcer:
      def check_permission(
          self,
          resource_type: str,
          resource_id: str,
          principal_id: str,
          permission: str
      ) -> bool:
          """Query st_acl for permission"""
          SELECT 1 FROM st_acl
          WHERE resource_type = ?
            AND resource_id = ?
            AND principal_id = ?
            AND permission = ?
            AND revoked_at IS NULL
            AND (expires_at IS NULL OR expires_at > NOW())

      def grant_permission(self, acl_id: str, resource_type: str, ...):
          """Insert into st_acl"""

      def revoke_permission(self, acl_id: str):
          """UPDATE st_acl SET revoked_at = NOW()"""
  ```

- [ ] `k0/query/` - UPDATE (filter queries by ACL)

  ```python
  # Before returning memories, check ACL
  if not acl_enforcer.check_permission("st_epi", event_id, user_id, "read"):
      continue  # Skip unauthorized memory
  ```

**Testing:**

- [ ] `tests/k0/integration/test_acl_enforcement.py`

**Performance Target:** <2ms P95 for ACL checks (indexed lookups)

---

#### **5. Retention Policy Management**

**Problem:** `st_retention_policy`, `st_archive_manifest` exist but no enforcement

**Files to Create:**

- [ ] `k0/policy/retention_enforcer.py` - NEW FILE

  ```python
  class RetentionEnforcer:
      def apply_policies(self):
          """Nightly job: Archive/delete based on st_retention_policy"""
          policies = SELECT * FROM st_retention_policy WHERE enabled = 1
          for policy in policies:
              expired = SELECT * FROM {policy.resource_type}
                        WHERE created_at < NOW() - INTERVAL {policy.retention_days} DAYS

              if policy.archive_enabled:
                  archive_to_blob(expired)
                  INSERT INTO st_archive_manifest (...)
              else:
                  hard_delete(expired)
  ```

- [ ] Integrate with P03 consolidation (learning-based decay)

  ```python
  # P03 suggests decay_score > 0.95
  # Check st_retention_policy for final decision
  policy = get_policy(memory_type, privacy_band)
  if age_days > policy.retention_days:
      archive_or_delete(memory)
  ```

**Testing:**

- [ ] `tests/k0/integration/test_retention_policies.py`

---

#### **6. CRDT Merge Log**

**Problem:** `st_crdt_merge_log` exists but no conflict logging

**Files to Update:**

- [ ] `k0/sync/` (CRDT merge logic) - UPDATE

  ```python
  def resolve_conflict(local_memory, remote_memory):
      # Determine winner (last-write-wins, etc)
      if local_memory.vector_clock > remote_memory.vector_clock:
          winner = local_memory
          loser = remote_memory
      else:
          winner = remote_memory
          loser = local_memory

      # Log to st_crdt_merge_log
      INSERT INTO st_crdt_merge_log (
          merge_id, resource_type, resource_id,
          merge_strategy, winner_device_id, loser_device_id,
          winner_vector_clock, loser_vector_clock,
          merged_at, conflict_reason
      ) VALUES (...)
  ```

**Testing:**

- [ ] `tests/k0/integration/test_crdt_merge_logging.py`

---

## 📊 Implementation Priority Matrix

| Feature | Priority | Blocks Release? | Effort | Performance Impact |
|---------|----------|-----------------|--------|-------------------|
| **FTS5 Indexing** | 🔴 P0 | ✅ YES | 2 days | +10ms keyword search |
| **WAL Envelope Tracing** | 🔴 P0 | ✅ YES | 1 day | +1ms trace context |
| **Outbox Backoff** | 🔴 P0 | ✅ YES | 2 days | +5ms retry query |
| **ACL Enforcement** | 🟡 P1 | ❌ NO | 3 days | +2ms permission check |
| **Retention Policies** | 🟡 P1 | ❌ NO | 4 days | Nightly job only |
| **CRDT Merge Log** | 🟢 P2 | ❌ NO | 2 days | +1ms conflict resolution |

**Total Effort (P0 only):** ~5 days
**Total Effort (P0+P1):** ~12 days
**Total Effort (All):** ~14 days

---

## 🧪 Testing Strategy

### Integration Tests Required

1. **test_fts5_memory_indexing.py**
   - Write to st_epi → Verify st_epi_fts populated
   - Search keyword → Verify results returned
   - Delete memory → Verify removed from FTS5

2. **test_wal_envelope_traceability.py**
   - Write envelope → Verify envelope_id extracted
   - Query by envelope_id → Verify WAL entry found
   - Distributed trace → Verify span context propagated

3. **test_outbox_exponential_backoff.py**
   - Fail entry → Verify next_attempt_ts set to NOW() + 2^backoff_exp
   - Query before time → Verify entry NOT returned
   - Query after time → Verify entry IS returned
   - Max retries → Verify status = 'DEAD'

4. **test_acl_enforcement.py**
   - Grant permission → Verify ACL entry created
   - Query with permission → Verify allowed
   - Query without permission → Verify denied
   - Revoke permission → Verify denied after revocation

5. **test_retention_policies.py**
   - Create policy (30 days, archive enabled)
   - Create old memory (40 days)
   - Run enforcer → Verify archived
   - Check st_archive_manifest → Verify manifest entry

6. **test_crdt_merge_logging.py**
   - Concurrent write conflict → Verify winner/loser logged
   - Check st_crdt_merge_log → Verify merge_strategy, vector_clocks

### Performance Tests Required

- [ ] `test_fts5_search_latency.py` - <10ms P95 for 100K memories
- [ ] `test_acl_check_latency.py` - <2ms P95 for permission checks
- [ ] `test_outbox_retry_query_latency.py` - <5ms P95 for ready batch query

---

## 📝 Migration Application Workflow

### Step 1: Apply Migration

```bash
# Dry-run validation
python -m k0.automation.migrate apply --dry-run /path/to/k0.db

# Apply migration
python -m k0.automation.migrate apply /path/to/k0.db

# Verify
sqlite3 k0.db ".schema st_acl"
sqlite3 k0.db ".schema st_epi_fts"
```

### Step 2: Deploy Kernel Code (Phased)

**Phase 1 (P0 - Week 1):**

- Deploy FTS5 indexing code
- Deploy WAL envelope tracing
- Deploy outbox backoff state
- Run integration tests

**Phase 2 (P1 - Week 2-3):**

- Deploy ACL enforcement
- Deploy retention policies
- Run E2E tests

**Phase 3 (P2 - Week 4):**

- Deploy CRDT merge logging
- Performance benchmarking

### Step 3: Backfill Existing Data (If Needed)

**FTS5 Backfill:**

```python
# Backfill st_epi_fts from existing st_epi
cursor = conn.execute("SELECT event_id, text, summary, tags, topics, ... FROM st_epi")
for row in cursor:
    fts5_indexer.index_episodic(row[0], row[1], row[2], ...)
```

**Envelope ID Backfill:**

```python
# Extract envelope_id from existing envelope_json
cursor = conn.execute("SELECT pos, envelope_json FROM st_wal WHERE envelope_id IS NULL")
for pos, envelope_json in cursor:
    envelope = json.loads(envelope_json)
    envelope_id = envelope.get("envelope_id") or envelope.get("id")
    conn.execute("UPDATE st_wal SET envelope_id = ? WHERE pos = ?", (envelope_id, pos))
```

---

## 🎯 Success Criteria

**Phase 1 (P0) Complete When:**

- ✅ FTS5 memory search returns results
- ✅ WAL entries have envelope_id populated
- ✅ Outbox retries respect next_attempt_ts
- ✅ All integration tests pass
- ✅ Performance budgets met (<10ms FTS5, <5ms outbox)

**Phase 2 (P1) Complete When:**

- ✅ ACL checks enforce permissions
- ✅ Retention policies archive old data
- ✅ Archive manifest tracks archived memories

**Phase 3 (P2) Complete When:**

- ✅ CRDT conflicts logged to merge log
- ✅ Audit trail complete for multi-device sync

---

## 🚨 Rollback Plan

If issues arise:

```bash
# Rollback to before Migration 0004
python -m k0.automation.migrate rollback --target-version 0003 /path/to/k0.db

# Result: All 0004 tables/columns dropped (auto-generated DOWN script)
```

**Safe Rollback:** All changes are additive (new tables/columns). Existing K0 code continues working even if new fields are NULL.

---

## 📚 Related Documentation

- **Migration DDL:** `k0/contracts/sql/migrations/0004_future_proof_enhancements.sql`
- **Migration System:** `k0/automation/migrate.py`
- **Whiteboard:** `docs/whiteboard/whiteboard_schema.md` (Option C section)
- **Storage Contract:** `k0/contracts/sql/storage.sql` (migration history in header)

---

## 🔍 Code Review Checklist

Before merging:

- [ ] All P0 integration tests pass
- [ ] Performance budgets verified (<10ms FTS5, <5ms outbox, <2ms ACL)
- [ ] Backward compatibility: Existing K0 code works with NULL new fields
- [ ] Forward compatibility: New code handles missing migration (graceful degradation)
- [ ] Documentation updated (README, ADRs, API docs)
- [ ] Metrics/telemetry added (FTS5 query count, ACL check latency, etc)
- [ ] Error handling: What if FTS5 indexing fails? (Log warning, continue)
- [ ] Edge cases: What if envelope_id missing from envelope_json? (Use wal_pos as fallback)
