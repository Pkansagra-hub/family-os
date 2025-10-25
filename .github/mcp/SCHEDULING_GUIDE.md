# Knowledge Graph Reindexing & Scheduling Guide

## Quick Start

### Mode Selection

```
┌─────────────────────────────────────────────────────────────┐
│         Choose Your Reindexing Mode                          │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Development/Quick Test                                      │
│  └─→ python reindex_kg.py                                  │
│      • Full reindex with embeddings                         │
│      • One-time only                                         │
│      • ~60 seconds                                           │
│                                                              │
│  Development/Auto-Update                                     │
│  └─→ python kg_scheduler.py --watch                         │
│      • Polls every 10 seconds                               │
│      • Auto-reindex on file change                          │
│      • Press Ctrl+C to stop                                 │
│                                                              │
│  Production/Background                                       │
│  └─→ python kg_scheduler.py --daemon --interval 21600       │
│      • Reindex every 6 hours (default)                      │
│      • Automatic maintenance (WAL, ANALYZE)                 │
│      • Runs in background                                   │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## Detailed Architecture

### 1. Full Reindex Flow

```
reindex_kg.py or kg_scheduler.py --full
        │
        ├─→ Load KGStore (kg.sqlite3)
        │
        ├─→ ADRIndexer.index_all("docs/architecture/decisions")
        │   ├─ Scan *.md files
        │   ├─ Extract: status, date, tags, references
        │   ├─ Generate embeddings (384-dim)
        │   └─ Return stats: indexed, errors, skipped
        │
        ├─→ ModuleIndexer.index_all("k0")
        │   ├─ Scan *.py files (recursive)
        │   ├─ Parse: classes, functions, imports
        │   ├─ Build hierarchy: k0.module.submodule
        │   └─ Return stats
        │
        ├─→ ModuleIndexer.index_all("k1")
        │   └─ (same as k0)
        │
        ├─→ ContractIndexer.index_all("k0/contracts")
        │   ├─ Scan *.yaml (OpenAPI)
        │   ├─ Scan *.json (JSON Schema)
        │   ├─ Validate against contracts
        │   └─ Return stats
        │
        ├─→ ContractIndexer.index_all("k1/contracts")
        │   └─ (same as k0)
        │
        └─→ Print Summary
            ├─ Total nodes: 1,204 (335 ADRs + 277 modules + 592 contracts)
            ├─ Total edges: 1,448
            ├─ Embeddings: 384-dimensional
            └─ Duration: ~60 seconds
```

### 2. Watch Mode Flow

```
kg_scheduler.py --watch --interval 10
        │
        └─→ While True:
            │
            ├─ Get all files to watch:
            │  ├─ ADRs: docs/architecture/decisions/*.md
            │  ├─ Modules: k0/**/*.py, k1/**/*.py
            │  └─ Contracts: */contracts/**/*.{yaml,json}
            │
            ├─ For each file:
            │  ├─ Check mtime (modification time)
            │  └─ If mtime > last_check[file]:
            │     ├─ Mark changed = True
            │     └─ Log: "Detected change: {file}"
            │
            ├─ If changed:
            │  └─→ full_reindex()
            │
            └─ sleep(10)
```

**Characteristics**:
- **Polling**: File system check every interval
- **Latency**: ~10 seconds from file save to reindex complete
- **CPU Impact**: <1% when no changes detected
- **Use Case**: Local development

### 3. Daemon Mode Flow

```
kg_scheduler.py --daemon --interval 21600
        │
        └─→ While True:
            │
            ├─→ full_reindex()
            │   └─ (as above)
            │
            ├─→ maintenance_counter += 1
            │
            ├─→ Check: maintenance_counter % 5 == 0 (every 5 min)
            │   └─ PRAGMA wal_checkpoint(RESTART)
            │      └─ Flush write-ahead log to main DB
            │
            ├─→ Check: maintenance_counter % 30 == 0 (every 30 min)
            │   └─ PRAGMA ANALYZE
            │      └─ Update query optimizer stats
            │
            ├─ sleep(21600)  # 6 hours default
            │
            └─→ (repeat)

On Shutdown (Ctrl+C):
        └─→ Final PRAGMA wal_checkpoint(RESTART)
```

**Characteristics**:
- **Interval**: Configurable (default: 6h)
- **Maintenance**: Automatic every 5/30 minutes
- **CPU Impact**: Spike during reindex, minimal between
- **Use Case**: Production server, scheduled updates

## Scheduling Scenarios

### Scenario 1: Local Development

```bash
# Terminal 1: Start daemon with shorter interval
$ python kg_scheduler.py --watch --interval 5

# Edit files in editor
# ↓ (automatic reindex)
# Graph updated in ~5 seconds
```

### Scenario 2: CI/CD Pipeline

```bash
# After commit, before deployment
$ python reindex_kg.py

# Fresh graph with all embeddings
# Database file: .github/copilot-memories/kg.sqlite3
# ~60 seconds
```

### Scenario 3: Production Server

```bash
# Start daemon at boot
$ nohup python kg_scheduler.py --daemon --interval 21600 &

# Runs in background
# Reindex every 6 hours
# Maintenance every 5/30 minutes
# Survives network disconnections
```

### Scenario 4: Frequent Updates

```bash
# More frequent reindexing for rapid development
$ python kg_scheduler.py --daemon --interval 3600

# Reindex every 1 hour
# Lower latency
# Higher CPU/I/O
```

## Database Paths

### Default Location

```
Repository Root/
  .github/
    copilot-memories/
      kg.sqlite3        ← Default database

# Resolved as:
Path(__file__).resolve().parent.parent.parent / ".github" / "copilot-memories" / "kg.sqlite3"
```

### Custom Location

```bash
$ python kg_scheduler.py --full --db /custom/path/kg.sqlite3
$ python kg_scheduler.py --watch --db /custom/path/kg.sqlite3
$ python kg_scheduler.py --daemon --db /custom/path/kg.sqlite3
```

## Performance Characteristics

### Reindex Time Breakdown

```
Total: ~60 seconds (with embeddings)

├─ ADRs (335):       ~5 seconds
│  └─ Embeddings:    ~3 seconds
│
├─ Modules (277):    ~15 seconds
│  ├─ K0 (143):      ~7 seconds
│  ├─ K1 (134):      ~8 seconds
│  └─ Embeddings:    ~10 seconds
│
├─ Contracts (592):  ~35 seconds
│  ├─ K0 (72):       ~3 seconds
│  ├─ K1 (600):      ~30 seconds
│  └─ Bridge:        ~2 seconds
│
└─ Store overhead:   ~5 seconds
   └─ FTS indexing:  ~3 seconds
```

### Resource Usage

| Resource | Watch Mode | Daemon Mode | Reindex Peak |
|----------|-----------|-----------|---------------|
| CPU | <1% idle | <5% idle | 30-50% during reindex |
| Memory | 100MB | 200-300MB | +50MB during reindex |
| Disk I/O | Minimal | Low (WAL) | High during reindex |
| Network | None | None | None |

### Database Size

```
kg.sqlite3: ~50-100MB
├─ Nodes table:    ~20MB
├─ Edges table:    ~5MB
├─ FTS5 index:     ~15MB
├─ Embeddings:     ~25MB
└─ WAL file:       ~5MB (dynamic)
```

## Monitoring & Logging

### Console Output

#### Full Reindex
```
[2025-10-25 14:32:15] Starting full reindex...
Indexing ADRs...
Indexing modules...
Indexing contracts...
[2025-10-25 14:33:05] Reindex complete in 50.23s
ADRs: 335 indexed, 0 errors
Modules: 277 indexed, 0 errors
Contracts: 592 indexed, 0 errors

Graph: 1204 nodes, 1448 edges
Types: {'adr': 335, 'module': 277, 'contract': 592}
```

#### Watch Mode
```
[2025-10-25 14:35:00] Starting watch mode (checking every 10s)...
Press Ctrl+C to stop
[2025-10-25 14:35:23] Detected change: k1/l2_orchestration/orchestrator.py
[2025-10-25 14:35:23] Reindexing...
[2025-10-25 14:35:30] Reindex complete in 7.12s
```

#### Daemon Mode
```
[2025-10-25 14:40:00] Starting daemon mode (interval: 21600s = 6.0h)...
[2025-10-25 14:40:05] Reindex complete in 52.10s
[2025-10-25 14:40:05] Next reindex in 6.0 hours...
[2025-10-25 14:45:05] ✓ WAL checkpoint completed
[2025-10-25 14:50:05] ✓ WAL checkpoint completed
[2025-10-25 15:10:05] ✓ PRAGMA ANALYZE completed (query optimizer updated)
```

## Troubleshooting

### Issue: "FileNotFoundError: docs/architecture/decisions"

**Cause**: Running from wrong directory

**Solution**:
```bash
# Run from repository root
cd /path/to/familyos
python kg_scheduler.py --full
```

### Issue: "database is locked"

**Cause**: Multiple schedulers writing simultaneously

**Solution**:
```bash
# Kill existing scheduler
pkill -f "kg_scheduler.py --daemon"

# Start fresh
python kg_scheduler.py --daemon
```

### Issue: "sentence-transformers not installed"

**Cause**: Optional dependency missing

**Solution**:
```bash
# Install optional dependency
pip install sentence-transformers

# Reindex will gracefully fallback to empty embeddings
python reindex_kg.py
```

### Issue: "WAL file growing too large"

**Cause**: Checkpoint not running or blocked

**Solution**:
```bash
# Check for stale locks
ls -la .github/copilot-memories/

# Manually checkpoint
sqlite3 .github/copilot-memories/kg.sqlite3 "PRAGMA wal_checkpoint(RESTART);"
```

## Advanced Configuration

### Custom Interval Examples

```bash
# Every 30 minutes (rapid development)
python kg_scheduler.py --daemon --interval 1800

# Every 1 hour
python kg_scheduler.py --daemon --interval 3600

# Every 12 hours
python kg_scheduler.py --daemon --interval 43200

# Every 24 hours (nightly)
python kg_scheduler.py --daemon --interval 86400
```

### Running as Systemd Service (Linux)

Create `/etc/systemd/system/kg-scheduler.service`:

```ini
[Unit]
Description=Knowledge Graph Scheduler
After=network.target

[Service]
Type=simple
User=copilot
WorkingDirectory=/home/copilot/familyos
ExecStart=/usr/bin/python3 .github/mcp/kg_scheduler.py --daemon --interval 21600
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
# Install
sudo systemctl enable kg-scheduler
sudo systemctl start kg-scheduler

# Check status
sudo systemctl status kg-scheduler

# View logs
sudo journalctl -u kg-scheduler -f
```

## Summary

| Mode | Command | Interval | Use Case |
|------|---------|----------|----------|
| **Full** | `reindex_kg.py` | One-time | Initial setup, CI/CD |
| **Watch** | `--watch --interval 10` | 10s polling | Local development |
| **Daemon** | `--daemon --interval 21600` | Configurable | Production server |

Choose based on your needs:
- **Development**: Watch mode for real-time updates
- **CI/CD**: Full reindex after each commit
- **Production**: Daemon mode with 6-24h interval
