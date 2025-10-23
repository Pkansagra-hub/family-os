"""
K1 L4 Ingress — Voice Pipeline

**Purpose:** 5-stage voice pipeline (Audio→ASR→Intent→Tools→TTS→Audio) with backpressure, barge-in

**Components:**
- asr_ingress/ — ASR integration, 20ms frames, VAD, partial results
- intent_bridge/ — K1 orchestrator integration, intent classification
- tool_interleaving/ — Tool execution during voice output
- tts_synthesis/ — TTS streaming, prosody controls, SSML
- audio_output/ — Jitter buffer 80ms, packet loss recovery
- backpressure/ — Frame drop (2-tier), TTS degradation (5-level ladder)
- barge_in/ — Fast stop <120ms, context preservation

**Performance:**
- E2E voice turn: <500ms P95
- ASR latency: <100ms
- TTS latency: <200ms
- Barge-in stop: <120ms P95

**ADRs (10 total):** ADR-0056 to 0056e (Voice Pipeline), ADR-0057a to 0057c (Voice Backpressure),
ADR-0068 (Voice Quality)

**Last Updated:** October 2025
"""

__version__ = "0.1.0"

# TODO: Implement asr_ingress/, intent_bridge/, tool_interleaving/, tts_synthesis/, audio_output/, backpressure/, barge_in/
