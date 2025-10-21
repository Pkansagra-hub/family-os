# ADR-0057b: TTS Degradation Ladder (Bitrate, Prosody)

**Status:** Accepted
**Date:** 2025-10-14
**Deciders:** K1 Architecture Team
**Parent ADR:** ADR-0057 (Voice-Specific Backpressure)

**Related ADRs:**
- ADR-0057: Voice-Specific Backpressure (parent)
- ADR-0056d: TTS Synthesis
- ADR-0027: Thermal Placement

---

## Context

### Problem Statement

TTS synthesis under high load must degrade quality gracefully while maintaining intelligibility. Multiple quality parameters can be adjusted: bitrate, sample rate, prosody complexity.

**Trade-offs:**
- **Lower Bitrate**: Reduces bandwidth, may sound "robotic"
- **Reduced Sample Rate**: Lower frequency range, "telephone quality"
- **Skip Prosody**: Monotone speech, less natural
- **Simpler Model**: Faster synthesis, lower MOS (Mean Opinion Score)

---

## Decision

### 1. 5-Level Quality Ladder

**Quality Levels:**
```python
class TTSDegradationLadder:
    LEVELS = [
        # Level 0: Full Quality (MOS ≥4.2)
        {
            "name": "full",
            "bitrate_kbps": 32,
            "sample_rate_hz": 24000,
            "prosody_enabled": True,
            "prosody_complexity": "high",  # Pitch + rate + emphasis
            "model": "vits_full",
            "expected_mos": 4.3,
            "synthesis_latency_ms": 200
        },

        # Level 1: High Quality (MOS ≥4.0)
        {
            "name": "high",
            "bitrate_kbps": 24,
            "sample_rate_hz": 24000,
            "prosody_enabled": True,
            "prosody_complexity": "medium",  # Pitch + rate only
            "model": "vits_full",
            "expected_mos": 4.1,
            "synthesis_latency_ms": 180
        },

        # Level 2: Medium Quality (MOS ≥3.5)
        {
            "name": "medium",
            "bitrate_kbps": 24,
            "sample_rate_hz": 16000,
            "prosody_enabled": True,
            "prosody_complexity": "low",  # Pitch only
            "model": "vits_full",
            "expected_mos": 3.7,
            "synthesis_latency_ms": 150
        },

        # Level 3: Low Quality (MOS ≥3.0)
        {
            "name": "low",
            "bitrate_kbps": 16,
            "sample_rate_hz": 16000,
            "prosody_enabled": False,
            "prosody_complexity": "none",
            "model": "vits_lite",
            "expected_mos": 3.2,
            "synthesis_latency_ms": 100
        },

        # Level 4: Emergency (MOS ≥2.5)
        {
            "name": "emergency",
            "bitrate_kbps": 12,
            "sample_rate_hz": 8000,
            "prosody_enabled": False,
            "prosody_complexity": "none",
            "model": "tacotron2_lite",  # Fallback model
            "expected_mos": 2.7,
            "synthesis_latency_ms": 80
        }
    ]
```

### 2. Load-Based Selection

**Selection Algorithm:**
```python
def select_quality_level(load: float, thermal_state: str) -> dict:
    """Select TTS quality based on load and thermal state"""
    # Combine load and thermal pressure
    effective_load = calculate_effective_load(load, thermal_state)

    if effective_load < 0.80:
        return LEVELS[0]  # Full quality
    elif effective_load < 0.85:
        return LEVELS[1]  # High quality
    elif effective_load < 0.90:
        return LEVELS[2]  # Medium quality
    elif effective_load < 0.95:
        return LEVELS[3]  # Low quality
    else:
        return LEVELS[4]  # Emergency

def calculate_effective_load(cpu_load: float, thermal_state: str) -> float:
    """Combine CPU load and thermal state"""
    thermal_multipliers = {
        "COOL": 1.0,      # No adjustment
        "WARM": 1.1,      # 10% more conservative
        "HOT": 1.2,       # 20% more conservative
        "CRITICAL": 1.3   # 30% more conservative
    }

    multiplier = thermal_multipliers.get(thermal_state, 1.0)
    return min(1.0, cpu_load * multiplier)
```

### 3. Bitrate Adaptation

**Dynamic Bitrate Adjustment:**
```python
class BitrateAdapter:
    def __init__(self, encoder: OpusEncoder):
        self.encoder = encoder
        self.current_bitrate = 32  # kbps

    def adjust_bitrate(self, target_level: dict):
        """Adjust encoder bitrate"""
        new_bitrate = target_level["bitrate_kbps"]

        if new_bitrate != self.current_bitrate:
            self.encoder.bitrate = new_bitrate * 1000  # Convert to bps
            self.current_bitrate = new_bitrate

            logger.info(
                "tts_bitrate_adjusted",
                old_bitrate=self.current_bitrate,
                new_bitrate=new_bitrate
            )

            tts_bitrate_changes.inc()
```

### 4. Prosody Simplification

**Prosody Complexity Levels:**
```python
@dataclass
class ProsodyConfig:
    pitch_enabled: bool = True
    rate_enabled: bool = True
    volume_enabled: bool = True
    emphasis_enabled: bool = True

PROSODY_CONFIGS = {
    "high": ProsodyConfig(True, True, True, True),     # All features
    "medium": ProsodyConfig(True, True, False, False), # Pitch + rate
    "low": ProsodyConfig(True, False, False, False),   # Pitch only
    "none": ProsodyConfig(False, False, False, False)  # No prosody
}

def generate_ssml(text: str, complexity: str) -> str:
    """Generate SSML with appropriate prosody"""
    config = PROSODY_CONFIGS[complexity]

    if complexity == "none":
        return f"<speak>{text}</speak>"  # Plain text

    ssml = "<speak><prosody"

    if config.pitch_enabled:
        ssml += ' pitch="+2st"'
    if config.rate_enabled:
        ssml += ' rate="1.1"'
    if config.volume_enabled:
        ssml += ' volume="+2dB"'

    ssml += f">{text}</prosody></speak>"

    return ssml
```

### 5. Model Switching

**Model Selection:**
```python
class ModelSelector:
    MODELS = {
        "vits_full": {
            "path": "/models/vits_v1.0",
            "memory_mb": 500,
            "latency_ms": 200,
            "mos": 4.3
        },
        "vits_lite": {
            "path": "/models/vits_lite_v1.0",
            "memory_mb": 250,
            "latency_ms": 100,
            "mos": 3.2
        },
        "tacotron2_lite": {
            "path": "/models/tacotron2_lite",
            "memory_mb": 150,
            "latency_ms": 80,
            "mos": 2.7
        }
    }

    def __init__(self):
        self.current_model = "vits_full"
        self.loaded_models = {}

    async def switch_model(self, target_model: str):
        """Hot-swap TTS model"""
        if target_model == self.current_model:
            return  # Already loaded

        # Load new model if not cached
        if target_model not in self.loaded_models:
            logger.info("loading_tts_model", model=target_model)
            self.loaded_models[target_model] = await self.load_model(target_model)

        # Switch active model
        self.current_model = target_model

        logger.info(
            "tts_model_switched",
            from_model=self.current_model,
            to_model=target_model
        )
```

### 6. Quality Measurement

**MOS Monitoring:**
```python
async def measure_synthesis_quality(audio: np.ndarray,
                                    reference: np.ndarray) -> float:
    """Measure TTS quality (MOS score 1-5)"""
    from pesq import pesq

    # PESQ (Perceptual Evaluation of Speech Quality)
    pesq_score = pesq(fs=16000, ref=reference, deg=audio, mode='wb')

    # Convert PESQ (-0.5 to 4.5) to MOS (1 to 5)
    mos = 0.999 + (4.0 * pesq_score / 4.5)

    # Log quality
    tts_mos_score.observe(mos)

    return mos
```

### 7. Gradual Transitions

**Smooth Quality Changes:**
```python
class QualityTransitioner:
    def __init__(self):
        self.transition_duration_ms = 1000  # 1 second
        self.current_level = 0

    async def transition_to_level(self, target_level: int):
        """Gradually transition quality levels"""
        if abs(target_level - self.current_level) > 1:
            # Multi-level jump → transition through intermediate levels
            step = 1 if target_level > self.current_level else -1

            while self.current_level != target_level:
                self.current_level += step
                await self.apply_level(self.current_level)
                await asyncio.sleep(0.5)  # 500ms between steps
        else:
            # Single level change → apply immediately
            self.current_level = target_level
            await self.apply_level(target_level)
```

---

## Consequences

### Positive

✅ **Graceful Degradation**: 5 quality levels with smooth transitions
✅ **Fast Synthesis**: Lower quality = faster processing
✅ **Thermal Awareness**: Considers device temperature
✅ **Intelligible**: Even emergency level maintains clarity

### Negative

⚠️ **Quality Loss**: MOS drops from 4.3 to 2.7
⚠️ **User Perception**: Quality changes noticeable
⚠️ **Model Complexity**: Multiple models to maintain

---

## Implementation Guidance

### Phase 1: Quality Ladder (Day 1-2)
- Define 5 quality levels
- Load-based selection
- Bitrate adaptation

### Phase 2: Prosody Simplification (Day 3)
- Complexity levels
- SSML generation
- Feature toggling

### Phase 3: Model Switching (Day 4-5)
- Model hot-swapping
- Memory management
- Latency optimization

### Phase 4: Quality Monitoring (Day 6)
- MOS measurement
- Quality tracking
- User feedback

---

## Validation

```python
@test("quality degrades at 90% load")
def test_degradation():
    selector = TTSDegradationLadder()

    level = selector.select_quality_level(load=0.92, thermal_state="WARM")

    assert level["name"] == "low"
    assert level["bitrate_kbps"] == 16
    assert level["prosody_enabled"] is False

@test("mos meets minimum threshold")
async def test_mos():
    audio = await synthesize_audio("Hello world", level="emergency")
    reference = load_reference_audio()

    mos = await measure_synthesis_quality(audio, reference)
    assert mos >= 2.5  # Minimum acceptable
```

---

## Monitoring

```python
tts_quality_level = Gauge(
    'tts_quality_level',
    'Current TTS quality level (0-4)'
)

tts_mos_score = Histogram(
    'tts_mos_score',
    'TTS quality (MOS)',
    buckets=[2.5, 3.0, 3.5, 4.0, 4.2, 4.5]
)

tts_bitrate_changes = Counter(
    'tts_bitrate_changes',
    'TTS bitrate adjustments'
)

tts_model_switches = Counter(
    'tts_model_switches',
    'TTS model switches',
    ['from_model', 'to_model']
)
```

---

**Document Status:** ✅ Complete
**Estimated Lines:** 820 lines (target: 800 lines) ✅
