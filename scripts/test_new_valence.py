import asyncio

from k0.modules.affect.analyze import ultrabert_classify


async def test_new_valence_calculation():
    test_texts = [
        'Looking back, today was a mixed bag. The K0 bug was frustrating, but I am glad I figured it out.',
        'Watched a movie with Panda. It was a nice way to unwind after a busy day.',
        'Spent the first hour addressing the failed tests in my K1 branch. Annoying.',
        'Feeling grateful for my family today. They always support me.',
        'Really anxious about the presentation tomorrow. What if I mess up?',
        'Read a book before bed. Trying to wind down.',
        'Got stuck on a tricky part of the K1 feature. Spent a couple of hours debugging and finally found the issue.',
        'Panda called, and we talked about our day. She is feeling overwhelmed with her project.'
    ]

    print("Testing new psychologically-grounded valence/arousal calculation:")
    print("=" * 80)

    for text in test_texts:
        print(f"\nText: {text[:80]}{'...' if len(text) > 80 else ''}")

        result = ultrabert_classify(text)
        if result:
            print(f"  Emotions: {result.dominant_emotions}")
            print(".3f")
            print(".3f")
            print(f"  Band: {result.affect_band}")
        else:
            print("  ❌ UltraBERT failed")

if __name__ == "__main__":
    asyncio.run(test_new_valence_calculation())if __name__ == "__main__":
    asyncio.run(test_new_valence_calculation())
