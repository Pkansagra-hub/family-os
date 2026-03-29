#!/usr/bin/env python3
"""
Visualize P03 Memory Layers
---------------------------
Generates a comprehensive Markdown report showing data flow from
raw hippocampus events through all 7 P03 memory output layers.

Memory Layers:
  INPUT:  st_hipp_events (raw memories)
  OUTPUT: st_vec, st_social, st_epi, st_kg_dom, st_kg_edges, st_learning_queue, st_outbox
"""

import asyncio
import os
from datetime import datetime, timezone

import asyncpg


async def generate_memory_report(dsn: str, output_path: str = "memory_layers_report.md"):
    """Generate a comprehensive markdown report of all memory layers."""

    # Disable statement cache for pgbouncer compatibility
    conn = await asyncpg.connect(dsn, statement_cache_size=0)

    lines = []

    def add(text: str = ""):
        lines.append(text)

    def add_table(headers: list, rows: list):
        """Add a markdown table."""
        add("| " + " | ".join(headers) + " |")
        add("| " + " | ".join(["---"] * len(headers)) + " |")
        for row in rows:
            cleaned = [str(cell).replace("|", "\\|").replace("\n", " ")[:80] for cell in row]
            add("| " + " | ".join(cleaned) + " |")

    # Header
    add("# 🧠 P03 Memory Layers Report")
    add()
    add(f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    add()

    # ========== TABLE COUNTS SUMMARY ==========
    add("## 📊 Memory Layer Summary")
    add()

    counts = await conn.fetch(
        """
        SELECT 'st_hipp_events' as tbl, COUNT(*) as cnt FROM st_hipp_events
        UNION ALL SELECT 'st_vec', COUNT(*) FROM st_vec
        UNION ALL SELECT 'st_social', COUNT(*) FROM st_social
        UNION ALL SELECT 'st_epi', COUNT(*) FROM st_epi
        UNION ALL SELECT 'st_kg_dom', COUNT(*) FROM st_kg_dom
        UNION ALL SELECT 'st_kg_edges', COUNT(*) FROM st_kg_edges
        UNION ALL SELECT 'st_learning_queue', COUNT(*) FROM st_learning_queue
        UNION ALL SELECT 'st_outbox', COUNT(*) FROM st_outbox
    """
    )

    add("| Layer | Table | Rows | Description |")
    add("| --- | --- | ---: | --- |")
    descriptions = {
        "st_hipp_events": "Raw input memories (hippocampus buffer)",
        "st_vec": "Vector embeddings for semantic search",
        "st_social": "Social relationships extracted",
        "st_epi": "Episodic memories (clustered events)",
        "st_kg_dom": "Knowledge graph entities",
        "st_kg_edges": "Knowledge graph relationships",
        "st_learning_queue": "Learning gaps (questions for clarification)",
        "st_outbox": "Published events for downstream consumers",
    }
    layer_num = 0
    for row in counts:
        tbl = row["tbl"]
        layer_label = "INPUT" if tbl == "st_hipp_events" else f"L{layer_num}"
        add(f"| {layer_label} | `{tbl}` | {row['cnt']} | {descriptions.get(tbl, '')} |")
        if tbl != "st_hipp_events":
            layer_num += 1
    add()

    # ========== LAYER 0: HIPPOCAMPUS EVENTS ==========
    add("---")
    add("## 📥 INPUT: st_hipp_events (Raw Memories)")
    add()
    add("These are the raw memories ingested into the hippocampus buffer.")
    add()

    # Sample events
    events = await conn.fetch(
        """
        SELECT event_id, topic, LEFT(text, 100) as text_preview,
               sentiment_label, affect_band, salience_band,
               num_participants, location_name
        FROM st_hipp_events
        ORDER BY ingested_at DESC
        LIMIT 15
    """
    )

    add("### Sample Memories (15 most recent)")
    add()
    add_table(
        [
            "Event ID (short)",
            "Text Preview",
            "Sentiment",
            "Affect",
            "Salience",
            "Participants",
            "Location",
        ],
        [
            [
                r["event_id"][:12],
                r["text_preview"] or "",
                r["sentiment_label"] or "",
                r["affect_band"] or "",
                r["salience_band"] or "",
                r["num_participants"] or 0,
                r["location_name"] or "",
            ]
            for r in events
        ],
    )
    add()

    # Sentiment distribution
    sentiment_dist = await conn.fetch(
        """
        SELECT sentiment_label, COUNT(*) as cnt
        FROM st_hipp_events
        GROUP BY sentiment_label
        ORDER BY cnt DESC
    """
    )
    add("### Sentiment Distribution")
    add()
    add_table(
        ["Sentiment", "Count"],
        [[r["sentiment_label"] or "unknown", r["cnt"]] for r in sentiment_dist],
    )
    add()

    # Affect band distribution
    affect_dist = await conn.fetch(
        """
        SELECT affect_band, COUNT(*) as cnt
        FROM st_hipp_events
        GROUP BY affect_band
        ORDER BY cnt DESC
    """
    )
    add("### Affect Band Distribution")
    add()
    add_table(
        ["Affect Band", "Count"], [[r["affect_band"] or "unknown", r["cnt"]] for r in affect_dist]
    )
    add()

    # ========== LAYER 1: VECTORS ==========
    add("---")
    add("## 🔢 L1: st_vec (Vector Embeddings)")
    add()
    add("Dense vector representations enabling semantic similarity search.")
    add()

    vec_stats = await conn.fetchrow(
        """
        SELECT COUNT(*) as total,
               COUNT(DISTINCT model_id) as models
        FROM st_vec
    """
    )
    add(f"- **Total embeddings:** {vec_stats['total']}")
    add(f"- **Model IDs:** {vec_stats['models']}")
    add()

    vec_samples = await conn.fetch(
        """
        SELECT v.embedding_id, v.event_id, v.model_id, v.vector_dim,
               LEFT(e.text, 60) as source_text
        FROM st_vec v
        JOIN st_hipp_events e ON v.event_id = e.event_id
        LIMIT 5
    """
    )
    add("### Sample Embeddings")
    add()
    add_table(
        ["Embedding ID (short)", "Event ID (short)", "Model", "Dim", "Source Text"],
        [
            [
                r["embedding_id"][:16],
                r["event_id"][:12],
                r["model_id"] or "",
                r["vector_dim"],
                r["source_text"] or "",
            ]
            for r in vec_samples
        ],
    )
    add()

    # ========== LAYER 2: SOCIAL RELATIONSHIPS ==========
    add("---")
    add("## 👥 L2: st_social (Social Relationships)")
    add()
    add("Extracted relationships between the user and other people.")
    add()

    # Relationship type distribution
    rel_types = await conn.fetch(
        """
        SELECT relationship_type, COUNT(*) as cnt,
               array_agg(DISTINCT actor_b_id) as actors
        FROM st_social
        GROUP BY relationship_type
        ORDER BY cnt DESC
    """
    )

    for r in rel_types:
        actors = r["actors"][:10] if r["actors"] else []
        add(f"### {r['relationship_type']} ({r['cnt']} relationships)")
        add()
        add(f"**People:** {', '.join(actors)}" + (" ..." if len(r["actors"] or []) > 10 else ""))
        add()

    # Sample relationships
    social_samples = await conn.fetch(
        """
        SELECT relationship_id, actor_b_id, relationship_type, relationship_subtype,
               emotional_role, emotional_valence_avg, interaction_count, confidence_score
        FROM st_social
        ORDER BY confidence_score DESC
        LIMIT 10
    """
    )

    add("### Top 10 Relationships (by confidence)")
    add()
    add_table(
        [
            "ID (short)",
            "Person",
            "Type",
            "Subtype",
            "Emotional Role",
            "Valence",
            "Interactions",
            "Confidence",
        ],
        [
            [
                r["relationship_id"][:16],
                r["actor_b_id"] or "",
                r["relationship_type"] or "",
                r["relationship_subtype"] or "",
                r["emotional_role"] or "",
                f"{r['emotional_valence_avg']:.2f}" if r["emotional_valence_avg"] else "",
                r["interaction_count"] or 0,
                f"{r['confidence_score']:.2f}" if r["confidence_score"] else "",
            ]
            for r in social_samples
        ],
    )
    add()

    # ========== LAYER 3: EPISODIC MEMORIES ==========
    add("---")
    add("## 📖 L3: st_epi (Episodic Memories)")
    add()
    add("Clustered events forming coherent episodes/experiences.")
    add()

    episodes = await conn.fetch(
        """
        SELECT episode_id, episode_type, episode_summary,
               source_event_count, participant_count, primary_location,
               duration_minutes, confidence_score
        FROM st_epi
        ORDER BY source_event_count DESC
    """
    )

    add("### All Episodes")
    add()
    add_table(
        [
            "Episode ID (short)",
            "Type",
            "Summary",
            "Events",
            "Participants",
            "Location",
            "Duration (min)",
            "Confidence",
        ],
        [
            [
                r["episode_id"][:20],
                r["episode_type"] or "",
                r["episode_summary"] or "",
                r["source_event_count"],
                r["participant_count"] or 0,
                r["primary_location"] or "",
                r["duration_minutes"] or "",
                f"{r['confidence_score']:.2f}" if r["confidence_score"] else "",
            ]
            for r in episodes
        ],
    )
    add()

    # ========== LAYER 4: KNOWLEDGE GRAPH ENTITIES ==========
    add("---")
    add("## 🏷️ L4: st_kg_dom (Knowledge Graph Entities)")
    add()
    add("Extracted entities forming the semantic knowledge graph.")
    add()

    # Entity type distribution
    entity_types = await conn.fetch(
        """
        SELECT entity_type, COUNT(*) as cnt
        FROM st_kg_dom
        GROUP BY entity_type
        ORDER BY cnt DESC
    """
    )

    add("### Entity Type Distribution")
    add()
    add_table(["Entity Type", "Count"], [[r["entity_type"], r["cnt"]] for r in entity_types])
    add()

    # Sample entities by type
    for etype in entity_types[:5]:
        entities = await conn.fetch(
            """
            SELECT entity_id, canonical_name, entity_subtype, observation_count, confidence_score
            FROM st_kg_dom
            WHERE entity_type = $1
            ORDER BY observation_count DESC
            LIMIT 8
        """,
            etype["entity_type"],
        )

        add(f"### {etype['entity_type']} Entities ({etype['cnt']} total)")
        add()
        add_table(
            ["Entity ID (short)", "Name", "Subtype", "Observations", "Confidence"],
            [
                [
                    r["entity_id"][:24],
                    r["canonical_name"] or "",
                    r["entity_subtype"] or "",
                    r["observation_count"] or 1,
                    f"{r['confidence_score']:.2f}" if r["confidence_score"] else "",
                ]
                for r in entities
            ],
        )
        add()

    # ========== LAYER 5: KNOWLEDGE GRAPH EDGES ==========
    add("---")
    add("## 🔗 L5: st_kg_edges (Knowledge Graph Relationships)")
    add()
    add("Relationships between entities in the knowledge graph.")
    add()

    # Edge type distribution
    edge_types = await conn.fetch(
        """
        SELECT relation_type, COUNT(*) as cnt
        FROM st_kg_edges
        GROUP BY relation_type
        ORDER BY cnt DESC
    """
    )

    add("### Relationship Type Distribution")
    add()
    add_table(["Relation Type", "Count"], [[r["relation_type"], r["cnt"]] for r in edge_types])
    add()

    # Sample edges
    edges = await conn.fetch(
        """
        SELECT e.edge_id,
               s.canonical_name as source_name, s.entity_type as source_type,
               e.relation_type,
               t.canonical_name as target_name, t.entity_type as target_type,
               e.confidence_score
        FROM st_kg_edges e
        JOIN st_kg_dom s ON e.source_entity_id = s.entity_id
        JOIN st_kg_dom t ON e.target_entity_id = t.entity_id
        ORDER BY e.confidence_score DESC
        LIMIT 15
    """
    )

    add("### Top 15 Relationships (by confidence)")
    add()
    add_table(
        ["Source", "Type", "→ Relation →", "Target", "Type", "Confidence"],
        [
            [
                r["source_name"][:15],
                r["source_type"],
                r["relation_type"],
                r["target_name"][:15],
                r["target_type"],
                f"{r['confidence_score']:.2f}" if r["confidence_score"] else "",
            ]
            for r in edges
        ],
    )
    add()

    # ========== LAYER 6: LEARNING QUEUE ==========
    add("---")
    add("## 🎓 L6: st_learning_queue (Knowledge Gaps)")
    add()
    add("Identified gaps in understanding that could be clarified through questions.")
    add()

    # Gap type distribution
    gap_types = await conn.fetch(
        """
        SELECT gap_type, status, COUNT(*) as cnt
        FROM st_learning_queue
        GROUP BY gap_type, status
        ORDER BY cnt DESC
    """
    )

    add("### Gap Type Distribution")
    add()
    add_table(
        ["Gap Type", "Status", "Count"], [[r["gap_type"], r["status"], r["cnt"]] for r in gap_types]
    )
    add()

    # Top priority gaps
    gaps = await conn.fetch(
        """
        SELECT id, entity_id, gap_type, confidence_score, importance_score, status
        FROM st_learning_queue
        ORDER BY importance_score DESC NULLS LAST
        LIMIT 10
    """
    )

    add("### Top 10 Priority Gaps (by importance)")
    add()
    add_table(
        ["ID (short)", "Entity", "Gap Type", "Confidence", "Importance", "Status"],
        [
            [
                r["id"][-20:],
                r["entity_id"][:30] if r["entity_id"] else "",
                r["gap_type"],
                f"{r['confidence_score']:.2f}" if r["confidence_score"] else "",
                f"{r['importance_score']:.2f}" if r["importance_score"] else "",
                r["status"],
            ]
            for r in gaps
        ],
    )
    add()

    # ========== LAYER 7: OUTBOX ==========
    add("---")
    add("## 📤 L7: st_outbox (Published Events)")
    add()
    add("Events published for downstream consumers and integrations.")
    add()

    # Outbox distribution
    outbox_dist = await conn.fetch(
        """
        SELECT driver, op_kind, status, COUNT(*) as cnt
        FROM st_outbox
        GROUP BY driver, op_kind, status
        ORDER BY cnt DESC
    """
    )

    add("### Event Distribution")
    add()
    add_table(
        ["Driver", "Operation", "Status", "Count"],
        [[r["driver"], r["op_kind"], r["status"], r["cnt"]] for r in outbox_dist],
    )
    add()

    # ========== DATA FLOW DIAGRAM ==========
    add("---")
    add("## 🔄 Data Flow Diagram")
    add()
    add("```mermaid")
    add("flowchart TD")
    add('    subgraph INPUT["📥 Input Layer"]')
    add(f"        HIPP[\"st_hipp_events<br/>{counts[0]['cnt']} memories\"]")
    add("    end")
    add()
    add('    subgraph P03["🔄 P03 Consolidation Pipeline"]')
    add("        R0[R0: Init] --> R1[R1: Clustering]")
    add("        R1 --> R2[R2: Reconciliation]")
    add("        R2 --> R3[R3: Episode Formation]")
    add("        R3 --> R4[R4: Entity Extraction]")
    add("        R4 --> R5[R5: Gap Detection]")
    add("        R5 --> R6[R6: Staging]")
    add("        R6 --> R7[R7: Write]")
    add("        R7 --> R8[R8: Emit]")
    add("    end")
    add()
    add('    subgraph OUTPUT["📤 Output Layers"]')
    add(f"        VEC[\"st_vec<br/>{counts[1]['cnt']} embeddings\"]")
    add(f"        SOCIAL[\"st_social<br/>{counts[2]['cnt']} relationships\"]")
    add(f"        EPI[\"st_epi<br/>{counts[3]['cnt']} episodes\"]")
    add(f"        KG_DOM[\"st_kg_dom<br/>{counts[4]['cnt']} entities\"]")
    add(f"        KG_EDGE[\"st_kg_edges<br/>{counts[5]['cnt']} edges\"]")
    add(f"        LEARN[\"st_learning_queue<br/>{counts[6]['cnt']} gaps\"]")
    add(f"        OUTBOX[\"st_outbox<br/>{counts[7]['cnt']} events\"]")
    add("    end")
    add()
    add("    HIPP --> P03")
    add("    P03 --> VEC")
    add("    P03 --> SOCIAL")
    add("    P03 --> EPI")
    add("    P03 --> KG_DOM")
    add("    P03 --> KG_EDGE")
    add("    P03 --> LEARN")
    add("    P03 --> OUTBOX")
    add("```")
    add()

    # ========== FOOTER ==========
    add("---")
    add()
    add("*Report generated by `visualize_memory_layers.py`*")

    await conn.close()

    # Write report
    report_content = "\n".join(lines)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report_content)

    print(f"✅ Report generated: {output_path}")
    print(f"   Total lines: {len(lines)}")
    return output_path


async def main():
    dsn = os.getenv("K0_DB_DSN", "postgresql://k0user:k0pass@pgbouncer:6432/k0_kernel")
    output = os.getenv("REPORT_OUTPUT", "/app/data/memory_layers_report.md")

    await generate_memory_report(dsn, output)


if __name__ == "__main__":
    asyncio.run(main())
