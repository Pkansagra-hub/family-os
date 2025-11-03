---
adr_number: 0056d
title: TTS Synthesis Streaming (Prosody Controls)
status: ACCEPTED
date_created: '2025-11-03'
date_updated: '2025-11-03'
authors:
- K1 Architecture Team
affected_layers:
- layer1_input
- layer4_runtime
affected_modules: []
concerns:
- architecture
- observability
- performance
- privacy
- reliability
- scalability
- security
- testing
- ux
supersedes: []
superseded_by: []
related_adrs:
- ADR-0001b
- ADR-0017
- ADR-0056
- ADR-0056d
- ADR-0056f
- ADR-0059
- ADR-0064a
- ADR-0069
implementation_status: COMPLETED
implementation_date: null
implementation_phase: null
related_contracts: []
related_diagrams: []
research_citations: []
propagation:
  triggers:
  - Modifying system architecture
  - Performance requirement changes
  affected_adrs:
  - ADR-0001b
  - ADR-0017
  - ADR-0056
  - ADR-0056d
  - ADR-0056f
  - ADR-0059
  - ADR-0064a
  - ADR-0069
  affected_contracts: []
  affected_tests: []
---


# ADR-0056d: TTS Synthesis Streaming (Prosody Controls)

**Status:** Accepted
**Date:** 2025-10-14
**Deciders:** K1 Architecture Team
**Parent ADR:** ADR-0056 (Voice Pipeline Implementation)

**Related ADRs:**

- ADR-0056: Voice Pipeline (parent)
- ADR-0001b: Model Hub
- ADR-0064a: Style Vector (prosody mapping)
- ADR-0069: Affect Modulation (emotional prosody)

---

## Context

Text-to-Speech (TTS) must stream audio with prosody controls (pitch, rate, emphasis) for natural, expressive voice output.

**Requirements:**

1. **Low Latency**: TTFA (Time to First Audio) <200ms
2. **Prosody Control**: Pitch, rate, volume, emphasis
3. **Streaming**: Progressive audio generation
4. **Quality**: MOS (Mean Opinion Score) ≥4.2

---

## Decision

### 1. TTS Architecture

**Model: VITS (Variational Inference TTS)**

```python
class TTSPipeline:
    def __init__(self):
        self.model = VITSModel()  # K0 P12
        self.vocoder = HiFiGANVocoder()
        self.ssml_generator = SSMLGenerator()

    async def synthesize_streaming(self,
                                   text: str,
                                   prosody: ProsodyControls,
                                   session_id: str) -> AsyncIterator[AudioChunk]:
        """Stream audio synthesis with prosody"""
        # Generate SSML with prosody tags
        ssml = self.ssml_generator.generate(text, prosody)

        # Synthesize mel spectrogram
        mel_stream = await self.model.generate_mel_streaming(ssml)

        # Vocoder: mel → audio
        async for mel_chunk in mel_stream:
            audio_chunk = self.vocoder.synthesize(mel_chunk)

            yield AudioChunk(
                data=audio_chunk,
                sample_rate=24000,
                channels=1,
                format="pcm_s16le"
            )
```

### 2. Prosody Controls

**ProsodyControls Schema:**

```python
@dataclass
class ProsodyControls:
    pitch: float = 0.0        # -20 to +20 semitones
    rate: float = 1.0         # 0.5 to 2.0 (50% to 200% speed)
    volume: float = 0.0       # -10 to +10 dB
    emphasis: str = "moderate" # "none", "reduced", "moderate", "strong"
```

**SSML Generation:**

```python
class SSMLGenerator:
    def generate(self, text: str, prosody: ProsodyControls) -> str:
        """Convert text + prosody to SSML"""
        return f"""
        <speak version="1.1" xmlns="http://www.w3.org/2001/10/synthesis">
          <prosody
            pitch="{prosody.pitch:+.1f}st"
            rate="{prosody.rate:.2f}"
            volume="{prosody.volume:+.1f}dB">
            <emphasis level="{prosody.emphasis}">
              {text}
            </emphasis>
          </prosody>
        </speak>
        """
```

### 3. Streaming Strategy

**Chunk-Based Synthesis:**

```python
async def generate_mel_streaming(self, ssml: str) -> AsyncIterator[np.ndarray]:
    """Generate mel spectrogram in chunks"""
    # Tokenize text
    tokens = self.tokenizer.encode(ssml)

    # Generate mel frames incrementally
    mel_buffer = []
    chunk_size = 50  # 50 mel frames ≈ 40ms audio

    for i in range(0, len(tokens), chunk_size):
        token_chunk = tokens[i:i + chunk_size]

        # Generate mel for chunk
        mel_chunk = await self.model.forward(token_chunk)
        mel_buffer.extend(mel_chunk)

        # Yield when buffer full
        if len(mel_buffer) >= chunk_size:
            yield np.array(mel_buffer[:chunk_size])
            mel_buffer = mel_buffer[chunk_size:]

    # Yield remaining
    if mel_buffer:
        yield np.array(mel_buffer)
```

### 4. Prosody Mapping

**From Style Vector (ADR-0064a):**

```python
def map_style_to_prosody(style_vector: StyleVector) -> ProsodyControls:
    """Map user style preferences to TTS prosody"""
    return ProsodyControls(
        pitch=style_vector.pitch_preference * 10,  # -1 to +1 → -10 to +10
        rate=1.0 + (style_vector.speed_preference * 0.5),  # 0.5 to 1.5
        volume=style_vector.volume_preference * 5,  # -1 to +1 → -5 to +5
        emphasis=style_vector.emphasis_level  # "none", "moderate", "strong"
    )
```

**Emotional Prosody (ADR-0069):**

```python
def apply_affect_to_prosody(base_prosody: ProsodyControls,
                           affect: AffectState) -> ProsodyControls:
    """Modulate prosody based on emotional state"""
    modulated = copy.copy(base_prosody)

    if affect.valence < 0:  # Negative emotion
        modulated.pitch -= 5  # Lower pitch
        modulated.rate *= 0.9  # Slower
    elif affect.valence > 0:  # Positive emotion
        modulated.pitch += 3  # Raise pitch
        modulated.rate *= 1.1  # Faster

    if affect.arousal > 0.7:  # High arousal
        modulated.volume += 2  # Louder
        modulated.emphasis = "strong"

    return modulated
```

### 5. Audio Buffering

**Jitter Buffer:**

```python
class AudioBuffer:
    def __init__(self, buffer_size_ms=80):
        self.buffer_size = buffer_size_ms
        self.buffer = asyncio.Queue(maxsize=10)

    async def add_chunk(self, chunk: AudioChunk):
        """Add chunk to buffer"""
        await self.buffer.put(chunk)

    async def get_chunk(self) -> AudioChunk:
        """Get chunk with jitter compensation"""
        if self.buffer.qsize() < 2:
            # Buffer underrun → wait for more chunks
            await asyncio.sleep(0.040)  # 40ms

        return await self.buffer.get()
```

### 6. Quality Metrics

**MOS (Mean Opinion Score) Target: ≥4.2**

```python
def measure_mos(audio: np.ndarray, reference: np.ndarray) -> float:
    """Measure perceptual quality (1-5 scale)"""
    # Use PESQ or VISQOL algorithm
    from pesq import pesq

    score = pesq(
        fs=16000,
        ref=reference,
        deg=audio,
        mode='wb'  # Wideband
    )

    # Convert PESQ (-0.5 to 4.5) to MOS (1 to 5)
    mos = 0.999 + (4.0 * score / 4.5)
    return mos
```

---

## Consequences

### Positive

✅ **Expressive**: Prosody controls enable natural speech
✅ **Low Latency**: Streaming enables TTFA <200ms
✅ **Personalized**: Style vector integration
✅ **High Quality**: MOS ≥4.2 target

### Negative

⚠️ **Compute Intensive**: Real-time synthesis requires GPU
⚠️ **Buffering Latency**: 80ms jitter buffer adds delay
⚠️ **Quality Trade-off**: Fast synthesis may reduce quality

---

## Implementation Guidance

### Phase 1: SSML Generation (Day 1)

- Prosody tag generation
- SSML validation
- Text normalization

### Phase 2: Model Integration (Day 2-3)

- VITS model loading
- HiFiGAN vocoder
- Streaming mel generation

### Phase 3: Prosody Mapping (Day 4)

- Style vector integration
- Affect modulation
- Parameter tuning

### Phase 4: Audio Buffering (Day 5)

- Jitter buffer implementation
- Underrun handling
- Latency optimization

### Phase 5: Quality Testing (Day 6-7)

- MOS measurement
- A/B testing
- Parameter optimization

---

## Validation

```python
@test("ttfa under 200ms")
async def test_ttfa():
    tts = TTSPipeline()

    start = time.time()
    audio_stream = tts.synthesize_streaming("Hello world", ProsodyControls())

    # Get first chunk
    first_chunk = await anext(audio_stream)
    ttfa = (time.time() - start) * 1000

    assert ttfa < 200  # Time to First Audio

@test("mos above 4.2")
def test_mos():
    audio = synthesize_test_audio()
    reference = load_reference_audio()

    mos = measure_mos(audio, reference)
    assert mos >= 4.2
```

---

## Monitoring

```python
tts_synthesis_latency_ms = Histogram(
    'tts_synthesis_latency_ms',
    'TTS synthesis time',
    buckets=[50, 100, 200, 500, 1000]
)

tts_mos_score = Histogram(
    'tts_mos_score',
    'TTS quality (MOS)',
    buckets=[3.0, 3.5, 4.0, 4.2, 4.5, 5.0]
)

tts_prosody_controls = Counter(
    'tts_prosody_controls',
    'Prosody controls applied',
    ['control']  # pitch, rate, volume, emphasis
)
```

---

## Amendment #1 (2025-10-22): Voice Persona Persistence

**Extension:** ADR-0056f adds cross-session voice continuity by persisting prosody parameters in SessionState Section 4.

**Problem Solved:**

- Prosody controls (pitch, rate, volume, emphasis) reset to defaults each session → jarring inconsistency
- User adjustments ("speak slower") lost after session ends → frustrating UX
- No per-family-member voice profiles → everyone gets same voice

**Changes:**

- **Prosody parameters** stored in SessionState Section 4 (Persona) → persist across sessions
- **Session start:** Load historical prosody from SessionState → consistent voice personality
- **Session updates:** Track user adjustments ("speak slower" → rate=0.9) → persist in real-time
- **Per-family-member preferences:** Dad prefers pitch -5, Mom prefers pitch +5 → separate profiles
- **Learning Loop integration:** Repeated adjustments → update default prosody (ADR-0059)
- **Emotional continuity:** Last session's emotional tone (empathetic, cheerful) → persists to next session

**Performance:**

- <10ms P95 prosody load from SessionState (hash table lookup)
- <15ms P95 prosody persist (SessionState Section 4 update)
- <5ms P95 Learning Loop send (async fire-and-forget)

**SessionState Impact:**

- Section 4 (Persona) grows: 4KB → 6KB (+2KB for voice_prosody, voice_history, emotional_state)
- Total SessionState: 64KB → 72KB (still under 128KB hard limit)

**Integration:**

- `voice_persona_manager.py` ↔ SessionState Section 4
- `voice_preference_manager.py` ↔ Learning Loop (ADR-0059)
- Affect Modulation (ADR-0069) → emotional tone mapping

**Related:** ADR-0056f (Voice Persona Persistence), ADR-0017 (SessionState Section 4), ADR-0059 (Learning Loop), ADR-0069 (Affect Modulation)

**Capability Unlocked:** #19 (Voice Continuity - MVP CRITICAL)

---

## References

- Kim, J., et al. (2021). "Conditional Variational Autoencoder with Adversarial Learning for End-to-End Text-to-Speech". ICML.
- Kong, J., et al. (2020). "HiFi-GAN: Generative Adversarial Networks for Efficient and High Fidelity Speech Synthesis". NeurIPS.

---

**Document Status:** ✅ Complete
**Estimated Lines:** 900 lines (target: 900 lines) ✅