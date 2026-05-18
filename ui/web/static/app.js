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
    tasksSelectedListId: null,
    shoppingSelectedListId: null,
    sessionStateSelectedSection: null,
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
    shopping: "shopping",
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
        shopping:  $("#view-shopping-body"),
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
    ssInspector:    $("#ss-inspector"),
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
    else if (ADAPTER_VIEW_IDS.includes(viewId)) {
        loadAdapterView(viewId);
    }
}

// ============================================================================
// Home dashboard
// ============================================================================

async function loadHomeDashboard() {
    if (dom.welcomeName) dom.welcomeName.textContent = state.member;

    // Family app data for counts + human-readable activity (best effort).
    const fetchData = async (adapter, action, qs = "") => {
        try {
            const r = await fetch(`/k1/tools/${adapter}/${action}${qs}`, { headers: buildAppsHeaders() });
            if (!r.ok) return null;
            return r.json();
        } catch { return null; }
    };

    const todayIso = new Date().toISOString().slice(0, 10);
    const endIso = (() => {
        const d = new Date();
        d.setDate(d.getDate() + 14);
        return d.toISOString().slice(0, 10);
    })();

    const [taskData, eventData, reminderData, choreData, shoppingListData, shoppingItemData] = await Promise.all([
        fetchData("tasks", "list_tasks"),
        fetchData("calendar", "list_events", `?start_date=${todayIso}&end_date=${endIso}`),
        fetchData("reminders", "list_reminders"),
        fetchData("chores", "list_chores"),
        fetchData("shopping", "list_lists"),
        fetchData("shopping", "list_items"),
    ]);

    const tasks = taskData ? _extractItems(taskData) : [];
    const events = eventData ? _extractItems(eventData) : [];
    const reminders = reminderData ? _extractItems(reminderData) : [];
    const chores = choreData ? _extractItems(choreData) : [];
    const shoppingLists = Array.isArray(shoppingListData?.lists) ? shoppingListData.lists : _extractItems(shoppingListData);
    const shoppingItems = Array.isArray(shoppingItemData?.items) ? shoppingItemData.items : _extractItems(shoppingItemData);

    dom.statTasks     && (dom.statTasks.textContent     = taskData     ? tasks.length     : "—");
    dom.statEvents    && (dom.statEvents.textContent    = eventData    ? events.length    : "—");
    dom.statReminders && (dom.statReminders.textContent = reminderData ? reminders.length : "—");
    dom.statChores    && (dom.statChores.textContent    = choreData    ? chores.length    : "—");

    if (dom.homeActivity) {
        _renderHomeActivity(_buildHomeActivityFeed({ tasks, events, reminders, chores, shoppingLists, shoppingItems }).slice(0, 6));
    }
}

function _renderHomeActivity(items) {
    if (!dom.homeActivity) return;
    if (!items.length) {
        dom.homeActivity.innerHTML = `<p class="muted-empty">Family activity will appear as people update the apps.</p>`;
        return;
    }
    dom.homeActivity.innerHTML = items.map((item) => {
        const actor = _actorDisplay(item.actorId);
        const target = item.target ? ` ${escapeHtml(item.targetPrefix || "in")} <span class="activity-object">${escapeHtml(item.target)}</span>` : "";
        const detail = [item.detail, _relativeTimeAgo(item.timestamp)].filter(Boolean).join(" · ");
        return `
            <div class="activity-row">
                <div class="activity-avatar" style="background:linear-gradient(135deg, ${actor.color}, ${actor.color}cc)">${escapeHtml(actor.initials)}</div>
                <div class="activity-body">
                    <p class="activity-text"><strong>${escapeHtml(actor.name)}</strong> ${escapeHtml(item.verb)} <span class="activity-object">${escapeHtml(item.title)}</span>${target}</p>
                    <p class="activity-time"><span class="activity-app">${escapeHtml(item.app)}</span>${detail ? ` · ${escapeHtml(detail)}` : ""}</p>
                </div>
            </div>`;
    }).join("");
}

function _buildHomeActivityFeed({ tasks = [], events = [], reminders = [], chores = [], shoppingLists = [], shoppingItems = [] } = {}) {
    const listNameById = new Map(shoppingLists.map((list) => [list.id, list.name || "Shopping"]));
    const activity = [];
    const push = (entity, app, verb, title, opts = {}) => {
        if (!entity || !title) return;
        const timestamp = _activityTimestamp(entity, opts.timestampFields || []);
        activity.push({
            app,
            verb,
            title,
            target: opts.target || "",
            targetPrefix: opts.targetPrefix || "in",
            detail: opts.detail || "",
            timestamp,
            sortTime: _timestampMs(timestamp),
            actorId: _activityActor(entity, opts.actorCandidates || []),
        });
    };

    events.forEach((event) => {
        push(event, "Calendar", Number(event.version || 1) > 1 ? "updated" : "added", event.title || "event", {
            detail: event.start ? _relativeDate(event.start) : "",
        });
    });
    tasks.forEach((task) => {
        const done = task.status === "done";
        push(task, "Tasks", done ? "completed" : (Number(task.version || 1) > 1 ? "updated" : "added"), task.title || "task", {
            target: task.assigned_to ? _actorDisplay(task.assigned_to).name : "",
            targetPrefix: "for",
            detail: task.due_at ? _relativeDate(task.due_at) : (task.priority ? `${task.priority} priority` : ""),
            timestampFields: done ? ["completed_at"] : [],
        });
    });
    reminders.forEach((reminder) => {
        const statusVerb = ({ dismissed: "dismissed", snoozed: "snoozed", fired: "fired" })[reminder.status];
        push(reminder, "Reminders", statusVerb || (Number(reminder.version || 1) > 1 ? "updated" : "set"), reminder.title || "reminder", {
            target: reminder.recipient ? _actorDisplay(reminder.recipient).name : "",
            targetPrefix: "for",
            detail: _reminderTriggerLabel(reminder.trigger) || reminder.status || "",
            timestampFields: ["fired_at", "snoozed_until"],
        });
    });
    chores.forEach((chore) => {
        const done = chore.status === "done";
        const skipped = chore.status === "skipped";
        push(chore, "Chores", done ? "completed" : (skipped ? "skipped" : "assigned"), chore.title || "chore", {
            target: chore.assigned_to ? _actorDisplay(chore.assigned_to).name : "",
            targetPrefix: "to",
            detail: done && chore.points_awarded ? `${chore.points_awarded} pts` : (chore.due_at ? _relativeDate(chore.due_at) : ""),
            actorCandidates: done ? [chore.completed_by] : [],
            timestampFields: done ? ["completed_at"] : (skipped ? ["skipped_at"] : []),
        });
    });
    shoppingItems.forEach((item) => {
        const checked = item.status === "checked";
        const pending = item.approval_status === "pending_parent_approval";
        const rejected = item.approval_status === "rejected";
        push(item, "Shopping", checked ? "checked off" : (rejected ? "rejected" : (pending ? "requested" : "added")), item.name || "item", {
            target: listNameById.get(item.list_id) || "Shopping",
            targetPrefix: checked ? "from" : "to",
            detail: item.quantity || item.category || "",
            actorCandidates: checked ? [item.checked_by] : (rejected ? [item.rejected_by] : [item.requested_by]),
            timestampFields: checked ? ["checked_at"] : (rejected ? ["rejected_at"] : ["approved_at"]),
        });
    });

    return activity.sort((a, b) => b.sortTime - a.sortTime);
}

function _activityTimestamp(entity, preferredFields = []) {
    const fields = [...preferredFields, "updated_at", "created_at", "start", "due_at"];
    for (const field of fields) {
        const value = entity?.[field];
        if (value && !Number.isNaN(new Date(value).getTime())) return value;
    }
    return "";
}

function _timestampMs(value) {
    const ms = value ? new Date(value).getTime() : 0;
    return Number.isNaN(ms) ? 0 : ms;
}

function _activityActor(entity, candidates = []) {
    const metadata = entity?.metadata && typeof entity.metadata === "object" ? entity.metadata : {};
    return [metadata._last_actor, ...candidates, entity?.actor].find((value) => value && String(value).trim()) || "system";
}

function _actorDisplay(actorId) {
    const raw = String(actorId || "family").trim();
    const normalized = raw.toLowerCase();
    const familyMember = (state.family?.members || []).find((member) =>
        String(member.actor_id || "").toLowerCase() === normalized || String(member.name || "").toLowerCase() === normalized
    );
    if (familyMember) {
        const memberMeta = MEMBERS[familyMember.name] || {};
        return { name: familyMember.name, initials: _initials(familyMember.name), color: memberMeta.color || _memberColor(familyMember.actor_id) };
    }
    for (const [name, meta] of Object.entries(MEMBERS)) {
        if (meta.key === normalized || name.toLowerCase() === normalized) {
            return { name, initials: meta.initials || _initials(name), color: meta.color };
        }
    }
    if (normalized.includes("concierge")) return { name: "Concierge", initials: "C", color: "#2563eb" };
    if (normalized === "system") return { name: "System", initials: "S", color: "#6b7280" };
    const name = _humanizeLabel(raw.replace(/[.:]/g, "_"));
    return { name, initials: _initials(name), color: _memberColor(raw) };
}

function _initials(name) {
    return String(name || "?").split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]?.toUpperCase() || "").join("") || "?";
}

function _relativeTimeAgo(isoStr) {
    const ms = _timestampMs(isoStr);
    if (!ms) return "recently";
    const diff = Date.now() - ms;
    if (diff < 60_000) return "just now";
    const minutes = Math.round(diff / 60_000);
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.round(minutes / 60);
    if (hours < 24) return `${hours}h ago`;
    const days = Math.round(hours / 24);
    if (days < 8) return `${days}d ago`;
    return new Date(ms).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function _reminderTriggerLabel(trigger) {
    if (!trigger || typeof trigger !== "object") return "";
    if (trigger.fire_at) return _relativeDate(trigger.fire_at);
    if (trigger.kind) return _humanizeLabel(trigger.kind);
    return "";
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
// Adapter views (Calendar / Tasks / Shopping / Reminders / Chores / Settings)
// ============================================================================

const adapterCache = {
    manifest: {},  // adapter_id → manifest
    listData: {},  // adapter_id → last list response
    context:  null,
};

const ADAPTER_FIELDS = {
    calendar:        ["start", "end", "all_day", "visibility"],
    tasks:           ["status", "priority", "due_at", "assigned_to"],
    shopping:        ["category", "status", "approval_status", "requested_by"],
    reminders:       ["recipient", "status", "trigger"],
    chores:          ["recurrence", "default_assignee", "reward_amount"],
    family_settings: ["enabled", "description", "scope"],
};

const SETTINGS_VISIBILITY_BANDS = [
    { value: "family",  label: "Family" },
    { value: "adults",  label: "Adults" },
    { value: "named",   label: "Named" },
    { value: "private", label: "Private" },
];

const SETTINGS_SOURCE_RULES = [
    { key: "native_default",   label: "Family-created items", meta: "Calendar, tasks, chores, shopping", defaultBand: "family" },
    { key: "google_work",      label: "Google work",          meta: "Work calendar imports",             defaultBand: "adults" },
    { key: "google_personal",  label: "Google personal",      meta: "Personal calendar imports",         defaultBand: "private" },
    { key: "outlook_default",  label: "Outlook",              meta: "Microsoft calendar imports",        defaultBand: "adults" },
    { key: "classroom",        label: "School and classroom",  meta: "Child school data",                 defaultBand: "family" },
];

const SETTINGS_KID_CAPABILITIES = [
    { key: "can_create_events",                   label: "Create family events",         defaultValue: true },
    { key: "can_create_reminders",                label: "Create reminders",             defaultValue: true },
    { key: "can_add_shopping_requests",           label: "Request shopping items",       defaultValue: true },
    { key: "can_mark_chores_complete",            label: "Mark chores complete",         defaultValue: true },
    { key: "can_see_parent_personal_calendar",    label: "See parent personal calendar", defaultValue: false },
    { key: "can_override_visibility",             label: "Override item visibility",     defaultValue: false },
    { key: "can_redeem_rewards_without_approval", label: "Redeem rewards directly",      defaultValue: false },
];

const calState = {
    year: new Date().getFullYear(),
    month: new Date().getMonth(),
    selectedDate: new Date().toISOString().slice(0, 10),
    events: [],
    feeds: [],
    manifest: null,
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
        case "shopping":         _renderShoppingView(viewId, manifest, writeActions, listData); break;
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
            if (action) showActionForm(aId, action, _actionDefaults(aId, actionName));
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
            if (adapterId === "shopping" && actionName === "add_item" && !state.shoppingSelectedListId) {
                showToast("Shopping", "Create or select a list before adding an item.");
                return;
            }
            if (action) showActionForm(adapterId, action, _actionDefaults(adapterId, actionName));
            else showToast("Action unavailable", `${actionName} not found in ${adapterId}`);
        });
    });
}

function _actionDefaults(adapterId, actionName) {
    if (adapterId === "calendar" && actionName === "create_event") {
        return _defaultEventTimes(calState.selectedDate);
    }
    if (adapterId === "tasks" && actionName === "create_task") {
        return {
            assigned_to: _currentMemberActorId(),
            list_id: state.tasksSelectedListId || undefined,
            priority: "medium",
        };
    }
    if (adapterId === "tasks" && actionName === "create_list") {
        return { color: "#2563eb" };
    }
    if (adapterId === "shopping" && actionName === "add_item" && state.shoppingSelectedListId) {
        return { list_id: state.shoppingSelectedListId };
    }
    if (adapterId === "reminders" && actionName === "create_reminder") {
        return {
            recipient: _currentMemberActorId(),
            trigger: { kind: "time", fire_at: _isoMinutesFromNow(60) },
            visibility: "family",
        };
    }
    if (adapterId === "chores" && actionName === "create_template") {
        return {
            assigned_to: _currentMemberActorId(),
            frequency: "weekly",
            base_points: 5,
            visibility: "family",
        };
    }
    if (adapterId === "family_settings" && actionName === "set_feature_flag") {
        return { enabled: true, scope: "space" };
    }
    if (adapterId === "family_settings" && actionName === "update_visibility_policy") {
        const policy = adapterCache.listData.family_settings?.policy || {};
        return {
            rules: policy.rules || {},
            sensitive_keywords: Array.isArray(policy.sensitive_keywords) ? policy.sensitive_keywords : [],
            kid_capabilities: policy.kid_capabilities || {},
        };
    }
    return {};
}

function _findAction(manifest, name) {
    return (manifest.actions || []).find((action) => action.name === name) || null;
}

function _hasAction(manifest, name) {
    return Boolean(_findAction(manifest, name));
}

function _openAdapterAction(adapterId, manifest, actionName, defaults = {}) {
    const action = _findAction(manifest, actionName);
    if (!action) {
        showToast("Action unavailable", `${actionName} not found in ${adapterId}`);
        return;
    }
    showActionForm(adapterId, action, defaults);
}

function _idOf(item, fallbackName = "id") {
    return item?.id || item?.[fallbackName] || "";
}

function _isoMinutesFromNow(minutes) {
    const d = new Date();
    d.setMinutes(d.getMinutes() + minutes);
    d.setSeconds(0, 0);
    return d.toISOString();
}

function _defaultEventTimes(dateIso) {
    const base = /^\d{4}-\d{2}-\d{2}$/.test(dateIso || "") ? dateIso : new Date().toISOString().slice(0, 10);
    return {
        start: new Date(`${base}T09:00:00`).toISOString(),
        end: new Date(`${base}T10:00:00`).toISOString(),
        visibility: "family",
    };
}

// ----------------------------------------------------------------------------
// Calendar view
// ----------------------------------------------------------------------------

function _renderCalendarView(viewId, manifest, writeActions, listData) {
    calState.events = Array.isArray(listData?.events) ? listData.events : _extractItems(listData);
    calState.feeds = Array.isArray(listData?.feeds) ? listData.feeds : [];
    calState.manifest = manifest;
    const body = dom.viewBody[viewId];

    const now = new Date();
    const todayIso = now.toISOString().slice(0, 10);
    const nextWeek = new Date(now);
    nextWeek.setDate(nextWeek.getDate() + 7);
    const upcoming = calState.events.filter((event) => event.start && new Date(event.start) >= now);
    const todayCount = calState.events.filter((event) => (event.start || "").slice(0, 10) === todayIso).length;
    const weekCount = upcoming.filter((event) => new Date(event.start) <= nextWeek).length;

    body.innerHTML = `
        <div class="cal-stats">
            <div class="cal-stat"><p class="cal-stat-label">Upcoming</p><p class="cal-stat-value">${upcoming.length}</p></div>
            <div class="cal-stat"><p class="cal-stat-label">Today</p><p class="cal-stat-value cal-stat-value--blue">${todayCount}</p></div>
            <div class="cal-stat"><p class="cal-stat-label">Next 7 Days</p><p class="cal-stat-value cal-stat-value--green">${weekCount}</p></div>
        </div>
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
                <div id="cal-selected-day"></div>
                <h3>Upcoming Events</h3>
                <div id="cal-upcoming"></div>
                ${calState.feeds.length ? `<div class="cal-feed-list"><h3>Feeds</h3><div id="cal-feeds"></div></div>` : ""}
            </aside>
        </div>`;

    _calRenderMonth();
    _calRenderSelectedDay();
    _calRenderUpcoming();
    _calRenderFeeds();

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
        const isSelected = calState.selectedDate === ds;
        const evs = evMap[ds] || [];
        const bars = evs.slice(0, 3).map((ev) =>
            `<div class="cal-event-bar" style="--bar-color:${_memberColor(ev.created_by || "")}" title="${escapeHtml(ev.title || "")}"></div>`
        ).join("");
        const more = evs.length > 3 ? `<span class="cal-more-events">+${evs.length - 3} more</span>` : "";
        html += `
            <button class="cal-cell${isToday ? " cal-cell--today" : ""}${isSelected ? " cal-cell--selected" : ""}" data-date="${ds}">
                <span class="cal-day-num">${d}</span>
                <div class="cal-event-bars">${bars}${more}</div>
            </button>`;
    }
    grid.innerHTML = html;
    grid.querySelectorAll(".cal-cell[data-date]").forEach((cell) => {
        cell.addEventListener("click", () => {
            calState.selectedDate = cell.dataset.date;
            _calRenderMonth();
            _calRenderSelectedDay();
        });
    });
}

function _calRenderSelectedDay() {
    const panel = document.getElementById("cal-selected-day");
    if (!panel) return;
    const manifest = calState.manifest || { actions: [] };
    const events = calState.events
        .filter((event) => (event.start || "").slice(0, 10) === calState.selectedDate)
        .sort((a, b) => String(a.start || "").localeCompare(String(b.start || "")));
    panel.innerHTML = `
        <div class="cal-selected-head">
            <div>
                <p class="cal-side-kicker">Selected Day</p>
                <h3>${escapeHtml(_formatDateLabel(calState.selectedDate))}</h3>
            </div>
            ${_hasAction(manifest, "create_event") ? `<button class="view-small-btn view-small-btn--primary" id="cal-add-selected">Add</button>` : ""}
        </div>
        <div class="cal-day-events">
            ${events.length === 0 ? `<p class="muted-empty">No events on this day.</p>` : events.map((event) => _renderCalendarEventRow(event, manifest)).join("")}
        </div>`;
    const add = panel.querySelector("#cal-add-selected");
    if (add) {
        add.addEventListener("click", () => _openAdapterAction("calendar", manifest, "create_event", _defaultEventTimes(calState.selectedDate)));
    }
    panel.querySelectorAll("[data-cal-action]").forEach((btn) => {
        btn.addEventListener("click", async () => {
            const eventId = btn.dataset.eventId;
            if (!eventId) return;
            await _submitAdapterAction("calendar", btn.dataset.calAction, { event_id: eventId });
        });
    });
}

function _renderCalendarEventRow(event, manifest) {
    const eventId = _idOf(event, "event_id");
    const canDelete = _hasAction(manifest, "delete_event") && eventId;
    return `
        <div class="cal-day-event-row">
            <div class="cal-day-event-dot" style="background:${_memberColor(event.created_by || event.actor || "")}"></div>
            <div class="cal-day-event-body">
                <p class="cal-day-event-title">${escapeHtml(event.title || "Untitled")}</p>
                <p class="cal-day-event-meta">${escapeHtml(_fmtEventTime(event.start, event.end, event.all_day))}${event.location ? ` · ${escapeHtml(event.location)}` : ""}</p>
            </div>
            ${canDelete ? `<button class="view-action-btn view-action-btn--danger" data-cal-action="delete_event" data-event-id="${escapeHtml(eventId)}">Remove</button>` : ""}
        </div>`;
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
    const manifest = calState.manifest || { actions: [] };
    list.innerHTML = upcoming.map((ev) => {
        const col = _memberColor(ev.created_by || "");
        const when = _fmtEventTime(ev.start, ev.end, ev.all_day);
        const eventId = _idOf(ev, "event_id");
        return `
            <div class="cal-event-card" style="--ev-color:${col}">
                <div class="cal-event-card-head">
                    <h4>${escapeHtml(ev.title || "Untitled")}</h4>
                    ${_hasAction(manifest, "delete_event") && eventId ? `<button class="view-action-btn view-action-btn--danger" data-cal-action="delete_event" data-event-id="${escapeHtml(eventId)}">Remove</button>` : ""}
                </div>
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
    list.querySelectorAll("[data-cal-action]").forEach((btn) => {
        btn.addEventListener("click", async () => {
            const eventId = btn.dataset.eventId;
            if (!eventId) return;
            await _submitAdapterAction("calendar", btn.dataset.calAction, { event_id: eventId });
        });
    });
}

function _calRenderFeeds() {
    const feedList = document.getElementById("cal-feeds");
    if (!feedList) return;
    feedList.innerHTML = calState.feeds.map((feed) => `
        <div class="cal-feed-row">
            <span>${escapeHtml(feed.feed_source || feed.source || "feed")}</span>
            <strong>${escapeHtml(feed.account || feed.source_label || "Connected")}</strong>
        </div>`).join("");
}

function _formatDateLabel(dateIso) {
    const d = new Date(`${dateIso}T00:00:00`);
    if (isNaN(d)) return dateIso || "Selected day";
    return d.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
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
    const items = Array.isArray(listData?.tasks) ? listData.tasks : _extractItems(listData);
    const lists = Array.isArray(listData?.lists) ? listData.lists : [];
    const body = dom.viewBody[viewId];

    if (state.tasksSelectedListId && !lists.some((list) => list.id === state.tasksSelectedListId)) {
        state.tasksSelectedListId = null;
    }
    const selectedListId = state.tasksSelectedListId || "__all__";
    const scopedItems = selectedListId === "__all__" ? items : items.filter((task) => (task.list_id || "") === selectedListId);

    const active = scopedItems.filter((t) => t.status !== "done" && t.status !== "cancelled");
    const completed = scopedItems.filter((t) => t.status === "done");
    const high = active.filter((t) => t.priority === "high").length;
    const dueToday = active.filter((t) => t.due_at && _relativeDate(t.due_at) === "Today").length;
    const actions = new Set((manifest.actions || []).map((action) => action.name));

    const listCount = (listId) => listId === "__all__"
        ? items.filter((task) => task.status !== "done" && task.status !== "cancelled").length
        : items.filter((task) => (task.list_id || "") === listId && task.status !== "done" && task.status !== "cancelled").length;

    const renderListButton = (list) => {
        const listId = list.id || "";
        const activeList = listId === selectedListId;
        return `
            <button class="task-list-tab${activeList ? " task-list-tab--active" : ""}" data-task-list-id="${escapeHtml(listId)}">
                <span class="task-list-name">${escapeHtml(list.name || "Untitled list")}</span>
                <span class="task-list-count">${listCount(listId)}</span>
            </button>`;
    };

    const renderRow = (t, done) => {
        const pri = t.priority || "normal";
        const due = t.due_at ? _relativeDate(t.due_at) : null;
        const assignee = t.assigned_to || "";
        const taskId = _idOf(t, "task_id");
        const canComplete = actions.has("complete_task") && taskId && !done;
        const canReopen = actions.has("reopen_task") && taskId && done;
        const canDelete = actions.has("delete_task") && taskId;
        return `
            <div class="task-row${done ? " task-row--done" : ""}">
                <button class="task-checkbox${done ? " task-checkbox--checked" : ""}" data-task-action="${done ? "reopen_task" : "complete_task"}" data-task-id="${escapeHtml(taskId)}" ${canComplete || canReopen ? "" : "disabled"} aria-label="${done ? "Reopen" : "Complete"} ${escapeHtml(t.title || "task")}">
                    ${done ? `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>` : ""}
                </button>
                <div class="task-body">
                    <p class="task-title">${escapeHtml(t.title || "Untitled")}</p>
                    <div class="task-meta">
                        ${assignee ? `<span class="task-meta-item"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>${escapeHtml(assignee)}</span>` : ""}
                        ${due ? `<span class="task-meta-item"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>${escapeHtml(due)}</span>` : ""}
                        ${t.list_id ? `<span class="task-meta-item">${escapeHtml(_taskListName(lists, t.list_id))}</span>` : ""}
                    </div>
                </div>
                ${pri && pri !== "normal" ? `<span class="task-priority task-priority--${pri}">${pri}</span>` : ""}
                <div class="task-actions">
                    ${done && canReopen ? `<button class="view-action-btn" data-task-action="reopen_task" data-task-id="${escapeHtml(taskId)}">Reopen</button>` : ""}
                    ${canDelete ? `<button class="view-action-btn view-action-btn--danger" data-task-action="delete_task" data-task-id="${escapeHtml(taskId)}">Remove</button>` : ""}
                </div>
            </div>`;
    };

    body.innerHTML = `
        <div class="task-stats">
            <div class="task-stat"><p class="task-stat-label">Active Tasks</p><p class="task-stat-value">${active.length}</p></div>
            <div class="task-stat"><p class="task-stat-label">Completed</p><p class="task-stat-value task-stat-value--green">${completed.length}</p></div>
            <div class="task-stat"><p class="task-stat-label">High Priority</p><p class="task-stat-value task-stat-value--red">${high}</p></div>
            <div class="task-stat"><p class="task-stat-label">Due Today</p><p class="task-stat-value task-stat-value--blue">${dueToday}</p></div>
        </div>

        <div class="task-layout">
            <aside class="task-lists">
                <div class="task-lists-header">
                    <h3>Lists</h3>
                    ${actions.has("create_list") ? `<button class="view-small-btn" data-app-action="tasks:create_list">New</button>` : ""}
                </div>
                <div class="task-list-tabs">
                    <button class="task-list-tab${selectedListId === "__all__" ? " task-list-tab--active" : ""}" data-task-list-id="__all__">
                        <span class="task-list-name">All tasks</span>
                        <span class="task-list-count">${listCount("__all__")}</span>
                    </button>
                    ${lists.map(renderListButton).join("")}
                </div>
            </aside>
            <section class="task-panel">
                <div class="task-panel-header">
                    <div>
                        <h3>${escapeHtml(selectedListId === "__all__" ? "Active Tasks" : _taskListName(lists, selectedListId))}</h3>
                        <p>${active.length} open · ${completed.length} done</p>
                    </div>
                    ${actions.has("create_task") ? `<button class="view-small-btn view-small-btn--primary" data-app-action="tasks:create_task">Add task</button>` : ""}
                </div>
                <div class="task-section task-section--flat">
                    ${active.length === 0
                        ? `<p class="muted-empty">All caught up.</p>`
                        : active.map((t) => renderRow(t, false)).join("")}
                </div>

                ${completed.length > 0 ? `
                <div class="task-section task-section--flat">
                    <h3>Completed</h3>
                    ${completed.map((t) => renderRow(t, true)).join("")}
                </div>` : ""}
            </section>
        </div>`;

    body.querySelectorAll("[data-task-list-id]").forEach((btn) => {
        btn.addEventListener("click", () => {
            state.tasksSelectedListId = btn.dataset.taskListId === "__all__" ? null : btn.dataset.taskListId;
            _renderAdapterBody(viewId, "tasks", manifest, writeActions, listData);
        });
    });
    body.querySelectorAll("[data-task-action]").forEach((btn) => {
        btn.addEventListener("click", async () => {
            const taskId = btn.dataset.taskId;
            const actionName = btn.dataset.taskAction;
            if (!taskId || !actionName || btn.disabled) return;
            await _submitAdapterAction("tasks", actionName, { task_id: taskId });
        });
    });
}

function _taskListName(lists, listId) {
    return (lists || []).find((list) => list.id === listId)?.name || "No list";
}

// ----------------------------------------------------------------------------
// Shopping view
// ----------------------------------------------------------------------------

function _renderShoppingView(viewId, manifest, writeActions, listData) {
    const body = dom.viewBody[viewId];
    const lists = Array.isArray(listData?.lists) ? listData.lists : [];
    const items = Array.isArray(listData?.items) ? listData.items : [];
    const actions = new Set((manifest.actions || []).map((action) => action.name));

    if (lists.length > 0 && !lists.some((list) => list.id === state.shoppingSelectedListId)) {
        state.shoppingSelectedListId = lists[0].id;
    }
    if (lists.length === 0) state.shoppingSelectedListId = null;

    const selectedList = lists.find((list) => list.id === state.shoppingSelectedListId) || lists[0] || null;
    if (selectedList) state.shoppingSelectedListId = selectedList.id;

    const selectedItems = selectedList
        ? items.filter((item) => item.list_id === selectedList.id)
        : items;
    const visibleItems = selectedItems.filter((item) => item.approval_status !== "rejected");
    const needed = visibleItems.filter((item) => item.status !== "checked");
    const checked = visibleItems.filter((item) => item.status === "checked");
    const pending = visibleItems.filter((item) => item.approval_status === "pending_parent_approval");

    const listCount = (listId) => items.filter((item) => item.list_id === listId && item.status !== "checked" && item.approval_status !== "rejected").length;
    const hasAction = (name) => actions.has(name);

    const renderListButton = (list) => {
        const active = list.id === state.shoppingSelectedListId;
        const count = listCount(list.id);
        return `
            <button class="shopping-list-tab${active ? " shopping-list-tab--active" : ""}" data-shopping-list-id="${escapeHtml(list.id || "")}">
                <span class="shopping-list-tab-name">${escapeHtml(list.name || "Untitled list")}</span>
                <span class="shopping-list-tab-meta">${escapeHtml(_humanizeLabel(list.category || "other"))}</span>
                <span class="shopping-list-tab-count">${count}</span>
            </button>`;
    };

    const renderItem = (item) => {
        const checkedOff = item.status === "checked";
        const pendingApproval = item.approval_status === "pending_parent_approval";
        const quantity = [item.quantity, item.unit].filter(Boolean).join(" ");
        const priority = item.priority || "medium";
        const canCheck = hasAction("check_off_item") && !checkedOff && !pendingApproval;
        const canApprove = hasAction("approve_item") && pendingApproval;
        const canDelete = hasAction("delete_item");
        return `
            <div class="shopping-row${checkedOff ? " shopping-row--checked" : ""}${pendingApproval ? " shopping-row--pending" : ""}">
                <button class="shopping-check${checkedOff ? " shopping-check--checked" : ""}" data-shopping-action="check_off_item" data-item-id="${escapeHtml(item.id || "")}" ${canCheck ? "" : "disabled"} aria-label="Check off ${escapeHtml(item.name || "item")}">
                    ${checkedOff ? `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>` : ""}
                </button>
                <div class="shopping-item-body">
                    <p class="shopping-item-title">${quantity ? `<span>${escapeHtml(quantity)}</span>` : ""}${escapeHtml(item.name || "Untitled item")}</p>
                    <div class="shopping-item-meta">
                        ${item.category ? `<span>${escapeHtml(_humanizeLabel(item.category))}</span>` : ""}
                        ${item.requested_by ? `<span>Requested by ${escapeHtml(item.requested_by)}</span>` : ""}
                        ${item.notes ? `<span>${escapeHtml(item.notes)}</span>` : ""}
                    </div>
                </div>
                <div class="shopping-badges">
                    ${pendingApproval ? `<span class="shopping-badge shopping-badge--pending">pending approval</span>` : ""}
                    ${checkedOff ? `<span class="shopping-badge shopping-badge--checked">checked</span>` : ""}
                    ${priority !== "medium" ? `<span class="shopping-badge shopping-badge--${escapeHtml(priority)}">${escapeHtml(priority)}</span>` : ""}
                </div>
                <div class="shopping-actions">
                    ${canApprove ? `<button class="shopping-action-btn" data-shopping-action="approve_item" data-item-id="${escapeHtml(item.id || "")}">Approve</button>` : ""}
                    ${canDelete ? `<button class="shopping-action-btn shopping-action-btn--danger" data-shopping-action="delete_item" data-item-id="${escapeHtml(item.id || "")}" aria-label="Remove ${escapeHtml(item.name || "item")}">Remove</button>` : ""}
                </div>
            </div>`;
    };

    body.innerHTML = `
        <div class="shopping-stats">
            <div class="shopping-stat"><p class="shopping-stat-label">Lists</p><p class="shopping-stat-value">${lists.length}</p></div>
            <div class="shopping-stat"><p class="shopping-stat-label">Needed</p><p class="shopping-stat-value shopping-stat-value--blue">${needed.length}</p></div>
            <div class="shopping-stat"><p class="shopping-stat-label">Pending</p><p class="shopping-stat-value shopping-stat-value--orange">${pending.length}</p></div>
        </div>
        <div class="shopping-layout">
            <aside class="shopping-lists">
                <div class="shopping-lists-header">
                    <h3>Lists</h3>
                    ${hasAction("create_list") ? `<button class="shopping-small-btn" data-app-action="shopping:create_list">New</button>` : ""}
                </div>
                <div class="shopping-list-tabs">
                    ${lists.length === 0 ? `<p class="muted-empty">No shopping lists yet.</p>` : lists.map(renderListButton).join("")}
                </div>
            </aside>
            <section class="shopping-panel">
                <div class="shopping-panel-header">
                    <div>
                        <h3>${escapeHtml(selectedList?.name || "Shopping")}</h3>
                        ${selectedList?.category ? `<p>${escapeHtml(_humanizeLabel(selectedList.category))}</p>` : ""}
                    </div>
                    ${selectedList && hasAction("add_item") ? `<button class="shopping-small-btn shopping-small-btn--primary" data-app-action="shopping:add_item">Add item</button>` : ""}
                </div>
                <div class="shopping-items">
                    ${selectedList == null
                        ? `<div class="view-empty">Create a shopping list to start tracking items.</div>`
                        : visibleItems.length === 0
                            ? `<div class="view-empty">No items in this list yet.</div>`
                            : `
                                ${needed.length ? `<div class="shopping-section-label">Needed</div>${needed.map(renderItem).join("")}` : ""}
                                ${checked.length ? `<div class="shopping-section-label">Checked off</div>${checked.map(renderItem).join("")}` : ""}
                            `}
                </div>
            </section>
        </div>`;

    body.querySelectorAll("[data-shopping-list-id]").forEach((btn) => {
        btn.addEventListener("click", () => {
            state.shoppingSelectedListId = btn.dataset.shoppingListId;
            _renderAdapterBody(viewId, "shopping", manifest, writeActions, listData);
        });
    });
    body.querySelectorAll("[data-shopping-action]").forEach((btn) => {
        btn.addEventListener("click", async () => {
            const itemId = btn.dataset.itemId;
            const actionName = btn.dataset.shoppingAction;
            if (!itemId || !actionName || btn.disabled) return;
            await _submitAdapterAction("shopping", actionName, { item_id: itemId });
        });
    });
}

// ----------------------------------------------------------------------------
// Reminders view
// ----------------------------------------------------------------------------

function _renderRemindersView(viewId, manifest, writeActions, listData) {
    const items = _extractItems(listData);
    const body = dom.viewBody[viewId];
    const actions = new Set((manifest.actions || []).map((action) => action.name));

    const order = { scheduled: 0, snoozed: 1, fired: 2, dismissed: 3 };
    const sorted = [...items].sort((a, b) => {
        const oa = order[a.status] ?? 9, ob = order[b.status] ?? 9;
        if (oa !== ob) return oa - ob;
        return ((a.trigger?.fire_at || a.fire_at || "")).localeCompare(b.trigger?.fire_at || b.fire_at || "");
    });

    const scheduled = sorted.filter((r) => r.status === "scheduled" || r.status === "snoozed");
    const fired = sorted.filter((r) => r.status === "fired");
    const dueToday = scheduled.filter((r) => {
        const fireAt = r.trigger?.fire_at || r.fire_at || r.snoozed_until;
        return fireAt && _relativeDate(fireAt) === "Today";
    }).length;

    body.innerHTML = `
        <div class="reminder-stats">
            <div class="reminder-stat"><p class="reminder-stat-label">Scheduled</p><p class="reminder-stat-value">${scheduled.length}</p></div>
            <div class="reminder-stat"><p class="reminder-stat-label">Due Today</p><p class="reminder-stat-value reminder-stat-value--blue">${dueToday}</p></div>
            <div class="reminder-stat"><p class="reminder-stat-label">Needs Attention</p><p class="reminder-stat-value reminder-stat-value--orange">${fired.length}</p></div>
        </div>
        <div class="reminder-list">
            ${sorted.length === 0 ? `<div class="view-empty">No reminders yet. Add one above.</div>` : sorted.map((r) => {
                const fireAt = r.trigger?.fire_at || r.fire_at;
                const kind = r.trigger?.kind || "time";
                const timeStr = fireAt ? _fmtReminderTime(fireAt) : "";
                const status = r.status || "scheduled";
                const muted = status === "fired" || status === "dismissed";
                const reminderId = _idOf(r, "reminder_id");
                const canDismiss = actions.has("dismiss_reminder") && reminderId && (status === "fired" || status === "snoozed");
                const canSnooze = actions.has("snooze_reminder") && reminderId && (status === "fired" || status === "snoozed");
                const canDelete = actions.has("delete_reminder") && reminderId;
                return `
                    <div class="reminder-row${muted ? " reminder-row--muted" : ""}">
                        <div class="reminder-icon">${_reminderKindIcon(kind)}</div>
                        <div class="reminder-body">
                            <p class="reminder-title">${escapeHtml(r.title || "Reminder")}</p>
                            <div class="reminder-meta">
                                ${timeStr ? `<span class="reminder-time">${escapeHtml(timeStr)}</span>` : ""}
                                ${r.recipient ? `<span class="reminder-recipient" style="--member-color:${_memberColor(r.recipient)};background:${_memberColor(r.recipient)}">${escapeHtml(r.recipient)}</span>` : ""}
                                ${r.message ? `<span style="color:var(--text-tertiary)">${escapeHtml(String(r.message).slice(0, 60))}${r.message.length > 60 ? "…" : ""}</span>` : ""}
                            </div>
                        </div>
                        <span class="reminder-status reminder-status--${status}">${escapeHtml(_humanizeLabel(status))}</span>
                        <div class="reminder-actions">
                            ${canSnooze ? `<button class="view-action-btn" data-reminder-action="snooze_reminder" data-reminder-id="${escapeHtml(reminderId)}">Snooze 10m</button>` : ""}
                            ${canDismiss ? `<button class="view-action-btn" data-reminder-action="dismiss_reminder" data-reminder-id="${escapeHtml(reminderId)}">Dismiss</button>` : ""}
                            ${canDelete ? `<button class="view-action-btn view-action-btn--danger" data-reminder-action="delete_reminder" data-reminder-id="${escapeHtml(reminderId)}">Remove</button>` : ""}
                        </div>
                    </div>`;
            }).join("")}
        </div>`;

    body.querySelectorAll("[data-reminder-action]").forEach((btn) => {
        btn.addEventListener("click", async () => {
            const reminderId = btn.dataset.reminderId;
            const actionName = btn.dataset.reminderAction;
            if (!reminderId || !actionName) return;
            const params = actionName === "snooze_reminder"
                ? { reminder_id: reminderId, snooze_until: _isoMinutesFromNow(10) }
                : { reminder_id: reminderId };
            await _submitAdapterAction("reminders", actionName, params);
        });
    });
}

function _reminderKindIcon(kind) {
    if (kind === "location_enter" || kind === "location_leave") {
        return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 10c0 7-9 13-9 13S3 17 3 10a9 9 0 1 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>`;
    }
    if (kind === "event_offset") {
        return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>`;
    }
    return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>`;
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
    const items = Array.isArray(listData?.chores) ? listData.chores : _extractItems(listData);
    const summary = Array.isArray(listData?.summary) ? listData.summary : [];
    const body = dom.viewBody[viewId];
    const actions = new Set((manifest.actions || []).map((action) => action.name));

    const pending = items.filter((chore) => (chore.status || "pending") === "pending");
    const done = items.filter((chore) => chore.status === "done");
    const skipped = items.filter((chore) => chore.status === "skipped");
    const points = done.reduce((total, chore) => total + Number(chore.points_awarded || 0), 0);

    const renderChore = (chore) => {
        const occurrenceId = _idOf(chore, "occurrence_id");
        const status = chore.status || "pending";
        const assignee = chore.assigned_to || "";
        const due = chore.due_at ? _relativeDate(chore.due_at) : null;
        const canComplete = status === "pending" && actions.has("complete_chore") && occurrenceId;
        const canSkip = status === "pending" && actions.has("skip_chore") && occurrenceId;
        const canReopen = status !== "pending" && actions.has("reopen_chore") && occurrenceId;
        return `
            <div class="chore-card chore-card--${escapeHtml(status)}">
                <div class="chore-card-top">
                    <span class="chore-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7h18"/><path d="M6 7v14h12V7"/><path d="M9 7V4h6v3"/></svg></span>
                    <span class="chore-reward">${Number(chore.points_awarded || chore.base_points || 0)} pts</span>
                </div>
                <p class="chore-title">${escapeHtml(chore.title || "Chore")}</p>
                ${chore.description ? `<p class="chore-desc">${escapeHtml(String(chore.description).slice(0, 90))}</p>` : ""}
                <div class="chore-meta">
                    ${status ? `<span class="chore-recur">${escapeHtml(_humanizeLabel(status))}</span>` : ""}
                    ${due ? `<span class="chore-recur">${escapeHtml(due)}</span>` : ""}
                    ${assignee ? `<span class="chore-assignee" style="background:${_memberColor(assignee)}" title="${escapeHtml(assignee)}">${escapeHtml(assignee.slice(0, 2).toUpperCase())}</span>` : ""}
                </div>
                <div class="chore-actions">
                    ${canComplete ? `<button class="view-action-btn" data-chore-action="complete_chore" data-occurrence-id="${escapeHtml(occurrenceId)}">Done</button>` : ""}
                    ${canSkip ? `<button class="view-action-btn" data-chore-action="skip_chore" data-occurrence-id="${escapeHtml(occurrenceId)}">Skip</button>` : ""}
                    ${canReopen ? `<button class="view-action-btn" data-chore-action="reopen_chore" data-occurrence-id="${escapeHtml(occurrenceId)}">Reopen</button>` : ""}
                </div>
            </div>`;
    };

    const renderColumn = (title, rows, empty) => `
        <section class="chore-column">
            <div class="chore-column-head"><h3>${escapeHtml(title)}</h3><span>${rows.length}</span></div>
            <div class="chore-column-list">${rows.length ? rows.map(renderChore).join("") : `<p class="muted-empty">${escapeHtml(empty)}</p>`}</div>
        </section>`;

    body.innerHTML = `
        <div class="chore-stats">
            <div class="chore-stat"><p class="chore-stat-label">Pending</p><p class="chore-stat-value">${pending.length}</p></div>
            <div class="chore-stat"><p class="chore-stat-label">Done</p><p class="chore-stat-value chore-stat-value--green">${done.length}</p></div>
            <div class="chore-stat"><p class="chore-stat-label">Skipped</p><p class="chore-stat-value chore-stat-value--orange">${skipped.length}</p></div>
            <div class="chore-stat"><p class="chore-stat-label">Points</p><p class="chore-stat-value chore-stat-value--blue">${points}</p></div>
        </div>
        <div class="chores-layout">
            <div class="chores-board">
                ${renderColumn("To Do", pending, "No pending chores.")}
                ${renderColumn("Done", done, "Nothing completed yet.")}
                ${renderColumn("Skipped", skipped, "No skipped chores.")}
            </div>
            <aside class="chore-summary">
                <div class="chore-summary-head">
                    <h3>Leaderboard</h3>
                    ${actions.has("create_template") ? `<button class="view-small-btn" data-app-action="chores:create_template">New template</button>` : ""}
                </div>
                ${summary.length === 0
                    ? `<p class="muted-empty">Chore points will appear here.</p>`
                    : summary.sort((a, b) => Number(b.total_points || 0) - Number(a.total_points || 0)).map((row) => `
                        <div class="chore-summary-row">
                            <span>${escapeHtml(row.member_id || "Unassigned")}</span>
                            <strong>${Number(row.total_points || 0)} pts</strong>
                        </div>`).join("")}
            </aside>
        </div>`;

    body.querySelectorAll("[data-chore-action]").forEach((btn) => {
        btn.addEventListener("click", async () => {
            const occurrenceId = btn.dataset.occurrenceId;
            const actionName = btn.dataset.choreAction;
            if (!occurrenceId || !actionName) return;
            await _submitAdapterAction("chores", actionName, { occurrence_id: occurrenceId });
        });
    });
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
    const flags = Array.isArray(listData?.flags) ? listData.flags : _extractItems(listData).filter((i) => "flag_name" in i || "enabled" in i);
    const policy = listData?.policy || null;
    const body = dom.viewBody[viewId];
    const rules = policy?.rules || {};
    const keywords = Array.isArray(policy?.sensitive_keywords) ? policy.sensitive_keywords : [];
    const kidCaps = policy?.kid_capabilities || {};
    const canUpdatePolicy = _hasAction(manifest, "update_visibility_policy");
    const enabledFlagCount = flags.filter((flag) => Boolean(flag.enabled)).length;
    const customizedRules = SETTINGS_SOURCE_RULES.filter((source) => Object.prototype.hasOwnProperty.call(rules, source.key)).length;
    const customizedKidCaps = SETTINGS_KID_CAPABILITIES.filter((cap) => Object.prototype.hasOwnProperty.call(kidCaps, cap.key)).length;

    const bandOptions = (selected) => SETTINGS_VISIBILITY_BANDS.map((band) =>
        `<option value="${escapeHtml(band.value)}" ${selected === band.value ? "selected" : ""}>${escapeHtml(band.label)}</option>`
    ).join("");

    const renderSourceRule = (source) => {
        const customized = Object.prototype.hasOwnProperty.call(rules, source.key);
        const band = rules[source.key] || source.defaultBand;
        return `
            <div class="settings-source-row">
                <div class="settings-source-copy">
                    <p class="settings-source-name">${escapeHtml(source.label)}</p>
                    <p class="settings-source-meta">${escapeHtml(source.meta)}</p>
                </div>
                <div class="settings-source-controls">
                    <span class="settings-pill ${customized ? "settings-pill--custom" : ""}">${customized ? "Custom" : "Default"}</span>
                    <select class="settings-select" data-setting-rule="${escapeHtml(source.key)}" data-current-band="${escapeHtml(band)}" ${canUpdatePolicy ? "" : "disabled"}>
                        ${bandOptions(band)}
                    </select>
                </div>
            </div>`;
    };

    const renderKidCapability = (cap) => {
        const customized = Object.prototype.hasOwnProperty.call(kidCaps, cap.key);
        const enabled = customized ? Boolean(kidCaps[cap.key]) : cap.defaultValue;
        return `
            <div class="settings-permission-row">
                <div class="settings-permission-copy">
                    <p class="settings-permission-name">${escapeHtml(cap.label)}</p>
                    <span class="settings-pill ${customized ? "settings-pill--custom" : ""}">${customized ? "Custom" : "Default"}</span>
                </div>
                <div class="toggle settings-capability-toggle${enabled ? " toggle--on" : ""}" data-kid-capability="${escapeHtml(cap.key)}" data-enabled="${enabled}" role="switch" aria-checked="${enabled}" tabindex="0" ${canUpdatePolicy ? "" : "aria-disabled=\"true\""}>
                    <div class="toggle-thumb"></div>
                </div>
            </div>`;
    };

    const renderFlag = (flag) => {
        const name = flag.flag_name || flag.name || flag.id || "flag";
        const enabled = Boolean(flag.enabled);
        const desc = flag.description || flag.scope || "";
        return `
            <div class="flag-row">
                <div class="flag-info">
                    <p class="flag-name">${escapeHtml(_humanizeLabel(name))}</p>
                    ${desc ? `<p class="flag-desc">${escapeHtml(desc)}</p>` : ""}
                </div>
                <div class="toggle settings-flag-toggle${enabled ? " toggle--on" : ""}" data-flag="${escapeHtml(name)}" data-enabled="${enabled}" role="switch" aria-checked="${enabled}" tabindex="0">
                    <div class="toggle-thumb"></div>
                </div>
            </div>`;
    };

    body.innerHTML = `
        <div class="settings-overview">
            <div class="settings-stat"><span>Privacy Rules</span><strong>${customizedRules}/${SETTINGS_SOURCE_RULES.length}</strong></div>
            <div class="settings-stat"><span>Sensitive Terms</span><strong>${keywords.length}</strong></div>
            <div class="settings-stat"><span>Kid Permissions</span><strong>${customizedKidCaps}/${SETTINGS_KID_CAPABILITIES.length}</strong></div>
            <div class="settings-stat"><span>Features On</span><strong>${enabledFlagCount}</strong></div>
        </div>
        <div class="settings-grid">
            <section class="settings-section settings-section--wide">
                <div class="settings-section-head">
                    <div>
                        <p class="settings-section-title">Family Privacy</p>
                        <h3>Default visibility by source</h3>
                    </div>
                    ${canUpdatePolicy ? `<button class="view-small-btn" data-app-action="family_settings:update_visibility_policy">Advanced</button>` : ""}
                </div>
                ${policy == null ? `<p class="muted-empty">No policy document visible.</p>` : `
                    <div class="settings-source-list">
                        ${SETTINGS_SOURCE_RULES.map(renderSourceRule).join("")}
                    </div>`}
            </section>

            <section class="settings-section">
                <div class="settings-section-head">
                    <div>
                        <p class="settings-section-title">Sensitive Information</p>
                        <h3>Adults-only terms</h3>
                    </div>
                </div>
                <div class="settings-keywords">
                    ${keywords.length === 0
                        ? `<p class="muted-empty">No sensitive terms configured.</p>`
                        : `<div class="settings-keyword-list">${keywords.map((kw) => `
                            <span class="settings-keyword-chip">${escapeHtml(kw)}${canUpdatePolicy ? `<button type="button" data-keyword-remove="${escapeHtml(kw)}" aria-label="Remove ${escapeHtml(kw)}">&times;</button>` : ""}</span>`).join("")}</div>`}
                    ${canUpdatePolicy ? `
                        <div class="settings-keyword-add">
                            <input type="text" class="settings-keyword-input" data-keyword-input placeholder="doctor, salary, therapy" aria-label="Add sensitive terms">
                            <button type="button" class="view-small-btn" data-keyword-add>Add</button>
                        </div>` : ""}
                </div>
            </section>

            <section class="settings-section">
                <div class="settings-section-head">
                    <div>
                        <p class="settings-section-title">Kid Permissions</p>
                        <h3>Child capability gates</h3>
                    </div>
                </div>
                <div class="settings-permission-list">
                    ${SETTINGS_KID_CAPABILITIES.map(renderKidCapability).join("")}
                </div>
            </section>

            <section class="settings-section settings-section--advanced">
                <div class="settings-section-head">
                    <div>
                        <p class="settings-section-title">Features</p>
                        <h3>Family feature flags</h3>
                    </div>
                    ${_hasAction(manifest, "set_feature_flag") ? `<button class="view-small-btn" data-app-action="family_settings:set_feature_flag">New flag</button>` : ""}
                </div>
                ${flags.length === 0 ? `<p class="muted-empty">No feature flags configured.</p>` : flags.map(renderFlag).join("")}
            </section>
        </div>`;

    body.querySelectorAll("[data-setting-rule]").forEach((select) => {
        select.addEventListener("change", () => _setVisibilityRule(select));
    });
    body.querySelectorAll("[data-keyword-remove]").forEach((btn) => {
        btn.addEventListener("click", () => _removeSensitiveKeyword(btn.dataset.keywordRemove, btn));
    });
    const keywordInput = body.querySelector("[data-keyword-input]");
    const keywordAdd = body.querySelector("[data-keyword-add]");
    if (keywordAdd && keywordInput) {
        keywordAdd.addEventListener("click", () => _addSensitiveKeywords(keywordInput, keywordAdd));
        keywordInput.addEventListener("keydown", (event) => {
            if (event.key === "Enter") {
                event.preventDefault();
                _addSensitiveKeywords(keywordInput, keywordAdd);
            }
        });
    }
    body.querySelectorAll(".settings-capability-toggle").forEach((tog) => {
        tog.addEventListener("click", () => _toggleKidCapability(tog));
        tog.addEventListener("keydown", (e) => {
            if (e.key === " " || e.key === "Enter") {
                e.preventDefault();
                _toggleKidCapability(tog);
            }
        });
    });
    body.querySelectorAll(".settings-flag-toggle").forEach((tog) => {
        tog.addEventListener("click", () => _toggleFlag(tog, manifest));
        tog.addEventListener("keydown", (e) => {
            if (e.key === " " || e.key === "Enter") {
                e.preventDefault();
                _toggleFlag(tog, manifest);
            }
        });
    });
}

function _settingsCurrentPolicy() {
    return adapterCache.listData.family_settings?.policy || {};
}

function _settingsCurrentKeywords() {
    const policy = _settingsCurrentPolicy();
    return Array.isArray(policy.sensitive_keywords) ? policy.sensitive_keywords.map(String) : [];
}

async function _setVisibilityRule(select) {
    const key = select.dataset.settingRule;
    const value = select.value;
    const previous = select.dataset.currentBand;
    if (!key || !value) return;
    const saved = await _updateSettingsPolicy({ rules: { [key]: value } }, select, "Privacy rule updated.");
    if (!saved) select.value = previous;
}

async function _addSensitiveKeywords(input, button) {
    const additions = String(input.value || "")
        .split(",")
        .map((value) => value.trim().toLowerCase())
        .filter(Boolean);
    if (!additions.length) return;
    const current = _settingsCurrentKeywords();
    const seen = new Set(current.map((value) => value.toLowerCase()));
    const next = [...current];
    additions.forEach((value) => {
        if (!seen.has(value)) {
            seen.add(value);
            next.push(value);
        }
    });
    input.value = "";
    await _updateSettingsPolicy({ sensitive_keywords: next }, button, "Sensitive terms updated.");
}

async function _removeSensitiveKeyword(keyword, button) {
    if (!keyword) return;
    const next = _settingsCurrentKeywords().filter((value) => value !== keyword);
    await _updateSettingsPolicy({ sensitive_keywords: next }, button, "Sensitive terms updated.");
}

async function _toggleKidCapability(tog) {
    if (tog.getAttribute("aria-disabled") === "true") return;
    const key = tog.dataset.kidCapability;
    const current = tog.dataset.enabled === "true";
    if (!key) return;
    await _updateSettingsPolicy({ kid_capabilities: { [key]: !current } }, tog, "Kid permissions updated.");
}

async function _updateSettingsPolicy(patch, pendingEl, message) {
    const manifest = adapterCache.manifest.family_settings || {};
    if (!_hasAction(manifest, "update_visibility_policy")) {
        showToast("Settings", "Policy editing is unavailable.");
        return false;
    }

    pendingEl?.classList?.add("settings-pending");
    if (pendingEl && "disabled" in pendingEl) pendingEl.disabled = true;
    try {
        const resp = await fetch("/k1/tools/family_settings/update_visibility_policy", {
            method: "POST",
            headers: { ...buildAppsHeaders(), "Content-Type": "application/json" },
            body: JSON.stringify(patch || {}),
        });
        const result = resp.ok ? await resp.json() : { success: false, error: `HTTP ${resp.status}` };
        if (result.success === false) {
            showToast("Action failed", result.error || result.error_code || "Unknown error", 7000);
            return false;
        }
        showToast("Settings", message || "Settings saved.");
        await loadAdapterView("settings");
        return true;
    } catch (e) {
        showToast("Error", e.message, 7000);
        return false;
    } finally {
        pendingEl?.classList?.remove("settings-pending");
        if (pendingEl && "disabled" in pendingEl) pendingEl.disabled = false;
    }
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
            await loadAdapterView("settings");
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

function showActionForm(adapterId, actionSpec, defaults = {}) {
    _pendingAction = { adapterId, actionSpec, defaults };

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
        const defaultValue = defaults[name];
        const inputType = schema.type === "boolean" ? "checkbox"
            : (schema.type === "integer" || schema.type === "number" ? "number" : "text");
        const placeholder = schema.description || schema.format || name;
        const encodedDefault = typeof defaultValue === "object" && defaultValue !== null
            ? JSON.stringify(defaultValue, null, 2)
            : (defaultValue ?? "");

        if (defaultValue !== undefined && name.endsWith("_id")) {
            return `<input id="af-${escapeHtml(name)}" name="${escapeHtml(name)}" type="hidden" class="action-field-input" data-field-type="${escapeHtml(schema.type || "string")}" value="${escapeHtml(encodedDefault)}">`;
        }

        if (inputType === "checkbox") {
            return `
                <div class="action-form-field action-form-field--check">
                    <input id="af-${escapeHtml(name)}" name="${escapeHtml(name)}" type="checkbox" class="action-field-input action-field-checkbox" ${defaultValue ? "checked" : ""}>
                    <label class="action-field-label" for="af-${escapeHtml(name)}">${escapeHtml(label)}</label>
                </div>`;
        }
        if (schema.type === "object" || schema.type === "array") {
            return `
                <div class="action-form-field">
                    <label class="action-field-label" for="af-${escapeHtml(name)}">${escapeHtml(label)}${isReq ? ' <span class="af-req">*</span>' : ""}</label>
                    <textarea id="af-${escapeHtml(name)}" name="${escapeHtml(name)}" data-field-type="${escapeHtml(schema.type)}"
                              placeholder="${escapeHtml(placeholder)}" class="action-field-input action-field-textarea" ${isReq ? "required" : ""}>${escapeHtml(encodedDefault)}</textarea>
                </div>`;
        }
        return `
            <div class="action-form-field">
                <label class="action-field-label" for="af-${escapeHtml(name)}">${escapeHtml(label)}${isReq ? ' <span class="af-req">*</span>' : ""}</label>
                <input id="af-${escapeHtml(name)}" name="${escapeHtml(name)}" type="${inputType}"
                       data-field-type="${escapeHtml(schema.type || "string")}" placeholder="${escapeHtml(placeholder)}" class="action-field-input" value="${escapeHtml(encodedDefault)}" ${isReq ? "required" : ""}>
            </div>`;
    }).join("");

    if (!Object.keys(properties).length) {
        fields.innerHTML = `<p class="muted-empty">No additional parameters needed.</p>`;
    }

    modal.classList.remove("hidden");
}

async function _submitAdapterAction(adapterId, actionName, params) {
    const manifest = adapterCache.manifest[adapterId] || {};
    const actionSpec = (manifest.actions || []).find((action) => action.name === actionName);
    const label = actionSpec?.label || _humanizeLabel(actionName);

    try {
        const resp = await fetch(`/k1/tools/${adapterId}/${actionName}`, {
            method: "POST",
            headers: { ...buildAppsHeaders(), "Content-Type": "application/json" },
            body: JSON.stringify(params || {}),
        });
        const result = resp.ok ? await resp.json() : { success: false, error: `HTTP ${resp.status}` };
        if (result.success !== false) {
            showToast("Done", `${label} completed.`);
            const viewId = Object.entries(ADAPTER_BACKEND_NAME).find(([, b]) => b === adapterId)?.[0];
            if (viewId) await loadAdapterView(viewId);
            if (state.currentView === "home") loadHomeDashboard();
        } else {
            showToast("Action failed", result.error || result.error_message || result.error_code || "Unknown error", 7000);
        }
    } catch (e) {
        showToast("Error", e.message, 7000);
    }
}

async function submitActionForm() {
    if (!_pendingAction) return;
    const { adapterId, actionSpec } = _pendingAction;

    const modal = document.getElementById("action-form-modal");
    const inputs = modal.querySelectorAll(".action-field-input");
    const properties = actionSpec.params?.properties || {};
    const params = {};
    try {
        inputs.forEach((input) => {
            if (!input.name) return;
            const value = _parseActionInput(input, properties[input.name] || {});
            if (value !== undefined) params[input.name] = value;
        });
    } catch (e) {
        showToast("Check the form", e.message, 7000);
        return;
    }

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

function _parseActionInput(input, schema) {
    if (input.type === "checkbox") return Boolean(input.checked);
    const raw = input.value;
    if (raw === "") return undefined;
    const type = schema.type || input.dataset.fieldType || "string";
    if (type === "integer") {
        const value = Number.parseInt(raw, 10);
        if (Number.isNaN(value)) throw new Error(`${_humanizeLabel(input.name)} must be a number.`);
        return value;
    }
    if (type === "number") {
        const value = Number.parseFloat(raw);
        if (Number.isNaN(value)) throw new Error(`${_humanizeLabel(input.name)} must be a number.`);
        return value;
    }
    if (type === "object" || type === "array") {
        try {
            const parsed = JSON.parse(raw);
            if (type === "array" && !Array.isArray(parsed)) throw new Error("array");
            if (type === "object" && (parsed === null || Array.isArray(parsed) || typeof parsed !== "object")) throw new Error("object");
            return parsed;
        } catch {
            throw new Error(`${_humanizeLabel(input.name)} must be valid JSON ${type}.`);
        }
    }
    return raw;
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
    const readAction = (name) => (manifest.actions || []).find((a) => a.kind === "read" && a.name === name);

    if (adapterId === "calendar") {
        const eventAction = readAction("list_events");
        const feedAction = readAction("list_feeds");
        const [eventData, feedData] = await Promise.all([
            eventAction ? _callListAction(adapterId, eventAction) : null,
            feedAction ? _callListAction(adapterId, feedAction) : null,
        ]);
        return {
            success: true,
            events: Array.isArray(eventData?.events) ? eventData.events : [],
            feeds: Array.isArray(feedData?.feeds) ? feedData.feeds : [],
            event_result: eventData,
            feed_result: feedData,
        };
    }

    if (adapterId === "tasks") {
        const taskAction = readAction("list_tasks");
        const listAction = readAction("list_lists");
        const [taskData, listData] = await Promise.all([
            taskAction ? _callListAction(adapterId, taskAction) : null,
            listAction ? _callListAction(adapterId, listAction) : null,
        ]);
        return {
            success: true,
            tasks: Array.isArray(taskData?.tasks) ? taskData.tasks : [],
            lists: Array.isArray(listData?.lists) ? listData.lists : [],
            task_result: taskData,
            list_result: listData,
        };
    }

    if (adapterId === "shopping") {
        const listAction = readAction("list_lists");
        const itemAction = readAction("list_items");
        const [listData, itemData] = await Promise.all([
            listAction ? _callListAction(adapterId, listAction) : null,
            itemAction ? _callListAction(adapterId, itemAction) : null,
        ]);
        return {
            success: true,
            lists: Array.isArray(listData?.lists) ? listData.lists : [],
            items: Array.isArray(itemData?.items) ? itemData.items : [],
            list_result: listData,
            item_result: itemData,
        };
    }

    if (adapterId === "chores") {
        const choreAction = readAction("list_chores");
        const summaryAction = readAction("chore_summary");
        const [choreData, summaryData] = await Promise.all([
            choreAction ? _callListAction(adapterId, choreAction) : null,
            summaryAction ? _callListAction(adapterId, summaryAction) : null,
        ]);
        return {
            success: true,
            chores: Array.isArray(choreData?.chores) ? choreData.chores : [],
            summary: Array.isArray(summaryData?.summary) ? summaryData.summary : [],
            chore_result: choreData,
            summary_result: summaryData,
        };
    }

    if (adapterId === "family_settings") {
        const policyAction = readAction("get_visibility_policy");
        const flagsAction = readAction("list_feature_flags");
        const [policyData, flagsData] = await Promise.all([
            policyAction ? _callListAction(adapterId, policyAction) : null,
            flagsAction ? _callListAction(adapterId, flagsAction) : null,
        ]);
        return {
            success: true,
            policy: policyData?.policy || null,
            flags: Array.isArray(flagsData?.flags) ? flagsData.flags : [],
            policy_result: policyData,
            flags_result: flagsData,
        };
    }

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
    const payloads = data.section_payloads || {};
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

    const sectionNames = Object.keys(sections);
    if (!state.sessionStateSelectedSection || !sections[state.sessionStateSelectedSection]) {
        state.sessionStateSelectedSection = sectionNames.find((name) => _ssPayloadHasData(payloads[name]?.data)) || sectionNames[0] || null;
    }

    const hot = [], warm = [];
    for (const [name, info] of Object.entries(sections)) {
        const d = details[name] || {};
        const sz = d.current_size_bytes ?? info.size_bytes;
        const cap = d.budget_bytes ?? info.budget_bytes;
        const pct = cap > 0 ? (sz / cap) * 100 : 0;
        const selected = state.sessionStateSelectedSection === name;
        const payloadSummary = _ssPayloadSummary(payloads[name]?.data);
        const row = `
            <button class="ss-section-row${selected ? " ss-section-row--active" : ""}" data-ss-section="${escapeHtml(name)}" type="button">
                <span class="ss-section-main">
                    <span class="ss-section-name">${escapeHtml(name.replace(/_/g, " "))}</span>
                    <span class="ss-section-subtitle">${escapeHtml(payloadSummary)}</span>
                </span>
                <span class="ss-section-detail">${(sz / 1024).toFixed(2)} / ${(cap / 1024).toFixed(0)} KB · ${pct.toFixed(0)}%</span>
            </button>`;
        (info.tier === "hot" ? hot : warm).push(row);
    }
    dom.ssHotSections.innerHTML = hot.join("") || `<p class="muted-empty">Empty.</p>`;
    dom.ssWarmSections.innerHTML = warm.join("") || `<p class="muted-empty">Empty.</p>`;
    document.querySelectorAll("[data-ss-section]").forEach((button) => {
        button.addEventListener("click", () => {
            state.sessionStateSelectedSection = button.dataset.ssSection;
            renderSessionState(data);
        });
    });
    renderSessionInspector(data, state.sessionStateSelectedSection);
    dom.ssColdInfo.innerHTML = `SQLite archive: <strong>${data.local_cold_count || 0}</strong> items (K1 edge storage)`;
}

function renderSessionInspector(data, sectionName) {
    if (!dom.ssInspector) return;
    const sections = data.sections || {};
    const details = data.section_details || {};
    const payload = (data.section_payloads || {})[sectionName] || {};
    const info = sections[sectionName] || {};
    const detail = details[sectionName] || {};
    const sectionTitle = sectionName ? sectionName.replace(/_/g, " ") : "No section selected";
    const size = detail.current_size_bytes ?? info.size_bytes ?? 0;
    const budget = detail.budget_bytes ?? info.budget_bytes ?? 0;
    const pct = budget > 0 ? (size / budget) * 100 : 0;
    const dataValue = payload.data;
    const stats = _ssInspectorStats(dataValue);

    dom.ssInspector.innerHTML = `
        <div class="ss-inspector-head">
            <div>
                <p class="ss-inspector-kicker">${escapeHtml(String(info.tier || "section").toUpperCase())} section</p>
                <h3>${escapeHtml(_humanizeLabel(sectionTitle))}</h3>
            </div>
            <div class="ss-inspector-meta">
                <span>${(size / 1024).toFixed(2)} KB</span>
                <span>${pct.toFixed(0)}%</span>
                <span>${escapeHtml(payload.serializer || "snapshot")}</span>
            </div>
        </div>
        <div class="ss-inspector-chips">
            ${stats.map((stat) => `<span>${escapeHtml(stat)}</span>`).join("")}
        </div>
        ${payload.error ? `<div class="view-error">${escapeHtml(payload.error)}</div>` : ""}
        <pre class="ss-data-viewer">${escapeHtml(_ssStringifyData(dataValue))}</pre>`;
}

function _ssPayloadHasData(value) {
    if (value == null) return false;
    if (Array.isArray(value)) return value.length > 0;
    if (typeof value === "object") return Object.keys(value).some((key) => _ssPayloadHasData(value[key]));
    if (typeof value === "string") return value.length > 0;
    return true;
}

function _ssPayloadSummary(value) {
    if (value == null) return "No stored data";
    if (Array.isArray(value)) return `${value.length} items`;
    if (typeof value === "object") {
        const keys = Object.keys(value);
        const counts = keys
            .map((key) => Array.isArray(value[key]) ? `${value[key].length} ${key}` : null)
            .filter(Boolean)
            .slice(0, 2);
        return counts.length ? counts.join(" · ") : `${keys.length} fields`;
    }
    return String(value).slice(0, 60);
}

function _ssInspectorStats(value) {
    if (value == null) return ["empty"];
    if (Array.isArray(value)) return [`${value.length} items`];
    if (typeof value === "object") {
        const keys = Object.keys(value);
        const chips = [`${keys.length} fields`];
        keys.forEach((key) => {
            if (Array.isArray(value[key])) chips.push(`${value[key].length} ${key}`);
            else if (value[key] && typeof value[key] === "object") chips.push(`${Object.keys(value[key]).length} ${key}`);
        });
        return chips.slice(0, 6);
    }
    return [typeof value];
}

function _ssStringifyData(value) {
    if (value == null) return "No stored data in this section yet.";
    try {
        return JSON.stringify(value, null, 2);
    } catch {
        return String(value);
    }
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
