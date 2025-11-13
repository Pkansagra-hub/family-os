# K0 Affect Module

On-device affect sensing and policy engine for FamilyOS.

## Overview

The Affect Module implements a complete affect sensing pipeline as specified in ADR-0012 (k003a-k003i):

1. **Tier-0/Tier-1 Classifiers**: Lexicon-based (<2ms) and ensemble (<60ms) affect classification
2. **Multi-Modal Fusion**: Confidence-weighted fusion of text and behavioral signals
3. **EMA Smoothing**: Dual exponential moving average (fast α=0.5, slow α=0.1)
4. **Policy Banding**: 27+ hierarchical rules mapping to GREEN/AMBER/RED/BLACK bands
5. **Social Cognition**: Relationship-aware modifiers (parent-child, partner, sibling)
6. **Household Dynamics**: Conflict detection, family moments, emotional contagion
7. **Counterfactual Safety**: Proactive "what if?" simulation before actions

## Architecture

```
Event → Tier-0 (2ms) → Tier-1 (60ms) → Fusion → EMA → Policy → Storage
                                          ↓         ↓      ↓
                                       Social  Household  K1
                                      Context  Dynamics  Bridge
```

## Performance Budgets

- **Tier-0**: <2ms P95
- **Tier-1**: <60ms P95 (optional)
- **Policy Banding**: <5ms P95
- **Total**: <70ms P95 (with Tier-1)

## Module Structure

```
affect/
├── classifiers/          # Tier-0 and Tier-1 classifiers
│   ├── tier0/           # Lexicon-based (<2ms)
│   └── tier1/           # VADER + TextBlob + ONNX (<60ms)
├── fusion/              # Multi-modal fusion and EMA
├── policy/              # Policy band rules (27+ rules)
├── social/              # Relationship graph and lifecycle context
├── household/           # Household dynamics (conflicts, family moments)
├── counterfactual/      # Proactive safety simulation
├── storage/             # st_hipp_store integration + EMA cache
├── bridge/              # K1 integration (AffectSummary)
├── models/              # Data structures
└── resources/           # Lexicons and ONNX models
```

## Quick Start

```python
from k0.modules.affect import AffectService

# Initialize service
affect_service = AffectService()

# Classify text
affect = affect_service.classify_text(
    text="I'm feeling stressed",
    context={"person_id": "user123", "space_id": "family"}
)

print(f"Valence: {affect.valence:.2f}")
print(f"Arousal: {affect.arousal:.2f}")
print(f"Band: {affect.band}")
print(f"Reasons: {affect.band_reasons}")

# Get EMA state
state = affect_service.get_ema_state("user123", "family")
print(f"Fast EMA: v={state.v_fast:.2f}, a={state.a_fast:.2f}")

# Get household state
household = affect_service.get_household_state("family")
print(f"Conflict active: {household.conflict_active}")
print(f"Family moment: {household.family_moment_active}")

# Get K1 summary
summary = affect_service.get_affect_summary("user123", "family")
print(f"Mood: {summary.mood_label}")
print(f"Trend: {summary.trend}")
```

## Related ADRs

- **k003a**: Affect Contracts & Storage Mapping
- **k003b**: Tier-0 Realtime Classifier
- **k003c**: Tier-1 Enhanced Classifier & ONNX
- **k003d**: Multi-Modal Fusion, EMA & Calibration
- **k003e**: Policy Band Rules & P18 Integration
- **k003f**: Affect → K1 Planner & Concierge Bridge
- **k003g**: Household-Level Affect Dynamics
- **k003h**: Social Cognition & Relationship Context Modifiers
- **k003i**: Counterfactual Emotional Safety & Sharing

## Implementation Status

- [x] Directory structure created
- [ ] Tier-0 classifier (lexicon + behavioral arousal)
- [ ] Tier-1 classifier (VADER + TextBlob + ONNX)
- [ ] Fusion engine (confidence-weighted + EMA)
- [ ] Policy engine (27+ hierarchical rules)
- [ ] Social context engine (relationship graph + lifecycle)
- [ ] Household dynamics (conflict + family moments + contagion)
- [ ] Counterfactual simulator (safety checks)
- [ ] Storage integration (st_hipp_store + EMA cache)
- [ ] K1 bridge (AffectSummary + behavior modes)
- [ ] Unit tests
- [ ] Integration tests
- [ ] Performance benchmarks

## Next Steps

1. **Implement Tier-0 Classifier** (k003b)
   - Load lexicon (~2000 words)
   - Tokenization and normalization
   - Negation handling
   - Behavioral arousal detection
   - Target: <2ms P95

2. **Implement Policy Engine** (k003e)
   - 27+ hierarchical rules
   - BLACK → RED → AMBER → GREEN evaluation
   - Explanation generation
   - Target: <5ms P95

3. **Implement Fusion Engine** (k003d)
   - Confidence-weighted fusion
   - Dual EMA (fast/slow)
   - Per-person calibration
   - In-memory cache

4. **Integration Tests**
   - Full pipeline: Event → Classification → Fusion → EMA → Policy → Storage
   - Performance validation (<70ms P95)
   - Accuracy validation (vs ground truth)

## Contributing

Follow the 5-step gated workflow from `.github/copilot-instructions.md`:

1. **GATE 1**: Verify ADR exists and is ACCEPTED
2. **GATE 2**: Check contracts in `k0/contracts/jsonschema/affect/`
3. **GATE 3**: Implement with contract compliance, add `cognitive_trace_id`
4. **GATE 4**: Write pytest tests (integration > unit)
5. **GATE 5**: Document in memory with `mem_write()`

## License

See LICENSE file in repository root.
