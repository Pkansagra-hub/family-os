import asyncio
import asyncpg

async def check():
    conn = await asyncpg.connect('postgresql://k0:k0pass@localhost:6432/k0_kernel', statement_cache_size=0)
    for table in ['st_epi', 'st_kg_dom']:
        cols = await conn.fetch(
            'SELECT column_name FROM information_schema.columns WHERE table_name = $1 ORDER BY ordinal_position',
            table
        )
        print(f'{table}: {[c[\"column_name\"] for c in cols]}')
    await conn.close()

asyncio.run(check())
