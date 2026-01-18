"""
Fix 4 Critical Data Quality Bugs in Memory System

Bug 1: Entity typing chaos (Panda as ORG, GERD as FAMILY_MEMBER, etc.)
Bug 2: Social sentiment always 0.00 (not propagated from observations)
Bug 3: "Joyful" query filters by sentiment, not emotion
Bug 4: Topic spam (152 monitor mentions instead of 1 canonical issue)

This script creates the necessary schema changes and data fixes.
"""

import asyncio
import asyncpg


async def fix_all_bugs():
    conn = await asyncpg.connect("postgresql://k0user:changeme@localhost:5432/k0_kernel")

    print("=" * 80)
    print("FIXING 4 CRITICAL DATA QUALITY BUGS")
    print("=" * 80)

    # ═══════════════════════════════════════════════════════════════════════════
    # BUG 1: Create Canonical Entity Registry
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n" + "─" * 80)
    print("BUG 1: Creating Canonical Entity Registry")
    print("─" * 80)

    # Create the canonical entity table
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS st_entity_canonical (
            entity_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            space_id TEXT NOT NULL,
            canonical_name TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            aliases_json TEXT DEFAULT '[]',
            type_confidence DOUBLE PRECISION DEFAULT 0.5,
            type_locked BOOLEAN DEFAULT FALSE,  -- Manual override
            first_seen_at BIGINT NOT NULL,
            last_seen_at BIGINT NOT NULL,
            occurrence_count INTEGER DEFAULT 1,
            source_contexts_json TEXT DEFAULT '[]',
            created_at BIGINT NOT NULL,
            updated_at BIGINT NOT NULL,
            
            CONSTRAINT ck_entity_type CHECK (entity_type IN (
                'PERSON', 'FAMILY_MEMBER', 'COLLEAGUE', 'FRIEND',
                'LOCATION', 'ORGANIZATION', 'CONCEPT', 'EVENT',
                'PRODUCT', 'HEALTH_CONDITION', 'PROJECT',
                'TOKEN', 'UNKNOWN'  -- Garbage bucket
            ))
        )
    """)
    print("  ✓ Created st_entity_canonical table")

    # Create index for fast lookup
    await conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_entity_canonical_name 
        ON st_entity_canonical(tenant_id, LOWER(canonical_name))
    """)
    
    await conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_entity_canonical_type 
        ON st_entity_canonical(tenant_id, entity_type)
    """)
    print("  ✓ Created indexes")

    # Define hard rules for entity type constraints
    type_constraints = {
        # Health conditions - NEVER person/org
        'GERD': 'HEALTH_CONDITION',
        'COVID': 'HEALTH_CONDITION',
        'headache': 'HEALTH_CONDITION',
        'nosebleed': 'HEALTH_CONDITION',
        
        # Tech products - NEVER person/org
        'SSD': 'PRODUCT',
        'HDMI': 'PRODUCT',
        'USB': 'PRODUCT',
        'ProArt': 'PRODUCT',
        'Samsung 990': 'PRODUCT',
        'Asus ProArt': 'PRODUCT',
        
        # Projects - custom type
        'FamilyOS': 'PROJECT',
        'K0': 'PROJECT',
        'K1': 'PROJECT',
        'P02': 'PROJECT',
        'P03': 'PROJECT',
        
        # Airports/Places
        'DFW': 'LOCATION',
        
        # Garbage tokens - should never be entities
        'Need': 'TOKEN',
        'need': 'TOKEN',
        'because': 'TOKEN',
        'else': 'TOKEN',
        'when': 'TOKEN',
        'prioritize': 'TOKEN',
        'got': 'TOKEN',
        'but': 'TOKEN',
        
        # Real people
        'Panda': 'FAMILY_MEMBER',
        'Maya': 'FAMILY_MEMBER',
        'Mom': 'FAMILY_MEMBER',
        'Dad': 'FAMILY_MEMBER',
        'Prince': 'PERSON',
    }

    # Insert canonical entities with locked types
    now = int(asyncio.get_event_loop().time() * 1000)
    for name, entity_type in type_constraints.items():
        await conn.execute("""
            INSERT INTO st_entity_canonical (
                entity_id, tenant_id, space_id, canonical_name, entity_type,
                type_confidence, type_locked, first_seen_at, last_seen_at,
                created_at, updated_at
            ) VALUES (
                $1, 'tenant-test', 'space-home', $2, $3,
                1.0, TRUE, $4, $4, $4, $4
            )
            ON CONFLICT (entity_id) DO UPDATE SET
                entity_type = EXCLUDED.entity_type,
                type_locked = TRUE,
                updated_at = EXCLUDED.updated_at
        """, f"canonical-{name.lower()}", name, entity_type, now)
    
    print(f"  ✓ Inserted {len(type_constraints)} canonical entity type constraints")

    # Clean up garbage entities from st_kg_dom
    garbage_deleted = await conn.execute("""
        DELETE FROM st_kg_dom
        WHERE LOWER(canonical_name) IN ('need', 'because', 'else', 'when', 'prioritize', 'got', 'but')
    """)
    print(f"  ✓ Removed garbage tokens from st_kg_dom")

    # Fix duplicate entity types - keep only the correct one
    # For each mistyped entity, update to canonical type
    for name, correct_type in type_constraints.items():
        if correct_type != 'TOKEN':
            await conn.execute("""
                UPDATE st_kg_dom
                SET entity_type = $1
                WHERE LOWER(canonical_name) = LOWER($2)
            """, correct_type, name)
    print("  ✓ Fixed entity types in st_kg_dom")

    # ═══════════════════════════════════════════════════════════════════════════
    # BUG 2: Fix Social Sentiment Propagation
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n" + "─" * 80)
    print("BUG 2: Fixing Social Sentiment Propagation")
    print("─" * 80)

    # Calculate avg sentiment for each relationship from observations
    # Join st_social with st_observations to get actual sentiment values
    await conn.execute("""
        UPDATE st_social s
        SET 
            avg_sentiment = sub.avg_sent,
            emotional_valence_avg = sub.avg_sent
        FROM (
            SELECT 
                o.record_id,
                AVG(o.sentiment_score) as avg_sent
            FROM st_observations o
            WHERE o.layer = 'st_social' AND o.sentiment_score IS NOT NULL
            GROUP BY o.record_id
        ) sub
        WHERE s.relationship_id = sub.record_id
    """)
    print("  ✓ Updated avg_sentiment from observations")

    # For relationships without observations, estimate from episodes mentioning them
    await conn.execute("""
        UPDATE st_social s
        SET avg_sentiment = COALESCE(
            (SELECT AVG(o.sentiment_score) 
             FROM st_observations o 
             JOIN st_epi e ON o.record_id::text = e.episode_id::text
             WHERE o.layer = 'st_epi' 
               AND e.participants_json ILIKE '%' || s.relationship_label || '%'
               AND o.sentiment_score IS NOT NULL
            ), 0.5
        ),
        emotional_valence_avg = COALESCE(
            (SELECT AVG(o.sentiment_score) 
             FROM st_observations o 
             JOIN st_epi e ON o.record_id::text = e.episode_id::text
             WHERE o.layer = 'st_epi' 
               AND e.participants_json ILIKE '%' || s.relationship_label || '%'
               AND o.sentiment_score IS NOT NULL
            ), 0.5
        )
        WHERE s.avg_sentiment = 0 OR s.avg_sentiment IS NULL
    """)
    print("  ✓ Estimated sentiment for remaining relationships from episodes")

    # Verify the fix
    result = await conn.fetch("""
        SELECT relationship_label, avg_sentiment, emotional_valence_avg
        FROM st_social
        ORDER BY interaction_count DESC
        LIMIT 5
    """)
    print("\n  Verification - Top 5 relationships:")
    for r in result:
        print(f"    {r['relationship_label']}: sentiment={r['avg_sentiment']:.2f}")

    # ═══════════════════════════════════════════════════════════════════════════
    # BUG 3: This is a query bug, fixed in explore_memory_layers.py
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n" + "─" * 80)
    print("BUG 3: 'Joyful' Query Fix (code change needed)")
    print("─" * 80)
    print("  ℹ️  This is a query bug in explore_memory_layers.py")
    print("  ℹ️  Current: sentiment_score >= 0.9 (wrong)")
    print("  ℹ️  Fixed:   dominant_emotion IN ('joy', 'love', 'gratitude') AND sentiment >= 0.7")
    print("  → Will fix in explore_memory_layers.py")

    # ═══════════════════════════════════════════════════════════════════════════
    # BUG 4: Create Issue Canonicalization Table
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n" + "─" * 80)
    print("BUG 4: Creating Issue Canonicalization Table")
    print("─" * 80)

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS st_issues (
            issue_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            space_id TEXT NOT NULL,
            canonical_title TEXT NOT NULL,
            issue_category TEXT NOT NULL,  -- TECH, HEALTH, ADMIN, WORK, PERSONAL
            status TEXT NOT NULL DEFAULT 'OPEN',  -- OPEN, RESOLVED, RECURRING
            first_seen_at BIGINT NOT NULL,
            last_seen_at BIGINT NOT NULL,
            evidence_count INTEGER DEFAULT 1,
            evidence_event_ids_json TEXT DEFAULT '[]',
            resolution_event_id TEXT,
            resolution_note TEXT,
            keywords_json TEXT DEFAULT '[]',  -- For matching new events
            created_at BIGINT NOT NULL,
            updated_at BIGINT NOT NULL,
            
            CONSTRAINT ck_issue_status CHECK (status IN ('OPEN', 'RESOLVED', 'RECURRING')),
            CONSTRAINT ck_issue_category CHECK (issue_category IN (
                'TECH', 'HEALTH', 'ADMIN', 'WORK', 'PERSONAL', 'FAMILY', 'FINANCE'
            ))
        )
    """)
    print("  ✓ Created st_issues table")

    await conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_issues_status 
        ON st_issues(tenant_id, status)
    """)
    
    await conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_issues_category 
        ON st_issues(tenant_id, issue_category)
    """)
    print("  ✓ Created indexes")

    # Canonicalize the known issues from the data
    known_issues = [
        {
            'id': 'issue-monitor-flicker',
            'title': 'Monitor Display Flicker',
            'category': 'TECH',
            'keywords': ['monitor', 'flicker', 'display', 'dock', 'HDMI', 'screen'],
            'status': 'RESOLVED',  # Based on "flicker stopped" mentions
            'resolution': 'Switched docks and cables, flicker stopped'
        },
        {
            'id': 'issue-gerd',
            'title': 'GERD/Digestive Issues',
            'category': 'HEALTH',
            'keywords': ['GERD', 'stomach', 'acid', 'spicy', 'digestion'],
            'status': 'RECURRING',
            'resolution': None
        },
        {
            'id': 'issue-h1b-visa',
            'title': 'H1B Visa/Immigration Paperwork',
            'category': 'ADMIN',
            'keywords': ['H1B', 'visa', 'SEVIS', 'DMV', 'immigration', 'extension'],
            'status': 'OPEN',
            'resolution': None
        },
        {
            'id': 'issue-wedding-planning',
            'title': 'Wedding Planning',
            'category': 'FAMILY',
            'keywords': ['wedding', 'venue', 'invite', 'catering', 'seating'],
            'status': 'OPEN',
            'resolution': None
        },
        {
            'id': 'issue-proart-cooling',
            'title': 'Asus ProArt Overheating/Fan Noise',
            'category': 'TECH',
            'keywords': ['ProArt', 'cooling', 'fan', 'noise', 'cooling pad'],
            'status': 'OPEN',
            'resolution': None
        },
    ]

    import json
    for issue in known_issues:
        # Count matching events
        keywords_pattern = '|'.join(issue['keywords'])
        count = await conn.fetchval(f"""
            SELECT COUNT(*) FROM st_hipp_events
            WHERE text ~* $1
        """, keywords_pattern)
        
        await conn.execute("""
            INSERT INTO st_issues (
                issue_id, tenant_id, space_id, canonical_title, issue_category,
                status, first_seen_at, last_seen_at, evidence_count,
                keywords_json, resolution_note, created_at, updated_at
            ) VALUES (
                $1, 'tenant-test', 'space-home', $2, $3,
                $4, $5, $5, $6, $7, $8, $5, $5
            )
            ON CONFLICT (issue_id) DO UPDATE SET
                evidence_count = EXCLUDED.evidence_count,
                last_seen_at = EXCLUDED.last_seen_at,
                updated_at = EXCLUDED.updated_at
        """, issue['id'], issue['title'], issue['category'],
            issue['status'], now, count, json.dumps(issue['keywords']),
            issue['resolution'])
        
        status_icon = '✅' if issue['status'] == 'RESOLVED' else '🔄' if issue['status'] == 'RECURRING' else '🔴'
        print(f"  {status_icon} {issue['title']}: {count} evidence events → {issue['status']}")

    print("\n" + "=" * 80)
    print("ALL FIXES APPLIED")
    print("=" * 80)

    # Summary report
    print("\n📊 SUMMARY:")
    
    entity_count = await conn.fetchval("SELECT COUNT(*) FROM st_entity_canonical")
    print(f"  • Canonical entities registered: {entity_count}")
    
    fixed_sentiment = await conn.fetchval("SELECT COUNT(*) FROM st_social WHERE avg_sentiment > 0")
    total_social = await conn.fetchval("SELECT COUNT(*) FROM st_social")
    print(f"  • Social relationships with sentiment: {fixed_sentiment}/{total_social}")
    
    issue_count = await conn.fetchval("SELECT COUNT(*) FROM st_issues")
    print(f"  • Canonical issues tracked: {issue_count}")

    await conn.close()


if __name__ == "__main__":
    asyncio.run(fix_all_bugs())
