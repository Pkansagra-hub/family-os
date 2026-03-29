"""Check column population rates for st_hipp_events (tenant-test events)."""

import asyncio

import asyncpg

COLUMNS = [
    "event_id",
    "wal_pos",
    "cognitive_trace_id",
    "tenant_id",
    "space_id",
    "effective_space_id",
    "topic",
    "uow_id",
    "schema_version",
    "envelope_sha256",
    "sig_alg",
    "sig_kid",
    "idem_key",
    "ingested_at",
    "clock_skew_ms",
    "policy_decision",
    "policy_band",
    "policy_version",
    "obligations_json",
    "visible_to_json",
    "visibility_scope",
    "owner_id",
    "co_owners_json",
    "retention_policy_id",
    "retention_bucket",
    "actor_id",
    "actor_role",
    "device_id",
    "device_kind",
    "device_os",
    "ingress_channel",
    "event_time_utc",
    "write_time_utc",
    "write_lag_ms",
    "local_date",
    "local_time",
    "day_of_week",
    "is_weekend",
    "time_of_day_bucket",
    "circadian_slot",
    "is_backdated",
    "created_at",
    "location_name",
    "location_type",
    "geohash_6",
    "geo_precision_external",
    "geo_masking_reason",
    "participants_json",
    "num_participants",
    "has_partner_present",
    "has_parent_present",
    "is_solo_event",
    "participant_roles_json",
    "social_context",
    "social_intimacy",
    "text",
    "text_normalized",
    "char_count",
    "token_count",
    "language",
    "activity_type",
    "activity_category",
    "is_meal",
    "is_outing",
    "ingress_source",
    "simhash_hex",
    "minhash32",
    "novelty_score",
    "near_duplicates_json",
    "is_near_duplicate",
    "episode_cluster_id",
    "cluster_confidence",
    "clustering_version",
    "embedding_id",
    "embedding_status",
    "entities_json",
    "kg_triples_json",
    "sentiment_score",
    "sentiment_label",
    "dominant_emotions_json",
    "affect_valence",
    "affect_arousal",
    "affect_band",
    "salience_score",
    "salience_reasons_json",
    "salience_band",
    "hippocampus_api_version",
    "space_resolver_version",
    "schema_uri",
    "updated_at",
    "consolidation_status",
    "consolidation_cycle_id",
    "consolidated_at",
    "reconciliation_decision",
    "truth_match_id",
    "truth_match_similarity",
    "ner_entities_json",
    "temporal_json",
    "intent_category",
    "ingress_category",
    "ultrabert_version",
    "merge_cascade_id",
    "archival_status",
    "reconciliation_action",
    "best_match_id",
    "best_match_layer",
    "similarity_score",
    "confidence",
    "reconciliation_reason",
    "consolidated_at_ms",
    "extracted_relations_json",
    "safety_familyos_band",
    "safety_familyos_subcategory",
    "effective_safety_band",
    "nli_label",
    "nli_confidence",
    "sentiment_confidence",
    "activity_type_ultrabert",
    "activity_type_confidence",
    "intent_ultrabert",
    "intent_confidence",
    "narrative_thread_id",
    "narrative_arc_position",
    "narrative_is_goal_event",
    "affect_dominance",
    "entity_salience_json",
    "temporal_mentioned_time",
    "temporal_resolved_epoch_ms",
    "temporal_orientation",
    "intent_type",
    "goal_context",
    "source_type",
    "novelty",
    "elaboration_depth",
    "identity_domains_json",
    "participant_relationships_json",
    "k1_signal_version",
    "surprise_level",
    "identity_relevance",
    "source_reliability",
    "memory_tier",
    "temporal_anchor_json",
]


async def main():
    conn = await asyncpg.connect(
        "postgresql://k0user:k0pass@pgbouncer:6432/k0_kernel",
        statement_cache_size=0,
    )
    total = await conn.fetchval("SELECT COUNT(*) FROM st_hipp_events WHERE tenant_id='tenant-test'")
    print(f"Total events: {total}\n")

    # Build a single query that counts non-null AND non-empty for each column
    parts = []
    for col in COLUMNS:
        parts.append(
            f"SUM(CASE WHEN {col} IS NOT NULL AND {col}::text != '' "
            f"AND {col}::text != '[]' AND {col}::text != '{{}}' "
            f"AND {col}::text != '0' AND {col}::text != '0.0' "
            f"AND {col}::text != 'false' "
            f"THEN 1 ELSE 0 END) AS {col}"
        )
    query = f"SELECT {', '.join(parts)} FROM st_hipp_events WHERE tenant_id='tenant-test'"
    row = await conn.fetchrow(query)

    populated = []
    empty = []
    defaultish = []  # columns where value exists but is a default/zero

    for col in COLUMNS:
        count = row[col]
        if count == total:
            populated.append((col, count))
        elif count == 0:
            empty.append((col, count))
        else:
            defaultish.append((col, count))

    print(f"=== FULLY POPULATED ({len(populated)}/{len(COLUMNS)}) ===")
    for col, cnt in populated:
        print(f"  {col}: {cnt}/{total}")

    print(f"\n=== PARTIALLY POPULATED ({len(defaultish)}/{len(COLUMNS)}) ===")
    for col, cnt in sorted(defaultish, key=lambda x: x[1], reverse=True):
        pct = cnt * 100 // total
        print(f"  {col}: {cnt}/{total} ({pct}%)")

    print(f"\n=== COMPLETELY EMPTY/DEFAULT ({len(empty)}/{len(COLUMNS)}) ===")
    for col, _ in empty:
        print(f"  {col}: 0/{total}")

    # Also get a sample of actual values for key MW v2 columns
    print("\n=== SAMPLE VALUES (1 row, MW v2 signal columns) ===")
    mw_cols = [
        "narrative_thread_id",
        "narrative_arc_position",
        "narrative_is_goal_event",
        "intent_type",
        "goal_context",
        "source_type",
        "novelty",
        "elaboration_depth",
        "identity_domains_json",
        "participant_relationships_json",
        "k1_signal_version",
        "affect_dominance",
        "temporal_mentioned_time",
        "temporal_resolved_epoch_ms",
        "temporal_orientation",
        "entity_salience_json",
        "surprise_level",
        "identity_relevance",
        "source_reliability",
        "memory_tier",
        "temporal_anchor_json",
        "activity_type_ultrabert",
        "activity_type_confidence",
        "intent_ultrabert",
        "intent_confidence",
        "location_name",
        "location_type",
        "geohash_6",
        "participants_json",
        "social_context",
        "social_intimacy",
        "affect_valence",
        "affect_arousal",
        "sentiment_score",
        "sentiment_label",
        "salience_score",
        "salience_band",
        "novelty_score",
    ]
    sample = await conn.fetchrow(
        f"SELECT {', '.join(mw_cols)} FROM st_hipp_events WHERE tenant_id='tenant-test' LIMIT 1"
    )
    for col in mw_cols:
        val = sample[col]
        val_str = str(val)[:80] if val is not None else "NULL"
        print(f"  {col}: {val_str}")

    await conn.close()


asyncio.run(main())
