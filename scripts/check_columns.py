import asyncio

import asyncpg


async def check_columns():
    dsn = 'postgresql://k0user:changeme@localhost:5432/k0_kernel'
    conn = await asyncpg.connect(dsn)

    # Get column names
    columns = await conn.fetch('''
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'st_hipp_events'
        ORDER BY ordinal_position
    ''')

    print('st_hipp_events columns:')
    for col in columns:
        print(f'  {col["column_name"]}')

    await conn.close()

if __name__ == "__main__":
    asyncio.run(check_columns())if __name__ == "__main__":
    asyncio.run(check_columns())
