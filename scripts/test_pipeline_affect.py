import asyncio

from k0.modules.affect.analyze import run


async def test_pipeline_module():
    # Simulate a cognitive.memory.write.committed.v1 event
    test_event = {
        'text': 'Spent the first hour addressing the failed tests in my K1 branch. Annoying.',
        'event_type': 'cognitive.memory.write.committed.v1'
    }

    # Mock context
    class MockContext:
        def __init__(self):
            self.logger = type('MockLogger', (), {
                'debug': lambda *args, **kwargs: print(f'DEBUG: {args[0]}'),
                'warning': lambda *args, **kwargs: print(f'WARNING: {args[0]}'),
                'info': lambda *args, **kwargs: print(f'INFO: {args[0]}'),
            })()

    context = MockContext()

    print('Testing affect.analyze module with pipeline interface...')
    result = await run(test_event, context)

    print(f'Final valence: {result.get("affect_valence")}')
    print(f'Final arousal: {result.get("affect_arousal")}')
    print(f'Final emotions: {result.get("dominant_emotions")}')
    print(f'Final band: {result.get("affect_band")}')
    print(f'Model version: {result.get("model_version")}')
    print(f'Tier: {result.get("affect_tier")}')

if __name__ == "__main__":
    asyncio.run(test_pipeline_module())if __name__ == "__main__":
    asyncio.run(test_pipeline_module())
