"""
Admission Control Module - Gateway Layer for Task Admission

Layer: L5 Infrastructure
Component: Admission Control
Priority: P2 (Flow Control)
Status: 🚧 STUB - NEEDS_IMPLEMENTATION

This module provides admission control functionality for K1 Intelligence Module,
including admission decision logic, schema validation, rate limiting integration,
and backpressure-aware task acceptance.

Architecture Decision Records:
    - ADR-0032: Admission Control Design
    - ADR-0002c: Actor Router & Admission Control (pattern reference)
    - ADR-0028: Backpressure Cascade System (integration)
    - ADR-0030: Rate Limiting Strategy (quota checks)
    - ADR-0031: Task Scheduling Strategy (queue integration)

Modules:
    - admission_controller: Core admission decision engine
    - task_validator: Schema validation and request type checking

Key Classes:
    - AdmissionController: Core admission decision engine
    - TaskValidator: Schema validation for task requests
    - AdmissionDecision: Admission decision states enum
    - Request: Incoming task request structure
    - ValidationResult: Validation result structure

Performance Budgets:
    - Admission decision: <10ms P95
    - Task validation: <2ms P95
    - Overall admission pipeline: <12ms P95

Usage:
    >>> from k1.l5_infrastructure.admission import AdmissionController, TaskValidator
    >>> from k1.l5_infrastructure.admission import Request, TaskPriority, PrivacyBand
    >>>
    >>> # Initialize components
    >>> controller = AdmissionController()
    >>> await controller.initialize()
    >>>
    >>> # Create request
    >>> request = Request(
    ...     request_id='req_123',
    ...     task_type='inference',
    ...     priority=TaskPriority.NORMAL,
    ...     privacy_band=PrivacyBand.GREEN,
    ...     user_id='user_456',
    ...     tenant_id='tenant_789',
    ...     payload={'model_id': 'llama7b', 'input_data': {'text': 'Hello'}},
    ...     cognitive_trace_id='trace_abc',
    ... )
    >>>
    >>> # Admit request
    >>> result = await controller.admit(request)
    >>> if result.decision == AdmissionDecision.ADMITTED:
    ...     # Enqueue to scheduler
    ...     pass
    >>>
    >>> await controller.shutdown()

References:
    - Diagram: architecture_diagrams/k1/k1_admission_control.mmd
    - Whiteboard: docs/whiteboard.md (Section 7: Flow Control)
    - Tests: tests/k1/l5_infrastructure/admission/
"""

# =============================================================================
# MODULE EXPORTS
# =============================================================================

from k1.l5_infrastructure.admission.admission_controller import (
    AdmissionController, AdmissionDecision, AdmissionMetrics, AdmissionResult,
    AdmissionStatus, BackpressureLevel, PrivacyBand, Request, TaskPriority,
    initialize_admission_controller)
from k1.l5_infrastructure.admission.task_validator import (
    TaskSchema, TaskValidator, ValidationMetrics, ValidationResult,
    ValidationStatus, initialize_task_validator)

__all__ = [
    # Admission Controller
    'AdmissionController',
    'AdmissionDecision',
    'AdmissionResult',
    'AdmissionStatus',
    'AdmissionMetrics',
    'Request',
    'TaskPriority',
    'PrivacyBand',
    'BackpressureLevel',
    'initialize_admission_controller',

    # Task Validator
    'TaskValidator',
    'ValidationStatus',
    'ValidationResult',
    'ValidationMetrics',
    'TaskSchema',
    'initialize_task_validator',
]

# Module version
__version__ = '0.1.0'

# Module metadata
__author__ = 'K1 Platform Team'
__description__ = 'Admission Control Module - Gateway Layer for Task Admission'
__status__ = 'STUB'
