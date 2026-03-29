/**
 * FamilyOS K1 Concierge -- Premium Web UI
 *
 * WebSocket chat, real-time streaming, timeline visualization,
 * family member switching, affect display, system dashboard.
 * Apple-tier micro-interactions and animations throughout.
 */

// ================================================================
// State
// ================================================================

const state = {
    ws: null,
    connected: false,
    member: "Alex",
    device: "alex_phone",
    turn: 0,
    family: null,
    streamingMsgId: null,
    streamBuffer: "",
    thinkingBuffer: "",
    thinkingActive: false,
    _thinkingStartMs: null,
    timelineEntries: [],
    lastActivity: null,
    currentAffect: { emotion: "neutral", valence: 0.5 },
    fsmState: "INITIALIZING",
    welcomeShown: false,
};

const DEFAULT_STREAMING_LABEL = "Concierge is thinking...";

const STREAMING_TOOL_LABELS = {
    update_beliefs: "Updating context...",
    update_scoreboard: "Tracking context...",
    update_clarifications: "Clarifying the request...",
    update_narrative: "Organizing context...",
    promote_belief: "Locking in details...",
    recall_memory: "Checking memory...",
    summarize_context: "Summarizing context...",
    dispatch_task: "Starting task...",
};

// Member metadata
const MEMBERS = {
    Alex:       { color: "#6366f1", gradient: "linear-gradient(135deg, #6366f1, #818cf8)", initials: "A", role: "Parent", key: "alex" },
    Jordan:     { color: "#ec4899", gradient: "linear-gradient(135deg, #ec4899, #f472b6)", initials: "J", role: "Parent", key: "jordan" },
    Riley:      { color: "#f59e0b", gradient: "linear-gradient(135deg, #f59e0b, #fbbf24)", initials: "R", role: "Child", key: "riley" },
    "Nana Liz": { color: "#14b8a6", gradient: "linear-gradient(135deg, #14b8a6, #2dd4bf)", initials: "N", role: "Grandparent", key: "nana" },
};

const AFFECT_MAP = {
    calm:       { emoji: "\u{1F60C}", color: "var(--affect-calm)" },
    warm:       { emoji: "\u{1F60A}", color: "var(--affect-warm)" },
    anxious:    { emoji: "\u{1F630}", color: "var(--affect-anxious)" },
    urgent:     { emoji: "\u{26A0}\u{FE0F}", color: "var(--affect-urgent)" },
    playful:    { emoji: "\u{1F60E}", color: "var(--affect-playful)" },
    empathetic: { emoji: "\u{1F497}", color: "var(--affect-empathetic)" },
    neutral:    { emoji: "--",  color: "var(--text-tertiary)" },
};

// Hint prompts for welcome screen
const WELCOME_HINTS = [
    "What's for dinner tonight?",
    "Help Riley with homework",
    "Family schedule this week",
    "Set a reminder for Jordan",
];

// ================================================================
// DOM refs
// ================================================================

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

const dom = {
    messages:       $("#messages"),
    input:          $("#message-input"),
    sendBtn:        $("#send-btn"),
    form:           $("#input-form"),
    memberList:     $("#member-list"),
    inputTag:       $("#input-member-tag"),
    turnBadge:      $("#turn-badge"),
    fsmState:       $("#fsm-state"),
    fsmBadge:       $("#fsm-badge"),
    affectEmoji:    $("#affect-emoji"),
    affectLabel:    $("#affect-label"),
    affectFill:     $("#affect-fill"),
    streaming:      $("#streaming-indicator"),
    streamingText:  $(".streaming-text"),
    toastContainer: $("#toast-container"),
    connStatus:     $("#connection-status"),
    rightPanel:     $("#right-panel"),
    btnTimeline:    $("#btn-timeline"),
    btnDashboard:   $("#btn-dashboard"),
    timelineEl:     $("#timeline-entries"),
    panelTabs:      $$(".panel-tab"),
    panelContents:  $$(".panel-content"),
    dashFsm:        $("#dash-fsm"),
    dashOps:        $("#dash-ops"),
    dashTools:      $("#dash-tools"),
    metricLatency:  $("#metric-latency"),
    metricBytesIn:  $("#metric-bytes-in"),
    metricBytesOut: $("#metric-bytes-out"),
};

// ================================================================
// WebSocket
// ================================================================

function connect() {
    setConnectionStatus("connecting");

    const protocol = location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${location.host}/ws`;

    state.ws = new WebSocket(wsUrl);

    state.ws.onopen = () => {
        state.connected = true;
        setConnectionStatus("connected");
        dom.input.disabled = false;
        dom.sendBtn.disabled = false;
        dom.input.focus();
    };

    state.ws.onclose = () => {
        state.connected = false;
        setConnectionStatus("disconnected");
        dom.input.disabled = true;
        dom.sendBtn.disabled = true;
        finishStreaming(true);
        setTimeout(connect, 3000);
    };

    state.ws.onerror = () => {
        state.connected = false;
        setConnectionStatus("disconnected");
        finishStreaming(true);
    };

    state.ws.onmessage = (event) => {
        try {
            const msg = JSON.parse(event.data);
            handleMessage(msg);
        } catch (e) {
            console.error("Failed to parse WS message:", e);
        }
    };
}

function send(data) {
    if (state.ws && state.ws.readyState === WebSocket.OPEN) {
        state.ws.send(JSON.stringify(data));
    }
}

// ================================================================
// Message router
// ================================================================

function handleMessage(msg) {
    switch (msg.type) {
        case "init":           handleInit(msg); break;
        case "response":       handleResponse(msg); break;
        case "stream_chunk":   handleStreamChunk(msg); break;
        case "proactive":      handleProactive(msg); break;
        case "weave":          handleWeave(msg); break;
        case "system":         handleSystem(msg); break;
        case "turn_info":      handleTurnInfo(msg); break;
        case "member_switched": handleMemberSwitched(msg); break;
        case "timeline":       addTimelineEntry(msg.entry); break;
        case "timeline_batch": (msg.entries || []).forEach(addTimelineEntry); break;
        case "affect_update":  updateAffect(msg.emotion, msg.valence); break;
        case "fsm_state":      updateFsmState(msg.to_state, msg.from_state, msg.trigger); break;
        case "fsm_current":    setFsmBadge(msg.state); break;
        case "activity":       updateDashboard(msg.data); break;
        case "tool_event":     handleToolEvent(msg); break;
        case "status_report":  handleStatusReport(msg.data); break;
    }
}

// ================================================================
// Handlers
// ================================================================

function handleInit(msg) {
    state.family = msg.family;
    state.member = msg.member;
    state.device = msg.device;
    state.turn = msg.turn;
    setFsmBadge(msg.fsm_state);
    renderMemberList();
    updateInputTag();
    dom.turnBadge.textContent = `Turn ${state.turn}`;

    if (!state.welcomeShown) {
        showWelcomeScreen();
        state.welcomeShown = true;
    }

    addSystemMessage("Connected to K1 Concierge");
}

function handleResponse(msg) {
    const affect = msg.affect || "calm";

    if (state.streamingMsgId) {
        const el = document.getElementById(state.streamingMsgId);
        if (el) {
            const affectInfo = AFFECT_MAP[affect] || AFFECT_MAP.neutral;
            const sender = el.querySelector(".msg-sender");
            el.classList.remove("streaming-placeholder");

            // Collapse thinking block if present
            const thinkBlock = el.querySelector(".thinking-block");
            if (thinkBlock) {
                thinkBlock.classList.add("collapsed");
                thinkBlock.classList.remove("active");
                const toggle = thinkBlock.querySelector(".thinking-toggle");
                if (toggle) {
                    const dur = _thinkingDuration();
                    toggle.innerHTML = `<span class="thinking-chevron"></span> Thought for ${dur}`;
                }
            }

            // Build response content (below thinking block)
            let contentArea = el.querySelector(".msg-response-text");
            if (!contentArea) {
                contentArea = document.createElement("div");
                contentArea.className = "msg-response-text";
                const body = el.querySelector(".msg-content");
                if (body) body.appendChild(contentArea);
            }
            contentArea.innerHTML = formatMessageText(msg.text);

            // Remove cursor
            const cursor = el.querySelector(".stream-cursor");
            if (cursor) cursor.remove();

            if (sender) {
                sender.innerHTML = `Concierge <span class="msg-affect-tag" style="background:${affectInfo.color}22;color:${affectInfo.color}">${affect}</span>`;
            }
        }
        state.streamingMsgId = null;
        state.streamBuffer = "";
        state.thinkingBuffer = "";
        state.thinkingActive = false;
        showStreaming(false, DEFAULT_STREAMING_LABEL);
        updateAffect(affect, state.currentAffect.valence);
        scrollToBottom();
    } else {
        finishStreaming();
        addConciergeMessage(msg.text, affect);
    }
}

function handleStreamChunk(msg) {
    ensureStreamingMessage();
    const el = document.getElementById(state.streamingMsgId);
    if (!el) return;

    if (msg.chunk_type === "thinking") {
        // Live thinking text -- render inside collapsible thinking block
        state.thinkingActive = true;
        state.thinkingBuffer += (msg.text || "");

        let thinkBlock = el.querySelector(".thinking-block");
        if (!thinkBlock) {
            // Create thinking block on first thinking chunk
            state._thinkingStartMs = Date.now();
            const content = el.querySelector(".msg-content");
            // Clear placeholder
            content.innerHTML = "";
            thinkBlock = document.createElement("div");
            thinkBlock.className = "thinking-block active";
            thinkBlock.innerHTML = `
                <div class="thinking-toggle">
                    <span class="thinking-chevron"></span>
                    <span class="thinking-dots"><span></span><span></span><span></span></span>
                    Thinking...
                </div>
                <div class="thinking-content"></div>
            `;
            content.appendChild(thinkBlock);

            // Toggle collapse on click
            thinkBlock.querySelector(".thinking-toggle").addEventListener("click", () => {
                thinkBlock.classList.toggle("collapsed");
            });
        }

        // Stream thinking text
        const thinkContent = thinkBlock.querySelector(".thinking-content");
        if (thinkContent) {
            thinkContent.innerHTML = formatThinkingText(state.thinkingBuffer);
            scrollToBottom();
        }

        showStreaming(true, DEFAULT_STREAMING_LABEL);
        return;
    }

    // Text chunk -- show in response area below thinking block
    if (msg.chunk_type === "text") {
        state.streamBuffer += (msg.text || "");
        let contentArea = el.querySelector(".msg-response-text");
        if (!contentArea) {
            contentArea = document.createElement("div");
            contentArea.className = "msg-response-text";
            const content = el.querySelector(".msg-content");
            content.appendChild(contentArea);
        }
        contentArea.innerHTML = formatMessageText(state.streamBuffer) +
            '<span class="stream-cursor"></span>';
        scrollToBottom();
    }

    showStreaming(true, "Concierge is drafting a reply...");
}

function _thinkingDuration() {
    if (!state._thinkingStartMs) return "a moment";
    const sec = Math.round((Date.now() - state._thinkingStartMs) / 1000);
    if (sec < 1) return "< 1s";
    return `${sec}s`;
}

function formatThinkingText(text) {
    // Minimal formatting for thinking: escape HTML, preserve newlines
    let html = escapeHtml(text);
    html = html.replace(/\n/g, "<br>");
    return html;
}

function finishStreaming(removePlaceholder = false) {
    if (state.streamingMsgId) {
        const el = document.getElementById(state.streamingMsgId);
        if (el) {
            if (removePlaceholder) {
                el.remove();
            } else {
                const cursor = el.querySelector(".stream-cursor");
                if (cursor) cursor.remove();
            }
        }
        state.streamingMsgId = null;
        state.streamBuffer = "";
        state.thinkingBuffer = "";
        state.thinkingActive = false;
        state._thinkingStartMs = null;
    }
    showStreaming(false, DEFAULT_STREAMING_LABEL);
}

function handleProactive(msg) {
    finishStreaming(true);
    addMessage("proactive", "Concierge", msg.text, { label: "proactive" });
    showToast("Notification", msg.text);
    // Pulse the header to draw attention
    animateElement(dom.turnBadge);
}

function handleWeave(msg) {
    finishStreaming(true);
    (msg.texts || []).forEach(text => {
        addMessage("weave", "Concierge", text, { label: "woven update" });
        showToast("Task Complete", text);
    });
}

function handleSystem(msg) {
    finishStreaming(true);
    addSystemMessage(msg.text);
}

function handleTurnInfo(msg) {
    state.turn = msg.turn;
    dom.turnBadge.textContent = `Turn ${msg.turn}`;
    animateElement(dom.turnBadge);
}

function handleMemberSwitched(msg) {
    state.member = msg.member;
    state.device = msg.device;
    updateInputTag();
    highlightActiveMember();
}

// Tools that represent external actions the user cares about
const EXTERNAL_TOOLS = new Set([
    "invoke_capability",
    "batch_invoke_capabilities",
    "spawn_via_fabric",
    "execute_workflow",
]);

// Human-readable labels for tool actions
const TOOL_ICONS = {
    invoke_capability:        { icon: "\u26A1", verb: "Executing" },
    batch_invoke_capabilities:{ icon: "\u26A1\u26A1", verb: "Batch executing" },
    discover_capabilities:    { icon: "\uD83D\uDD0D", verb: "Discovering" },
    spawn_via_fabric:         { icon: "\uD83E\uDDF5", verb: "Spawning agent" },
    execute_workflow:         { icon: "\u2699\uFE0F", verb: "Running workflow" },
    recall_memory:            { icon: "\uD83E\uDDE0", verb: "Recalling" },
    submit_result:            { icon: "\u2705", verb: "Submitting" },
};

function _parseCapabilityName(argsSummary) {
    // Extract capability_name from args_summary string like
    // "{'capability_name': 'tool.execute.smart_home_control', ...}"
    if (!argsSummary) return null;
    const m = argsSummary.match(/capability_name['"]?\s*[:=]\s*['"]([^'"]+)['"]/);
    return m ? m[1] : null;
}

function _humanizeCapName(name) {
    if (!name) return "";
    // Strip tool.execute. prefix for display
    let clean = name.replace(/^tool\.execute\./, "");
    return clean.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
}

function handleToolEvent(msg) {
    // Always add to timeline
    addTimelineEntry({
        elapsed_ms: msg.duration_ms || 0,
        phase: "tool",
        component: msg.actor,
        summary: `${msg.phase}: ${msg.tool_name}`,
    });

    if (msg.actor === "front" && msg.phase === "started" && !EXTERNAL_TOOLS.has(msg.tool_name)) {
        const label = STREAMING_TOOL_LABELS[msg.tool_name] || "Thinking...";
        ensureStreamingMessage();
        // Update the placeholder text if no thinking block is active yet
        const el = document.getElementById(state.streamingMsgId);
        if (el && !el.querySelector(".thinking-block")) {
            const content = el.querySelector(".msg-content");
            if (content) {
                content.innerHTML = `<span class="stream-placeholder-text">${escapeHtml(label)}</span>`;
            }
        }
        showStreaming(true, label);
    }

    // Show external tool executions as chips in the chat area
    if (EXTERNAL_TOOLS.has(msg.tool_name)) {
        const capName = _parseCapabilityName(msg.args_summary || "");
        const info = TOOL_ICONS[msg.tool_name] || { icon: "\u2699\uFE0F", verb: "Running" };
        const label = capName ? _humanizeCapName(capName) : msg.tool_name.replace(/_/g, " ");

        if (msg.phase === "started") {
            addToolChip(msg.tool_name, info.icon, `${info.verb}: ${label}`, "running", capName);
        } else {
            // completed -- update existing chip or add a new one
            updateToolChip(capName || msg.tool_name, msg.success !== false, msg.duration_ms || 0);
        }
    }
}

function addToolChip(toolName, icon, label, status, capName) {
    const chipId = `tool-chip-${(capName || toolName).replace(/[^a-z0-9]/gi, "-")}-${Date.now()}`;
    const div = document.createElement("div");
    div.className = `message tool-chip ${status}`;
    div.id = chipId;
    div.dataset.capName = capName || toolName;

    // Extract device/target from args for more context (e.g. coffee_machine, bedroom_speaker)
    const deviceMatch = (label || "").match(/Smart Home Control/i);
    const displayLabel = deviceMatch ? label : label;

    div.innerHTML = `
        <div class="tool-chip-content">
            <span class="tool-chip-icon">${icon}</span>
            <span class="tool-chip-label">${escapeHtml(displayLabel)}</span>
            <span class="tool-chip-spinner"></span>
        </div>
    `;

    // Insert BEFORE streaming indicator or at end of messages
    const streaming = dom.messages.querySelector(".streaming-indicator");
    if (streaming && streaming.parentNode === dom.messages) {
        dom.messages.insertBefore(div, streaming);
    } else {
        dom.messages.appendChild(div);
    }
    scrollToBottom();
    return chipId;
}

function updateToolChip(capOrTool, success, durationMs) {
    // Find the most recent running chip matching this capability
    const normalizedKey = (capOrTool || "").replace(/[^a-z0-9]/gi, "-");
    const chips = dom.messages.querySelectorAll(".tool-chip.running");
    let chip = null;
    for (let i = chips.length - 1; i >= 0; i--) {
        if (chips[i].dataset.capName && chips[i].dataset.capName.replace(/[^a-z0-9]/gi, "-") === normalizedKey) {
            chip = chips[i];
            break;
        }
    }
    // Fallback: pick last running chip
    if (!chip && chips.length) chip = chips[chips.length - 1];
    if (!chip) return;

    chip.classList.remove("running");
    chip.classList.add(success ? "done" : "failed");

    const spinner = chip.querySelector(".tool-chip-spinner");
    if (spinner) {
        spinner.textContent = success ? "\u2713" : "\u2717";
        spinner.className = `tool-chip-status ${success ? "ok" : "err"}`;
    }

    // Add duration
    if (durationMs > 0) {
        const dur = document.createElement("span");
        dur.className = "tool-chip-dur";
        dur.textContent = `${durationMs}ms`;
        chip.querySelector(".tool-chip-content").appendChild(dur);
    }
}

function handleStatusReport(data) {
    addSystemMessage(
        `Status: ready=${data.system_ready}, phases=${data.phases_completed}, timeline=${data.timeline_count} entries`
    );
}

// ================================================================
// Welcome screen
// ================================================================

function showWelcomeScreen() {
    const welcomeEl = document.createElement("div");
    welcomeEl.className = "welcome-container";
    welcomeEl.id = "welcome-screen";
    welcomeEl.innerHTML = `
        <div class="welcome-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                <path d="M12 2L2 7l10 5 10-5-10-5z"/>
                <path d="M2 17l10 5 10-5"/>
                <path d="M2 12l10 5 10-5"/>
            </svg>
        </div>
        <h2 class="welcome-title">Good ${getTimeGreeting()}</h2>
        <p class="welcome-subtitle">Your family's intelligent concierge is ready. Ask anything about schedules, meals, homework, or family coordination.</p>
        <div class="welcome-hints">
            ${WELCOME_HINTS.map(h => `<button class="welcome-hint" type="button">${escapeHtml(h)}</button>`).join("")}
        </div>
    `;

    dom.messages.appendChild(welcomeEl);

    // Wire hint clicks
    welcomeEl.querySelectorAll(".welcome-hint").forEach(btn => {
        btn.addEventListener("click", () => {
            dom.input.value = btn.textContent;
            dom.input.focus();
            removeWelcomeScreen();
            sendMessage();
        });
    });
}

function removeWelcomeScreen() {
    const el = document.getElementById("welcome-screen");
    if (el) {
        el.style.transition = "opacity 0.3s ease, transform 0.3s ease";
        el.style.opacity = "0";
        el.style.transform = "translateY(-16px) scale(0.97)";
        setTimeout(() => el.remove(), 300);
    }
}

function getTimeGreeting() {
    const h = new Date().getHours();
    if (h < 12) return "morning";
    if (h < 17) return "afternoon";
    return "evening";
}

// ================================================================
// Message rendering
// ================================================================

let msgCounter = 0;

function addMessage(type, sender, text, opts = {}) {
    removeWelcomeScreen();
    msgCounter++;
    const id = opts.id || `msg-${msgCounter}`;
    const div = document.createElement("div");
    div.className = `message ${type}`;
    div.id = id;

    // Stagger animation
    div.style.animationDelay = `${Math.min(msgCounter * 20, 100)}ms`;

    const meta = MEMBERS[sender] || { initials: "K1", color: "var(--brand-blue)", gradient: "linear-gradient(135deg, var(--brand-blue), var(--brand-indigo))" };

    if (type === "system") {
        div.innerHTML = `<div class="msg-body"><div class="msg-content">${escapeHtml(text)}</div></div>`;
    } else if (type === "user") {
        div.innerHTML = `
            <div class="msg-avatar" style="background:${meta.gradient || meta.color}">${meta.initials}</div>
            <div class="msg-body">
                <div class="msg-sender">${escapeHtml(sender)}</div>
                <div class="msg-content">${escapeHtml(text)}</div>
                <div class="msg-meta"><span>${formatTime()}</span></div>
            </div>
        `;
    } else {
        const affectTag = opts.affect
            ? `<span class="msg-affect-tag" style="background:${(AFFECT_MAP[opts.affect] || AFFECT_MAP.neutral).color}22;color:${(AFFECT_MAP[opts.affect] || AFFECT_MAP.neutral).color}">${opts.affect}</span>`
            : "";
        const labelTag = opts.label
            ? `<span class="msg-affect-tag" style="background:rgba(100,210,255,0.12);color:var(--brand-teal)">${opts.label}</span>`
            : "";

        div.innerHTML = `
            <div class="msg-avatar concierge-avatar">K1</div>
            <div class="msg-body">
                <div class="msg-sender">Concierge ${affectTag}${labelTag}</div>
                <div class="msg-content">${formatMessageText(text)}</div>
                <div class="msg-meta"><span>${formatTime()}</span></div>
            </div>
        `;
    }

    dom.messages.appendChild(div);
    scrollToBottom();
    return id;
}

function addUserMessage(text) {
    addMessage("user", state.member, text);
}

function addConciergeMessage(text, affect) {
    addMessage("concierge", "Concierge", text, { affect });
    updateAffect(affect, state.currentAffect.valence);
}

function addSystemMessage(text) {
    addMessage("system", "System", text);
}

function createStreamingMessage(id) {
    removeWelcomeScreen();
    const div = document.createElement("div");
    div.className = "message concierge streaming-placeholder";
    div.id = id;
    div.innerHTML = `
        <div class="msg-avatar concierge-avatar">K1</div>
        <div class="msg-body">
            <div class="msg-sender">Concierge</div>
            <div class="msg-content">
                <span class="stream-placeholder-text">Thinking...</span>
            </div>
            <div class="msg-meta"><span>${formatTime()}</span></div>
        </div>
    `;
    dom.messages.appendChild(div);
    scrollToBottom();
}

function ensureStreamingMessage() {
    if (state.streamingMsgId) return;
    state.streamingMsgId = "stream-" + Date.now();
    state.streamBuffer = "";
    state.thinkingBuffer = "";
    state.thinkingActive = false;
    state._thinkingStartMs = null;
    createStreamingMessage(state.streamingMsgId);
}

// ================================================================
// Member switcher
// ================================================================

function renderMemberList() {
    dom.memberList.innerHTML = "";
    const members = state.family ? state.family.members : [];

    members.forEach((m, i) => {
        const meta = MEMBERS[m.name] || { initials: m.name[0], color: "#666", key: m.name.toLowerCase(), gradient: "#666" };
        const card = document.createElement("div");
        card.className = `member-card${m.name === state.member ? " active" : ""}`;
        card.dataset.member = m.name;
        card.setAttribute("role", "option");
        card.setAttribute("aria-selected", m.name === state.member);
        card.style.animationDelay = `${i * 60}ms`;
        card.innerHTML = `
            <div class="member-avatar ${meta.key}">${meta.initials}</div>
            <div class="member-info">
                <span class="member-name">${m.name}</span>
                <span class="member-role">${m.relation || ""}</span>
            </div>
        `;
        card.addEventListener("click", () => switchMember(m.name));
        dom.memberList.appendChild(card);
    });
}

function switchMember(name) {
    if (name === state.member) return;
    state.member = name;
    send({ type: "switch_member", member: name.toLowerCase() });
    updateInputTag();
    highlightActiveMember();
    // Haptic-style feedback on the input tag
    animateElement(dom.inputTag);
}

function highlightActiveMember() {
    document.querySelectorAll(".member-card").forEach(card => {
        const isActive = card.dataset.member === state.member;
        card.classList.toggle("active", isActive);
        card.setAttribute("aria-selected", isActive);
    });
}

function updateInputTag() {
    dom.inputTag.textContent = state.member;
    const meta = MEMBERS[state.member];
    if (meta) {
        dom.inputTag.style.background = meta.gradient || meta.color;
    }
}

// ================================================================
// Affect indicator
// ================================================================

function updateAffect(emotion, valence) {
    state.currentAffect = { emotion, valence };
    const info = AFFECT_MAP[emotion] || AFFECT_MAP.neutral;
    dom.affectEmoji.textContent = info.emoji;
    dom.affectLabel.textContent = emotion;
    const pct = Math.max(0, Math.min(100, (valence + 1) * 50));
    dom.affectFill.style.width = `${pct}%`;
    dom.affectFill.style.background = info.color;
    // Subtle flash on the affect indicator
    animateElement(dom.affectEmoji);
}

// ================================================================
// FSM state
// ================================================================

function updateFsmState(toState, fromState, trigger) {
    setFsmBadge(toState);
    addTimelineEntry({
        elapsed_ms: 0,
        phase: "state",
        component: "fsm",
        summary: `${fromState} -> ${toState} (${trigger})`,
    });
}

function setFsmBadge(stateName) {
    state.fsmState = stateName;
    dom.fsmState.textContent = stateName;
    const isActive = stateName !== "LISTENING" && stateName !== "INITIALIZING";
    dom.fsmBadge.classList.toggle("active", isActive);
    animateElement(dom.fsmBadge);
}

// ================================================================
// Timeline
// ================================================================

function addTimelineEntry(entry) {
    state.timelineEntries.push(entry);

    const div = document.createElement("div");
    div.className = "tl-entry";
    const phase = entry.phase || "state";
    const ms = typeof entry.elapsed_ms === "number" ? entry.elapsed_ms.toFixed(0) : "?";

    div.innerHTML = `
        <span class="tl-time">${ms}ms</span>
        <span class="tl-dot ${phase}"></span>
        <span class="tl-text">
            <span class="tl-component">${entry.component || ""}</span>
            ${escapeHtml(entry.summary || "")}
        </span>
    `;

    dom.timelineEl.appendChild(div);
    dom.timelineEl.scrollTop = dom.timelineEl.scrollHeight;

    // Keep max 200
    while (dom.timelineEl.children.length > 200) {
        dom.timelineEl.removeChild(dom.timelineEl.firstChild);
    }
}

// ================================================================
// Dashboard
// ================================================================

function updateDashboard(data) {
    state.lastActivity = data;

    dom.dashFsm.innerHTML = (data.fsm_states || []).map(s =>
        `<span class="fsm-state-tag ${s === state.fsmState ? 'current' : ''}">${s}</span>`
    ).join("");

    dom.dashOps.innerHTML = (data.session_ops || []).map(op =>
        `<div class="op-item">${escapeHtml(op)}</div>`
    ).join("");

    dom.dashTools.innerHTML = (data.tool_calls || []).map(t =>
        `<div class="op-item">${escapeHtml(t)}</div>`
    ).join("");

    // Animate metric values
    animateMetricValue(dom.metricLatency, `${data.latency_ms || 0}ms`);
    animateMetricValue(dom.metricBytesIn, formatBytes(data.bytes_in || 0));
    animateMetricValue(dom.metricBytesOut, formatBytes(data.bytes_out || 0));
}

function animateMetricValue(el, newValue) {
    if (el.textContent === newValue) return;
    el.style.transition = "none";
    el.style.transform = "scale(0.8)";
    el.style.opacity = "0.5";
    requestAnimationFrame(() => {
        el.textContent = newValue;
        el.style.transition = "all 0.3s cubic-bezier(0.34, 1.56, 0.64, 1)";
        el.style.transform = "scale(1)";
        el.style.opacity = "1";
    });
}

// ================================================================
// Toast notifications
// ================================================================

function showToast(title, text, duration = 5000) {
    const toast = document.createElement("div");
    toast.className = "toast";
    toast.innerHTML = `
        <div class="toast-title">${escapeHtml(title)}</div>
        <div>${escapeHtml(text.substring(0, 140))}${text.length > 140 ? '...' : ''}</div>
    `;
    dom.toastContainer.appendChild(toast);
    setTimeout(() => {
        if (toast.parentNode) toast.parentNode.removeChild(toast);
    }, duration);
}

// ================================================================
// Streaming indicator
// ================================================================

function showStreaming(visible, label = DEFAULT_STREAMING_LABEL) {
    dom.streaming.classList.toggle("hidden", !visible);
    dom.streamingText.textContent = visible ? label : DEFAULT_STREAMING_LABEL;
}

// ================================================================
// Panel toggling
// ================================================================

function setupPanelToggles() {
    dom.btnTimeline.addEventListener("click", () => togglePanel("timeline"));
    dom.btnDashboard.addEventListener("click", () => togglePanel("dashboard"));

    dom.panelTabs.forEach(tab => {
        tab.addEventListener("click", () => {
            const panel = tab.dataset.panel;
            dom.panelTabs.forEach(t => {
                t.classList.toggle("active", t.dataset.panel === panel);
                t.setAttribute("aria-selected", t.dataset.panel === panel);
            });
            dom.panelContents.forEach(p => p.classList.toggle("active", p.id === `${panel}-panel`));
        });
    });
}

function togglePanel(panel) {
    const isHidden = dom.rightPanel.classList.contains("hidden");

    if (isHidden) {
        dom.rightPanel.classList.remove("hidden");
        dom.panelTabs.forEach(t => {
            t.classList.toggle("active", t.dataset.panel === panel);
            t.setAttribute("aria-selected", t.dataset.panel === panel);
        });
        dom.panelContents.forEach(p => p.classList.toggle("active", p.id === `${panel}-panel`));
    } else {
        const activeTab = document.querySelector(".panel-tab.active");
        if (activeTab && activeTab.dataset.panel === panel) {
            dom.rightPanel.classList.add("hidden");
        } else {
            dom.panelTabs.forEach(t => {
                t.classList.toggle("active", t.dataset.panel === panel);
                t.setAttribute("aria-selected", t.dataset.panel === panel);
            });
            dom.panelContents.forEach(p => p.classList.toggle("active", p.id === `${panel}-panel`));
        }
    }

    const isVisible = !dom.rightPanel.classList.contains("hidden");
    const activePanel = document.querySelector(".panel-tab.active");
    dom.btnTimeline.classList.toggle("active", isVisible && activePanel?.dataset.panel === "timeline");
    dom.btnDashboard.classList.toggle("active", isVisible && activePanel?.dataset.panel === "dashboard");
}

// ================================================================
// Input handling
// ================================================================

function setupInput() {
    dom.form.addEventListener("submit", (e) => {
        e.preventDefault();
        sendMessage();
    });

    dom.input.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    // Subtle input wrapper interaction
    dom.input.addEventListener("focus", () => {
        dom.form.querySelector(".input-wrapper").style.transform = "translateY(-1px)";
    });

    dom.input.addEventListener("blur", () => {
        dom.form.querySelector(".input-wrapper").style.transform = "translateY(0)";
    });
}

function sendMessage() {
    const text = dom.input.value.trim();
    if (!text || !state.connected) return;

    // Animate send button
    dom.sendBtn.style.transform = "scale(0.85)";
    setTimeout(() => { dom.sendBtn.style.transform = ""; }, 150);

    if (text.startsWith("/")) {
        send({ type: "command", cmd: text });
        dom.input.value = "";
        addSystemMessage(`Command: ${text}`);
        return;
    }

    addUserMessage(text);
    ensureStreamingMessage();
    send({
        type: "message",
        text: text,
        member: state.member,
        device: state.device,
    });

    dom.input.value = "";
    showStreaming(true, DEFAULT_STREAMING_LABEL);
}

// ================================================================
// Micro-interactions
// ================================================================

function animateElement(el) {
    if (!el) return;
    el.style.transition = "none";
    el.style.transform = "scale(0.92)";
    requestAnimationFrame(() => {
        el.style.transition = "transform 0.4s cubic-bezier(0.34, 1.56, 0.64, 1)";
        el.style.transform = "scale(1)";
    });
}

// ================================================================
// Utility
// ================================================================

function setConnectionStatus(status) {
    const el = dom.connStatus;
    el.className = `connection-status ${status}`;
    const textEl = el.querySelector(".status-text");
    const labels = { connected: "Connected", disconnected: "Disconnected", connecting: "Connecting..." };
    textEl.textContent = labels[status] || status;
}

function scrollToBottom() {
    requestAnimationFrame(() => {
        dom.messages.scrollTo({
            top: dom.messages.scrollHeight,
            behavior: "smooth",
        });
    });
}

function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
}

function formatMessageText(text) {
    let html = escapeHtml(text);
    html = html.replace(/\n/g, "<br>");
    html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
    html = html.replace(/`(.+?)`/g, '<code style="background:rgba(255,255,255,0.06);padding:1px 5px;border-radius:4px;font-size:12px;font-family:\'SF Mono\',\'JetBrains Mono\',monospace;">$1</code>');
    return html;
}

function formatTime() {
    return new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function formatBytes(bytes) {
    if (bytes < 1024) return `${bytes}B`;
    if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)}KB`;
    return `${(bytes / 1048576).toFixed(1)}MB`;
}

// ================================================================
// Keyboard shortcuts
// ================================================================

function setupKeyboardShortcuts() {
    document.addEventListener("keydown", (e) => {
        // Cmd/Ctrl + K: Focus input
        if ((e.metaKey || e.ctrlKey) && e.key === "k") {
            e.preventDefault();
            dom.input.focus();
        }
        // Cmd/Ctrl + T: Toggle timeline
        if ((e.metaKey || e.ctrlKey) && e.key === "t") {
            e.preventDefault();
            togglePanel("timeline");
        }
        // Cmd/Ctrl + D: Toggle dashboard
        if ((e.metaKey || e.ctrlKey) && e.key === "d") {
            e.preventDefault();
            togglePanel("dashboard");
        }
        // Escape: Close right panel
        if (e.key === "Escape") {
            if (!dom.rightPanel.classList.contains("hidden")) {
                dom.rightPanel.classList.add("hidden");
                dom.btnTimeline.classList.remove("active");
                dom.btnDashboard.classList.remove("active");
            }
        }
    });
}

// ================================================================
// Init
// ================================================================

function init() {
    setupInput();
    setupPanelToggles();
    setupKeyboardShortcuts();

    // Smooth transition wrapper for input
    const wrapper = dom.form.querySelector(".input-wrapper");
    wrapper.style.transition = "all 0.25s cubic-bezier(0.16, 1, 0.3, 1)";

    connect();
}

document.addEventListener("DOMContentLoaded", init);
