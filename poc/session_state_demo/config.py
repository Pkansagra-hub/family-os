"""
Session State Demo Configuration
================================

Configuration for the session state demo using Google AI.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Load environment variables from multiple locations
load_dotenv(Path(__file__).parent.parent.parent / ".env")
load_dotenv(Path(__file__).parent.parent / "chat_experience_poc" / ".env")


@dataclass
class DemoConfig:
    """Configuration for the session state demo."""

    # LLM Settings
    llm_provider: str = "google"
    google_api_key: Optional[str] = None
    google_model: str = "gemini-2.5-pro-preview-05-06"

    # Session Settings
    session_id: str = "demo-session-001"
    db_path: Path = field(
        default_factory=lambda: Path.home() / ".familyos" / "demo" / "session_demo.db"
    )

    # Display Settings
    show_state_changes: bool = True
    show_tool_calls: bool = True
    colorized_output: bool = True

    # Demo Mode
    guided_mode: bool = False  # Step-by-step explanations

    def __post_init__(self) -> None:
        """Load from environment after init."""
        self.google_api_key = self.google_api_key or os.getenv("GOOGLE_API_KEY")
        self.google_model = os.getenv("GOOGLE_MODEL", self.google_model)

        if not self.google_api_key:
            raise ValueError(
                "GOOGLE_API_KEY not set. Add to .env file or set environment variable."
            )


def get_config() -> DemoConfig:
    """Get demo configuration with environment overrides."""
    return DemoConfig()
