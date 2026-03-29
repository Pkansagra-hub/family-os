"""Quick diagnostic: what does asyncpg return for pgvector VECTOR(768)?"""

import asyncio

import asyncpg


async def main():
    conn = await asyncpg.connect("postgresql://k0user:k0pass@pgbouncer:6432/k0_kernel")
    row = await conn.fetchrow(
        "SELECT vector, vector_dim, pg_typeof(vector)::text as vtype FROM st_vec LIMIT 1"
    )
    v = row["vector"]
    print(f"Python type: {type(v).__name__}")
    print(f"pg_typeof: {row['vtype']}")
    print(f"repr[:300]: {repr(v)[:300]}")
    if hasattr(v, "__len__"):
        print(f"len: {len(v)}")
    if isinstance(v, str):
        print("IT IS A STRING - struct.unpack will fail!")
    elif isinstance(v, (bytes, bytearray)):
        print(f"It is bytes, len={len(v)}")
    elif isinstance(v, list):
        print(f"It is a list of {type(v[0]).__name__}, len={len(v)}")
    else:
        # Try to iterate
        try:
            items = list(v)
            print(f"Iterable with {len(items)} items, first type: {type(items[0]).__name__}")
        except Exception as e:
            print(f"Not iterable: {e}")
    await conn.close()


asyncio.run(main())
asyncio.run(main())
