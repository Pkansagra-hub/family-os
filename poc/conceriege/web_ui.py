"""
Web UI for Concierge V2 - Real-time proactive conversation

Uses FastAPI + WebSocket to push findings in real-time without waiting for user input.
"""

import asyncio
import random
from datetime import datetime
from pathlib import Path

from backend.agents.concierge_v2 import ConciergeAgentV2
from backend.config.settings import Settings
from backend.services.k0_query_service import MockK0QueryService
from backend.services.llm_client import LLMClient
from backend.services.metrics_collector import MetricsCollector
from backend.services.progress_publisher import ProgressPublisher
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI()

# Mount static files directory for markdown.js and markdown.js
static_dir = Path(__file__).parent / "src"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Initialize services (now uses enriched data automatically)
settings = Settings()
llm_client = LLMClient(settings)
k0_query_service = MockK0QueryService()
metrics_collector = MetricsCollector()
progress_publisher = ProgressPublisher()

# Initialize concierge
concierge = ConciergeAgentV2(
    llm_client=llm_client,
    k0_query_service=k0_query_service,
    metrics_collector=metrics_collector,
    progress_publisher=progress_publisher,
)

user_id = "web_user"


# ============================================================================
# TOPIC 1: CONVERSATIONAL RHYTHM
# ============================================================================
# Functions to send messages with human-like typing delays and indicators
# ============================================================================


async def send_with_rhythm(websocket: WebSocket, message_type: str, content: str):
    """
    Send message with human-like typing delay and indicator.

    Calculates delay based on message length (150ms per word, max 2s),
    adds variance for natural randomness, and shows typing indicator.

    Args:
        websocket: Active WebSocket connection
        message_type: Type of message ("agent_message", "system_notification", etc.)
        content: Message content to send
    """
    word_count = len(content.split())
    base_delay = min(word_count * 0.15, 2.0)  # 150ms per word, max 2s
    variance = random.uniform(0.8, 1.2)  # ±20% variance
    delay = base_delay * variance

    # Show typing indicator
    await websocket.send_json({"type": "typing_indicator", "visible": True})

    # Simulate thinking/typing
    await asyncio.sleep(delay)

    # Hide typing indicator
    await websocket.send_json({"type": "typing_indicator", "visible": False})

    # Send actual message
    await websocket.send_json(
        {"type": message_type, "message": content, "timestamp": datetime.now().isoformat()}
    )


async def send_chunked_response(websocket: WebSocket, full_text: str):
    """
    Split long response into 2-3 chunks with micro-pauses between them.

    This mimics human behavior where longer thoughts are expressed in
    multiple sentences with natural pauses.

    Args:
        websocket: Active WebSocket connection
        full_text: Complete response to be chunked
    """
    sentences = full_text.split(". ")

    # If short response (≤2 sentences), send as one
    if len(sentences) <= 2:
        await send_with_rhythm(websocket, "agent_message", full_text)
        return

    # Split into 2-3 chunks
    chunk_size = len(sentences) // 2 if len(sentences) > 4 else 2
    chunks = [
        ". ".join(sentences[i : i + chunk_size]) + "." for i in range(0, len(sentences), chunk_size)
    ]

    # Send each chunk with micro-pause between them
    for i, chunk in enumerate(chunks):
        await send_with_rhythm(websocket, "agent_message", chunk)

        # Micro-pause between chunks (300-800ms)
        if i < len(chunks) - 1:
            await asyncio.sleep(random.uniform(0.3, 0.8))


async def send_agent_event(websocket: WebSocket, event_data: dict):
    """
    Send agent activity event to frontend for visualization

    Args:
        websocket: Active WebSocket connection
        event_data: Event data with type and agent info
    """
    try:
        await websocket.send_json(event_data)
    except Exception as e:
        print(f"Failed to send agent event: {e}")


@app.get("/")
async def get():
    """Serve the chat UI"""
    return HTMLResponse(HTML_TEMPLATE)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time bidirectional communication"""
    await websocket.accept()

    # Background task monitor - proactively pushes findings
    async def background_monitor():
        """Monitor background tasks and push findings in real-time"""
        while True:
            try:
                await asyncio.sleep(0.5)  # Check every 500ms

                # Check for completed analyses
                await concierge._check_completed_tasks()

                if concierge.completed_analyses:
                    # TOPIC 5: Check focus tracker before injection
                    # Don't interrupt if user is in insight thread
                    if concierge.focus_tracker.state.current_focus != "insight_thread":
                        # PROACTIVE PUSH - don't wait for user message
                        # Pop the analysis to avoid re-injecting it
                        analysis = concierge.completed_analyses.pop(0)
                        primary_insight = analysis.get_primary_insight()
                        insight_text = (
                            primary_insight.summary if primary_insight else "completed analysis"
                        )

                        # Push system notification with rhythm
                        notification_message = f"🔔 Analysis complete: {insight_text}"
                        await send_with_rhythm(
                            websocket, "system_notification", notification_message
                        )

                        # Generate natural injection response
                        injection_response = await concierge._respond_with_findings(
                            "(continuing our conversation)"
                        )

                        # Track injection for focus tracker
                        concierge.focus_tracker.track_insight_injection(injection_response)

                        # Push agent message with rhythm and chunking
                        await send_chunked_response(websocket, injection_response)

            except Exception as e:
                print(f"Background monitor error: {e}")
                await asyncio.sleep(1)

    # Start background monitor
    monitor_task = asyncio.create_task(background_monitor())

    # Create a global task_id for tracking all agent events
    session_task_id = f"session_{user_id}_{datetime.now().timestamp()}"

    # Task to forward progress_publisher events to WebSocket as agent events
    async def forward_agent_events():
        """Subscribe to progress_publisher and forward events to WebSocket."""
        try:
            # Track active specialists for generating agent IDs
            active_specialists = {}
            specialist_counter = 0

            async for event_data in progress_publisher.subscribe(session_task_id):
                if not event_data:
                    continue

                # Map progress_publisher events to agent panel events
                event_type = event_data.get("type", "")
                specialist_type = event_data.get("specialist_type", "unknown")

                # Generate or reuse agent_id for this specialist
                if specialist_type not in active_specialists:
                    specialist_counter += 1
                    active_specialists[specialist_type] = f"specialist_{specialist_counter}"

                agent_id = active_specialists[specialist_type]

                # Convert to agent panel event format
                if event_type == "background_analysis_started":
                    # Enhanced task description with topic
                    topic = event_data.get("topic", "unknown topic")
                    task_description = f"Analyzing {topic} from {specialist_type} perspective"

                    await send_agent_event(
                        websocket,
                        {
                            "type": "agent.started",
                            "agent_id": agent_id,
                            "agent_type": specialist_type,
                            "parent_agent": "concierge",
                            "task": task_description,
                        },
                    )

                    # Show subtle status in chat
                    status_msg = f"🤖 {specialist_type.title()} specialist is analyzing {topic}..."
                    await websocket.send_json({"type": "status", "content": status_msg})

                elif event_type == "backchannel":
                    backchannel_text = event_data.get("text", "Processing...")
                    await send_agent_event(
                        websocket,
                        {
                            "type": "agent.progress",
                            "agent_id": agent_id,
                            "progress": 0.5,  # Estimate mid-progress
                            "status": backchannel_text,
                        },
                    )

                    # Show backchannel in chat as subtle update
                    await websocket.send_json(
                        {
                            "type": "thinking",
                            "content": f"💭 {specialist_type.title()}: {backchannel_text}",
                        }
                    )

                elif event_type == "insight_ready":
                    await send_agent_event(
                        websocket,
                        {
                            "type": "agent.completed",
                            "agent_id": agent_id,
                            "result": event_data.get("message", "Analysis complete"),
                        },
                    )
                    # Remove from active specialists
                    if specialist_type in active_specialists:
                        del active_specialists[specialist_type]

        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"Agent event forwarding error: {e}")

    # Start agent event forwarder
    agent_events_task = asyncio.create_task(forward_agent_events())

    try:
        while True:
            # Receive user message
            data = await websocket.receive_json()
            user_message = data.get("message", "")

            if not user_message:
                continue

            # Echo user message
            await send_with_rhythm(websocket, "user_message", user_message)

            # Show thinking indicator while processing
            await websocket.send_json(
                {"type": "thinking", "content": "🤔 Concierge is thinking..."}
            )

            # Process message (this will trigger real agent events via progress_publisher)
            response = await concierge.process_message(user_id, user_message)

            # Clear thinking indicator
            await websocket.send_json({"type": "thinking_done", "content": ""})

            # Send agent response with rhythm and chunking
            await send_chunked_response(websocket, response)

            # Send background task status
            if concierge.background_tasks:
                status_message = (
                    f"🔄 {len(concierge.background_tasks)} task(s) running in background..."
                )
                await send_with_rhythm(websocket, "status", status_message)

    except WebSocketDisconnect:
        print("Client disconnected")
    finally:
        monitor_task.cancel()
        agent_events_task.cancel()


HTML_TEMPLATE = """
<!DOCTYPE html>
<html data-theme="light">
<head>
    <title>Concierge V2 - Proactive Chat</title>
    <meta name="theme-color" content="#667eea">
    <link rel="stylesheet" href="/static/styles/theme.css">
    <link rel="stylesheet" href="/static/styles/markdown.css">
    <link rel="stylesheet" href="/static/styles/toast.css">
    <link rel="stylesheet" href="/static/styles/search.css">
    <link rel="stylesheet" href="/static/styles/sidebar.css">
    <link rel="stylesheet" href="/static/styles/agent-panel.css">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
            background: var(--bg-secondary);
            height: 100vh;
            display: flex;
            flex-direction: column;
            margin: 0;
            padding: 0;
        }

        .container {
            width: 100%;
            height: 100vh;
            background: var(--bg-primary);
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }

        .main-layout {
            display: flex;
            flex: 1;
            overflow: hidden;
        }

        .header {
            background: var(--bubble-user-bg);
            color: var(--bubble-user-text);
            padding: 20px;
            text-align: center;
        }

        .header h1 {
            font-size: 24px;
            margin-bottom: 5px;
        }

        .header p {
            font-size: 14px;
            opacity: 0.9;
        }

        .messages {
            flex: 1;
            min-height: 0;
            overflow-y: auto;
            padding: 20px;
            background: var(--bg-secondary);
            width: 100%;
        }

        .message {
            margin-bottom: 15px;
            animation: slideIn 0.3s ease-out;
        }

        @keyframes slideIn {
            from {
                opacity: 0;
                transform: translateY(10px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }

        .message.user {
            text-align: right;
        }

        .message-bubble {
            display: inline-block;
            max-width: 70%;
            padding: 12px 16px;
            border-radius: 18px;
            word-wrap: break-word;
        }

        .message.user .message-bubble {
            background: var(--bubble-user-bg);
            color: var(--bubble-user-text);
        }

        .message.agent .message-bubble {
            background: var(--bubble-agent-bg);
            color: var(--bubble-agent-text);
            box-shadow: var(--shadow-md);
        }

        .message.system .message-bubble {
            background: var(--bubble-system-bg);
            color: var(--bubble-system-text);
            border: 1px solid var(--bubble-system-border);
            animation: pulse 2s ease-in-out;
        }

        @keyframes pulse {
            0%, 100% { transform: scale(1); }
            50% { transform: scale(1.02); }
        }

        .message.status .message-bubble {
            background: var(--surface);
            color: var(--info);
            font-size: 12px;
        }

        /* Typing Indicator Animation */
        .typing-indicator {
            display: none;
            padding: 10px 20px;
            background: var(--bg-secondary);
        }

        .typing-indicator span {
            display: inline-block;
            width: 8px;
            height: 8px;
            background: var(--text-tertiary);
            border-radius: 50%;
            margin: 0 2px;
            animation: typing 1.4s infinite;
        }

        .typing-indicator span:nth-child(2) {
            animation-delay: 0.2s;
        }

        .typing-indicator span:nth-child(3) {
            animation-delay: 0.4s;
        }

        @keyframes typing {
            0%, 60%, 100% {
                transform: translateY(0);
                opacity: 1;
            }
            30% {
                transform: translateY(-10px);
                opacity: 0.8;
            }
        }

        .timestamp {
            font-size: 11px;
            color: var(--text-tertiary);
            margin-top: 4px;
        }

        .input-area {
            padding: 20px;
            background: var(--bg-primary);
            border-top: 1px solid var(--border-default);
            display: flex;
            gap: 10px;
        }

        #messageInput {
            flex: 1;
            padding: 12px 16px;
            border: 2px solid var(--border-default);
            border-radius: 25px;
            font-size: 14px;
            outline: none;
            transition: border-color 0.3s;
            background: var(--bg-primary);
            color: var(--text-primary);
        }

        #messageInput:focus {
            border-color: var(--primary-600);
        }

        #sendButton {
            padding: 12px 24px;
            background: var(--bubble-user-bg);
            color: var(--bubble-user-text);
            border: none;
            border-radius: 25px;
            cursor: pointer;
            font-weight: 600;
            transition: transform 0.2s;
        }

        #sendButton:hover {
            transform: scale(1.05);
        }

        #sendButton:active {
            transform: scale(0.95);
        }
    </style>
</head>
<body>
    <!-- Theme Toggle Button -->
    <button class="theme-toggle" id="themeToggle" aria-label="Toggle theme">
        <span class="icon-light">☀️</span>
        <span class="icon-dark">🌙</span>
    </button>

    <div class="container">
        <div class="header">
            <h1>🤖 Concierge V2</h1>
            <p>Real-time proactive conversation with background intelligence</p>
        </div>

        <div class="main-layout">
            <!-- Sidebar -->
            <div class="sidebar open" id="sidebar">
                <div class="sidebar-header">
                    <span class="sidebar-title">Conversations</span>
                    <button id="sidebarToggle" aria-label="Toggle sidebar">⟨</button>
                </div>
                <button id="newChatBtn" aria-label="Start new conversation">+ New Chat</button>
                <div class="sidebar-content">
                    <div id="conversationsList"></div>
                </div>
            </div>

            <!-- Main Chat Area -->
            <div style="flex: 1; display: flex; flex-direction: column; overflow: hidden;">
                <div class="messages" id="messagesContainer">
                    <div class="message system">
                        <div class="message-bubble">
                            💡 Try: "Hello" → "Milk makes me sick" → Wait for proactive findings!
                        </div>
                    </div>
                </div>

                <!-- Typing Indicator (shown during message delays) -->
                <div id="typing-indicator" class="typing-indicator" style="display: none;">
                    <div class="message agent">
                        <div class="message-bubble">
                            <span></span><span></span><span></span>
                        </div>
                    </div>
                </div>

                <div class="input-area">
                    <input type="text" id="messageInput" placeholder="Type your message..."
                           onkeypress="if(event.keyCode==13) sendMessage()">
                    <button id="sendButton" onclick="sendMessage()">Send</button>
                </div>
            </div>
        </div>

        <!-- Agent Activity Panel -->
        <div id="agentActivityPanel"></div>
    </div>

    <script type="module">
        // Import services
        import { renderMarkdown, hasMarkdown } from '/static/services/markdown.js';
        import { ThemeManager } from '/static/services/theme.js';
        import { showToast } from '/static/services/toast.js';
        import { copyMessageContent } from '/static/services/copy.js';
        import { storage } from '/static/services/storage.js';
        import { initializeSidebar, switchConversation, handleNewConversation, renderConversationList } from '/static/services/sidebar.js';
        import { initializeAgentPanel, handleAgentEvent } from '/static/services/agent-panel.js';

        // Initialize theme manager
        const themeManager = new ThemeManager();

        // Setup theme toggle button
        const themeToggle = document.getElementById('themeToggle');
        themeToggle.addEventListener('click', () => {
            themeManager.toggleTheme();
        });

        // Initialize sidebar
        await initializeSidebar();

        // Initialize agent panel
        initializeAgentPanel();

        // Listen for conversation changes
        window.addEventListener('conversationChanged', async (e) => {
            const messagesEl = document.getElementById('messagesContainer');
            messagesEl.innerHTML = '';

            // Load messages for new conversation
            const currentConvId = await storage.getCurrentConversationId();
            const messages = await storage.loadMessages(currentConvId);

            if (messages && messages.length > 0) {
                messages.forEach(msg => {
                    addMessage(msg, false);
                });
            }
        });

        // Initialize storage and restore messages
        async function initializeStorage() {
            try {
                // Wait for storage to initialize
                await new Promise(resolve => setTimeout(resolve, 100));

                // Load previous messages from current conversation
                const currentConvId = await storage.getCurrentConversationId();
                const messages = await storage.loadMessages(currentConvId);

                if (messages && messages.length > 0) {
                    console.log(`Restored ${messages.length} messages`);
                    messages.forEach(msg => {
                        addMessage(msg, false); // false = don't save to storage
                    });
                    showToast(`Restored ${messages.length} messages`, 'info', 2000);
                }
            } catch (error) {
                console.error('Failed to restore messages:', error);
            }
        }

        // Call on page load
        initializeStorage();

        // WebSocket setup
        const ws = new WebSocket(`ws://${window.location.host}/ws`);
        const messagesDiv = document.getElementById('messagesContainer');
        const messageInput = document.getElementById('messageInput');

        ws.onopen = () => {
            console.log('Connected to server');
            showToast('Connected', 'success', 1000);
        };

        ws.onmessage = (event) => {
            const data = JSON.parse(event.data);

            // Handle agent events separately
            if (data.type && data.type.startsWith('agent.')) {
                handleAgentEvent(data);
            } else if (data.type === 'specialist.spawned') {
                handleAgentEvent(data);
            } else if (data.type === 'typing_indicator') {
                const indicator = document.getElementById('typing-indicator');
                indicator.style.display = data.visible ? 'block' : 'none';
            } else if (data.type === 'thinking') {
                // Show thinking indicator in chat
                showThinkingIndicator(data.content);
            } else if (data.type === 'thinking_done') {
                // Remove thinking indicator
                removeThinkingIndicator();
            } else if (data.type === 'status') {
                // Show subtle status message
                showStatusMessage(data.content);
            } else {
                addMessage(data, true); // true = save to storage
            }
        };

        ws.onerror = (error) => {
            console.error('WebSocket error:', error);
            showToast('Connection error', 'error', 2000);
        };

        ws.onclose = () => {
            console.log('Disconnected from server');
            showToast('Disconnected', 'error', 2000);
        };

        function addMessage(data, saveToStorage = true) {
            const messageDiv = document.createElement('div');
            messageDiv.className = `message ${data.type.replace('_message', '').replace('_notification', ' system')}`;

            const bubble = document.createElement('div');
            bubble.className = 'message-bubble';

            // Render markdown for agent messages, plain text for others
            if (data.type === 'agent_message' && hasMarkdown(data.message)) {
                bubble.innerHTML = renderMarkdown(data.message);
            } else if (data.type === 'agent_message') {
                bubble.innerHTML = renderMarkdown(data.message);
            } else {
                bubble.textContent = data.message;
            }

            // Add copy button for agent messages
            if (data.type === 'agent_message') {
                const copyButton = document.createElement('button');
                copyButton.className = 'copy-button';
                copyButton.innerHTML = '📋';
                copyButton.title = 'Copy message';
                copyButton.addEventListener('click', async () => {
                    const success = await copyMessageContent(messageDiv);
                    if (success) {
                        copyButton.innerHTML = '✓';
                        copyButton.classList.add('copied');
                        showToast('Copied to clipboard!', 'success', 2000);
                        setTimeout(() => {
                            copyButton.innerHTML = '📋';
                            copyButton.classList.remove('copied');
                        }, 2000);
                    } else {
                        showToast('Failed to copy', 'error', 2000);
                    }
                });
                bubble.appendChild(copyButton);
            }

            const timestamp = document.createElement('div');
            timestamp.className = 'timestamp';
            timestamp.textContent = new Date(data.timestamp).toLocaleTimeString();

            messageDiv.appendChild(bubble);
            messageDiv.appendChild(timestamp);
            messagesDiv.appendChild(messageDiv);

            // Auto-scroll to bottom
            messagesDiv.scrollTop = messagesDiv.scrollHeight;

            // Save to storage if requested
            if (saveToStorage) {
                storage.getCurrentConversationId().then(convoId => {
                    if (convoId) {
                        storage.saveMessage(convoId, {
                            type: data.type,
                            message: data.message,
                            timestamp: data.timestamp
                        }).catch(error => {
                            console.error('Failed to save message:', error);
                        });
                    }
                });
            }
        }

        // Thinking indicator management
        let thinkingElement = null;

        function showThinkingIndicator(message) {
            // Remove existing thinking indicator
            removeThinkingIndicator();

            // Create new thinking indicator
            thinkingElement = document.createElement('div');
            thinkingElement.className = 'message system thinking-message';
            thinkingElement.id = 'thinking-indicator-msg';

            const bubble = document.createElement('div');
            bubble.className = 'message-bubble';
            bubble.style.fontStyle = 'italic';
            bubble.style.opacity = '0.8';
            bubble.textContent = message;

            thinkingElement.appendChild(bubble);
            messagesDiv.appendChild(thinkingElement);
            messagesDiv.scrollTop = messagesDiv.scrollHeight;
        }

        function removeThinkingIndicator() {
            if (thinkingElement && thinkingElement.parentNode) {
                thinkingElement.parentNode.removeChild(thinkingElement);
                thinkingElement = null;
            }
        }

        function showStatusMessage(message) {
            const statusDiv = document.createElement('div');
            statusDiv.className = 'message system status-message';
            statusDiv.style.opacity = '0.6';
            statusDiv.style.fontSize = '0.85em';

            const bubble = document.createElement('div');
            bubble.className = 'message-bubble';
            bubble.textContent = message;

            statusDiv.appendChild(bubble);
            messagesDiv.appendChild(statusDiv);
            messagesDiv.scrollTop = messagesDiv.scrollHeight;

            // Auto-remove after 3 seconds
            setTimeout(() => {
                if (statusDiv.parentNode) {
                    statusDiv.style.transition = 'opacity 0.3s';
                    statusDiv.style.opacity = '0';
                    setTimeout(() => {
                        if (statusDiv.parentNode) {
                            statusDiv.parentNode.removeChild(statusDiv);
                        }
                    }, 300);
                }
            }, 3000);
        }

        function sendMessage() {
            const message = messageInput.value.trim();
            if (!message) return;

            ws.send(JSON.stringify({ message }));
            messageInput.value = '';
        }

        // Make sendMessage available globally
        window.sendMessage = sendMessage;
    </script>
</body>
</html>
"""


if __name__ == "__main__":
    import uvicorn

    print("\n" + "=" * 70)
    print("🚀 Starting Concierge V2 Web UI")
    print("=" * 70)
    print("\n📱 Open your browser: http://localhost:8000")
    print("\n💡 Features:")
    print("   • Real-time bidirectional communication")
    print("   • Proactive push notifications (no waiting!)")
    print("   • Background specialist analysis")
    print("   • Automatic findings injection\n")

    uvicorn.run(app, host="0.0.0.0", port=8000)
