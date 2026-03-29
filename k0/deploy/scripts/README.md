# K0 Deploy Scripts

Organized collection of operational scripts for K0 kernel deployment, testing, and data management.

## 📂 Directory Structure

```
scripts/
├── validation/         Database and data quality checks
├── reporting/          Export and visualization tools
├── data_management/    Data cleanup and consolidation
├── provisioning/       Device setup and registration
├── events/            Event submission utilities
├── testing/           Integration and component tests
└── seeding/           Initial data population
```

---

## 🔍 validation/

**Purpose:** Inspect database schemas, data quality, and memory layer contents.

### Scripts

| Script | Purpose | Usage |
|--------|---------|-------|
| `check_columns.py` | Verify table column structure | `python scripts/validation/check_columns.py` |
| `check_embeddings.py` | Check embedding vector coverage | `python scripts/validation/check_embeddings.py` |
| `check_quality.py` | Validate pattern names and summaries | `python scripts/validation/check_quality.py` |
| `check_schemas.py` | Display all memory table schemas | `python scripts/validation/check_schemas.py` |
| `explore_memory_layers.py` | Deep dive into all memory layers (1400+ lines) | `python scripts/validation/explore_memory_layers.py` |
| `query_learning_gaps.py` | Query st_learning_queue gaps | `python scripts/validation/query_learning_gaps.py` |
| `query_memories.py` | Query all memory formation layers | `python scripts/validation/query_memories.py` |
| `query_observations.py` | Query st_observations P01 data | `python scripts/validation/query_observations.py` |

**When to use:**
- After running P03 consolidation
- When debugging data quality issues
- To understand memory formation results
- Before/after data fixes

---

## 📊 reporting/

**Purpose:** Export data for analysis and generate comprehensive reports.

### Scripts

| Script | Purpose | Usage |
|--------|---------|-------|
| `export_memory_samples.py` | Export sample rows from all tables | `python scripts/reporting/export_memory_samples.py` |
| `export_memory_tables.py` | Full markdown export of memory system | `python scripts/reporting/export_memory_tables.py` |
| `visualize_memory_layers.py` | Generate memory layers report (571 lines) | `python scripts/reporting/visualize_memory_layers.py` |

**When to use:**
- Generate reports for stakeholders
- Export data for external analysis
- Create documentation snapshots
- Share memory system state

---

## 🔧 data_management/

**Purpose:** Clean, fix, and consolidate data in the memory system.

### Scripts

| Script | Purpose | Usage |
|--------|---------|-------|
| `clear_p03_data.py` | Delete all P03 output tables | `python scripts/data_management/clear_p03_data.py` |
| `consolidate_batches.py` | Run P03 consolidation in batches (278 lines) | `python scripts/data_management/consolidate_batches.py --max-batches 10` |
| `fix_data_quality_bugs.py` | Fix known data quality issues (364 lines) | `python scripts/data_management/fix_data_quality_bugs.py` |

**When to use:**
- Before fresh test runs (clear_p03_data)
- Process large event backlogs (consolidate_batches)
- Fix entity typing, sentiment, or topic issues

**⚠️ Warning:** `clear_p03_data.py` deletes data. Use with caution.

---

## 🔐 provisioning/

**Purpose:** Register devices and set up authentication.

### Scripts

| Script | Purpose | Usage |
|--------|---------|-------|
| `provision_device.py` | Full device provisioning CLI (388 lines) | `python scripts/provisioning/provision_device.py --device-id <id> --tenant-id <tid>` |
| `provision_and_submit.py` | Provision + submit test event (344 lines) | `python scripts/provisioning/provision_and_submit.py` |

**When to use:**
- Register new devices before first use
- Test device authentication flow
- Set up test environments

---

## 📨 events/

**Purpose:** Submit test events to the K0 kernel for processing.

### Scripts

| Script | Purpose | Usage |
|--------|---------|-------|
| `multi_envelope.py` | Submit multiple envelopes (616 lines) | `python scripts/events/multi_envelope.py` |
| `submit_diverse_events.py` | Diverse events for P03 testing (1030 lines) | `python scripts/events/submit_diverse_events.py` |
| `submit_gap_clarifications.py` | Events to resolve learning gaps (376 lines) | `python scripts/events/submit_gap_clarifications.py` |
| `submit_reallife_events.py` | Realistic daily schedule events (879 lines) | `python scripts/events/submit_reallife_events.py` |
| `submit_test_events.py` | Algorithm-specific test events (582 lines) | `python scripts/events/submit_test_events.py` |

**When to use:**
- Test P03 consolidation algorithms
- Generate realistic memory data
- Test entity resolution
- Validate temporal patterns

**Event Types:**
- **diverse_events**: Tests R2 clustering, R3 dedup, R4 entity extraction
- **reallife_events**: Simulates realistic daily routines
- **gap_clarifications**: Resolves ambiguous entities
- **test_events**: Focused algorithm testing

---

## 🧪 testing/

**Purpose:** Validate components, measure performance, and test integrations.

### Scripts

| Script | Purpose | Usage |
|--------|---------|-------|
| `load_test.py` | Command port throughput/latency test (384 lines) | `python scripts/testing/load_test.py --duration 60 --concurrency 10` |
| `test_all_ports.py` | Test all K0 ports (362 lines) | `python scripts/testing/test_all_ports.py` |
| `test_db.py` | Basic database connectivity check | `python scripts/testing/test_db.py` |
| `test_recall_queries.py` | Test FAISS recall queries | `python scripts/testing/test_recall_queries.py` |
| `test_ultrabert_family.py` | Test UltraBERT 12 capabilities | `python scripts/testing/test_ultrabert_family.py` |

**When to use:**
- Validate deployment health (test_all_ports)
- Measure performance under load (load_test)
- Test recall/search (test_recall_queries)

---

## 🌱 seeding/

**Purpose:** Initialize foundational data in the system.

### Scripts

| Script | Purpose | Usage |
|--------|---------|-------|
| `seed_family_graph.py` | Seed family relationships (513 lines) | `python scripts/seeding/seed_family_graph.py --interactive` |

**When to use:**
- Initial system setup
- Populate family graph (st_kg_dom, st_kg_edges)
- Test social memory features

**Architecture:** Implements ADR-K022 (PostgreSQL-only graph storage, replaces Neo4j)

---

## 🚀 Quick Start Workflows

### Fresh System Setup
```powershell
# 1. Provision device
python scripts/provisioning/provision_device.py --device-id device-001 --tenant-id tenant-test --space-id space-home

# 2. Seed family graph
python scripts/seeding/seed_family_graph.py --interactive

# 3. Submit realistic events
python scripts/events/submit_reallife_events.py

# 4. Run consolidation
python scripts/data_management/consolidate_batches.py --max-batches 5

# 5. Validate results
python scripts/validation/query_memories.py
python scripts/validation/explore_memory_layers.py
```

### Data Quality Check
```powershell
# Check schemas
python scripts/validation/check_schemas.py

# Check data quality
python scripts/validation/check_quality.py

# Check embeddings
python scripts/validation/check_embeddings.py

# Generate report
python scripts/reporting/visualize_memory_layers.py
```

### Performance Testing
```powershell
# Test all ports
python scripts/testing/test_all_ports.py

# Load test
python scripts/testing/load_test.py --duration 60 --concurrency 10

# Test recall
python scripts/testing/test_recall_queries.py
```

### Clean Slate
```powershell
# ⚠️ WARNING: Deletes all P03 data
python scripts/data_management/clear_p03_data.py

# Submit fresh events
python scripts/events/submit_diverse_events.py

# Consolidate
python scripts/data_management/consolidate_batches.py
```

---

## 🔗 Related Documentation

- [Deploy README](../readme.md) - Main deployment guide
- [Quick Start](../QUICK_START.md) - Getting started guide
- [K0 Runbook](../k0-runbook-device-provisioning-multikernel.md) - Device provisioning guide

---

## 📝 Notes

1. **Database Connection:** Most scripts connect to `postgresql://k0user:changeme@localhost:5432/k0_kernel`
2. **Docker Required:** Some scripts use `docker exec` to run SQL commands
3. **Python Path:** Scripts may need project root in PYTHONPATH
4. **Async Scripts:** Most use `asyncio` and `asyncpg` for database access

---

**Last Updated:** January 18, 2026
