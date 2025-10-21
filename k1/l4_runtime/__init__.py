"""Layer 4: Runtime Core

State management, flow execution, learning loop.

Performance Budget: SessionState serialize <1ms P95

Module Categories:
- runtime/: Core runtime (4 modules) - Leases, mailbox, session_state, flow_engine
- learning/: Learning loop (4 modules) - Adaptive learning, feedback, drift detection
"""
