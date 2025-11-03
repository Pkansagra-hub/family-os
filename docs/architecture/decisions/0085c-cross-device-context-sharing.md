---
adr_number: 0085c
title: Cross-Device Context Sharing & Presence-Aware Features
status: PROPOSED
date_created: '2025-11-03'
date_updated: '2025-11-03'
authors:
- K1 Architecture Team
affected_layers:
- layer1_input
- layer4_runtime
affected_modules: []
concerns:
- architecture
- observability
- performance
- privacy
- reliability
- scalability
supersedes: []
superseded_by: []
related_adrs:
- ADR-0017
- ADR-0032
- ADR-0050
- ADR-0085
- ADR-0085a
- ADR-0085b
implementation_status: PLANNED
implementation_date: null
implementation_phase: null
related_contracts: []
related_diagrams: []
research_citations: []
propagation:
  triggers:
  - Modifying system architecture
  - Performance requirement changes
  affected_adrs:
  - ADR-0017
  - ADR-0032
  - ADR-0050
  - ADR-0085
  - ADR-0085a
  - ADR-0085b
  affected_contracts: []
  affected_tests: []
---


# ADR-0085c: Cross-Device Context Sharing & Presence-Aware Features

**Status:** Proposed 🔄
**Parent ADR:** ADR-0085 (Embodied Awareness & Device Presence)
**Last Updated:** 2025-01-22

---

## Context

**From ADR-0085:** Embodied Awareness Layer requires **cross-device coordination** to share presence context and enable **presence-aware features** (smart notification routing, device handoff suggestions, preference learning).

**Key Requirements:**

1. **Context Sharing:** Sync presence metadata across family devices (privacy-aware)
2. **Notification Coordination:** Send notifications to active device only (suppress inactive devices)
3. **Smart Handoff:** Detect device switches, suggest resuming context on new device
4. **Preference Learning:** Learn user device preferences (laptop for writing, phone for quick queries)

**Use Cases:**

- User switches from phone → laptop → Send notification to laptop only
- User walks away from laptop → Detect laptop inactive → Route notifications to phone
- User asks question on phone, walks to laptop → Suggest resuming conversation on laptop
- User prefers laptop for long responses → Automatically switch to laptop for multi-paragraph answers

---

## Decision

Implement **four-component cross-device architecture**:

### Component 1: Presence Context Syncer (CRDT-based Metadata Exchange)
### Component 2: Notification Coordinator (Active Device Routing)
### Component 3: Smart Handoff Suggester (Context Resumption)
### Component 4: Device Preference Learner (Usage Pattern Detection)

---

## Component 1: Presence Context Syncer

### CRDT-Based Metadata Exchange

**Goal:** Sync presence metadata across family devices via ADR-0050 K0 P07.

```python
class PresenceContextSyncer:
    """
    Sync presence metadata across family devices.

    Sync protocol:
    - Use K0 P07 (ADR-0050) CRDT sync for presence metadata
    - Broadcast updates every 30 seconds (heartbeat interval)
    - Apply privacy transforms before sync (RED → GREEN degradation)

    Metadata fields:
    - device_id: String
    - online_status: ONLINE | OFFLINE
    - last_seen: Timestamp
    - coarse_location: City-level string (privacy-safe)
    - proximity_devices: List[DeviceID] (devices in NEAR zone)
    - active_session: Bool (screen + input + foreground app)
    - motion_context: STATIONARY | IN_POCKET | BEING_HELD | IN_VEHICLE | WALKING | RUNNING
    - battery_level: 0-100
    - charging_status: CHARGING | DISCHARGING | FULL
    - power_mode: LOW_POWER | NORMAL | HIGH_PERFORMANCE
    """

    def __init__(self, device_id: str, family_id: str):
        self.device_id = device_id
        self.family_id = family_id
        self.local_presence = None
        self.remote_devices = {}  # device_id → PresenceMetadata
        self.sync_interval_seconds = 30

    async def sync_presence_loop(self):
        """
        Sync presence metadata every 30 seconds.
        """
        while True:
            # Gather local presence metadata
            self.local_presence = await self.gather_local_presence()

            # Apply privacy transforms
            public_presence = self.apply_privacy_transforms(self.local_presence)

            # Broadcast via K0 P07 CRDT sync
            await self.broadcast_presence(public_presence)

            # Fetch remote device presence
            self.remote_devices = await self.fetch_remote_presence()

            # Wait 30 seconds
            await asyncio.sleep(self.sync_interval_seconds)

    async def gather_local_presence(self) -> PresenceMetadata:
        """
        Gather local presence metadata from all components.
        """
        # Get device presence (ADR-0085a)
        device_presence = await device_presence_detector.get_presence()

        # Get location (ADR-0085a)
        location = await location_tracker.get_location()

        # Get BLE proximity devices (ADR-0085b)
        proximity_devices = await ble_proximity_sensor.get_nearby_devices()

        # Get active session state (ADR-0085b)
        active_session = await active_session_monitor.is_active()

        # Get motion context (ADR-0085b)
        motion_context = await motion_sensor_integrator.get_context()

        # Get power state (ADR-0085b)
        power_state = await power_state_monitor.get_power_state()

        return PresenceMetadata(
            device_id=self.device_id,
            online_status=device_presence.online_status,
            last_seen=now(),
            location=location,
            proximity_devices=[d.device_id for d in proximity_devices],
            active_session=active_session,
            motion_context=motion_context.value,
            battery_level=power_state.battery_level,
            charging_status=power_state.charging_status.value,
            power_mode=power_state.power_mode.value
        )

    def apply_privacy_transforms(self, presence: PresenceMetadata) -> PresenceMetadata:
        """
        Apply privacy transforms before syncing.

        Rules:
        - RED location (GPS) → Degrade to GREEN city-level
        - AMBER location (WiFi SSID) → Hash SSID before sync
        - GREEN location (IP geolocation) → Sync as-is
        - Proximity devices → Keep (family-scoped UUIDs already private)
        - Active session → Keep (boolean flag, low privacy risk)
        - Motion context → Keep (enum value, no PII)
        - Battery/power → Keep (numeric values, no PII)
        """
        public_presence = presence.copy()

        # Apply location privacy transform (from ADR-0085a)
        public_presence.location = apply_location_privacy(presence.location)

        return public_presence

    async def broadcast_presence(self, presence: PresenceMetadata):
        """
        Broadcast presence metadata via K0 P07 CRDT sync.

        Sync protocol:
        1. Write to local KV store: key = "presence:<device_id>", value = JSON(presence)
        2. K0 P07 detects local write
        3. K0 P07 broadcasts CRDT update to all family devices (mDNS LAN + cloud fallback)
        4. Remote devices merge update into their local KV stores
        """
        key = f"presence:{self.device_id}"
        value = json.dumps(presence.to_dict())

        # Write to local KV store (triggers K0 P07 sync)
        await kv_put(key, value)

        logger.debug(
            "presence_broadcasted",
            device_id=self.device_id,
            online_status=presence.online_status,
            active_session=presence.active_session,
            motion_context=presence.motion_context
        )

    async def fetch_remote_presence(self) -> Dict[str, PresenceMetadata]:
        """
        Fetch presence metadata from all family devices.

        Query:
        1. List all keys matching "presence:*" in local KV store
        2. Parse JSON values into PresenceMetadata objects
        3. Return dictionary: device_id → PresenceMetadata
        """
        remote_devices = {}

        # List all presence keys
        presence_keys = await kv_list_keys(prefix="presence:")

        for key in presence_keys:
            device_id = key.split(":")[1]

            # Skip self
            if device_id == self.device_id:
                continue

            # Fetch presence metadata
            value = await kv_get(key)
            presence = PresenceMetadata.from_dict(json.loads(value))

            remote_devices[device_id] = presence

        return remote_devices
```

---

## Component 2: Notification Coordinator

### Active Device Routing

**Goal:** Send notifications to active device only (suppress inactive devices).

```python
class NotificationCoordinator:
    """
    Coordinate notifications across family devices.

    Routing rules:
    1. If single active device → Send to active device only
    2. If multiple active devices → Send to most recently active
    3. If no active devices → Send to all online devices
    4. If user explicitly specifies device → Override routing logic

    Suppression rules:
    - Suppress device if screen OFF
    - Suppress device if no input for >5 minutes
    - Suppress device if battery <10% (LOW_POWER mode)
    - Suppress device if motion context IN_POCKET or IN_BAG
    """

    def __init__(self):
        self.presence_syncer = None  # Injected

    async def route_notification(
        self,
        notification: Notification,
        user_id: str
    ) -> List[str]:
        """
        Determine target devices for notification.

        Returns: List of device IDs to send notification to
        """
        # Fetch all user devices
        all_devices = await self.get_user_devices(user_id)

        # Filter to online devices
        online_devices = [
            d for d in all_devices
            if self.presence_syncer.remote_devices.get(d.device_id, {}).get("online_status") == "ONLINE"
        ]

        if not online_devices:
            logger.warning("no_online_devices", user_id=user_id)
            return []

        # Check for user override
        if notification.target_device_id:
            return [notification.target_device_id]

        # Filter to active devices
        active_devices = self.filter_active_devices(online_devices)

        # Route to active device(s)
        if len(active_devices) == 1:
            # Single active device → Send to it only
            return [active_devices[0].device_id]

        elif len(active_devices) > 1:
            # Multiple active devices → Send to most recently active
            most_recent = max(
                active_devices,
                key=lambda d: self.presence_syncer.remote_devices[d.device_id].last_seen
            )
            return [most_recent.device_id]

        else:
            # No active devices → Send to all online devices
            logger.info(
                "no_active_devices_fallback",
                user_id=user_id,
                online_count=len(online_devices)
            )
            return [d.device_id for d in online_devices]

    def filter_active_devices(self, devices: List[Device]) -> List[Device]:
        """
        Filter to devices that are actively used.

        Active criteria:
        - active_session = True (screen on + recent input)
        - motion_context NOT IN [IN_POCKET, IN_BAG]
        - power_mode NOT LOW_POWER (battery >20%)
        """
        active_devices = []

        for device in devices:
            presence = self.presence_syncer.remote_devices.get(device.device_id)

            if not presence:
                continue

            # Check active session
            if not presence.active_session:
                continue

            # Check motion context (skip if in pocket/bag)
            if presence.motion_context in ["IN_POCKET", "IN_BAG"]:
                continue

            # Check power mode (skip if battery critical)
            if presence.power_mode == "LOW_POWER":
                continue

            active_devices.append(device)

        return active_devices
```

### Notification Suppression

```python
class NotificationSuppressor:
    """
    Suppress notifications on inactive devices.

    When notification sent to active device only, suppress on other devices:
    - Show "delivered to laptop" message on phone
    - Don't vibrate/sound on inactive devices
    - Mark notification as "seen" on all devices when read on any device
    """

    async def suppress_on_inactive_devices(
        self,
        notification: Notification,
        active_device_id: str,
        all_device_ids: List[str]
    ):
        """
        Suppress notification on inactive devices.
        """
        inactive_device_ids = [
            d for d in all_device_ids
            if d != active_device_id
        ]

        for device_id in inactive_device_ids:
            # Send suppression signal
            await self.send_suppression_signal(device_id, notification.id)

            logger.debug(
                "notification_suppressed",
                notification_id=notification.id,
                device_id=device_id,
                active_device=active_device_id
            )

    async def mark_seen_on_all_devices(
        self,
        notification_id: str,
        seen_on_device_id: str,
        all_device_ids: List[str]
    ):
        """
        Mark notification as seen on all devices when read on any device.
        """
        for device_id in all_device_ids:
            if device_id == seen_on_device_id:
                continue

            # Send "seen" signal
            await self.send_seen_signal(device_id, notification_id)

            logger.debug(
                "notification_synced_seen",
                notification_id=notification_id,
                device_id=device_id,
                seen_on_device=seen_on_device_id
            )
```

---

## Component 3: Smart Handoff Suggester

### Device Switch Detection

**Goal:** Detect device switches and suggest resuming context on new device.

```python
class SmartHandoffSuggester:
    """
    Suggest resuming context when user switches devices.

    Detection criteria:
    1. Previous device became inactive (active_session: True → False)
    2. New device became active (active_session: False → True)
    3. Time gap <5 minutes (likely same conversation)
    4. Devices in proximity (BLE NEAR/MEDIUM zone)

    Suggestion types:
    - RESUME_CONVERSATION: "You switched from phone to laptop. Resume here?"
    - CONTINUE_TASK: "Continue writing document on laptop?"
    - HANDOFF_MEDIA: "Continue playing music on speaker?"
    """

    def __init__(self):
        self.presence_syncer = None  # Injected
        self.recent_switches = []    # List[(from_device_id, to_device_id, timestamp)]

    async def monitor_device_switches(self):
        """
        Monitor presence metadata for device switches (1 Hz).
        """
        previous_active_device = None

        while True:
            # Determine currently active device
            current_active_device = self.get_active_device()

            # Detect device switch
            if current_active_device and current_active_device != previous_active_device:
                await self.handle_device_switch(
                    from_device=previous_active_device,
                    to_device=current_active_device
                )

            previous_active_device = current_active_device

            # Wait 1 second
            await asyncio.sleep(1)

    def get_active_device(self) -> Optional[str]:
        """
        Get currently active device ID.

        Returns: Device ID with active_session=True, or None if no active device
        """
        for device_id, presence in self.presence_syncer.remote_devices.items():
            if presence.active_session:
                return device_id

        return None

    async def handle_device_switch(
        self,
        from_device: Optional[str],
        to_device: str
    ):
        """
        Handle device switch event.
        """
        # Skip if no previous device (first activation)
        if not from_device:
            return

        # Check if devices in proximity
        to_device_presence = self.presence_syncer.remote_devices[to_device]

        if from_device not in to_device_presence.proximity_devices:
            logger.debug(
                "device_switch_not_proximate",
                from_device=from_device,
                to_device=to_device
            )
            return

        # Record switch
        self.recent_switches.append((from_device, to_device, now()))

        # Fetch active session context from previous device
        session_context = await self.fetch_session_context(from_device)

        if not session_context:
            logger.debug(
                "device_switch_no_context",
                from_device=from_device,
                to_device=to_device
            )
            return

        # Generate handoff suggestion
        suggestion = self.generate_handoff_suggestion(
            from_device=from_device,
            to_device=to_device,
            session_context=session_context
        )

        # Send suggestion to new device
        await self.send_handoff_suggestion(to_device, suggestion)

        logger.info(
            "device_switch_suggestion",
            from_device=from_device,
            to_device=to_device,
            suggestion_type=suggestion.type,
            session_id=session_context.session_id
        )

    async def fetch_session_context(self, device_id: str) -> Optional[SessionContext]:
        """
        Fetch active session context from device.

        Query: K0 KV store for "session:active:<device_id>"

        Returns: SessionContext or None if no active session
        """
        key = f"session:active:{device_id}"
        value = await kv_get(key)

        if not value:
            return None

        return SessionContext.from_dict(json.loads(value))

    def generate_handoff_suggestion(
        self,
        from_device: str,
        to_device: str,
        session_context: SessionContext
    ) -> HandoffSuggestion:
        """
        Generate handoff suggestion based on session context.

        Suggestion types:
        - RESUME_CONVERSATION: Active conversation within 5 minutes
        - CONTINUE_TASK: Document editing, form filling
        - HANDOFF_MEDIA: Music, video playback
        """
        # Check session recency (within 5 minutes)
        time_since_last_turn = now() - session_context.last_turn_timestamp

        if time_since_last_turn > 300:  # 5 minutes
            return None

        # Determine suggestion type
        if session_context.has_active_media:
            suggestion_type = SuggestionType.HANDOFF_MEDIA
            message = f"Continue playing {session_context.media_title} here?"

        elif session_context.has_active_document:
            suggestion_type = SuggestionType.CONTINUE_TASK
            message = f"Continue editing {session_context.document_title}?"

        else:
            suggestion_type = SuggestionType.RESUME_CONVERSATION
            message = f"You switched from {self.get_device_name(from_device)} to {self.get_device_name(to_device)}. Resume here?"

        return HandoffSuggestion(
            type=suggestion_type,
            message=message,
            session_id=session_context.session_id,
            from_device=from_device,
            to_device=to_device
        )
```

---

## Component 4: Device Preference Learner

### Usage Pattern Detection

**Goal:** Learn user device preferences from historical usage patterns.

```python
class DevicePreferenceLearner:
    """
    Learn user device preferences from usage patterns.

    Patterns detected:
    - Device preference by task type (laptop for writing, phone for quick queries)
    - Device preference by time of day (phone in morning, laptop during work hours)
    - Device preference by location (phone when traveling, laptop at home/work)
    - Response length patterns (laptop for long responses, phone for short)

    Learning approach:
    - Track device used for each session turn
    - Aggregate patterns over 30-day sliding window
    - Calculate preference scores (0.0-1.0) per device-context pair
    - Use scores to predict preferred device for new requests
    """

    def __init__(self):
        self.usage_history = []  # List[UsageEvent]
        self.preference_model = {}  # (device_id, context) → score
        self.learning_window_days = 30

    async def record_usage(
        self,
        session_id: str,
        device_id: str,
        task_type: str,
        location: str,
        time_of_day: str,
        response_length: int
    ):
        """
        Record device usage for learning.
        """
        usage_event = UsageEvent(
            timestamp=now(),
            session_id=session_id,
            device_id=device_id,
            task_type=task_type,
            location=location,
            time_of_day=time_of_day,
            response_length=response_length
        )

        self.usage_history.append(usage_event)

        # Trim history to 30-day window
        cutoff = now() - timedelta(days=self.learning_window_days)
        self.usage_history = [
            e for e in self.usage_history
            if e.timestamp > cutoff
        ]

    async def update_preference_model(self):
        """
        Update preference model from usage history (daily).
        """
        # Aggregate usage counts per (device, context) pair
        counts = defaultdict(int)  # (device_id, context) → count

        for event in self.usage_history:
            context = self.extract_context(event)
            counts[(event.device_id, context)] += 1

        # Calculate preference scores
        for (device_id, context), count in counts.items():
            # Total usage for this context across all devices
            total_count = sum(
                c for (d, ctx), c in counts.items()
                if ctx == context
            )

            # Preference score = device usage / total usage
            score = count / total_count

            self.preference_model[(device_id, context)] = score

        logger.info(
            "preference_model_updated",
            model_size=len(self.preference_model),
            history_size=len(self.usage_history)
        )

    def extract_context(self, event: UsageEvent) -> str:
        """
        Extract context key from usage event.

        Context keys:
        - "<task_type>" (e.g., "writing", "quick_query")
        - "<location>" (e.g., "HOME", "WORK", "TRAVELING")
        - "<time_of_day>" (e.g., "morning", "afternoon", "evening")
        - "<response_length>" (e.g., "short", "medium", "long")
        """
        # Primary context: Task type
        context = event.task_type

        # Secondary context: Location (if strong signal)
        if event.location in ["HOME", "WORK"]:
            context += f"_{event.location}"

        # Tertiary context: Time of day (if strong signal)
        if event.time_of_day in ["morning", "evening"]:
            context += f"_{event.time_of_day}"

        return context

    async def predict_preferred_device(
        self,
        user_id: str,
        task_type: str,
        location: str,
        time_of_day: str
    ) -> Optional[str]:
        """
        Predict preferred device for given context.

        Returns: Device ID with highest preference score, or None if no preference
        """
        # Extract context key
        context = f"{task_type}_{location}_{time_of_day}"

        # Find devices with preference scores for this context
        candidates = [
            (device_id, score)
            for (device_id, ctx), score in self.preference_model.items()
            if ctx == context
        ]

        if not candidates:
            # No preference data for this context
            return None

        # Sort by preference score (descending)
        candidates.sort(key=lambda x: x[1], reverse=True)

        # Return device with highest preference score
        preferred_device_id, score = candidates[0]

        # Require minimum confidence threshold (>0.6)
        if score < 0.6:
            return None

        logger.info(
            "preferred_device_predicted",
            device_id=preferred_device_id,
            score=round(score, 2),
            context=context
        )

        return preferred_device_id
```

---

## Performance Characteristics

| Operation | Target Latency (P95) | Storage Impact |
|-----------|---------------------|----------------|
| Presence metadata sync (30s interval) | <200ms | ~1 KB per device |
| Notification routing decision | <50ms | N/A |
| Device switch detection | <1 second | N/A |
| Handoff suggestion generation | <100ms | N/A |
| Preference model update (daily) | <5 seconds | ~10 KB per user |
| Preferred device prediction | <10ms | N/A |

---

## Observability

### Metrics

```python
presence_sync_latency_ms = Histogram(
    'presence_sync_latency_ms',
    'Presence metadata sync latency',
    buckets=[10, 50, 100, 200, 500]
)

notification_routing_decisions = Counter(
    'notification_routing_decisions',
    'Notification routing decisions',
    ['routing_type']  # active_device, all_devices, user_override
)

device_switches_detected = Counter(
    'device_switches_detected',
    'Device switch events detected'
)

handoff_suggestions_sent = Counter(
    'handoff_suggestions_sent',
    'Handoff suggestions sent',
    ['suggestion_type']  # RESUME_CONVERSATION, CONTINUE_TASK, HANDOFF_MEDIA
)

device_preference_score = Histogram(
    'device_preference_score',
    'Device preference scores',
    buckets=[0.1, 0.3, 0.5, 0.7, 0.9]
)
```

### Events

```text
presence.sync.success            — Presence metadata synced successfully
presence.sync.failure            — Presence metadata sync failed
notification.routed              — Notification routed to device(s)
notification.suppressed          — Notification suppressed on device
device.switch.detected           — Device switch detected
handoff.suggestion.sent          — Handoff suggestion sent
handoff.suggestion.accepted      — User accepted handoff suggestion
handoff.suggestion.dismissed     — User dismissed handoff suggestion
preference.model.updated         — Device preference model updated
preference.device.predicted      — Preferred device predicted
```

---

## Related ADRs

- **ADR-0085:** Embodied Awareness & Device Presence (parent)
- **ADR-0085a:** Device Presence Detection & Location Awareness
- **ADR-0085b:** BLE Proximity & Active Session Tracking
- **ADR-0050:** Multi-Device Family Sync (K0 P07 CRDT sync foundation)
- **ADR-0017:** SessionState (Section 5 multimodal context storage)
- **ADR-0032:** Privacy Bands (RED/AMBER/GREEN classification)

---

## End of ADR-0085c