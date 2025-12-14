"""
Mailbox System (MPSC with 4 Priority Levels)

Actor Model mailbox implementation for inter-agent communication.

Components:
- mailbox.py: Message model, Priority enum, Mailbox class (MPSC queues with WFQ)
- mailbox_manager.py: MailboxManager singleton (routing, broadcasting, metrics)

Related ADRs:
- ADR-0002a: Mailbox MPSC Queue Implementation
- ADR-0005: Agent Lifecycle FSM
"""

from .mailbox import Mailbox, Message, Priority
from .mailbox_manager import MailboxManager

__all__ = [
    "Mailbox",
    "Message",
    "Priority",
    "MailboxManager",
]
