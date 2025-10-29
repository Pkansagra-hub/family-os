# L5 Infrastructure Analysis Scripts

This directory contains scripts for analyzing the L5 infrastructure layer of the K1 system.

## Scripts Overview

### 1. `analyze_l5_connections.py`
Analyzes all stub files in `k1/l5_infrastructure/` to extract upstream and downstream connections.

**Usage:**
```bash
python scripts/analyze_l5_connections.py
```

**Outputs:**
- `scripts/output/l5_connections.json` - Detailed connection data
- `scripts/output/l5_connections_summary.txt` - Human-readable summary
- `scripts/output/l5_connection_patterns.txt` - Pattern analysis

### 2. `generate_l5_connection_diagram.py`
Creates a Mermaid diagram from the connection analysis output.

**Usage:**
```bash
python scripts/generate_l5_connection_diagram.py
```

**Outputs:**
- `scripts/output/l5_infrastructure_connections.mmd` - Mermaid diagram
- `scripts/output/l5_connection_diagram_readme.md` - Diagram statistics

## Complete Workflow

```bash
# Step 1: Extract connections from stub files
python scripts/analyze_l5_connections.py

# Step 2: Generate visual diagram
python scripts/generate_l5_connection_diagram.py

# Optional: Convert diagram to image
npm install -g @mermaid-js/mermaid-cli
mmdc -i scripts/output/l5_infrastructure_connections.mmd -o l5_connections.png
```

## Analysis Results Summary

**Current Status** (as of latest run):
- **94 total stub files** analyzed
- **50 files with connections** (53% coverage)
- **160 total connections** found

### Most Connected Components
1. **BACKPRESSURE**: 9 modules, 18 connections
2. **BRIDGE_K0**: 11 modules, 22 connections
3. **PLACEMENT**: 7 modules, 16 connections
4. **CACHING**: 7 modules, 9 connections

### Most Connected Modules
- `backpressure.metrics`: 6 connections
- `backpressure.backpressure_manager`: 5 connections
- `placement.metrics`: 5 connections

## Mermaid Diagram Features

### Visual Elements
- **🔷 Blue nodes**: L5 Infrastructure modules (internal components)
- **🔶 Orange nodes**: External systems and services
- **Subgraphs**: Components grouped by functionality
- **Arrows**: Data flow direction (upstream → downstream)

### Viewing Options
1. **VS Code**: Install Mermaid preview extension
2. **GitHub/GitLab**: Native markdown rendering
3. **Browser**: Use mermaid.live editor
4. **Images**: Convert with mermaid-cli

## Architecture Insights

The L5 infrastructure serves as a **coordination layer** that:

- **Receives** telemetry and control signals from higher layers (L2, L3)
- **Coordinates** with K0 bridge for external communications
- **Manages** cross-cutting concerns (caching, rate limiting, placement, backpressure)
- **Exports** metrics to monitoring systems (Prometheus, Grafana)

### Key Integration Points
- **Orchestrator** → Most modules (central coordination hub)
- **Agent Fabric** → Rate limiting, caching, scheduling
- **Model Hub** → Placement decisions
- **External APIs** → Bridge K0 components

## Connection Data Structure

Connections are extracted from "Connects To:" sections in stub file docstrings:

```python
"""
Connects To:
    Upstream:
        - k1.l2_orchestration.orchestrator (control signals)
        - k1.telemetry.metrics_collector (metrics data)
    Downstream:
        - k1.api.gateway (HTTP responses)
        - Prometheus server (metrics export)
"""
```

## Dependencies

- Python 3.6+
- Standard library only (pathlib, json, re)

## Other Scripts

- `check_missing_adrs.py` - Validates ADR references
- `generate_k1_metrics.py` - Generates metrics documentation
- `generate_layer_adr_references.py` - Creates ADR reference tables
