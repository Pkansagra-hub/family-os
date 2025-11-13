---
adr_number: '0012d'
parent_adr: '0012'
affected_layers:
  - K0 Memory Kernel
  - Cognitive Services
affected_modules:
  - affect
  - modules/affect
  - learning (P06)
authors:
  - '@K0-Architecture'
concerns:
  - architecture
  - performance
  - calibration
  - observability
date_created: '2025-11-13'
date_updated: '2025-11-13'
implementation_status: ACCEPTED
status: ACCEPTED
title: 'ADR-0012d: Multi-Modal Fusion, EMA & Calibration'
---

# ADR-0012d: Multi-Modal Fusion, EMA & Calibration

**Status**: Accepted
**Parent ADR**: ADR-0012 (Affect Module)
**Date**: 2025-11-13
**Authors**: @K0-Architecture

---

## Context

ADR-0012b defines **Tier-0** (lexicon + behavioral arousal), and ADR-0012c defines **Tier-1** (VADER + TextBlob + ONNX). This ADR specifies:

1. **Multi-modal fusion**: How to combine text, behavior, prosody, face, HRV signals
2. **EMA (Exponential Moving Average)**: Temporal smoothing of affect state per person×space
3. **Calibration**: Adapting priors and thresholds based on P06 feedback signals

**Goals**:

- **Robust fusion**: Handle missing modalities gracefully (e.g., no prosody on text-only messages)
- **Temporal consistency**: Avoid whiplash from single noisy measurements
- **Personalization**: Adapt to individual expression styles over time
- **Explainability**: Maintain attribution for which signals contributed to final affect state

---

## Decision

### 1. Multi-Modal Fusion Architecture

**Available Modalities** (per ADR-0012):

| Modality | Source | Signals | Availability |
|----------|--------|---------|--------------|
| **Text** | Message content | Valence (lexicon, VADER, ONNX), arousal (magnitude, density) | Always |
| **Behavior** | Typing patterns | Burstiness, backspace ratio, retries, friction | Always (if text input) |
| **Prosody** | Voice analysis | Pitch variance, speech rate, pauses | Optional (voice messages) |
| **Face** | Action Units (AU) | AU12 (smile), AU4 (frown), AU6+12 (genuine joy) | Optional (video calls) |
| **HRV** | Wearable sensors | RMSSD, HF power | Optional (if wearable connected) |

**Fusion Strategy**: **Confidence-weighted late fusion**

**Why Late Fusion?**

- Modalities have different scales and semantics
- Early fusion (concatenate features) assumes synchronized multi-modal data
- Late fusion allows graceful degradation when modalities are missing

---

### 2. Fusion Algorithm

#### 2.1 Per-Modality Scoring

Each modality produces a tuple:

```python
@dataclass
class ModalityScore:
    valence: float          # [-1, 1]
    arousal: float          # [0, 1]
    confidence: float       # [0, 1]
    source: str             # "text", "behavior", "prosody", "face", "hrv"
```

**Example**:

```python
text_score = ModalityScore(
    valence=0.65,
    arousal=0.45,
    confidence=0.85,
    source="text"
)

behavior_score = ModalityScore(
    valence=0.0,            # Behavior doesn't contribute to valence
    arousal=0.72,
    confidence=0.75,
    source="behavior"
)
```

#### 2.2 Confidence-Weighted Fusion

**Formula** (for valence):

$$
v_{\text{fused}} = \frac{\sum_{i} c_i \cdot v_i}{\sum_{i} c_i}
$$

where:

- $v_i$ = valence from modality $i$
- $c_i$ = confidence from modality $i$

**Formula** (for arousal):

$$
a_{\text{fused}} = \frac{\sum_{i} c_i \cdot a_i}{\sum_{i} c_i}
$$

**Confidence of Fused Result**:

$$
c_{\text{fused}} = \frac{1}{N} \sum_{i} c_i
$$

(Average confidence across modalities)

**Implementation**:

```python
def fuse_modalities(scores: list[ModalityScore]) -> Tuple[float, float, float, dict]:
    """
    Confidence-weighted late fusion.

    Returns:
        (valence_fused, arousal_fused, confidence_fused, attribution)
    """
    if not scores:
        return 0.0, 0.0, 0.0, {}

    # Valence fusion (only modalities with valence signal)
    valence_scores = [(s.valence, s.confidence) for s in scores if s.valence != 0.0]
    if valence_scores:
        total_weight_v = sum(c for _, c in valence_scores)
        valence_fused = sum(v * c for v, c in valence_scores) / total_weight_v
    else:
        valence_fused = 0.0

    # Arousal fusion (all modalities)
    arousal_scores = [(s.arousal, s.confidence) for s in scores]
    total_weight_a = sum(c for _, c in arousal_scores)
    arousal_fused = sum(a * c for a, c in arousal_scores) / total_weight_a

    # Confidence fusion (average)
    confidence_fused = sum(s.confidence for s in scores) / len(scores)

    # Attribution dictionary
    attribution = {
        s.source + "_valence": s.valence for s in scores if s.valence != 0.0
    }
    attribution.update({
        s.source + "_arousal": s.arousal for s in scores
    })
    attribution.update({
        s.source + "_confidence": s.confidence for s in scores
    })

    return valence_fused, arousal_fused, confidence_fused, attribution
```

**Example**:

```python
scores = [
    ModalityScore(valence=0.65, arousal=0.45, confidence=0.85, source="text"),
    ModalityScore(valence=0.0, arousal=0.72, confidence=0.75, source="behavior"),
    ModalityScore(valence=0.50, arousal=0.30, confidence=0.70, source="prosody"),
]

v, a, c, attr = fuse_modalities(scores)

# v = (0.65*0.85 + 0.50*0.70) / (0.85 + 0.70) = 0.591
# a = (0.45*0.85 + 0.72*0.75 + 0.30*0.70) / (0.85 + 0.75 + 0.70) = 0.522
# c = (0.85 + 0.75 + 0.70) / 3 = 0.767

# attr = {
#   "text_valence": 0.65,
#   "prosody_valence": 0.50,
#   "text_arousal": 0.45,
#   "behavior_arousal": 0.72,
#   "prosody_arousal": 0.30,
#   "text_confidence": 0.85,
#   "behavior_confidence": 0.75,
#   "prosody_confidence": 0.70,
# }
```

---

### 3. Exponential Moving Average (EMA)

**Purpose**: Smooth noisy per-event measurements into a stable affect state per person×space.

**Why EMA?**

- Balances **responsiveness** (detect sudden mood shifts) with **stability** (ignore outliers)
- Computationally cheap: $O(1)$ update per event
- Interpretable: Single parameter $\alpha$ controls smoothing strength

#### 3.1 EMA Formula

$$
\text{EMA}_{t} = \alpha \cdot x_t + (1 - \alpha) \cdot \text{EMA}_{t-1}
$$

where:

- $x_t$ = new measurement at time $t$
- $\alpha$ = smoothing parameter $\in (0, 1)$
  - **High $\alpha$** (e.g., 0.5): Responsive, tracks recent changes
  - **Low $\alpha$** (e.g., 0.1): Stable, smooths out noise
- $\text{EMA}_{t-1}$ = previous EMA value

**Initialization**:

- $\text{EMA}_0 = x_0$ (first measurement)
- Or use neutral prior: $\text{EMA}_0 = 0.0$ (for valence), $0.3$ (for arousal)

#### 3.2 Dual EMA (Fast + Slow)

**Problem**: Single EMA can't detect both gradual trends and sudden shifts.

**Solution**: Maintain two EMAs:

- **Fast EMA** ($\alpha_{\text{fast}} = 0.5$): Tracks recent changes
- **Slow EMA** ($\alpha_{\text{slow}} = 0.1$): Tracks long-term baseline

**Usage**:

- **Current state** = Fast EMA
- **Trend detection** = Fast EMA - Slow EMA
  - Positive divergence → mood improving
  - Negative divergence → mood declining

**Example**:

```python
@dataclass
class AffectEMAState:
    """Per person×space affect EMA state."""

    person_id: str
    space_id: str

    # Fast EMA (α=0.5)
    v_fast: float = 0.0
    a_fast: float = 0.3

    # Slow EMA (α=0.1)
    v_slow: float = 0.0
    a_slow: float = 0.3

    # Metadata
    n_events: int = 0
    last_updated: float = 0.0
    confidence: float = 0.0


def update_ema(state: AffectEMAState,
               v_new: float,
               a_new: float,
               c_new: float) -> AffectEMAState:
    """
    Update dual EMA state with new measurement.
    """
    alpha_fast = 0.5
    alpha_slow = 0.1

    # Fast EMA
    state.v_fast = alpha_fast * v_new + (1 - alpha_fast) * state.v_fast
    state.a_fast = alpha_fast * a_new + (1 - alpha_fast) * state.a_fast

    # Slow EMA
    state.v_slow = alpha_slow * v_new + (1 - alpha_slow) * state.v_slow
    state.a_slow = alpha_slow * a_new + (1 - alpha_slow) * state.a_slow

    # Update metadata
    state.n_events += 1
    state.last_updated = time.time()
    state.confidence = c_new

    return state
```

**Trend Detection**:

```python
def get_trend(state: AffectEMAState) -> Tuple[str, float]:
    """
    Detect mood trend.

    Returns:
        (trend_label, divergence_magnitude)
    """
    v_divergence = state.v_fast - state.v_slow
    a_divergence = state.a_fast - state.a_slow

    # Valence trend
    if v_divergence > 0.2:
        v_trend = "improving"
    elif v_divergence < -0.2:
        v_trend = "declining"
    else:
        v_trend = "stable"

    # Arousal trend
    if a_divergence > 0.2:
        a_trend = "rising"
    elif a_divergence < -0.2:
        a_trend = "falling"
    else:
        a_trend = "stable"

    return f"valence_{v_trend}_arousal_{a_trend}", abs(v_divergence) + abs(a_divergence)
```

#### 3.3 EMA Parameter Selection

**Recommended Values**:

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| $\alpha_{\text{fast}}$ | 0.5 | Effective window: ~2 events (responsive) |
| $\alpha_{\text{slow}}$ | 0.1 | Effective window: ~10 events (stable baseline) |
| Initial valence | 0.0 | Neutral prior (no assumption) |
| Initial arousal | 0.3 | Mild arousal prior (typical baseline) |

**Effective Window** (for $\alpha$):

$$
N_{\text{eff}} = \frac{2}{\alpha}
$$

Examples:

- $\alpha = 0.5 \Rightarrow N_{\text{eff}} = 4$ events
- $\alpha = 0.1 \Rightarrow N_{\text{eff}} = 20$ events

**Tuning Considerations**:

- **Households with frequent messages** (e.g., teens): Use higher $\alpha$ (e.g., 0.6) for fast EMA
- **Households with sparse messages** (e.g., elderly): Use lower $\alpha$ (e.g., 0.3) for fast EMA
- **Child safety contexts**: Use lower $\alpha$ (e.g., 0.2) to avoid false alarms from single events

---

### 4. Calibration Strategy

**Problem**: Initial thresholds and priors may not generalize across:

- **Individuals** (baseline expressiveness varies)
- **Households** (communication norms differ)
- **Contexts** (work vs family vs bedtime)

**Solution**: Adapt parameters using feedback from **P06 Learning** pipeline.

#### 4.1 Feedback Signals

**Explicit Feedback** (user-initiated):

- User corrects policy band: "This wasn't RED, it was AMBER"
- User labels emotion: "I was feeling anxious" (arousal correction)
- User deletes/edits message → infer affect mismatch

**Implicit Feedback** (behavioral):

- High arousal + no follow-up → likely false positive
- Low arousal + rapid message deletion → likely false negative
- Family conflict prediction + harmonious outcome → false positive

**Ground Truth Proxies** (from P06):

- Recall queries: "Show me happy moments" → validate valence predictions
- User preferences: Skip/highlight based on affect tags
- Downstream UX: User engagement with affect-filtered content

#### 4.2 Calibration Parameters

**Learnable Parameters** (per person):

| Parameter | Initial Value | Range | Update Rule |
|-----------|---------------|-------|-------------|
| Valence bias | 0.0 | [-0.3, 0.3] | Linear shift |
| Arousal bias | 0.0 | [-0.2, 0.2] | Linear shift |
| Temperature (valence) | 1.0 | [0.5, 2.0] | Scaling factor |
| Temperature (arousal) | 1.0 | [0.5, 2.0] | Scaling factor |
| EMA $\alpha_{\text{fast}}$ | 0.5 | [0.3, 0.7] | Responsiveness |

**Calibration Formula**:

$$
v_{\text{calibrated}} = T_v \cdot (v_{\text{raw}} + b_v)
$$

$$
a_{\text{calibrated}} = T_a \cdot (a_{\text{raw}} + b_a)
$$

where:

- $b_v, b_a$ = bias terms (shift predictions)
- $T_v, T_a$ = temperature terms (scale confidence)

**Example**:

```python
@dataclass
class CalibrationParams:
    person_id: str

    # Bias terms
    valence_bias: float = 0.0
    arousal_bias: float = 0.0

    # Temperature terms
    valence_temp: float = 1.0
    arousal_temp: float = 1.0

    # EMA responsiveness
    alpha_fast: float = 0.5

    # Metadata
    n_feedback_samples: int = 0
    last_updated: float = 0.0


def apply_calibration(v_raw: float,
                      a_raw: float,
                      params: CalibrationParams) -> Tuple[float, float]:
    """
    Apply per-person calibration.
    """
    v_cal = params.valence_temp * (v_raw + params.valence_bias)
    a_cal = params.arousal_temp * (a_raw + params.arousal_bias)

    # Clamp to valid range
    v_cal = np.clip(v_cal, -1.0, 1.0)
    a_cal = np.clip(a_cal, 0.0, 1.0)

    return v_cal, a_cal
```

#### 4.3 Calibration Update Algorithm

**Online Learning** (incremental updates per feedback):

```python
def update_calibration(params: CalibrationParams,
                       v_predicted: float,
                       v_ground_truth: float,
                       learning_rate: float = 0.05) -> CalibrationParams:
    """
    Update calibration parameters using gradient descent.

    Loss: MSE between predicted and ground truth valence.
    """
    error = v_ground_truth - v_predicted

    # Update bias (gradient: -error)
    params.valence_bias += learning_rate * error

    # Update temperature (gradient: -error * v_raw)
    params.valence_temp += learning_rate * error * v_predicted

    # Clamp to valid range
    params.valence_bias = np.clip(params.valence_bias, -0.3, 0.3)
    params.valence_temp = np.clip(params.valence_temp, 0.5, 2.0)

    params.n_feedback_samples += 1
    params.last_updated = time.time()

    return params
```

**Batch Learning** (weekly recalibration):

- Collect feedback samples over 1 week
- Fit linear regression: $v_{\text{ground}} = T \cdot v_{\text{raw}} + b$
- Update calibration parameters atomically

#### 4.4 Guardrails

**Safety Constraints**:

- **Max bias**: $|b_v| \leq 0.3$, $|b_a| \leq 0.2$ (prevent runaway drift)
- **Min feedback samples**: Require ≥10 samples before first calibration
- **Decay rate**: Exponential decay of old feedback (half-life: 30 days)
- **Manual override**: Allow users to reset calibration to defaults

**Observability**:

- Log calibration parameter changes to Prometheus
- Alert if parameters exceed thresholds (e.g., $|b_v| > 0.25$)
- Dashboard: Show per-person calibration status and drift

**Rollback**:

- Feature flag: Disable calibration globally
- Per-person toggle: Opt-out of calibration
- Revert to default parameters if user reports issues

---

### 5. Integration with P06 Learning

**P06 Learning Pipeline** (ADR-TBD):

1. **Collect feedback signals** (explicit + implicit)
2. **Aggregate per person×context**
3. **Compute calibration updates**
4. **Apply updates to affect module** (via MCP)
5. **Validate improvements** (A/B test)

**Affect Module Role**:

- Expose calibration API: `update_calibration_params(person_id, params)`
- Log predictions + ground truth for P06 ingestion
- Emit metrics: `affect_prediction_error`, `affect_calibration_drift`

**Example Workflow**:

```python
# Step 1: User corrects policy band (explicit feedback)
user_correction = {
    "event_id": "evt_12345",
    "predicted_band": "RED",
    "ground_truth_band": "AMBER",
    "v_predicted": -0.6,
    "a_predicted": 0.8,
    "v_ground_truth": -0.3,  # Inferred from AMBER band
    "a_ground_truth": 0.5,
}

# Step 2: P06 sends calibration update
calibration_update = CalibrationParams(
    person_id="person_abc",
    valence_bias=0.15,      # Shift predictions more positive
    valence_temp=1.1,       # Increase confidence slightly
)

# Step 3: Affect module applies calibration
affect_service.update_calibration(calibration_update)

# Step 4: Future predictions use calibrated parameters
v_new, a_new = affect_service.classify(...)
# v_new is now more positive due to bias shift
```

---

### 6. Implementation

**Module**: `k0/modules/affect/fusion.py`

```python
from dataclasses import dataclass
from typing import Optional, Tuple, List
import numpy as np
import time

@dataclass
class ModalityScore:
    valence: float
    arousal: float
    confidence: float
    source: str


@dataclass
class AffectEMAState:
    person_id: str
    space_id: str
    v_fast: float = 0.0
    a_fast: float = 0.3
    v_slow: float = 0.0
    a_slow: float = 0.3
    n_events: int = 0
    last_updated: float = 0.0
    confidence: float = 0.0


@dataclass
class CalibrationParams:
    person_id: str
    valence_bias: float = 0.0
    arousal_bias: float = 0.0
    valence_temp: float = 1.0
    arousal_temp: float = 1.0
    alpha_fast: float = 0.5
    n_feedback_samples: int = 0
    last_updated: float = 0.0


class MultiModalFusion:
    """
    Multi-modal affect fusion with EMA smoothing and calibration.
    """

    def __init__(self):
        self.ema_cache: dict[Tuple[str, str], AffectEMAState] = {}
        self.calibration_cache: dict[str, CalibrationParams] = {}

    def fuse_and_smooth(self,
                        person_id: str,
                        space_id: str,
                        modality_scores: List[ModalityScore],
                        apply_calibration: bool = True) -> Tuple[float, float, float, dict]:
        """
        Main fusion + EMA + calibration pipeline.

        Returns:
            (valence, arousal, confidence, attribution)
        """
        # Step 1: Confidence-weighted fusion
        v_fused, a_fused, c_fused, attribution = self._fuse_modalities(modality_scores)

        # Step 2: Apply calibration
        if apply_calibration:
            calibration = self._get_calibration(person_id)
            v_fused, a_fused = self._apply_calibration(v_fused, a_fused, calibration)
            attribution['calibration_valence_bias'] = calibration.valence_bias
            attribution['calibration_arousal_bias'] = calibration.arousal_bias

        # Step 3: EMA smoothing
        ema_state = self._get_ema_state(person_id, space_id)
        ema_state = self._update_ema(ema_state, v_fused, a_fused, c_fused)
        self.ema_cache[(person_id, space_id)] = ema_state

        # Return smoothed values
        return ema_state.v_fast, ema_state.a_fast, ema_state.confidence, attribution

    def _fuse_modalities(self, scores: List[ModalityScore]) -> Tuple[float, float, float, dict]:
        """Confidence-weighted late fusion."""
        if not scores:
            return 0.0, 0.0, 0.0, {}

        # Valence fusion
        valence_scores = [(s.valence, s.confidence) for s in scores if s.valence != 0.0]
        if valence_scores:
            total_weight_v = sum(c for _, c in valence_scores)
            valence_fused = sum(v * c for v, c in valence_scores) / total_weight_v
        else:
            valence_fused = 0.0

        # Arousal fusion
        arousal_scores = [(s.arousal, s.confidence) for s in scores]
        total_weight_a = sum(c for _, c in arousal_scores)
        arousal_fused = sum(a * c for a, c in arousal_scores) / total_weight_a

        # Confidence fusion
        confidence_fused = sum(s.confidence for s in scores) / len(scores)

        # Attribution
        attribution = {}
        for s in scores:
            if s.valence != 0.0:
                attribution[f"{s.source}_valence"] = s.valence
            attribution[f"{s.source}_arousal"] = s.arousal
            attribution[f"{s.source}_confidence"] = s.confidence

        return valence_fused, arousal_fused, confidence_fused, attribution

    def _get_ema_state(self, person_id: str, space_id: str) -> AffectEMAState:
        """Get or create EMA state."""
        key = (person_id, space_id)
        if key not in self.ema_cache:
            self.ema_cache[key] = AffectEMAState(person_id=person_id, space_id=space_id)
        return self.ema_cache[key]

    def _update_ema(self,
                    state: AffectEMAState,
                    v_new: float,
                    a_new: float,
                    c_new: float) -> AffectEMAState:
        """Update dual EMA."""
        alpha_fast = 0.5
        alpha_slow = 0.1

        # Fast EMA
        state.v_fast = alpha_fast * v_new + (1 - alpha_fast) * state.v_fast
        state.a_fast = alpha_fast * a_new + (1 - alpha_fast) * state.a_fast

        # Slow EMA
        state.v_slow = alpha_slow * v_new + (1 - alpha_slow) * state.v_slow
        state.a_slow = alpha_slow * a_new + (1 - alpha_slow) * state.a_slow

        # Metadata
        state.n_events += 1
        state.last_updated = time.time()
        state.confidence = c_new

        return state

    def _get_calibration(self, person_id: str) -> CalibrationParams:
        """Get or create calibration parameters."""
        if person_id not in self.calibration_cache:
            self.calibration_cache[person_id] = CalibrationParams(person_id=person_id)
        return self.calibration_cache[person_id]

    def _apply_calibration(self,
                          v_raw: float,
                          a_raw: float,
                          params: CalibrationParams) -> Tuple[float, float]:
        """Apply calibration transform."""
        v_cal = params.valence_temp * (v_raw + params.valence_bias)
        a_cal = params.arousal_temp * (a_raw + params.arousal_bias)

        # Clamp to valid range
        v_cal = np.clip(v_cal, -1.0, 1.0)
        a_cal = np.clip(a_cal, 0.0, 1.0)

        return v_cal, a_cal

    def update_calibration_params(self, person_id: str, params: CalibrationParams):
        """Update calibration parameters (called by P06)."""
        self.calibration_cache[person_id] = params
        logger.info(f"Updated calibration for {person_id}: bias={params.valence_bias:.3f}")

    def get_trend(self, person_id: str, space_id: str) -> Tuple[str, float]:
        """Detect mood trend from dual EMA."""
        state = self._get_ema_state(person_id, space_id)

        v_divergence = state.v_fast - state.v_slow
        a_divergence = state.a_fast - state.a_slow

        # Valence trend
        if v_divergence > 0.2:
            v_trend = "improving"
        elif v_divergence < -0.2:
            v_trend = "declining"
        else:
            v_trend = "stable"

        # Arousal trend
        if a_divergence > 0.2:
            a_trend = "rising"
        elif a_divergence < -0.2:
            a_trend = "falling"
        else:
            a_trend = "stable"

        return f"valence_{v_trend}_arousal_{a_trend}", abs(v_divergence) + abs(a_divergence)
```

---

## Consequences

### Positive

✅ **Robust fusion**: Handles missing modalities gracefully
✅ **Temporal stability**: EMA smooths noisy per-event measurements
✅ **Personalization**: Calibration adapts to individual expression styles
✅ **Explainability**: Attribution dictionary shows contribution of each modality
✅ **Trend detection**: Dual EMA detects both recent shifts and long-term baselines
✅ **P06 integration**: Feedback loop enables continuous improvement

### Negative

❌ **Complexity**: Multi-modal fusion + EMA + calibration adds 3 layers of logic
❌ **State management**: Per-person×space EMA cache requires memory
❌ **Calibration drift**: Parameters may overfit to recent feedback
❌ **Debugging difficulty**: Hard to trace attribution through fusion → EMA → calibration

### Risks

- **Cold start problem**: New users have no calibration data (use default parameters)
- **Feedback quality**: Noisy or adversarial feedback can corrupt calibration
- **Privacy leakage**: Calibration parameters reveal personal baselines (must encrypt)
- **Performance regression**: Calibration may reduce accuracy for edge cases

**Mitigation**:

- Default parameters work well for cold start (no calibration required)
- Outlier detection on feedback signals (reject adversarial samples)
- Encrypt calibration parameters with person-scoped MLS key
- A/B testing: Validate calibration improvements before wide rollout
- Rollback mechanism: Revert to default parameters if accuracy drops

---

## Implementation Checklist

- [ ] Implement `MultiModalFusion` class in `k0/modules/affect/fusion.py`
- [ ] Add EMA state storage (in-memory LRU cache, backed by `st_affect_state`)
- [ ] Add calibration parameter storage (encrypted in `st_calibration_params`)
- [ ] Expose calibration API for P06: `update_calibration_params(person_id, params)`
- [ ] Unit tests: Fusion, EMA update, calibration transform, trend detection
- [ ] Integration tests: P02 → fusion → EMA → `st_hipp_store`
- [ ] Performance tests: Fusion latency <5ms, EMA update <1ms
- [ ] Observability: Metrics for calibration drift, EMA divergence, fusion confidence
- [ ] Documentation: Fusion algorithm, EMA tuning guide, calibration guardrails

---

## References

- **Parent ADR**: ADR-0012 (Affect Module)
- **Related ADRs**:
  - k003a (Affect Contracts & Storage)
  - k003b (Tier-0 Realtime Classifier)
  - k003c (Tier-1 Enhanced Classifier)
  - k003e (Policy Band Rules)
- **Module Location**: `k0/modules/affect/fusion.py`
- **Research**:
  - Multi-Modal Fusion: Baltrusaitis et al., 2019 (IEEE Transactions on Pattern Analysis)
  - EMA for Time Series: Hunter, 1986 (IMA Journal)
  - Calibration: Guo et al., 2017 (ICML - "On Calibration of Modern Neural Networks")

---

## Revision History

- 2025-11-13: Initial draft (@K0-Architecture)
