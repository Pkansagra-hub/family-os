"""
Core Modules - Fundamental Storage and Event Operations

This package contains core modules for:
- hipp_events_writer (M16): Write enriched events to st_hipp_events
- event_emitter (M17): Emit completion events to bus
- Additional core storage operations

All modules follow Phase 2 declarative architecture:
- Pure functions (async def run)
- No direct storage access
- Use syscalls for capability-gated operations
"""
