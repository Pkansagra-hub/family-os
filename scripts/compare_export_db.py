import asyncio

import asyncpg


async def compare_export_vs_db():
    dsn = 'postgresql://k0user:changeme@localhost:5432/k0_kernel'
    conn = await asyncpg.connect(dsn)

    # Check if the events from the export exist in DB
    export_events = []
    with open('data/hipp_events_export.txt', 'r') as f:
        lines = f.readlines()[2:]  # Skip header lines
        for line in lines:
            if '|' in line:
                parts = line.split('|')
                if len(parts) >= 3:
                    event_id = parts[0].strip()
                    emotions = parts[2].strip()
                    if event_id and emotions and emotions != 'dominant_emotions_json':
                        export_events.append((event_id, emotions))

    print(f'Found {len(export_events)} events in export')

    # Check first few events in DB
    db_events = await conn.fetch('''
        SELECT event_id, dominant_emotions_json, affect_valence, affect_arousal
        FROM st_hipp_events
        ORDER BY created_at DESC
        LIMIT 10
    ''')

    print(f'Latest {len(db_events)} events in DB:')
    for row in db_events:
        print(f'  {row["event_id"][:8]}...: emotions={row["dominant_emotions_json"]}, valence={row["affect_valence"]}, arousal={row["affect_arousal"]}')

    # Check if any export events exist in DB
    if export_events:
        sample_ids = [eid for eid, _ in export_events[:5]]
        placeholders = ','.join(['$'+str(i+1) for i in range(len(sample_ids))])
        query = f'SELECT event_id, dominant_emotions_json FROM st_hipp_events WHERE event_id IN ({placeholders})'

        existing = await conn.fetch(query, *sample_ids)
        print(f'\nChecking if export events exist in DB: {len(existing)} found')
        for row in existing:
            print(f'  {row["event_id"][:8]}...: {row["dominant_emotions_json"]}')

    await conn.close()

if __name__ == "__main__":
    asyncio.run(compare_export_vs_db())if __name__ == "__main__":
    asyncio.run(compare_export_vs_db())
