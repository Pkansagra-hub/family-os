"""
FastAPI Server - WebSocket endpoint for POC demo
"""

import sys
from pathlib import Path

# Add current directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from config.settings import settings
from l2_orchestration.concierge import ConciergeCoordinator
from l3_execution.nutritionist_specialist import NutritionistSpecialist

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# Start specialist listener on startup
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle"""
    logger.info("Starting POC server...")

    # Start nutritionist specialist listener
    specialist = NutritionistSpecialist()
    listener_task = asyncio.create_task(specialist.start_listening())

    logger.info("Nutritionist specialist listening for jobs")

    yield

    # Cleanup
    listener_task.cancel()
    logger.info("Shutting down...")


app = FastAPI(
    title="Concierge Dual-Agent POC",
    description="Proof of concept for Reactive/Proactive dual-agent pattern",
    version="0.1.0",
    lifespan=lifespan,
)


# Active concierge sessions
active_sessions: dict[str, ConciergeCoordinator] = {}


@app.get("/")
async def get_homepage():
    """Simple HTML client for testing"""
    return HTMLResponse(
        """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Concierge Dual-Agent POC</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                max-width: 800px;
                margin: 50px auto;
                padding: 20px;
            }
            #chat {
                border: 1px solid #ccc;
                height: 400px;
                overflow-y: auto;
                padding: 10px;
                margin-bottom: 10px;
                background: #f9f9f9;
            }
            .message {
                margin: 10px 0;
                padding: 8px;
                border-radius: 5px;
            }
            .user {
                background: #007bff;
                color: white;
                text-align: right;
            }
            .assistant {
                background: #e9ecef;
            }
            .system {
                background: #fff3cd;
                font-style: italic;
                font-size: 0.9em;
            }
            #input-container {
                display: flex;
                gap: 10px;
            }
            #message-input {
                flex: 1;
                padding: 10px;
                font-size: 16px;
            }
            #send-button {
                padding: 10px 20px;
                font-size: 16px;
                background: #007bff;
                color: white;
                border: none;
                cursor: pointer;
            }
            #send-button:disabled {
                background: #ccc;
                cursor: not-allowed;
            }
            #status {
                margin-top: 10px;
                font-size: 0.9em;
                color: #666;
            }
        </style>
    </head>
    <body>
        <h1>🤖 Concierge Dual-Agent POC</h1>
        <p>Try: "milk makes me sick"</p>

        <div id="chat"></div>

        <div id="input-container">
            <input type="text" id="message-input" placeholder="Type your message..." />
            <button id="send-button">Send</button>
        </div>

        <div id="status">Status: Disconnected</div>

        <script>
            const chat = document.getElementById('chat');
            const input = document.getElementById('message-input');
            const sendButton = document.getElementById('send-button');
            const status = document.getElementById('status');

            let ws = null;
            let isConnected = false;

            function connect() {
                ws = new WebSocket(`ws://${window.location.host}/ws/chat`);

                ws.onopen = () => {
                    isConnected = true;
                    status.textContent = 'Status: Connected';
                    status.style.color = 'green';
                    sendButton.disabled = false;
                };

                ws.onmessage = (event) => {
                    const data = JSON.parse(event.data);

                    if (data.type === 'message') {
                        addMessage(data.content, data.source || 'assistant');
                    } else if (data.type === 'state') {
                        status.textContent = `Status: ${data.reactive_state} / ${data.proactive_state}`;
                    }
                };

                ws.onerror = (error) => {
                    console.error('WebSocket error:', error);
                    status.textContent = 'Status: Error';
                    status.style.color = 'red';
                };

                ws.onclose = () => {
                    isConnected = false;
                    status.textContent = 'Status: Disconnected';
                    status.style.color = 'gray';
                    sendButton.disabled = true;

                    // Reconnect after 3 seconds
                    setTimeout(connect, 3000);
                };
            }

            function addMessage(content, source) {
                const div = document.createElement('div');
                div.className = `message ${source}`;
                div.textContent = content;
                chat.appendChild(div);
                chat.scrollTop = chat.scrollHeight;
            }

            function sendMessage() {
                const message = input.value.trim();
                if (!message || !isConnected) return;

                addMessage(message, 'user');
                ws.send(JSON.stringify({ message }));
                input.value = '';
                sendButton.disabled = true;
            }

            sendButton.addEventListener('click', sendMessage);
            input.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') sendMessage();
            });

            // Initial connection
            connect();
        </script>
    </body>
    </html>
    """
    )


@app.websocket("/ws/chat")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for chat"""
    await websocket.accept()

    # Create new concierge session
    concierge = ConciergeCoordinator()
    thread_id = concierge.thread_id
    active_sessions[thread_id] = concierge

    logger.info(f"New WebSocket connection: {thread_id}")

    # Send welcome message
    await websocket.send_json(
        {
            "type": "message",
            "content": "Hi! I'm your family health concierge. How can I help you today?",
            "source": "system",
        }
    )

    try:
        while True:
            # Receive message
            data = await websocket.receive_json()
            user_message = data.get("message", "")

            if not user_message:
                continue

            logger.info(f"[{thread_id}] Received: {user_message}")

            # Process through concierge
            responses = await concierge.process_user_message(user_message)

            # Stream responses to client
            for response in responses:
                await websocket.send_json(
                    {"type": "message", "content": response, "source": "assistant"}
                )

                # Small delay between messages for natural feel
                await asyncio.sleep(0.5)

            # Send state update
            state = concierge.get_state()
            await websocket.send_json({"type": "state", **state})

    except WebSocketDisconnect:
        logger.info(f"[{thread_id}] WebSocket disconnected")
    except Exception as e:
        logger.error(f"[{thread_id}] Error: {e}")
    finally:
        # Cleanup
        active_sessions.pop(thread_id, None)
        logger.info(f"[{thread_id}] Session closed")


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "active_sessions": len(active_sessions)}


@app.get("/session/{thread_id}")
async def get_session_state(thread_id: str):
    """Get session state for debugging"""
    concierge = active_sessions.get(thread_id)
    if not concierge:
        return {"error": "Session not found"}

    state = concierge.get_state()
    history = concierge.get_conversation_history()

    return {
        "state": state,
        "conversation": history,
        "shared_context_keys": list(concierge.shared_context.keys()),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=settings.server_host, port=settings.server_port, log_level="info")
