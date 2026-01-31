import asyncio
import json

from k0.runtime.ultrabert_adapter import analyze_affect, is_ultrabert_available


async def test_ultrabert_on_timeline():
    print("Checking UltraBERT availability...")
    if not is_ultrabert_available():
        print("❌ UltraBERT is NOT available!")
        return

    print("✅ UltraBERT is available")

    # Load timeline events
    with open('d:\\familyos\\k0\\deploy\\scripts\\events\\timeline_3days_v7.jsonl', 'r') as f:
        events = [json.loads(line) for line in f]

    print(f"\nLoaded {len(events)} events from timeline")
    print("\n" + "="*80)

    # Test on first 10 events
    for i, event in enumerate(events[:10]):
        text = event['text']
        print(f"\nEvent {i+1}: {text[:100]}{'...' if len(text) > 100 else ''}")

        try:
            result = analyze_affect(text)
            if result:
                print(f"  Sentiment: {result.sentiment}")
                print(f"  Emotions: {result.dominant_emotions}")
                print(f"  Affect Band: {result.affect_band}")
                print(f"  Confidence: {result.confidence}")
                print(f"  Reasons: {result.band_reasons}")
            else:
                print("  ❌ No result from UltraBERT")
        except Exception as e:
            print(f"  ❌ Error: {e}")

        print("-" * 40)

if __name__ == "__main__":
    asyncio.run(test_ultrabert_on_timeline())if __name__ == "__main__":
    asyncio.run(test_ultrabert_on_timeline())
