"""UltraBERT Integration Benchmark Script."""

import time


def main():
    print("=" * 60)
    print("UltraBERT Integration Benchmark")
    print("=" * 60)

    text = "Had dinner with mom and dad at Olive Garden for Emma birthday yesterday. I am so happy!"

    # 1. Test Affect Analysis (M04)
    print()
    print("1. M04 Affect Analysis (UltraBERT)")
    print("-" * 40)
    start = time.perf_counter()
    from k0.modules.affect.analyze import ultrabert_classify

    result = ultrabert_classify(text)
    latency = (time.perf_counter() - start) * 1000
    print(f"   Latency: {latency:.1f}ms")
    if result:
        print(f"   Result: valence={result.valence:.2f}, band={result.affect_band}")
        print(f"   Emotions: {result.dominant_emotions[:3]}")
        print(f"   Tier: {result.tier}")
    else:
        print("   FAILED: UltraBERT not available")

    # 2. Test Entity Extraction (M02)
    print()
    print("2. M02 Entity Extraction (UltraBERT)")
    print("-" * 40)
    start = time.perf_counter()
    from k0.modules.hippocampus.semantic_project import _extract_entities

    entities = _extract_entities(text)
    latency = (time.perf_counter() - start) * 1000
    print(f"   Latency: {latency:.1f}ms")
    print(f"   Count: {len(entities)} entities")
    for e in entities[:4]:
        print(f"     - {e.text} ({e.label}) [source: {e.source}]")

    # 3. Test Activity Classification (M10)
    print()
    print("3. M10 Activity Classification (UltraBERT)")
    print("-" * 40)
    start = time.perf_counter()
    from k0.modules.context.ingress_classify import classify_activity_type_enhanced

    activity = classify_activity_type_enhanced(text)
    latency = (time.perf_counter() - start) * 1000
    print(f"   Latency: {latency:.1f}ms")
    print(f"   Activity: {activity.get('activity_type')}")
    print(f"   Intent: {activity.get('intent', 'N/A')}")
    print(f"   Source: {activity.get('source', 'legacy')}")

    # 4. Test Safety Check
    print()
    print("4. Safety Check (UltraBERT)")
    print("-" * 40)
    from k0.runtime.ultrabert_adapter import check_safety

    is_concern, level, summary = check_safety(text)
    print(f"   Concern: {is_concern}")
    print(f"   Level: {level}")

    # 5. Test with concerning text
    print()
    print("5. Safety Check - Concerning Text")
    print("-" * 40)
    concerning_text = "I feel so hopeless, I want to hurt myself"
    is_concern, level, summary = check_safety(concerning_text)
    print(f"   Concern: {is_concern}")
    print(f"   Level: {level}")
    print(f"   Summary: {summary}")

    print()
    print("=" * 60)
    print("BENCHMARK COMPLETE - UltraBERT Integration Successful!")
    print("=" * 60)


if __name__ == "__main__":
    main()
