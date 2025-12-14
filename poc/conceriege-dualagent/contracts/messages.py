"""
Message Contracts for Handoff Space Communication
"""

from enum import Enum
from typing import Any, Dict

from pydantic import BaseModel


class MessageType(str, Enum):
    """Types of messages in handoff space"""

    JOB_REQUEST = "job.request"
    JOB_CLARIFICATION = "job.clarification"
    JOB_CLARIFICATION_RESPONSE = "job.clarification_response"
    JOB_PROGRESS = "job.progress"
    JOB_RESULT = "job.result"


class JobRequest(BaseModel):
    """Initial job request from Reactive to Specialist"""

    thread_id: str
    specialist_name: str
    query: str
    context: Dict[str, Any]


class JobClarification(BaseModel):
    """Clarification request from Specialist to Proactive"""

    thread_id: str
    specialist_name: str
    question: str
    clarification_round: int


class JobClarificationResponse(BaseModel):
    """User response to clarification question"""

    thread_id: str
    specialist_name: str
    answer: str
    clarification_round: int


class JobProgress(BaseModel):
    """Progress update from Specialist"""

    thread_id: str
    specialist_name: str
    status: str
    message: str


class JobResult(BaseModel):
    """Final result from Specialist to Reactive"""

    thread_id: str
    specialist_name: str
    findings: str
    confidence: float
    sources: list[str]
