"""
Temporal Module - Time-based scheduling and proactive triggers

Purpose:
- Manages time-based triggers (reminders, schedules)
- Provides temporal context to agents
- Runs background scheduler for trigger evaluation
- Mimics K0 P05 Prospective Memory for PoC

Exports:
- TriggerType: Enum of trigger types
- Trigger: Trigger data model
- TemporalModule: Scheduler and trigger execution
- get_temporal_module: Singleton factory
- TriggerManager: CRUD operations for triggers
"""

from l5_infrastructure.temporal.temporal_module import (
    TemporalModule,
    Trigger,
    TriggerType,
    get_temporal_module,
)
from l5_infrastructure.temporal.trigger_manager import TriggerManager

__all__ = ["TriggerType", "Trigger", "TemporalModule", "get_temporal_module", "TriggerManager"]
