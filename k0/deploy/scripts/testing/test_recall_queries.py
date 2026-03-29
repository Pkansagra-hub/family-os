import asyncio
import asyncpg
import numpy as np

async def test_queries():
    conn = await asyncpg.connect(
        host='localhost', port=6432, user='k0', password='k0pass',
        database='k0_kernel', statement_cache_size=0
    )
    
    from k0.runtime.ultrabert_adapter import get_embedding
    from k0.modules.embedding.union_index_manager import get_manager
    
    manager = get_manager()
    searcher = manager.get_searcher()
    
    if not searcher:
        print('No searcher available - run with --build-index first')
        await conn.close()
        return
    
    queries = [
        'Where is Emma?',
        'meetings at work',
        'health checkup doctor',
    ]
    
    for query in queries:
        emb = get_embedding(query)
        vec = np.array(emb, dtype=np.float32)
        results = searcher.search(vec, k=3)
        
        print(f'Query: {query}')
        for i, r in enumerate(results):
            print(f'  [{i+1}] {r.layer:15} score={r.score:.4f}')
        print()
    
    await conn.close()

asyncio.run(test_queries())
