import asyncio
import asyncpg

async def check():
    conn = await asyncpg.connect('postgresql://k0:k0pass@localhost:6432/k0_kernel')
    result = await conn.fetch('''
        SELECT 'st_epi' as layer, COUNT(*) as total, COUNT(embedding_vector) as with_embedding FROM st_epi
        UNION ALL SELECT 'st_sem', COUNT(*) , COUNT(embedding_vector) FROM st_sem
        UNION ALL SELECT 'st_kg_dom', COUNT(*), COUNT(embedding_vector) FROM st_kg_dom
        UNION ALL SELECT 'st_social', COUNT(*), COUNT(embedding_vector) FROM st_social
        UNION ALL SELECT 'st_procedural', COUNT(*), COUNT(embedding_vector) FROM st_procedural
        UNION ALL SELECT 'st_prospective', COUNT(*), COUNT(embedding_vector) FROM st_prospective
        ORDER BY layer
    ''')
    for row in result:
        layer, total, with_emb = row['layer'], row['total'], row['with_embedding']
        pct = (with_emb / total * 100) if total > 0 else 0
        print(f'{layer:15} | {total:5} | {with_emb:5} | {pct:6.1f}%')
    await conn.close()

asyncio.run(check())
