/**
 * FamilyOS — Family Hub Web UI
 *
 * Sidebar-driven SPA:
 *   - Home dashboard (real K1 data)
 *   - Chat assistant (WebSocket streaming, FSM, affect, turn)
 *   - Adapter views (calendar, tasks, shopping, reminders, chores, family settings)
 *   - System views (timeline, dashboard, session state)
 *
 * Light theme, Figma-inspired layout. Backend integration unchanged.
 */

"use strict";

// ============================================================================
// State
// ============================================================================

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
    currentView: "home",
    memberDropdownOpen: false,
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

// Family member metadata
const MEMBERS = {
    "Alex":     { color: "#6366f1", initials: "A", role: "Parent",      key: "alex"   },
    "Jordan":   { color: "#ec4899", initials: "J", role: "Parent",      key: "jordan" },
    "Riley":    { color: "#f59e0b", initials: "R", role: "Child",       key: "riley"  },
    "Nana Liz": { color: "#14b8a6", initials: "N", role: "Grandparent", key: "nana"   },
};

const AFFECT_MAP = {
    calm:       { emoji: "😌", color: "#3b82f6" },
    warm:       { emoji: "😊", color: "#f59e0b" },
    anxious:    { emoji: "😰", color: "#a855f7" },
    urgent:     { emoji: "⚠️", color: "#ef4444" },
    playful:    { emoji: "😎", color: "#10b981" },
    empathetic: { emoji: "💗", color: "#ec4899" },
    neutral:    { emoji: "—",  color: "#9ca3af" },
};

const ADAPTER_VIEW_IDS = ["calendar", "tasks", "shopping", "reminders", "chores", "settings"];
const ADAPTER_BACKEND_NAME = {
    calendar: "calendar",
    tasks: "tasks",
    reminders: "reminders",
    chores: "chores",
    settings: "family_settings",
};

// ============================================================================
// DOM refs
// ============================================================================

const $  = (s) => document.querySelector(s);
const $$ = (s) => Array.from(document.querySelectorAll(s));

const dom = {
    // Chat
    messages:       $("#messages"),
    input:          $("#message-input"),
    sendBtn:        $("#send-btn"),
    form:           $("#input-form"),
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

    // Sidebar
    connStatus:        $("#connection-status"),
    memberSwitcher:    $("#member-switcher"),
    memberAvatar:      $("#member-avatar"),
    memberName:        $("#member-name"),
    memberRole:        $("#member-role"),
    memberDropdown:    $("#member-list-dropdown"),
    welcomeName:       $("#welcome-name"),
    navItems:          $$(".nav-item"),
    views:             $$(".view"),

    // Home stats
    statTasks:     $("#stat-tasks"),
    statEvents:    $("#stat-events"),
    statReminders: $("#stat-reminders"),
    statChores:    $("#stat-chores"),
    homeActivity:  $("#home-activity"),

    // View bodies
    viewBody: {
        calendar:  $("#view-calendar-body"),
        tasks:     $("#view-tasks-body"),
        reminders: $("#view-reminders-body"),
        chores:    $("#view-chores-body"),
        settings:  $("#view-settings-body"),
    },

    // Timeline / Dashboard / Session state
    timelineEl:     $("#timeline-entries"),
    dashFsm:        $("#dash-fsm"),
    dashOps:        $("#dash-ops"),
    dashTools:      $("#dash-tools"),
    metricLatency:  $("#metric-latency"),
    metricBytesIn:  $("#metric-bytes-in"),
    metricBytesOut: $("#metric-bytes-out"),
    ssLoading:      $("#ss-loading"),
    ssContent:      $("#ss-content"),
    ssOverview:     $("#ss-overview"),
    ssTierBars:     $("#ss-tier-bars"),
    ssHotSections:  $("#ss-hot-sections"),
    ssWarmSections: $("#ss-warm-sections"),
    ssColdInfo:     $("#ss-cold-info"),
};

// ============================================================================
// Init
// ============================================================================

function init() {
    setupNav();
    setupMemberSwitcher();
    setupInput();
    setupActionFormHandlers();
    setupKeyboardShortcuts();
    connect();
}

document.addEventListener("DOMContentLoaded", init);

// ============================================================================
// View navigation
// ============================================================================

function setupNav() {
    dom.navItems.forEach((item) => {
        item.addEventListener("click", () => navigateTo(item.dataset.view));
    });
    // Quick-action / stat-card data-target buttons
    $$("[data-target]").forEach((btn) => {
        btn.addEventListener("click", () => navigateTo(btn.dataset.target));
    });
}

function navigateTo(viewId) {
    if (!viewId) return;
    state.currentView = viewId;

    dom.navItems.forEach((item) => {
        const active = item.dataset.view === viewId;
        item.classList.toggle("active", active);
        item.setAttribute("aria-selected", active ? "true" : "false");
    });

    dom.views.forEach((view) => {
        view.classList.toggle("view--active", view.id === `view-${viewId}`);
    });

    // View-specific loaders
    if (viewId === "home")          loadHomeDashboard();
    else if (viewId === "chat")     dom.input && dom.input.focus();
    else if (viewId === "timeline") {/* live-updated */}
    else if (viewId === "dashboard") {/* live-updated */}
    else if (viewId === "sessionstate") fetchSessionState();
    else if (ADAPTER_VIEW_IDS.includes(viewId) && viewId !== "shopping") {
        loadAdapterView(viewId);
    }
}

// ============================================================================
// Home dashboard
// ============================================================================

async function loadHomeDashboard() {
    if (dom.welcomeName) dom.welcomeName.textContent = state.member;

    // Counts via list endpoints (best effort; shows -- on failure)
    const fetchCount = async (adapter, action, qs = "") => {
        try {
            const r = await fetch(`/k1/tools/${adapter}/${action}${qs}`, { headers: buildAppsHeaders() });
            if (!r.ok) return null;
            const data = await r.json();
            return _extractItems(data).length;
        } catch { return null; }
    };

    const todayIso = new Date().toISOString().slice(0, 10);
    const endIso = (() => {
        const d = new Date();
        d.setDate(d.getDate() + 14);
        return d.toISOString().slice(0, 10);
    })();

    const [tasks, events, reminders, chores] = await Promise.all([
        fetchCount("tasks", "list_tasks"),
        fetchCount("calendar", "list_events", `?start_date=${todayIso}&end_date=${endIso}`),
        fetchCount("reminders", "list_reminders"),
        fetchCount("chores", "list_chores"),
    ]);

    dom.statTasks     && (dom.statTasks.textContent     = tasks     ?? "—");
    dom.statEvents    && (dom.statEvents.textContent    = events    ?? "—");
    dom.statReminders && (dom.statReminders.textContent = reminders ?? "—");
    dom.statChores    && (dom.statChores.textContent    = chores    ?? "—");

    // Recent activity from timeline entries
    if (dom.homeActivity) {
        const recent = state.timelineEntries.slice(-6).reverse();
        if (recent.length === 0) {
            dom.homeActivity.innerHTML = `<p class="muted-empty">Activity will appear as the family hub becomes active.</p>`;
        } else {
            dom.homeActivity.innerHTML = recent.map((e) => {
                const meta = MEMBERS[state.member] || { initials: "?", color: "#9ca3af" };
                return `
                    <div class="activity-row">
                        <div class="activity-avatar" style="background:linear-gradient(135deg, ${meta.color}, ${meta.color}cc)">${meta.initials}</div>
                        <div style="flex:1;min-width:0">
                            <p class="activity-text"><strong>${escapeHtml(e.component || "system")}</strong> — ${escapeHtml(e.summary || "")}</p>
                            <p class="activity-time">${(e.elapsed_ms || 0).toFixed(0)}ms</p>
                        </div>
                    </div>`;
            }).join("");
        }
    }
}

// ============================================================================
// WebSocket
// ============================================================================

function connect() {
    setConnectionStatus("connecting");

    const protocol = location.protocol === "https:" ? "wss:" : "ws:";
    state.ws = new WebSocket(`${protocol}//${location.host}/ws`);

    state.ws.onopen = () => {
        state.connected = true;
        setConnectionStatus("connected");
        if (dom.input) {
            dom.input.disabled = false;
            dom.sendBtn.disabled = false;
        }
    };

    state.ws.onclose = () => {
        state.connected = false;
        setConnectionStatus("disconnected");
        if (dom.input) {
            dom.input.disabled = true;
            dom.sendBtn.disabled = true;
        }
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
            handleMessage(JSON.parse(event.data));
        } catch (e) {
            console.error("WS parse error:", e);
        }
    };
}

function send(data) {
    if (state.ws && state.ws.readyState === WebSocket.OPEN) {
        state.ws.send(JSON.stringify(data));
    }
}

// ============================================================================
// Message router
// ============================================================================

function handleMessage(msg) {
    switch (msg.type) {
        case "init":            handleInit(msg); break;
        case "response":        handleResponse(msg); break;
        case "stream_chunk":    handleStreamChunk(msg); break;
        case "proactive":       handleProactive(msg); break;
        case "weave":           handleWeave(msg); break;
        case "system":          handleSystem(msg); break;
        case "turn_info":       handleTurnInfo(msg); break;
        case "member_switched": handleMemberSwitched(msg); break;
        case "timeline":        addTimelineEntry(msg.entry); break;
        case "timeline_batch":  (msg.entries || []).forEach(addTimelineEntry); break;
        case "affect_update":   updateAffect(msg.emotion, msg.valence); break;
        case "fsm_state":       updateFsmState(msg.to_state, msg.from_state, msg.trigger); break;
        case "fsm_current":     setFsmBadge(msg.state); break;
        case "activity":        updateDashboard(msg.data); break;
        case "tool_event":      handleToolEvent(msg); break;
        case "tool_refresh":    handleToolRefresh(msg); break;
        case "status_report":   /* silent */ break;
        case "hil_request":     handleHilRequest(msg); break;
    }
}

// ============================================================================
// Handlers
// ============================================================================

function handleInit(msg) {
    state.family = msg.family;
    state.member = msg.member || state.member;
    state.device = msg.device || state.device;
    state.turn = msg.turn || 0;
    setFsmBadge(msg.fsm_state || "READY");
    renderMemberDropdown();
    renderActiveMember();
    if (dom.turnBadge) dom.turnBadge.textContent = `Turn ${state.turn}`;
    if (state.currentView === "home") loadHomeDashboard();
}

function handleResponse(msg) {
    const affect = msg.affect || "calm";

    if (state.streamingMsgId) {
        const el = document.getElementById(state.streamingMsgId);
        if (el) {
            el.classList.remove("message-thinking");
            const bubble = el.querySelector(".message-bubble");
            if (bubble) {
                bubble.innerHTML = formatMessageText(msg.text) +
                    `<div class="message-meta">${formatTime()}</div>`;
            }
        }
        state.streamingMsgId = null;
        state.streamBuffer = "";
        state.thinkingBuffer = "";
        state.thinkingActive = false;
        showStreaming(false);
        updateAffect(affect, state.currentAffect.valence);
        scrollChatToBottom();
    } else {
        finishStreaming();
        addAssistantMessage(msg.text);
        updateAffect(affect, state.currentAffect.valence);
    }
}

function handleStreamChunk(msg) {
    ensureStreamingMessage();
    const el = document.getElementById(state.streamingMsgId);
    if (!el) return;

    if (msg.chunk_type === "thinking") {
        state.thinkingActive = true;
        state.thinkingBuffer += (msg.text || "");
        const bubble = el.querySelector(".message-bubble");
        if (bubble) {
            bubble.innerHTML = `<em style="color:var(--text-tertiary)">${escapeHtml(state.thinkingBuffer)}</em>`;
        }
        el.classList.add("message-thinking");
        showStreaming(true, DEFAULT_STREAMING_LABEL);
        return;
    }

    if (msg.chunk_type === "text") {
        state.streamBuffer += (msg.text || "");
        el.classList.remove("message-thinking");
        const bubble = el.querySelector(".message-bubble");
        if (bubble) {
            bubble.innerHTML = formatMessageText(state.streamBuffer);
        }
        scrollChatToBottom();
    }

    showStreaming(true, "Concierge is drafting a reply...");
}

function finishStreaming(removePlaceholder = false) {
    if (state.streamingMsgId) {
        const el = document.getElementById(state.streamingMsgId);
        if (el && removePlaceholder) el.remove();
        state.streamingMsgId = null;
        state.streamBuffer = "";
        state.thinkingBuffer = "";
        state.thinkingActive = false;
        state._thinkingStartMs = null;
    }
    showStreaming(false);
}

function handleProactive(msg) {
    finishStreaming(true);
    addAssistantMessage(msg.text, { label: "proactive" });
    showToast("Notification", msg.text);
}

function handleWeave(msg) {
    finishStreaming(true);
    (msg.texts || []).forEach((text) => {
        addAssistantMessage(text, { label: "woven update" });
        showToast("Task Complete", text);
    });
}

function handleSystem(msg) {
    finishStreaming(true);
    addSystemMessage(msg.text);
}

function handleSystem(msg) {
    finishStreaming(true);
    addSystemMessage(msg.text);
}

// ============================================================================
// HIL (Human-in-the-Loop) approval widget
// ============================================================================

function _buildHilCardInner(baseId, title, body, approveLabel, denyLabel) {
    return `
        <div style="font-weight:600;margin-bottom:6px;color:var(--text-primary)">${escapeHtml(title)}</div>
        ${body}
        <div style="display:flex;gap:8px;margin-top:10px">
            <button id="${baseId}-approve" style="flex:1;padding:8px 0;border-radius:8px;border:none;background:var(--accent,#22c55e);color:#fff;font-weight:600;cursor:pointer">${escapeHtml(approveLabel)}</button>
            <button id="${baseId}-deny" style="flex:1;padding:8px 0;border-radius:8px;border:1.5px solid var(--border,#e2e8f0);background:transparent;color:var(--text-primary);font-weight:600;cursor:pointer">${escapeHtml(denyLabel)}</button>
        </div>
        <div id="${baseId}-status" style="margin-top:6px;font-size:0.8em;color:var(--text-tertiary);display:none"></div>`;
}

function _setHilWidgetState(baseIds, statusText) {
    (baseIds || []).forEach((baseId) => {
        const approveBtn = document.getElementById(`${baseId}-approve`);
        const denyBtn = document.getElementById(`${baseId}-deny`);
        const statusEl = document.getElementById(`${baseId}-status`);
        if (approveBtn) { approveBtn.disabled = true; approveBtn.style.opacity = "0.5"; }
        if (denyBtn) { denyBtn.disabled = true; denyBtn.style.opacity = "0.5"; }
        if (statusEl) {
            statusEl.textContent = statusText;
            statusEl.style.display = "block";
        }
    });
}

function handleHilRequest(msg) {
    finishStreaming();
    const id = "hil-" + msg.hil_request_id;
    const overlayId = "hil-overlay-" + msg.hil_request_id;
    // Remove any existing widget for the same request (idempotent)
    const existing = document.getElementById(id);
    if (existing) existing.remove();
    const existingOverlay = document.getElementById(overlayId);
    if (existingOverlay) existingOverlay.remove();

    const kind = msg.kind || "";
    const payload = msg.payload || {};

    // Architecture: free-text clarification (needs_human / clarification)
    // must be handled by Front via the normal chat channel, NOT a binary
    // Approve/Deny widget. Back publishes task.suspended → FSM →
    // Front(HITL_RELAY) → ordinary chat bubble → user replies via the
    // text box → Front(HITL_RESOLVE) → task.resume. If any caller still
    // emits one of these kinds via TOPIC_HIL_REQUEST, drop it on the
    // floor so we don't render a useless binary widget.
    if (kind === "needs_human" || kind === "clarification") {
        console.warn("handleHilRequest: ignoring kind=" + kind + " (must arrive via chat, not HIL widget)");
        return;
    }

    // Build human-readable title + body
    let title = "Action requires approval";
    let body = "";
    let approveLabel = "Approve";
    let denyLabel = "Deny";

    if (kind === "capability_gate") {
        const cap = payload.capability_name || payload.contract?.name || "action";
        const summary = payload.params_summary || JSON.stringify(payload.params || {});
        title = `Approve: ${cap}`;
        body = summary ? `<p style="margin:0 0 4px 0;color:var(--text-secondary);font-size:0.85em">${escapeHtml(summary)}</p>` : "";
        const sideEffects = payload.contract?.side_effects || [];
        if (sideEffects.length) {
            body += `<p style="margin:0;color:var(--text-tertiary);font-size:0.8em">Side effects: ${sideEffects.map(s => escapeHtml(typeof s === "string" ? s : JSON.stringify(s))).join(", ")}</p>`;
        }
        approveLabel = "Allow";
        denyLabel = "Block";
    } else if (kind === "needs_human") {
        title = payload.question || "Input needed";
        const opts = payload.options || [];
        if (opts.length) {
            body = `<p style="margin:0;color:var(--text-secondary);font-size:0.85em">Options: ${opts.map(o => escapeHtml(typeof o === "string" ? o : (o.label || JSON.stringify(o)))).join(" · ")}</p>`;
        }
    } else if (kind === "approval") {
        title = payload.summary || "Plan requires approval";
        approveLabel = "Approve";
        denyLabel = "Reject";
    }

    const cardInner = _buildHilCardInner(id, title, body, approveLabel, denyLabel);

    const row = document.createElement("div");
    row.id = id;
    row.className = "message-row message-row--system";
    row.style.cssText = "padding: 8px 0;";
    row.innerHTML = `
        <div class="message-avatar" style="background:var(--amber,#f59e0b);color:#fff">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
        </div>
        <div class="message-bubble" style="border:1.5px solid var(--amber,#f59e0b);background:var(--surface-elevated,#fff);padding:12px 14px;">
            ${cardInner}
        </div>`;

    if (dom.messages) {
        dom.messages.appendChild(row);
        scrollChatToBottom();
    }

    const overlay = document.createElement("div");
    overlay.id = overlayId;
    overlay.style.cssText = [
        "position:fixed",
        "top:84px",
        "right:20px",
        "width:min(420px, calc(100vw - 24px))",
        "z-index:9999",
        "pointer-events:auto",
    ].join(";");
    overlay.innerHTML = `
        <div style="border:2px solid var(--amber,#f59e0b);background:var(--surface-elevated,#fff);border-radius:16px;padding:14px 16px;box-shadow:0 18px 40px rgba(15,23,42,0.22);">
            ${_buildHilCardInner(overlayId, title, body, approveLabel, denyLabel)}
        </div>`;
    document.body.appendChild(overlay);

    const widgetIds = [id, overlayId];
    const dismissWidgets = () => {
        widgetIds.forEach((baseId) => {
            const el = document.getElementById(baseId);
            if (!el) return;
            el.style.transition = "opacity 350ms ease, transform 350ms ease";
            el.style.opacity = "0";
            el.style.transform = "translateY(-6px)";
            window.setTimeout(() => { try { el.remove(); } catch (_) { /* noop */ } }, 380);
        });
    };
    const approve = () => {
        _setHilWidgetState(widgetIds, "Response sent — waiting for completion…");
        showToast("Approval sent", title, 3000);
        sendHilResponse(msg, true);
        window.setTimeout(dismissWidgets, 900);
    };
    const deny = () => {
        _setHilWidgetState(widgetIds, "Blocked.");
        showToast("Action blocked", title, 3000);
        sendHilResponse(msg, false);
        window.setTimeout(dismissWidgets, 900);
    };

    widgetIds.forEach((baseId) => {
        const approveBtn = document.getElementById(`${baseId}-approve`);
        const denyBtn = document.getElementById(`${baseId}-deny`);
        if (approveBtn) approveBtn.addEventListener("click", approve);
        if (denyBtn) denyBtn.addEventListener("click", deny);
    });

    showToast("Approval required", title, 8000);
}

function sendHilResponse(hilMsg, approved) {
    const kind = hilMsg.kind || "";
    let payload = {};

    if (kind === "capability_gate") {
        payload = { approved: approved, reason: approved ? "user_approved" : "user_denied" };
    } else if (kind === "needs_human") {
        // Architecture safety net: should never reach here because
        // handleHilRequest short-circuits these kinds above. Kept as a
        // last-resort no-op to avoid sending a Front-mistaken binary
        // decision for a free-text clarification.
        console.warn("sendHilResponse: dropping stale needs_human response");
        return;
    } else if (kind === "approval") {
        payload = { decision: approved ? "approve" : "reject" };
    } else {
        payload = { approved: approved };
    }

    send({
        type: "hil_response",
        hil_request_id: hilMsg.hil_request_id,
        kind: kind,
        payload: payload,
    });
}

function handleTurnInfo(msg) {
    state.turn = msg.turn;
    if (dom.turnBadge) dom.turnBadge.textContent = `Turn ${msg.turn}`;
}

function handleMemberSwitched(msg) {
    state.member = msg.member;
    state.device = msg.device;
    renderActiveMember();
}

const EXTERNAL_TOOLS = new Set([
    "invoke_capability",
    "batch_invoke_capabilities",
    "spawn_via_fabric",
    "execute_workflow",
]);

function handleToolEvent(msg) {
    addTimelineEntry({
        elapsed_ms: msg.duration_ms || 0,
        phase: "tool",
        component: msg.actor,
        summary: `${msg.phase}: ${msg.tool_name}`,
    });

    if (msg.actor === "front" && msg.phase === "started" && !EXTERNAL_TOOLS.has(msg.tool_name)) {
        const label = STREAMING_TOOL_LABELS[msg.tool_name] || "Thinking...";
        ensureStreamingMessage();
        showStreaming(true, label);
    }
}

// E15.10: refresh adapter view + timeline when a family-tool's data changes
function handleToolRefresh(msg) {
    const adapterId = msg.adapter || "";
    // Map backend adapter_id → SPA view id
    const viewId = Object.entries(ADAPTER_BACKEND_NAME)
        .find(([, b]) => b === adapterId)?.[0];
    if (viewId) {
        // Invalidate cached list data so next load hits the server
        delete adapterCache.listData[adapterId];
        if (state.currentView === viewId) {
            loadAdapterView(viewId);
        }
    }
    if (state.currentView === "home") {
        loadHomeDashboard();
    }
    addTimelineEntry({
        elapsed_ms: 0,
        phase: "tool",
        component: adapterId || "family-tool",
        summary: `tool_state.changed → ${adapterId || "unknown"}`,
    });
}

// ============================================================================
// Chat — message rendering (Figma bubbles)
// ============================================================================

let msgCounter = 0;

function addMessageRow(kind, sender, text, opts = {}) {
    if (!dom.messages) return null;
    msgCounter++;
    const id = opts.id || `msg-${msgCounter}`;
    const meta = MEMBERS[sender] || { initials: "K1", color: "#2563eb" };
    const row = document.createElement("div");
    row.className = `message-row message-row--${kind}`;
    row.id = id;

    if (kind === "system") {
        row.innerHTML = `
            <div style="margin:8px auto;font-size:11px;color:var(--text-tertiary);text-align:center;width:100%">
                ${escapeHtml(text)}
            </div>`;
    } else if (kind === "user") {
        row.innerHTML = `
            <div class="message-avatar" style="background:${meta.color}">${meta.initials}</div>
            <div class="message-bubble">
                ${formatMessageText(text)}
                <div class="message-meta">${escapeHtml(sender)} · ${formatTime()}</div>
            </div>`;
    } else {
        const labelTag = opts.label
            ? `<span style="background:rgba(37,99,235,0.1);color:var(--brand-blue);padding:1px 6px;border-radius:6px;font-size:10px;margin-left:4px">${opts.label}</span>`
            : "";
        row.innerHTML = `
            <div class="message-avatar">
                <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="12" cy="11" r="2"/><path d="M8 16h8"/></svg>
            </div>
            <div class="message-bubble">
                ${formatMessageText(text)}
                <div class="message-meta">Concierge${labelTag} · ${formatTime()}</div>
            </div>`;
    }

    dom.messages.appendChild(row);
    scrollChatToBottom();
    return id;
}

function addUserMessage(text)        { return addMessageRow("user", state.member, text); }
function addAssistantMessage(text, o){ return addMessageRow("assistant", "Concierge", text, o); }
function addSystemMessage(text)      { return addMessageRow("system", "System", text); }

function createStreamingMessage(id) {
    const row = document.createElement("div");
    row.className = "message-row message-row--assistant message-thinking";
    row.id = id;
    row.innerHTML = `
        <div class="message-avatar">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="12" cy="11" r="2"/><path d="M8 16h8"/></svg>
        </div>
        <div class="message-bubble"><em style="color:var(--text-tertiary)">Thinking...</em></div>`;
    dom.messages.appendChild(row);
    scrollChatToBottom();
}

function ensureStreamingMessage() {
    if (state.streamingMsgId) return;
    state.streamingMsgId = "stream-" + Date.now();
    state.streamBuffer = "";
    state.thinkingBuffer = "";
    state.thinkingActive = false;
    state._thinkingStartMs = Date.now();
    createStreamingMessage(state.streamingMsgId);
}

function scrollChatToBottom() {
    if (!dom.messages) return;
    requestAnimationFrame(() => {
        const area = dom.messages.parentElement;
        if (area) area.scrollTop = area.scrollHeight;
    });
}

// ============================================================================
// Member switcher
// ============================================================================

function setupMemberSwitcher() {
    if (!dom.memberSwitcher) return;
    dom.memberSwitcher.addEventListener("click", (e) => {
        e.stopPropagation();
        toggleMemberDropdown();
    });
    document.addEventListener("click", (e) => {
        if (state.memberDropdownOpen && !dom.memberDropdown.contains(e.target) && e.target !== dom.memberSwitcher) {
            closeMemberDropdown();
        }
    });
    renderMemberDropdown();
    renderActiveMember();
}

function toggleMemberDropdown() {
    if (state.memberDropdownOpen) closeMemberDropdown();
    else openMemberDropdown();
}
function openMemberDropdown() {
    if (!dom.memberDropdown) return;
    state.memberDropdownOpen = true;
    dom.memberDropdown.classList.remove("hidden");
}
function closeMemberDropdown() {
    if (!dom.memberDropdown) return;
    state.memberDropdownOpen = false;
    dom.memberDropdown.classList.add("hidden");
}

function renderMemberDropdown() {
    if (!dom.memberDropdown) return;
    const members = (state.family && state.family.members) || _defaultFamily();
    dom.memberDropdown.innerHTML = members.map((m) => {
        const meta = MEMBERS[m.name] || { initials: m.name[0], color: "#9ca3af", role: m.relation || "Member" };
        const selected = m.name === state.member ? " selected" : "";
        return `
            <button class="member-dropdown-item${selected}" data-member="${escapeHtml(m.name)}">
                <div class="member-avatar" style="background:${meta.color}">${meta.initials}</div>
                <div class="member-info">
                    <p class="member-name">${escapeHtml(m.name)}</p>
                    <p class="member-role">${escapeHtml(m.relation || meta.role)}</p>
                </div>
            </button>`;
    }).join("");
    dom.memberDropdown.querySelectorAll(".member-dropdown-item").forEach((el) => {
        el.addEventListener("click", () => {
            switchMember(el.dataset.member);
            closeMemberDropdown();
        });
    });
}

function _defaultFamily() {
    return Object.entries(MEMBERS).map(([name, m]) => ({ name, relation: m.role }));
}

function switchMember(name) {
    if (!name || name === state.member) return;
    state.member = name;
    send({ type: "switch_member", member: name.toLowerCase() });
    renderActiveMember();
    if (state.currentView === "home") loadHomeDashboard();
}

function renderActiveMember() {
    const meta = MEMBERS[state.member] || { initials: "?", color: "#9ca3af", role: "Member" };
    if (dom.memberAvatar) {
        dom.memberAvatar.textContent = meta.initials;
        dom.memberAvatar.style.background = meta.color;
    }
    if (dom.memberName)  dom.memberName.textContent = state.member;
    if (dom.memberRole)  dom.memberRole.textContent = meta.role;
    if (dom.inputTag) {
        dom.inputTag.textContent = state.member;
        dom.inputTag.style.background = `${meta.color}1a`;
        dom.inputTag.style.color = meta.color;
    }
    if (dom.welcomeName) dom.welcomeName.textContent = state.member;
    // Mark dropdown selection
    dom.memberDropdown && dom.memberDropdown.querySelectorAll(".member-dropdown-item").forEach((el) => {
        el.classList.toggle("selected", el.dataset.member === state.member);
    });
}

// ============================================================================
// Affect / FSM
// ============================================================================

function updateAffect(emotion, valence) {
    state.currentAffect = { emotion, valence };
    const info = AFFECT_MAP[emotion] || AFFECT_MAP.neutral;
    if (dom.affectEmoji) dom.affectEmoji.textContent = info.emoji;
    if (dom.affectLabel) dom.affectLabel.textContent = emotion;
    if (dom.affectFill) {
        const pct = Math.max(0, Math.min(100, (valence + 1) * 50));
        dom.affectFill.style.width = `${pct}%`;
        dom.affectFill.style.background = info.color;
    }
}

function updateFsmState(toState, fromState, trigger) {
    setFsmBadge(toState);
    addTimelineEntry({
        elapsed_ms: 0,
        phase: "fsm",
        component: "fsm",
        summary: `${fromState} → ${toState} (${trigger})`,
    });
}

function setFsmBadge(stateName) {
    state.fsmState = stateName;
    if (dom.fsmState) dom.fsmState.textContent = stateName;
}

// ============================================================================
// Timeline
// ============================================================================

function addTimelineEntry(entry) {
    state.timelineEntries.push(entry);
    if (!dom.timelineEl) return;

    const phase = entry.phase || "state";
    const ms = typeof entry.elapsed_ms === "number" ? entry.elapsed_ms.toFixed(0) : "?";

    const div = document.createElement("div");
    div.className = `timeline-entry timeline-entry--${phase}`;
    div.innerHTML = `
        <span class="timeline-time">${ms}ms</span>
        <div class="timeline-content">
            <strong>${escapeHtml(entry.component || "system")}</strong> — ${escapeHtml(entry.summary || "")}
        </div>`;

    dom.timelineEl.appendChild(div);
    dom.timelineEl.scrollTop = dom.timelineEl.scrollHeight;

    while (dom.timelineEl.children.length > 200) {
        dom.timelineEl.removeChild(dom.timelineEl.firstChild);
    }
}

// ============================================================================
// Dashboard
// ============================================================================

function updateDashboard(data) {
    state.lastActivity = data;

    if (dom.dashFsm) {
        dom.dashFsm.innerHTML = (data.fsm_states || []).map((s) =>
            `<span class="dash-fsm-state${s === state.fsmState ? " dash-fsm-state--active" : ""}">${escapeHtml(s)}</span>`
        ).join("");
    }
    if (dom.dashOps) {
        dom.dashOps.innerHTML = (data.session_ops || []).map((op) =>
            `<div class="dash-list-item"><span class="dash-list-item-name">${escapeHtml(op)}</span></div>`
        ).join("") || `<p class="muted-empty">No session ops yet.</p>`;
    }
    if (dom.dashTools) {
        dom.dashTools.innerHTML = (data.tool_calls || []).map((t) =>
            `<div class="dash-list-item"><span class="dash-list-item-name">${escapeHtml(t)}</span></div>`
        ).join("") || `<p class="muted-empty">No tool calls yet.</p>`;
    }
    if (dom.metricLatency)  dom.metricLatency.textContent  = `${data.latency_ms || 0}ms`;
    if (dom.metricBytesIn)  dom.metricBytesIn.textContent  = formatBytes(data.bytes_in || 0);
    if (dom.metricBytesOut) dom.metricBytesOut.textContent = formatBytes(data.bytes_out || 0);
}

// ============================================================================
// Toast
// ============================================================================

function showToast(title, text, duration = 5000) {
    if (!dom.toastContainer) return;
    const toast = document.createElement("div");
    toast.className = "toast";
    toast.innerHTML = `
        <strong>${escapeHtml(title)}</strong>
        ${escapeHtml(String(text).slice(0, 140))}${String(text).length > 140 ? "..." : ""}`;
    dom.toastContainer.appendChild(toast);
    setTimeout(() => toast.remove(), duration);
}

// ============================================================================
// Streaming indicator
// ============================================================================

function showStreaming(visible, label = DEFAULT_STREAMING_LABEL) {
    if (!dom.streaming) return;
    dom.streaming.classList.toggle("hidden", !visible);
    if (dom.streamingText) dom.streamingText.textContent = label;
}

// ============================================================================
// Input
// ============================================================================

function setupInput() {
    if (!dom.form) return;
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
}

function sendMessage() {
    const text = dom.input.value.trim();
    if (!text || !state.connected) return;

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
        text,
        member: state.member,
        device: state.device,
    });

    dom.input.value = "";
    showStreaming(true, DEFAULT_STREAMING_LABEL);
}

// ============================================================================
// Connection status
// ============================================================================

function setConnectionStatus(status) {
    if (!dom.connStatus) return;
    dom.connStatus.classList.remove("connected", "disconnected", "connecting");
    dom.connStatus.classList.add(status === "connected" ? "connected" : "disconnected");
    const textEl = dom.connStatus.querySelector(".status-text");
    if (textEl) {
        textEl.textContent = status === "connected" ? "Connected"
            : status === "connecting" ? "Connecting..."
            : "Disconnected";
    }
}

// ============================================================================
// Keyboard shortcuts
// ============================================================================

function setupKeyboardShortcuts() {
    document.addEventListener("keydown", (e) => {
        if ((e.metaKey || e.ctrlKey) && e.key === "k") {
            e.preventDefault();
            navigateTo("chat");
            dom.input && dom.input.focus();
        }
        if (e.key === "Escape") {
            const modal = document.getElementById("action-form-modal");
            if (modal && !modal.classList.contains("hidden")) closeActionForm();
            else closeMemberDropdown();
        }
    });
}

// ============================================================================
// Utilities
// ============================================================================

function escapeHtml(text) {
    const d = document.createElement("div");
    d.textContent = text == null ? "" : String(text);
    return d.innerHTML;
}

function formatMessageText(text) {
    let html = escapeHtml(text);
    html = html.replace(/\n/g, "<br>");
    html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
    html = html.replace(/`(.+?)`/g, '<code style="background:rgba(0,0,0,0.04);padding:1px 5px;border-radius:4px;font-size:12px;font-family:ui-monospace,Menlo,monospace">$1</code>');
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

function _humanizeLabel(name) {
    return String(name).replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function _memberColor(nameOrId) {
    if (!nameOrId) return "#9ca3af";
    const key = (nameOrId || "").toLowerCase().trim();
    for (const [name, m] of Object.entries(MEMBERS)) {
        if (m.key === key || name.toLowerCase() === key) return m.color;
    }
    return "#9ca3af";
}

// ============================================================================
// Adapter views (Calendar / Tasks / Reminders / Chores / Settings)
// ============================================================================

const adapterCache = {
    manifest: {},  // adapter_id → manifest
    listData: {},  // adapter_id → last list response
    context:  null,
};

const ADAPTER_FIELDS = {
    calendar:        ["start", "end", "all_day", "visibility"],
    tasks:           ["status", "priority", "due_at", "assigned_to"],
    reminders:       ["recipient", "status", "trigger"],
    chores:          ["recurrence", "default_assignee", "reward_amount"],
    family_settings: ["enabled", "description", "scope"],
};

const calState = {
    year: new Date().getFullYear(),
    month: new Date().getMonth(),
    events: [],
};

async function loadAdapterView(viewId) {
    const adapterId = ADAPTER_BACKEND_NAME[viewId];
    if (!adapterId) return;
    const body = dom.viewBody[viewId];
    if (!body) return;

    body.innerHTML = `<div class="view-loading"><div class="typing-dots"><span></span><span></span><span></span></div> Loading…</div>`;

    try {
        // Ensure context is loaded
        if (!adapterCache.context) {
            const r = await fetch("/api/family-tools");
            if (r.ok) {
                const data = await r.json();
                adapterCache.context = data.context || {};
            }
        }
        // Fetch manifest
        const role = _currentRole();
        let manifest = adapterCache.manifest[adapterId];
        if (!manifest) {
            const mResp = await fetch(`/api/family-tools/${adapterId}?role=${role}`);
            if (!mResp.ok) throw new Error(`Manifest HTTP ${mResp.status}`);
            manifest = await mResp.json();
            adapterCache.manifest[adapterId] = manifest;
        }
        // Fetch list data
        const listData = await _fetchAdapterData(adapterId, manifest);
        adapterCache.listData[adapterId] = listData;
        const writeActions = (manifest.actions || []).filter((a) => a.kind !== "read");
        _renderAdapterBody(viewId, adapterId, manifest, writeActions, listData);
    } catch (e) {
        body.innerHTML = `<div class="view-error">Could not load: ${escapeHtml(e.message)}</div>`;
    }
}

function _renderAdapterBody(viewId, adapterId, manifest, writeActions, listData) {
    switch (adapterId) {
        case "calendar":         _renderCalendarView(viewId, manifest, writeActions, listData); break;
        case "tasks":            _renderTasksView(viewId, manifest, writeActions, listData); break;
        case "reminders":        _renderRemindersView(viewId, manifest, writeActions, listData); break;
        case "chores":           _renderChoresView(viewId, manifest, writeActions, listData); break;
        case "family_settings":  _renderSettingsView(viewId, manifest, writeActions, listData); break;
        default:                 _renderGenericView(viewId, manifest, writeActions, listData); break;
    }
    // Wire any inline `data-app-action` buttons inside the body
    dom.viewBody[viewId].querySelectorAll("[data-app-action]").forEach((btn) => {
        btn.addEventListener("click", () => {
            const [aId, actionName] = btn.dataset.appAction.split(":");
            const action = ((adapterCache.manifest[aId] || {}).actions || []).find((a) => a.name === actionName);
            if (action) showActionForm(aId, action);
        });
    });
}

// Page-header level "+ Add" button click handlers (set up once globally below)
function setupHeaderActionButtons() {
    $$("[data-app-action]").forEach((btn) => {
        // Skip those already wired by view bodies
        if (btn.closest(".view-body")) return;
        btn.addEventListener("click", async () => {
            const [adapterId, actionName] = btn.dataset.appAction.split(":");
            // Ensure manifest is loaded
            if (!adapterCache.manifest[adapterId]) {
                try {
                    const role = _currentRole();
                    const mResp = await fetch(`/api/family-tools/${adapterId}?role=${role}`);
                    if (mResp.ok) adapterCache.manifest[adapterId] = await mResp.json();
                } catch {/* */}
            }
            const action = ((adapterCache.manifest[adapterId] || {}).actions || []).find((a) => a.name === actionName);
            if (action) showActionForm(adapterId, action);
            else showToast("Action unavailable", `${actionName} not found in ${adapterId}`);
        });
    });
}

// ----------------------------------------------------------------------------
// Calendar view
// ----------------------------------------------------------------------------

function _renderCalendarView(viewId, manifest, writeActions, listData) {
    calState.events = _extractItems(listData);
    const body = dom.viewBody[viewId];

    body.innerHTML = `
        <div class="cal-layout">
            <div class="cal-main">
                <div class="cal-nav">
                    <h3 class="cal-month-label" id="cal-month-label"></h3>
                    <div class="cal-nav-controls">
                        <button class="cal-nav-btn" id="cal-prev" aria-label="Previous month"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6"/></svg></button>
                        <button class="cal-today-btn" id="cal-today">Today</button>
                        <button class="cal-nav-btn" id="cal-next" aria-label="Next month"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"/></svg></button>
                    </div>
                </div>
                <div class="cal-grid-header">
                    <span>Sun</span><span>Mon</span><span>Tue</span>
                    <span>Wed</span><span>Thu</span><span>Fri</span><span>Sat</span>
                </div>
                <div class="cal-grid" id="cal-grid"></div>
            </div>
            <aside class="cal-side">
                <h3>Upcoming Events</h3>
                <div id="cal-upcoming"></div>
            </aside>
        </div>`;

    _calRenderMonth();
    _calRenderUpcoming();

    body.querySelector("#cal-prev").addEventListener("click", () => {
        calState.month--;
        if (calState.month < 0) { calState.month = 11; calState.year--; }
        _calRenderMonth();
    });
    body.querySelector("#cal-next").addEventListener("click", () => {
        calState.month++;
        if (calState.month > 11) { calState.month = 0; calState.year++; }
        _calRenderMonth();
    });
    body.querySelector("#cal-today").addEventListener("click", () => {
        const now = new Date();
        calState.year = now.getFullYear();
        calState.month = now.getMonth();
        _calRenderMonth();
    });
}

function _calRenderMonth() {
    const MONTHS = ["January","February","March","April","May","June","July","August","September","October","November","December"];
    const label = document.getElementById("cal-month-label");
    const grid = document.getElementById("cal-grid");
    if (!label || !grid) return;
    label.textContent = `${MONTHS[calState.month]} ${calState.year}`;

    const today = new Date();
    const firstDay = new Date(calState.year, calState.month, 1).getDay();
    const daysInMonth = new Date(calState.year, calState.month + 1, 0).getDate();

    const evMap = {};
    calState.events.forEach((ev) => {
        const d = (ev.start || "").slice(0, 10);
        if (d) (evMap[d] = evMap[d] || []).push(ev);
    });

    let html = "";
    for (let i = 0; i < firstDay; i++) html += `<div class="cal-cell cal-cell--empty"></div>`;
    for (let d = 1; d <= daysInMonth; d++) {
        const ds = `${calState.year}-${String(calState.month + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
        const isToday = today.getFullYear() === calState.year && today.getMonth() === calState.month && today.getDate() === d;
        const evs = evMap[ds] || [];
        const bars = evs.slice(0, 3).map((ev) =>
            `<div class="cal-event-bar" style="--bar-color:${_memberColor(ev.created_by || "")}" title="${escapeHtml(ev.title || "")}"></div>`
        ).join("");
        const more = evs.length > 3 ? `<span class="cal-more-events">+${evs.length - 3} more</span>` : "";
        html += `
            <button class="cal-cell${isToday ? " cal-cell--today" : ""}" data-date="${ds}">
                <span class="cal-day-num">${d}</span>
                <div class="cal-event-bars">${bars}${more}</div>
            </button>`;
    }
    grid.innerHTML = html;
}

function _calRenderUpcoming() {
    const list = document.getElementById("cal-upcoming");
    if (!list) return;
    const now = new Date();
    const upcoming = calState.events
        .filter((e) => e.start && new Date(e.start) >= now)
        .sort((a, b) => a.start.localeCompare(b.start))
        .slice(0, 5);

    if (upcoming.length === 0) {
        list.innerHTML = `<p class="muted-empty">No upcoming events.</p>`;
        return;
    }
    list.innerHTML = upcoming.map((ev) => {
        const col = _memberColor(ev.created_by || "");
        const when = _fmtEventTime(ev.start, ev.end, ev.all_day);
        return `
            <div class="cal-event-card" style="--ev-color:${col}">
                <h4>${escapeHtml(ev.title || "Untitled")}</h4>
                <div class="cal-event-meta">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
                    ${escapeHtml(when)}
                </div>
                ${ev.created_by ? `
                    <div class="cal-event-meta">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
                        ${escapeHtml(ev.created_by)}
                    </div>` : ""}
            </div>`;
    }).join("");
}

function _fmtEventTime(start, end, allDay) {
    if (allDay) return "All day";
    const fmt = (dt) => {
        const d = new Date(dt);
        return isNaN(d) ? dt : d.toLocaleString("en-US", { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
    };
    return end ? `${fmt(start)} – ${new Date(end).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" })}` : fmt(start);
}

// ----------------------------------------------------------------------------
// Tasks view
// ----------------------------------------------------------------------------

function _renderTasksView(viewId, manifest, writeActions, listData) {
    const items = _extractItems(listData);
    const body = dom.viewBody[viewId];

    const active = items.filter((t) => t.status !== "done" && t.status !== "cancelled");
    const completed = items.filter((t) => t.status === "done");
    const high = active.filter((t) => t.priority === "high").length;

    const renderRow = (t, done) => {
        const pri = t.priority || "normal";
        const due = t.due_at ? _relativeDate(t.due_at) : null;
        const assignee = t.assigned_to || "";
        const aColor = _memberColor(assignee);
        return `
            <div class="task-row${done ? " task-row--done" : ""}">
                <div class="task-checkbox${done ? " task-checkbox--checked" : ""}" data-id="${escapeHtml(t.id || "")}">
                    ${done ? `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>` : ""}
                </div>
                <div class="task-body">
                    <p class="task-title">${escapeHtml(t.title || "Untitled")}</p>
                    <div class="task-meta">
                        ${assignee ? `<span class="task-meta-item"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>${escapeHtml(assignee)}</span>` : ""}
                        ${due ? `<span class="task-meta-item"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>${escapeHtml(due)}</span>` : ""}
                    </div>
                </div>
                ${pri && pri !== "normal" ? `<span class="task-priority task-priority--${pri}">${pri}</span>` : ""}
            </div>`;
    };

    body.innerHTML = `
        <div class="task-stats">
            <div class="task-stat"><p class="task-stat-label">Active Tasks</p><p class="task-stat-value">${active.length}</p></div>
            <div class="task-stat"><p class="task-stat-label">Completed</p><p class="task-stat-value task-stat-value--green">${completed.length}</p></div>
            <div class="task-stat"><p class="task-stat-label">High Priority</p><p class="task-stat-value task-stat-value--red">${high}</p></div>
        </div>

        <section class="task-section">
            <h3>Active Tasks</h3>
            ${active.length === 0
                ? `<p class="muted-empty">All caught up!</p>`
                : active.map((t) => renderRow(t, false)).join("")}
        </section>

        ${completed.length > 0 ? `
        <section class="task-section">
            <h3>Completed</h3>
            ${completed.map((t) => renderRow(t, true)).join("")}
        </section>` : ""}`;
}

// ----------------------------------------------------------------------------
// Reminders view
// ----------------------------------------------------------------------------

function _renderRemindersView(viewId, manifest, writeActions, listData) {
    const items = _extractItems(listData);
    const body = dom.viewBody[viewId];

    const order = { scheduled: 0, snoozed: 1, fired: 2, dismissed: 3 };
    const sorted = [...items].sort((a, b) => {
        const oa = order[a.status] ?? 9, ob = order[b.status] ?? 9;
        if (oa !== ob) return oa - ob;
        return ((a.trigger?.fire_at || a.fire_at || "")).localeCompare(b.trigger?.fire_at || b.fire_at || "");
    });

    if (sorted.length === 0) {
        body.innerHTML = `<div class="view-empty">No reminders yet. Add one above.</div>`;
        return;
    }

    body.innerHTML = `
        <div class="reminder-list">
            ${sorted.map((r) => {
                const fireAt = r.trigger?.fire_at || r.fire_at;
                const kind = r.trigger?.kind || "time";
                const kindIcon = ({ time: "🕐", location_enter: "📍", location_leave: "🚪", event_offset: "📅" }[kind]) || "🔔";
                const timeStr = fireAt ? _fmtReminderTime(fireAt) : "";
                const status = r.status || "scheduled";
                const muted = status === "fired" || status === "dismissed";
                return `
                    <div class="reminder-row${muted ? " reminder-row--muted" : ""}">
                        <div class="reminder-icon">${kindIcon}</div>
                        <div class="reminder-body">
                            <p class="reminder-title">${escapeHtml(r.title || "Reminder")}</p>
                            <div class="reminder-meta">
                                ${timeStr ? `<span class="reminder-time">${escapeHtml(timeStr)}</span>` : ""}
                                ${r.recipient ? `<span class="reminder-recipient" style="--member-color:${_memberColor(r.recipient)};background:${_memberColor(r.recipient)}">${escapeHtml(r.recipient)}</span>` : ""}
                                ${r.message ? `<span style="color:var(--text-tertiary)">${escapeHtml(String(r.message).slice(0, 60))}${r.message.length > 60 ? "…" : ""}</span>` : ""}
                            </div>
                        </div>
                        <span class="reminder-status reminder-status--${status}">${escapeHtml(_humanizeLabel(status))}</span>
                    </div>`;
            }).join("")}
        </div>`;
}

function _fmtReminderTime(dt) {
    const d = new Date(dt);
    if (isNaN(d)) return dt;
    const diff = d - new Date();
    if (Math.abs(diff) < 60_000) return "now";
    if (diff > 0 && diff < 86_400_000) return `in ${Math.round(diff / 60_000)}m`;
    return d.toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

// ----------------------------------------------------------------------------
// Chores view
// ----------------------------------------------------------------------------

function _renderChoresView(viewId, manifest, writeActions, listData) {
    const items = _extractItems(listData);
    const body = dom.viewBody[viewId];

    if (items.length === 0) {
        body.innerHTML = `<div class="view-empty">No chores set up yet.</div>`;
        return;
    }

    body.innerHTML = `
        <div class="chores-grid">
            ${items.map((c) => {
                const assignee = c.default_assignee || "";
                const recur = _shortRecurrence(c.recurrence);
                const hasReward = c.reward_amount && Number(c.reward_amount) > 0;
                const verify = c.requires_verification;
                return `
                    <div class="chore-card">
                        <div class="chore-card-top">
                            <span class="chore-icon">🧹</span>
                            ${hasReward ? `<span class="chore-reward">$${Number(c.reward_amount).toFixed(0)}</span>` : ""}
                        </div>
                        <p class="chore-title">${escapeHtml(c.title || "Chore")}</p>
                        <div class="chore-meta">
                            ${recur ? `<span class="chore-recur">${escapeHtml(recur)}</span>` : ""}
                            ${verify ? `<span class="chore-verify-badge">verify</span>` : ""}
                            ${assignee ? `<span class="chore-assignee" style="background:${_memberColor(assignee)}" title="${escapeHtml(assignee)}">${escapeHtml(assignee.slice(0, 2).toUpperCase())}</span>` : ""}
                        </div>
                    </div>`;
            }).join("")}
        </div>`;
}

function _shortRecurrence(rrule) {
    if (!rrule) return "";
    if (/DAILY/i.test(rrule))   return "Daily";
    if (/WEEKLY/i.test(rrule))  return "Weekly";
    if (/MONTHLY/i.test(rrule)) return "Monthly";
    return "Recurring";
}

// ----------------------------------------------------------------------------
// Family Settings view
// ----------------------------------------------------------------------------

function _renderSettingsView(viewId, manifest, writeActions, listData) {
    const items = _extractItems(listData);
    const flags = items.filter((i) => "flag_name" in i || "enabled" in i);
    const body = dom.viewBody[viewId];

    body.innerHTML = `
        <div class="settings-section">
            <p class="settings-section-title">Feature Flags</p>
            ${flags.length === 0
                ? `<p class="muted-empty">No flags configured.</p>`
                : flags.map((f) => {
                    const name = f.flag_name || f.name || f.id || "flag";
                    const enabled = Boolean(f.enabled);
                    const desc = f.description || f.scope || "";
                    return `
                        <div class="flag-row">
                            <div class="flag-info">
                                <p class="flag-name">${escapeHtml(_humanizeLabel(name))}</p>
                                ${desc ? `<p class="flag-desc">${escapeHtml(desc)}</p>` : ""}
                            </div>
                            <div class="toggle${enabled ? " toggle--on" : ""}" data-flag="${escapeHtml(name)}" data-enabled="${enabled}" role="switch" aria-checked="${enabled}" tabindex="0">
                                <div class="toggle-thumb"></div>
                            </div>
                        </div>`;
                }).join("")}
        </div>`;

    body.querySelectorAll(".toggle").forEach((tog) => {
        tog.addEventListener("click", () => _toggleFlag(tog, manifest));
        tog.addEventListener("keydown", (e) => {
            if (e.key === " " || e.key === "Enter") {
                e.preventDefault();
                _toggleFlag(tog, manifest);
            }
        });
    });
}

async function _toggleFlag(tog, manifest) {
    const flagName = tog.dataset.flag;
    const current = tog.dataset.enabled === "true";
    const newVal = !current;
    const setAction = (manifest.actions || []).find((a) => a.name === "set_feature_flag");
    if (!setAction) return;

    tog.classList.add("toggle--pending");
    try {
        const resp = await fetch("/k1/tools/family_settings/set_feature_flag", {
            method: "POST",
            headers: { ...buildAppsHeaders(), "Content-Type": "application/json" },
            body: JSON.stringify({ flag_name: flagName, enabled: newVal }),
        });
        if (resp.ok) {
            tog.dataset.enabled = String(newVal);
            tog.setAttribute("aria-checked", String(newVal));
            tog.classList.toggle("toggle--on", newVal);
            showToast("Settings", `${_humanizeLabel(flagName)} ${newVal ? "enabled" : "disabled"}.`);
        } else {
            showToast("Error", `HTTP ${resp.status}`);
        }
    } catch (e) {
        showToast("Error", e.message);
    } finally {
        tog.classList.remove("toggle--pending");
    }
}

// ----------------------------------------------------------------------------
// Generic fallback
// ----------------------------------------------------------------------------

function _renderGenericView(viewId, manifest, writeActions, listData) {
    const items = _extractItems(listData);
    const body = dom.viewBody[viewId];
    body.innerHTML = `
        <div class="card card--padded">
            <h3>${escapeHtml(manifest.title || viewId)}</h3>
            <p style="color:var(--text-tertiary);font-size:13px">${escapeHtml(manifest.summary || "")}</p>
            ${items.length === 0 ? `<p class="muted-empty">No items yet.</p>` :
                `<pre style="background:var(--bg-muted);padding:12px;border-radius:8px;font-size:11px;overflow:auto">${escapeHtml(JSON.stringify(items, null, 2))}</pre>`}
        </div>`;
}

// ============================================================================
// Action form modal
// ============================================================================

let _pendingAction = null;

function setupActionFormHandlers() {
    const close = document.getElementById("btn-action-close");
    const cancel = document.getElementById("btn-action-cancel");
    const submit = document.getElementById("btn-action-submit");
    const backdrop = document.getElementById("action-form-backdrop");
    if (close)    close.addEventListener("click", closeActionForm);
    if (cancel)   cancel.addEventListener("click", closeActionForm);
    if (submit)   submit.addEventListener("click", submitActionForm);
    if (backdrop) backdrop.addEventListener("click", closeActionForm);

    setupHeaderActionButtons();
}

function showActionForm(adapterId, actionSpec) {
    _pendingAction = { adapterId, actionSpec };

    const modal = document.getElementById("action-form-modal");
    const title = document.getElementById("action-form-title");
    const fields = document.getElementById("action-form-fields");

    title.textContent = actionSpec.label || _humanizeLabel(actionSpec.name);

    const params = actionSpec.params || {};
    const properties = params.properties || {};
    const required = params.required || [];

    fields.innerHTML = Object.entries(properties).map(([name, schema]) => {
        const isReq = required.includes(name);
        const label = _humanizeLabel(name);
        const inputType = schema.type === "boolean" ? "checkbox"
            : (schema.type === "integer" || schema.type === "number" ? "number" : "text");
        const placeholder = schema.description || schema.format || name;

        if (inputType === "checkbox") {
            return `
                <div class="action-form-field action-form-field--check">
                    <input id="af-${escapeHtml(name)}" name="${escapeHtml(name)}" type="checkbox" class="action-field-input action-field-checkbox">
                    <label class="action-field-label" for="af-${escapeHtml(name)}">${escapeHtml(label)}</label>
                </div>`;
        }
        return `
            <div class="action-form-field">
                <label class="action-field-label" for="af-${escapeHtml(name)}">${escapeHtml(label)}${isReq ? ' <span class="af-req">*</span>' : ""}</label>
                <input id="af-${escapeHtml(name)}" name="${escapeHtml(name)}" type="${inputType}"
                       placeholder="${escapeHtml(placeholder)}" class="action-field-input" ${isReq ? "required" : ""}>
            </div>`;
    }).join("");

    if (!Object.keys(properties).length) {
        fields.innerHTML = `<p class="muted-empty">No additional parameters needed.</p>`;
    }

    modal.classList.remove("hidden");
}

async function submitActionForm() {
    if (!_pendingAction) return;
    const { adapterId, actionSpec } = _pendingAction;

    const modal = document.getElementById("action-form-modal");
    const inputs = modal.querySelectorAll(".action-field-input");
    const params = {};
    inputs.forEach((input) => {
        if (!input.name) return;
        params[input.name] = input.type === "checkbox" ? input.checked : (input.value || undefined);
    });

    const btn = document.getElementById("btn-action-submit");
    btn.textContent = "Submitting…";
    btn.disabled = true;

    try {
        const resp = await fetch(`/k1/tools/${adapterId}/${actionSpec.name}`, {
            method: "POST",
            headers: { ...buildAppsHeaders(), "Content-Type": "application/json" },
            body: JSON.stringify(params),
        });
        const result = resp.ok ? await resp.json() : { success: false, error: `HTTP ${resp.status}` };
        closeActionForm();
        if (result.success !== false) {
            showToast("Done", `${actionSpec.label || actionSpec.name} completed.`);
            // Reload the relevant view
            const viewId = Object.entries(ADAPTER_BACKEND_NAME).find(([, b]) => b === adapterId)?.[0];
            if (viewId) await loadAdapterView(viewId);
            if (state.currentView === "home") loadHomeDashboard();
        } else {
            showToast("Action failed", result.error || result.error_code || "Unknown error", 7000);
        }
    } catch (e) {
        showToast("Error", e.message, 7000);
    } finally {
        btn.textContent = "Submit";
        btn.disabled = false;
    }
}

function closeActionForm() {
    const modal = document.getElementById("action-form-modal");
    if (modal) modal.classList.add("hidden");
    _pendingAction = null;
}

// ============================================================================
// Adapter helpers
// ============================================================================

function buildAppsHeaders() {
    const ctx = adapterCache.context || {};
    return {
        "X-Actor-Member-Id": _currentMemberActorId(),
        "X-Actor-Role":      _currentRole(),
        "X-Space-Id":        ctx.space_id || "smith_family",
        "X-Trace-Id":        (crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).slice(2)),
    };
}

function _currentMemberActorId() {
    if (state.family && state.family.members) {
        const m = state.family.members.find((mem) => mem.name === state.member);
        if (m) return m.actor_id || m.name.toLowerCase().replace(/\s+/g, "_");
    }
    return (adapterCache.context && adapterCache.context.member_id) || (state.member || "alex").toLowerCase().replace(/\s+/g, "_");
}

function _currentRole() {
    if (state.family && state.family.members) {
        const m = state.family.members.find((mem) => mem.name === state.member);
        if (m) {
            const rel = (m.relation || m.access_level || "parent").toLowerCase();
            return ({ parent: "parent", child: "child", guardian: "guardian", grandparent: "elder", elder: "elder" }[rel]) || "parent";
        }
    }
    return (adapterCache.context && adapterCache.context.role) || "parent";
}

async function _fetchAdapterData(adapterId, manifest) {
    const listAction = (manifest.actions || []).find((a) => a.kind === "read" && a.name.startsWith("list_"))
        || (manifest.actions || []).find((a) => a.kind === "read")
        || null;
    if (!listAction) return null;
    return _callListAction(adapterId, listAction);
}

async function _callListAction(adapterId, action) {
    let url = `/k1/tools/${adapterId}/${action.name}`;
    if (adapterId === "calendar" && action.name === "list_events") {
        const today = new Date();
        const end = new Date(today);
        end.setDate(end.getDate() + 60);
        const fmt = (d) => d.toISOString().split("T")[0];
        url += `?start_date=${fmt(today)}&end_date=${fmt(end)}`;
    }
    try {
        const resp = await fetch(url, { headers: buildAppsHeaders() });
        if (!resp.ok) return null;
        return resp.json();
    } catch { return null; }
}

function _extractItems(data) {
    if (!data || data.success === false) return [];
    const KEYS = ["items", "events", "tasks", "reminders", "chores", "lists", "flags", "results", "assignments", "rows"];
    for (const k of KEYS) if (Array.isArray(data[k])) return data[k];
    return [];
}

function _relativeDate(isoStr) {
    const d = new Date(isoStr);
    if (isNaN(d)) return isoStr;
    const diffD = Math.round((d - new Date()) / 86_400_000);
    if (diffD === 0) return "Today";
    if (diffD === 1) return "Tomorrow";
    if (diffD === -1) return "Yesterday";
    if (diffD > 0 && diffD < 8) return `in ${diffD}d`;
    if (diffD < 0 && diffD > -8) return `${-diffD}d ago`;
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

// ============================================================================
// Session State (unchanged logic, light-themed render)
// ============================================================================

let _ssFetchTimer = null;

async function fetchSessionState() {
    if (!dom.ssLoading) return;
    try {
        const resp = await fetch("/api/session/state");
        if (!resp.ok) {
            dom.ssLoading.textContent = `Session state error (HTTP ${resp.status})`;
            dom.ssLoading.style.display = "";
            dom.ssContent.style.display = "none";
            _scheduleSSRefresh();
            return;
        }
        const data = await resp.json();
        if (!data.available) {
            dom.ssLoading.textContent = data.error
                ? `Session state error: ${data.error}`
                : "Session state not available (coordinator initializing...)";
            dom.ssLoading.style.display = "";
            dom.ssContent.style.display = "none";
            _scheduleSSRefresh();
            return;
        }
        dom.ssLoading.style.display = "none";
        dom.ssContent.style.display = "";
        renderSessionState(data);
    } catch (e) {
        dom.ssLoading.textContent = "Failed to load session state";
        dom.ssLoading.style.display = "";
        dom.ssContent.style.display = "none";
    }
    _scheduleSSRefresh();
}

function _scheduleSSRefresh() {
    clearTimeout(_ssFetchTimer);
    if (state.currentView === "sessionstate") {
        _ssFetchTimer = setTimeout(fetchSessionState, 5000);
    }
}

function renderSessionState(data) {
    const sections = data.sections || {};
    const details = data.section_details || {};
    let hotBytes = 0, warmBytes = 0, hotCap = 0, warmCap = 0;
    for (const [n, info] of Object.entries(sections)) {
        const d = details[n] || {};
        const sz = d.current_size_bytes ?? info.size_bytes;
        const cap = d.budget_bytes ?? info.budget_bytes;
        if (info.tier === "hot") { hotBytes += sz; hotCap += cap; }
        else { warmBytes += sz; warmCap += cap; }
    }
    const totalBytes = hotBytes + warmBytes;
    const totalCap = hotCap + warmCap;
    const totalPct = totalCap > 0 ? (totalBytes / totalCap) * 100 : 0;
    const hotPct = hotCap > 0 ? (hotBytes / hotCap) * 100 : 0;
    const warmPct = warmCap > 0 ? (warmBytes / warmCap) * 100 : 0;

    dom.ssOverview.innerHTML = `
        <div class="ss-overview-item">
            <span class="ss-overview-label">Total Used</span>
            <span class="ss-overview-value">${(totalBytes / 1024).toFixed(1)} KB</span>
            <span class="ss-overview-label">${totalPct.toFixed(1)}% utilized</span>
        </div>
        <div class="ss-overview-item">
            <span class="ss-overview-label">Pressure</span>
            <span class="ss-overview-value" style="font-size:13px">${escapeHtml(String(data.pressure || "normal").toUpperCase())}</span>
            <span class="ss-overview-label">${data.is_running ? "Running" : "Stopped"}</span>
        </div>
        <div class="ss-overview-item">
            <span class="ss-overview-label">Sections</span>
            <span class="ss-overview-value">${Object.keys(sections).length}</span>
            <span class="ss-overview-label">total</span>
        </div>
        <div class="ss-overview-item">
            <span class="ss-overview-label">Local Cold</span>
            <span class="ss-overview-value">${data.local_cold_count || 0}</span>
            <span class="ss-overview-label">archived</span>
        </div>`;

    dom.ssTierBars.innerHTML = `
        ${_ssTierBar("HOT", hotPct, hotBytes / 1024, hotCap / 1024)}
        ${_ssTierBar("WARM", warmPct, warmBytes / 1024, warmCap / 1024)}`;

    const hot = [], warm = [];
    for (const [name, info] of Object.entries(sections)) {
        const d = details[name] || {};
        const sz = d.current_size_bytes ?? info.size_bytes;
        const cap = d.budget_bytes ?? info.budget_bytes;
        const pct = cap > 0 ? (sz / cap) * 100 : 0;
        const row = `
            <div class="ss-section-row">
                <span class="ss-section-name">${escapeHtml(name.replace(/_/g, " "))}</span>
                <span class="ss-section-detail">${(sz / 1024).toFixed(2)} / ${(cap / 1024).toFixed(0)} KB · ${pct.toFixed(0)}%</span>
            </div>`;
        (info.tier === "hot" ? hot : warm).push(row);
    }
    dom.ssHotSections.innerHTML = hot.join("") || `<p class="muted-empty">Empty.</p>`;
    dom.ssWarmSections.innerHTML = warm.join("") || `<p class="muted-empty">Empty.</p>`;
    dom.ssColdInfo.innerHTML = `SQLite archive: <strong>${data.local_cold_count || 0}</strong> items (K1 edge storage)`;
}

function _ssTierBar(label, pct, usedKB, totalKB) {
    pct = pct || 0;
    return `
        <div class="ss-tier-bar">
            <span class="ss-tier-bar-label">${label}</span>
            <div class="ss-tier-bar-track">
                <div class="ss-tier-bar-fill" style="width:${Math.min(pct, 100)}%"></div>
            </div>
            <span class="ss-tier-bar-value">${usedKB.toFixed(1)} / ${totalKB.toFixed(0)} KB</span>
        </div>`;
}
