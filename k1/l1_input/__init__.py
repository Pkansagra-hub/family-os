"""Layer 1: Input Processing

Multi-modal input perception and intent routing.

Performance Budget: <10ms P95

Modules:
- streams/stream_switch: Unified multi-modal input bus
- streams/operators: Stream transformations (VAD, ASR, TTS, vision)
- orchestration/intent_router: 3-tier intent classification
- orchestration/meta_policy: Proactivity & clarification engines
"""
