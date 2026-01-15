#!/usr/bin/env python3
"""
Export all memory tables from k0_kernel database to markdown.

Usage:
    python k0/deploy/export_memory_tables.py
    python k0/deploy/export_memory_tables.py --output data/memory_export.md
"""

import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Memory layer tables (organized by layer)
MEMORY_TABLES = {
    "Episodic Memory (Hippocampus)": [
        "st_hipp_events",
        "st_epi",
        "st_vec",
        "st_embedding_queue",
    ],
    "Semantic Memory (Knowledge Graph)": [
        "st_kg_dom",
        "st_kg_edges",
        "st_sem",
    ],
    "Social Memory": [
        "st_social",
        "st_relationships",
        "st_anchors",
        "st_anchor_observations",
    ],
    "Procedural Memory": [
        "st_procedural",
    ],
    "Prospective Memory": [
        "st_prospective",
    ],
    "Learning & Feedback": [
        "st_learning_queue",
        "st_learned_weights",
        "st_learned_weights_history",
        "st_feedback_signals",
        "st_feedback_quarantine",
        "st_decay_feedback",
        "st_golden_dataset_pairs",
    ],
    "Entity Resolution": [
        "st_entity_merges",
        "st_entity_resolutions",
        "st_pruned_entities",
    ],
    "Pipeline State": [
        "st_offsets",
        "st_pipeline_status",
        "st_pipeline_watermarks",
        "st_pipeline_processed",
        "st_consolidation_audit",
    ],
    "Infrastructure": [
        "st_devices",
        "st_device_keys",
        "st_acl",
        "st_retention_policy",
        "st_outbox",
        "st_dlq",
        "st_wal",
        "st_receipts",
        "st_validation_results",
        "st_archive_manifest",
        "st_obligation_log",
        "st_crdt_merge_log",
        "st_mcts_decisions",
        "st_mcts_shadow_log",
        "idem_ledger",
    ],
    "Core Tables": [
        "households",
        "people",
    ],
}

# Tables to show full data (small reference tables)
FULL_DATA_TABLES = [
    "st_epi",
    "st_kg_dom",
    "st_kg_edges",
    "st_anchors",
    "st_relationships",
    "st_offsets",
    "st_pipeline_status",
    "st_retention_policy",
    "households",
    "people",
    "st_devices",
]

# Sample limit for large tables
SAMPLE_LIMIT = 10


def run_psql(query: str) -> str:
    """Run a psql query and return output."""
    cmd = [
        "docker",
        "exec",
        "k0-postgres",
        "psql",
        "-U",
        "k0user",
        "-d",
        "k0_kernel",
        "-P",
        "pager=off",
        "-c",
        query,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        return "(query timed out)"
    except Exception as e:
        return f"(error: {e})"


def get_table_count(table: str) -> int:
    """Get row count for a table."""
    output = run_psql(f"SELECT COUNT(*) FROM {table};")
    try:
        # Parse "count\n-------\n   123" format
        lines = output.strip().split("\n")
        for line in lines:
            line = line.strip()
            if line.isdigit():
                return int(line)
        return 0
    except:
        return 0


def get_table_schema(table: str) -> str:
    """Get table schema (columns)."""
    query = f"""
    SELECT column_name, data_type, is_nullable
    FROM information_schema.columns
    WHERE table_name = '{table}'
    ORDER BY ordinal_position;
    """
    return run_psql(query)


def get_table_data(table: str, limit: int = None) -> str:
    """Get table data."""
    if limit:
        query = f"SELECT * FROM {table} LIMIT {limit};"
    else:
        query = f"SELECT * FROM {table};"
    return run_psql(query)


def get_table_sample(table: str) -> str:
    """Get a sample of table data with key columns."""
    # Special handling for large tables - show meaningful columns
    special_queries = {
        "st_hipp_events": """
            SELECT event_id, activity_type, ingress_topic,
                   LEFT(text, 60) as text_preview,
                   created_at::date as date
            FROM st_hipp_events
            ORDER BY created_at DESC LIMIT 10;
        """,
        "st_vec": """
            SELECT event_id, vector_type, model_version,
                   created_at::date as date
            FROM st_vec
            ORDER BY created_at DESC LIMIT 10;
        """,
        "st_embedding_queue": """
            SELECT event_id, status, attempts,
                   created_at::date as date
            FROM st_embedding_queue
            ORDER BY created_at DESC LIMIT 10;
        """,
        "st_learning_queue": """
            SELECT event_id, status, priority,
                   created_at::date as date
            FROM st_learning_queue
            ORDER BY created_at DESC LIMIT 10;
        """,
    }

    if table in special_queries:
        return run_psql(special_queries[table])
    else:
        return run_psql(f"SELECT * FROM {table} LIMIT {SAMPLE_LIMIT};")


def export_to_markdown(output_path: str):
    """Export all memory tables to markdown."""
    lines = []

    # Header
    lines.append("# K0 Memory Tables Export")
    lines.append("")
    lines.append(f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("**Database**: k0_kernel")
    lines.append("")

    # Table of Contents
    lines.append("## Table of Contents")
    lines.append("")
    for layer_name in MEMORY_TABLES.keys():
        anchor = layer_name.lower().replace(" ", "-").replace("(", "").replace(")", "")
        lines.append(f"- [{layer_name}](#{anchor})")
    lines.append("")

    # Summary
    lines.append("## Summary")
    lines.append("")
    lines.append("| Layer | Table | Row Count |")
    lines.append("|-------|-------|-----------|")

    total_rows = 0
    for layer_name, tables in MEMORY_TABLES.items():
        for table in tables:
            count = get_table_count(table)
            total_rows += count
            lines.append(f"| {layer_name} | `{table}` | {count:,} |")

    lines.append(f"| **TOTAL** | | **{total_rows:,}** |")
    lines.append("")

    # Detailed sections
    for layer_name, tables in MEMORY_TABLES.items():
        anchor = layer_name.lower().replace(" ", "-").replace("(", "").replace(")", "")
        lines.append(f"## {layer_name}")
        lines.append("")

        for table in tables:
            lines.append(f"### {table}")
            lines.append("")

            count = get_table_count(table)
            lines.append(f"**Row Count**: {count:,}")
            lines.append("")

            # Schema
            lines.append("**Schema**:")
            lines.append("```")
            lines.append(get_table_schema(table))
            lines.append("```")
            lines.append("")

            # Data
            if count > 0:
                if table in FULL_DATA_TABLES or count <= SAMPLE_LIMIT:
                    lines.append("**Data**:")
                else:
                    lines.append(
                        f"**Sample Data** (showing {min(count, SAMPLE_LIMIT)} of {count:,} rows):"
                    )

                lines.append("```")
                if table in FULL_DATA_TABLES:
                    lines.append(get_table_data(table))
                else:
                    lines.append(get_table_sample(table))
                lines.append("```")
            else:
                lines.append("*No data*")

            lines.append("")
            lines.append("---")
            lines.append("")

    # Write to file
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines), encoding="utf-8")

    print(
        f"Exported {total_rows:,} total rows from {sum(len(t) for t in MEMORY_TABLES.values())} tables"
    )
    print(f"Output: {output_path}")


def main():
    # Default output path
    output_path = "data/memory_tables_export.md"

    # Check for --output argument
    if "--output" in sys.argv:
        idx = sys.argv.index("--output")
        if idx + 1 < len(sys.argv):
            output_path = sys.argv[idx + 1]

    export_to_markdown(output_path)


if __name__ == "__main__":
    main()
