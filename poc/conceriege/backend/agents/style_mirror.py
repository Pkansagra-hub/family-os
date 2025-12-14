"""
Style Mirror - User Communication Style Analysis & Mirroring

TOPIC 9: MICRO-PERSONALIZATION

This module analyzes user communication style and enables the agent to mirror it
back, creating stronger rapport through style matching.

Key Features:
- Detects emoji frequency and patterns
- Analyzes punctuation style (!!!, ..., ???)
- Estimates formality level (casual vs formal)
- Measures energy level (low, medium, high)
- Generates style-matched response instructions

UPGRADE #6: Style Memory Persistence
- Save/load style profiles to disk
- Track style evolution over sessions
- Persist preferences across conversations

Rule-based analysis for fast, deterministic results.
"""

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal, Optional


@dataclass
class UserStyle:
    """Detected user communication style"""

    emoji_frequency: float  # emojis per message (0.0-1.0)
    exclamation_use: bool  # uses !!, !!!
    ellipsis_use: bool  # uses ...
    question_style: Literal["simple", "multiple"]  # ?, ??, ???
    formality: Literal["casual", "neutral", "formal"]  # language level
    energy_level: Literal["low", "medium", "high"]  # enthusiasm level


class StyleMirror:
    """
    RULE-BASED style analysis and mirroring engine.

    Analyzes user communication patterns and generates instructions
    for LLM to mirror back the user's style naturally.
    """

    def __init__(self):
        """Initialize style mirror"""
        # Casual language markers
        self.casual_markers = [
            "btw",
            "gonna",
            "wanna",
            "yeah",
            "yep",
            "nah",
            "lol",
            "haha",
            "omg",
            "ur",
            "u",
            "imo",
            "tbh",
            "imo",
        ]

        # Formal language markers
        self.formal_markers = [
            "however",
            "therefore",
            "regarding",
            "please",
            "kindly",
            "accordingly",
            "furthermore",
            "consequently",
            "shall",
            "previously",
        ]

        # Emoji categories for detection
        self.emoji_pattern = re.compile(
            "["
            "\U0001f600-\U0001f64f"  # emoticons
            "\U0001f300-\U0001f5ff"  # symbols & pictographs
            "\U0001f680-\U0001f6ff"  # transport & map symbols
            "\U0001f1e0-\U0001f1ff"  # flags (iOS)
            "\U00002702-\U000027b0"
            "\U000024c2-\U0001f251"
            "\U0001f926-\U0001f937"
            "\U00010000-\U0010ffff"
            "\u2640-\u2642"
            "\u2600-\u2b55"
            "\u200d"
            "\u23cf"
            "\u23e9"
            "\u231a"
            "\ufe0f"  # dingbats
            "\u3030"
            "]+"
        )

    def analyze_style(self, message: str) -> UserStyle:
        """
        Analyze user message style using RULE-BASED heuristics.

        FAST: <5ms, no LLM calls

        Args:
            message: User message to analyze

        Returns:
            UserStyle with detected patterns
        """

        # Emoji detection
        emoji_matches = self.emoji_pattern.findall(message)
        emoji_count = len(emoji_matches)
        emoji_frequency = min(emoji_count / max(len(message.split()), 1), 1.0)

        # Punctuation patterns
        exclamation_use = "!!" in message or "!!!" in message
        ellipsis_use = "..." in message
        question_style = "multiple" if "??" in message or "???" in message else "simple"

        # Formality detection (stricter matching with word boundaries)
        message_lower = message.lower()
        casual_count = sum(
            1
            for m in self.casual_markers
            if f" {m} " in f" {message_lower} "
            or message_lower.startswith(m)
            or message_lower.endswith(m)
        )
        formal_count = sum(
            1
            for m in self.formal_markers
            if f" {m} " in f" {message_lower} "
            or message_lower.startswith(m)
            or message_lower.endswith(m)
        )

        if casual_count > 0 and formal_count == 0:
            formality = "casual"
        elif formal_count > 0 and casual_count == 0:
            formality = "formal"
        else:
            formality = "neutral"

        # Energy level (based on caps, emojis, exclamation)
        caps_ratio = sum(1 for c in message if c.isupper()) / max(len(message), 1)
        exclamation_weight = 0.3 if exclamation_use else 0
        energy_score = emoji_frequency + exclamation_weight + (caps_ratio * 0.5)

        if energy_score > 0.2:
            energy_level = "high"
        elif energy_score > 0.05:
            energy_level = "medium"
        else:
            energy_level = "low"

        return UserStyle(
            emoji_frequency=emoji_frequency,
            exclamation_use=exclamation_use,
            ellipsis_use=ellipsis_use,
            question_style=question_style,
            formality=formality,
            energy_level=energy_level,
        )

    def get_style_instructions(self, style: UserStyle) -> str:
        """
        Generate LLM prompt instructions to mirror user style.

        Args:
            style: UserStyle from analyze_style()

        Returns:
            String with style mirroring instructions for LLM
        """

        instructions = ["TOPIC 9: MICRO-PERSONALIZATION - MATCH USER STYLE"]

        # Emoji guidance
        if style.emoji_frequency > 0.1:
            instructions.append("- Use emojis occasionally (1-2 per response)")
        else:
            instructions.append("- Minimal or no emojis")

        # Punctuation guidance
        if style.exclamation_use:
            instructions.append("- Can use ! or !! for emphasis")
        if style.ellipsis_use:
            instructions.append("- Can use ... for pauses or trailing thoughts")

        # Question style guidance
        if style.question_style == "multiple":
            instructions.append("- Can use multiple question marks (??)")

        # Formality guidance
        if style.formality == "casual":
            instructions.append("- Stay very casual: use 'gonna', 'btw', 'yeah', contractions")
            instructions.append("- Avoid formal language")
        elif style.formality == "formal":
            instructions.append("- Be slightly more formal and structured")
            instructions.append("- Use complete sentences and proper grammar")
        else:
            instructions.append("- Use conversational but clear language")

        # Energy guidance
        if style.energy_level == "high":
            instructions.append("- Match enthusiasm: be warm and engaged")
            instructions.append("- Use upbeat language")
        elif style.energy_level == "low":
            instructions.append("- Keep tone calm and gentle")
            instructions.append("- Avoid excessive enthusiasm")
        else:
            instructions.append("- Maintain balanced, friendly energy")

        # Summary rule
        instructions.append("")
        instructions.append(
            "MATCHING PRIORITY: Adapt your response to mirror this user's communication style naturally."
        )

        return "\n".join(instructions)

    def should_use_emoji(self, style: UserStyle) -> bool:
        """Check if emojis should be used"""
        return style.emoji_frequency > 0.05

    def should_use_exclamation(self, style: UserStyle) -> bool:
        """Check if exclamation marks should be used"""
        return style.exclamation_use

    def should_use_ellipsis(self, style: UserStyle) -> bool:
        """Check if ellipsis should be used"""
        return style.ellipsis_use

    def get_formality_tone(self, style: UserStyle) -> str:
        """Get formality-appropriate tone"""
        if style.formality == "casual":
            return "conversational, casual, friendly"
        elif style.formality == "formal":
            return "professional, structured, clear"
        else:
            return "balanced, natural, accessible"

    def get_energy_descriptor(self, style: UserStyle) -> str:
        """Get energy-level descriptor"""
        if style.energy_level == "high":
            return "enthusiastic, engaged, upbeat"
        elif style.energy_level == "low":
            return "calm, thoughtful, gentle"
        else:
            return "warm, friendly, balanced"

    # ========================================================================
    # UPGRADE #6: Style Memory Persistence
    # ========================================================================

    def save_style(self, user_id: str, style: UserStyle, filepath: str = "./data/styles/") -> bool:
        """
        Save user style profile to disk for persistence across sessions.

        Args:
            user_id: Unique user identifier
            style: UserStyle object to persist
            filepath: Directory path for storing style profiles

        Returns:
            True if save successful, False otherwise

        File Format:
            {filepath}/{user_id}_style.json
        """
        try:
            # Create directory if it doesn't exist
            Path(filepath).mkdir(parents=True, exist_ok=True)

            # Convert UserStyle to dict
            style_dict = asdict(style)

            # Save to JSON file
            file_path = Path(filepath) / f"{user_id}_style.json"
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(style_dict, f, indent=2)

            return True

        except Exception as e:
            print(f"Error saving style for user {user_id}: {e}")
            return False

    def load_style(self, user_id: str, filepath: str = "./data/styles/") -> Optional[UserStyle]:
        """
        Load user style profile from disk.

        Args:
            user_id: Unique user identifier
            filepath: Directory path where style profiles are stored

        Returns:
            UserStyle object if found, None otherwise

        File Format:
            {filepath}/{user_id}_style.json
        """
        try:
            file_path = Path(filepath) / f"{user_id}_style.json"

            # Check if file exists
            if not file_path.exists():
                return None

            # Load from JSON file
            with open(file_path, "r", encoding="utf-8") as f:
                style_dict = json.load(f)

            # Convert dict to UserStyle
            style = UserStyle(**style_dict)
            return style

        except Exception as e:
            print(f"Error loading style for user {user_id}: {e}")
            return None
