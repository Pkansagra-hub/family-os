"""
Intent Router - Layer 1 Ingress Point for All User Messages

The Intent Router is the first component users interact with. It:
1. Generates cognitive_trace_id at ingress for end-to-end tracing
2. Creates/retrieves SessionState from SessionStateManager
3. Bootstraps new sessions with User KG data
4. Handles CLI commands (/help, /status, /agents, /exit)
5. Creates Envelope with metadata and routes to Concierge
6. Provides observability: metrics, logging, tracing

Performance Budget: <5ms P95 (fast ingress, before Concierge processing)

References:
- docs/plans/chat_experience_poc_plan.md - Issue 6.5.1.1 (Intent Router Design)
- ADR-0017 - SessionState structure
- docs/whiteboard/chat_experience.md - Intent Router ingress flow
"""

import threading
import time
import uuid
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

from l4_runtime.deltabus.deltabus import DeltaBus
from l4_runtime.mailbox.mailbox import Message, Priority
from l4_runtime.session_state.session_state_manager import SessionStateManager
from models.envelope import Envelope, EnvelopeHeader, EnvelopePayload, QoSBand
from utils.awaiters import AwaiterTimeout, await_response

# Thread-local storage for trace_id propagation
_trace_context = threading.local()


class IntentRouter:
    """
    Intent Router - Layer 1 Ingress for All User Messages

    Responsibilities:
    - Generate cognitive_trace_id at ingress
    - Create/retrieve SessionState
    - Bootstrap new sessions with User KG
    - Handle CLI commands
    - Route to Concierge via mailbox
    - Track metrics and latency

    Dependencies:
    - SessionStateManager: For session creation/retrieval
    - DeltaBus: For publishing response events
    - Mailbox (from Concierge's mailbox manager): For routing

    Fields:
        session_manager: SessionStateManager instance
        deltabus: DeltaBus instance for events
        concierge_agent_id: ID of Concierge agent ("concierge-1")
        command_handlers: Dict of command name → handler function
    """

    def __init__(
        self,
        session_manager: SessionStateManager,
        deltabus: DeltaBus,
        mailbox_manager: Any,
    ):
        """
        Initialize Intent Router

        Args:
            session_manager: SessionStateManager for session lifecycle
            deltabus: DeltaBus for event publishing and response listening
            mailbox_manager: MailboxManager for routing to Concierge mailbox (REQUIRED)
        """
        self.session_manager = session_manager
        self.deltabus = deltabus
        self.mailbox_manager = mailbox_manager
        self.concierge_agent_id = "concierge_001"  # Match SystemCoordinator agent ID

        # Performance tracking
        self._request_count = 0
        self._total_latency_ms = 0.0
        self._latencies: list[float] = []  # For P95 calculation

        # Command handlers (register CLI commands)
        self.command_handlers: Dict[str, Any] = {
            "/help": self._handle_help_command,
            "/status": self._handle_status_command,
            "/agents": self._handle_agents_command,
            "/dashboard": self._handle_dashboard_command,
            "/exit": self._handle_exit_command,
        }

        # Register with ComponentRegistry for dashboard visibility
        try:
            from monitoring.component_registry import ComponentRegistry

            reg = ComponentRegistry.inst()
            reg.register("Intent Router")
            reg.set("Intent Router", "RUNNING", details="idle")
        except Exception:
            pass  # Registry optional for now

        print("[IntentRouter] Initialized with mailbox flow", flush=True)

    @staticmethod
    def get_trace_id() -> Optional[str]:
        """
        Get current trace_id from thread-local context.

        Returns:
            trace_id if set, otherwise None
        """
        return getattr(_trace_context, "trace_id", None)

    @staticmethod
    def set_trace_id(trace_id: str) -> None:
        """
        Set trace_id in thread-local context for propagation.

        Args:
            trace_id: Cognitive trace ID to propagate
        """
        _trace_context.trace_id = trace_id

    async def route_user_input(
        self,
        user_input: str,
        user_id: str,
        session_id: Optional[str] = None,
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Route user input through Intent Router - Main Entry Point

        Step 1: Generate cognitive_trace_id
        Step 2: Session management (create/retrieve)
        Step 3: Normalize input (trim, detect commands)
        Step 4: Handle CLI commands or create envelope
        Step 5: Route to Concierge
        Step 6: Wait for response via DeltaBus

        Args:
            user_input: Raw user message text
            user_id: User ID for this request
            session_id: Optional existing session ID (auto-create if None)

        Returns:
            Tuple of (response_text, metadata_dict)

        Raises:
            ValueError: If session creation fails
            TimeoutError: If Concierge doesn't respond within 5s
        """
        start_time = time.time()

        # Step 1: Generate cognitive_trace_id
        # Format: trace_{timestamp_10d}_{uuid4_12c}
        # Example: trace_20251105143025_a1b2c3d4e5f6
        timestamp_str = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        trace_id = f"trace_{timestamp_str}_{uuid.uuid4().hex[:12]}"
        self.set_trace_id(trace_id)

        print(
            f"[IntentRouter] New request: trace_id={trace_id}, user_id={user_id}",
            flush=True,
        )

        try:
            # Step 2: Session management
            if session_id is None:
                # Create new session
                try:
                    session_state = self.session_manager.create_session(
                        user_id=user_id,
                        cognitive_trace_id=trace_id,
                    )
                    session_id = session_state.session_id
                    print(
                        f"[IntentRouter] Created new session: {session_id}",
                        flush=True,
                    )
                except ValueError as e:
                    print(f"[IntentRouter] Session creation failed: {str(e)}", flush=True)
                    return ("System error: Could not create session", {"error": str(e)})
            else:
                # Retrieve existing session
                try:
                    session_state = self.session_manager.get_session(session_id)
                    if session_state is None:
                        print(
                            "[IntentRouter] Session not found, creating new",
                            flush=True,
                        )
                        session_state = self.session_manager.create_session(
                            user_id=user_id,
                            cognitive_trace_id=trace_id,
                        )
                        session_id = session_state.session_id
                except Exception as e:
                    print(f"[IntentRouter] Session retrieval failed: {str(e)}", flush=True)
                    return ("System error: Could not access session", {"error": str(e)})

            # Step 3: Normalize input
            normalized_input = user_input.strip()

            # Step 4: Check for CLI commands
            for command, handler in self.command_handlers.items():
                if normalized_input.lower().startswith(command):
                    result = handler(session_state)
                    latency_ms = (time.time() - start_time) * 1000
                    print(
                        f"[IntentRouter] Command handled: {command} ({latency_ms:.2f}ms)",
                        flush=True,
                    )
                    self._record_latency(latency_ms)
                    return result

            # Step 5: Create envelope for Concierge
            envelope = self._create_envelope(
                trace_id=trace_id,
                session_id=session_id,
                user_id=user_id,
                user_input=normalized_input,
                session_state=session_state,
            )

            # Step 5b: Send envelope to Concierge via mailbox
            concierge_mailbox = self.mailbox_manager.get_mailbox(self.concierge_agent_id)
            if concierge_mailbox is None:
                print(
                    "[IntentRouter] ERROR: Concierge mailbox not found",
                    flush=True,
                )
                return (
                    "System error: Concierge unavailable",
                    {"error": "concierge_mailbox_not_found", "trace_id": trace_id},
                )

            # Convert Envelope to Message for mailbox send
            message = Message(
                message_id=envelope.header.envelope_id,
                sender_id="intent_router",
                receiver_id=self.concierge_agent_id,
                priority=Priority.STANDARD,  # INTERACTIVE QoS maps to STANDARD priority
                payload=envelope.to_dict(),  # Serialize envelope as payload
                trace_id=envelope.header.trace_id,
            )

            # Send message to Concierge's mailbox
            sent = await concierge_mailbox.send(message)
            if not sent:
                print(
                    f"[IntentRouter] ERROR: Failed to send envelope (mailbox full): {envelope.header.envelope_id}",
                    flush=True,
                )
                return (
                    "System busy, please try again",
                    {"error": "mailbox_full", "trace_id": trace_id},
                )

            print(
                f"[IntentRouter] Sent envelope to Concierge mailbox: {envelope.header.envelope_id}",
                flush=True,
            )

            # Step 6: Wait for response from Concierge via DeltaBus (25s timeout)
            try:
                response_data = await await_response(
                    envelope_id=envelope.header.envelope_id,
                    deltabus=self.deltabus,
                    timeout=25.0,  # Increased from 15s to allow for orchestrator + planner LLM calls
                    trace_id=trace_id,
                )

                latency_ms = (time.time() - start_time) * 1000
                self._record_latency(latency_ms)

                print(
                    f"[IntentRouter] Response received: latency={latency_ms:.2f}ms",
                    flush=True,
                )

                return (
                    response_data.get("message", "No response from Concierge"),
                    {
                        "trace_id": trace_id,
                        "cognitive_trace_id": trace_id,  # Add for backward compatibility
                        "session_id": session_id,
                        "envelope_id": envelope.header.envelope_id,
                        "latency_ms": latency_ms,
                        "metadata": response_data.get("metadata", {}),
                    },
                )

            except AwaiterTimeout as e:
                latency_ms = (time.time() - start_time) * 1000
                self._record_latency(latency_ms)
                print(
                    f"[IntentRouter] Concierge timeout after {latency_ms:.0f}ms: {str(e)}",
                    flush=True,
                )
                return (
                    "System busy, please try again",
                    {
                        "error": "timeout",
                        "trace_id": trace_id,
                        "session_id": session_id,
                        "latency_ms": latency_ms,
                    },
                )

        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            self._record_latency(latency_ms)
            print(f"[IntentRouter] Request failed: {str(e)}", flush=True)
            return (f"System error: {str(e)}", {"error": str(e), "trace_id": trace_id})

    def _create_envelope(
        self,
        trace_id: str,
        session_id: str,
        user_id: str,
        user_input: str,
        session_state: Any,
    ) -> Envelope:
        """
        Create envelope for routing to Concierge

        Args:
            trace_id: Cognitive trace ID
            session_id: Session ID
            user_id: User ID
            user_input: User message text
            session_state: SessionState object (for user context)

        Returns:
            Envelope instance ready for routing
        """
        header = EnvelopeHeader(
            trace_id=trace_id,
            session_id=session_id,
            user_id=user_id,
            qos_band=QoSBand.INTERACTIVE,
            actor="intent_router",
        )

        # Extract user context from session_state (if available)
        user_context = {
            "user_id": user_id,
            "session_id": session_id,
            "turn_count": getattr(session_state.meta, "turn_count", 0) if session_state else 0,
        }

        payload = EnvelopePayload(
            message_type="user_input",
            content={
                "text": user_input,
                "timestamp": datetime.utcnow().isoformat(),
                "user_context": user_context,
            },
        )

        return Envelope(header=header, payload=payload)

    def _handle_help_command(self, session_state: Any) -> Tuple[str, Dict[str, Any]]:
        """Handle /help command"""
        help_text = """
K1 Intelligence Module - Chat Interface

Commands:
  /help      - Show this help message
  /status    - Show session status and stats
  /agents    - List active agents
  /dashboard - Show system health dashboard
  /exit      - Exit chat

Examples:
  "How's my recovery?"          - Query specialist
  "Remind me to drink water"    - Set prospective trigger
  "Book a restaurant"           - Multi-step planning task
        """
        return (help_text.strip(), {"command": "help"})

    def _handle_status_command(self, session_state: Any) -> Tuple[str, Dict[str, Any]]:
        """Handle /status command"""
        if session_state:
            turn_count = getattr(session_state.meta, "turn_count", 0)
            created_at = getattr(session_state.meta, "created_at", datetime.utcnow())
            uptime = (datetime.utcnow() - created_at).total_seconds()
            state_size = (
                len(str(session_state.to_dict())) if hasattr(session_state, "to_dict") else 0
            )
        else:
            turn_count = 0
            uptime = 0
            state_size = 0

        status_text = f"""
Session Status:
  Session ID: {session_state.session_id if session_state else "unknown"}
  Turns: {turn_count}
  Uptime: {uptime:.1f}s
  State Size: {state_size} bytes
        """
        return (status_text.strip(), {"command": "status"})

    def _handle_agents_command(self, session_state: Any) -> Tuple[str, Dict[str, Any]]:
        """Handle /agents command"""
        if session_state and hasattr(session_state, "control"):
            agent_roster = getattr(session_state.control, "agent_roster", [])
        else:
            agent_roster = []

        agents_text = f"""
Active Agents:
  {chr(10).join(f"  - {agent}" for agent in agent_roster) if agent_roster else "  (none)"}
        """
        return (agents_text.strip(), {"command": "agents", "agents": agent_roster})

    def _handle_exit_command(self, session_state: Any) -> Tuple[str, Dict[str, Any]]:
        """Handle /exit command"""
        session_id = session_state.session_id if session_state else "unknown"
        return ("Goodbye! 👋", {"command": "exit", "session_id": session_id})

    def _handle_dashboard_command(self, session_state: Any) -> Tuple[str, Dict[str, Any]]:
        """
        Handle /dashboard command (Issue 6.5.5.2)

        Shows Integration Health Dashboard with all component status
        """
        try:
            from monitoring.integration_dashboard import get_integration_dashboard

            get_integration_dashboard()
            # Note: display_status is async, so we return a placeholder
            # In production, this would be handled by async CLI
            dashboard_text = "Dashboard loading... (requires async context)"

            return (dashboard_text, {"command": "dashboard"})
        except Exception as e:
            return (f"Dashboard error: {e}", {"command": "dashboard", "error": str(e)})

    def _record_latency(self, latency_ms: float) -> None:
        """
        Record request latency for metrics

        Args:
            latency_ms: Latency in milliseconds
        """
        self._request_count += 1
        self._total_latency_ms += latency_ms
        self._latencies.append(latency_ms)

        # Keep only last 1000 latencies for P95 calculation
        if len(self._latencies) > 1000:
            self._latencies = self._latencies[-1000:]

    def get_metrics(self) -> Dict[str, Any]:
        """
        Get Intent Router metrics

        Returns:
            Dictionary with request count, latency stats, etc.
        """
        if not self._latencies:
            return {
                "request_count": 0,
                "avg_latency_ms": 0.0,
                "p50_latency_ms": 0.0,
                "p95_latency_ms": 0.0,
                "p99_latency_ms": 0.0,
            }

        sorted_latencies = sorted(self._latencies)
        return {
            "request_count": self._request_count,
            "avg_latency_ms": self._total_latency_ms / self._request_count,
            "p50_latency_ms": sorted_latencies[len(sorted_latencies) // 2],
            "p95_latency_ms": sorted_latencies[int(len(sorted_latencies) * 0.95)],
            "p99_latency_ms": sorted_latencies[int(len(sorted_latencies) * 0.99)],
        }

    def get_stats(self) -> Dict[str, Any]:
        """
        Get Intent Router stats (for dashboard compatibility).

        Returns:
            Dict with requests_total and avg_latency_ms
        """
        return {
            "requests_total": self._request_count,
            "avg_latency_ms": (
                self._total_latency_ms / self._request_count if self._request_count > 0 else 0.0
            ),
        }
