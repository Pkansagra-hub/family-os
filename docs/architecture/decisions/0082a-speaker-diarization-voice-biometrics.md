---
adr_number: 0082a
title: Speaker Diarization & Voice Biometrics
status: PROPOSED
date_created: '2025-11-03'
date_updated: '2025-11-03'
authors:
- K1 Architecture Team
affected_layers:
- layer1_input
- layer3_execution
- layer4_runtime
affected_modules: []
concerns:
- architecture
- cost
- modularity
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
- ADR-0017
- ADR-0036
- ADR-0053
- ADR-0082
- ADR-0082a
implementation_status: PLANNED
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
  - ADR-0017
  - ADR-0036
  - ADR-0053
  - ADR-0082
  - ADR-0082a
  affected_contracts:
  - k0/contracts/api/rest/idempotency/24h_retention.yml
  - k0/contracts/asyncapi.events.yaml
  - k0/contracts/openapi.k0.yaml
  - k1/contracts/flatbuffers/layer3_execution/mcp_message.fbs
  - k1/contracts/flatbuffers/layer3_execution/mcp_resource_request.fbs
  - k1/contracts/flatbuffers/layer3_execution/mcp_resource_response.fbs
  - k1/contracts/flatbuffers/layer3_execution/mcp_tool_discovery.fbs
  - k1/contracts/flatbuffers/layer3_execution/model_cache_entry.fbs
  - k1/contracts/flatbuffers/layer3_execution/model_request.fbs
  - k1/contracts/flatbuffers/layer3_execution/model_response.fbs
  affected_tests: []
---


# ADR-0082a: Speaker Diarization & Voice Biometrics

**Status:** Proposed
**Date:** 2025-10-22
**Parent ADR:** ADR-0082 (Multi-Party Dialogue Coordination)
**Related ADRs:** ADR-0053 (ASR Pipeline), ADR-0036 (E2EE), ADR-0017 (SessionState)

---

## Context

### **Problem Statement**

Multi-party dialogue coordination (ADR-0082) requires **real-time speaker identification** to attribute utterances to specific family members. Traditional approaches use:
- **Visual cues:** Face recognition (requires camera, privacy concerns)
- **Explicit user selection:** Manual speaker tagging (high friction, breaks voice-first experience)
- **No identification:** Treat all speakers as same user (loses personalization)

**FamilyOS Requirements:**
1. **Voice-first:** Identify speakers from audio alone (no camera required, hands-free)
2. **Real-time:** <100ms P95 speaker identification latency (doesn't block ASR pipeline)
3. **Privacy-preserving:** Encrypt voice biometrics at rest (ADR-0036 E2EE)
4. **Robust:** Handle noise, distance variations, voice changes over time

### **Why Voice Biometrics?**

**Voice biometrics** extract unique speaker characteristics from audio:
- **Physiological features:** Vocal tract shape, pitch, formants (unique per person)
- **Behavioral features:** Speaking rate, intonation patterns, phoneme pronunciation
- **Deep embeddings:** 768-dim neural network representations capturing speaker identity

**Advantages over alternatives:**

| Approach | Pros | Cons |
|----------|------|------|
| **Face Recognition** | High accuracy (99%+) | Requires camera, privacy invasive, doesn't work in dark |
| **Manual Selection** | 100% accurate | High friction, breaks voice-first UX |
| **No Identification** | Simple | Zero personalization, treats all users same |
| **Voice Biometrics** | Voice-first compatible, hands-free, privacy-friendly | Requires enrollment, 90-95% accuracy |

**Decision:** Use voice biometrics (speaker embeddings) for primary identification method.

---

## Decision

### **Architecture: Speaker Embedding Pipeline**

```
┌─────────────────────────────────────────────────────────────────────────┐
│ ENROLLMENT PHASE (One-Time Setup Per Family Member)                     │
├─────────────────────────────────────────────────────────────────────────┤
│ User: "Add new family member"                                           │
│   ↓                                                                      │
│ System: "Please state your name"                                        │
│ User: "This is Dad"                                                     │
│   ↓                                                                      │
│ System: "Hi Dad, please read these sentences naturally..."              │
│   ↓                                                                      │
│ [Record 30-60 seconds of speech - 10-15 diverse utterances]             │
│   ↓                                                                      │
│ Audio Preprocessing:                                                    │
│   - Resample to 16kHz mono                                              │
│   - Noise reduction (Wiener filter)                                     │
│   - Voice Activity Detection (VAD) → remove silence                     │
│   ↓                                                                      │
│ Speaker Embedding Extraction (x-vector/ECAPA-TDNN model):               │
│   - 10-15 utterances → 10-15 embeddings (768-dim each)                  │
│   - Average embeddings → single profile embedding (768-dim)             │
│   ↓                                                                      │
│ Profile Storage in K0:                                                  │
│   {                                                                      │
│     "speaker_id": "Dad",                                                │
│     "voice_profile_id": "profile_001",                                  │
│     "embedding": [768-dim float vector],  # Encrypted AES-256-GCM       │
│     "created_at": 1729620000000000,                                     │
│     "sample_count": 12,                                                 │
│     "enrollment_snr_db": 22.5  # Signal-to-noise ratio during enrollment│
│   }                                                                      │
│   ↓                                                                      │
│ System: "Voice profile created for Dad. I'll now recognize you."        │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│ RUNTIME PHASE (Real-Time Speaker Identification)                        │
├─────────────────────────────────────────────────────────────────────────┤
│ Live Audio Input (Multi-Channel)                                        │
│   ↓                                                                      │
│ Voice Activity Detection (VAD):                                         │
│   - Detect speech regions (remove silence)                              │
│   - Segment into utterances (1-3 seconds each)                          │
│   ↓                                                                      │
│ Audio Preprocessing:                                                    │
│   - Resample to 16kHz mono                                              │
│   - Normalize volume                                                    │
│   - Noise reduction                                                     │
│   ↓                                                                      │
│ Speaker Embedding Extraction (x-vector/ECAPA-TDNN):                     │
│   - Input: 1-3 second audio segment                                     │
│   - Output: 768-dim embedding vector                                    │
│   - Latency: <50ms P95 (ONNX optimized inference)                       │
│   ↓                                                                      │
│ Profile Matching (Cosine Similarity):                                   │
│   current_embedding = extract_embedding(audio_segment)  # 768-dim       │
│   similarities = []                                                     │
│   for profile in enrolled_profiles:                                     │
│       similarity = cosine_similarity(current_embedding, profile.embedding)│
│       similarities.append((profile.speaker_id, similarity))             │
│   ↓                                                                      │
│   best_match = max(similarities, key=lambda x: x[1])                    │
│   if best_match.similarity > 0.8:                                       │
│       speaker_id = best_match.speaker_id                                │
│       confidence = best_match.similarity                                │
│   else:                                                                  │
│       speaker_id = "Unknown"  # Guest or low-confidence match           │
│       confidence = best_match.similarity                                │
│   ↓                                                                      │
│ Output: {speaker_id: "Dad", confidence: 0.92, embedding: [...]}         │
└─────────────────────────────────────────────────────────────────────────┘
```

### **Model Selection: x-vector vs ECAPA-TDNN**

**Option 1: x-vector (Snyder et al. 2018)**
- **Architecture:** Time Delay Neural Network (TDNN) with statistics pooling
- **Embedding Size:** 512-dim (expandable to 768-dim)
- **Training Data:** VoxCeleb (>7,000 speakers, 1M+ utterances)
- **Accuracy:** 90-92% on NIST SRE benchmark
- **Latency:** ~30ms on CPU (ONNX optimized)
- **Model Size:** ~50MB

**Option 2: ECAPA-TDNN (Desplanques et al. 2020)**
- **Architecture:** Emphasized Channel Attention + TDNN
- **Embedding Size:** 192-dim, 512-dim, or 768-dim (configurable)
- **Training Data:** VoxCeleb + VoxCeleb2 (>1M utterances)
- **Accuracy:** 93-95% on NIST SRE benchmark
- **Latency:** ~40ms on CPU (ONNX optimized)
- **Model Size:** ~80MB

**Decision:** **ECAPA-TDNN 768-dim** (primary), **x-vector 512-dim** (fallback for low-resource devices)

**Rationale:**
- ECAPA-TDNN higher accuracy (93-95% vs 90-92%) → fewer misidentifications
- 768-dim embeddings → better separation in high-speaker-count families (5+ members)
- Channel attention mechanism → robust to background noise
- +10ms latency acceptable (40ms vs 30ms) for 3-5% accuracy gain

### **Enrollment Protocol**

**Enrollment Prompts (10-15 Sentences):**

```
# Phonetically diverse sentences covering English phonemes
enrollment_prompts = [
    "The quick brown fox jumps over the lazy dog",
    "I need help with my calendar and grocery list",
    "What's the weather forecast for this week?",
    "Please remind me to call Mom at three o'clock",
    "Turn on the living room lights and play some jazz music",
    "How long will it take to drive to the airport tomorrow morning?",
    "Show me recipes for chicken pasta with garlic and basil",
    "Cancel my two PM meeting and reschedule for Friday afternoon",
    "What time does the hardware store close on Saturday?",
    "Read me the latest news about technology and science",
    # ... 5 more sentences
]
```

**Enrollment Requirements:**

| **Parameter** | **Value** | **Rationale** |
|---------------|-----------|---------------|
| **Duration** | 30-60 seconds | 10-15 utterances needed for robust profile (balance enrollment friction vs accuracy) |
| **SNR** | >20dB | Quiet environment ensures clean training data (noisy enrollment → poor runtime matching) |
| **Microphone** | Same device family uses | Device-specific microphone characteristics affect embeddings |
| **Utterances** | 10-15 diverse sentences | Phonetic diversity ensures embedding captures full speaker characteristics |
| **Re-enrollment** | Optional every 6-12 months | Voice changes over time (aging, illness) → periodic updates improve accuracy |

**Adaptive Enrollment (Future Enhancement):**

```
# Incremental profile updates from high-confidence runtime matches
if runtime_confidence > 0.95:
    # Add current embedding to profile (running average)
    profile.embedding = (profile.embedding * profile.sample_count + current_embedding) / (profile.sample_count + 1)
    profile.sample_count += 1
    profile.last_updated = now()
```

### **Runtime Speaker Identification**

**Step 1: Voice Activity Detection (VAD)**

```python
# Webrtc VAD (fast, low-latency)
import webrtcvad

vad = webrtcvad.Vad(2)  # Aggressiveness level 0-3
frame_duration_ms = 30
sample_rate = 16000

for frame in audio_stream:
    is_speech = vad.is_speech(frame, sample_rate)
    if is_speech:
        speech_segments.append(frame)
```

**Step 2: Embedding Extraction**

```python
# ONNX Runtime for CPU inference (optimized)
import onnxruntime as ort

session = ort.InferenceSession("ecapa_tdnn_768.onnx")
input_name = session.get_inputs()[0].name

# Preprocess audio (resample, normalize)
audio_preprocessed = preprocess(audio_segment)  # 1-3 seconds

# Extract embedding
embedding = session.run(None, {input_name: audio_preprocessed})[0]  # 768-dim
```

**Step 3: Profile Matching (Cosine Similarity)**

```python
import numpy as np

def cosine_similarity(embedding_a, embedding_b):
    """Compute cosine similarity between two embeddings"""
    return np.dot(embedding_a, embedding_b) / (
        np.linalg.norm(embedding_a) * np.linalg.norm(embedding_b)
    )

# Match against enrolled profiles
enrolled_profiles = [
    {"speaker_id": "Dad", "embedding": dad_embedding},
    {"speaker_id": "Mom", "embedding": mom_embedding},
    {"speaker_id": "Child", "embedding": child_embedding}
]

current_embedding = extract_embedding(audio_segment)

similarities = []
for profile in enrolled_profiles:
    similarity = cosine_similarity(current_embedding, profile["embedding"])
    similarities.append((profile["speaker_id"], similarity))

# Best match
best_match = max(similarities, key=lambda x: x[1])
speaker_id, confidence = best_match

if confidence > 0.8:
    identified_speaker = speaker_id
else:
    identified_speaker = "Unknown"  # Guest or ambiguous
```

**Confidence Thresholds:**

| **Confidence** | **Action** | **Rationale** |
|----------------|------------|---------------|
| **≥0.9** | High confidence match | Proceed with speaker attribution, no confirmation |
| **0.8-0.9** | Medium confidence match | Proceed, but track for adaptive re-enrollment if repeated low scores |
| **0.6-0.8** | Low confidence match | Fallback to "Unknown", ask for explicit confirmation: "Are you Dad?" |
| **<0.6** | No match | Treat as guest speaker (restricted permissions) |

### **Privacy & Security**

**Voice Biometric Storage (K0 Driver):**

```python
# Encrypt embeddings at rest (AES-256-GCM per ADR-0036)
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import os

# Generate encryption key (derived from master key)
encryption_key = derive_key(master_key, "voice_profiles")
cipher = AESGCM(encryption_key)

# Encrypt embedding before storage
nonce = os.urandom(12)
embedding_bytes = embedding.tobytes()  # 768 floats → bytes
encrypted_embedding = cipher.encrypt(nonce, embedding_bytes, None)

# Store in K0
profile = {
    "speaker_id": "Dad",
    "voice_profile_id": "profile_001",
    "embedding_encrypted": encrypted_embedding,
    "nonce": nonce,
    "created_at": now()
}
k0_storage.write("voice_profiles", profile)
```

**Anti-Spoofing (Future Enhancement):**

```
# Liveness detection to prevent replay attacks
# Detect if audio is pre-recorded vs live speech
liveness_check = {
    "interactive_enrollment": True,  # Randomize prompts to prevent pre-recording
    "audio_artifacts": detect_compression_artifacts(audio),  # Detect MP3/AAC encoding
    "spectral_analysis": detect_replay_attack(audio)  # Analyze frequency patterns
}

if liveness_check["audio_artifacts"] or liveness_check["spectral_analysis"]:
    raise SecurityError("Potential voice spoofing detected")
```

### **Profile Drift Handling**

**Problem:** Voice changes over time due to:
- **Aging:** Vocal cords change (pitch drops, formants shift)
- **Illness:** Temporary voice changes (cold, sore throat)
- **Environmental:** Different microphones, background noise

**Solution: Adaptive Profile Updates**

```python
# Track confidence scores over time
speaker_history = {
    "Dad": {
        "recent_confidences": [0.92, 0.91, 0.88, 0.85, 0.82],  # Last 5 identifications
        "rolling_average": 0.876,
        "drift_detected": False
    }
}

# Detect drift (confidence trending down)
if speaker_history["Dad"]["rolling_average"] < 0.85:
    speaker_history["Dad"]["drift_detected"] = True

    # Proactive re-enrollment prompt
    system_prompt = "Your voice sounds a bit different recently. Would you like to update your voice profile for better recognition?"
```

### **Performance Budget**

| **Operation** | **Target (P95)** | **Implementation** |
|---------------|------------------|-------------------|
| **VAD** | <10ms | webrtcvad (optimized C library) |
| **Audio Preprocessing** | <20ms | NumPy operations (resample, normalize) |
| **Embedding Extraction** | <50ms | ONNX Runtime on CPU (ECAPA-TDNN 768-dim) |
| **Profile Matching** | <10ms | Cosine similarity (10 profiles max, vectorized) |
| **Total Speaker ID** | **<100ms** | Sum of above stages |

**Justification:** 100ms speaker ID latency is acceptable because:
1. Runs in parallel with ASR transcription (doesn't block speech-to-text)
2. Multi-party conversations typically have natural pauses (200-500ms between speakers)
3. User doesn't perceive <100ms delays in voice interactions

---

## Consequences

### **Positive**

1. **Voice-First UX:** No manual speaker selection, hands-free operation
2. **Privacy-Preserving:** Biometrics encrypted at rest (ADR-0036), no cloud storage required
3. **Robust to Noise:** ECAPA-TDNN channel attention handles background noise well
4. **Low Latency:** <100ms speaker ID doesn't block conversational flow
5. **Scalable:** Supports 10+ family members + guests (O(n) profile matching)

### **Negative**

1. **Enrollment Friction:** 30-60 second setup per family member (one-time burden)
2. **Accuracy Limitations:** 93-95% accuracy → 5-7% misidentification rate (mitigated by confidence thresholds)
3. **Voice Drift:** Profiles may degrade over time (requires periodic re-enrollment)
4. **Compute Cost:** ONNX inference ~40ms CPU time per utterance (acceptable for <5 concurrent speakers)
5. **Privacy Risk:** Voice biometrics are sensitive data (mitigated by encryption + access controls)

### **Risks & Mitigations**

| **Risk** | **Impact** | **Mitigation** |
|----------|------------|----------------|
| Voice spoofing (replay attack) | HIGH | Future: Liveness detection, interactive enrollment |
| Profile theft (embedding leaked) | HIGH | Encrypt embeddings (AES-256-GCM), restrict K0 port access |
| Misidentification (Dad → Mom) | MEDIUM | Confidence threshold >0.8, fallback to "Unknown" if ambiguous |
| Profile drift (accuracy degrades) | MEDIUM | Track confidence trends, proactive re-enrollment prompts |
| Child voice changes (puberty) | LOW | Re-enroll every 6-12 months for children <18 years old |

---

## Implementation Guidance

### **ONNX Model Integration**

```python
# Download pre-trained ECAPA-TDNN model from Hugging Face
# https://huggingface.co/speechbrain/spkrec-ecapa-voxceleb
import onnxruntime as ort

# Convert to ONNX (if using PyTorch checkpoint)
# torch.onnx.export(model, dummy_input, "ecapa_tdnn_768.onnx")

# Load ONNX model
session = ort.InferenceSession(
    "ecapa_tdnn_768.onnx",
    providers=["CPUExecutionProvider"]  # CPU inference (no GPU required)
)

# Inference
input_name = session.get_inputs()[0].name
embedding = session.run(None, {input_name: audio_tensor})[0]
```

### **K0 Storage Schema**

```sql
-- Voice profiles table
CREATE TABLE voice_profiles (
    voice_profile_id TEXT PRIMARY KEY,
    speaker_id TEXT NOT NULL,
    embedding_encrypted BLOB NOT NULL,  -- AES-256-GCM encrypted 768-dim float array
    nonce BLOB NOT NULL,  -- 12-byte nonce for AESGCM
    created_at INTEGER NOT NULL,
    sample_count INTEGER DEFAULT 1,
    enrollment_snr_db REAL,
    last_updated INTEGER,
    UNIQUE(speaker_id)
);

-- Speaker identification log (for drift detection)
CREATE TABLE speaker_identifications (
    identification_id TEXT PRIMARY KEY,
    voice_profile_id TEXT,
    confidence REAL NOT NULL,
    identified_at INTEGER NOT NULL,
    audio_snr_db REAL,
    FOREIGN KEY (voice_profile_id) REFERENCES voice_profiles(voice_profile_id)
);
```

### **Metrics & Observability**

```python
# Prometheus metrics
from prometheus_client import Histogram, Counter, Gauge

speaker_id_latency_ms = Histogram(
    'speaker_identification_latency_ms',
    'Speaker diarization latency',
    buckets=[10, 25, 50, 75, 100, 150]
)

speaker_id_confidence = Histogram(
    'speaker_identification_confidence',
    'Speaker match confidence score',
    buckets=[0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.95, 1.0]
)

unknown_speaker_total = Counter(
    'unknown_speaker_detections_total',
    'Total unknown speaker detections (guests)'
)

profile_drift_alerts = Counter(
    'profile_drift_alerts_total',
    'Profile drift detected (re-enrollment needed)',
    ['speaker_id']
)
```

---

## References

### **Research Papers**

1. **Snyder et al. (2018):** "X-vectors: Robust DNN Embeddings for Speaker Recognition" - Johns Hopkins University
2. **Desplanques et al. (2020):** "ECAPA-TDNN: Emphasized Channel Attention, Propagation and Aggregation in TDNN Based Speaker Verification" - Ghent University
3. **Bredin et al. (2020):** "pyannote.audio: Neural Building Blocks for Speaker Diarization" - CNRS/IRIT
4. **Nagrani et al. (2017):** "VoxCeleb: A Large-Scale Speaker Identification Dataset" - University of Oxford

### **Pre-Trained Models**

- **SpeechBrain ECAPA-TDNN:** https://huggingface.co/speechbrain/spkrec-ecapa-voxceleb
- **NVIDIA NeMo Speaker Diarization:** https://github.com/NVIDIA/NeMo
- **pyannote.audio:** https://github.com/pyannote/pyannote-audio

### **Datasets**

- **VoxCeleb1:** 7,000+ speakers, 1M+ utterances
- **VoxCeleb2:** 6,000+ speakers, 1M+ utterances
- **NIST SRE:** Speaker Recognition Evaluation benchmarks

---

## Changelog

- **2025-10-22:** Initial proposal for Speaker Diarization & Voice Biometrics (Sub-ADR of ADR-0082)

---

**Next Steps:**

1. **Model Selection:** Benchmark x-vector vs ECAPA-TDNN on VoxCeleb test set (1 week)
2. **ONNX Conversion:** Convert PyTorch checkpoints to ONNX for CPU inference (3 days)
3. **Enrollment Flow:** Implement voice profile creation UI (1 week)
4. **K0 Integration:** Create voice profiles storage driver (1 week)
5. **Performance Tuning:** Optimize ONNX inference to <50ms P95 (1 week)