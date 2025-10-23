"""
Automatic Speech Recognition (ASR) Operator

ADR References:
- ADR-0004: Layer 1 architecture, operator pipeline
- ADR-0024: Performance budgets (ASR <80ms P95)
- ADR-0027: Model placement cascade (on-device ASR models)
- ADR-0056a: ASR Ingress (frame handling, partial results)

Purpose:
Converts audio to text using on-device ASR models with <80ms P95 latency.
Implements model placement cascade (on-device first, remote fallback).

Performance Budget:
- ASR latency: <80ms P95 (on-device model)
- Frame handling: 20ms audio frames
- Partial results streaming: <50ms
- Model: Whisper (on-device) or remote API

Components:
- 20ms frame buffering and processing
- VAD integration for speech segmentation
- Partial transcript streaming (is_partial flag)
- On-device model inference (Whisper)
- Remote API fallback

Key Responsibilities:
1. Buffer 20ms audio frames (ADR-0056a)
2. Run ASR inference (<80ms P95)
3. Emit partial transcripts for typing indicator UX (ADR-0065a)
4. Emit final transcript on turn boundary (2s silence from VAD)
5. Use on-device model first, fallback to remote (ADR-0027)

Integration Points:
- VAD Operator: Speech start/stop triggers
- WebSocket: Receive audio frames (ADR-0015)
- EventBus: Publish ASRResult events (ADR-0004a)
- Model Hub: On-device/remote model selection (ADR-0001b)

Contracts to Review:
- contracts/flatbuffers/asr_result.fbs
- contracts/flatbuffers/audio_frame.fbs
- k0/contracts/pipelines/p11_asr.yml
"""

# TODO: Implement 20ms frame buffering (80ms ring buffer)
# TODO: Implement VAD integration for segmentation
# TODO: Implement on-device Whisper inference (<80ms)
# TODO: Implement partial transcript streaming (ADR-0056a)
# TODO: Implement remote API fallback (ADR-0027)
# TODO: Emit ASRResult events to EventBus
# TODO: Add Prometheus metrics (asr_latency_ms histogram) (ADR-0029)
