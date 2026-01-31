import asyncio

from k0.runtime.ultrabert_adapter import analyze_affect


async def test_specific_texts():
    test_texts = [
        'Looking back, today was a mixed bag. The K0 bug was frustrating, but I am glad I figured it out.',
        'Read a book before bed. Trying to wind down.',
        'Watched a movie with Panda. It was a nice way to unwind after a busy day.',
        'Got stuck on a tricky part of the K1 feature. Spent a couple of hours debugging and finally found the issue.',
        'Panda called, and we talked about our day. She is feeling overwhelmed with her project.'
    ]

    for text in test_texts:
        print(f'Text: {text[:80]}...')
        result = analyze_affect(text)
        if result:
            sentiment_to_valence = {
                "very_positive": 0.9,
                "positive": 0.7,
                "neutral": 0.5,
                "negative": 0.3,
                "very_negative": 0.1,
            }
            valence = sentiment_to_valence.get(result.sentiment, 0.5)
            print(f'  Sentiment: {result.sentiment}')
            print(f'  Emotions: {result.dominant_emotions}')
            print(f'  Valence (from sentiment): {valence}')
        else:
            print('  ❌ No result')
        print()

if __name__ == "__main__":
    asyncio.run(test_specific_texts())if __name__ == "__main__":
    asyncio.run(test_specific_texts())
