"""
Session State Demo - Main Entry Point
======================================

EPIC: 3 - CLI Interactive Demo
ISSUES: 3.1, 3.2, 3.3

Interactive CLI demonstrating K1 SessionState with real LLM integration.

Usage:
    python -m poc.session_state_demo.demo

Features:
- Real conversation with Google Gemini
- Automatic turn recording to session state
- LLM tool calling for persona/emotion updates
- Checkpoint/crash/restore demonstration
- State inspection commands
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from poc.session_state_demo.bridge import SessionLLMBridge  # noqa: E402
from poc.session_state_demo.config import DemoConfig, get_config  # noqa: E402
from poc.session_state_demo.display import (  # noqa: E402
    print_assistant_message,
    print_command_result,
    print_error,
    print_help,
    print_info,
    print_section_data,
    print_snapshot,
    print_state_change,
    print_stats,
    print_tool_call,
    print_user_message,
    print_warning,
    print_welcome,
)
from poc.session_state_demo.tools import SESSIONSTATE_TOOLS, parse_tool_call  # noqa: E402

# =============================================================================
# LLM CLIENT WRAPPER
# =============================================================================


class LLMClient:
    """Wrapper for Google AI client with tool calling support."""

    def __init__(self, config: DemoConfig):
        """Initialize LLM client."""
        self.config = config
        self._client = None

    def _get_client(self):
        """Lazy load the Google client."""
        if self._client is None:
            from poc.session_state_demo.llm_client import SimpleLLMClient

            self._client = SimpleLLMClient(
                api_key=self.config.google_api_key,
                model=self.config.google_model,
            )
        return self._client

    async def complete_with_tools(
        self,
        system_prompt: str,
        messages: List[Dict[str, str]],
        tools: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Get LLM completion with tool calling support.

        Args:
            system_prompt: System prompt for context
            messages: Conversation history
            tools: Tool definitions

        Returns:
            Dict with 'content' and/or 'tool_calls'
        """
        client = self._get_client()

        try:
            result = await client.complete_with_tools(
                system_prompt=system_prompt,
                messages=messages,
                tools=tools,
            )
            return result
        except Exception as e:
            return {"content": f"Error calling LLM: {e}", "tool_calls": []}

    async def complete(
        self,
        system_prompt: str,
        messages: List[Dict[str, str]],
    ) -> str:
        """
        Get simple LLM completion without tools.

        Args:
            system_prompt: System prompt
            messages: Conversation history

        Returns:
            Response text
        """
        client = self._get_client()

        try:
            result = await client.complete(
                system_prompt=system_prompt,
                messages=messages,
            )
            return result
        except Exception as e:
            return f"Error calling LLM: {e}"


# =============================================================================
# DEMO CONTROLLER
# =============================================================================


class DemoController:
    """Main controller for the interactive demo."""

    def __init__(self, config: DemoConfig):
        """Initialize demo controller."""
        self.config = config
        self.bridge: Optional[SessionLLMBridge] = None
        self.llm: Optional[LLMClient] = None
        self._running = False

    def start(self) -> None:
        """Start the demo session."""
        # Create database directory
        self.config.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Initialize bridge
        self.bridge = SessionLLMBridge(
            session_id=self.config.session_id,
            db_path=str(self.config.db_path),
            restore_on_start=True,
        )

        # Start session
        success, message = self.bridge.start()
        if success:
            print_info(message)
        else:
            print_warning(message)

        # Initialize LLM client
        self.llm = LLMClient(self.config)

        self._running = True

    def stop(self) -> None:
        """Stop the demo session."""
        if self.bridge and self.bridge.is_running:
            success, message = self.bridge.stop(checkpoint_before_stop=True)
            print_info(message)
        self._running = False

    async def process_input(self, user_input: str) -> bool:
        """
        Process user input.

        Args:
            user_input: Raw user input

        Returns:
            True to continue, False to exit
        """
        user_input = user_input.strip()

        if not user_input:
            return True

        # Check for commands
        if user_input.startswith("/"):
            return await self._handle_command(user_input)

        # Regular chat message
        await self._handle_chat(user_input)
        return True

    async def _handle_command(self, command: str) -> bool:
        """Handle a / command."""
        cmd = command.lower().split()[0]

        if cmd == "/quit" or cmd == "/exit":
            return False

        elif cmd == "/help":
            print_help()

        elif cmd == "/state":
            if self.bridge:
                snapshot = self.bridge.get_snapshot()
                print_snapshot(snapshot)

        elif cmd == "/history":
            if self.bridge:
                data = self.bridge.get_section_data("history_active")
                print_section_data("history_active", data)

        elif cmd == "/persona":
            if self.bridge:
                data = self.bridge.get_section_data("persona")
                print_section_data("persona", data)

        elif cmd == "/emotion":
            if self.bridge:
                data = self.bridge.get_section_data("affective_now")
                print_section_data("affective_now", data)

        elif cmd == "/stats":
            if self.bridge:
                stats = self.bridge.get_stats()
                print_stats(stats)

        elif cmd == "/checkpoint":
            if self.bridge:
                success, message, bytes_saved = self.bridge.checkpoint()
                print_command_result(f"{message} ({bytes_saved:,} bytes)", success)

        elif cmd == "/crash":
            if self.bridge:
                message = self.bridge.crash_simulate()
                print_warning(message)
                print_info("Use /restore to recover from the last checkpoint")

        elif cmd == "/restore":
            if self.bridge:
                # Recreate bridge for restore
                self.bridge = SessionLLMBridge(
                    session_id=self.config.session_id,
                    db_path=str(self.config.db_path),
                    restore_on_start=True,
                )
                success, message = self.bridge.start()
                print_command_result(message, success)

        else:
            print_error(f"Unknown command: {command}")
            print_help()

        return True

    async def _handle_chat(self, user_message: str) -> None:
        """Handle a chat message."""
        if not self.bridge or not self.llm:
            print_error("Session not initialized")
            return

        # Print user message
        print_user_message(user_message)

        # Record user turn
        changes = self.bridge.record_user_turn(user_message)
        if self.config.show_state_changes:
            for change in changes:
                print_state_change(
                    change.section,
                    change.operation,
                    change.description,
                    auto=change.auto,
                    success=change.success,
                )

        # Build LLM context
        context = self.bridge.build_llm_context()

        # Add current user message to history for LLM
        messages = context["messages"].copy()
        messages.append({"role": "user", "content": user_message})

        # Call LLM with tools
        start_time = time.time()
        response = await self.llm.complete_with_tools(
            system_prompt=context["system_prompt"],
            messages=messages,
            tools=SESSIONSTATE_TOOLS,
        )
        duration_ms = int((time.time() - start_time) * 1000)

        # Process tool calls if any
        tool_calls = parse_tool_call(response)
        had_tool_call = len(tool_calls) > 0

        if tool_calls and self.config.show_tool_calls:
            for call in tool_calls:
                print_tool_call(call["name"], call["args"])

            # Execute tool calls
            tool_changes = self.bridge.execute_tool_calls(tool_calls)
            if self.config.show_state_changes:
                for change in tool_changes:
                    print_state_change(
                        change.section,
                        change.operation,
                        change.description,
                        auto=change.auto,
                        success=change.success,
                    )

        # Get response content
        content = response.get("content", "")
        if not content:
            content = "I've noted that information."

        # Print assistant response
        print_assistant_message(content)

        # Record assistant turn
        changes = self.bridge.record_assistant_turn(
            content=content,
            duration_ms=duration_ms,
            token_count=0,  # Could estimate from response
            had_tool_call=had_tool_call,
        )
        if self.config.show_state_changes:
            for change in changes:
                print_state_change(
                    change.section,
                    change.operation,
                    change.description,
                    auto=change.auto,
                    success=change.success,
                )


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================


async def main() -> None:
    """Main async entry point."""
    try:
        config = get_config()
    except ValueError as e:
        print(f"Configuration error: {e}")
        print("Please set GOOGLE_API_KEY in .env file")
        sys.exit(1)

    controller = DemoController(config)

    try:
        print_welcome(config.session_id)
        controller.start()

        # Main input loop
        while True:
            try:
                user_input = input("\n> ")
                should_continue = await controller.process_input(user_input)
                if not should_continue:
                    break
            except KeyboardInterrupt:
                print("\n")
                print_info("Interrupted - saving checkpoint...")
                break
            except EOFError:
                break

    finally:
        controller.stop()
        print_info("Goodbye!")


def run() -> None:
    """Sync entry point."""
    asyncio.run(main())


if __name__ == "__main__":
    run()
if __name__ == "__main__":
    run()
