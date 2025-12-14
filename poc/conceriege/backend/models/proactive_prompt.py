"""
Proactive Prompt Model

Represents proactive prompts generated during background specialist work to maintain
conversation flow.

Research basis:
- Mixed-Initiative Dialogue (Allen 1999, Horvitz 1999)
- Proactive Dialogue Systems (Yang 2018, Sun 2021)
- Reactive-Proactive Loop (Novel pattern - our contribution)
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Optional


@dataclass
class ProactivePrompt:
    """
    Proactive prompt generated to fill conversation gaps during background work.

    This is a key component of the novel Reactive-Proactive Loop pattern.

    Fields:
        text: The proactive prompt text
        prompt_type: Strategy used - fill_gap, future_action, or clarify
        information_target: What information we're trying to gather
        sent_at: When this prompt was sent
        user_responded: Whether user responded to this prompt
        response_text: User's response text (if responded)

    Examples:
        >>> prompt = ProactivePrompt(
        ...     text="Until nutritionist gathers data, tell me how uneasy it was?",
        ...     prompt_type="fill_gap",
        ...     information_target="pain_severity"
        ... )
        >>> prompt.mark_responded("pain in left side")
        >>> prompt.user_responded
        True
    """

    text: str
    prompt_type: Literal["fill_gap", "future_action", "clarify"]
    information_target: str
    sent_at: datetime = field(default_factory=datetime.utcnow)
    user_responded: bool = False
    response_text: Optional[str] = None

    def to_dict(self) -> dict:
        """
        Convert to dictionary for JSON serialization.

        Returns:
            Dictionary representation of ProactivePrompt
        """
        return {
            "text": self.text,
            "prompt_type": self.prompt_type,
            "information_target": self.information_target,
            "sent_at": self.sent_at.isoformat(),
            "user_responded": self.user_responded,
            "response_text": self.response_text,
        }

    def mark_responded(self, response_text: str):
        """
        Mark this prompt as responded to by user.

        Args:
            response_text: User's response text
        """
        self.user_responded = True
        self.response_text = response_text
