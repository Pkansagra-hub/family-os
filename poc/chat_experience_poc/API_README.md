# K1 Intelligence API - WebSocket Streaming Chat

Real-time WebSocket streaming chat powered by K1 Intelligence Module.

## 🚀 Quick Start

### 1. Install Dependencies

```bash
cd poc/chat_experience_poc
pip install -r requirements-api.txt
```

### 2. Start the API

```bash
# Option 1: Direct Python
python api.py

# Option 2: With Uvicorn (recommended for production)
uvicorn api:app --host 0.0.0.0 --port 8000 --workers 1
```

**⚠️ Important:** Use `--workers 1` to preserve SystemCoordinator singleton!

### 3. Test the API

```bash
# Run test client
python test_websocket_client.py
```

## 📡 API Endpoints

### WebSocket (Streaming)

```
ws://localhost:8000/ws/chat/{user_id}
```

**Protocol:**

1. **Connect**: Client connects with `user_id` in URL
2. **Send Message**:
   ```json
   {"type": "message", "text": "How's my recovery going?"}
   ```
3. **Receive Events** (real-time streaming):
   ```json
   {"type": "connected", "user_id": "...", "message": "..."}
   {"type": "ack", "turn": 1, "message": "Processing..."}
   {"type": "processing", "agent": "concierge", "status": "thinking"}
   {"type": "event", "event_type": "agent.task_received", ...}
   {"type": "response", "content": "...", "final": true}
   {"type": "delta", "delta_type": "episodic", ...}
   {"type": "completed", "agent": "...", "latency_ms": 6500}
   {"type": "response_final", "content": "...", "trace_id": "..."}
   ```
4. **Multi-Turn**: Send more messages in the same connection
5. **Disconnect**: Close WebSocket when done

**Event Types:**
- `connected` - Initial connection confirmation
- `ack` - Message received acknowledgment
- `processing` - Agent is thinking
- `event` - DeltaBus event (agent.*, session.*, tool.*)
- `response` - Streaming response chunk
- `response_final` - Complete response with metadata
- `delta` - Memory delta (episodic, semantic, learning)
- `tool_call` - Tool invocation
- `completed` - Agent task completed
- `error` - Error occurred

### REST API (Non-Streaming)

**POST /chat**
```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "How is my recovery going?",
    "user_id": "demo_user"
  }'
```

**Response:**
```json
{
  "message": "**Current Assessment...**",
  "trace_id": "trace_20251107...",
  "session_id": "session_abc123",
  "envelope_id": "env_xyz789",
  "latency_ms": 6500.0,
  "metadata": {...}
}
```

**GET /health**
```bash
curl http://localhost:8000/health
```

**Response:**
```json
{
  "status": "operational",
  "components": {
    "Concierge Agent": "RUNNING",
    "DeltaBus": "RUNNING",
    ...
  },
  "uptime_seconds": 120.5
}
```

**GET /**
```bash
curl http://localhost:8000/
```

API info and available endpoints.

## 🧪 Testing

### WebSocket Test Client

```bash
python test_websocket_client.py
```

Tests:
1. ✅ Connection establishment
2. ✅ Single message streaming (Healthcare query)
3. ✅ Multi-turn conversation (Planning query)
4. ✅ Heartbeat (Ping/Pong)
5. ✅ REST API fallback

### Manual Testing with wscat

```bash
# Install wscat
npm install -g wscat

# Connect
wscat -c ws://localhost:8000/ws/chat/test_user

# Send message
> {"type": "message", "text": "How's my recovery?"}

# Watch events stream in real-time
```

### Browser Testing (JavaScript)

```javascript
const ws = new WebSocket('ws://localhost:8000/ws/chat/browser_user');

ws.onopen = () => {
  console.log('Connected!');
  ws.send(JSON.stringify({
    type: 'message',
    text: "What's my health status?"
  }));
};

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Event:', data.type, data);

  if (data.type === 'response_final') {
    console.log('Response:', data.content);
  }
};
```

## 🏗️ Architecture

### System Initialization (Startup)

```
FastAPI Startup Event
  ↓
SystemCoordinator.initialize_system()
  ↓
7-Phase Init (from system_coordinator.py)
  1. Configuration & Registries
  2. Runtime Infrastructure (DeltaBus, MailboxManager)
  3. Mock Services (MCP, K0 SSE, K0 API)
  4. Core Agents (Concierge, Proactive)
  5. Background Services (Writer Agents)
  6. Orchestration Layer (Planner, Orchestrator)
  7. System Health Check
  ↓
API Ready for WebSocket Connections
```

### Message Flow (WebSocket)

```
Client WebSocket Message
  ↓
IntentRouter.route_user_input()
  ↓
Concierge Mailbox (MPSC queue)
  ↓
ConciergeAgent.process_message()
  ↓
DeltaBus Events Published
  ├─ agent.task_received
  ├─ agent.task_completed
  ├─ session.delta
  └─ response.env_*
  ↓
WebSocket Event Handler
  ↓
Stream to Client (real-time)
```

### Components Reused

From `system_coordinator.py`:
- ✅ SystemCoordinator (singleton)
- ✅ DeltaBus (event streaming)
- ✅ MailboxManager (message queuing)
- ✅ ConciergeAgent (Tier 1 agent)
- ✅ IntentRouter (mailbox routing)
- ✅ SessionStateManager (session tracking)

From `run_e2e_paths.py`:
- ✅ DeltaBus subscription pattern (lines 106-117)
- ✅ IntentRouter mailbox flow (lines 154-170)
- ✅ Event streaming logic (lines 109-116)

**Zero code duplication!** All business logic reused from existing components.

## 🐳 Docker Deployment

### Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Copy dependencies
COPY requirements.txt requirements-api.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-api.txt

# Copy application
COPY . .

# Expose port
EXPOSE 8000

# Run API
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
```

### Build & Run

```bash
# Build
docker build -t k1-chat-api .

# Run
docker run -p 8000:8000 \
  -e GROQ_API_KEY=$GROQ_API_KEY \
  -e GROQ_MODEL=groq/compound \
  k1-chat-api
```

### Docker Compose

```yaml
version: '3.8'

services:
  k1-api:
    build: .
    ports:
      - "8000:8000"
    environment:
      - GROQ_API_KEY=${GROQ_API_KEY}
      - GROQ_MODEL=groq/compound
      - K1_ENVIRONMENT=production
    restart: unless-stopped
```

## 📊 Performance

**Startup Time:** ~5-6 seconds (7-phase initialization)

**Message Latency (P95):**
- Query intent (specialist): ~6.5s
- Planning intent (orchestrator): ~1.4s

**Event Streaming:** <10ms per event (DeltaBus target: <1ms)

**Memory:** ~450MB baseline + ~50MB per active session

**Concurrent Connections:** Tested up to 100 simultaneous WebSocket connections

## 🔧 Configuration

### Environment Variables

```bash
# Groq API (required)
GROQ_API_KEY=your_api_key_here
GROQ_MODEL=groq/compound

# K1 Configuration
K1_ENVIRONMENT=development  # or production
K1_LOG_LEVEL=info
K1_TRACE_ENABLED=true

# API Server
API_HOST=0.0.0.0
API_PORT=8000
API_WORKERS=1  # MUST be 1 for singleton
```

### CORS Configuration

Edit `api.py` line 75:
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://yourdomain.com"],  # Production: Restrict origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

## 🐛 Troubleshooting

### API Won't Start

**Problem:** `System not ready` or initialization errors

**Solution:**
1. Check GROQ_API_KEY is set: `echo $GROQ_API_KEY`
2. Verify config files exist:
   - `config/poc_config.yml`
   - `config/perf.yml`
   - `config/tool_registry.json`
   - `config/prompt_registry.json`
3. Check logs for Phase 1-7 initialization errors

### WebSocket Connection Refused

**Problem:** `Connection refused` or timeout

**Solution:**
1. Ensure API is running: `curl http://localhost:8000/`
2. Check firewall allows port 8000
3. Verify WebSocket URL: `ws://` not `wss://` (unless SSL)

### Events Not Streaming

**Problem:** Connected but no events received

**Solution:**
1. Check DeltaBus subscriptions in logs
2. Verify session_id filtering is correct
3. Test with `test_websocket_client.py`

### High Latency

**Problem:** Responses take >10s

**Solution:**
1. Check GROQ_MODEL is fast model (groq/compound)
2. Monitor LLM API latency in logs
3. Verify network connection to Groq API
4. Check system health: `curl http://localhost:8000/health`

## 📚 References

- **System Coordinator**: `system_coordinator.py` - 7-phase initialization
- **E2E Test Runner**: `scripts/run_e2e_paths.py` - DeltaBus patterns
- **Intent Router**: `l1_input/intent_router.py` - Mailbox routing
- **DeltaBus**: `l4_runtime/deltabus/deltabus.py` - Event pub/sub
- **Mailbox Rewire Plan**: `poc/chat_experience_poc_mailbox_rewire_plan.md`

## 📄 License

Same as parent project (FamilyOS).

## 🤝 Contributing

See `CONTRIBUTING.md` in project root.

---

**Built with:** FastAPI, WebSocket, SystemCoordinator, DeltaBus, MailboxManager

**Zero code duplication** - 100% reuse of existing K1 Intelligence Module components! 🚀
