#!/usr/bin/env python3
"""
WebSocket Test Client for K1 Intelligence API

Usage:
    python test_websocket_client.py

Tests:
    1. Connection establishment
    2. Single message streaming
    3. Multi-turn conversation
    4. Event streaming (agent events, deltas, tool calls)

Requirements:
    pip install websockets asyncio
"""

import asyncio
import json
import sys

try:
    import websockets
except ImportError:
    print("❌ websockets not installed. Run: pip install websockets")
    sys.exit(1)


async def test_websocket_chat(user_id: str = "test_user"):
    """
    Test WebSocket streaming chat with K1 Intelligence API.

    Pattern: Connects to /ws/chat/{user_id} and streams events.
    """
    uri = f"ws://localhost:8000/ws/chat/{user_id}"
    print(f"🔌 Connecting to: {uri}")

    try:
        async with websockets.connect(uri) as websocket:
            print("✅ Connected!")

            # Wait for connection confirmation
            response = await websocket.recv()
            data = json.loads(response)
            print(f"📩 {data.get('type')}: {data.get('message')}")

            # Test 1: Single message
            print("\n" + "=" * 70)
            print("TEST 1: Single Message - Healthcare Query")
            print("=" * 70)

            message1 = {
                "type": "message",
                "text": "How's my recovery going?",
            }
            await websocket.send(json.dumps(message1))
            print(f"📤 Sent: {message1['text']}")

            # Stream events
            turn1_complete = False
            while not turn1_complete:
                response = await websocket.recv()
                data = json.loads(response)
                event_type = data.get("type")

                if event_type == "ack":
                    print(f"   ✓ Acknowledged (Turn {data.get('turn')})")

                elif event_type == "processing":
                    agent = data.get("agent", "unknown")
                    print(f"   🤔 {agent} is thinking...")

                elif event_type == "event":
                    evt = data.get("event_type", "")
                    print(f"   📡 Event: {evt}")

                elif event_type == "tool_call":
                    tool = data.get("tool", "unknown")
                    print(f"   🔧 Tool called: {tool}")

                elif event_type == "delta":
                    delta_type = data.get("delta_type", "unknown")
                    print(f"   💾 Memory delta: {delta_type}")

                elif event_type == "response":
                    content = data.get("content", "")[:200]
                    print(f"   💬 Response: {content}...")

                elif event_type == "response_final":
                    content = data.get("content", "")[:200]
                    latency = data.get("latency_ms", 0)
                    print(f"   ✅ Final response ({latency:.0f}ms): {content}...")
                    turn1_complete = True

                elif event_type == "completed":
                    agent = data.get("agent", "unknown")
                    latency = data.get("latency_ms", 0)
                    print(f"   ✓ {agent} completed ({latency:.0f}ms)")

                elif event_type == "error":
                    print(f"   ❌ Error: {data.get('message')}")
                    turn1_complete = True

            # Test 2: Multi-turn conversation
            print("\n" + "=" * 70)
            print("TEST 2: Multi-Turn - Planning Query")
            print("=" * 70)

            await asyncio.sleep(1)  # Brief pause

            message2 = {
                "type": "message",
                "text": "Plan a dinner at an Italian restaurant nearby tonight",
            }
            await websocket.send(json.dumps(message2))
            print(f"📤 Sent: {message2['text']}")

            # Stream events
            turn2_complete = False
            while not turn2_complete:
                response = await websocket.recv()
                data = json.loads(response)
                event_type = data.get("type")

                if event_type == "ack":
                    print(f"   ✓ Acknowledged (Turn {data.get('turn')})")

                elif event_type == "processing":
                    agent = data.get("agent", "unknown")
                    print(f"   🤔 {agent} is thinking...")

                elif event_type == "event":
                    evt = data.get("event_type", "")
                    if "orchestration" in evt or "agent" in evt:
                        print(f"   📡 Event: {evt}")

                elif event_type == "response":
                    content = data.get("content", "")[:200]
                    print(f"   💬 Response: {content}...")

                elif event_type == "response_final":
                    content = data.get("content", "")[:200]
                    latency = data.get("latency_ms", 0)
                    trace_id = data.get("trace_id", "")
                    print(f"   ✅ Final response ({latency:.0f}ms): {content}...")
                    print(f"   📝 Trace ID: {trace_id}")
                    turn2_complete = True

                elif event_type == "error":
                    print(f"   ❌ Error: {data.get('message')}")
                    turn2_complete = True

            # Test 3: Ping/Pong (heartbeat)
            print("\n" + "=" * 70)
            print("TEST 3: Heartbeat (Ping/Pong)")
            print("=" * 70)

            ping_msg = {"type": "ping"}
            await websocket.send(json.dumps(ping_msg))
            print("📤 Sent: ping")

            response = await websocket.recv()
            data = json.loads(response)
            if data.get("type") == "pong":
                print("✅ Received: pong")

            print("\n" + "=" * 70)
            print("✅ All tests completed successfully!")
            print("=" * 70)

    except websockets.exceptions.ConnectionClosed as e:
        print(f"❌ Connection closed: {e}")
    except Exception as e:
        print(f"❌ Error: {e}", exc_info=True)


async def test_rest_api():
    """Test REST API endpoint (non-streaming fallback)"""
    import httpx

    print("\n" + "=" * 70)
    print("TEST: REST API (Non-Streaming)")
    print("=" * 70)

    try:
        async with httpx.AsyncClient() as client:
            # Test /health endpoint
            print("\n1. Health Check:")
            response = await client.get("http://localhost:8000/health")
            print(f"   Status: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                print(f"   System: {data.get('status')}")
                print(f"   Uptime: {data.get('uptime_seconds', 0):.1f}s")

            # Test /chat endpoint
            print("\n2. Chat (REST):")
            chat_request = {
                "message": "What's my current health status?",
                "user_id": "rest_test_user",
            }
            response = await client.post("http://localhost:8000/chat", json=chat_request)
            print(f"   Status: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                print(f"   Response: {data.get('message', '')[:200]}...")
                print(f"   Latency: {data.get('latency_ms', 0):.0f}ms")
                print(f"   Session: {data.get('session_id', '')}")

    except httpx.ConnectError:
        print("❌ Cannot connect to API. Is it running?")
        print("   Start with: python api.py")
    except Exception as e:
        print(f"❌ Error: {e}")


async def main():
    """Run all tests"""
    print("=" * 70)
    print("🧪 K1 Intelligence API - WebSocket Test Client")
    print("=" * 70)

    # Check if API is running
    print("\n📡 Checking if API is running on http://localhost:8000...")
    try:
        import httpx

        async with httpx.AsyncClient() as client:
            response = await client.get("http://localhost:8000/")
            if response.status_code == 200:
                data = response.json()
                print(f"✅ API Status: {data.get('status')}")
                print(f"   Version: {data.get('version')}")
            else:
                print(f"⚠️  API returned status {response.status_code}. May be initializing...")
    except Exception as e:
        print(f"❌ API not reachable: {e}")
        print("   Start the API with: python api.py")
        print("   Or: uvicorn api:app --host 0.0.0.0 --port 8000")
        return

    # Run tests
    try:
        # Test WebSocket streaming
        await test_websocket_chat(user_id="websocket_test_user")

        # Test REST API
        await test_rest_api()

    except KeyboardInterrupt:
        print("\n\n⏹️  Tests interrupted by user")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Bye!")
