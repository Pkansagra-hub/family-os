#!/usr/bin/env python3
"""
K1 Intelligence Module - Interactive Chat CLI

Simple command-line interface to chat with the K1 system via WebSocket.
"""

import asyncio
import json
import sys
from datetime import datetime, timezone

try:
    import websockets
except ImportError:
    print("❌ Error: websockets library not installed")
    print("   Install with: pip install websockets")
    sys.exit(1)


class ChatCLI:
    """Interactive chat client for K1 Intelligence Module"""

    def __init__(self, api_url: str = "ws://localhost:8000", user_id: str = "cli_user"):
        self.api_url = api_url
        self.user_id = user_id
        self.session_id = None
        self.turn_count = 0
        self.processing = False  # Flag to prevent overlapping inputs

    async def connect(self):
        """Connect to the K1 API WebSocket endpoint"""
        uri = f"{self.api_url}/ws/chat/{self.user_id}"
        print("🔌 Connecting to K1 Intelligence Module...")
        print(f"   URL: {uri}")
        print()

        try:
            async with websockets.connect(uri) as websocket:
                print("✅ Connected! Type your message and press Enter.")
                print("   Commands: /help, /status, /exit")
                print("=" * 70)
                print()

                # Start listening for server messages
                listener_task = asyncio.create_task(self.listen(websocket))

                # Start sending user input
                sender_task = asyncio.create_task(self.send_messages(websocket))

                # Wait for either task to complete
                done, pending = await asyncio.wait(
                    [listener_task, sender_task], return_when=asyncio.FIRST_COMPLETED
                )

                # Cancel pending tasks
                for task in pending:
                    task.cancel()

        except ConnectionRefusedError:
            print("❌ Connection refused!")
            print("   Is the API server running?")
            print("   Start it with: python api.py")
            sys.exit(1)
        except Exception as e:
            print(f"❌ Connection error: {e}")
            sys.exit(1)

    async def listen(self, websocket):
        """Listen for messages from the server"""
        try:
            async for message in websocket:
                await self.handle_message(message)
        except websockets.exceptions.ConnectionClosed:
            print("\n❌ Connection closed by server")
        except Exception as e:
            print(f"\n❌ Error receiving message: {e}")

    async def send_messages(self, websocket):
        """Send user input to the server"""
        try:
            while True:
                # Wait if currently processing a response
                while self.processing:
                    await asyncio.sleep(0.1)

                # Read user input
                try:
                    user_input = await asyncio.get_event_loop().run_in_executor(
                        None, input, "You: "
                    )
                except EOFError:
                    print("\n👋 Goodbye!")
                    break

                if not user_input.strip():
                    continue

                # Handle exit command
                if user_input.strip().lower() in ["/exit", "/quit", "exit", "quit"]:
                    print("👋 Goodbye!")
                    break

                # Set processing flag
                self.processing = True

                # Send message
                message = {
                    "type": "message",
                    "text": user_input,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }

                await websocket.send(json.dumps(message))
                self.turn_count += 1

        except Exception as e:
            print(f"\n❌ Error sending message: {e}")

    async def handle_message(self, message: str):
        """Handle incoming messages from the server"""
        try:
            data = json.loads(message)
            event_type = data.get("type", "unknown")

            if event_type == "connected":
                print(f"✅ {data.get('message', 'Connected')}")
                print()

            elif event_type == "ack":
                # Acknowledgment - message received
                # Just show dots to indicate processing without repeating message
                pass

            elif event_type == "processing":
                agent = data.get("agent", "system")
                print(f"🤔 {agent} is thinking...")

            elif event_type == "event":
                # System event (agent.registered, session.created, etc.)
                event_name = data.get("event", "")
                if "agent.registered" in event_name:
                    agent_type = data.get("data", {}).get("agent_type", "agent")
                    print(f"   📡 Spawned {agent_type} agent")

            elif event_type == "tool_call":
                tool = data.get("tool", "unknown")
                print(f"   🔧 Using tool: {tool}")

            elif event_type == "response":
                # Partial response (streaming)
                content = data.get("content", "")
                if content:
                    print(content, end="", flush=True)

            elif event_type == "response_final":
                # Final complete response
                content = data.get("content", "")
                latency = data.get("latency_ms", 0)

                print()
                print(f"\n🤖 K1: {content}")
                print(f"   ⏱️  Response time: {latency:.0f}ms")
                print()

                # Clear processing flag to allow next input
                self.processing = False

            elif event_type == "delta":
                # Session delta event
                pass

            elif event_type == "completed":
                # Interaction completed
                trace_id = data.get("trace_id", "")
                if trace_id:
                    print(f"   ✅ Completed (trace: {trace_id[:16]}...)")

            elif event_type == "error":
                error_msg = data.get("message", "Unknown error")
                print(f"\n❌ Error: {error_msg}")
                print()

                # Clear processing flag on error too
                self.processing = False

            elif event_type == "pong":
                # Heartbeat response
                pass

            else:
                # Unknown event type - log for debugging
                pass

        except json.JSONDecodeError:
            print(f"⚠️  Invalid message: {message}")
        except Exception as e:
            print(f"⚠️  Error handling message: {e}")


async def main():
    """Main entry point"""
    print("=" * 70)
    print("🧠 K1 Intelligence Module - Interactive Chat")
    print("=" * 70)
    print()

    # Parse command line arguments
    user_id = "cli_user"
    if len(sys.argv) > 1:
        user_id = sys.argv[1]

    # Create and start chat client
    cli = ChatCLI(user_id=user_id)
    await cli.connect()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n👋 Goodbye!")
        sys.exit(0)
