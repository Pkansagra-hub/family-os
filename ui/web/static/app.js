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
    backReasoningBuffer: "",
    thinkingActive: false,
    streamingLabel: "",
    _thinkingStartMs: null,
    _chatWelcomeHideTimer: null,
    activityItems: [],
    activityByKey: new Map(),
    activitySeq: 0,
    activityRailExpanded: false,
    timelineEntries: [],
    lastActivity: null,
    currentAffect: { emotion: "neutral", valence: 0.5 },
    fsmState: "INITIALIZING",
    currentView: "home",
    memberDropdownOpen: false,
    tasksSelectedListId: null,
    tasksSelectedTaskKey: null,
    tasksViewMode: "list",
    tasksFilter: "now",
    tasksSearchQuery: "",
    shoppingSelectedListId: null,
    shoppingSelectedItemKey: null,
    shoppingViewMode: "list",
    shoppingFilter: "needed",
    shoppingSearchQuery: "",
    remindersSelectedRecipient: null,
    remindersSelectedKey: null,
    remindersViewMode: "timeline",
    remindersFilter: "active",
    remindersSearchQuery: "",
    choresSelectedAssignee: "__all__",
    choresSelectedKey: null,
    choresViewMode: "today",
    choresFilter: "pending",
    choresSearchQuery: "",
    settingsViewMode: "overview",
    settingsSearchQuery: "",
    settingsAdvancedOpen: false,
    sessionStateSelectedSection: null,
    browserLocationFix: null,
    browserLocationPermission: "unknown",
    browserLocationStatus: "idle",
    browserLocationError: null,
    browserLocationRequested: false,
    browserLocationPromise: null,
    browserLocationLastAttemptMs: 0,
};

const DEFAULT_STREAMING_LABEL = "Understanding request...";
const BROWSER_LOCATION_TARGET_ACCURACY_M = 1;
const BROWSER_LOCATION_WATCH_TIMEOUT_MS = 12000;
const BROWSER_LOCATION_REFRESH_INTERVAL_MS = 60000;
const BROWSER_LOCATION_POSITION_OPTIONS = Object.freeze({
    enableHighAccuracy: true,
    timeout: BROWSER_LOCATION_WATCH_TIMEOUT_MS,
    maximumAge: 0,
});

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
    "Riley":    { color: "#0d9488", initials: "R", role: "Child",       key: "riley"  },
    "Nana Liz": { color: "#14b8a6", initials: "N", role: "Grandparent", key: "nana"   },
};

const AFFECT_MAP = {
    calm:       { emoji: "😌", color: "#3b82f6" },
    warm:       { emoji: "😊", color: "#ec4899" },
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
    chatArea:       $("#chat-area"),
    messages:       $("#messages"),
    chatWelcome:    $("#chat-welcome"),
    chatSystemDetails: $(".chat-system-details"),
    chatMemberLine: $("#chat-member-line"),
    chatWelcomeTitle: $("#chat-welcome-title"),
    chatWelcomeNote:  $("#chat-welcome-note"),
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
    activityRail:   $("#activity-rail"),
    activityToggle: $("#activity-rail-toggle"),
    activityClose:  $("#activity-rail-close"),
    activityList:   $("#activity-rail-list"),
    activityEmpty:  $("#activity-rail-empty"),
    activityStatus: $("#activity-rail-status"),

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
    homeTodayTitle:   $("#home-today-title"),
    homeTodayDetail:  $("#home-today-detail"),
    homeTodayMeta:    $("#home-today-meta"),
    homeStatusSummary: $("#home-status-summary"),
    homeSignalTasks:  $("#home-signal-tasks"),
    homeSignalEvents: $("#home-signal-events"),
    homeSignalNudges: $("#home-signal-nudges"),

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
    setupProgressiveDisclosure();
    setupActivityRail();
    renderActivityRail();
    setChatWelcomeVisible();
    connect();
}

document.addEventListener("DOMContentLoaded", init);

function setupActivityRail() {
    if (!dom.activityRail || !dom.activityToggle) return;
    const saved = window.localStorage?.getItem("familyos.activityRailExpanded");
    setActivityRailExpanded(saved === "true" && hasRunningActivity(), { persist: false });

    dom.activityToggle.addEventListener("click", () => {
        setActivityRailExpanded(!state.activityRailExpanded);
    });
    dom.activityClose?.addEventListener("click", () => {
        setActivityRailExpanded(false);
        dom.activityToggle?.focus();
    });
    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && state.activityRailExpanded) {
            setActivityRailExpanded(false);
        }
    });
}

function setActivityRailExpanded(expanded, options = {}) {
    state.activityRailExpanded = Boolean(expanded);
    dom.activityRail?.classList.toggle("activity-rail--expanded", state.activityRailExpanded);
    dom.activityRail?.classList.toggle("activity-rail--collapsed", !state.activityRailExpanded);
    dom.activityToggle?.setAttribute("aria-expanded", state.activityRailExpanded ? "true" : "false");
    if (options.persist !== false) {
        window.localStorage?.setItem("familyos.activityRailExpanded", state.activityRailExpanded ? "true" : "false");
    }
}

function hasRunningActivity() {
    return state.activityItems.some((item) => item.status === "running");
}

function setupProgressiveDisclosure() {
    document.addEventListener("click", (event) => {
        const drawerOpen = event.target.closest("[data-app-drawer-open]");
        if (drawerOpen) {
            event.preventDefault();
            openAppDetailDrawer(drawerOpen.dataset.appDrawerOpen);
            return;
        }

        const drawerClose = event.target.closest("[data-app-drawer-close], .app-detail-drawer__close, .app-detail-drawer-backdrop");
        if (drawerClose) {
            event.preventDefault();
            const target = drawerClose.dataset.appDrawerClose || drawerClose.dataset.appDrawerBackdrop || null;
            if (target) closeAppDetailDrawer(resolveAppDisclosureTarget(target, ".app-detail-drawer"));
            else closeAppDetailDrawer(drawerClose.closest(".app-detail-drawer"));
            return;
        }

        const filterToggle = event.target.closest("[data-app-filter-toggle]");
        if (filterToggle) {
            event.preventDefault();
            toggleAppFilterRow(filterToggle);
        }
    });

    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") closeAllAppDetailDrawers();
    });
}

function resolveAppDisclosureTarget(targetRef, fallbackSelector) {
    if (!targetRef) return null;
    if (targetRef instanceof Element) return targetRef;
    const ref = String(targetRef).trim();
    if (!ref) return null;
    if (ref.startsWith("#") || ref.startsWith(".")) {
        try { return document.querySelector(ref); } catch { return null; }
    }
    return document.getElementById(ref)
        || $$(fallbackSelector).find((node) => node.dataset.appDrawer === ref || node.dataset.appDisclosure === ref)
        || null;
}

function openAppDetailDrawer(targetRef) {
    const drawer = resolveAppDisclosureTarget(targetRef, ".app-detail-drawer");
    if (!drawer) return;
    drawer.classList.add("app-detail-drawer--open");
    drawer.setAttribute("aria-hidden", "false");
    const key = drawer.id || drawer.dataset.appDrawer || drawer.dataset.appDisclosure || String(targetRef || "");
    toggleAppDrawerBackdrops(key, true);
    const focusTarget = drawer.querySelector("[data-autofocus], button, [href], input, select, textarea, [tabindex]:not([tabindex='-1'])");
    focusTarget?.focus?.({ preventScroll: true });
}

function closeAppDetailDrawer(drawer) {
    if (!drawer) return;
    drawer.classList.remove("app-detail-drawer--open");
    drawer.setAttribute("aria-hidden", "true");
    const key = drawer.id || drawer.dataset.appDrawer || drawer.dataset.appDisclosure || "";
    toggleAppDrawerBackdrops(key, false);
}

function closeAllAppDetailDrawers() {
    $$(".app-detail-drawer--open, .app-detail-drawer[aria-hidden='false']").forEach(closeAppDetailDrawer);
}

function toggleAppDrawerBackdrops(key, open) {
    if (!key) return;
    $$(`[data-app-drawer-backdrop]`).forEach((backdrop) => {
        if (backdrop.dataset.appDrawerBackdrop !== key) return;
        backdrop.classList.toggle("app-detail-drawer-backdrop--open", open);
        backdrop.setAttribute("aria-hidden", open ? "false" : "true");
    });
}

function toggleAppFilterRow(button) {
    const target = resolveAppDisclosureTarget(button.dataset.appFilterToggle, ".app-filter-row")
        || button.closest(".app-filter-shell")?.querySelector(".app-filter-row");
    if (!target) return;
    const expanded = target.classList.toggle("app-filter-row--expanded");
    target.classList.toggle("app-filter-row--collapsed", !expanded);
    target.setAttribute("aria-expanded", expanded ? "true" : "false");
    button.setAttribute("aria-expanded", expanded ? "true" : "false");
}

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
    else if (viewId === "chat") {
        dom.input && dom.input.focus();
        if (!hasRunningActivity()) setActivityRailExpanded(false, { persist: false });
    }
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

    const todayIso = _localDateIso();
    const endIso = (() => {
        const d = new Date();
        d.setDate(d.getDate() + 14);
        return _localDateIso(d);
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

    const activeTasks = tasks.filter(_taskIsActive);
    const dueTasks = activeTasks.filter((task) => _taskIsOverdue(task) || _taskIsDueToday(task));
    const eventsToday = events.filter((event) => _calEventOverlapsDate(event, todayIso));
    const activeReminders = reminders.filter(_reminderIsActive);
    const remindersToNotice = activeReminders.filter((reminder) => _reminderNeedsAttention(reminder) || _reminderIsOverdue(reminder) || _reminderIsDueToday(reminder));
    const pendingChores = chores.filter((chore) => _choreStatus(chore) === "pending");
    const choresDueNow = pendingChores.filter(_choreIsDueNow);
    const shoppingNeeded = shoppingItems.filter(_shoppingIsNeeded);
    const nudgeCount = remindersToNotice.length + choresDueNow.length;

    dom.statTasks     && (dom.statTasks.textContent     = taskData     ? activeTasks.length       : "—");
    dom.statEvents    && (dom.statEvents.textContent    = eventData    ? events.length            : "—");
    dom.statReminders && (dom.statReminders.textContent = reminderData ? activeReminders.length  : "—");
    dom.statChores    && (dom.statChores.textContent    = choreData    ? pendingChores.length    : "—");
    dom.homeSignalTasks  && (dom.homeSignalTasks.textContent  = taskData ? dueTasks.length : "—");
    dom.homeSignalEvents && (dom.homeSignalEvents.textContent = eventData ? eventsToday.length : "—");
    dom.homeSignalNudges && (dom.homeSignalNudges.textContent = (reminderData || choreData) ? nudgeCount : "—");
    _renderHomeTodayGlance({
        activeTasks,
        dueTasks,
        events,
        eventsToday,
        activeReminders,
        remindersToNotice,
        pendingChores,
        choresDueNow,
        shoppingNeeded,
        loaded: { taskData, eventData, reminderData, choreData, shoppingItemData },
    });

    if (dom.homeActivity) {
        _renderHomeActivity(_buildHomeActivityFeed({ tasks, events, reminders, chores, shoppingLists, shoppingItems }).slice(0, 1));
    }
}

function _renderHomeTodayGlance(metrics) {
    const {
        activeTasks,
        dueTasks,
        events,
        eventsToday,
        activeReminders,
        remindersToNotice,
        pendingChores,
        choresDueNow,
        shoppingNeeded,
        loaded,
    } = metrics;
    const attentionCount = dueTasks.length + remindersToNotice.length + choresDueNow.length;
    const todayCount = attentionCount + eventsToday.length;
    const hasLoadedCore = loaded.taskData || loaded.eventData || loaded.reminderData || loaded.choreData;
    const title = !hasLoadedCore
        ? "Family status is unavailable"
        : attentionCount > 0
            ? `${attentionCount} ${attentionCount === 1 ? "thing needs" : "things need"} attention`
            : todayCount > 0
                ? `${todayCount} ${todayCount === 1 ? "thing is" : "things are"} in motion today`
                : "Today looks open";
    const detailParts = [
        eventsToday.length ? _countPhrase(eventsToday.length, "calendar event") : "",
        dueTasks.length ? _countPhrase(dueTasks.length, "due task") : "",
        remindersToNotice.length ? _countPhrase(remindersToNotice.length, "reminder") : "",
        choresDueNow.length ? _countPhrase(choresDueNow.length, "chore") : "",
    ].filter(Boolean);
    const detail = !hasLoadedCore
        ? "Open the apps for full detail."
        : detailParts.length
            ? `${detailParts.join(", ")} need the first look.`
            : "No due tasks, reminders, or chores are calling for attention.";
    const meta = [
        _countPhrase(activeTasks.length, "open task"),
        _countPhrase(events.length, "event", "events"),
        _countPhrase(activeReminders.length, "active reminder"),
        _countPhrase(pendingChores.length, "pending chore"),
    ].join(" · ");
    const status = [
        _countPhrase(activeTasks.length, "task"),
        _countPhrase(events.length, "calendar item"),
        _countPhrase(activeReminders.length, "reminder"),
        _countPhrase(pendingChores.length, "chore"),
        shoppingNeeded.length ? _countPhrase(shoppingNeeded.length, "shopping item") : "",
    ].filter(Boolean).join(" · ");

    if (dom.homeTodayTitle) dom.homeTodayTitle.textContent = title;
    if (dom.homeTodayDetail) dom.homeTodayDetail.textContent = detail;
    if (dom.homeTodayMeta) dom.homeTodayMeta.textContent = meta;
    if (dom.homeStatusSummary) dom.homeStatusSummary.textContent = status || "Full stats when needed";
}

function _countPhrase(count, singular, plural = `${singular}s`) {
    return `${count} ${count === 1 ? singular : plural}`;
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
    const kind = trigger.kind || (trigger.fire_at ? "time" : "");
    if (kind === "time" && trigger.fire_at) return _relativeDate(trigger.fire_at);
    if (kind === "location_enter" || kind === "location_leave") {
        const place = trigger.location?.name || trigger.location?.label || "location";
        return `${kind === "location_enter" ? "Arrive at" : "Leave"} ${place}`;
    }
    if (kind === "event_offset") {
        const offset = Number(trigger.offset_minutes || 0);
        if (offset === 0) return "At event time";
        return `${Math.abs(offset)}m ${offset < 0 ? "before" : "after"} event`;
    }
    if (kind) return _humanizeLabel(kind);
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
        case "hil_presented":   handleHilPresented(msg); break;
        case "task_failed":     handleTaskFailed(msg); break;
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
    _sendDeviceContext();
    _ensureBrowserLocation().then(_sendDeviceContext).catch(_sendDeviceContext);
    if (dom.turnBadge) dom.turnBadge.textContent = `Turn ${state.turn}`;
    if (state.currentView === "home") loadHomeDashboard();
}

function handleResponse(msg) {
    const affect = msg.affect || "calm";
    const reasoning = getCurrentReasoningSnapshot();

    if (state.streamingMsgId) {
        const el = document.getElementById(state.streamingMsgId);
        if (el) {
            el.classList.remove("message-thinking", "message-working");
            const bubble = el.querySelector(".message-bubble");
            if (bubble) {
                bubble.classList.remove("message-bubble--work");
                bubble.innerHTML = renderAssistantBubbleContent(msg.text, { final: true, reasoning });
            }
        }
        state.streamingMsgId = null;
        state.streamBuffer = "";
        state.thinkingBuffer = "";
        state.backReasoningBuffer = "";
        state.thinkingActive = false;
        state.streamingLabel = "";
        state._thinkingStartMs = null;
        showStreaming(false);
        updateAffect(affect, state.currentAffect.valence);
        scrollChatToBottom();
    } else {
        finishStreaming();
        addAssistantMessage(msg.text, { reasoning });
        updateAffect(affect, state.currentAffect.valence);
    }
}

function handleStreamChunk(msg) {
    if (msg.chunk_type === "back_reasoning") {
        handleActivityReasoningChunk(msg);
        return;
    }

    ensureStreamingMessage();
    const el = document.getElementById(state.streamingMsgId);
    if (!el) return;

    if (msg.chunk_type === "thinking") {
        state.thinkingActive = true;
        state.thinkingBuffer += (msg.text || "");
        updateStreamingWorkCard(state.streamingLabel || DEFAULT_STREAMING_LABEL);
        el.classList.add("message-thinking", "message-working");
        showStreaming(true, DEFAULT_STREAMING_LABEL);
        return;
    }

    if (msg.chunk_type === "text") {
        state.streamBuffer += (msg.text || "");
        el.classList.remove("message-thinking", "message-working");
        const bubble = el.querySelector(".message-bubble");
        if (bubble) {
            bubble.classList.remove("message-bubble--work");
            bubble.innerHTML = renderAssistantBubbleContent(state.streamBuffer, {
                final: false,
                reasoning: getCurrentReasoningSnapshot(),
            });
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
        state.backReasoningBuffer = "";
        state.thinkingActive = false;
        state.streamingLabel = "";
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

function handleTaskFailed(msg) {
    markActivityFailed(msg);
    // Back failed (e.g. exceeded iteration budget without submit_result, or
    // dispatcher rejected the final tool call). Front may never publish a
    // response.final, so we clear the spinner ourselves and surface a brief
    // fallback so the user knows the turn is over.
    finishStreaming(true);
    const reason = (msg && msg.reason) ? String(msg.reason) : "error";
    const detail = (msg && msg.error_message) ? String(msg.error_message) : "";
    let text = "Hmm, I couldn't finish that one. Want to try again?";
    if (reason === "missing_submit_result") {
        text = "I ran out of room to finish that. Want me to try again with a shorter ask?";
    } else if (reason === "timeout") {
        text = "That took too long. Try again or rephrase?";
    } else if (detail) {
        text = `I hit a snag: ${detail}. Want to try again?`;
    }
    addSystemMessage(text);
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

// GAP-HIL-009 -- mark the chat input as the active HIL answer channel
// when a presentation ack arrives. Front publishes TOPIC_HIL_PRESENTED
// once it has rendered the question text to chat (or, in widget paths,
// once the widget is on screen). The data-hil-active attribute lets
// styling / submit logic know the next user message should be treated
// as a reply to the open HIL request rather than a new turn.
function handleHilPresented(msg) {
    const input = document.getElementById("chatInput");
    if (!input) return;
    const requestId = msg.hil_request_id || "";
    if (!requestId) return;
    input.setAttribute("data-hil-active", "true");
    input.setAttribute("data-hil-request-id", requestId);
    if (msg.kind) input.setAttribute("data-hil-kind", msg.kind);
    if (msg.task_id) input.setAttribute("data-hil-task-id", msg.task_id);
    console.info(
        "hil_presented: chat input armed for request_id=" + requestId.slice(0, 8) +
        " kind=" + (msg.kind || "")
    );
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
        <div class="message-avatar" style="background:var(--color-rose,#e11d48);color:#fff">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
        </div>
        <div class="message-bubble" style="border:1.5px solid var(--color-rose,#e11d48);background:var(--surface-elevated,#fff);padding:12px 14px;">
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
        <div style="border:2px solid var(--color-rose,#e11d48);background:var(--surface-elevated,#fff);border-radius:16px;padding:14px 16px;box-shadow:0 18px 40px rgba(15,23,42,0.22);">
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
    _sendDeviceContext();
    _ensureBrowserLocation({ force: true }).then(_sendDeviceContext).catch(_sendDeviceContext);
}

const EXTERNAL_TOOLS = new Set([
    "invoke_capability",
    "batch_invoke_capabilities",
    "spawn_via_fabric",
    "execute_workflow",
]);

const ACTIVITY_SOURCE_META = {
    back: { label: "Background", title: "Background reasoning", tone: "blue" },
    front: { label: "Reply", title: "Response planning", tone: "blue" },
    planner: { label: "Planner", title: "Planner", tone: "purple" },
    orchestrator: { label: "Orchestrator", title: "Orchestrator", tone: "green" },
    fabric: { label: "Fabric", title: "Fabric", tone: "purple" },
    agent: { label: "Helper", title: "Helper agent", tone: "teal" },
    tool: { label: "Tool", title: "Tool invocation", tone: "gray" },
    kernel: { label: "System", title: "System work", tone: "gray" },
};

function normalizeActivitySource(source) {
    const raw = String(source || "kernel").toLowerCase();
    if (raw.includes("planner")) return "planner";
    if (raw.includes("orchestrator")) return "orchestrator";
    if (raw.includes("fabric")) return "fabric";
    if (raw.includes("agent")) return "agent";
    if (raw.includes("front")) return "front";
    if (raw.includes("back")) return "back";
    if (raw.includes("tool")) return "tool";
    return "kernel";
}

function activityMeta(source) {
    return ACTIVITY_SOURCE_META[normalizeActivitySource(source)] || ACTIVITY_SOURCE_META.kernel;
}

function getOrCreateActivityItem(key, seed = {}) {
    const existing = state.activityByKey.get(key);
    const now = Date.now();
    if (existing) {
        Object.assign(existing, seed, { updatedAt: now });
        return existing;
    }

    const source = normalizeActivitySource(seed.source || "kernel");
    const meta = activityMeta(source);
    const item = {
        id: `activity-${++state.activitySeq}`,
        key,
        source,
        title: seed.title || meta.title,
        status: seed.status || "running",
        phase: seed.phase || "Starting",
        reasoning: seed.reasoning || "",
        events: seed.events || [],
        startedAt: now,
        updatedAt: now,
    };
    state.activityByKey.set(key, item);
    state.activityItems.unshift(item);
    if (state.activityItems.length > 10) {
        const removed = state.activityItems.pop();
        if (removed) state.activityByKey.delete(removed.key);
    }
    return item;
}

function activeActivityForSource(source) {
    const normalized = normalizeActivitySource(source);
    return state.activityItems.find((item) => item.source === normalized && item.status === "running") || null;
}

function handleActivityReasoningChunk(msg) {
    state.backReasoningBuffer += msg.text || "";
    const key = msg.trace_id ? `back:${msg.trace_id}` : `back:turn:${state.turn || "active"}`;
    const item = getOrCreateActivityItem(key, {
        source: "back",
        title: "Background reasoning",
        status: "running",
        phase: "Reasoning",
    });
    item.reasoning += msg.text || "";
    item.updatedAt = Date.now();
    if (!item.events.some((event) => event.kind === "reasoning")) {
        item.events.push({
            kind: "reasoning",
            label: "Reasoning stream opened",
            status: "running",
            at: item.updatedAt,
        });
    }
    renderActivityRail();
    updateStreamingWorkCard(state.streamingLabel || "Checking tools...");
}

function updateActivityForToolEvent(msg) {
    const actor = normalizeActivitySource(msg.actor || "tool");
    const toolName = msg.tool_name || "tool";
    if (actor === "kernel" && !EXTERNAL_TOOLS.has(toolName)) return;
    if (actor === "front" && !EXTERNAL_TOOLS.has(toolName)) return;

    const item = activeActivityForSource(actor) || getOrCreateActivityItem(`${actor}:${state.turn || "active"}`, {
        source: actor,
        title: activityMeta(actor).title,
        status: "running",
        phase: "Tool activity",
    });
    const failed = msg.success === false || msg.phase === "failed";
    const completed = msg.phase === "completed" || failed;
    item.status = failed ? "failed" : item.status;
    item.phase = failed
        ? `${toolName} failed`
        : completed
            ? `${toolName} completed`
            : `${toolName} running`;
    if (completed && actor === "back" && toolName === "submit_result" && !failed) {
        item.status = "done";
        item.phase = "Result submitted";
    }
    item.events.push({
        kind: "tool",
        label: toolName,
        status: failed ? "failed" : msg.phase || "started",
        detail: msg.result_summary || msg.args_summary || "",
        at: Date.now(),
    });
    item.updatedAt = Date.now();
    renderActivityRail();
    updateStreamingWorkCard(state.streamingLabel || "Checking tools...");
}

function markActivityFailed(msg) {
    const item = activeActivityForSource("back");
    if (!item) return;
    item.status = "failed";
    item.phase = msg.reason || "Failed";
    item.events.push({
        kind: "error",
        label: "Task failed",
        status: "failed",
        detail: msg.error_message || msg.reason || "",
        at: Date.now(),
    });
    item.updatedAt = Date.now();
    renderActivityRail();
}

function renderActivityRail() {
    if (!dom.activityList || !dom.activityEmpty || !dom.activityStatus) return;
    const items = state.activityItems.slice().sort((a, b) => {
        const ar = a.status === "running" ? 1 : 0;
        const br = b.status === "running" ? 1 : 0;
        if (ar !== br) return br - ar;
        return b.updatedAt - a.updatedAt;
    });
    const activeCount = items.filter((item) => item.status === "running").length;
    dom.activityStatus.textContent = activeCount ? `${activeCount} active` : "Idle";
    dom.activityRail?.classList.toggle("activity-rail--has-active", activeCount > 0);
    dom.activityEmpty.classList.toggle("hidden", items.length > 0);
    dom.activityList.innerHTML = items.map(renderActivityCard).join("");
    updateChatSystemDisclosureState();
}

function renderActivityCard(item) {
    const meta = activityMeta(item.source);
    const status = item.status || "running";
    const reasoning = String(item.reasoning || "").trim();
    const events = item.events.slice(-5).map(renderActivityEvent).join("");
    const reasoningBlock = reasoning
        ? `<details class="activity-reasoning"${status === "running" ? " open" : ""}>
                <summary>Reasoning trace</summary>
                <div class="activity-reasoning__body">${escapeHtml(item.reasoning)}</div>
            </details>`
        : "";
    return `
        <article class="activity-card activity-card--${escapeHtml(status)} activity-card--${escapeHtml(meta.tone)}">
            <div class="activity-card__top">
                <span class="activity-card__dot" aria-hidden="true"></span>
                <div class="activity-card__headings">
                    <div class="activity-card__title">${escapeHtml(item.title)}</div>
                    <div class="activity-card__phase">${escapeHtml(item.phase)}</div>
                </div>
                <span class="activity-card__source">${escapeHtml(meta.label)}</span>
            </div>
            ${events ? `<div class="activity-card__events">${events}</div>` : ""}
            ${reasoningBlock}
            <div class="activity-card__meta">Updated ${escapeHtml(formatActivityAge(item.updatedAt))}</div>
        </article>`;
}

function renderActivityEvent(event) {
    const status = event.status || "started";
    const detail = event.detail ? `<span class="activity-event__detail">${escapeHtml(event.detail)}</span>` : "";
    return `
        <div class="activity-event activity-event--${escapeHtml(status)}">
            <span class="activity-event__status">${escapeHtml(status)}</span>
            <span class="activity-event__label">${escapeHtml(event.label)}</span>
            ${detail}
        </div>`;
}

function formatActivityAge(updatedAt) {
    const seconds = Math.max(0, Math.round((Date.now() - updatedAt) / 1000));
    if (seconds < 3) return "now";
    if (seconds < 60) return `${seconds}s ago`;
    return `${Math.round(seconds / 60)}m ago`;
}

function handleToolEvent(msg) {
    updateActivityForToolEvent(msg);
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
        const body = opts.reasoning
            ? renderAssistantBubbleContent(text, {
                final: true,
                includeMeta: false,
                reasoning: opts.reasoning,
            })
            : formatMessageText(text);
        row.innerHTML = `
            <div class="message-avatar message-avatar--concierge">C</div>
            <div class="message-bubble">
                ${body}
                <div class="message-meta">Concierge${labelTag} · ${formatTime()}</div>
            </div>`;
    }

    dom.messages.appendChild(row);
    setChatWelcomeVisible();
    scrollChatToBottom();
    return id;
}

function addUserMessage(text)        { return addMessageRow("user", state.member, text); }
function addAssistantMessage(text, o){ return addMessageRow("assistant", "Concierge", text, o); }
function addSystemMessage(text)      { return addMessageRow("system", "System", text); }

function createStreamingMessage(id) {
    const row = document.createElement("div");
    row.className = "message-row message-row--assistant message-thinking message-working";
    row.id = id;
    row.innerHTML = `
        <div class="message-avatar message-avatar--concierge">C</div>
        <div class="message-bubble message-bubble--work">${renderConciergeWorkCard(DEFAULT_STREAMING_LABEL)}</div>`;
    dom.messages.appendChild(row);
    setChatWelcomeVisible();
    scrollChatToBottom();
}

function ensureStreamingMessage() {
    if (state.streamingMsgId) return;
    state.streamingMsgId = "stream-" + Date.now();
    state.streamBuffer = "";
    state.thinkingBuffer = "";
    state.backReasoningBuffer = "";
    state.thinkingActive = false;
    state.streamingLabel = DEFAULT_STREAMING_LABEL;
    state._thinkingStartMs = Date.now();
    createStreamingMessage(state.streamingMsgId);
}

function updateStreamingWorkCard(label = DEFAULT_STREAMING_LABEL) {
    if (!state.streamingMsgId || String(state.streamBuffer || "").trim()) return;
    const el = document.getElementById(state.streamingMsgId);
    if (!el) return;
    const bubble = el.querySelector(".message-bubble");
    if (!bubble) return;
    el.classList.add("message-working", "message-thinking");
    bubble.classList.add("message-bubble--work");
    bubble.innerHTML = renderConciergeWorkCard(label, { reasoning: getCurrentReasoningSnapshot() });
    scrollChatToBottom();
}

function renderConciergeWorkCard(label = DEFAULT_STREAMING_LABEL, opts = {}) {
    const phase = _conciergeWorkPhase(label);
    const chips = _conciergeWorkChips(label);
    const trace = renderConciergeWorkTrace(opts.reasoning || getCurrentReasoningSnapshot());
    return `
        <section class="concierge-work-card" role="status" aria-live="polite">
            <div class="concierge-work-head">
                <span class="concierge-work-orb" aria-hidden="true"><span></span></span>
                <div class="concierge-work-title">
                    <strong>I'm on it</strong>
                    <span>${escapeHtml(phase.detail)}</span>
                </div>
                <span class="concierge-work-live">Working</span>
            </div>
            <div class="concierge-work-rail" aria-hidden="true"><span></span></div>
            <div class="concierge-work-phase">
                <span class="concierge-work-phase-label">Now</span>
                <strong>${escapeHtml(phase.title)}</strong>
            </div>
            <div class="concierge-work-steps" aria-label="Work progress">
                <span class="concierge-work-step concierge-work-step--done">Listen</span>
                <span class="concierge-work-step concierge-work-step--active">Check</span>
                <span class="concierge-work-step">Reply</span>
            </div>
            ${chips.length ? `<div class="concierge-work-chips">${chips.map((chip) => `<span class="concierge-work-chip concierge-work-chip--${escapeHtml(chip.tone)}">${escapeHtml(chip.label)}</span>`).join("")}</div>` : ""}
            ${trace}
        </section>`;
}

function renderConciergeWorkTrace(snapshot = {}) {
    const frontText = String(snapshot.front || "").trim();
    const backText = String(snapshot.back || "").trim();
    if (!frontText && !backText) return "";
    const sections = [];
    if (frontText) {
        sections.push(`<section><strong>Reply</strong><pre>${escapeHtml(snapshot.front || "")}</pre></section>`);
    }
    if (backText) {
        sections.push(`<section><strong>Background</strong><pre>${escapeHtml(snapshot.back || "")}</pre></section>`);
    }
    return `
        <details class="concierge-work-trace">
            <summary><span>Reasoning notes</span><span>${frontText && backText ? "Reply + context" : frontText ? "Reply" : "Context"}</span></summary>
            <div class="concierge-work-trace-body">${sections.join("")}</div>
        </details>`;
}

function _conciergeWorkPhase(label = DEFAULT_STREAMING_LABEL) {
    const raw = String(label || DEFAULT_STREAMING_LABEL).replace(/\.{3,}$/g, "").trim();
    const lower = raw.toLowerCase();
    if (lower.includes("draft") || lower.includes("reply")) {
        return { title: "Writing response", detail: raw || "Preparing answer" };
    }
    if (lower.includes("memory") || lower.includes("context") || lower.includes("summar")) {
        return { title: "Checking context", detail: raw };
    }
    if (lower.includes("clarif")) {
        return { title: "Clarifying intent", detail: raw };
    }
    if (lower.includes("task") || lower.includes("tool") || lower.includes("starting")) {
        return { title: "Coordinating tools", detail: raw };
    }
    if (state.thinkingActive || String(state.thinkingBuffer || "").trim()) {
        return { title: "Reasoning through it", detail: raw };
    }
    return { title: "Understanding request", detail: raw };
}

function _conciergeWorkChips(label = DEFAULT_STREAMING_LABEL) {
    const chips = new Map();
    const add = (labelText, tone = "brand") => chips.set(labelText, { label: labelText, tone });
    const lower = String(label || "").toLowerCase();
    add("Context", "system");
    if (lower.includes("memory") || lower.includes("context") || lower.includes("belief")) add("Memory", "purple");
    if (lower.includes("task") || lower.includes("tool") || lower.includes("dispatch")) add("Tools", "teal");
    if (lower.includes("reply") || lower.includes("draft")) add("Reply", "brand");
    state.activityItems
        .filter((item) => item.status === "running")
        .slice(0, 3)
        .forEach((item) => {
            const chip = _conciergeActivityChip(item.source);
            add(chip.label, chip.tone || "system");
        });
    return Array.from(chips.values()).slice(0, 4);
}

function _conciergeActivityChip(source) {
    const normalized = normalizeActivitySource(source);
    const map = {
        back: { label: "Background", tone: "blue" },
        front: { label: "Reply", tone: "brand" },
        planner: { label: "Planning", tone: "purple" },
        orchestrator: { label: "Coordinating", tone: "green" },
        fabric: { label: "Context", tone: "purple" },
        agent: { label: "Helper", tone: "teal" },
        tool: { label: "Tools", tone: "teal" },
        kernel: { label: "System", tone: "gray" },
    };
    return map[normalized] || map.kernel;
}

function renderReasoningTrace() {
    return renderReasoningTraceBlock({ final: false });
}

function renderAssistantBubbleContent(text, opts = {}) {
    const final = Boolean(opts.final);
    const includeMeta = opts.includeMeta !== false;
    const content = [];
    const reasoning = renderReasoningTraceBlock({ final, reasoning: opts.reasoning });

    const responseText = String(text || "").trim();
    if (responseText) {
        content.push(`<div class="message-response-text">${formatMessageText(text)}</div>`);
        if (!final && reasoning) content.push(reasoning);
    } else if (!reasoning) {
        content.push(`<em class="message-placeholder">Thinking...</em>`);
    } else {
        content.push(reasoning);
    }
    if (final && reasoning) content.push(reasoning);

    if (final && includeMeta) {
        content.push(`<div class="message-meta">${formatTime()}</div>`);
    }
    return content.join("");
}

function renderReasoningTraceBlock(opts = {}) {
    const final = Boolean(opts.final);
    const snapshot = opts.reasoning || getCurrentReasoningSnapshot();
    const frontRaw = String((snapshot && snapshot.front) || "");
    const backRaw = String((snapshot && snapshot.back) || "");
    const frontText = frontRaw.trim();
    const backText = backRaw.trim();
    if (!frontText && !backText) return "";

    const sources = [];
    const sections = [];
    if (frontText) {
        sources.push("Front");
        sections.push(`
            <section class="reasoning-trace__section">
                <div class="reasoning-trace__section-title">${final ? "Reply reasoning" : "Front reasoning"}</div>
                <div class="reasoning-trace__body">${escapeHtml(frontRaw)}</div>
            </section>`);
    }
    if (backText) {
        sources.push("Back");
        sections.push(`
            <section class="reasoning-trace__section">
                <div class="reasoning-trace__section-title">${final ? "Background reasoning" : "Back reasoning"}</div>
                <div class="reasoning-trace__body">${escapeHtml(backRaw)}</div>
            </section>`);
    }

    const openAttr = final ? "" : " open";
    const label = final ? "Behind the scenes" : "Working through it";
    const sourceLabel = final
        ? (frontText && backText ? "Reply + context" : frontText ? "Reply" : "Context")
        : sources.join(" + ");
    const statusClass = final ? " reasoning-trace--done" : " reasoning-trace--active";

    return `
        <details class="reasoning-trace${statusClass}"${openAttr}>
            <summary>
                <span class="reasoning-trace__chevron" aria-hidden="true"></span>
                <span class="reasoning-trace__label">${escapeHtml(label)}</span>
                <span class="reasoning-trace__source">${escapeHtml(sourceLabel)}</span>
            </summary>
            <div class="reasoning-trace__content">${sections.join("")}</div>
        </details>`;
}

function getCurrentReasoningSnapshot() {
    return {
        front: state.thinkingBuffer || "",
        back: state.backReasoningBuffer || "",
        startMs: state._thinkingStartMs,
    };
}

function _thinkingDuration(startMs) {
    if (!startMs) return "a moment";
    const sec = Math.round((Date.now() - startMs) / 1000);
    if (sec < 1) return "< 1s";
    return `${sec}s`;
}

function scrollChatToBottom() {
    if (!dom.messages) return;
    requestAnimationFrame(() => {
        const area = dom.messages.parentElement;
        if (area) area.scrollTop = area.scrollHeight;
    });
}

function setChatWelcomeVisible() {
    if (!dom.chatWelcome || !dom.messages) return;
    const hasConversation = dom.messages.children.length > 0 || Boolean(state.streamingMsgId);
    dom.chatArea?.classList.toggle("chat-area--has-conversation", hasConversation);
    updateChatSystemDisclosureState();

    if (hasConversation) {
        if (state._chatWelcomeHideTimer) window.clearTimeout(state._chatWelcomeHideTimer);
        dom.chatWelcome.classList.add("chat-welcome--leaving");
        dom.chatWelcome.setAttribute("aria-hidden", "true");
        state._chatWelcomeHideTimer = window.setTimeout(() => {
            dom.chatWelcome?.classList.add("hidden");
            state._chatWelcomeHideTimer = null;
        }, 220);
        return;
    }

    if (state._chatWelcomeHideTimer) {
        window.clearTimeout(state._chatWelcomeHideTimer);
        state._chatWelcomeHideTimer = null;
    }
    dom.chatWelcome.classList.remove("hidden");
    dom.chatWelcome.setAttribute("aria-hidden", "false");
    requestAnimationFrame(() => dom.chatWelcome?.classList.remove("chat-welcome--leaving"));
}

function updateChatSystemDisclosureState() {
    const active = Boolean(state.streamingMsgId) || hasRunningActivity();
    dom.chatSystemDetails?.classList.toggle("chat-system-details--active", active);
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
    if (dom.chatMemberLine) dom.chatMemberLine.textContent = `Here with ${state.member}`;
    if (dom.chatWelcomeTitle) dom.chatWelcomeTitle.textContent = `Hi, ${state.member}.`;
    if (dom.chatWelcomeNote) dom.chatWelcomeNote.textContent = "Tell me the outcome. I can help shape the plan, reminders, and next steps.";
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
    state.streamingLabel = visible ? (label || DEFAULT_STREAMING_LABEL) : "";
    if (dom.streaming) {
        dom.streaming.classList.add("hidden");
        dom.streaming.setAttribute("aria-hidden", "true");
    }
    if (dom.streamingText) dom.streamingText.textContent = state.streamingLabel || DEFAULT_STREAMING_LABEL;
    if (visible) updateStreamingWorkCard(state.streamingLabel);
    updateChatSystemDisclosureState();
}

// ============================================================================
// Input
// ============================================================================

function setupInput() {
    if (!dom.form) return;
    dom.form.addEventListener("submit", (e) => {
        e.preventDefault();
        sendMessage().catch((err) => console.error("sendMessage failed:", err));
    });
    dom.input.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            sendMessage().catch((err) => console.error("sendMessage failed:", err));
        }
    });
    $$("[data-chat-suggestion]").forEach((button) => {
        button.addEventListener("click", () => applyChatSuggestion(button.dataset.chatSuggestion || ""));
    });
}

function applyChatSuggestion(text) {
    if (!dom.input || !text) return;
    dom.input.value = text;
    dom.input.focus();
    $$(".chat-more-ideas[open]").forEach((details) => details.removeAttribute("open"));
}

async function sendMessage() {
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
    dom.input.value = "";
    // GAP-HIL-009 -- once the user has dispatched a reply, the chat
    // input is no longer the dedicated answer channel for the prior
    // HIL request. Clear the data-hil-* markers so a subsequent
    // unrelated user message isn't mis-tagged.
    if (dom.input.hasAttribute("data-hil-active")) {
        dom.input.removeAttribute("data-hil-active");
        dom.input.removeAttribute("data-hil-request-id");
        dom.input.removeAttribute("data-hil-kind");
        dom.input.removeAttribute("data-hil-task-id");
    }
    showStreaming(true, DEFAULT_STREAMING_LABEL);

    await _ensureBrowserLocation();

    send({
        type: "message",
        text,
        member: state.member,
        device: state.device,
        device_context: _browserDeviceContext(),
    });
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
    const options = { hour: "2-digit", minute: "2-digit" };
    const timeZone = _displayTimeZone();
    if (timeZone) options.timeZone = timeZone;
    try {
        return new Intl.DateTimeFormat([], options).format(new Date());
    } catch {
        return new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    }
}

function _familyTimeZone() {
    const tz = state.family && typeof state.family.timezone === "string" ? state.family.timezone.trim() : "";
    return tz || null;
}

function _familyLocation() {
    const loc = state.family && typeof state.family.location === "string" ? state.family.location.trim() : "";
    return loc || null;
}

function _semanticPlaceHint() {
    return _familyLocation();
}

function _browserTimeZone() {
    try {
        return Intl.DateTimeFormat().resolvedOptions().timeZone || null;
    } catch {
        return null;
    }
}

function _displayTimeZone() {
    return _familyTimeZone() || _browserTimeZone() || null;
}

function _localDateIso(date = new Date()) {
    const timeZone = _displayTimeZone();
    if (timeZone && typeof Intl !== "undefined") {
        try {
            const parts = new Intl.DateTimeFormat("en-US", {
                timeZone,
                year: "numeric",
                month: "2-digit",
                day: "2-digit",
            }).formatToParts(date).reduce((acc, part) => {
                acc[part.type] = part.value;
                return acc;
            }, {});
            if (parts.year && parts.month && parts.day) {
                return `${parts.year}-${parts.month}-${parts.day}`;
            }
        } catch {/* fall through */}
    }
    const y = date.getFullYear();
    const m = String(date.getMonth() + 1).padStart(2, "0");
    const d = String(date.getDate()).padStart(2, "0");
    return `${y}-${m}-${d}`;
}

function _timeZoneOffsetMs(date, timeZone) {
    const parts = new Intl.DateTimeFormat("en-US", {
        timeZone,
        hourCycle: "h23",
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
    }).formatToParts(date).reduce((acc, part) => {
        acc[part.type] = part.value;
        return acc;
    }, {});
    const wallTimeMs = Date.UTC(
        Number(parts.year),
        Number(parts.month) - 1,
        Number(parts.day),
        Number(parts.hour),
        Number(parts.minute),
        Number(parts.second),
    );
    return wallTimeMs - date.getTime();
}

function _zonedDateTimeToIso(dateIso, timeText) {
    const timeZone = _displayTimeZone();
    const [year, month, day] = String(dateIso || "").split("-").map(Number);
    const [hour, minute, second = 0] = String(timeText || "00:00:00").split(":").map(Number);
    if (![year, month, day, hour, minute, second].every(Number.isFinite)) {
        return new Date().toISOString();
    }
    const wallTimeMs = Date.UTC(year, month - 1, day, hour, minute, second, 0);
    if (!timeZone || typeof Intl === "undefined") {
        return new Date(`${dateIso}T${timeText}`).toISOString();
    }
    try {
        let utcMs = wallTimeMs - _timeZoneOffsetMs(new Date(wallTimeMs), timeZone);
        utcMs = wallTimeMs - _timeZoneOffsetMs(new Date(utcMs), timeZone);
        return new Date(utcMs).toISOString();
    } catch {
        return new Date(`${dateIso}T${timeText}`).toISOString();
    }
}

function _browserDeviceContext() {
    const browserTimezone = _browserTimeZone();
    const profileTimezone = _familyTimeZone();
    const context = {
        timezone: _displayTimeZone(),
        locale: navigator.language || "en-US",
        observed_at_utc: new Date().toISOString(),
        timezone_offset_minutes: new Date().getTimezoneOffset(),
        surface: "web",
        browser_timezone: browserTimezone,
        profile_timezone: profileTimezone,
        profile_location: _familyLocation(),
        semantic_place_hint: _semanticPlaceHint(),
        browser_geolocation_supported: _browserGeolocationSupported(),
        browser_geolocation_permission: state.browserLocationPermission,
        browser_geolocation_status: state.browserLocationStatus,
        location_permission: state.browserLocationPermission,
        location_fix: state.browserLocationFix,
    };
    if (state.browserLocationError) {
        context.browser_geolocation_error = state.browserLocationError;
    }
    return context;
}

function _sendDeviceContext() {
    if (!state.connected || !state.device) return;
    send({
        type: "device_context",
        member: state.member,
        device: state.device,
        device_context: _browserDeviceContext(),
    });
}

function _browserGeolocationSupported() {
    return typeof navigator !== "undefined" && !!navigator.geolocation && !!window.isSecureContext;
}

function _ensureBrowserLocation(options = {}) {
    const force = !!options.force;
    if (state.browserLocationPromise && !force) return state.browserLocationPromise;
    if (state.browserLocationRequested && !force && !_browserLocationNeedsRefresh()) {
        return Promise.resolve(state.browserLocationFix);
    }

    state.browserLocationRequested = true;
    state.browserLocationLastAttemptMs = Date.now();
    state.browserLocationPromise = _requestBrowserLocation()
        .catch((err) => {
            state.browserLocationPermission = "unavailable";
            state.browserLocationStatus = "unavailable";
            state.browserLocationFix = null;
            state.browserLocationError = {
                code: "location_request_failed",
                message: err && err.message ? String(err.message) : "Browser location request failed.",
            };
            return null;
        })
        .finally(() => {
            state.browserLocationPromise = null;
        });
    return state.browserLocationPromise;
}

async function _requestBrowserLocation() {
    if (!_browserGeolocationSupported()) {
        state.browserLocationPermission = "unavailable";
        state.browserLocationStatus = "unavailable";
        state.browserLocationFix = null;
        state.browserLocationError = {
            code: "unsupported_or_insecure_context",
            message: "Browser geolocation is unavailable on this page.",
        };
        return null;
    }

    const permission = await _readBrowserLocationPermission();
    if (permission === "denied") {
        state.browserLocationPermission = "denied";
        state.browserLocationStatus = "denied";
        state.browserLocationFix = null;
        state.browserLocationError = {
            code: "permission_denied",
            message: "Browser geolocation permission is denied.",
        };
        return null;
    }

    state.browserLocationPermission = _browserPermissionToSpatialPermission(permission);
    state.browserLocationStatus = "requesting";
    const position = await _getCurrentBrowserPosition();
    const coords = position.coords || {};
    state.browserLocationPermission = "granted";
    state.browserLocationStatus = "available";
    state.browserLocationError = null;
    state.browserLocationFix = {
        latitude: coords.latitude,
        longitude: coords.longitude,
        accuracy_m: coords.accuracy,
        altitude_m: coords.altitude,
        heading_deg: coords.heading,
        speed_mps: coords.speed,
        captured_at_utc: new Date(position.timestamp || Date.now()).toISOString(),
        source: "browser_geolocation",
        permission_state: "granted",
        metadata: {
            browser_geolocation: true,
            high_accuracy_requested: true,
            high_accuracy_strategy: "best_watch_position",
            desired_accuracy_m: BROWSER_LOCATION_TARGET_ACCURACY_M,
            observed_accuracy_m: coords.accuracy,
            accuracy_target_met: _positionAccuracy(position) <= BROWSER_LOCATION_TARGET_ACCURACY_M,
            maximum_age_ms: BROWSER_LOCATION_POSITION_OPTIONS.maximumAge,
            position_age_ms: Math.max(0, Date.now() - (position.timestamp || Date.now())),
        },
    };
    return state.browserLocationFix;
}

function _readBrowserLocationPermission() {
    const permissions = navigator.permissions;
    if (!permissions || typeof permissions.query !== "function") {
        return Promise.resolve("unknown");
    }
    return permissions.query({ name: "geolocation" })
        .then((result) => {
            result.onchange = () => {
                state.browserLocationPermission = _browserPermissionToSpatialPermission(result.state);
                state.browserLocationRequested = false;
                _sendDeviceContext();
            };
            return result.state || "unknown";
        })
        .catch(() => "unknown");
}

function _getCurrentBrowserPosition() {
    return new Promise((resolve, reject) => {
        let bestPosition = null;
        let lastError = null;
        let settled = false;
        let watchId = null;
        let timerId = null;

        const cleanup = () => {
            if (timerId !== null) window.clearTimeout(timerId);
            if (watchId !== null) {
                try { navigator.geolocation.clearWatch(watchId); } catch (_) { /* noop */ }
            }
        };
        const settle = (position, error) => {
            if (settled) return;
            settled = true;
            cleanup();
            if (position) {
                resolve(position);
                return;
            }
            const denied = error && error.code === error.PERMISSION_DENIED;
            state.browserLocationPermission = denied ? "denied" : "unavailable";
            state.browserLocationStatus = denied ? "denied" : "unavailable";
            state.browserLocationFix = null;
            state.browserLocationError = {
                code: error && error.code ? String(error.code) : "unknown",
                message: error && error.message ? String(error.message) : "Browser location unavailable.",
            };
            reject(error || new Error("Browser location unavailable."));
        };
        const consider = (position) => {
            if (!position || !position.coords) return;
            if (!bestPosition || _positionAccuracy(position) < _positionAccuracy(bestPosition)) {
                bestPosition = position;
            }
            if (_positionAccuracy(bestPosition) <= BROWSER_LOCATION_TARGET_ACCURACY_M) {
                settle(bestPosition, null);
            }
        };
        const rememberError = (error) => {
            lastError = error;
        };

        try {
            navigator.geolocation.getCurrentPosition(
                consider,
                rememberError,
                BROWSER_LOCATION_POSITION_OPTIONS,
            );
        } catch (error) {
            lastError = error;
        }
        try {
            watchId = navigator.geolocation.watchPosition(
                consider,
                rememberError,
                BROWSER_LOCATION_POSITION_OPTIONS,
            );
        } catch (error) {
            lastError = error;
        }
        timerId = window.setTimeout(() => {
            settle(bestPosition, lastError);
        }, BROWSER_LOCATION_WATCH_TIMEOUT_MS);
    });
}

function _browserLocationNeedsRefresh() {
    const elapsedMs = Date.now() - (state.browserLocationLastAttemptMs || 0);
    if (!state.browserLocationFix) return elapsedMs > BROWSER_LOCATION_REFRESH_INTERVAL_MS;
    const capturedMs = Date.parse(state.browserLocationFix.captured_at_utc || "");
    if (!Number.isNaN(capturedMs) && Date.now() - capturedMs > BROWSER_LOCATION_REFRESH_INTERVAL_MS) {
        return true;
    }
    const accuracy = Number(state.browserLocationFix.accuracy_m);
    return Number.isFinite(accuracy)
        && accuracy > BROWSER_LOCATION_TARGET_ACCURACY_M
        && elapsedMs > BROWSER_LOCATION_REFRESH_INTERVAL_MS;
}

function _positionAccuracy(position) {
    const accuracy = Number(position && position.coords ? position.coords.accuracy : NaN);
    return Number.isFinite(accuracy) ? accuracy : Number.POSITIVE_INFINITY;
}

function _browserPermissionToSpatialPermission(permission) {
    if (permission === "granted") return "granted";
    if (permission === "denied") return "denied";
    return "unknown";
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
    viewMode: "focus",
    year: new Date().getFullYear(),
    month: new Date().getMonth(),
    selectedDate: _localDateIso(),
    selectedEventKey: null,
    detailMode: null,
    events: [],
    feeds: [],
    manifest: null,
    loadedStart: "",
    loadedEnd: "",
};

const CALENDAR_VIEW_MODES = ["focus", "month", "week", "day"];
const CALENDAR_VIEW_LABELS = { focus: "Today & next", month: "Month", week: "Week", day: "Day" };
const CALENDAR_DAY_START_HOUR = 6;
const CALENDAR_DAY_END_HOUR = 22;
const CALENDAR_HOUR_HEIGHT = 56;
const CALENDAR_SOURCE_COLORS = {
    native: "#2563eb",
    google: "#16a34a",
    google_work: "#16a34a",
    google_personal: "#22c55e",
    outlook: "#7c3aed",
    outlook_default: "#7c3aed",
    microsoft: "#7c3aed",
    teams: "#4f46e5",
    classroom: "#0d9488",
    apple: "#4b5563",
    manual_import: "#0891b2",
    system_generated: "#be123c",
};
const CALENDAR_EVENT_PALETTE = ["#2563eb", "#16a34a", "#0d9488", "#dc2626", "#7c3aed", "#0891b2", "#be123c"];
const TASK_VIEW_MODES = ["list", "board", "focus"];
const TASK_PRIORITY_ORDER = { high: 0, medium: 1, low: 2 };
const TASK_STATUS_ORDER = { open: 0, in_progress: 1, done: 2, cancelled: 3 };
const REMINDER_VIEW_MODES = ["timeline", "board", "focus"];
const REMINDER_STATUS_ORDER = { fired: 0, scheduled: 1, snoozed: 2, dismissed: 3 };
const SHOPPING_VIEW_MODES = ["list", "aisles", "approval"];
const SHOPPING_CATEGORY_ORDER = ["groceries", "pharmacy", "household", "school", "clothes", "pets", "gifts", "other"];
const SHOPPING_CATEGORY_COLORS = {
    groceries: "#16a34a",
    pharmacy: "#dc2626",
    household: "#2563eb",
    school: "#7c3aed",
    clothes: "#ec4899",
    pets: "#0891b2",
    gifts: "#be123c",
    other: "#6b7280",
};
const SHOPPING_QUICK_ITEMS = {
    groceries: ["Milk", "Bread", "Eggs", "Fruit"],
    pharmacy: ["Allergy meds", "Bandages", "Vitamins", "Thermometer"],
    household: ["Paper towels", "Laundry soap", "Dish tabs", "Trash bags"],
    school: ["Notebook", "Pencils", "Glue sticks", "Lunch bags"],
    clothes: ["Socks", "Shoes", "Rain jacket", "Uniform"],
    gifts: ["Card", "Wrapping paper", "Candles", "Flowers"],
    other: ["Milk", "Bread", "Medicine", "Paper towels"],
};
const CHORE_VIEW_MODES = ["today", "board", "list", "rewards"];
const CHORE_STATUS_ORDER = { pending: 0, done: 1, skipped: 2 };
const CHORE_STATUS_META = {
    pending: { label: "Pending", color: "#2563eb" },
    done: { label: "Done", color: "#16a34a" },
    skipped: { label: "Skipped", color: "#64748b" },
};
const SETTINGS_VIEW_MODES = ["overview", "privacy", "kids", "sensitive", "features"];
const SETTINGS_BAND_COLORS = {
    family: "#2563eb",
    adults: "#7c3aed",
    named: "#0891b2",
    private: "#dc2626",
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
            const shoppingLists = adapterCache.listData.shopping?.lists || [];
            const shoppingItems = adapterCache.listData.shopping?.items || [];
            const shoppingDefaults = adapterId === "shopping" && actionName === "add_item"
                ? _shoppingAddDefaults(shoppingLists, shoppingItems)
                : {};
            if (adapterId === "shopping" && actionName === "add_item" && !shoppingDefaults.list_id) {
                showToast("Shopping", "Create or select a list before adding an item.");
                return;
            }
            if (action) showActionForm(adapterId, action, adapterId === "shopping" && actionName === "add_item" ? shoppingDefaults : _actionDefaults(adapterId, actionName));
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
    if (adapterId === "shopping" && actionName === "add_item") {
        const lists = adapterCache.listData.shopping?.lists || [];
        const items = adapterCache.listData.shopping?.items || [];
        const defaults = _shoppingAddDefaults(lists, items);
        if (defaults.list_id) return defaults;
    }
    if (adapterId === "reminders" && actionName === "create_reminder") {
        const selectedRecipient = state.remindersSelectedRecipient && state.remindersSelectedRecipient !== "__all__"
            ? _reminderCanonicalMemberId(state.remindersSelectedRecipient)
            : _currentMemberActorId();
        return {
            recipient: selectedRecipient,
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
    const base = /^\d{4}-\d{2}-\d{2}$/.test(dateIso || "") ? dateIso : _localDateIso();
    return {
        start: _zonedDateTimeToIso(base, "09:00:00"),
        end: _zonedDateTimeToIso(base, "10:00:00"),
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

    body.innerHTML = `
        <div class="cal-shell app-page-shell app-density--calm">
            <div class="cal-layout app-workspace">
                <div class="cal-main app-focus-card">
                <div class="cal-nav">
                    <div class="cal-nav-heading">
                        <h3 class="cal-month-label" id="cal-month-label"></h3>
                        <p class="cal-mode-hint" id="cal-mode-hint"></p>
                    </div>
                    <div class="cal-nav-actions">
                        <div class="cal-view-switch" role="tablist" aria-label="Calendar view">
                            ${CALENDAR_VIEW_MODES.map((mode) => `
                                <button class="cal-view-switch-btn${calState.viewMode === mode ? " cal-view-switch-btn--active" : ""}" type="button" role="tab" aria-selected="${calState.viewMode === mode ? "true" : "false"}" data-cal-view="${mode}">${CALENDAR_VIEW_LABELS[mode] || _humanizeLabel(mode)}</button>
                            `).join("")}
                        </div>
                        <div class="cal-nav-controls">
                            <button class="cal-nav-btn" id="cal-prev" aria-label="Previous"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6"/></svg></button>
                            <button class="cal-today-btn" id="cal-today">Today</button>
                            <button class="cal-nav-btn" id="cal-next" aria-label="Next"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"/></svg></button>
                        </div>
                    </div>
                </div>
                <div id="cal-main-surface"></div>
            </div>
            <aside class="cal-side app-support-rail">
                <div id="cal-side-panel"></div>
                <div id="cal-color-legend"></div>
                ${calState.feeds.length ? `<div class="cal-feed-list"><h3>Feeds</h3><div id="cal-feeds"></div></div>` : ""}
            </aside>
            </div>
            <div class="app-detail-drawer-backdrop" data-app-drawer-backdrop="cal-detail-drawer" aria-hidden="true"></div>
            <aside class="app-detail-drawer app-detail-drawer--overlay cal-detail-drawer" id="cal-detail-drawer" data-app-drawer="cal-detail-drawer" aria-hidden="true" aria-label="Calendar detail">
                <div id="cal-detail-drawer-body"></div>
            </aside>
        </div>`;

    _calRenderMain();
    _calRenderEventDetail();
    _calRenderSidePanel();
    _calRenderColorLegend();
    _calRenderFeeds();

    body.querySelector("#cal-prev").addEventListener("click", () => {
        _calNavigate(-1);
    });
    body.querySelector("#cal-next").addEventListener("click", () => {
        _calNavigate(1);
    });
    body.querySelector("#cal-today").addEventListener("click", () => {
        _calSetSelectedDate(_localDateIso());
        calState.selectedEventKey = null;
        calState.detailMode = null;
        calState.viewMode = "focus";
        _calRenderAll();
    });
    body.querySelectorAll("[data-cal-view]").forEach((button) => {
        button.addEventListener("click", () => {
            calState.viewMode = button.dataset.calView || "focus";
            calState.detailMode = null;
            _calRefreshForCurrentRange();
        });
    });
}

function _calRenderAll() {
    _calRenderMain();
    _calRenderEventDetail();
    _calRenderSidePanel();
    _calRenderColorLegend();
}

function _calRenderMain() {
    const MONTHS = ["January","February","March","April","May","June","July","August","September","October","November","December"];
    const label = document.getElementById("cal-month-label");
    const hint = document.getElementById("cal-mode-hint");
    const surface = document.getElementById("cal-main-surface");
    if (!label || !surface) return;

    document.querySelectorAll("[data-cal-view]").forEach((button) => {
        const active = button.dataset.calView === calState.viewMode;
        button.classList.toggle("cal-view-switch-btn--active", active);
        button.setAttribute("aria-selected", active ? "true" : "false");
    });

    if (calState.viewMode === "focus") {
        label.textContent = "Today and next";
        if (hint) hint.textContent = _formatDateLabel(calState.selectedDate);
        _calRenderFocus(surface);
        return;
    }
    if (calState.viewMode === "day") {
        label.textContent = _calLongDateLabel(calState.selectedDate);
        if (hint) hint.textContent = "Detailed day grid";
        _calRenderDay(surface);
        return;
    }
    if (calState.viewMode === "week") {
        label.textContent = _calWeekLabel(calState.selectedDate);
        if (hint) hint.textContent = "Full week grid";
        _calRenderWeek(surface);
        return;
    }

    label.textContent = `${MONTHS[calState.month]} ${calState.year}`;
    if (hint) hint.textContent = "Month overview";
    _calRenderMonth(surface);
}

function _calRenderFocus(surface) {
    const manifest = calState.manifest || { actions: [] };
    const metrics = _calOverviewMetrics();
    const nextEvent = metrics.nextEvent;
    const nextColor = nextEvent ? _calEventColor(nextEvent) : "#2563eb";
    const nextDateIso = nextEvent ? _calEventDateIso(nextEvent) : calState.selectedDate;
    const nextDate = _calDateFromIso(nextDateIso);
    const todayPreview = metrics.selectedDayEvents.slice(0, 4);
    const upcomingBlocks = metrics.weekEvents.slice(0, 6);

    surface.innerHTML = `
        <div class="cal-focus-surface">
            <div class="cal-focus-stage">
                <section class="cal-focus-hero${nextEvent ? "" : " cal-focus-hero--empty"}" style="--ev-color:${nextColor}">
                    <div class="cal-focus-hero-top">
                        <p class="cal-side-kicker">Up next</p>
                        <div class="cal-focus-date-token" aria-hidden="true">
                            <span>${nextDate.toLocaleDateString("en-US", { weekday: "short" })}</span>
                            <strong>${nextDate.getDate()}</strong>
                            <small>${nextDate.toLocaleDateString("en-US", { month: "short" })}</small>
                        </div>
                    </div>
                    <div class="cal-focus-hero-copy">
                        <h4>${escapeHtml(nextEvent?.title || "Open family time")}</h4>
                        <p>${escapeHtml(nextEvent ? _fmtEventTime(nextEvent.start, nextEvent.end, nextEvent.all_day) : "The next stretch is clear. Add anything the family needs to coordinate.")}</p>
                        <div class="cal-focus-pill-row">
                            <span class="cal-focus-pill">${escapeHtml(nextEvent ? _calEventDurationLabel(nextEvent) : "Clear")}</span>
                            <span class="cal-focus-pill cal-focus-pill--source">${escapeHtml(nextEvent ? _calEventColorLabel(nextEvent) : "Family")}</span>
                            ${nextEvent?.location ? `<span class="cal-focus-pill cal-focus-pill--location">${escapeHtml(nextEvent.location)}</span>` : ""}
                        </div>
                    </div>
                    <div class="cal-focus-hero-actions">
                        ${nextEvent ? `<button class="view-small-btn view-small-btn--primary" type="button" data-cal-event-key="${escapeHtml(_calEventKey(nextEvent))}" data-cal-event-date="${escapeHtml(nextDateIso)}">Details</button>` : ""}
                        ${_hasAction(manifest, "create_event") ? `<button class="view-small-btn" type="button" id="cal-add-focus">Add event</button>` : ""}
                    </div>
                </section>
                <section class="cal-focus-panel cal-focus-panel--decisions cal-focus-panel--feature">
                    <header class="cal-focus-panel-head">
                        <div>
                            <p class="cal-side-kicker">Needs a decision</p>
                            <h4>${metrics.conflicts.length ? `${metrics.conflicts.length} overlap${metrics.conflicts.length === 1 ? "" : "s"}` : "Schedule is calm"}</h4>
                        </div>
                    </header>
                    <div class="cal-decision-list">
                        ${metrics.conflicts.length ? metrics.conflicts.slice(0, 3).map((conflict) => _calConflictRow(conflict)).join("") : `
                            <div class="cal-decision-empty">
                                <strong>No overlaps in the next week</strong>
                                <span>Month, Week, and Day stay ready when you need the full scheduler.</span>
                            </div>`}
                    </div>
                </section>
            </div>
            <div class="cal-focus-lower">
                <section class="cal-focus-panel cal-focus-panel--today">
                    <header class="cal-focus-panel-head">
                        <div>
                            <p class="cal-side-kicker">Today</p>
                            <h4>${escapeHtml(_formatDateLabel(calState.selectedDate))}</h4>
                        </div>
                        <button class="view-small-btn" type="button" data-cal-day-open="${escapeHtml(calState.selectedDate)}">Open day</button>
                    </header>
                    <div class="cal-focus-list">
                        ${todayPreview.length ? todayPreview.map((event) => _calFocusEventRow(event, calState.selectedDate)).join("") : `<div class="cal-quiet-state">No events on this day.</div>`}
                        ${metrics.selectedDayEvents.length > todayPreview.length ? `<button class="cal-subtle-link" type="button" data-cal-day-open="${escapeHtml(calState.selectedDate)}">View ${metrics.selectedDayEvents.length - todayPreview.length} more</button>` : ""}
                    </div>
                </section>
                <section class="cal-focus-panel cal-family-blocks">
                    <header class="cal-focus-panel-head">
                        <div>
                            <p class="cal-side-kicker">Coming up</p>
                            <h4>Family blocks</h4>
                        </div>
                        <button class="view-small-btn view-small-btn--primary" type="button" data-cal-show-week>Show full week grid</button>
                    </header>
                    <div class="cal-block-list">
                        ${upcomingBlocks.length ? upcomingBlocks.map((event) => _calFocusEventRow(event, _calEventDateIso(event), "cal-focus-event-row--block")).join("") : `<div class="cal-quiet-state">Nothing scheduled in the next seven days.</div>`}
                    </div>
                </section>
            </div>
        </div>`;

    const addButton = surface.querySelector("#cal-add-focus");
    if (addButton) {
        addButton.addEventListener("click", () => _openAdapterAction("calendar", manifest, "create_event", _defaultEventTimes(calState.selectedDate)));
    }
    _calWireDayOpen(surface);
    _calWireShowWeek(surface);
    _calWireEventClicks(surface);
}

function _calOverviewMetrics() {
    const selectedDate = calState.selectedDate || _localDateIso();
    const selectedDayEvents = _calEventsOnDate(selectedDate);
    const weekEnd = _calAddDays(selectedDate, 6);
    const weekEvents = _calSortEvents(calState.events.filter((event) => {
        const eventDate = _calEventDateIso(event);
        return eventDate && eventDate >= selectedDate && eventDate <= weekEnd;
    }));
    const futureEvents = weekEvents.filter((event) => _calEventIsUpcomingOrOngoing(event, selectedDate));
    const currentEvent = selectedDayEvents.find((event) => _calEventIsOngoing(event)) || null;
    return {
        selectedDate,
        selectedDayEvents,
        weekEvents,
        nextEvent: currentEvent || futureEvents[0] || weekEvents[0] || null,
        conflicts: _calFindConflicts(selectedDate, weekEnd),
    };
}

function _calEventIsUpcomingOrOngoing(event, fallbackDateIso = "") {
    const now = new Date();
    const endMs = _calEventEndMs(event);
    const startMs = _calEventStartMs(event);
    if (Number.isFinite(endMs) && endMs >= now.getTime()) return true;
    if (Number.isFinite(startMs) && startMs >= now.getTime()) return true;
    const eventDate = _calEventDateIso(event);
    const todayIso = _localDateIso(now);
    return Boolean(fallbackDateIso && eventDate > todayIso && eventDate >= fallbackDateIso);
}

function _calEventIsOngoing(event) {
    const nowMs = Date.now();
    const startMs = _calEventStartMs(event);
    const endMs = _calEventEndMs(event);
    return Number.isFinite(startMs) && Number.isFinite(endMs) && startMs <= nowMs && endMs >= nowMs;
}

function _calEventStartMs(event) {
    const date = new Date(event.start || "");
    return isNaN(date) ? NaN : date.getTime();
}

function _calEventEndMs(event) {
    const date = new Date(event.end || event.start || "");
    if (isNaN(date)) return NaN;
    const startMs = _calEventStartMs(event);
    return Number.isFinite(startMs) && date.getTime() <= startMs ? startMs + 30 * 60 * 1000 : date.getTime();
}

function _calEventDurationLabel(event) {
    if (event.all_day || _calIsAllDay(event)) return "All day";
    const startMs = _calEventStartMs(event);
    const endMs = _calEventEndMs(event);
    if (!Number.isFinite(startMs) || !Number.isFinite(endMs) || endMs <= startMs) return "Scheduled";
    const minutes = Math.round((endMs - startMs) / 60000);
    if (minutes < 60) return `${minutes} min`;
    const hours = Math.floor(minutes / 60);
    const remaining = minutes % 60;
    return remaining ? `${hours}h ${remaining}m` : `${hours}h`;
}

function _calFindConflicts(startIso, endIso) {
    const conflicts = [];
    for (let cursor = startIso, guard = 0; guard < 31 && cursor <= endIso; guard += 1, cursor = _calAddDays(cursor, 1)) {
        const timedEvents = _calTimedEvents(cursor).filter((event) => Number.isFinite(_calEventStartMs(event)));
        const sorted = _calSortEvents(timedEvents);
        const active = [];
        sorted.forEach((current) => {
            const currentStart = _calEventStartMs(current);
            for (let index = active.length - 1; index >= 0; index -= 1) {
                if (_calEventEndMs(active[index]) <= currentStart) active.splice(index, 1);
            }
            active.forEach((previous) => {
                conflicts.push({ dateIso: cursor, first: previous, second: current });
            });
            active.push(current);
        });
        if (conflicts.length >= 12) {
            return conflicts.slice(0, 12);
        }
    }
    return conflicts;
}

function _calFocusEventRow(event, dateIso = "", extraClass = "") {
    const color = _calEventColor(event);
    const eventDate = dateIso || _calEventDateIso(event);
    return `
        <button class="cal-focus-event-row ${extraClass}" type="button" data-cal-event-key="${escapeHtml(_calEventKey(event))}" data-cal-event-date="${escapeHtml(eventDate)}" style="--ev-color:${color}">
            <span class="cal-focus-event-mark"></span>
            <span class="cal-focus-event-copy">
                <strong>${escapeHtml(event.title || "Untitled")}</strong>
                <span>${escapeHtml(_calCompactEventLine(event, eventDate))}</span>
            </span>
        </button>`;
}

function _calConflictRow(conflict) {
    return `
        <button class="cal-conflict-row" type="button" data-cal-day-open="${escapeHtml(conflict.dateIso)}">
            <span class="cal-conflict-badge">Overlap</span>
            <span class="cal-conflict-copy">
                <strong>${escapeHtml(_formatDateLabel(conflict.dateIso))}</strong>
                <span>${escapeHtml(conflict.first.title || "Untitled")} + ${escapeHtml(conflict.second.title || "Untitled")}</span>
            </span>
        </button>`;
}

function _calCompactEventLine(event, eventDate = "") {
    const dateLabel = eventDate && eventDate !== calState.selectedDate ? `${_formatDateLabel(eventDate)} · ` : "";
    const timeLabel = _fmtEventTimeShort(event.start, event.end, event.all_day);
    const location = event.location ? ` · ${event.location}` : "";
    return `${dateLabel}${timeLabel}${location}`;
}

function _calRenderSidePanel() {
    const panel = document.getElementById("cal-side-panel");
    if (!panel) return;
    const metrics = _calOverviewMetrics();
    const dayButtons = Array.from({ length: 7 }, (_, index) => {
        const dateIso = _calAddDays(metrics.selectedDate, index);
        const date = _calDateFromIso(dateIso);
        const events = _calEventsOnDate(dateIso);
        return `
            <button class="cal-week-peek-day${dateIso === metrics.selectedDate ? " cal-week-peek-day--selected" : ""}${dateIso === _localDateIso() ? " cal-week-peek-day--today" : ""}" type="button" data-cal-day-open="${escapeHtml(dateIso)}">
                <span>${date.toLocaleDateString("en-US", { weekday: "short" })}</span>
                <strong>${date.getDate()}</strong>
                <small>${events.length}</small>
            </button>`;
    }).join("");
    panel.innerHTML = `
        <section class="cal-side-card">
            <div class="cal-side-card-head">
                <div>
                    <p class="cal-side-kicker">Week rhythm</p>
                    <h3>Pick a day</h3>
                </div>
                <button class="cal-subtle-link" type="button" data-cal-view-side="focus">Reset</button>
            </div>
            <div class="cal-week-peek">${dayButtons}</div>
        </section>
        <section class="cal-side-card cal-side-card--quiet">
            <p class="cal-side-kicker">Power scheduler</p>
            <h3>${CALENDAR_VIEW_LABELS[calState.viewMode] || _humanizeLabel(calState.viewMode)}</h3>
            <p>${calState.viewMode === "focus" ? "Use the full week grid when timing and overlaps matter." : "You are in a dense planning mode. Event and day details still open in the drawer."}</p>
            <div class="cal-side-actions">
                <button class="view-small-btn view-small-btn--primary" type="button" data-cal-show-week>Show full week grid</button>
                <button class="view-small-btn" type="button" data-cal-view-side="month">Month</button>
            </div>
        </section>`;
    _calWireDayOpen(panel);
    _calWireShowWeek(panel);
    panel.querySelectorAll("[data-cal-view-side]").forEach((button) => {
        button.addEventListener("click", () => {
            calState.viewMode = button.dataset.calViewSide || "focus";
            calState.detailMode = null;
            _calRefreshForCurrentRange();
        });
    });
}

function _calWireDayOpen(container) {
    container.querySelectorAll("[data-cal-day-open]").forEach((button) => {
        button.addEventListener("click", () => _calOpenDay(button.dataset.calDayOpen));
    });
}

function _calWireShowWeek(container) {
    container.querySelectorAll("[data-cal-show-week]").forEach((button) => {
        button.addEventListener("click", () => {
            calState.viewMode = "week";
            calState.detailMode = null;
            if (typeof closeAppDetailDrawer === "function") closeAppDetailDrawer(resolveAppDisclosureTarget("cal-detail-drawer", ".app-detail-drawer"));
            _calRefreshForCurrentRange();
        });
    });
}

function _calRenderMonth(surface) {
    const today = new Date();
    const firstDay = new Date(calState.year, calState.month, 1).getDay();
    const daysInMonth = new Date(calState.year, calState.month + 1, 0).getDate();

    const evMap = {};
    calState.events.forEach((event) => {
        _calEventDateIsos(event).forEach((dateIso) => {
            (evMap[dateIso] = evMap[dateIso] || []).push(event);
        });
    });

    let html = "";
    for (let i = 0; i < firstDay; i++) html += `<div class="cal-cell cal-cell--empty"></div>`;
    for (let dayOfMonth = 1; dayOfMonth <= daysInMonth; dayOfMonth++) {
        const dateIso = `${calState.year}-${String(calState.month + 1).padStart(2, "0")}-${String(dayOfMonth).padStart(2, "0")}`;
        const isToday = today.getFullYear() === calState.year && today.getMonth() === calState.month && today.getDate() === dayOfMonth;
        const isSelected = calState.selectedDate === dateIso;
        const events = _calSortEvents(evMap[dateIso] || []);
        const chips = events.slice(0, 3).map((event) =>
            _calEventChip(event, "cal-event-chip--month", dateIso)
        ).join("");
        const more = events.length > 3 ? `<button class="cal-more-events" type="button" data-cal-more-date="${dateIso}">+${events.length - 3} more</button>` : "";
        html += `
            <div class="cal-cell${isToday ? " cal-cell--today" : ""}${isSelected ? " cal-cell--selected" : ""}" data-date="${dateIso}">
                <button class="cal-cell-date" type="button" data-date="${dateIso}" aria-label="${escapeHtml(_formatDateLabel(dateIso))}">
                    <span class="cal-day-num">${dayOfMonth}</span>
                </button>
                <div class="cal-event-bars">${chips}${more}</div>
            </div>`;
    }
    surface.innerHTML = `
        <div class="cal-grid-header">
            <span>Sun</span><span>Mon</span><span>Tue</span>
            <span>Wed</span><span>Thu</span><span>Fri</span><span>Sat</span>
        </div>
        <div class="cal-grid" id="cal-grid">${html}</div>`;
    surface.querySelectorAll(".cal-cell[data-date]").forEach((cell) => {
        cell.addEventListener("click", (clickEvent) => {
            if (clickEvent.target.closest("[data-cal-event-key]")) return;
            if (clickEvent.target.closest("[data-cal-more-date]")) return;
            _calOpenDay(cell.dataset.date);
        });
    });
    surface.querySelectorAll("[data-cal-more-date]").forEach((button) => {
        button.addEventListener("click", (clickEvent) => {
            clickEvent.stopPropagation();
            _calOpenDay(button.dataset.calMoreDate);
        });
    });
    _calWireEventClicks(surface);
}

function _calRenderWeek(surface) {
    const weekStartIso = _calStartOfWeekIso(calState.selectedDate);
    const dayIsos = Array.from({ length: 7 }, (_, index) => _calAddDays(weekStartIso, index));
    const hourLabels = _calHourLabels();
    surface.innerHTML = `
        <div class="cal-week-shell" style="--cal-hour-height:${CALENDAR_HOUR_HEIGHT}px;--cal-schedule-height:${_calScheduleHeight()}px">
            <div class="cal-week-head">
                <div class="cal-time-gutter"></div>
                ${dayIsos.map((dateIso) => _calWeekDayHeader(dateIso)).join("")}
            </div>
            <div class="cal-week-all-day">
                <div class="cal-all-day-label">All-day</div>
                ${dayIsos.map((dateIso) => _calAllDayLane(dateIso)).join("")}
            </div>
            <div class="cal-schedule-scroll">
                <div class="cal-hour-gutter">
                    ${hourLabels.map((labelText) => `<span>${escapeHtml(labelText)}</span>`).join("")}
                </div>
                <div class="cal-week-days">
                    ${dayIsos.map((dateIso) => _calTimedDayColumn(dateIso, "week")).join("")}
                </div>
            </div>
        </div>`;
    _calWireDateButtons(surface);
    _calWireEventClicks(surface);
}

function _calRenderDay(surface) {
    const dateIso = calState.selectedDate;
    const hourLabels = _calHourLabels();
    surface.innerHTML = `
        <div class="cal-day-shell" style="--cal-hour-height:${CALENDAR_HOUR_HEIGHT}px;--cal-schedule-height:${_calScheduleHeight()}px">
            <div class="cal-day-focus-head">
                <div>
                    <p class="cal-side-kicker">${escapeHtml(_formatDateLabel(dateIso))}</p>
                    <h4>${_calEventsOnDate(dateIso).length} events</h4>
                </div>
                ${_hasAction(calState.manifest || { actions: [] }, "create_event") ? `<button class="view-small-btn view-small-btn--primary" id="cal-add-main-day">Add event</button>` : ""}
            </div>
            <div class="cal-day-all-day">
                <span class="cal-all-day-label">All-day</span>
                <div>${_calAllDayEvents(dateIso).map((event) => _calEventChip(event, "cal-event-chip--all-day", dateIso)).join("") || `<span class="cal-empty-inline">None</span>`}</div>
            </div>
            <div class="cal-schedule-scroll cal-schedule-scroll--day">
                <div class="cal-hour-gutter">
                    ${hourLabels.map((labelText) => `<span>${escapeHtml(labelText)}</span>`).join("")}
                </div>
                <div class="cal-day-column-wrap">
                    ${_calTimedDayColumn(dateIso, "day")}
                </div>
            </div>
        </div>`;
    const addButton = surface.querySelector("#cal-add-main-day");
    if (addButton) {
        addButton.addEventListener("click", () => _openAdapterAction("calendar", calState.manifest || { actions: [] }, "create_event", _defaultEventTimes(calState.selectedDate)));
    }
    _calWireEventClicks(surface);
}

async function _calNavigate(direction) {
    if (calState.viewMode === "month") {
        const nextMonth = new Date(calState.year, calState.month + direction, 1);
        calState.year = nextMonth.getFullYear();
        calState.month = nextMonth.getMonth();
        calState.selectedDate = _calDateToIso(nextMonth);
    } else {
        const days = calState.viewMode === "week" ? 7 : 1;
        _calSetSelectedDate(_calAddDays(calState.selectedDate, direction * days));
    }
    calState.selectedEventKey = null;
    calState.detailMode = null;
    await _calRefreshForCurrentRange();
}

async function _calRefreshForCurrentRange() {
    const manifest = calState.manifest || adapterCache.manifest.calendar || { actions: [] };
    const action = (manifest.actions || []).find((item) => item.kind === "read" && item.name === "list_events");
    if (!action) {
        _calRenderAll();
        return;
    }
    const range = _calListRangeParams();
    if (calState.loadedStart === range.start && calState.loadedEnd === range.end) {
        _calRenderAll();
        return;
    }
    const previousEvents = calState.events;
    try {
        const eventData = await _callListAction("calendar", action, range);
        if (Array.isArray(eventData?.events)) {
            calState.events = eventData.events;
            calState.loadedStart = range.start;
            calState.loadedEnd = range.end;
            adapterCache.listData.calendar = {
                ...(adapterCache.listData.calendar || {}),
                events: calState.events,
                event_result: eventData,
            };
        }
    } catch {
        calState.events = previousEvents;
    }
    _calRenderAll();
}

function _calListRangeParams() {
    const visible = _calVisibleRange();
    const todayIso = _localDateIso();
    const upcomingEndIso = _calAddDays(todayIso, 90);
    const startDate = visible.start < todayIso ? visible.start : todayIso;
    const endDate = visible.end > upcomingEndIso ? visible.end : upcomingEndIso;
    return {
        start: `${startDate}T00:00:00`,
        end: `${endDate}T23:59:59`,
        start_date: startDate,
        end_date: endDate,
    };
}

function _calVisibleRange() {
    if (calState.viewMode === "month") {
        const firstOfMonth = `${calState.year}-${String(calState.month + 1).padStart(2, "0")}-01`;
        const start = _calStartOfWeekIso(firstOfMonth);
        return { start, end: _calAddDays(start, 41) };
    }
    if (calState.viewMode === "week") {
        const start = _calStartOfWeekIso(calState.selectedDate);
        return { start, end: _calAddDays(start, 6) };
    }
    if (calState.viewMode === "focus") {
        return { start: calState.selectedDate, end: _calAddDays(calState.selectedDate, 6) };
    }
    return { start: calState.selectedDate, end: calState.selectedDate };
}

function _calDateFromIso(dateIso) {
    const parts = String(dateIso || "").split("-").map((part) => Number(part));
    if (parts.length >= 3 && parts.every(Number.isFinite)) {
        return new Date(parts[0], parts[1] - 1, parts[2]);
    }
    return new Date();
}

function _calDateToIso(date) {
    return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

function _calSetSelectedDate(dateIso) {
    const date = _calDateFromIso(dateIso);
    calState.selectedDate = _calDateToIso(date);
    calState.year = date.getFullYear();
    calState.month = date.getMonth();
}

function _calAddDays(dateIso, days) {
    const date = _calDateFromIso(dateIso);
    date.setDate(date.getDate() + days);
    return _calDateToIso(date);
}

function _calStartOfWeekIso(dateIso) {
    const date = _calDateFromIso(dateIso);
    date.setDate(date.getDate() - date.getDay());
    return _calDateToIso(date);
}

function _calWeekLabel(dateIso) {
    const startIso = _calStartOfWeekIso(dateIso);
    const endIso = _calAddDays(startIso, 6);
    const startDate = _calDateFromIso(startIso);
    const endDate = _calDateFromIso(endIso);
    const sameMonth = startDate.getMonth() === endDate.getMonth() && startDate.getFullYear() === endDate.getFullYear();
    const startLabel = startDate.toLocaleDateString("en-US", { month: "short", day: "numeric" });
    if (sameMonth) {
        return `${startLabel} - ${endDate.getDate()}, ${endDate.getFullYear()}`;
    }
    const endLabel = endDate.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
    return `${startLabel} - ${endLabel}`;
}

function _calLongDateLabel(dateIso) {
    const date = _calDateFromIso(dateIso);
    return date.toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric", year: "numeric" });
}

function _calEventKey(event) {
    return _calEventId(event) || [event.start || "", event.end || "", event.title || "", event.actor || event.created_by || ""].join("|");
}

function _calEventId(event) {
    return _idOf(event, "event_id");
}

function _calFindEvent(eventKey) {
    return calState.events.find((event) => _calEventKey(event) === eventKey) || null;
}

function _calEventDateIso(event) {
    const rawStart = String(event.start || "");
    if (/^\d{4}-\d{2}-\d{2}$/.test(rawStart)) return rawStart;
    const parts = _calDateTimeParts(rawStart);
    if (!parts) return "";
    return `${parts.year}-${String(parts.month).padStart(2, "0")}-${String(parts.day).padStart(2, "0")}`;
}

function _calEventsOnDate(dateIso) {
    return _calSortEvents(calState.events.filter((event) => _calEventOverlapsDate(event, dateIso)));
}

function _calSortEvents(events) {
    return [...events].sort((firstEvent, secondEvent) => String(firstEvent.start || "").localeCompare(String(secondEvent.start || "")));
}

function _calAllDayEvents(dateIso) {
    return _calEventsOnDate(dateIso).filter((event) => event.all_day || _calIsAllDay(event));
}

function _calTimedEvents(dateIso) {
    return _calEventsOnDate(dateIso).filter((event) => !event.all_day && !_calIsAllDay(event));
}

function _calEventEndDateIso(event) {
    const rawEnd = String(event.end || event.start || "");
    if (/^\d{4}-\d{2}-\d{2}$/.test(rawEnd)) return rawEnd;
    const parts = _calDateTimeParts(rawEnd);
    if (!parts) return _calEventDateIso(event);
    return `${parts.year}-${String(parts.month).padStart(2, "0")}-${String(parts.day).padStart(2, "0")}`;
}

function _calEventOverlapsDate(event, dateIso) {
    const startIso = _calEventDateIso(event);
    const endIso = _calEventEndDateIso(event) || startIso;
    if (!startIso) return false;
    return dateIso >= startIso && dateIso <= endIso;
}

function _calEventDateIsos(event) {
    const startIso = _calEventDateIso(event);
    if (!startIso) return [];
    const endIso = _calEventEndDateIso(event) || startIso;
    const dates = [];
    let cursor = startIso;
    for (let guard = 0; guard < 370 && cursor <= endIso; guard += 1) {
        dates.push(cursor);
        cursor = _calAddDays(cursor, 1);
    }
    return dates;
}

function _calIsAllDay(event) {
    const start = String(event.start || "");
    const end = String(event.end || "");
    return /^\d{4}-\d{2}-\d{2}$/.test(start) || (start.endsWith("T00:00:00") && end.endsWith("T00:00:00"));
}

function _calEventColor(event) {
    const metadata = event.metadata && typeof event.metadata === "object" ? event.metadata : {};
    const directColor = event.color || metadata.color || metadata.calendar_color;
    if (typeof directColor === "string" && /^#[0-9a-f]{3,8}$/i.test(directColor.trim())) {
        return directColor.trim();
    }
    const source = String(event.source || event.feed_source || "").toLowerCase();
    if (CALENDAR_SOURCE_COLORS[source]) return CALENDAR_SOURCE_COLORS[source];
    if (source.includes("google")) return CALENDAR_SOURCE_COLORS.google;
    if (source.includes("outlook") || source.includes("microsoft")) return CALENDAR_SOURCE_COLORS.outlook;
    if (source.includes("team")) return CALENDAR_SOURCE_COLORS.teams;
    if (source.includes("classroom") || source.includes("school")) return CALENDAR_SOURCE_COLORS.classroom;
    const owner = event.actor || event.created_by || (Array.isArray(event.attendees) ? event.attendees[0] : "");
    const memberColor = _memberColor(owner);
    if (memberColor !== "#9ca3af") return memberColor;
    const key = `${event.source_label || ""}|${event.visibility || ""}|${event.title || ""}`;
    let hash = 0;
    for (const character of key) hash = ((hash << 5) - hash) + character.charCodeAt(0);
    return CALENDAR_EVENT_PALETTE[Math.abs(hash) % CALENDAR_EVENT_PALETTE.length];
}

function _calEventColorLabel(event) {
    if (event.source_label) return _calReadableLabel(event.source_label);
    if (event.source && event.source !== "native") return _calReadableLabel(event.source);
    if (event.actor) return _calReadableLabel(event.actor);
    if (Array.isArray(event.attendees) && event.attendees.length) return _calReadableLabel(event.attendees[0]);
    return "Family";
}

function _calReadableLabel(value) {
    const label = String(value || "").replace(/[._-]+/g, " ").replace(/\s+/g, " ").trim();
    if (/^(concierge|system|kernel|adapter)\b/i.test(label) || /\b(back|backend|generated)\b/i.test(label)) return "Family";
    return label ? _humanizeLabel(label) : "Family";
}

function _calEventChip(event, extraClass = "", dateIso = "") {
    const color = _calEventColor(event);
    const eventKey = _calEventKey(event);
    const title = event.title || "Untitled";
    return `
        <button class="cal-event-chip ${extraClass}" type="button" data-cal-event-key="${escapeHtml(eventKey)}"${dateIso ? ` data-cal-event-date="${escapeHtml(dateIso)}"` : ""} style="--ev-color:${color}" title="${escapeHtml(title)}">
            ${escapeHtml(title)}
        </button>`;
}

function _calWeekDayHeader(dateIso) {
    const date = _calDateFromIso(dateIso);
    const isToday = dateIso === _localDateIso();
    const isSelected = dateIso === calState.selectedDate;
    return `
        <button class="cal-week-day-head${isToday ? " cal-week-day-head--today" : ""}${isSelected ? " cal-week-day-head--selected" : ""}" type="button" data-cal-date="${dateIso}">
            <span>${date.toLocaleDateString("en-US", { weekday: "short" })}</span>
            <strong>${date.getDate()}</strong>
        </button>`;
}

function _calAllDayLane(dateIso) {
    const events = _calAllDayEvents(dateIso);
    return `
        <div class="cal-all-day-lane${dateIso === calState.selectedDate ? " cal-all-day-lane--selected" : ""}">
            ${events.length ? events.map((event) => _calEventChip(event, "cal-event-chip--all-day", dateIso)).join("") : `<span class="cal-empty-inline">None</span>`}
        </div>`;
}

function _calTimedDayColumn(dateIso, density) {
    const events = _calTimedEvents(dateIso);
    const layouts = _calTimedEventLayouts(events, dateIso);
    const todayIso = _localDateIso();
    return `
        <div class="cal-timed-column cal-timed-column--${density}${dateIso === todayIso ? " cal-timed-column--today" : ""}${dateIso === calState.selectedDate ? " cal-timed-column--selected" : ""}" data-cal-date="${dateIso}">
            ${layouts.map((layout) => _calTimedEventBlock(layout.event, density, dateIso, layout)).join("")}
        </div>`;
}

function _calTimedEventBlock(event, density, dateIso, layout = null) {
    const placement = layout?.placement || _calTimedPlacement(event, dateIso);
    const color = _calEventColor(event);
    const compactClass = placement.height < 40 ? " cal-time-event--compact" : "";
    const laneCount = Math.max(1, Number(layout?.laneCount || 1));
    const laneIndex = Math.max(0, Number(layout?.laneIndex || 0));
    const laneClass = laneCount > 1 ? " cal-time-event--overlap" : "";
    const denseClass = laneCount >= 3 ? " cal-time-event--dense-overlap" : "";
    const leftPct = (laneIndex / laneCount) * 100;
    const widthPct = 100 / laneCount;
    const widthInset = laneCount === 1 ? 8 : 6;
    return `
        <button class="cal-time-event cal-time-event--${density}${compactClass}${laneClass}${denseClass}" type="button" data-cal-event-key="${escapeHtml(_calEventKey(event))}" data-cal-event-date="${escapeHtml(dateIso)}" style="--event-color:${color};--event-top:${placement.top}px;--event-height:${placement.height}px;--event-left:calc(${leftPct}% + 4px);--event-width:calc(${widthPct}% - ${widthInset}px)" title="${escapeHtml(event.title || "Untitled")}">
            <span class="cal-time-event-title">${escapeHtml(event.title || "Untitled")}</span>
            <span class="cal-time-event-meta">${escapeHtml(_fmtEventTimeShort(event.start, event.end, event.all_day))}</span>
            ${event.location ? `<span class="cal-time-event-meta">${escapeHtml(event.location)}</span>` : ""}
        </button>`;
}

function _calTimedEventLayouts(events, dateIso) {
    const positioned = _calSortEvents(events).map((event, index) => {
        const placement = _calTimedPlacement(event, dateIso);
        return {
            event,
            placement,
            originalIndex: index,
            top: placement.top,
            bottom: placement.top + placement.height,
            laneIndex: 0,
            laneCount: 1,
        };
    }).sort((first, second) => first.top - second.top || first.bottom - second.bottom || first.originalIndex - second.originalIndex);

    const assignCluster = (cluster) => {
        const laneEnds = [];
        cluster.forEach((item) => {
            let lane = laneEnds.findIndex((end) => end <= item.top + 0.1);
            if (lane === -1) {
                lane = laneEnds.length;
                laneEnds.push(0);
            }
            item.laneIndex = lane;
            laneEnds[lane] = item.bottom;
        });
        cluster.forEach((item) => {
            item.laneCount = Math.max(1, laneEnds.length);
        });
    };

    let cluster = [];
    let clusterEnd = -Infinity;
    positioned.forEach((item) => {
        if (cluster.length && item.top >= clusterEnd) {
            assignCluster(cluster);
            cluster = [];
            clusterEnd = -Infinity;
        }
        cluster.push(item);
        clusterEnd = Math.max(clusterEnd, item.bottom);
    });
    if (cluster.length) assignCluster(cluster);
    return positioned.sort((first, second) => first.top - second.top || first.laneIndex - second.laneIndex || first.originalIndex - second.originalIndex);
}

function _calTimedPlacement(event, dateIso = "") {
    const start = _calDateTimeParts(event.start || "");
    const end = _calDateTimeParts(event.end || event.start || "");
    const fallbackHeight = 44;
    if (!start) return { top: 0, height: fallbackHeight };
    const startIso = _calEventDateIso(event);
    const endIso = _calEventEndDateIso(event) || startIso;
    const startMinutes = dateIso && dateIso > startIso ? 0 : start.hour * 60 + start.minute;
    const rawEndMinutes = end
        ? (dateIso && dateIso < endIso ? 24 * 60 : end.hour * 60 + end.minute)
        : startMinutes + 60;
    const minimumEnd = Math.max(rawEndMinutes, startMinutes + 30);
    const minMinutes = CALENDAR_DAY_START_HOUR * 60;
    const maxMinutes = CALENDAR_DAY_END_HOUR * 60;
    const clampedStart = Math.max(minMinutes, Math.min(startMinutes, maxMinutes));
    const clampedEnd = Math.max(clampedStart + 30, Math.min(minimumEnd, maxMinutes));
    return {
        top: Math.max(0, ((clampedStart - minMinutes) / 60) * CALENDAR_HOUR_HEIGHT),
        height: Math.max(32, ((clampedEnd - clampedStart) / 60) * CALENDAR_HOUR_HEIGHT),
    };
}

function _calDateTimeParts(value) {
    const date = new Date(value || "");
    if (isNaN(date)) return null;
    const timeZone = _displayTimeZone();
    const options = {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        hourCycle: "h23",
    };
    if (timeZone) options.timeZone = timeZone;
    try {
        const parts = new Intl.DateTimeFormat("en-US", options)
            .formatToParts(date)
            .reduce((acc, part) => {
                acc[part.type] = part.value;
                return acc;
            }, {});
        return {
            year: Number(parts.year),
            month: Number(parts.month),
            day: Number(parts.day),
            hour: Number(parts.hour || 0),
            minute: Number(parts.minute || 0),
        };
    } catch {
        return {
            year: date.getFullYear(),
            month: date.getMonth() + 1,
            day: date.getDate(),
            hour: date.getHours(),
            minute: date.getMinutes(),
        };
    }
}

function _calHourLabels() {
    const labels = [];
    for (let hour = CALENDAR_DAY_START_HOUR; hour < CALENDAR_DAY_END_HOUR; hour++) {
        labels.push(new Date(2026, 0, 1, hour, 0, 0).toLocaleTimeString("en-US", { hour: "numeric" }));
    }
    return labels;
}

function _calScheduleHeight() {
    return (CALENDAR_DAY_END_HOUR - CALENDAR_DAY_START_HOUR) * CALENDAR_HOUR_HEIGHT;
}

function _calWireDateButtons(container) {
    container.querySelectorAll("[data-cal-date]").forEach((button) => {
        button.addEventListener("click", () => _calOpenDay(button.dataset.calDate));
    });
}

function _calWireEventClicks(container) {
    container.querySelectorAll("[data-cal-event-key]").forEach((eventNode) => {
        eventNode.addEventListener("click", (clickEvent) => {
            if (clickEvent.target.closest("[data-cal-action], [data-cal-detail-action]")) return;
            clickEvent.stopPropagation();
            _calOpenEvent(eventNode.dataset.calEventKey, eventNode.dataset.calEventDate || "");
        });
        eventNode.addEventListener("keydown", (keyEvent) => {
            if (keyEvent.key === "Enter" || keyEvent.key === " ") {
                keyEvent.preventDefault();
                _calOpenEvent(eventNode.dataset.calEventKey, eventNode.dataset.calEventDate || "");
            }
        });
    });
}

function _calOpenEvent(eventKey, dateIso = "") {
    const event = _calFindEvent(eventKey);
    if (!event) return;
    calState.selectedEventKey = eventKey;
    calState.detailMode = "event";
    const selectedDateIso = dateIso || _calEventDateIso(event);
    if (selectedDateIso) _calSetSelectedDate(selectedDateIso);
    _calRenderAll();
    _calOpenDetailDrawer();
}

function _calOpenDay(dateIso) {
    if (!dateIso) return;
    _calSetSelectedDate(dateIso);
    calState.selectedEventKey = null;
    calState.detailMode = "day";
    _calRenderAll();
    _calOpenDetailDrawer();
}

function _calOpenDetailDrawer() {
    if (typeof openAppDetailDrawer === "function") {
        openAppDetailDrawer("cal-detail-drawer");
    }
}

function _calCloseDetailDrawer() {
    calState.detailMode = null;
    calState.selectedEventKey = null;
    if (typeof closeAppDetailDrawer === "function") {
        closeAppDetailDrawer(resolveAppDisclosureTarget("cal-detail-drawer", ".app-detail-drawer"));
    }
    _calRenderMain();
    _calRenderSidePanel();
}

function _calUpdateDefaults(event) {
    return {
        event_id: _calEventId(event),
        title: event.title || "",
        start: event.start || "",
        end: event.end || "",
        attendees: Array.isArray(event.attendees) ? event.attendees : [],
        location: event.location || "",
        notes: event.notes || "",
        rrule: event.rrule || undefined,
    };
}

function _calRenderColorLegend() {
    const panel = document.getElementById("cal-color-legend");
    if (!panel) return;
    const entries = [];
    const seen = new Set();
    calState.events.forEach((event) => {
        const label = _calEventColorLabel(event);
        const color = _calEventColor(event);
        const key = `${label}|${color}`;
        if (seen.has(key)) return;
        seen.add(key);
        entries.push({ label, color });
    });
    if (!entries.length) {
        panel.innerHTML = "";
        return;
    }
    panel.innerHTML = `
        <details class="cal-color-legend app-advanced-section">
            <summary>
                <span>Color key</span>
                <small>${entries.length} source${entries.length === 1 ? "" : "s"}</small>
            </summary>
            <div class="cal-color-legend-list">
                ${entries.slice(0, 8).map((entry) => `
                    <span class="cal-color-legend-item"><span class="cal-color-swatch" style="background:${entry.color}"></span>${escapeHtml(entry.label)}</span>
                `).join("")}
            </div>
        </details>`;
}

function _calRenderEventDetail() {
    const panel = document.getElementById("cal-detail-drawer-body");
    if (!panel) return;
    if (calState.detailMode === "day") {
        _calRenderDayDetail(panel);
        return;
    }
    const event = calState.selectedEventKey ? _calFindEvent(calState.selectedEventKey) : null;
    if (!event) {
        panel.innerHTML = `
            <header class="app-detail-drawer__head">
                <div>
                    <p class="app-detail-drawer__eyebrow">Calendar</p>
                    <h3 class="app-detail-drawer__title">Details</h3>
                </div>
                <button class="app-detail-drawer__close" type="button" data-cal-detail-close aria-label="Close calendar detail"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg></button>
            </header>`;
        const close = panel.querySelector("[data-cal-detail-close]");
        if (close) close.addEventListener("click", _calCloseDetailDrawer);
        return;
    }
    const manifest = calState.manifest || { actions: [] };
    const eventId = _calEventId(event);
    const canUpdate = _hasAction(manifest, "update_event") && eventId;
    const canDelete = _hasAction(manifest, "delete_event") && eventId;
    const canSetVisibility = _hasAction(manifest, "set_visibility") && eventId;
    const color = _calEventColor(event);
    const attendees = Array.isArray(event.attendees) ? event.attendees : [];
    panel.innerHTML = `
        <section class="cal-event-detail cal-event-detail--drawer" style="--ev-color:${color}">
            <header class="app-detail-drawer__head cal-event-detail-head">
                <div>
                    <p class="app-detail-drawer__eyebrow">${escapeHtml(_calEventColorLabel(event))}</p>
                    <h3 class="app-detail-drawer__title">${escapeHtml(event.title || "Untitled")}</h3>
                </div>
                <button class="app-detail-drawer__close" type="button" data-cal-detail-close aria-label="Close event details"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg></button>
            </header>
            <div class="cal-event-detail-meta">
                <span><strong>When</strong>${escapeHtml(_fmtEventTime(event.start, event.end, event.all_day))}</span>
                ${event.location ? `<span><strong>Where</strong>${escapeHtml(event.location)}</span>` : ""}
                ${attendees.length ? `<span><strong>With</strong>${escapeHtml(attendees.join(", "))}</span>` : ""}
                ${event.visibility ? `<span><strong>Visibility</strong>${escapeHtml(_humanizeLabel(event.visibility))}</span>` : ""}
                ${event.response ? `<span><strong>RSVP</strong>${escapeHtml(_humanizeLabel(event.response))}</span>` : ""}
            </div>
            ${event.notes ? `<p class="cal-event-detail-notes">${escapeHtml(event.notes)}</p>` : ""}
            <div class="cal-event-detail-actions">
                ${canUpdate ? `<button class="view-small-btn view-small-btn--primary" type="button" data-cal-detail-action="update_event">Edit</button>` : ""}
                ${canSetVisibility ? `<button class="view-small-btn" type="button" data-cal-detail-action="set_visibility">Visibility</button>` : ""}
                ${canDelete ? `<button class="view-action-btn view-action-btn--danger" type="button" data-cal-detail-action="delete_event">Remove</button>` : ""}
            </div>
        </section>`;

    const close = panel.querySelector("[data-cal-detail-close]");
    if (close) close.addEventListener("click", _calCloseDetailDrawer);
    panel.querySelectorAll("[data-cal-detail-action]").forEach((button) => {
        button.addEventListener("click", async () => {
            const actionName = button.dataset.calDetailAction;
            if (actionName === "update_event") {
                _openAdapterAction("calendar", manifest, "update_event", _calUpdateDefaults(event));
            } else if (actionName === "set_visibility") {
                _openAdapterAction("calendar", manifest, "set_visibility", { event_id: eventId, visibility: event.visibility || "family" });
            } else if (actionName === "delete_event") {
                await _submitAdapterAction("calendar", "delete_event", { event_id: eventId });
            }
        });
    });
}

function _calRenderDayDetail(panel) {
    const manifest = calState.manifest || { actions: [] };
    const events = _calEventsOnDate(calState.selectedDate);
    panel.innerHTML = `
        <section class="cal-event-detail cal-day-detail--drawer">
            <header class="app-detail-drawer__head cal-event-detail-head">
                <div>
                    <p class="app-detail-drawer__eyebrow">Selected day</p>
                    <h3 class="app-detail-drawer__title">${escapeHtml(_formatDateLabel(calState.selectedDate))}</h3>
                    <span class="cal-selected-count">${events.length} ${events.length === 1 ? "event" : "events"}</span>
                </div>
                <button class="app-detail-drawer__close" type="button" data-cal-detail-close aria-label="Close day details"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg></button>
            </header>
            <div class="cal-event-detail-actions cal-event-detail-actions--top">
                ${_hasAction(manifest, "create_event") ? `<button class="view-small-btn view-small-btn--primary" type="button" id="cal-add-selected">Add event</button>` : ""}
                <button class="view-small-btn" type="button" data-cal-show-day>Open day grid</button>
                <button class="view-small-btn" type="button" data-cal-show-week>Show week grid</button>
            </div>
            <div class="cal-day-events cal-day-events--drawer">
                ${events.length === 0 ? `<p class="muted-empty">No events on this day.</p>` : events.map((event) => _renderCalendarEventRow(event, manifest, calState.selectedDate)).join("")}
            </div>
        </section>`;
    const close = panel.querySelector("[data-cal-detail-close]");
    if (close) close.addEventListener("click", _calCloseDetailDrawer);
    const add = panel.querySelector("#cal-add-selected");
    if (add) {
        add.addEventListener("click", () => _openAdapterAction("calendar", manifest, "create_event", _defaultEventTimes(calState.selectedDate)));
    }
    const showDay = panel.querySelector("[data-cal-show-day]");
    if (showDay) {
        showDay.addEventListener("click", () => {
            calState.viewMode = "day";
            calState.detailMode = null;
            closeAppDetailDrawer(resolveAppDisclosureTarget("cal-detail-drawer", ".app-detail-drawer"));
            _calRefreshForCurrentRange();
        });
    }
    _calWireShowWeek(panel);
    panel.querySelectorAll("[data-cal-action]").forEach((btn) => {
        btn.addEventListener("click", async () => {
            const eventId = btn.dataset.eventId;
            if (!eventId) return;
            await _submitAdapterAction("calendar", btn.dataset.calAction, { event_id: eventId });
        });
    });
    _calWireEventClicks(panel);
}

function _calRenderSelectedDay() {
    const panel = document.getElementById("cal-selected-day");
    if (!panel) return;
    const manifest = calState.manifest || { actions: [] };
    const events = _calEventsOnDate(calState.selectedDate);
    panel.innerHTML = `
        <div class="cal-selected-head">
            <div>
                <p class="cal-side-kicker">Selected Day</p>
                <h3>${escapeHtml(_formatDateLabel(calState.selectedDate))}</h3>
                <span class="cal-selected-count">${events.length} ${events.length === 1 ? "event" : "events"}</span>
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
    _calWireEventClicks(panel);
}

function _renderCalendarEventRow(event, manifest, dateIso = "") {
    const eventId = _idOf(event, "event_id");
    const canDelete = _hasAction(manifest, "delete_event") && eventId;
    const color = _calEventColor(event);
    return `
        <div class="cal-day-event-row" role="button" tabindex="0" data-cal-event-key="${escapeHtml(_calEventKey(event))}"${dateIso ? ` data-cal-event-date="${escapeHtml(dateIso)}"` : ""} style="--ev-color:${color}">
            <div class="cal-day-event-dot" style="background:${color}"></div>
            <div class="cal-day-event-body">
                <p class="cal-day-event-title">${escapeHtml(event.title || "Untitled")}</p>
                <p class="cal-day-event-meta">${escapeHtml(_fmtEventTime(event.start, event.end, event.all_day))}${event.location ? ` · ${escapeHtml(event.location)}` : ""}</p>
                <p class="cal-day-event-source">${escapeHtml(_calEventColorLabel(event))}</p>
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
        const col = _calEventColor(ev);
        const when = _fmtEventTime(ev.start, ev.end, ev.all_day);
        const eventId = _idOf(ev, "event_id");
        return `
            <div class="cal-event-card" role="button" tabindex="0" data-cal-event-key="${escapeHtml(_calEventKey(ev))}" style="--ev-color:${col}">
                <div class="cal-event-card-head">
                    <h4>${escapeHtml(ev.title || "Untitled")}</h4>
                    ${_hasAction(manifest, "delete_event") && eventId ? `<button class="view-action-btn view-action-btn--danger" data-cal-action="delete_event" data-event-id="${escapeHtml(eventId)}">Remove</button>` : ""}
                </div>
                <div class="cal-event-meta">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
                    ${escapeHtml(when)}
                </div>
                <div class="cal-event-meta">
                    <span class="cal-event-source-dot" style="background:${col}"></span>
                    ${escapeHtml(_calEventColorLabel(ev))}
                </div>
                ${ev.actor || ev.created_by ? `
                    <div class="cal-event-meta">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
                        ${escapeHtml(ev.actor || ev.created_by)}
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
    _calWireEventClicks(list);
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
    const timeZone = _displayTimeZone();
    const withTimeZone = (options) => timeZone ? { ...options, timeZone } : options;
    const fmt = (dt) => {
        const d = new Date(dt);
        return isNaN(d) ? dt : d.toLocaleString("en-US", withTimeZone({ weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }));
    };
    return end ? `${fmt(start)} – ${new Date(end).toLocaleTimeString("en-US", withTimeZone({ hour: "numeric", minute: "2-digit" }))}` : fmt(start);
}

function _fmtEventTimeShort(start, end, allDay) {
    if (allDay) return "All day";
    const timeZone = _displayTimeZone();
    const withTimeZone = (options) => timeZone ? { ...options, timeZone } : options;
    const fmt = (dt) => {
        const d = new Date(dt);
        return isNaN(d) ? "" : d.toLocaleTimeString("en-US", withTimeZone({ hour: "numeric", minute: "2-digit" }));
    };
    const startLabel = fmt(start);
    const endLabel = end ? fmt(end) : "";
    if (!startLabel) return _fmtEventTime(start, end, allDay);
    return endLabel ? `${startLabel} - ${endLabel}` : startLabel;
}

// ----------------------------------------------------------------------------
// Tasks view
// ----------------------------------------------------------------------------

function _renderTasksView(viewId, manifest, writeActions, listData) {
    const items = Array.isArray(listData?.tasks) ? listData.tasks : _extractItems(listData);
    const lists = Array.isArray(listData?.lists) ? listData.lists : [];
    const body = dom.viewBody[viewId];
    const actions = new Set((manifest.actions || []).map((action) => action.name));
    const currentMember = _currentMemberActorId();

    if (state.tasksSelectedListId && state.tasksSelectedListId !== "__no_list__" && !lists.some((list) => list.id === state.tasksSelectedListId)) {
        state.tasksSelectedListId = null;
    }
    if (state.tasksSelectedListId === "__no_list__" && !items.some((task) => !task.list_id)) {
        state.tasksSelectedListId = null;
    }
    if (state.tasksSelectedTaskKey && !items.some((task) => _taskKey(task) === state.tasksSelectedTaskKey)) {
        state.tasksSelectedTaskKey = null;
    }
    if (!TASK_VIEW_MODES.includes(state.tasksViewMode)) state.tasksViewMode = "list";
    if (!state.tasksFilter) state.tasksFilter = "now";

    const selectedListId = state.tasksSelectedListId || "__all__";
    const scopedItems = _taskScopeByList(items, selectedListId);
    const active = scopedItems.filter(_taskIsActive);
    const completed = scopedItems.filter((task) => task.status === "done");
    const visibleItems = _taskSortTasks(_taskApplyFilters(scopedItems, state.tasksFilter, state.tasksSearchQuery, currentMember, lists));
    const selectedTask = state.tasksSelectedTaskKey ? items.find((task) => _taskKey(task) === state.tasksSelectedTaskKey) : null;
    const overdue = active.filter(_taskIsOverdue);
    const dueToday = active.filter(_taskIsDueToday);
    const decision = active.filter((task) => _taskNeedsDecision(task, currentMember));
    const nowTasks = _taskNowTasks(scopedItems, currentMember);
    const nextTask = nowTasks[0] || _taskSortTasks(active)[0] || null;
    const high = active.filter((task) => task.priority === "high");
    const filterOptions = _taskFilterOptions(scopedItems, currentMember);
    const primaryFilters = [
        { key: "today", label: "Today", count: dueToday.length, hint: "Due before the day ends" },
        { key: "overdue", label: "Overdue", count: overdue.length, hint: "Needs a reset" },
        { key: "decision", label: "Needs decision", count: decision.length, hint: "Assign, reprioritize, or clear" },
    ];
    const secondaryFilters = filterOptions.filter((filter) => !["now", "today", "overdue", "decision"].includes(filter.key));

    const listCount = (listId) => listId === "__all__"
        ? items.length
        : _taskScopeByList(items, listId).length;

    const renderListButton = (list) => {
        const listId = list.id || "";
        const activeList = listId === selectedListId;
        const color = _taskListColor(list, listId);
        return `
            <button class="task-list-tab${activeList ? " task-list-tab--active" : ""}" data-task-list-id="${escapeHtml(listId)}">
                <span class="task-list-swatch" style="background:${color}"></span>
                <span class="task-list-name">${escapeHtml(list.name || "Untitled list")}</span>
                <span class="task-list-count">${listCount(listId)}</span>
            </button>`;
    };

    body.innerHTML = `
        <div class="task-shell app-page-shell app-density--calm">
            <div class="task-workbench app-workspace${selectedTask ? "" : " app-workspace--single task-workbench--single"}">
                <section class="task-main app-focus-card">
                    <div class="task-focus-stage">
                        <section class="task-next-hero${nextTask ? "" : " task-next-hero--empty"}" style="--task-accent:${nextTask ? _taskAccent(nextTask, lists) : "var(--brand-blue)"}">
                            <div>
                                <p class="task-side-kicker">Next best move</p>
                                <h3>${escapeHtml(nextTask?.title || "Nothing urgent right now")}</h3>
                                <p>${escapeHtml(nextTask ? _taskDueLabel(nextTask, true) : `${completed.length} completed task${completed.length === 1 ? "" : "s"} are tucked away. Add the next real move when it appears.`)}</p>
                                <div class="task-hero-pills">
                                    <span>${escapeHtml(nextTask ? _taskFocusReason(nextTask, currentMember) : "Clear")}</span>
                                    <span>${escapeHtml(nextTask ? _taskListName(lists, nextTask.list_id) : _taskSelectedListLabel(lists, selectedListId))}</span>
                                    ${nextTask?.assigned_to ? `<span>${escapeHtml(_actorDisplay(nextTask.assigned_to).name)}</span>` : ""}
                                </div>
                            </div>
                            <div class="task-next-hero-actions">
                                ${nextTask ? `<button class="view-small-btn view-small-btn--primary" type="button" data-task-key="${escapeHtml(_taskKey(nextTask))}">Details</button>` : ""}
                                ${actions.has("create_task") ? `<button class="view-small-btn" type="button" data-app-action="tasks:create_task">Add task</button>` : ""}
                            </div>
                        </section>
                        <section class="task-now-panel">
                            <header>
                                <p class="task-side-kicker">Today, overdue, decisions</p>
                                <h3>${nowTasks.length ? `${nowTasks.length} to consider` : "All clear"}</h3>
                            </header>
                            <div class="task-signal-grid">
                                ${primaryFilters.map((filter) => `
                                    <button class="task-signal-card${state.tasksFilter === filter.key ? " task-signal-card--active" : ""}" type="button" data-task-filter="${filter.key}">
                                        <span>${escapeHtml(filter.label)}</span>
                                        <strong>${filter.count}</strong>
                                        <small>${escapeHtml(filter.hint)}</small>
                                    </button>
                                `).join("")}
                            </div>
                        </section>
                    </div>

                    <div class="task-toolbar task-toolbar--m4">
                        <div>
                            <p class="task-side-kicker">Task queue</p>
                            <h3>${escapeHtml(_taskSelectedListLabel(lists, selectedListId))}</h3>
                            <p>${visibleItems.length} shown · ${active.length} open · ${completed.length} done</p>
                        </div>
                        <div class="task-toolbar-actions">
                            <details class="task-list-menu">
                                <summary>
                                    <span class="task-list-swatch${selectedListId === "__all__" ? " task-list-swatch--all" : selectedListId === "__no_list__" ? " task-list-swatch--none" : ""}" style="${selectedListId !== "__all__" && selectedListId !== "__no_list__" ? `background:${_taskListColorById(lists, selectedListId)}` : ""}"></span>
                                    <span>${escapeHtml(_taskSelectedListLabel(lists, selectedListId))}</span>
                                    <strong>${listCount(selectedListId)}</strong>
                                </summary>
                                <div class="task-list-menu__panel">
                                    <div class="task-lists-header">
                                        <h3>Lists</h3>
                                        ${actions.has("create_list") ? `<button class="view-small-btn" data-app-action="tasks:create_list">New</button>` : ""}
                                    </div>
                                    <div class="task-list-tabs">
                                        <button class="task-list-tab${selectedListId === "__all__" ? " task-list-tab--active" : ""}" data-task-list-id="__all__">
                                            <span class="task-list-swatch task-list-swatch--all"></span>
                                            <span class="task-list-name">All tasks</span>
                                            <span class="task-list-count">${listCount("__all__")}</span>
                                        </button>
                                        ${lists.map(renderListButton).join("")}
                                        ${items.some((task) => !task.list_id) ? `
                                        <button class="task-list-tab${selectedListId === "__no_list__" ? " task-list-tab--active" : ""}" data-task-list-id="__no_list__">
                                            <span class="task-list-swatch task-list-swatch--none"></span>
                                            <span class="task-list-name">Unlisted</span>
                                            <span class="task-list-count">${listCount("__no_list__")}</span>
                                        </button>` : ""}
                                    </div>
                                </div>
                            </details>
                            <div class="task-view-switch" role="tablist" aria-label="Task view">
                                ${TASK_VIEW_MODES.map((mode) => `
                                    <button class="task-view-switch-btn${state.tasksViewMode === mode ? " task-view-switch-btn--active" : ""}" type="button" role="tab" aria-selected="${state.tasksViewMode === mode ? "true" : "false"}" data-task-view="${mode}">${escapeHtml(_humanizeLabel(mode))}</button>
                                `).join("")}
                            </div>
                            ${actions.has("create_task") ? `<button class="view-small-btn view-small-btn--primary" data-app-action="tasks:create_task">Add task</button>` : ""}
                        </div>
                    </div>

                    <div class="task-filter-summary">
                        <button class="task-now-chip${state.tasksFilter === "now" ? " task-now-chip--active" : ""}" type="button" data-task-filter="now">
                            <span>Now queue</span><strong>${nowTasks.length}</strong>
                        </button>
                        <details class="task-more-filters app-advanced-section">
                            <summary><span>More filters</span><small>${escapeHtml(_taskFilterLabel(filterOptions, state.tasksFilter))}</small></summary>
                            <div class="app-advanced-section__body">
                                <div class="task-filter-row" role="tablist" aria-label="Task filter">
                                    ${secondaryFilters.map((filter) => `
                                        <button class="task-filter-chip${state.tasksFilter === filter.key ? " task-filter-chip--active" : ""}" type="button" data-task-filter="${filter.key}">
                                            <span>${escapeHtml(filter.label)}</span><strong>${filter.count}</strong>
                                        </button>
                                    `).join("")}
                                </div>
                                <label class="task-search-wrap">
                                    <span>Search</span>
                                    <input class="task-search" type="search" data-task-search value="${escapeHtml(state.tasksSearchQuery || "")}" placeholder="Title, person, list">
                                </label>
                            </div>
                        </details>
                    </div>

                    ${_renderTaskSurface(visibleItems, scopedItems, lists, manifest, currentMember)}
                </section>
                ${selectedTask ? `
                    <aside class="task-inspector app-detail-drawer" id="task-inspector">
                        <button class="app-detail-drawer__close task-detail-close" type="button" data-task-close-detail aria-label="Close task details">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                        </button>
                        ${_renderTaskDetail(selectedTask, lists, manifest, currentMember, scopedItems)}
                    </aside>` : ""}
            </div>
        </div>`;

    body.querySelectorAll("[data-task-list-id]").forEach((btn) => {
        btn.addEventListener("click", () => {
            state.tasksSelectedListId = btn.dataset.taskListId === "__all__" ? null : btn.dataset.taskListId;
            state.tasksSelectedTaskKey = null;
            _renderAdapterBody(viewId, "tasks", manifest, writeActions, listData);
        });
    });
    body.querySelectorAll("[data-task-view]").forEach((btn) => {
        btn.addEventListener("click", () => {
            state.tasksViewMode = btn.dataset.taskView || "list";
            _renderAdapterBody(viewId, "tasks", manifest, writeActions, listData);
        });
    });
    body.querySelectorAll("[data-task-filter]").forEach((btn) => {
        btn.addEventListener("click", () => {
            state.tasksFilter = btn.dataset.taskFilter || "open";
            _renderAdapterBody(viewId, "tasks", manifest, writeActions, listData);
        });
    });
    const searchInput = body.querySelector("[data-task-search]");
    if (searchInput) {
        searchInput.addEventListener("input", () => {
            state.tasksSearchQuery = searchInput.value;
            const cursor = searchInput.selectionStart || state.tasksSearchQuery.length;
            window.clearTimeout(state._tasksSearchTimer);
            state._tasksSearchTimer = window.setTimeout(() => {
                _renderAdapterBody(viewId, "tasks", manifest, writeActions, listData);
                const nextInput = dom.viewBody[viewId]?.querySelector("[data-task-search]");
                if (nextInput) {
                    nextInput.focus();
                    nextInput.setSelectionRange(cursor, cursor);
                }
            }, 120);
        });
    }
    body.querySelectorAll("[data-task-action]").forEach((btn) => {
        btn.addEventListener("click", async () => {
            const taskId = btn.dataset.taskId;
            const actionName = btn.dataset.taskAction;
            if (!taskId || !actionName || btn.disabled) return;
            await _submitAdapterAction("tasks", actionName, { task_id: taskId });
        });
    });
    body.querySelectorAll("[data-task-detail-action]").forEach((btn) => {
        btn.addEventListener("click", async () => {
            const task = items.find((item) => _taskKey(item) === btn.dataset.taskKey);
            if (!task) return;
            const taskId = _taskId(task);
            const actionName = btn.dataset.taskDetailAction;
            if (actionName === "update_task") {
                _openAdapterAction("tasks", manifest, "update_task", _taskUpdateDefaults(task));
            } else if (actionName === "reassign_task") {
                _openAdapterAction("tasks", manifest, "reassign_task", { task_id: taskId, new_assignee: task.assigned_to || currentMember });
            } else if (actionName === "complete_task" || actionName === "reopen_task" || actionName === "delete_task") {
                await _submitAdapterAction("tasks", actionName, { task_id: taskId });
            }
        });
    });
    body.querySelectorAll("[data-task-reassign]").forEach((btn) => {
        btn.addEventListener("click", async () => {
            const taskId = btn.dataset.taskId;
            const newAssignee = btn.dataset.taskAssignee;
            if (!taskId || !newAssignee || btn.disabled) return;
            await _submitAdapterAction("tasks", "reassign_task", { task_id: taskId, new_assignee: newAssignee });
        });
    });
    body.querySelectorAll("[data-task-close-detail]").forEach((btn) => {
        btn.addEventListener("click", () => {
            state.tasksSelectedTaskKey = null;
            _renderAdapterBody(viewId, "tasks", manifest, writeActions, listData);
        });
    });
    body.querySelectorAll("[data-task-key]").forEach((node) => {
        node.addEventListener("click", (event) => {
            if (event.target.closest("[data-task-action], [data-task-detail-action], [data-task-reassign]")) return;
            state.tasksSelectedTaskKey = node.dataset.taskKey;
            _renderAdapterBody(viewId, "tasks", manifest, writeActions, listData);
        });
        node.addEventListener("keydown", (event) => {
            if (event.key !== "Enter" && event.key !== " ") return;
            if (event.target.closest("[data-task-action], [data-task-detail-action], [data-task-reassign]")) return;
            event.preventDefault();
            state.tasksSelectedTaskKey = node.dataset.taskKey;
            _renderAdapterBody(viewId, "tasks", manifest, writeActions, listData);
        });
    });
}

function _renderTaskSurface(tasks, scopedItems, lists, manifest, currentMember) {
    if (state.tasksViewMode === "board") return _renderTaskBoard(tasks, lists, manifest);
    if (state.tasksViewMode === "focus") return _renderTaskFocus(tasks, scopedItems, lists, manifest, currentMember);
    return _renderTaskList(tasks, lists, manifest);
}

function _renderTaskList(tasks, lists, manifest) {
    if (!tasks.length) return `<div class="task-empty">${escapeHtml(_taskEmptyMessage())}</div>`;
    const groups = _taskGroupTasks(tasks);
    return `
        <div class="task-list-surface">
            ${groups.map((group) => `
                <section class="task-group">
                    <header class="task-group-head"><h4>${escapeHtml(group.label)}</h4><span>${group.tasks.length}</span></header>
                    <div class="task-rows">
                        ${group.tasks.map((task) => _renderTaskRow(task, lists, manifest)).join("")}
                    </div>
                </section>
            `).join("")}
        </div>`;
}

function _renderTaskBoard(tasks, lists, manifest) {
    const columns = [
        { key: "open", label: "Open" },
        { key: "in_progress", label: "In Progress" },
        { key: "done", label: "Done" },
        { key: "cancelled", label: "Cancelled" },
    ];
    return `
        <div class="task-board">
            ${columns.map((column) => {
                const columnTasks = tasks.filter((task) => (task.status || "open") === column.key);
                return `
                    <section class="task-board-column task-board-column--${column.key}">
                        <header><h4>${escapeHtml(column.label)}</h4><span>${columnTasks.length}</span></header>
                        <div class="task-board-stack">
                            ${columnTasks.length ? columnTasks.map((task) => _renderTaskRow(task, lists, manifest, { compact: true })).join("") : `<p class="task-column-empty">Empty</p>`}
                        </div>
                    </section>`;
            }).join("")}
        </div>`;
}

function _renderTaskFocus(tasks, scopedItems, lists, manifest, currentMember) {
    const sorted = _taskSortTasks(tasks.filter(_taskIsActive));
    const lanes = [
        { label: "Due Now", tasks: sorted.filter((task) => _taskIsOverdue(task) || _taskIsDueToday(task)).slice(0, 6) },
        { label: "High Priority", tasks: sorted.filter((task) => task.priority === "high" && !_taskIsDueToday(task) && !_taskIsOverdue(task)).slice(0, 6) },
        { label: "Mine", tasks: sorted.filter((task) => task.assigned_to === currentMember).slice(0, 6) },
        { label: "Unassigned", tasks: sorted.filter((task) => !task.assigned_to).slice(0, 6) },
    ];
    const allEmpty = lanes.every((lane) => lane.tasks.length === 0);
    if (allEmpty && scopedItems.some((task) => task.status === "done")) {
        return `<div class="task-empty">No active focus work in this scope.</div>`;
    }
    if (allEmpty) return `<div class="task-empty">No focus tasks yet.</div>`;
    return `
        <div class="task-focus-grid">
            ${lanes.map((lane) => `
                <section class="task-focus-lane">
                    <header><h4>${escapeHtml(lane.label)}</h4><span>${lane.tasks.length}</span></header>
                    ${lane.tasks.length ? lane.tasks.map((task) => _renderTaskRow(task, lists, manifest, { compact: true })).join("") : `<p class="task-column-empty">Clear</p>`}
                </section>
            `).join("")}
        </div>`;
}

function _renderTaskRow(task, lists, manifest, options = {}) {
    const taskId = _taskId(task);
    const taskKey = _taskKey(task);
    const done = task.status === "done";
    const cancelled = task.status === "cancelled";
    const selected = state.tasksSelectedTaskKey === taskKey;
    const canComplete = _hasAction(manifest, "complete_task") && taskId && !done && !cancelled;
    const canReopen = _hasAction(manifest, "reopen_task") && taskId && (done || cancelled);
    const canDelete = _hasAction(manifest, "delete_task") && taskId;
    const accent = _taskAccent(task, lists);
    const dueClass = _taskDueClass(task);
    const assignee = task.assigned_to ? _actorDisplay(task.assigned_to) : null;
    return `
        <div class="task-row task-row--${escapeHtml(dueClass)}${done ? " task-row--done" : ""}${cancelled ? " task-row--cancelled" : ""}${selected ? " task-row--selected" : ""}${options.compact ? " task-row--compact" : ""}" role="button" tabindex="0" data-task-key="${escapeHtml(taskKey)}" style="--task-accent:${accent}">
            <button class="task-checkbox${done ? " task-checkbox--checked" : ""}" data-task-action="${done || cancelled ? "reopen_task" : "complete_task"}" data-task-id="${escapeHtml(taskId)}" ${canComplete || canReopen ? "" : "disabled"} aria-label="${done || cancelled ? "Reopen" : "Complete"} ${escapeHtml(task.title || "task")}">
                ${done ? `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>` : ""}
            </button>
            <div class="task-body">
                <div class="task-title-line">
                    <p class="task-title">${escapeHtml(task.title || "Untitled")}</p>
                    ${_taskStatusPill(task)}
                </div>
                <div class="task-meta">
                    <span class="task-meta-item task-meta-item--${dueClass}">${escapeHtml(_taskDueLabel(task))}</span>
                    ${assignee ? `<span class="task-meta-item"><span class="task-avatar" style="background:${assignee.color}">${escapeHtml(assignee.initials)}</span>${escapeHtml(assignee.name)}</span>` : `<span class="task-meta-item">Unassigned</span>`}
                    <span class="task-meta-item"><span class="task-list-dot" style="background:${_taskListColorById(lists, task.list_id)}"></span>${escapeHtml(_taskListName(lists, task.list_id))}</span>
                </div>
            </div>
            <span class="task-priority task-priority--${escapeHtml(task.priority || "medium")}">${escapeHtml(task.priority || "medium")}</span>
            <div class="task-actions">
                ${canReopen ? `<button class="view-action-btn" data-task-action="reopen_task" data-task-id="${escapeHtml(taskId)}">Reopen</button>` : ""}
                ${canDelete ? `<button class="view-action-btn view-action-btn--danger" data-task-action="delete_task" data-task-id="${escapeHtml(taskId)}">Remove</button>` : ""}
            </div>
        </div>`;
}

function _renderTaskDetail(task, lists, manifest, currentMember, scopedItems) {
    if (!task) {
        const focus = scopedItems.filter(_taskIsActive).filter((item) => _taskIsOverdue(item) || _taskIsDueToday(item) || item.priority === "high");
        return `
            <section class="task-detail task-detail--empty">
                <p class="task-side-kicker">Task details</p>
                <h3>No task selected</h3>
                <div class="task-detail-mini-stats">
                    <span><strong>${focus.length}</strong> focus</span>
                    <span><strong>${scopedItems.filter(_taskIsActive).length}</strong> open</span>
                </div>
            </section>`;
    }
    const taskId = _taskId(task);
    const taskKey = _taskKey(task);
    const canComplete = _hasAction(manifest, "complete_task") && taskId && !_taskIsDone(task) && task.status !== "cancelled";
    const canReopen = _hasAction(manifest, "reopen_task") && taskId && (task.status === "done" || task.status === "cancelled");
    const canUpdate = _hasAction(manifest, "update_task") && taskId;
    const canReassign = _hasAction(manifest, "reassign_task") && taskId;
    const canDelete = _hasAction(manifest, "delete_task") && taskId;
    const accent = _taskAccent(task, lists);
    const assignee = task.assigned_to ? _actorDisplay(task.assigned_to) : null;
    const creator = _actorDisplay(task.actor || "system");
    return `
        <section class="task-detail" style="--task-accent:${accent}">
            <header class="task-detail-head">
                <div>
                    <p class="task-side-kicker">${escapeHtml(_taskListName(lists, task.list_id))}</p>
                    <h3>${escapeHtml(task.title || "Untitled")}</h3>
                </div>
                ${_taskStatusPill(task)}
            </header>
            <div class="task-detail-meta">
                <span><strong>Due</strong>${escapeHtml(_taskDueLabel(task, true))}</span>
                <span><strong>Priority</strong>${escapeHtml(_humanizeLabel(task.priority || "medium"))}</span>
                <span><strong>Assigned</strong>${escapeHtml(assignee?.name || "Unassigned")}</span>
                <span><strong>Created By</strong>${escapeHtml(creator.name)}</span>
                ${task.linked_event_id ? `<span><strong>Calendar Link</strong>${escapeHtml(task.linked_event_id)}</span>` : ""}
                ${task.visibility ? `<span><strong>Visibility</strong>${escapeHtml(_humanizeLabel(task.visibility))}</span>` : ""}
            </div>
            ${canReassign ? `
                <div class="task-assignee-strip">
                    ${_taskMembers().map((member) => `
                        <button class="task-assignee-chip${task.assigned_to === member.id ? " task-assignee-chip--active" : ""}" type="button" data-task-reassign data-task-id="${escapeHtml(taskId)}" data-task-assignee="${escapeHtml(member.id)}" ${task.assigned_to === member.id ? "disabled" : ""}>
                            <span style="background:${member.color}">${escapeHtml(member.initials)}</span>${escapeHtml(member.name)}
                        </button>
                    `).join("")}
                </div>` : ""}
            <div class="task-detail-actions">
                ${canComplete ? `<button class="view-small-btn view-small-btn--primary" type="button" data-task-detail-action="complete_task" data-task-key="${escapeHtml(taskKey)}">Mark done</button>` : ""}
                ${canReopen ? `<button class="view-small-btn view-small-btn--primary" type="button" data-task-detail-action="reopen_task" data-task-key="${escapeHtml(taskKey)}">Reopen</button>` : ""}
                ${canUpdate ? `<button class="view-small-btn" type="button" data-task-detail-action="update_task" data-task-key="${escapeHtml(taskKey)}">Edit</button>` : ""}
                ${canReassign ? `<button class="view-small-btn" type="button" data-task-detail-action="reassign_task" data-task-key="${escapeHtml(taskKey)}">Reassign</button>` : ""}
                ${canDelete ? `<button class="view-action-btn view-action-btn--danger" type="button" data-task-detail-action="delete_task" data-task-key="${escapeHtml(taskKey)}">Remove</button>` : ""}
            </div>
        </section>`;
}

function _taskScopeByList(tasks, selectedListId) {
    if (selectedListId === "__all__") return tasks;
    if (selectedListId === "__no_list__") return tasks.filter((task) => !task.list_id);
    return tasks.filter((task) => (task.list_id || "") === selectedListId);
}

function _taskApplyFilters(tasks, filter, query, currentMember, lists) {
    const normalizedQuery = String(query || "").trim().toLowerCase();
    return tasks.filter((task) => {
        if (filter === "now" && !_taskNowTasks(tasks, currentMember).some((item) => _taskKey(item) === _taskKey(task))) return false;
        if (filter === "open" && !_taskIsActive(task)) return false;
        if (filter === "today" && (!_taskIsActive(task) || !_taskIsDueToday(task))) return false;
        if (filter === "overdue" && (!_taskIsActive(task) || !_taskIsOverdue(task))) return false;
        if (filter === "decision" && !_taskNeedsDecision(task, currentMember)) return false;
        if (filter === "high" && (!_taskIsActive(task) || task.priority !== "high")) return false;
        if (filter === "mine" && (!_taskIsActive(task) || task.assigned_to !== currentMember)) return false;
        if (filter === "done" && task.status !== "done") return false;
        if (!normalizedQuery) return true;
        const haystack = [
            task.title,
            task.assigned_to,
            _actorDisplay(task.assigned_to).name,
            task.priority,
            task.status,
            _taskListName(lists, task.list_id),
        ].join(" ").toLowerCase();
        return haystack.includes(normalizedQuery);
    });
}

function _taskFilterOptions(tasks, currentMember) {
    const active = tasks.filter(_taskIsActive);
    return [
        { key: "now", label: "Now", count: _taskNowTasks(tasks, currentMember).length },
        { key: "today", label: "Today", count: active.filter(_taskIsDueToday).length },
        { key: "overdue", label: "Overdue", count: active.filter(_taskIsOverdue).length },
        { key: "decision", label: "Needs decision", count: active.filter((task) => _taskNeedsDecision(task, currentMember)).length },
        { key: "open", label: "Open", count: active.length },
        { key: "high", label: "High", count: active.filter((task) => task.priority === "high").length },
        { key: "mine", label: "Mine", count: active.filter((task) => task.assigned_to === currentMember).length },
        { key: "done", label: "Done", count: tasks.filter((task) => task.status === "done").length },
        { key: "all", label: "All", count: tasks.length },
    ];
}

function _taskNowTasks(tasks, currentMember) {
    return _taskSortTasks(tasks.filter((task) => _taskIsActive(task) && (
        _taskIsDueToday(task) || _taskIsOverdue(task) || _taskNeedsDecision(task, currentMember)
    )));
}

function _taskNeedsDecision(task, currentMember) {
    if (!_taskIsActive(task)) return false;
    return _taskIsOverdue(task)
        || task.priority === "high"
        || !task.assigned_to
        || (task.assigned_to === currentMember && !task.due_at);
}

function _taskFocusReason(task, currentMember) {
    const reasons = [];
    if (_taskIsOverdue(task)) reasons.push("Overdue");
    else if (_taskIsDueToday(task)) reasons.push("Today");
    if (task.priority === "high") reasons.push("High priority");
    if (!task.assigned_to) reasons.push("Unassigned");
    else if (task.assigned_to === currentMember) reasons.push("Yours");
    return reasons.slice(0, 2).join(" · ") || _humanizeLabel(task.status || "open");
}

function _taskFilterLabel(filterOptions, selectedFilter) {
    return filterOptions.find((filter) => filter.key === selectedFilter)?.label || "Now";
}

function _taskEmptyMessage() {
    if (state.tasksFilter === "now") return "No tasks need attention right now.";
    if (state.tasksFilter === "today") return "Nothing is due today.";
    if (state.tasksFilter === "overdue") return "No overdue tasks.";
    if (state.tasksFilter === "decision") return "No tasks need a decision.";
    if (state.tasksFilter === "done") return "No completed tasks in this scope yet.";
    if (state.tasksSearchQuery) return "No tasks match that search.";
    return "No tasks in this view.";
}

function _taskGroupTasks(tasks) {
    const order = ["overdue", "today", "week", "later", "none", "done", "cancelled"];
    const labels = {
        overdue: "Overdue",
        today: "Today",
        week: "Next 7 Days",
        later: "Later",
        none: "No Deadline",
        done: "Completed",
        cancelled: "Cancelled",
    };
    const groups = new Map(order.map((key) => [key, []]));
    tasks.forEach((task) => groups.get(_taskBucket(task)).push(task));
    return order.map((key) => ({ key, label: labels[key], tasks: groups.get(key) })).filter((group) => group.tasks.length);
}

function _taskBucket(task) {
    if (task.status === "done") return "done";
    if (task.status === "cancelled") return "cancelled";
    if (!task.due_at) return "none";
    if (_taskIsOverdue(task)) return "overdue";
    if (_taskIsDueToday(task)) return "today";
    const dueIso = _taskDueDateIso(task);
    const weekEnd = _calAddDays(_localDateIso(), 7);
    return dueIso && dueIso <= weekEnd ? "week" : "later";
}

function _taskSortTasks(tasks) {
    return [...tasks].sort((first, second) => {
        const firstStatus = TASK_STATUS_ORDER[first.status || "open"] ?? 9;
        const secondStatus = TASK_STATUS_ORDER[second.status || "open"] ?? 9;
        if (firstStatus !== secondStatus) return firstStatus - secondStatus;
        const firstPriority = TASK_PRIORITY_ORDER[first.priority || "medium"] ?? 9;
        const secondPriority = TASK_PRIORITY_ORDER[second.priority || "medium"] ?? 9;
        if (firstPriority !== secondPriority) return firstPriority - secondPriority;
        const firstDue = _taskDueMs(first);
        const secondDue = _taskDueMs(second);
        if (firstDue !== secondDue) return firstDue - secondDue;
        return String(first.created_at || "").localeCompare(String(second.created_at || ""));
    });
}

function _taskId(task) {
    return _idOf(task, "task_id");
}

function _taskKey(task) {
    return _taskId(task) || [task.title || "", task.created_at || "", task.assigned_to || ""].join("|");
}

function _taskIsActive(task) {
    return task.status !== "done" && task.status !== "cancelled";
}

function _taskIsDone(task) {
    return task.status === "done";
}

function _taskDueMs(task) {
    if (!task.due_at) return Number.POSITIVE_INFINITY;
    const ms = new Date(task.due_at).getTime();
    return Number.isNaN(ms) ? Number.POSITIVE_INFINITY : ms;
}

function _taskDueDateIso(task) {
    if (!task.due_at) return "";
    const parts = _calDateTimeParts(task.due_at);
    if (!parts) return "";
    return `${parts.year}-${String(parts.month).padStart(2, "0")}-${String(parts.day).padStart(2, "0")}`;
}

function _taskIsDueToday(task) {
    return Boolean(task.due_at && _taskDueDateIso(task) === _localDateIso());
}

function _taskIsOverdue(task) {
    if (!_taskIsActive(task) || !task.due_at) return false;
    const ms = new Date(task.due_at).getTime();
    return Number.isFinite(ms) && ms < Date.now();
}

function _taskDueClass(task) {
    if (!task.due_at) return "none";
    if (_taskIsOverdue(task)) return "overdue";
    if (_taskIsDueToday(task)) return "today";
    return "future";
}

function _taskDueLabel(task, includeExact = false) {
    if (!task.due_at) return "No deadline";
    const date = new Date(task.due_at);
    if (Number.isNaN(date.getTime())) return String(task.due_at);
    const timeZone = _displayTimeZone();
    const withTimeZone = (options) => timeZone ? { ...options, timeZone } : options;
    const relative = _relativeDate(task.due_at);
    const time = date.toLocaleTimeString("en-US", withTimeZone({ hour: "numeric", minute: "2-digit" }));
    if (!includeExact) return `${relative} ${time}`;
    const full = date.toLocaleDateString("en-US", withTimeZone({ weekday: "long", month: "long", day: "numeric", year: "numeric" }));
    return `${full} at ${time}`;
}

function _taskStatusPill(task) {
    const status = task.status || "open";
    return `<span class="task-status task-status--${escapeHtml(status)}">${escapeHtml(_humanizeLabel(status))}</span>`;
}

function _taskListName(lists, listId) {
    if (!listId) return "Unlisted";
    return (lists || []).find((list) => list.id === listId)?.name || "Missing list";
}

function _taskSelectedListLabel(lists, selectedListId) {
    if (selectedListId === "__all__") return "All Tasks";
    if (selectedListId === "__no_list__") return "Unlisted Tasks";
    return _taskListName(lists, selectedListId);
}

function _taskListColorById(lists, listId) {
    const list = (lists || []).find((item) => item.id === listId) || null;
    return _taskListColor(list, listId || "unlisted");
}

function _taskListColor(list, fallbackKey = "") {
    const color = list?.color;
    if (typeof color === "string" && /^#[0-9a-f]{3,8}$/i.test(color.trim())) return color.trim();
    const key = String(fallbackKey || list?.name || "task");
    let hash = 0;
    for (const character of key) hash = ((hash << 5) - hash) + character.charCodeAt(0);
    const palette = ["#2563eb", "#16a34a", "#0d9488", "#dc2626", "#7c3aed", "#0891b2", "#be123c"];
    return palette[Math.abs(hash) % palette.length];
}

function _taskAccent(task, lists) {
    if (task.list_id) return _taskListColorById(lists, task.list_id);
    if (task.assigned_to) {
        const memberColor = _actorDisplay(task.assigned_to).color || _memberColor(task.assigned_to);
        if (memberColor && memberColor !== "#9ca3af") return memberColor;
    }
    if (task.priority === "high") return "#dc2626";
    if (task.priority === "low") return "#16a34a";
    return "#0891b2";
}

function _taskUpdateDefaults(task) {
    return {
        task_id: _taskId(task),
        expected_version: task.version,
        title: task.title || "",
        due_at: task.due_at || "",
        priority: task.priority || "medium",
        list_id: task.list_id || "",
        linked_event_id: task.linked_event_id || "",
    };
}

function _taskMembers() {
    const members = state.family?.members?.length ? state.family.members : _defaultFamily();
    return members.map((member) => {
        const name = member.name || member.actor_id || "Member";
        const id = member.actor_id || name.toLowerCase().replace(/\s+/g, "_");
        const display = _actorDisplay(id);
        return {
            id,
            name: display.name || name,
            initials: display.initials || _initials(name),
            color: display.color || _memberColor(id),
        };
    });
}

// ----------------------------------------------------------------------------
// Shopping view
// ----------------------------------------------------------------------------

function _renderShoppingView(viewId, manifest, writeActions, listData) {
    const body = dom.viewBody[viewId];
    const lists = Array.isArray(listData?.lists) ? listData.lists : [];
    const items = Array.isArray(listData?.items) ? listData.items : [];
    const actions = new Set((manifest.actions || []).map((action) => action.name));
    const currentMember = _currentMemberActorId();

    if (state.shoppingSelectedListId && state.shoppingSelectedListId !== "__all__" && !lists.some((list) => list.id === state.shoppingSelectedListId)) {
        state.shoppingSelectedListId = null;
    }
    if (!state.shoppingSelectedListId) {
        const defaultListId = _shoppingDefaultListId(lists, items);
        if (defaultListId) state.shoppingSelectedListId = defaultListId;
    }
    if (state.shoppingSelectedItemKey && !items.some((item) => _shoppingItemKey(item) === state.shoppingSelectedItemKey)) {
        state.shoppingSelectedItemKey = null;
    }
    if (!SHOPPING_VIEW_MODES.includes(state.shoppingViewMode)) state.shoppingViewMode = "list";
    if (!state.shoppingFilter) state.shoppingFilter = "needed";

    const selectedListId = state.shoppingSelectedListId || "__all__";
    const selectedList = selectedListId === "__all__" ? null : lists.find((list) => list.id === selectedListId) || null;
    const scopedItems = _shoppingScopeByList(items, selectedListId);
    const visibleItems = _shoppingSortItems(_shoppingApplyFilters(scopedItems, state.shoppingFilter, state.shoppingSearchQuery, currentMember, lists));
    const selectedItem = state.shoppingSelectedItemKey ? items.find((item) => _shoppingItemKey(item) === state.shoppingSelectedItemKey) : null;
    const needed = scopedItems.filter(_shoppingIsNeeded);
    const checked = scopedItems.filter((item) => item.status === "checked");
    const pending = scopedItems.filter((item) => item.approval_status === "pending_parent_approval");
    const rejected = scopedItems.filter((item) => item.approval_status === "rejected");
    const high = needed.filter((item) => item.priority === "high");
    const mine = needed.filter((item) => item.requested_by === currentMember);
    const filterOptions = _shoppingFilterOptions(scopedItems, currentMember);
    const selectedListLabel = _shoppingSelectedListLabel(lists, selectedListId);
    const selectedColor = selectedList ? _shoppingCategoryColor(selectedList.category) : "var(--brand-blue)";
    const sortedNeeded = _shoppingSortItems(needed);
    const nextItem = sortedNeeded[0] || null;
    const quickItems = _shoppingQuickItems(selectedList);
    const hasAction = (name) => actions.has(name);
    const addDefaults = _shoppingAddDefaults(lists, items, selectedListId, selectedList);

    const listItems = (listId) => listId === "__all__" ? items : items.filter((item) => item.list_id === listId);

    const renderListButton = (list) => {
        const listId = list.id || "";
        const active = listId === selectedListId;
        const scoped = listItems(listId);
        const count = scoped.length;
        const neededCount = scoped.filter(_shoppingIsNeeded).length;
        const color = _shoppingCategoryColor(list.category);
        return `
            <button class="shopping-list-tab${active ? " shopping-list-tab--active" : ""}" data-shopping-list-id="${escapeHtml(listId)}" style="--shopping-accent:${color}">
                <span class="shopping-list-swatch" style="background:${color}"></span>
                <span class="shopping-list-tab-name">${escapeHtml(list.name || "Untitled list")}</span>
                <span class="shopping-list-tab-meta">${escapeHtml(_humanizeLabel(list.category || "other"))} - ${neededCount} needed</span>
                <span class="shopping-list-tab-count">${count}</span>
            </button>`;
    };

    const signalCards = [
        { key: "needed", label: "Needed", count: needed.length, note: needed.length ? "Ready to buy" : "List is clear" },
        ...(pending.length ? [{ key: "pending", label: "Approvals", count: pending.length, note: "Needs a parent" }] : []),
        ...(high.length ? [{ key: "high", label: "High priority", count: high.length, note: "Do first" }] : []),
        ...(mine.length ? [{ key: "mine", label: "Mine", count: mine.length, note: "Requested by you" }] : []),
        ...(rejected.length ? [{ key: "rejected", label: "Rejected", count: rejected.length, note: "Review later" }] : []),
    ];
    const heroTitle = nextItem
        ? `Pick up ${nextItem.name || "the next item"}`
        : `${selectedListLabel} is clear`;
    const heroCopy = nextItem
        ? `${selectedListLabel} has ${_countPhrase(needed.length, "open item")}${pending.length ? ` and ${_countPhrase(pending.length, "approval")}` : ""}.`
        : scopedItems.length ? `${selectedListLabel} has no open shopping items.` : `${selectedListLabel} is ready for the next item.`;
    const itemDetailPill = nextItem ? (_shoppingQuantityLabel(nextItem) || `${_humanizeLabel(nextItem.priority || "medium")} priority`) : _countPhrase(scopedItems.length, "item");
    const heroPills = [
        selectedListLabel,
        itemDetailPill,
        pending.length ? `${pending.length} approval${pending.length === 1 ? "" : "s"}` : "No approvals waiting",
    ].filter(Boolean);
    const selectedListMeta = selectedList
        ? `${escapeHtml(_humanizeLabel(selectedList.category || "other"))} - ${needed.length} needed`
        : `${needed.length} needed across lists`;

    body.innerHTML = `
        <div class="shopping-shell">
            <div class="shopping-stage">
                <article class="shopping-hero${nextItem ? "" : " shopping-hero--empty"}" style="--shopping-accent:${selectedColor}">
                    <div>
                        <p class="shopping-side-kicker">Active list</p>
                        <h3>${escapeHtml(heroTitle)}</h3>
                        <p>${escapeHtml(heroCopy)}</p>
                        <div class="shopping-hero-pills">
                            ${heroPills.map((pill) => `<span>${escapeHtml(pill)}</span>`).join("")}
                        </div>
                    </div>
                    ${hasAction("add_item") ? `
                        <form class="shopping-quick-add" data-shopping-quick-form>
                            <label>
                                <span>Add quickly</span>
                                <input type="text" data-shopping-quick-input placeholder="Milk, medicine, paper towels" autocomplete="off">
                            </label>
                            <button class="shopping-small-btn shopping-small-btn--primary" type="submit" ${addDefaults.list_id ? "" : "disabled"}>Add</button>
                        </form>
                        <div class="shopping-quick-chips" aria-label="Common shopping items">
                            ${quickItems.map((name) => `<button type="button" data-shopping-quick-name="${escapeHtml(name)}">${escapeHtml(name)}</button>`).join("")}
                        </div>
                    ` : ""}
                    <div class="shopping-hero-actions">
                        ${hasAction("add_item") ? `<button class="shopping-small-btn shopping-small-btn--primary" type="button" data-shopping-add-item ${addDefaults.list_id ? "" : "disabled"}>Add item</button>` : ""}
                        ${nextItem && _hasAction(manifest, "check_off_item") && _shoppingItemId(nextItem) && nextItem.approval_status === "approved" ? `<button class="shopping-small-btn" type="button" data-shopping-action="check_off_item" data-item-id="${escapeHtml(_shoppingItemId(nextItem))}">Check off</button>` : ""}
                    </div>
                </article>
                <aside class="shopping-signal-panel">
                    <div class="shopping-signal-head">
                        <p class="shopping-side-kicker">Signals</p>
                        <strong>${escapeHtml(selectedListLabel)}</strong>
                    </div>
                    <div class="shopping-signal-grid">
                        ${signalCards.map((signal) => `
                            <button class="shopping-signal-card${state.shoppingFilter === signal.key ? " shopping-signal-card--active" : ""}" type="button" data-shopping-filter="${escapeHtml(signal.key)}">
                                <span>${escapeHtml(signal.label)}</span>
                                <strong>${signal.count}</strong>
                                <small>${escapeHtml(signal.note)}</small>
                            </button>
                        `).join("")}
                    </div>
                    <div class="shopping-mode-card">
                        <span>Mode</span>
                        <div class="shopping-view-switch" role="tablist" aria-label="Shopping view">
                            ${SHOPPING_VIEW_MODES.map((mode) => `
                                <button class="shopping-view-switch-btn${state.shoppingViewMode === mode ? " shopping-view-switch-btn--active" : ""}" type="button" role="tab" aria-selected="${state.shoppingViewMode === mode ? "true" : "false"}" data-shopping-view="${mode}">${escapeHtml(_humanizeLabel(mode))}</button>
                            `).join("")}
                        </div>
                    </div>
                </aside>
            </div>
            <div class="shopping-workspace${selectedItem ? " shopping-workspace--with-detail" : " shopping-workspace--single"}">
                <section class="shopping-main shopping-main--m5">
                    <div class="shopping-toolbar shopping-toolbar--m5">
                        <div>
                            <h3>${escapeHtml(selectedListLabel)}</h3>
                            <p>${visibleItems.length} shown - ${needed.length} needed${checked.length ? ` - ${checked.length} checked` : ""}</p>
                        </div>
                        <div class="shopping-toolbar-actions">
                            <details class="shopping-list-menu">
                                <summary style="--shopping-accent:${selectedColor}">
                                    <span class="shopping-list-swatch" style="background:${selectedColor}"></span>
                                    <span>${escapeHtml(selectedListLabel)}</span>
                                    <strong>${needed.length}</strong>
                                </summary>
                                <div class="shopping-list-menu__panel">
                                    <div class="shopping-lists-header">
                                        <div><h3>Lists</h3><p>${selectedListMeta}</p></div>
                                        ${hasAction("create_list") ? `<button class="shopping-small-btn" data-app-action="shopping:create_list">New</button>` : ""}
                                    </div>
                                    <div class="shopping-list-tabs">
                                        <button class="shopping-list-tab${selectedListId === "__all__" ? " shopping-list-tab--active" : ""}" data-shopping-list-id="__all__" style="--shopping-accent:var(--brand-blue)">
                                            <span class="shopping-list-swatch shopping-list-swatch--all"></span>
                                            <span class="shopping-list-tab-name">All shopping</span>
                                            <span class="shopping-list-tab-meta">${items.filter(_shoppingIsNeeded).length} needed across lists</span>
                                            <span class="shopping-list-tab-count">${items.length}</span>
                                        </button>
                                        ${lists.length === 0 ? `<p class="muted-empty">No shopping lists yet.</p>` : lists.map(renderListButton).join("")}
                                    </div>
                                </div>
                            </details>
                            ${hasAction("add_item") ? `<button class="shopping-small-btn shopping-small-btn--primary" type="button" data-shopping-add-item ${addDefaults.list_id ? "" : "disabled"}>Add quickly</button>` : ""}
                        </div>
                    </div>
                    <div class="shopping-filter-summary">
                        <button class="shopping-now-chip${state.shoppingFilter === "needed" ? " shopping-now-chip--active" : ""}" type="button" data-shopping-filter="needed">
                            <span>Needed</span><strong>${needed.length}</strong>
                        </button>
                        <details class="app-advanced-section shopping-more-filters">
                            <summary><span>More filters</span><span>${escapeHtml(_humanizeLabel(state.shoppingFilter || "needed"))}</span></summary>
                            <div class="app-advanced-section__body">
                                <div class="app-filter-row" role="tablist" aria-label="Shopping filter">
                                    ${filterOptions.map((filter) => `
                                        <button class="app-filter-chip${state.shoppingFilter === filter.key ? " app-filter-chip--active" : ""}" type="button" data-shopping-filter="${escapeHtml(filter.key)}">
                                            <span>${escapeHtml(filter.label)}</span><strong>${filter.count}</strong>
                                        </button>
                                    `).join("")}
                                </div>
                                <label class="shopping-search-wrap">
                                    <span>Search</span>
                                    <input class="shopping-search" type="search" data-shopping-search value="${escapeHtml(state.shoppingSearchQuery || "")}" placeholder="Item, list, note">
                                </label>
                            </div>
                        </details>
                    </div>
                    ${_renderShoppingSurface(visibleItems, scopedItems, lists, manifest)}
                </section>
                ${selectedItem ? `<aside class="shopping-inspector shopping-detail-rail" id="shopping-inspector">
                    <button class="app-detail-drawer__close shopping-detail-close" type="button" data-shopping-close-detail aria-label="Close item details">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                    </button>
                    ${_renderShoppingDetail(selectedItem, lists, manifest, currentMember, scopedItems)}
                </aside>` : ""}
            </div>
        </div>`;

    const openAddItem = (name = "") => {
        const defaults = _shoppingAddDefaults(lists, items, selectedListId, selectedList);
        if (!defaults.list_id) {
            showToast("Shopping", "Create or select a list before adding an item.");
            return;
        }
        _openAdapterAction("shopping", manifest, "add_item", { ...defaults, name: String(name || "").trim() });
    };

    body.querySelectorAll("[data-shopping-list-id]").forEach((btn) => {
        btn.addEventListener("click", () => {
            state.shoppingSelectedListId = btn.dataset.shoppingListId === "__all__" ? "__all__" : btn.dataset.shoppingListId;
            state.shoppingSelectedItemKey = null;
            _renderAdapterBody(viewId, "shopping", manifest, writeActions, listData);
        });
    });
    body.querySelectorAll("[data-shopping-view]").forEach((btn) => {
        btn.addEventListener("click", () => {
            state.shoppingViewMode = btn.dataset.shoppingView || "list";
            _renderAdapterBody(viewId, "shopping", manifest, writeActions, listData);
        });
    });
    body.querySelectorAll("[data-shopping-filter]").forEach((btn) => {
        btn.addEventListener("click", () => {
            state.shoppingFilter = btn.dataset.shoppingFilter || "needed";
            _renderAdapterBody(viewId, "shopping", manifest, writeActions, listData);
        });
    });
    body.querySelectorAll("[data-shopping-add-item]").forEach((btn) => {
        btn.addEventListener("click", () => openAddItem());
    });
    const quickForm = body.querySelector("[data-shopping-quick-form]");
    if (quickForm) {
        quickForm.addEventListener("submit", (event) => {
            event.preventDefault();
            const input = quickForm.querySelector("[data-shopping-quick-input]");
            const name = String(input?.value || "").trim();
            if (!name) {
                input?.focus();
                return;
            }
            openAddItem(name);
        });
    }
    body.querySelectorAll("[data-shopping-quick-name]").forEach((btn) => {
        btn.addEventListener("click", () => openAddItem(btn.dataset.shoppingQuickName || ""));
    });
    const searchInput = body.querySelector("[data-shopping-search]");
    if (searchInput) {
        searchInput.addEventListener("input", () => {
            state.shoppingSearchQuery = searchInput.value;
            const cursor = searchInput.selectionStart || state.shoppingSearchQuery.length;
            window.clearTimeout(state._shoppingSearchTimer);
            state._shoppingSearchTimer = window.setTimeout(() => {
                _renderAdapterBody(viewId, "shopping", manifest, writeActions, listData);
                const nextInput = dom.viewBody[viewId]?.querySelector("[data-shopping-search]");
                if (nextInput) {
                    nextInput.focus();
                    nextInput.setSelectionRange(cursor, cursor);
                }
            }, 120);
        });
    }
    const submitShoppingAction = async (btn) => {
        const itemId = btn.dataset.itemId;
        const actionName = btn.dataset.shoppingAction || btn.dataset.shoppingDetailAction;
        if (!itemId || !actionName || btn.disabled) return;
        await _submitAdapterAction("shopping", actionName, { item_id: itemId });
    };
    body.querySelectorAll("[data-shopping-action]").forEach((btn) => {
        btn.addEventListener("click", async () => {
            await submitShoppingAction(btn);
        });
    });
    body.querySelectorAll("[data-shopping-detail-action]").forEach((btn) => {
        btn.addEventListener("click", async () => {
            const item = items.find((candidate) => _shoppingItemKey(candidate) === btn.dataset.shoppingItemKey);
            if (!item) return;
            const itemId = _shoppingItemId(item);
            const actionName = btn.dataset.shoppingDetailAction;
            if (actionName === "update_item") {
                _openAdapterAction("shopping", manifest, "update_item", _shoppingUpdateDefaults(item));
            } else if (actionName === "approve_item" || actionName === "reject_item" || actionName === "check_off_item" || actionName === "delete_item") {
                btn.dataset.itemId = itemId;
                await submitShoppingAction(btn);
            }
        });
    });
    body.querySelectorAll("[data-shopping-item-key]").forEach((node) => {
        node.addEventListener("click", (event) => {
            if (event.target.closest("[data-shopping-action], [data-shopping-detail-action]")) return;
            state.shoppingSelectedItemKey = node.dataset.shoppingItemKey;
            _renderAdapterBody(viewId, "shopping", manifest, writeActions, listData);
        });
        node.addEventListener("keydown", (event) => {
            if (event.key !== "Enter" && event.key !== " ") return;
            if (event.target.closest("[data-shopping-action], [data-shopping-detail-action]")) return;
            event.preventDefault();
            state.shoppingSelectedItemKey = node.dataset.shoppingItemKey;
            _renderAdapterBody(viewId, "shopping", manifest, writeActions, listData);
        });
    });
    body.querySelectorAll("[data-shopping-close-detail]").forEach((btn) => {
        btn.addEventListener("click", () => {
            state.shoppingSelectedItemKey = null;
            _renderAdapterBody(viewId, "shopping", manifest, writeActions, listData);
        });
    });
}

function _renderShoppingSurface(items, scopedItems, lists, manifest) {
    if (state.shoppingViewMode === "aisles") return _renderShoppingAisles(items, lists, manifest);
    if (state.shoppingViewMode === "approval") return _renderShoppingApproval(items, scopedItems, lists, manifest);
    return _renderShoppingList(items, lists, manifest);
}

function _renderShoppingList(items, lists, manifest) {
    if (!items.length) return `<div class="shopping-empty">${escapeHtml(_shoppingEmptyCopy(state.shoppingFilter))}</div>`;
    const groups = _shoppingGroupItems(items);
    return `
        <div class="shopping-list-surface">
            ${groups.map((group) => `
                <section class="shopping-group">
                    <header class="shopping-group-head"><h4>${escapeHtml(group.label)}</h4><span>${group.items.length}</span></header>
                    <div class="shopping-items">
                        ${group.items.map((item) => _renderShoppingRow(item, lists, manifest)).join("")}
                    </div>
                </section>
            `).join("")}
        </div>`;
}

function _renderShoppingAisles(items, lists, manifest) {
    const groups = _shoppingCategoryGroups(items);
    if (!groups.length) return `<div class="shopping-empty">No aisle items match this view.</div>`;
    return `
        <div class="shopping-aisle-grid">
            ${groups.map((group) => `
                <section class="shopping-aisle" style="--shopping-accent:${_shoppingCategoryColor(group.key)}">
                    <header><h4>${escapeHtml(group.label)}</h4><span>${group.items.length}</span></header>
                    ${group.items.map((item) => _renderShoppingRow(item, lists, manifest, { compact: true })).join("")}
                </section>
            `).join("")}
        </div>`;
}

function _renderShoppingApproval(items, scopedItems, lists, manifest) {
    const pending = _shoppingSortItems(scopedItems.filter((item) => item.approval_status === "pending_parent_approval"));
    const rejected = _shoppingSortItems(scopedItems.filter((item) => item.approval_status === "rejected"));
    const approved = _shoppingSortItems(scopedItems.filter((item) => item.approval_status === "approved" && item.status !== "checked")).slice(0, 8);
    return `
        <div class="shopping-approval-grid">
            <section class="shopping-approval-lane shopping-approval-lane--pending">
                <header><h4>Pending Approval</h4><span>${pending.length}</span></header>
                ${pending.length ? pending.map((item) => _renderShoppingRow(item, lists, manifest, { compact: true })).join("") : `<p class="shopping-column-empty">Clear</p>`}
            </section>
            <section class="shopping-approval-lane shopping-approval-lane--approved">
                <header><h4>Ready To Buy</h4><span>${approved.length}</span></header>
                ${approved.length ? approved.map((item) => _renderShoppingRow(item, lists, manifest, { compact: true })).join("") : `<p class="shopping-column-empty">Nothing waiting</p>`}
            </section>
            <section class="shopping-approval-lane shopping-approval-lane--rejected">
                <header><h4>Rejected</h4><span>${rejected.length}</span></header>
                ${rejected.length ? rejected.map((item) => _renderShoppingRow(item, lists, manifest, { compact: true })).join("") : `<p class="shopping-column-empty">None</p>`}
            </section>
        </div>`;
}

function _renderShoppingRow(item, lists, manifest, options = {}) {
    const itemId = _shoppingItemId(item);
    const itemKey = _shoppingItemKey(item);
    const checkedOff = item.status === "checked";
    const pendingApproval = item.approval_status === "pending_parent_approval";
    const rejected = item.approval_status === "rejected";
    const selected = state.shoppingSelectedItemKey === itemKey;
    const quantity = _shoppingQuantityLabel(item);
    const requester = item.requested_by ? _shoppingRequesterDisplay(item.requested_by) : null;
    const canCheck = _hasAction(manifest, "check_off_item") && itemId && !checkedOff && item.approval_status === "approved";
    const canApprove = _hasAction(manifest, "approve_item") && itemId && item.approval_status !== "approved";
    const canReject = _hasAction(manifest, "reject_item") && itemId && pendingApproval;
    const canUpdate = _hasAction(manifest, "update_item") && itemId && !checkedOff;
    const canDelete = _hasAction(manifest, "delete_item") && itemId;
    return `
        <div class="shopping-row${checkedOff ? " shopping-row--checked" : ""}${pendingApproval ? " shopping-row--pending" : ""}${rejected ? " shopping-row--rejected" : ""}${selected ? " shopping-row--selected" : ""}${options.compact ? " shopping-row--compact" : ""}" role="button" tabindex="0" data-shopping-item-key="${escapeHtml(itemKey)}" style="--shopping-accent:${_shoppingItemAccent(item)}">
            <button class="shopping-check${checkedOff ? " shopping-check--checked" : ""}" data-shopping-action="check_off_item" data-item-id="${escapeHtml(itemId)}" ${canCheck ? "" : "disabled"} aria-label="Check off ${escapeHtml(item.name || "item")}">
                ${checkedOff ? `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>` : ""}
            </button>
            <div class="shopping-item-body">
                <div class="shopping-item-title-line">
                    <p class="shopping-item-title">${quantity ? `<span>${escapeHtml(quantity)}</span>` : ""}${escapeHtml(item.name || "Untitled item")}</p>
                    ${_shoppingStatusPill(item)}
                </div>
                <div class="shopping-item-meta">
                    <span><span class="shopping-list-dot" style="background:${_shoppingItemAccent(item)}"></span>${escapeHtml(_humanizeLabel(item.category || "other"))}</span>
                    <span>${escapeHtml(_shoppingListName(lists, item.list_id))}</span>
                    ${requester ? `<span><span class="shopping-avatar" style="background:${requester.color}">${escapeHtml(requester.initials)}</span>${escapeHtml(requester.name)}</span>` : ""}
                    ${item.notes ? `<span class="shopping-note-preview">${escapeHtml(String(item.notes).slice(0, 70))}${String(item.notes).length > 70 ? "..." : ""}</span>` : ""}
                </div>
            </div>
            <span class="shopping-priority shopping-priority--${escapeHtml(item.priority || "medium")}">${escapeHtml(item.priority || "medium")}</span>
            <div class="shopping-actions">
                ${canApprove ? `<button class="shopping-action-btn" data-shopping-action="approve_item" data-item-id="${escapeHtml(itemId)}">Approve</button>` : ""}
                ${canReject ? `<button class="shopping-action-btn" data-shopping-action="reject_item" data-item-id="${escapeHtml(itemId)}">Reject</button>` : ""}
                ${canUpdate ? `<button class="shopping-action-btn" data-shopping-detail-action="update_item" data-shopping-item-key="${escapeHtml(itemKey)}">Edit</button>` : ""}
                ${canDelete ? `<button class="shopping-action-btn shopping-action-btn--danger" data-shopping-action="delete_item" data-item-id="${escapeHtml(itemId)}">Remove</button>` : ""}
            </div>
        </div>`;
}

function _renderShoppingDetail(item, lists, manifest, currentMember, scopedItems) {
    if (!item) {
        const needed = scopedItems.filter(_shoppingIsNeeded);
        const pending = scopedItems.filter((candidate) => candidate.approval_status === "pending_parent_approval");
        return `
            <section class="shopping-detail shopping-detail--empty">
                <p class="shopping-side-kicker">Item details</p>
                <h3>No item selected</h3>
                <div class="shopping-detail-mini-stats">
                    <span><strong>${needed.length}</strong> needed</span>
                    <span><strong>${pending.length}</strong> pending</span>
                </div>
            </section>`;
    }
    const itemId = _shoppingItemId(item);
    const itemKey = _shoppingItemKey(item);
    const requester = item.requested_by ? _shoppingRequesterDisplay(item.requested_by) : null;
    const canCheck = _hasAction(manifest, "check_off_item") && itemId && item.status !== "checked" && item.approval_status === "approved";
    const canApprove = _hasAction(manifest, "approve_item") && itemId && item.approval_status !== "approved";
    const canReject = _hasAction(manifest, "reject_item") && itemId && item.approval_status === "pending_parent_approval";
    const canUpdate = _hasAction(manifest, "update_item") && itemId && item.status !== "checked";
    const canDelete = _hasAction(manifest, "delete_item") && itemId;
    return `
        <section class="shopping-detail" style="--shopping-accent:${_shoppingItemAccent(item)}">
            <header class="shopping-detail-head">
                <div>
                    <p class="shopping-side-kicker">${escapeHtml(_shoppingListName(lists, item.list_id))}</p>
                    <h3>${escapeHtml(item.name || "Untitled item")}</h3>
                </div>
                ${_shoppingStatusPill(item)}
            </header>
            <div class="shopping-detail-meta">
                <span><strong>Quantity</strong>${escapeHtml(_shoppingQuantityLabel(item) || "As needed")}</span>
                <span><strong>Category</strong>${escapeHtml(_humanizeLabel(item.category || "other"))}</span>
                <span><strong>Priority</strong>${escapeHtml(_humanizeLabel(item.priority || "medium"))}</span>
                <span><strong>Requested By</strong>${escapeHtml(requester?.name || item.requested_by || "Family")}</span>
                <span><strong>Approval</strong>${escapeHtml(_humanizeLabel(item.approval_status || "approved"))}</span>
                ${item.checked_at ? `<span><strong>Checked</strong>${escapeHtml(_relativeTimeAgo(item.checked_at))}</span>` : ""}
                ${item.rejection_reason ? `<span><strong>Rejection</strong>${escapeHtml(item.rejection_reason)}</span>` : ""}
            </div>
            ${item.notes ? `<p class="shopping-detail-notes">${escapeHtml(item.notes)}</p>` : ""}
            <div class="shopping-detail-actions">
                ${canCheck ? `<button class="shopping-small-btn shopping-small-btn--primary" type="button" data-shopping-detail-action="check_off_item" data-shopping-item-key="${escapeHtml(itemKey)}">Check off</button>` : ""}
                ${canApprove ? `<button class="shopping-small-btn shopping-small-btn--primary" type="button" data-shopping-detail-action="approve_item" data-shopping-item-key="${escapeHtml(itemKey)}">Approve</button>` : ""}
                ${canReject ? `<button class="shopping-small-btn" type="button" data-shopping-detail-action="reject_item" data-shopping-item-key="${escapeHtml(itemKey)}">Reject</button>` : ""}
                ${canUpdate ? `<button class="shopping-small-btn" type="button" data-shopping-detail-action="update_item" data-shopping-item-key="${escapeHtml(itemKey)}">Edit</button>` : ""}
                ${canDelete ? `<button class="shopping-action-btn shopping-action-btn--danger" type="button" data-shopping-detail-action="delete_item" data-shopping-item-key="${escapeHtml(itemKey)}">Remove</button>` : ""}
            </div>
        </section>`;
}

function _shoppingScopeByList(items, selectedListId) {
    if (selectedListId === "__all__") return items;
    return items.filter((item) => item.list_id === selectedListId);
}

function _shoppingDefaultListId(lists, items) {
    if (!lists.length) return "";
    const neededByList = new Map(lists.map((list) => [list.id, 0]));
    items.forEach((item) => {
        if (!_shoppingIsNeeded(item) || !neededByList.has(item.list_id)) return;
        neededByList.set(item.list_id, neededByList.get(item.list_id) + 1);
    });
    const activeList = [...lists].sort((first, second) => {
        const firstCount = neededByList.get(first.id) || 0;
        const secondCount = neededByList.get(second.id) || 0;
        if (firstCount !== secondCount) return secondCount - firstCount;
        return String(first.name || "").localeCompare(String(second.name || ""));
    })[0];
    return activeList?.id || lists[0]?.id || "";
}

function _shoppingAddDefaults(lists, items, selectedListId = state.shoppingSelectedListId, selectedList = null) {
    const explicitListId = selectedListId && selectedListId !== "__all__" ? selectedListId : "";
    const defaultListId = explicitListId || (lists.length === 1 ? lists[0].id : _shoppingDefaultListId(lists, items));
    const defaultList = selectedList || lists.find((list) => list.id === defaultListId) || null;
    return {
        ...(defaultListId ? { list_id: defaultListId } : {}),
        requested_by: _currentMemberActorId(),
        category: defaultList?.category || "groceries",
        priority: "medium",
    };
}

function _shoppingQuickItems(selectedList) {
    const category = selectedList?.category || "other";
    return SHOPPING_QUICK_ITEMS[category] || SHOPPING_QUICK_ITEMS.other;
}

function _shoppingRequesterDisplay(actorId) {
    const raw = String(actorId || "").toLowerCase();
    if (/concierge|system|kernel|adapter/.test(raw)) return { name: "Family", initials: "F", color: "#2563eb" };
    return _actorDisplay(actorId);
}

function _shoppingEmptyCopy(filter) {
    if (filter === "needed") return "Nothing needed on this list.";
    if (filter === "pending") return "No approvals waiting.";
    if (filter === "high") return "No high-priority items.";
    if (filter === "mine") return "Nothing requested by you here.";
    if (filter === "checked") return "Nothing checked off in this view.";
    if (filter === "rejected") return "No rejected items in this view.";
    return "No shopping items match this view.";
}

function _shoppingApplyFilters(items, filter, query, currentMember, lists) {
    const normalizedQuery = String(query || "").trim().toLowerCase();
    return items.filter((item) => {
        if (filter === "needed" && !_shoppingIsNeeded(item)) return false;
        if (filter === "pending" && item.approval_status !== "pending_parent_approval") return false;
        if (filter === "high" && (!_shoppingIsNeeded(item) || item.priority !== "high")) return false;
        if (filter === "mine" && (!_shoppingIsNeeded(item) || item.requested_by !== currentMember)) return false;
        if (filter === "checked" && item.status !== "checked") return false;
        if (filter === "rejected" && item.approval_status !== "rejected") return false;
        if (!normalizedQuery) return true;
        const requester = _actorDisplay(item.requested_by);
        const haystack = [
            item.name,
            item.quantity,
            item.unit,
            item.category,
            item.notes,
            item.priority,
            item.status,
            item.approval_status,
            item.requested_by,
            requester.name,
            _shoppingListName(lists, item.list_id),
        ].join(" ").toLowerCase();
        return haystack.includes(normalizedQuery);
    });
}

function _shoppingFilterOptions(items, currentMember) {
    const needed = items.filter(_shoppingIsNeeded);
    return [
        { key: "needed", label: "Needed", count: needed.length },
        { key: "pending", label: "Pending", count: items.filter((item) => item.approval_status === "pending_parent_approval").length },
        { key: "high", label: "High", count: needed.filter((item) => item.priority === "high").length },
        { key: "mine", label: "Mine", count: needed.filter((item) => item.requested_by === currentMember).length },
        { key: "checked", label: "Checked", count: items.filter((item) => item.status === "checked").length },
        { key: "rejected", label: "Rejected", count: items.filter((item) => item.approval_status === "rejected").length },
        { key: "all", label: "All", count: items.length },
    ];
}

function _shoppingGroupItems(items) {
    const order = ["pending", "high", "needed", "checked", "rejected"];
    const labels = {
        pending: "Needs Approval",
        high: "High Priority",
        needed: "Needed",
        checked: "Checked Off",
        rejected: "Rejected",
    };
    const groups = new Map(order.map((key) => [key, []]));
    items.forEach((item) => groups.get(_shoppingBucket(item)).push(item));
    return order.map((key) => ({ key, label: labels[key], items: groups.get(key) })).filter((group) => group.items.length);
}

function _shoppingBucket(item) {
    if (item.approval_status === "pending_parent_approval") return "pending";
    if (item.approval_status === "rejected") return "rejected";
    if (item.status === "checked") return "checked";
    if (item.priority === "high") return "high";
    return "needed";
}

function _shoppingCategoryGroups(items) {
    const groups = new Map(SHOPPING_CATEGORY_ORDER.map((category) => [category, []]));
    items.forEach((item) => {
        const category = SHOPPING_CATEGORY_ORDER.includes(item.category) ? item.category : "other";
        groups.get(category).push(item);
    });
    return SHOPPING_CATEGORY_ORDER.map((key) => ({ key, label: _humanizeLabel(key), items: groups.get(key) })).filter((group) => group.items.length);
}

function _shoppingSortItems(items) {
    const priorityOrder = { high: 0, medium: 1, low: 2 };
    const statusOrder = { pending_parent_approval: 0, approved: 1, rejected: 3 };
    return [...items].sort((first, second) => {
        const firstApproval = statusOrder[first.approval_status || "approved"] ?? 9;
        const secondApproval = statusOrder[second.approval_status || "approved"] ?? 9;
        if (firstApproval !== secondApproval) return firstApproval - secondApproval;
        const firstChecked = first.status === "checked" ? 1 : 0;
        const secondChecked = second.status === "checked" ? 1 : 0;
        if (firstChecked !== secondChecked) return firstChecked - secondChecked;
        const firstPriority = priorityOrder[first.priority || "medium"] ?? 9;
        const secondPriority = priorityOrder[second.priority || "medium"] ?? 9;
        if (firstPriority !== secondPriority) return firstPriority - secondPriority;
        const firstCategory = SHOPPING_CATEGORY_ORDER.indexOf(first.category || "other");
        const secondCategory = SHOPPING_CATEGORY_ORDER.indexOf(second.category || "other");
        if (firstCategory !== secondCategory) return firstCategory - secondCategory;
        return String(first.name || "").localeCompare(String(second.name || ""));
    });
}

function _shoppingItemId(item) {
    return _idOf(item, "item_id");
}

function _shoppingItemKey(item) {
    return _shoppingItemId(item) || [item.name || "", item.created_at || "", item.list_id || ""].join("|");
}

function _shoppingIsNeeded(item) {
    return item.status !== "checked" && item.approval_status !== "rejected";
}

function _shoppingQuantityLabel(item) {
    return [item.quantity, item.unit].filter(Boolean).join(" ").trim();
}

function _shoppingListName(lists, listId) {
    if (!listId) return "No list";
    return (lists || []).find((list) => list.id === listId)?.name || "Missing list";
}

function _shoppingSelectedListLabel(lists, selectedListId) {
    if (selectedListId === "__all__") return "All Shopping";
    return _shoppingListName(lists, selectedListId);
}

function _shoppingCategoryColor(category) {
    return SHOPPING_CATEGORY_COLORS[category || "other"] || SHOPPING_CATEGORY_COLORS.other;
}

function _shoppingItemAccent(item) {
    if (item.approval_status === "pending_parent_approval") return "#0891b2";
    if (item.approval_status === "rejected") return "#9ca3af";
    if (item.status === "checked") return "#16a34a";
    return _shoppingCategoryColor(item.category);
}

function _shoppingStatusPill(item) {
    if (item.approval_status === "pending_parent_approval") return `<span class="shopping-status shopping-status--pending">Pending</span>`;
    if (item.approval_status === "rejected") return `<span class="shopping-status shopping-status--rejected">Rejected</span>`;
    if (item.status === "checked") return `<span class="shopping-status shopping-status--checked">Checked</span>`;
    return "";
}

function _shoppingUpdateDefaults(item) {
    return {
        item_id: _shoppingItemId(item),
        name: item.name || "",
        quantity: item.quantity || "",
        unit: item.unit || "",
        category: item.category || "groceries",
        notes: item.notes || "",
        priority: item.priority || "medium",
    };
}

// ----------------------------------------------------------------------------
// Reminders view
// ----------------------------------------------------------------------------

function _renderRemindersView(viewId, manifest, writeActions, listData) {
    const items = _reminderSortReminders(_extractItems(listData));
    const body = dom.viewBody[viewId];
    const actions = new Set((manifest.actions || []).map((action) => action.name));
    const currentMember = _currentMemberActorId();

    if (!REMINDER_VIEW_MODES.includes(state.remindersViewMode)) state.remindersViewMode = "timeline";
    if (!state.remindersFilter) state.remindersFilter = "active";

    if (state.remindersSelectedRecipient) {
        state.remindersSelectedRecipient = _reminderCanonicalMemberId(state.remindersSelectedRecipient);
    }
    const validRecipients = new Set(["__all__", ..._reminderMembers().map((member) => member.id), ...items.map((item) => _reminderRecipientCanonical(item)).filter(Boolean)]);
    if (state.remindersSelectedRecipient && !validRecipients.has(state.remindersSelectedRecipient)) {
        state.remindersSelectedRecipient = null;
    }
    if (state.remindersSelectedKey && !items.some((reminder) => _reminderKey(reminder) === state.remindersSelectedKey)) {
        state.remindersSelectedKey = null;
    }

    const selectedRecipient = state.remindersSelectedRecipient || "__all__";
    const scopedItems = _reminderScopeByRecipient(items, selectedRecipient);
    const active = scopedItems.filter(_reminderIsActive);
    const visibleItems = _reminderSortReminders(_reminderApplyFilters(scopedItems, state.remindersFilter, state.remindersSearchQuery, currentMember));
    const selectedReminder = state.remindersSelectedKey ? items.find((reminder) => _reminderKey(reminder) === state.remindersSelectedKey) : null;
    const attention = scopedItems.filter(_reminderNeedsAttention);
    const dueNow = active.filter((reminder) => _reminderNeedsAttention(reminder) || _reminderIsOverdue(reminder));
    const dueToday = active.filter((reminder) => _reminderIsDueToday(reminder) && !dueNow.includes(reminder));
    const later = active.filter((reminder) => !dueNow.includes(reminder) && !dueToday.includes(reminder));
    const overdue = active.filter(_reminderIsOverdue);
    const snoozed = scopedItems.filter((reminder) => reminder.status === "snoozed");
    const dismissed = scopedItems.filter((reminder) => reminder.status === "dismissed");
    const filterOptions = _reminderFilterOptions(scopedItems, currentMember);
    const recipientOptions = _reminderRecipientOptions(items, currentMember);
    const selectedRecipientOption = recipientOptions.find((recipient) => recipient.id === selectedRecipient) || recipientOptions[0] || { id: "__all__", label: "All reminders", initials: "All", color: "#2563eb", count: scopedItems.length, activeCount: active.length };
    const nextReminder = dueNow[0] || dueToday[0] || later[0] || null;
    const heroTitle = dueNow.length
        ? `${dueNow.length} nudge${dueNow.length === 1 ? "" : "s"} need a reset`
        : nextReminder ? nextReminder.title || "Next reminder" : "No active nudges";
    const heroCopy = dueNow.length
        ? `${_countPhrase(overdue.length, "overdue reminder")}${attention.length ? ` and ${_countPhrase(attention.length, "active alert")}` : ""} are asking for a decision.`
        : nextReminder ? `${_reminderDueLabel(nextReminder, true)} for ${_reminderSelectedRecipientLabel(selectedRecipient).replace("'s Reminders", "")}.` : "The nudge lane is clear for this scope.";
    const heroPills = [
        _reminderSelectedRecipientLabel(selectedRecipient),
        nextReminder ? _reminderDueLabel(nextReminder) : `${active.length} active`,
        dismissed.length ? `${dismissed.length} dismissed tucked away` : "History tucked away",
    ];
    const signalCards = [
        { key: "now", label: "Due now", count: dueNow.length, hint: dueNow.length ? "Needs a reset" : "Clear" },
        { key: "today", label: "Today", count: dueToday.length, hint: dueToday.length ? "Before the day ends" : "No time pressure" },
        { key: "later", label: "Later", count: later.length, hint: later.length ? "Already scheduled" : "Nothing waiting" },
    ];
    const secondaryFilters = filterOptions.filter((filter) => !["active", "now", "today", "later"].includes(filter.key));

    body.innerHTML = `
        <div class="reminder-shell">
            <div class="reminder-stage">
                <article class="reminder-hero${nextReminder ? "" : " reminder-hero--empty"}" style="--reminder-accent:${nextReminder ? _reminderAccent(nextReminder) : "var(--brand-blue)"}">
                    <div>
                        <p class="reminder-side-kicker">Nudge lane</p>
                        <h3>${escapeHtml(heroTitle)}</h3>
                        <p>${escapeHtml(heroCopy)}</p>
                        <div class="reminder-hero-pills">
                            ${heroPills.map((pill) => `<span>${escapeHtml(pill)}</span>`).join("")}
                        </div>
                    </div>
                    <div class="reminder-hero-actions">
                        ${nextReminder ? `<button class="view-small-btn view-small-btn--primary" type="button" data-reminder-key="${escapeHtml(_reminderKey(nextReminder))}">Details</button>` : ""}
                        ${actions.has("create_reminder") ? `<button class="view-small-btn" data-app-action="reminders:create_reminder">Add reminder</button>` : ""}
                    </div>
                </article>
                <aside class="reminder-signal-panel">
                    <div class="reminder-signal-head">
                        <p class="reminder-side-kicker">Due now, today, later</p>
                        <strong>${active.length ? `${active.length} active nudges` : "All clear"}</strong>
                    </div>
                    <div class="reminder-signal-grid">
                        ${signalCards.map((signal) => `
                            <button class="reminder-signal-card${state.remindersFilter === signal.key ? " reminder-signal-card--active" : ""}" type="button" data-reminder-filter="${escapeHtml(signal.key)}">
                                <span>${escapeHtml(signal.label)}</span>
                                <strong>${signal.count}</strong>
                                <small>${escapeHtml(signal.hint)}</small>
                            </button>
                        `).join("")}
                    </div>
                    <div class="reminder-mode-card">
                        <span>Mode</span>
                        <div class="reminder-view-switch" role="tablist" aria-label="Reminder view">
                            ${REMINDER_VIEW_MODES.map((mode) => `
                                <button class="reminder-view-switch-btn${state.remindersViewMode === mode ? " reminder-view-switch-btn--active" : ""}" type="button" role="tab" aria-selected="${state.remindersViewMode === mode ? "true" : "false"}" data-reminder-view="${mode}">${escapeHtml(_humanizeLabel(mode))}</button>
                            `).join("")}
                        </div>
                    </div>
                </aside>
            </div>
            <div class="reminder-workspace${selectedReminder ? " reminder-workspace--with-detail" : " reminder-workspace--single"}">
                <section class="reminder-main reminder-main--m6">
                    <div class="reminder-toolbar reminder-toolbar--m6">
                        <div>
                            <p class="reminder-side-kicker">Reminder queue</p>
                            <h3>${escapeHtml(_reminderSelectedRecipientLabel(selectedRecipient))}</h3>
                            <p>${visibleItems.length} shown - ${active.length} active${dueNow.length ? ` - ${dueNow.length} due now` : ""}</p>
                        </div>
                        <div class="reminder-toolbar-actions">
                            <details class="reminder-recipient-menu">
                                <summary style="--reminder-accent:${selectedRecipientOption.color}">
                                    <span class="reminder-recipient-avatar" style="background:${selectedRecipientOption.color}">${escapeHtml(selectedRecipientOption.initials)}</span>
                                    <span>${escapeHtml(selectedRecipientOption.label)}</span>
                                    <strong>${selectedRecipientOption.activeCount}</strong>
                                </summary>
                                <div class="reminder-recipient-menu__panel">
                                    <div class="reminder-sidebar-head">
                                        <div><h3>Recipients</h3><p>${active.length} active in this scope</p></div>
                                        ${actions.has("create_reminder") ? `<button class="view-small-btn" data-app-action="reminders:create_reminder">New</button>` : ""}
                                    </div>
                                    <div class="reminder-recipient-tabs">
                                        ${recipientOptions.map((recipient) => `
                                            <button class="reminder-recipient-tab${selectedRecipient === recipient.id ? " reminder-recipient-tab--active" : ""}" type="button" data-reminder-recipient="${escapeHtml(recipient.id)}">
                                                <span class="reminder-recipient-avatar" style="background:${recipient.color}">${escapeHtml(recipient.initials)}</span>
                                                <span class="reminder-recipient-copy"><strong>${escapeHtml(recipient.label)}</strong><em>${recipient.activeCount} active</em></span>
                                                <span class="reminder-recipient-count">${recipient.count}</span>
                                            </button>
                                        `).join("")}
                                    </div>
                                </div>
                            </details>
                            ${actions.has("create_reminder") ? `<button class="view-small-btn view-small-btn--primary" data-app-action="reminders:create_reminder">Add reminder</button>` : ""}
                        </div>
                    </div>
                    <div class="reminder-filter-summary">
                        <button class="reminder-now-chip${state.remindersFilter === "active" ? " reminder-now-chip--active" : ""}" type="button" data-reminder-filter="active">
                            <span>Active</span><strong>${active.length}</strong>
                        </button>
                        <details class="app-advanced-section reminder-more-filters">
                            <summary><span>More filters</span><small>${escapeHtml(_reminderFilterLabel(filterOptions, state.remindersFilter))}</small></summary>
                            <div class="app-advanced-section__body">
                                <div class="app-filter-row" role="tablist" aria-label="Reminder filter">
                                    ${secondaryFilters.map((filter) => `
                                        <button class="app-filter-chip${state.remindersFilter === filter.key ? " app-filter-chip--active" : ""}" type="button" data-reminder-filter="${escapeHtml(filter.key)}">
                                            <span>${escapeHtml(filter.label)}</span><strong>${filter.count}</strong>
                                        </button>
                                    `).join("")}
                                </div>
                                <label class="reminder-search-wrap">
                                    <span>Search</span>
                                    <input class="reminder-search" type="search" data-reminder-search value="${escapeHtml(state.remindersSearchQuery || "")}" placeholder="Title, person, trigger">
                                </label>
                            </div>
                        </details>
                    </div>
                    ${_renderReminderSurface(visibleItems, scopedItems, manifest, currentMember)}
                </section>
                ${selectedReminder ? `<aside class="reminder-inspector reminder-detail-rail" id="reminder-inspector">
                    ${_renderReminderDetail(selectedReminder, manifest, currentMember, scopedItems)}
                </aside>` : ""}
            </div>
        </div>`;

    body.querySelectorAll("[data-reminder-recipient]").forEach((btn) => {
        btn.addEventListener("click", () => {
            state.remindersSelectedRecipient = btn.dataset.reminderRecipient === "__all__" ? null : btn.dataset.reminderRecipient;
            state.remindersSelectedKey = null;
            _renderAdapterBody(viewId, "reminders", manifest, writeActions, listData);
        });
    });
    body.querySelectorAll("[data-reminder-view]").forEach((btn) => {
        btn.addEventListener("click", () => {
            state.remindersViewMode = btn.dataset.reminderView || "timeline";
            _renderAdapterBody(viewId, "reminders", manifest, writeActions, listData);
        });
    });
    body.querySelectorAll("[data-reminder-filter]").forEach((btn) => {
        btn.addEventListener("click", () => {
            state.remindersFilter = btn.dataset.reminderFilter || "active";
            _renderAdapterBody(viewId, "reminders", manifest, writeActions, listData);
        });
    });
    const searchInput = body.querySelector("[data-reminder-search]");
    if (searchInput) {
        searchInput.addEventListener("input", () => {
            state.remindersSearchQuery = searchInput.value;
            const cursor = searchInput.selectionStart || state.remindersSearchQuery.length;
            window.clearTimeout(state._remindersSearchTimer);
            state._remindersSearchTimer = window.setTimeout(() => {
                _renderAdapterBody(viewId, "reminders", manifest, writeActions, listData);
                const nextInput = dom.viewBody[viewId]?.querySelector("[data-reminder-search]");
                if (nextInput) {
                    nextInput.focus();
                    nextInput.setSelectionRange(cursor, cursor);
                }
            }, 120);
        });
    }

    const submitReminderAction = async (btn) => {
        const reminderId = btn.dataset.reminderId;
        const actionName = btn.dataset.reminderAction || btn.dataset.reminderDetailAction;
        if (!reminderId || !actionName || btn.disabled) return;
        const params = actionName === "snooze_reminder"
            ? { reminder_id: reminderId, snooze_until: _isoMinutesFromNow(Number(btn.dataset.reminderSnoozeMinutes || 10)) }
            : { reminder_id: reminderId };
        await _submitAdapterAction("reminders", actionName, params);
    };
    body.querySelectorAll("[data-reminder-action]").forEach((btn) => {
        btn.addEventListener("click", async () => {
            await submitReminderAction(btn);
        });
    });
    body.querySelectorAll("[data-reminder-detail-action]").forEach((btn) => {
        btn.addEventListener("click", async () => {
            const reminder = items.find((item) => _reminderKey(item) === btn.dataset.reminderKey);
            if (!reminder) return;
            const reminderId = _reminderId(reminder);
            const actionName = btn.dataset.reminderDetailAction;
            if (actionName === "update_reminder") {
                _openAdapterAction("reminders", manifest, "update_reminder", _reminderUpdateDefaults(reminder));
            } else if (actionName === "snooze_custom") {
                _openAdapterAction("reminders", manifest, "snooze_reminder", { reminder_id: reminderId, snooze_until: _isoMinutesFromNow(30) });
            } else if (actionName === "snooze_reminder" || actionName === "dismiss_reminder" || actionName === "delete_reminder") {
                btn.dataset.reminderId = reminderId;
                await submitReminderAction(btn);
            }
        });
    });
    body.querySelectorAll("[data-reminder-key]").forEach((node) => {
        node.addEventListener("click", (event) => {
            if (event.target.closest("[data-reminder-action], [data-reminder-detail-action]")) return;
            state.remindersSelectedKey = node.dataset.reminderKey;
            _renderAdapterBody(viewId, "reminders", manifest, writeActions, listData);
        });
        node.addEventListener("keydown", (event) => {
            if (event.key !== "Enter" && event.key !== " ") return;
            if (event.target.closest("[data-reminder-action], [data-reminder-detail-action]")) return;
            event.preventDefault();
            state.remindersSelectedKey = node.dataset.reminderKey;
            _renderAdapterBody(viewId, "reminders", manifest, writeActions, listData);
        });
    });
    body.querySelectorAll("[data-reminder-close-detail]").forEach((btn) => {
        btn.addEventListener("click", () => {
            state.remindersSelectedKey = null;
            _renderAdapterBody(viewId, "reminders", manifest, writeActions, listData);
        });
    });
}

function _renderReminderSurface(reminders, scopedItems, manifest, currentMember) {
    if (state.remindersViewMode === "board") return _renderReminderBoard(reminders, manifest);
    if (state.remindersViewMode === "focus") return _renderReminderFocus(reminders, scopedItems, manifest, currentMember);
    return _renderReminderTimeline(reminders, manifest);
}

function _renderReminderTimeline(reminders, manifest) {
    if (!reminders.length) return `<div class="reminder-empty">${escapeHtml(_reminderEmptyMessage())}</div>`;
    const groups = _reminderGroupReminders(reminders);
    return `
        <div class="reminder-timeline-surface">
            ${groups.map((group) => group.key === "dismissed" ? `
                <details class="reminder-group reminder-history-group">
                    <summary class="reminder-group-head"><h4>${escapeHtml(group.label)}</h4><span>${group.reminders.length}</span></summary>
                    <div class="reminder-rows">
                        ${group.reminders.map((reminder) => _renderReminderRow(reminder, manifest)).join("")}
                    </div>
                </details>
            ` : `
                <section class="reminder-group reminder-group--${escapeHtml(group.key)}">
                    <header class="reminder-group-head"><h4>${escapeHtml(group.label)}</h4><span>${group.reminders.length}</span></header>
                    <div class="reminder-rows">
                        ${group.reminders.map((reminder) => _renderReminderRow(reminder, manifest)).join("")}
                    </div>
                </section>
            `).join("")}
        </div>`;
}

function _renderReminderBoard(reminders, manifest) {
    const columns = [
        { key: "fired", label: "Attention" },
        { key: "scheduled", label: "Scheduled" },
        { key: "snoozed", label: "Snoozed" },
        { key: "dismissed", label: "Dismissed" },
    ];
    return `
        <div class="reminder-board">
            ${columns.map((column) => {
                const columnReminders = reminders.filter((reminder) => (reminder.status || "scheduled") === column.key);
                return `
                    <section class="reminder-board-column reminder-board-column--${column.key}">
                        <header><h4>${escapeHtml(column.label)}</h4><span>${columnReminders.length}</span></header>
                        <div class="reminder-board-stack">
                            ${columnReminders.length ? columnReminders.map((reminder) => _renderReminderRow(reminder, manifest, { compact: true })).join("") : `<p class="reminder-column-empty">Empty</p>`}
                        </div>
                    </section>`;
            }).join("")}
        </div>`;
}

function _renderReminderFocus(reminders, scopedItems, manifest, currentMember) {
    const active = _reminderSortReminders(reminders.filter(_reminderIsActive));
    const lanes = [
        { label: "Needs Attention", reminders: active.filter(_reminderNeedsAttention).slice(0, 6) },
        { label: "Due Now", reminders: active.filter(_reminderIsOverdue).slice(0, 6) },
        { label: "Today", reminders: active.filter((reminder) => _reminderIsDueToday(reminder) && !_reminderIsOverdue(reminder)).slice(0, 6) },
        { label: "Mine", reminders: active.filter((reminder) => _reminderRecipientCanonical(reminder) === _reminderCanonicalMemberId(currentMember)).slice(0, 6) },
    ];
    const allEmpty = lanes.every((lane) => lane.reminders.length === 0);
    if (allEmpty && scopedItems.some((reminder) => reminder.status === "dismissed")) {
        return `<div class="reminder-empty">No active reminders in this scope.</div>`;
    }
    if (allEmpty) return `<div class="reminder-empty">No focus reminders yet.</div>`;
    return `
        <div class="reminder-focus-grid">
            ${lanes.map((lane) => `
                <section class="reminder-focus-lane">
                    <header><h4>${escapeHtml(lane.label)}</h4><span>${lane.reminders.length}</span></header>
                    ${lane.reminders.length ? lane.reminders.map((reminder) => _renderReminderRow(reminder, manifest, { compact: true })).join("") : `<p class="reminder-column-empty">Clear</p>`}
                </section>
            `).join("")}
        </div>`;
}

function _renderReminderRow(reminder, manifest, options = {}) {
    const reminderId = _reminderId(reminder);
    const reminderKey = _reminderKey(reminder);
    const status = reminder.status || "scheduled";
    const kind = _reminderKind(reminder);
    const selected = state.remindersSelectedKey === reminderKey;
    const recipient = reminder.recipient ? _actorDisplay(_reminderRecipientCanonical(reminder)) : null;
    const canSnooze = _hasAction(manifest, "snooze_reminder") && reminderId && (status === "fired" || status === "snoozed");
    const canDismiss = _hasAction(manifest, "dismiss_reminder") && reminderId && (status === "fired" || status === "snoozed");
    const canUpdate = _hasAction(manifest, "update_reminder") && reminderId && status === "scheduled";
    const canDelete = _hasAction(manifest, "delete_reminder") && reminderId;
    const message = String(reminder.message || "").trim();
    const dueClass = _reminderDueClass(reminder);
    return `
        <div class="reminder-row reminder-row--${escapeHtml(dueClass)}${selected ? " reminder-row--selected" : ""}${status === "dismissed" ? " reminder-row--muted" : ""}${options.compact ? " reminder-row--compact" : ""}" role="button" tabindex="0" data-reminder-key="${escapeHtml(reminderKey)}" style="--reminder-accent:${_reminderAccent(reminder)}">
            <div class="reminder-icon reminder-icon--${escapeHtml(kind)}">${_reminderKindIcon(kind)}</div>
            <div class="reminder-body">
                <div class="reminder-title-line">
                    <p class="reminder-title">${escapeHtml(reminder.title || "Reminder")}</p>
                    ${_reminderStatusPill(reminder)}
                </div>
                <div class="reminder-meta">
                    <span class="reminder-meta-item reminder-meta-item--${dueClass}">${escapeHtml(_reminderDueLabel(reminder))}</span>
                    ${recipient ? `<span class="reminder-meta-item"><span class="reminder-avatar" style="background:${recipient.color}">${escapeHtml(recipient.initials)}</span>${escapeHtml(recipient.name)}</span>` : ""}
                    <span class="reminder-meta-item">${escapeHtml(_reminderTriggerKindLabel(kind))}</span>
                    ${message ? `<span class="reminder-meta-item reminder-message-preview">${escapeHtml(message.slice(0, 70))}${message.length > 70 ? "..." : ""}</span>` : ""}
                </div>
            </div>
            <div class="reminder-actions">
                ${canSnooze ? `<button class="view-action-btn" data-reminder-action="snooze_reminder" data-reminder-id="${escapeHtml(reminderId)}" data-reminder-snooze-minutes="10">Snooze 10m</button>` : ""}
                ${canDismiss ? `<button class="view-action-btn" data-reminder-action="dismiss_reminder" data-reminder-id="${escapeHtml(reminderId)}">Dismiss</button>` : ""}
                ${canUpdate ? `<button class="view-action-btn" data-reminder-detail-action="update_reminder" data-reminder-key="${escapeHtml(reminderKey)}">Edit</button>` : ""}
                ${canDelete ? `<button class="view-action-btn view-action-btn--danger" data-reminder-action="delete_reminder" data-reminder-id="${escapeHtml(reminderId)}">Remove</button>` : ""}
            </div>
        </div>`;
}

function _renderReminderDetail(reminder, manifest, currentMember, scopedItems) {
    if (!reminder) {
        const active = scopedItems.filter(_reminderIsActive);
        const focus = active.filter((item) => _reminderNeedsAttention(item) || _reminderIsOverdue(item) || _reminderIsDueToday(item));
        return `
            <section class="reminder-detail reminder-detail--empty">
                <p class="reminder-side-kicker">Reminder details</p>
                <h3>No reminder selected</h3>
                <div class="reminder-detail-mini-stats">
                    <span><strong>${focus.length}</strong> focus</span>
                    <span><strong>${active.length}</strong> active</span>
                </div>
            </section>`;
    }
    const reminderId = _reminderId(reminder);
    const reminderKey = _reminderKey(reminder);
    const status = reminder.status || "scheduled";
    const canSnooze = _hasAction(manifest, "snooze_reminder") && reminderId && (status === "fired" || status === "snoozed");
    const canDismiss = _hasAction(manifest, "dismiss_reminder") && reminderId && (status === "fired" || status === "snoozed");
    const canUpdate = _hasAction(manifest, "update_reminder") && reminderId && status === "scheduled";
    const canDelete = _hasAction(manifest, "delete_reminder") && reminderId;
    const recipient = reminder.recipient ? _actorDisplay(_reminderRecipientCanonical(reminder)) : null;
    const creator = _actorDisplay(reminder.actor || "system");
    const triggerDetail = _reminderTriggerDetail(reminder);
    const message = String(reminder.message || "").trim();
    return `
        <section class="reminder-detail" style="--reminder-accent:${_reminderAccent(reminder)}">
            <header class="reminder-detail-head">
                <div>
                    <p class="reminder-side-kicker">${escapeHtml(_reminderTriggerKindLabel(_reminderKind(reminder)))}</p>
                    <h3>${escapeHtml(reminder.title || "Reminder")}</h3>
                </div>
                <button class="reminder-detail-close" type="button" data-reminder-close-detail aria-label="Close reminder details">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                </button>
            </header>
            <div class="reminder-detail-status-row">
                ${_reminderStatusPill(reminder)}
                ${recipient ? `<span class="reminder-detail-recipient"><span style="background:${recipient.color}">${escapeHtml(recipient.initials)}</span>${escapeHtml(recipient.name)}</span>` : ""}
            </div>
            <div class="reminder-detail-meta">
                <span><strong>When</strong>${escapeHtml(_reminderDueLabel(reminder, true))}</span>
                <span><strong>Trigger</strong>${escapeHtml(triggerDetail)}</span>
                <span><strong>Created By</strong>${escapeHtml(creator.name)}</span>
                ${reminder.visibility ? `<span><strong>Visibility</strong>${escapeHtml(_humanizeLabel(reminder.visibility))}</span>` : ""}
                ${reminder.linked_event_id ? `<span><strong>Calendar Link</strong>${escapeHtml(reminder.linked_event_id)}</span>` : ""}
                ${reminder.fired_at ? `<span><strong>Fired</strong>${escapeHtml(_fmtReminderTime(reminder.fired_at))}</span>` : ""}
            </div>
            ${message ? `<p class="reminder-detail-message">${escapeHtml(message)}</p>` : ""}
            ${canSnooze ? `
                <div class="reminder-snooze-strip">
                    ${[10, 30, 60].map((minutes) => `
                        <button class="reminder-snooze-chip" type="button" data-reminder-detail-action="snooze_reminder" data-reminder-key="${escapeHtml(reminderKey)}" data-reminder-snooze-minutes="${minutes}">${minutes < 60 ? `${minutes}m` : "1h"}</button>
                    `).join("")}
                </div>` : ""}
            <div class="reminder-detail-actions">
                ${canUpdate ? `<button class="view-small-btn view-small-btn--primary" type="button" data-reminder-detail-action="update_reminder" data-reminder-key="${escapeHtml(reminderKey)}">Edit</button>` : ""}
                ${canSnooze ? `<button class="view-small-btn" type="button" data-reminder-detail-action="snooze_custom" data-reminder-key="${escapeHtml(reminderKey)}">Snooze...</button>` : ""}
                ${canDismiss ? `<button class="view-small-btn" type="button" data-reminder-detail-action="dismiss_reminder" data-reminder-key="${escapeHtml(reminderKey)}">Dismiss</button>` : ""}
                ${canDelete ? `<button class="view-action-btn view-action-btn--danger" type="button" data-reminder-detail-action="delete_reminder" data-reminder-key="${escapeHtml(reminderKey)}">Remove</button>` : ""}
            </div>
        </section>`;
}

function _reminderScopeByRecipient(reminders, selectedRecipient) {
    if (selectedRecipient === "__all__") return reminders;
    const canonicalRecipient = _reminderCanonicalMemberId(selectedRecipient);
    return reminders.filter((reminder) => _reminderRecipientCanonical(reminder) === canonicalRecipient);
}

function _reminderApplyFilters(reminders, filter, query, currentMember) {
    const normalizedQuery = String(query || "").trim().toLowerCase();
    return reminders.filter((reminder) => {
        if (filter === "active" && !_reminderIsActive(reminder)) return false;
        if (filter === "now" && (!_reminderIsActive(reminder) || !(_reminderNeedsAttention(reminder) || _reminderIsOverdue(reminder)))) return false;
        if (filter === "attention" && !_reminderNeedsAttention(reminder)) return false;
        if (filter === "today" && (!_reminderIsActive(reminder) || !_reminderIsDueToday(reminder) || _reminderNeedsAttention(reminder) || _reminderIsOverdue(reminder))) return false;
        if (filter === "later" && (!_reminderIsActive(reminder) || _reminderNeedsAttention(reminder) || _reminderIsOverdue(reminder) || _reminderIsDueToday(reminder))) return false;
        if (filter === "overdue" && (!_reminderIsActive(reminder) || !_reminderIsOverdue(reminder))) return false;
        if (filter === "mine" && (!_reminderIsActive(reminder) || _reminderRecipientCanonical(reminder) !== _reminderCanonicalMemberId(currentMember))) return false;
        if (filter === "scheduled" && reminder.status !== "scheduled") return false;
        if (filter === "snoozed" && reminder.status !== "snoozed") return false;
        if (filter === "dismissed" && reminder.status !== "dismissed") return false;
        if (!normalizedQuery) return true;
        const canonicalRecipient = _reminderRecipientCanonical(reminder);
        const recipient = _actorDisplay(canonicalRecipient);
        const haystack = [
            reminder.title,
            reminder.message,
            reminder.recipient,
            canonicalRecipient,
            recipient.name,
            reminder.status,
            _reminderTriggerKindLabel(_reminderKind(reminder)),
            _reminderTriggerDetail(reminder),
        ].join(" ").toLowerCase();
        return haystack.includes(normalizedQuery);
    });
}

function _reminderFilterOptions(reminders, currentMember) {
    const active = reminders.filter(_reminderIsActive);
    const canonicalCurrentMember = _reminderCanonicalMemberId(currentMember);
    const now = active.filter((reminder) => _reminderNeedsAttention(reminder) || _reminderIsOverdue(reminder));
    const today = active.filter((reminder) => _reminderIsDueToday(reminder) && !now.includes(reminder));
    return [
        { key: "active", label: "Active", count: active.length },
        { key: "now", label: "Due now", count: now.length },
        { key: "today", label: "Today", count: today.length },
        { key: "later", label: "Later", count: active.filter((reminder) => !now.includes(reminder) && !today.includes(reminder)).length },
        { key: "attention", label: "Attention", count: reminders.filter(_reminderNeedsAttention).length },
        { key: "overdue", label: "Overdue", count: active.filter(_reminderIsOverdue).length },
        { key: "mine", label: "Mine", count: active.filter((reminder) => _reminderRecipientCanonical(reminder) === canonicalCurrentMember).length },
        { key: "scheduled", label: "Scheduled", count: reminders.filter((reminder) => reminder.status === "scheduled").length },
        { key: "snoozed", label: "Snoozed", count: reminders.filter((reminder) => reminder.status === "snoozed").length },
        { key: "dismissed", label: "Dismissed", count: reminders.filter((reminder) => reminder.status === "dismissed").length },
        { key: "all", label: "All", count: reminders.length },
    ];
}

function _reminderFilterLabel(filterOptions, key) {
    return filterOptions.find((filter) => filter.key === key)?.label || _humanizeLabel(key || "active");
}

function _reminderEmptyMessage() {
    const filter = state.remindersFilter || "active";
    if (filter === "active") return "No active nudges in this scope.";
    if (filter === "now") return "Nothing needs a reset right now.";
    if (filter === "today") return "No reminders left for today.";
    if (filter === "later") return "No later reminders in this scope.";
    if (filter === "attention") return "No alerts need attention.";
    if (filter === "overdue") return "No overdue reminders.";
    if (filter === "mine") return "No reminders assigned to you here.";
    if (filter === "dismissed") return "No dismissed reminders in this scope.";
    return "No reminders match this view.";
}

function _reminderGroupReminders(reminders) {
    const order = ["now", "today", "upcoming", "location", "event", "snoozed", "dismissed", "other"];
    const labels = {
        now: "Due Now",
        today: "Today",
        upcoming: "Later",
        location: "Location Triggers",
        event: "Event Linked",
        snoozed: "Snoozed",
        dismissed: "Dismissed",
        other: "Other",
    };
    const groups = new Map(order.map((key) => [key, []]));
    reminders.forEach((reminder) => groups.get(_reminderBucket(reminder)).push(reminder));
    return order.map((key) => ({ key, label: labels[key], reminders: groups.get(key) })).filter((group) => group.reminders.length);
}

function _reminderBucket(reminder) {
    const status = reminder.status || "scheduled";
    const kind = _reminderKind(reminder);
    if (status === "dismissed") return "dismissed";
    if (status === "snoozed") return "snoozed";
    if (status === "fired" || _reminderIsOverdue(reminder)) return "now";
    if (_reminderIsDueToday(reminder)) return "today";
    if (kind === "location_enter" || kind === "location_leave") return "location";
    if (kind === "event_offset") return "event";
    if (_reminderNextAt(reminder)) return "upcoming";
    return "other";
}

function _reminderSortReminders(reminders) {
    return [...reminders].sort((first, second) => {
        const firstStatus = REMINDER_STATUS_ORDER[first.status || "scheduled"] ?? 9;
        const secondStatus = REMINDER_STATUS_ORDER[second.status || "scheduled"] ?? 9;
        if (firstStatus !== secondStatus) return firstStatus - secondStatus;
        const firstDue = _reminderDueMs(first);
        const secondDue = _reminderDueMs(second);
        if (firstDue !== secondDue) return firstDue - secondDue;
        return String(first.created_at || "").localeCompare(String(second.created_at || ""));
    });
}

function _reminderId(reminder) {
    return _idOf(reminder, "reminder_id");
}

function _reminderKey(reminder) {
    return _reminderId(reminder) || [reminder.title || "", reminder.created_at || "", reminder.recipient || ""].join("|");
}

function _reminderIsActive(reminder) {
    return (reminder.status || "scheduled") !== "dismissed";
}

function _reminderNeedsAttention(reminder) {
    return (reminder.status || "scheduled") === "fired";
}

function _reminderNextAt(reminder) {
    if ((reminder.status || "scheduled") === "snoozed" && reminder.snoozed_until) return reminder.snoozed_until;
    return reminder.trigger?.fire_at || reminder.fire_at || "";
}

function _reminderDueMs(reminder) {
    const nextAt = _reminderNextAt(reminder);
    if (!nextAt) return Number.POSITIVE_INFINITY;
    const ms = new Date(nextAt).getTime();
    return Number.isNaN(ms) ? Number.POSITIVE_INFINITY : ms;
}

function _reminderIsDueToday(reminder) {
    const nextAt = _reminderNextAt(reminder);
    if (!nextAt) return false;
    const parts = _calDateTimeParts(nextAt);
    if (!parts) return false;
    const dateIso = `${parts.year}-${String(parts.month).padStart(2, "0")}-${String(parts.day).padStart(2, "0")}`;
    return dateIso === _localDateIso();
}

function _reminderIsOverdue(reminder) {
    const status = reminder.status || "scheduled";
    if (status !== "scheduled" && status !== "snoozed") return false;
    const dueMs = _reminderDueMs(reminder);
    return Number.isFinite(dueMs) && dueMs < Date.now();
}

function _reminderDueClass(reminder) {
    const status = reminder.status || "scheduled";
    if (status === "fired") return "attention";
    if (status === "dismissed") return "dismissed";
    if (status === "snoozed") return _reminderIsOverdue(reminder) ? "overdue" : "snoozed";
    if (_reminderIsOverdue(reminder)) return "overdue";
    if (_reminderIsDueToday(reminder)) return "today";
    if (_reminderNextAt(reminder)) return "future";
    return _reminderKind(reminder);
}

function _reminderDueLabel(reminder, includeExact = false) {
    const status = reminder.status || "scheduled";
    if (status === "fired") return reminder.fired_at ? `Fired ${_relativeTimeAgo(reminder.fired_at)}` : "Needs attention";
    if (status === "dismissed") return reminder.fired_at ? `Dismissed after ${_fmtReminderTime(reminder.fired_at)}` : "Dismissed";
    const nextAt = _reminderNextAt(reminder);
    if (nextAt) {
        const prefix = status === "snoozed" ? "Snoozed until " : "";
        if (includeExact) return `${prefix}${_fmtReminderTime(nextAt)}`;
        const date = new Date(nextAt);
        if (Number.isNaN(date.getTime())) return `${prefix}${nextAt}`;
        const relative = _relativeDate(nextAt);
        const timeZone = _displayTimeZone();
        const time = date.toLocaleTimeString("en-US", timeZone ? { hour: "numeric", minute: "2-digit", timeZone } : { hour: "numeric", minute: "2-digit" });
        return `${prefix}${relative} ${time}`;
    }
    return _reminderTriggerDetail(reminder);
}

function _reminderKind(reminder) {
    return reminder.trigger?.kind || (reminder.fire_at ? "time" : "time");
}

function _reminderTriggerKindLabel(kind) {
    if (kind === "time") return "Time";
    if (kind === "location_enter") return "Arrive";
    if (kind === "location_leave") return "Leave";
    if (kind === "event_offset") return "Event";
    return _humanizeLabel(kind || "reminder");
}

function _reminderTriggerDetail(reminder) {
    const trigger = reminder.trigger || {};
    const kind = _reminderKind(reminder);
    if (kind === "time") return trigger.fire_at ? _fmtReminderTime(trigger.fire_at) : "Time reminder";
    if (kind === "location_enter" || kind === "location_leave") {
        const label = _reminderLocationLabel(trigger.location);
        return `${kind === "location_enter" ? "Arrive at" : "Leave"} ${label}`;
    }
    if (kind === "event_offset") {
        const offset = Number(trigger.offset_minutes || 0);
        const when = offset === 0 ? "At event time" : `${Math.abs(offset)} minutes ${offset < 0 ? "before" : "after"}`;
        return trigger.event_id ? `${when} (${trigger.event_id})` : when;
    }
    return _reminderTriggerLabel(trigger) || "Reminder trigger";
}

function _reminderLocationLabel(location) {
    if (!location || typeof location !== "object") return "location";
    if (location.name || location.label) return location.name || location.label;
    const lat = location.lat ?? location.latitude;
    const lon = location.lon ?? location.lng ?? location.longitude;
    if (lat !== undefined && lon !== undefined) return `${lat}, ${lon}`;
    return "location";
}

function _reminderStatusPill(reminder) {
    const status = reminder.status || "scheduled";
    return `<span class="reminder-status reminder-status--${escapeHtml(status)}">${escapeHtml(_humanizeLabel(status))}</span>`;
}

function _memberRefSlug(value) {
    return String(value || "").trim().toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
}

function _reminderIsKnownMemberId(value) {
    const slug = _memberRefSlug(value);
    if (!slug) return false;
    return _reminderMembers().some((member) => _memberRefSlug(member.id) === slug);
}

function _reminderCanonicalMemberId(value, fallbackId = "") {
    const raw = String(value || "").trim();
    if (!raw) return fallbackId;
    const slug = _memberRefSlug(raw);
    if (["user", "me", "self", "myself", "current_user", "current_member"].includes(slug)) {
        return fallbackId || _currentMemberActorId();
    }
    const members = _reminderMembers();
    const direct = members.find((member) =>
        _memberRefSlug(member.id) === slug || _memberRefSlug(member.label) === slug
    );
    if (direct) return direct.id;
    for (const [name, meta] of Object.entries(MEMBERS)) {
        if (_memberRefSlug(name) === slug || _memberRefSlug(meta.key) === slug) {
            const familyMember = (state.family?.members || []).find((member) => member.name === name);
            return familyMember?.actor_id || meta.key || slug;
        }
    }
    return raw;
}

function _reminderRecipientCanonical(reminder) {
    const actorCanonical = _reminderCanonicalMemberId(reminder?.actor || "");
    const fallback = _reminderIsKnownMemberId(actorCanonical) ? actorCanonical : _currentMemberActorId();
    return _reminderCanonicalMemberId(reminder?.recipient || "", fallback);
}

function _reminderRecipientOptions(reminders, currentMember) {
    const memberOptions = _reminderMembers();
    const known = new Set(memberOptions.map((member) => member.id));
    const extraRecipients = Array.from(new Set(reminders.map((reminder) => _reminderRecipientCanonical(reminder)).filter(Boolean).filter((recipient) => !known.has(recipient))));
    const allOptions = [
        { id: "__all__", label: "All reminders", initials: "All", color: "#2563eb" },
        ...memberOptions,
        ...extraRecipients.map((recipient) => {
            const display = _actorDisplay(recipient);
            return { id: recipient, label: display.name, initials: display.initials, color: display.color };
        }),
    ];
    return allOptions.map((option) => {
        const canonicalOption = option.id === "__all__" ? option.id : _reminderCanonicalMemberId(option.id);
        const scoped = canonicalOption === "__all__" ? reminders : reminders.filter((reminder) => _reminderRecipientCanonical(reminder) === canonicalOption);
        const label = canonicalOption === _reminderCanonicalMemberId(currentMember) ? `${option.label} (you)` : option.label;
        return {
            ...option,
            id: canonicalOption,
            label,
            count: scoped.length,
            activeCount: scoped.filter(_reminderIsActive).length,
        };
    });
}

function _reminderSelectedRecipientLabel(selectedRecipient) {
    if (selectedRecipient === "__all__") return "All Reminders";
    const display = _actorDisplay(_reminderCanonicalMemberId(selectedRecipient));
    return `${display.name}'s Reminders`;
}

function _reminderMembers() {
    const members = state.family?.members?.length ? state.family.members : _defaultFamily();
    return members.map((member) => {
        const name = member.name || member.actor_id || "Member";
        const id = member.actor_id || name.toLowerCase().replace(/\s+/g, "_");
        const display = _actorDisplay(id);
        return {
            id,
            label: display.name || name,
            initials: display.initials || _initials(name),
            color: display.color || _memberColor(id),
        };
    });
}

function _reminderAccent(reminder) {
    const status = reminder.status || "scheduled";
    if (status === "fired") return "#e11d48";
    if (status === "dismissed") return "#9ca3af";
    if (status === "snoozed") return "#0891b2";
    const canonicalRecipient = _reminderRecipientCanonical(reminder);
    const memberColor = canonicalRecipient ? _actorDisplay(canonicalRecipient).color || _memberColor(canonicalRecipient) : "";
    if (memberColor && memberColor !== "#9ca3af") return memberColor;
    const kind = _reminderKind(reminder);
    if (kind === "location_enter" || kind === "location_leave") return "#16a34a";
    if (kind === "event_offset") return "#7c3aed";
    return "#2563eb";
}

function _reminderUpdateDefaults(reminder) {
    return {
        reminder_id: _reminderId(reminder),
        title: reminder.title || "",
        message: reminder.message || "",
        trigger: reminder.trigger || { kind: "time", fire_at: _reminderNextAt(reminder) || _isoMinutesFromNow(60) },
    };
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
    if (diff > 0 && diff < 86_400_000) return `in ${Math.max(1, Math.round(diff / 60_000))}m`;
    const timeZone = _displayTimeZone();
    const options = { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" };
    return d.toLocaleString("en-US", timeZone ? { ...options, timeZone } : options);
}

// ----------------------------------------------------------------------------
// Chores view
// ----------------------------------------------------------------------------

function _renderChoresView(viewId, manifest, writeActions, listData) {
    const items = Array.isArray(listData?.chores) ? listData.chores : _extractItems(listData);
    const summary = Array.isArray(listData?.summary) ? listData.summary : [];
    const body = dom.viewBody[viewId];
    const actions = new Set((manifest.actions || []).map((action) => action.name));

    if (!CHORE_VIEW_MODES.includes(state.choresViewMode)) state.choresViewMode = "today";
    if (!state.choresSelectedAssignee) state.choresSelectedAssignee = "__all__";
    if (state.choresSelectedAssignee !== "__all__") state.choresSelectedAssignee = _choreCanonicalAssigneeId(state.choresSelectedAssignee);
    if (!state.choresFilter) state.choresFilter = "pending";
    if (state.choresSelectedKey && !items.some((chore) => _choreKey(chore) === state.choresSelectedKey)) {
        state.choresSelectedKey = null;
    }

    const selectedAssignee = state.choresSelectedAssignee || "__all__";
    const scopedItems = selectedAssignee === "__all__"
        ? items
        : items.filter((chore) => _choreAssigneeId(chore) === selectedAssignee);
    const pending = scopedItems.filter((chore) => _choreStatus(chore) === "pending");
    const visibleItems = _choreSort(_choreApplyFilters(scopedItems, state.choresFilter, state.choresSearchQuery));
    if (state.choresSelectedKey && !scopedItems.some((chore) => _choreKey(chore) === state.choresSelectedKey)) {
        state.choresSelectedKey = null;
    }
    const done = scopedItems.filter((chore) => _choreStatus(chore) === "done");
    const skipped = scopedItems.filter((chore) => _choreStatus(chore) === "skipped");
    const dueNow = pending.filter((chore) => _choreIsDueNow(chore));
    const upcoming = pending.filter((chore) => !_choreIsDueNow(chore));
    const overdue = pending.filter(_choreIsOverdue);
    const points = done.reduce((total, chore) => total + Number(chore.points_awarded || 0), 0);
    const hasSearchQuery = String(state.choresSearchQuery || "").trim().length > 0;
    const todayScopedItems = hasSearchQuery ? _choreSort(_choreApplyFilters(scopedItems, "all", state.choresSearchQuery)) : scopedItems;
    const todayPending = todayScopedItems.filter((chore) => _choreStatus(chore) === "pending");
    const todayDone = todayScopedItems.filter((chore) => _choreStatus(chore) === "done");
    const todayDueNow = todayPending.filter((chore) => _choreIsDueNow(chore));
    const todayUpcoming = todayPending.filter((chore) => !_choreIsDueNow(chore));
    const recentDone = _choreSort(todayDone).slice(0, 4);
    const todaySelectionItems = state.choresViewMode === "today" && (state.choresFilter || "pending") === "pending"
        ? [...todayDueNow, ...todayUpcoming, ...recentDone]
        : visibleItems;
    if (state.choresSelectedKey && !todaySelectionItems.some((chore) => _choreKey(chore) === state.choresSelectedKey)) {
        state.choresSelectedKey = null;
    }
    const selectedChore = state.choresSelectedKey
        ? scopedItems.find((chore) => _choreKey(chore) === state.choresSelectedKey) || null
        : null;
    const assigneeBuckets = _choreAssigneeBuckets(items, summary);
    const filterOptions = _choreFilterOptions(scopedItems);
    const selectedBucket = assigneeBuckets.find((bucket) => bucket.id === selectedAssignee) || assigneeBuckets[0];
    const selectedLabel = _choreSelectedAssigneeLabel(assigneeBuckets, selectedAssignee);
    const nextChore = _choreSort(todayPending)[0] || null;
    const rhythmCount = todayDueNow.length + todayUpcoming.length;
    const todayDisplayedCount = (state.choresFilter || "pending") === "pending" ? todayDueNow.length + todayUpcoming.length + recentDone.length : visibleItems.length;
    const displayedCount = state.choresViewMode === "today" ? todayDisplayedCount : visibleItems.length;
    const signalPoints = todayDone.reduce((total, chore) => total + Number(chore.points_awarded || 0), 0);
    const heroTitle = nextChore ? nextChore.title || "Next chore" : "Chores are clear today";
    const heroCopy = nextChore
        ? `${selectedLabel} has ${_countPhrase(rhythmCount, "open chore")}. ${_choreDueLabel(nextChore)}.`
        : hasSearchQuery && !todayDone.length
            ? `No chores match this search in ${selectedLabel}.`
            : `${todayDone.length ? _countPhrase(todayDone.length, "finished chore") : "No chores"} in this scope and nothing calling for attention.`;
    const heroPills = [
        selectedLabel,
        todayDueNow.length ? `${todayDueNow.length} due now` : "Nothing due now",
        todayDone.length ? `${todayDone.length} done` : "No wins yet",
    ];
    const primarySignals = [
        { key: "due_now", label: "Due now", count: todayDueNow.length, hint: todayDueNow.length ? "Needs doing" : "Clear" },
        { key: "upcoming", label: "Upcoming", count: todayUpcoming.length, hint: todayUpcoming.length ? "Next rhythm" : "Nothing waiting" },
        { key: "done", label: "Done", count: todayDone.length, hint: todayDone.length ? `${signalPoints} points` : "No wins yet" },
    ];
    const filtersExpanded = hasSearchQuery || (state.choresFilter || "pending") !== "pending";

    body.innerHTML = `
        <div class="chore-shell">
            <div class="chore-stage">
                <article class="chore-hero${nextChore ? "" : " chore-hero--clear"}" style="--chore-accent:${nextChore ? _choreAccent(nextChore) : selectedBucket?.color || "var(--brand-blue)"}">
                    <div>
                        <p class="chore-side-kicker">Today in chores</p>
                        <h3>${escapeHtml(heroTitle)}</h3>
                        <p>${escapeHtml(heroCopy)}</p>
                        <div class="chore-hero-pills">
                            ${heroPills.map((pill) => `<span>${escapeHtml(pill)}</span>`).join("")}
                        </div>
                    </div>
                    <div class="chore-hero-actions">
                        ${nextChore ? `<button class="view-small-btn view-small-btn--primary" type="button" data-chore-select-key="${escapeHtml(_choreKey(nextChore))}">Details</button>` : ""}
                        ${nextChore && _hasAction(manifest, "complete_chore") && _choreOccurrenceId(nextChore) ? `<button class="view-small-btn" type="button" data-chore-action="complete_chore" data-occurrence-id="${escapeHtml(_choreOccurrenceId(nextChore))}">Done</button>` : ""}
                        ${actions.has("create_template") ? `<button class="view-small-btn" data-app-action="chores:create_template">New template</button>` : ""}
                    </div>
                </article>
                <aside class="chore-rhythm-panel">
                    <header>
                        <p class="chore-side-kicker">Rhythm</p>
                        <h3>${rhythmCount ? `${rhythmCount} still moving` : "All clear"}</h3>
                    </header>
                    <div class="chore-signal-grid">
                        ${primarySignals.map((signal) => `
                            <button class="chore-signal-card${state.choresFilter === signal.key ? " chore-signal-card--active" : ""}" type="button" data-chore-filter="${escapeHtml(signal.key)}">
                                <span>${escapeHtml(signal.label)}</span>
                                <strong>${signal.count}</strong>
                                <small>${escapeHtml(signal.hint)}</small>
                            </button>
                        `).join("")}
                    </div>
                    <div class="chore-mode-card">
                        <span>Mode</span>
                        <div class="chore-view-switch" role="tablist" aria-label="Chores view">
                            ${CHORE_VIEW_MODES.map((mode) => `
                                <button class="chore-view-switch-btn${state.choresViewMode === mode ? " chore-view-switch-btn--active" : ""}" type="button" role="tab" aria-selected="${state.choresViewMode === mode ? "true" : "false"}" data-chore-view="${mode}">${escapeHtml(_humanizeLabel(mode))}</button>
                            `).join("")}
                        </div>
                    </div>
                </aside>
            </div>
            <div class="chore-workspace${selectedChore ? " chore-workspace--with-detail" : " chore-workspace--single"}">
                <section class="chore-main chore-main--m7">
                    <div class="chore-toolbar chore-toolbar--m7">
                        <div>
                            <p class="chore-side-kicker">Chore queue</p>
                            <h3>${escapeHtml(selectedLabel)}</h3>
                            <p>${displayedCount} shown - ${pending.length} pending${done.length ? ` - ${done.length} done` : ""}</p>
                        </div>
                        <div class="chore-toolbar-actions">
                            <details class="chore-assignee-menu">
                                <summary style="--chore-accent:${selectedBucket?.color || "var(--brand-blue)"}">
                                    <span class="chore-person-avatar chore-person-avatar--mini" style="background:${selectedBucket?.color || "#2563eb"}">${escapeHtml(selectedBucket?.initials || "All")}</span>
                                    <span>${escapeHtml(selectedLabel)}</span>
                                    <strong>${selectedBucket?.pending ?? pending.length}</strong>
                                </summary>
                                <div class="chore-assignee-menu__panel">
                                    <div class="chore-panel-head">
                                        <div><h3>Assignees</h3><p>${pending.length} pending - ${points} points</p></div>
                                        ${actions.has("create_template") ? `<button class="view-small-btn" data-app-action="chores:create_template">New</button>` : ""}
                                    </div>
                                    <div class="chore-person-list">
                                        ${assigneeBuckets.map((bucket) => _renderChoreAssigneeTab(bucket, selectedAssignee)).join("")}
                                    </div>
                                </div>
                            </details>
                            ${actions.has("create_template") ? `<button class="view-small-btn view-small-btn--primary" data-app-action="chores:create_template">New template</button>` : ""}
                        </div>
                    </div>
                    <div class="chore-filter-summary">
                        <button class="chore-now-chip${state.choresFilter === "pending" ? " chore-now-chip--active" : ""}" type="button" data-chore-filter="pending">
                            <span>Pending</span><strong>${pending.length}</strong>
                        </button>
                        <details class="chore-more-filters app-advanced-section"${filtersExpanded ? " open" : ""}>
                            <summary><span>More filters</span><small>${escapeHtml(_choreFilterLabel(filterOptions, state.choresFilter))}</small></summary>
                            <div class="app-advanced-section__body">
                                <div class="chore-filter-row" role="tablist" aria-label="Chore filter">
                                    ${filterOptions.map((filter) => `
                                        <button class="chore-filter-chip${state.choresFilter === filter.key ? " chore-filter-chip--active" : ""}" type="button" data-chore-filter="${escapeHtml(filter.key)}">
                                            <span>${escapeHtml(filter.label)}</span><strong>${filter.count}</strong>
                                        </button>
                                    `).join("")}
                                </div>
                                <label class="chore-search-wrap">
                                    <span>Search</span>
                                    <input class="chore-search" type="search" data-chore-search value="${escapeHtml(state.choresSearchQuery || "")}" placeholder="Title, person, status">
                                </label>
                            </div>
                        </details>
                    </div>
                    ${_renderChoresSurface(visibleItems, scopedItems, summary, manifest, { dueNow: todayDueNow, upcoming: todayUpcoming, recentDone })}
                </section>
                ${selectedChore ? `<aside class="chore-inspector chore-detail-rail" id="chore-inspector">
                    <button class="app-detail-drawer__close chore-detail-close" type="button" data-chore-close-detail aria-label="Close chore details">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                    </button>
                    ${_renderChoreDetail(selectedChore, manifest, scopedItems, summary)}
                </aside>` : ""}
            </div>
        </div>`;

    body.querySelectorAll("[data-chore-assignee]").forEach((btn) => {
        btn.addEventListener("click", () => {
            state.choresSelectedAssignee = btn.dataset.choreAssignee || "__all__";
            state.choresSelectedKey = null;
            _renderAdapterBody(viewId, "chores", manifest, writeActions, listData);
        });
    });
    body.querySelectorAll("[data-chore-view]").forEach((btn) => {
        btn.addEventListener("click", () => {
            state.choresViewMode = btn.dataset.choreView || "today";
            _renderAdapterBody(viewId, "chores", manifest, writeActions, listData);
        });
    });
    body.querySelectorAll("[data-chore-filter]").forEach((btn) => {
        btn.addEventListener("click", () => {
            state.choresFilter = btn.dataset.choreFilter || "pending";
            _renderAdapterBody(viewId, "chores", manifest, writeActions, listData);
        });
    });
    const searchInput = body.querySelector("[data-chore-search]");
    if (searchInput) {
        searchInput.addEventListener("input", () => {
            state.choresSearchQuery = searchInput.value;
            const cursor = searchInput.selectionStart || state.choresSearchQuery.length;
            window.clearTimeout(state._choresSearchTimer);
            state._choresSearchTimer = window.setTimeout(() => {
                _renderAdapterBody(viewId, "chores", manifest, writeActions, listData);
                const nextInput = dom.viewBody[viewId]?.querySelector("[data-chore-search]");
                if (nextInput) {
                    nextInput.focus();
                    nextInput.setSelectionRange(cursor, cursor);
                }
            }, 120);
        });
    }
    body.querySelectorAll("[data-chore-action]").forEach((btn) => {
        btn.addEventListener("click", async () => {
            const occurrenceId = btn.dataset.occurrenceId;
            const actionName = btn.dataset.choreAction;
            if (!occurrenceId || !actionName) return;
            await _submitAdapterAction("chores", actionName, { occurrence_id: occurrenceId });
        });
    });
    body.querySelectorAll("[data-chore-form-action]").forEach((btn) => {
        btn.addEventListener("click", () => {
            const chore = items.find((candidate) => _choreKey(candidate) === btn.dataset.choreKey);
            if (!chore) return;
            const actionName = btn.dataset.choreFormAction;
            if (actionName === "assign_chore") {
                _openAdapterAction("chores", manifest, "assign_chore", _choreAssignDefaults(chore));
            } else if (actionName === "update_template") {
                _openAdapterAction("chores", manifest, "update_template", _choreTemplateDefaults(chore));
            }
        });
    });
    body.querySelectorAll("[data-chore-close-detail]").forEach((btn) => {
        btn.addEventListener("click", () => {
            state.choresSelectedKey = null;
            _renderAdapterBody(viewId, "chores", manifest, writeActions, listData);
        });
    });
    body.querySelectorAll("[data-chore-select-key]").forEach((node) => {
        node.addEventListener("click", (event) => {
            if (event.target.closest("[data-chore-action], [data-chore-form-action]")) return;
            state.choresSelectedKey = node.dataset.choreSelectKey;
            _renderAdapterBody(viewId, "chores", manifest, writeActions, listData);
        });
        node.addEventListener("keydown", (event) => {
            if (event.key !== "Enter" && event.key !== " ") return;
            if (event.target.closest("[data-chore-action], [data-chore-form-action]")) return;
            event.preventDefault();
            state.choresSelectedKey = node.dataset.choreSelectKey;
            _renderAdapterBody(viewId, "chores", manifest, writeActions, listData);
        });
    });
}

function _renderChoreAssigneeTab(bucket, selectedAssignee) {
    const active = bucket.id === selectedAssignee;
    return `
        <button class="chore-person-tab${active ? " chore-person-tab--active" : ""}" type="button" data-chore-assignee="${escapeHtml(bucket.id)}" style="--chore-accent:${bucket.color}">
            <span class="chore-person-avatar" style="background:${bucket.color}">${escapeHtml(bucket.initials)}</span>
            <span class="chore-person-copy"><strong>${escapeHtml(bucket.label)}</strong><small>${bucket.pending} pending - ${bucket.points} pts</small></span>
            <span class="chore-person-count">${bucket.total}</span>
        </button>`;
}

function _renderChoresSurface(items, scopedItems, summary, manifest, todayData = {}) {
    if (state.choresViewMode === "today") return _renderChoresToday(items, scopedItems, manifest, todayData);
    if (state.choresViewMode === "list") return _renderChoresList(items, manifest);
    if (state.choresViewMode === "rewards") return _renderChoresRewards(scopedItems, summary, manifest);
    return _renderChoresBoard(items, manifest);
}

function _renderChoresToday(items, scopedItems, manifest, todayData = {}) {
    const filter = state.choresFilter || "pending";
    const dueNow = filter === "pending" ? (todayData.dueNow || []) : items.filter((chore) => _choreStatus(chore) === "pending" && _choreIsDueNow(chore));
    const upcoming = filter === "pending" ? (todayData.upcoming || []) : items.filter((chore) => _choreStatus(chore) === "pending" && !_choreIsDueNow(chore));
    const done = filter === "pending" ? (todayData.recentDone || []) : items.filter((chore) => _choreStatus(chore) === "done");
    const skipped = filter === "skipped" ? items.filter((chore) => _choreStatus(chore) === "skipped") : [];
    const lanes = [
        { key: "due_now", label: "Due now", items: dueNow, empty: "Nothing due now" },
        { key: "upcoming", label: "Upcoming", items: upcoming.slice(0, 6), empty: "No chores waiting" },
        { key: "done", label: "Done recently", items: done.slice(0, 6), empty: "No wins yet" },
        ...(skipped.length ? [{ key: "skipped", label: "Skipped", items: skipped, empty: "None" }] : []),
    ];
    if (!scopedItems.length) return `<div class="chore-empty">No chores in this scope yet.</div>`;
    if (!lanes.some((lane) => lane.items.length)) return `<div class="chore-empty">${escapeHtml(_choreEmptyMessage())}</div>`;
    return `
        <div class="chore-today-grid">
            ${lanes.map((lane) => `
                <section class="chore-today-lane chore-today-lane--${escapeHtml(lane.key)}">
                    <header><h4>${escapeHtml(lane.label)}</h4><span>${lane.items.length}</span></header>
                    <div class="chore-lane-list">
                        ${lane.items.length ? lane.items.map((chore) => _renderChoreRow(chore, manifest, { compact: lane.key !== "done" })).join("") : `<p class="chore-column-empty">${escapeHtml(lane.empty)}</p>`}
                    </div>
                </section>
            `).join("")}
        </div>`;
}

function _renderChoresBoard(items, manifest) {
    const lanes = [
        { key: "due_now", label: "Due Now", items: items.filter((chore) => _choreStatus(chore) === "pending" && _choreIsDueNow(chore)) },
        { key: "upcoming", label: "Upcoming", items: items.filter((chore) => _choreStatus(chore) === "pending" && !_choreIsDueNow(chore)) },
        { key: "done", label: "Done", items: items.filter((chore) => _choreStatus(chore) === "done") },
        { key: "skipped", label: "Skipped", items: items.filter((chore) => _choreStatus(chore) === "skipped") },
    ];
    if (!items.length) return `<div class="chore-empty">${escapeHtml(_choreEmptyMessage())}</div>`;
    return `
        <div class="chore-board">
            ${lanes.map((lane) => `
                <section class="chore-lane chore-lane--${lane.key}">
                    <header><h4>${escapeHtml(lane.label)}</h4><span>${lane.items.length}</span></header>
                    <div class="chore-lane-list">
                        ${lane.items.length ? lane.items.map((chore) => _renderChoreRow(chore, manifest, { compact: true })).join("") : `<p class="chore-column-empty">Clear</p>`}
                    </div>
                </section>
            `).join("")}
        </div>`;
}

function _renderChoresList(items, manifest) {
    if (!items.length) return `<div class="chore-empty">${escapeHtml(_choreEmptyMessage())}</div>`;
    const groups = _choreListGroups(items);
    return `
        <div class="chore-list-surface">
            ${groups.map((group) => `
                <section class="chore-list-group">
                    <header><h4>${escapeHtml(group.label)}</h4><span>${group.items.length}</span></header>
                    ${group.items.map((chore) => _renderChoreRow(chore, manifest)).join("")}
                </section>
            `).join("")}
        </div>`;
}

function _renderChoresRewards(scopedItems, summary, manifest) {
    const leaderboard = _choreLeaderboard(scopedItems, summary);
    const completed = scopedItems.filter((chore) => _choreStatus(chore) === "done");
    return `
        <div class="chore-rewards-grid">
            <section class="chore-rewards-panel chore-rewards-panel--leaderboard">
                <header><h4>Leaderboard</h4><span>${leaderboard.length}</span></header>
                ${leaderboard.length ? leaderboard.map((row, index) => {
                    const display = _choreAssigneeDisplay(row.member_id);
                    return `
                        <div class="chore-leader-row" style="--chore-accent:${display.color}">
                            <span class="chore-leader-rank">${index + 1}</span>
                            <span class="chore-person-avatar" style="background:${display.color}">${escapeHtml(display.initials)}</span>
                            <span class="chore-leader-copy"><strong>${escapeHtml(display.name)}</strong><small>${row.done || 0} done - ${row.pending || 0} pending</small></span>
                            <strong>${Number(row.total_points || 0)} pts</strong>
                        </div>`;
                }).join("") : `<p class="chore-column-empty">No points yet</p>`}
            </section>
            <section class="chore-rewards-panel">
                <header><h4>Recent Wins</h4><span>${completed.length}</span></header>
                ${completed.length ? _choreSort(completed).slice(0, 8).map((chore) => _renderChoreRow(chore, manifest, { compact: true })).join("") : `<p class="chore-column-empty">No completed chores yet</p>`}
            </section>
        </div>`;
}

function _renderChoreRow(chore, manifest, options = {}) {
    const occurrenceId = _choreOccurrenceId(chore);
    const choreKey = _choreKey(chore);
    const status = _choreStatus(chore);
    const selected = state.choresSelectedKey === choreKey;
    const assignee = _choreAssigneeDisplay(_choreAssigneeId(chore));
    const points = Number(chore.points_awarded || chore.base_points || 0);
    const canComplete = status === "pending" && _hasAction(manifest, "complete_chore") && occurrenceId;
    const canSkip = status === "pending" && _hasAction(manifest, "skip_chore") && occurrenceId;
    const canReopen = status !== "pending" && _hasAction(manifest, "reopen_chore") && occurrenceId;
    const canAssign = _hasAction(manifest, "assign_chore") && chore.template_id;
    const canEdit = _hasAction(manifest, "update_template") && chore.template_id;
    return `
        <div class="chore-row chore-row--${escapeHtml(status)}${selected ? " chore-row--selected" : ""}${options.compact ? " chore-row--compact" : ""}" role="button" tabindex="0" data-chore-select-key="${escapeHtml(choreKey)}" style="--chore-accent:${_choreAccent(chore)}">
            <button class="chore-check" type="button" data-chore-action="complete_chore" data-occurrence-id="${escapeHtml(occurrenceId)}" ${canComplete ? "" : "disabled"} aria-label="Complete ${escapeHtml(chore.title || "chore")}">
                ${status === "done" ? `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>` : ""}
            </button>
            <div class="chore-row-body">
                <div class="chore-row-title-line">
                    <p class="chore-row-title">${escapeHtml(chore.title || "Chore")}</p>
                    ${_choreStatusPill(chore)}
                </div>
                <div class="chore-row-meta">
                    <span><span class="chore-person-avatar chore-person-avatar--mini" style="background:${assignee.color}">${escapeHtml(assignee.initials)}</span>${escapeHtml(assignee.name)}</span>
                    <span>${escapeHtml(_choreDueLabel(chore))}</span>
                    <span class="chore-points-badge">${points} pts</span>
                    ${chore.skip_reason ? `<span>${escapeHtml(chore.skip_reason)}</span>` : ""}
                </div>
            </div>
            <div class="chore-row-actions">
                ${canSkip ? `<button class="view-action-btn" type="button" data-chore-action="skip_chore" data-occurrence-id="${escapeHtml(occurrenceId)}">Skip</button>` : ""}
                ${canReopen ? `<button class="view-action-btn" type="button" data-chore-action="reopen_chore" data-occurrence-id="${escapeHtml(occurrenceId)}">Reopen</button>` : ""}
                ${canAssign ? `<button class="view-action-btn" type="button" data-chore-form-action="assign_chore" data-chore-key="${escapeHtml(choreKey)}">Assign</button>` : ""}
                ${canEdit ? `<button class="view-action-btn" type="button" data-chore-form-action="update_template" data-chore-key="${escapeHtml(choreKey)}">Edit</button>` : ""}
            </div>
        </div>`;
}

function _renderChoreDetail(chore, manifest, scopedItems, summary) {
    if (!chore) {
        const pending = scopedItems.filter((item) => _choreStatus(item) === "pending").length;
        const points = scopedItems.filter((item) => _choreStatus(item) === "done").reduce((total, item) => total + Number(item.points_awarded || 0), 0);
        return `
            <section class="chore-detail chore-detail--empty">
                <p class="chore-side-kicker">Chore details</p>
                <h3>No chore selected</h3>
                <div class="chore-detail-mini-stats">
                    <span><strong>${pending}</strong> pending</span>
                    <span><strong>${points}</strong> points</span>
                </div>
            </section>`;
    }
    const occurrenceId = _choreOccurrenceId(chore);
    const choreKey = _choreKey(chore);
    const status = _choreStatus(chore);
    const assignee = _choreAssigneeDisplay(_choreAssigneeId(chore));
    const points = Number(chore.points_awarded || chore.base_points || 0);
    const canComplete = status === "pending" && _hasAction(manifest, "complete_chore") && occurrenceId;
    const canSkip = status === "pending" && _hasAction(manifest, "skip_chore") && occurrenceId;
    const canReopen = status !== "pending" && _hasAction(manifest, "reopen_chore") && occurrenceId;
    const canAssign = _hasAction(manifest, "assign_chore") && chore.template_id;
    const canEdit = _hasAction(manifest, "update_template") && chore.template_id;
    return `
        <section class="chore-detail" style="--chore-accent:${_choreAccent(chore)}">
            <header class="chore-detail-head">
                <div>
                    <p class="chore-side-kicker">${escapeHtml(status)}</p>
                    <h3>${escapeHtml(chore.title || "Chore")}</h3>
                </div>
                ${_choreStatusPill(chore)}
            </header>
            <div class="chore-detail-assignee">
                <span class="chore-person-avatar" style="background:${assignee.color}">${escapeHtml(assignee.initials)}</span>
                <div><strong>${escapeHtml(assignee.name)}</strong><small>${escapeHtml(_choreDueLabel(chore))}</small></div>
            </div>
            <div class="chore-detail-meta">
                <span><strong>Points</strong>${points}</span>
                <span><strong>Status</strong>${escapeHtml(_humanizeLabel(status))}</span>
                <span><strong>Template</strong>${escapeHtml(chore.template_title || chore.template_name || "Recurring chore")}</span>
                <span><strong>Created By</strong>${escapeHtml(_choreActorDisplay(chore.actor || "system").name)}</span>
                ${chore.completed_at ? `<span><strong>Completed</strong>${escapeHtml(_relativeTimeAgo(chore.completed_at))}</span>` : ""}
                ${chore.completed_by ? `<span><strong>Completed By</strong>${escapeHtml(_choreActorDisplay(chore.completed_by).name)}</span>` : ""}
                ${chore.skipped_at ? `<span><strong>Skipped</strong>${escapeHtml(_relativeTimeAgo(chore.skipped_at))}</span>` : ""}
            </div>
            ${chore.skip_reason ? `<p class="chore-detail-note">${escapeHtml(chore.skip_reason)}</p>` : ""}
            <div class="chore-detail-actions">
                ${canComplete ? `<button class="view-small-btn view-small-btn--primary" type="button" data-chore-action="complete_chore" data-occurrence-id="${escapeHtml(occurrenceId)}">Done</button>` : ""}
                ${canSkip ? `<button class="view-small-btn" type="button" data-chore-action="skip_chore" data-occurrence-id="${escapeHtml(occurrenceId)}">Skip</button>` : ""}
                ${canReopen ? `<button class="view-small-btn view-small-btn--primary" type="button" data-chore-action="reopen_chore" data-occurrence-id="${escapeHtml(occurrenceId)}">Reopen</button>` : ""}
                ${canAssign ? `<button class="view-small-btn" type="button" data-chore-form-action="assign_chore" data-chore-key="${escapeHtml(choreKey)}">Assign</button>` : ""}
                ${canEdit ? `<button class="view-small-btn" type="button" data-chore-form-action="update_template" data-chore-key="${escapeHtml(choreKey)}">Edit template</button>` : ""}
            </div>
        </section>`;
}

function _choreOccurrenceId(chore) {
    return _idOf(chore, "occurrence_id");
}

function _choreKey(chore) {
    return _choreOccurrenceId(chore) || [chore.title || "", chore.template_id || "", chore.due_at || ""].join("|");
}

function _choreStatus(chore) {
    return chore.status || "pending";
}

function _choreAssigneeId(chore) {
    return _choreCanonicalAssigneeId(chore.assigned_to);
}

function _choreCanonicalAssigneeId(value) {
    if (!value) return "__unassigned__";
    return _reminderCanonicalMemberId(value, "") || String(value);
}

function _choreAssigneeDisplay(memberId) {
    if (!memberId || memberId === "__unassigned__") return { name: "Unassigned", initials: "U", color: "#94a3b8" };
    return _actorDisplay(memberId);
}

function _choreActorDisplay(actorId) {
    const raw = String(actorId || "").toLowerCase();
    if (/concierge|system|kernel|adapter/.test(raw)) return { name: "Family", initials: "F", color: "#2563eb" };
    return _actorDisplay(actorId);
}

function _choreAssigneeBuckets(items, summary) {
    const map = new Map();
    const ensure = (rawId) => {
        const id = rawId === "__unassigned__" ? rawId : _choreCanonicalAssigneeId(rawId);
        if (!map.has(id)) {
            const display = _choreAssigneeDisplay(id);
            map.set(id, { id, label: display.name, initials: display.initials, color: display.color, total: 0, pending: 0, points: 0 });
        }
        return map.get(id);
    };
    (state.family?.members || []).forEach((member) => ensure(member.actor_id || member.name));
    items.forEach((chore) => {
        const bucket = ensure(_choreAssigneeId(chore));
        bucket.total += 1;
        if (_choreStatus(chore) === "pending") bucket.pending += 1;
        if (_choreStatus(chore) === "done") bucket.points += Number(chore.points_awarded || 0);
    });
    summary.forEach((row) => {
        const bucket = ensure(row.member_id || "__unassigned__");
        bucket.points = Math.max(bucket.points, Number(row.total_points || 0));
        bucket.pending = Math.max(bucket.pending, Number(row.pending || 0));
    });
    const allPoints = Array.from(map.values()).reduce((total, bucket) => total + bucket.points, 0);
    const allPending = items.filter((chore) => _choreStatus(chore) === "pending").length;
    const all = { id: "__all__", label: "All chores", initials: "All", color: "#2563eb", total: items.length, pending: allPending, points: allPoints };
    return [all, ...Array.from(map.values()).sort((a, b) => b.pending - a.pending || b.points - a.points || a.label.localeCompare(b.label))];
}

function _choreSelectedAssigneeLabel(buckets, selectedAssignee) {
    return buckets.find((bucket) => bucket.id === selectedAssignee)?.label || "All chores";
}

function _choreApplyFilters(items, filter, query) {
    const normalizedQuery = String(query || "").trim().toLowerCase();
    return items.filter((chore) => {
        const status = _choreStatus(chore);
        if (filter === "pending" && status !== "pending") return false;
        if (filter === "due_now" && (status !== "pending" || !_choreIsDueNow(chore))) return false;
        if (filter === "upcoming" && (status !== "pending" || _choreIsDueNow(chore))) return false;
        if (filter === "overdue" && !(_choreIsOverdue(chore) && status === "pending")) return false;
        if (filter === "mine" && (status !== "pending" || _choreAssigneeId(chore) !== _currentMemberActorId())) return false;
        if (filter === "done" && status !== "done") return false;
        if (filter === "skipped" && status !== "skipped") return false;
        if (!normalizedQuery) return true;
        const assignee = _choreAssigneeDisplay(_choreAssigneeId(chore));
        const haystack = [chore.title, chore.description, status, chore.due_at, chore.skip_reason, chore.template_id, assignee.name].join(" ").toLowerCase();
        return haystack.includes(normalizedQuery);
    });
}

function _choreFilterOptions(items) {
    const pending = items.filter((chore) => _choreStatus(chore) === "pending");
    return [
        { key: "pending", label: "Pending", count: pending.length },
        { key: "due_now", label: "Due Now", count: pending.filter(_choreIsDueNow).length },
        { key: "upcoming", label: "Upcoming", count: pending.filter((chore) => !_choreIsDueNow(chore)).length },
        { key: "overdue", label: "Overdue", count: pending.filter(_choreIsOverdue).length },
        { key: "mine", label: "Mine", count: pending.filter((chore) => _choreAssigneeId(chore) === _currentMemberActorId()).length },
        { key: "done", label: "Done", count: items.filter((chore) => _choreStatus(chore) === "done").length },
        { key: "skipped", label: "Skipped", count: items.filter((chore) => _choreStatus(chore) === "skipped").length },
        { key: "all", label: "All", count: items.length },
    ];
}

function _choreFilterLabel(filterOptions, key) {
    return filterOptions.find((filter) => filter.key === key)?.label || _humanizeLabel(key || "pending");
}

function _choreEmptyMessage() {
    const filter = state.choresFilter || "pending";
    if (filter === "pending") return "No pending chores in this scope.";
    if (filter === "due_now") return "Nothing is due now.";
    if (filter === "upcoming") return "No upcoming chores in this scope.";
    if (filter === "overdue") return "No overdue chores.";
    if (filter === "mine") return "No chores assigned to you here.";
    if (filter === "done") return "No completed chores in this view.";
    if (filter === "skipped") return "No skipped chores in this view.";
    return "No chores match this view.";
}

function _choreListGroups(items) {
    const groupOrder = ["overdue", "today", "upcoming", "unscheduled", "done", "skipped"];
    const labels = { overdue: "Overdue", today: "Today", upcoming: "Upcoming", unscheduled: "Unscheduled", done: "Done", skipped: "Skipped" };
    const groups = new Map(groupOrder.map((key) => [key, []]));
    items.forEach((chore) => groups.get(_choreBucket(chore)).push(chore));
    return groupOrder.map((key) => ({ key, label: labels[key], items: groups.get(key) })).filter((group) => group.items.length);
}

function _choreBucket(chore) {
    const status = _choreStatus(chore);
    if (status === "done") return "done";
    if (status === "skipped") return "skipped";
    if (_choreIsOverdue(chore)) return "overdue";
    if (_choreIsDueToday(chore)) return "today";
    return chore.due_at ? "upcoming" : "unscheduled";
}

function _choreLeaderboard(items, summary) {
    const byMember = new Map();
    const ensure = (memberId) => {
        const id = memberId || "__unassigned__";
        if (!byMember.has(id)) byMember.set(id, { member_id: id, pending: 0, done: 0, skipped: 0, total_points: 0 });
        return byMember.get(id);
    };
    summary.forEach((row) => Object.assign(ensure(row.member_id), row));
    items.forEach((chore) => {
        const row = ensure(_choreAssigneeId(chore));
        const status = _choreStatus(chore);
        row[status] = Number(row[status] || 0) + 1;
        if (status === "done") row.total_points = Number(row.total_points || 0) + Number(chore.points_awarded || 0);
    });
    return Array.from(byMember.values()).sort((a, b) => Number(b.total_points || 0) - Number(a.total_points || 0) || Number(b.done || 0) - Number(a.done || 0));
}

function _choreSort(items) {
    return [...items].sort((first, second) => {
        const firstStatus = CHORE_STATUS_ORDER[_choreStatus(first)] ?? 9;
        const secondStatus = CHORE_STATUS_ORDER[_choreStatus(second)] ?? 9;
        if (firstStatus !== secondStatus) return firstStatus - secondStatus;
        const firstDue = _choreDueMs(first);
        const secondDue = _choreDueMs(second);
        if (firstDue !== secondDue) return firstDue - secondDue;
        return String(first.title || "").localeCompare(String(second.title || ""));
    });
}

function _choreDueMs(chore) {
    const ms = chore.due_at ? Date.parse(chore.due_at) : NaN;
    return Number.isFinite(ms) ? ms : Number.MAX_SAFE_INTEGER;
}

function _choreIsOverdue(chore) {
    if (!chore.due_at || _choreStatus(chore) !== "pending") return false;
    const due = new Date(chore.due_at);
    if (Number.isNaN(due.getTime())) return false;
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    return due < today;
}

function _choreIsDueToday(chore) {
    if (!chore.due_at || _choreStatus(chore) !== "pending") return false;
    const due = new Date(chore.due_at);
    if (Number.isNaN(due.getTime())) return false;
    const today = new Date();
    return due.getFullYear() === today.getFullYear() && due.getMonth() === today.getMonth() && due.getDate() === today.getDate();
}

function _choreIsDueNow(chore) {
    return _choreIsOverdue(chore) || _choreIsDueToday(chore);
}

function _choreDueLabel(chore) {
    if (_choreStatus(chore) === "done") return chore.completed_at ? `Done ${_relativeTimeAgo(chore.completed_at)}` : "Done";
    if (_choreStatus(chore) === "skipped") return chore.skipped_at ? `Skipped ${_relativeTimeAgo(chore.skipped_at)}` : "Skipped";
    if (!chore.due_at) return "No due date";
    if (_choreIsOverdue(chore)) return `Overdue ${_relativeDate(chore.due_at)}`;
    return _relativeDate(chore.due_at);
}

function _choreStatusPill(chore) {
    const status = _choreStatus(chore);
    const label = _choreIsOverdue(chore) ? "Overdue" : (CHORE_STATUS_META[status]?.label || _humanizeLabel(status));
    return `<span class="chore-status chore-status--${escapeHtml(_choreIsOverdue(chore) ? "overdue" : status)}">${escapeHtml(label)}</span>`;
}

function _choreAccent(chore) {
    if (_choreIsOverdue(chore)) return "#dc2626";
    return CHORE_STATUS_META[_choreStatus(chore)]?.color || "#2563eb";
}

function _choreAssignDefaults(chore) {
    return {
        template_id: chore.template_id || "",
        assigned_to: _choreAssigneeId(chore) === "__unassigned__" ? _currentMemberActorId() : _choreAssigneeId(chore),
        due_at: chore.due_at || "",
        points_awarded: Number(chore.points_awarded || 0),
        visibility: chore.visibility || "family",
    };
}

function _choreTemplateDefaults(chore) {
    return {
        template_id: chore.template_id || "",
        title: chore.title || "",
        assigned_to: _choreAssigneeId(chore) === "__unassigned__" ? "" : _choreAssigneeId(chore),
        base_points: Number(chore.points_awarded || 0),
        visibility: chore.visibility || "family",
    };
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
    const canSetFlag = _hasAction(manifest, "set_feature_flag");
    const enabledFlagCount = flags.filter((flag) => Boolean(flag.enabled)).length;
    const customizedRules = SETTINGS_SOURCE_RULES.filter((source) => Object.prototype.hasOwnProperty.call(rules, source.key)).length;
    const customizedKidCaps = SETTINGS_KID_CAPABILITIES.filter((cap) => Object.prototype.hasOwnProperty.call(kidCaps, cap.key)).length;
    const disabledKidCaps = SETTINGS_KID_CAPABILITIES.filter((cap) => Object.prototype.hasOwnProperty.call(kidCaps, cap.key) ? !Boolean(kidCaps[cap.key]) : !cap.defaultValue).length;
    const guardedSources = SETTINGS_SOURCE_RULES.filter((source) => _settingsBandForSource(source, rules) !== "family").length;
    if (state.settingsViewMode === "permissions") state.settingsViewMode = "kids";
    if (!SETTINGS_VIEW_MODES.includes(state.settingsViewMode)) state.settingsViewMode = "overview";
    if (state.settingsViewMode !== "features" && state.settingsSearchQuery) state.settingsSearchQuery = "";
    const filteredFlags = _settingsFilteredFlags(flags, state.settingsSearchQuery);
    const openKidCaps = SETTINGS_KID_CAPABILITIES.length - disabledKidCaps;
    const privateSources = SETTINGS_SOURCE_RULES.filter((source) => _settingsBandForSource(source, rules) === "private").length;
    const safetySignals = [
        { key: "privacy", label: "Privacy posture", value: guardedSources, detail: guardedSources ? `${guardedSources} sources limited` : "Family-wide defaults" },
        { key: "kids", label: "Kid permissions", value: disabledKidCaps, detail: disabledKidCaps ? `${disabledKidCaps} locks active` : "All kid actions open" },
        { key: "sensitive", label: "Sensitive terms", value: keywords.length, detail: keywords.length ? "Adults-only language guarded" : "No terms configured" },
        { key: "features", label: "Feature access", value: enabledFlagCount, detail: flags.length ? `${enabledFlagCount}/${flags.length} enabled` : "No flags configured" },
    ];
    const reviewItems = [
        !policy ? "Policy document has not loaded" : null,
        guardedSources === 0 ? "No source visibility limits are active" : null,
        keywords.length === 0 ? "No sensitive terms are configured" : null,
        disabledKidCaps === 0 ? "Kid permissions are fully open" : null,
    ].filter(Boolean);
    const safetyTitle = reviewItems.length ? "Safety settings need a look" : "Family safety is set";
    const safetyCopy = reviewItems.length
        ? `${reviewItems.length} area${reviewItems.length === 1 ? "" : "s"} may need a parent review before this feels locked in.`
        : `${guardedSources} privacy source${guardedSources === 1 ? "" : "s"}, ${disabledKidCaps} kid lock${disabledKidCaps === 1 ? "" : "s"}, and ${keywords.length} sensitive term${keywords.length === 1 ? "" : "s"} are active.`;

    const bandOptions = (selected) => SETTINGS_VISIBILITY_BANDS.map((band) =>
        `<option value="${escapeHtml(band.value)}" ${selected === band.value ? "selected" : ""}>${escapeHtml(band.label)}</option>`
    ).join("");

    const renderSourceRule = (source) => {
        const customized = Object.prototype.hasOwnProperty.call(rules, source.key);
        const band = _settingsBandForSource(source, rules);
        return `
            <div class="settings-source-row" style="--settings-accent:${_settingsBandColor(band)}">
                <span class="settings-source-swatch"></span>
                <div class="settings-source-copy">
                    <p class="settings-source-name">${escapeHtml(source.label)}</p>
                    <p class="settings-source-meta">${escapeHtml(source.meta)}</p>
                </div>
                <div class="settings-source-controls">
                    <span class="settings-pill ${customized ? "settings-pill--custom" : ""}">${customized ? "Custom" : "Default"}</span>
                    <span class="settings-band settings-band--${escapeHtml(band)}">${escapeHtml(_settingsBandLabel(band))}</span>
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
            <div class="settings-permission-row${enabled ? "" : " settings-permission-row--locked"}">
                <div class="settings-permission-copy">
                    <p class="settings-permission-name">${enabled ? "" : `<span class="settings-lock-mark" aria-hidden="true"></span>`}${escapeHtml(cap.label)}</p>
                    <div class="settings-permission-meta">
                        <span class="settings-pill ${customized ? "settings-pill--custom" : ""}">${customized ? "Custom" : "Default"}</span>
                        <span class="settings-capability-state">${enabled ? "Allowed" : "Blocked"}</span>
                    </div>
                </div>
                <div class="toggle settings-capability-toggle${enabled ? " toggle--on" : ""}" data-kid-capability="${escapeHtml(cap.key)}" data-enabled="${enabled}" role="switch" aria-checked="${enabled}" tabindex="0" ${canUpdatePolicy ? "" : "aria-disabled=\"true\""}>
                    <div class="toggle-thumb"></div>
                </div>
            </div>`;
    };

    const renderFlag = (flag) => {
        const name = flag.flag_name || flag.name || flag.id || "flag";
        const enabled = Boolean(flag.enabled);
        const desc = flag.description || "";
        const scope = flag.scope || "";
        const descriptionText = desc ? `${desc}${scope ? ` - ${scope}` : ""}` : (scope || name);
        return `
            <div class="flag-row${enabled ? " flag-row--enabled" : ""}">
                <div class="flag-info">
                    <p class="flag-name">${escapeHtml(_humanizeLabel(name))}</p>
                    <p class="flag-desc">${escapeHtml(descriptionText)}</p>
                </div>
                <span class="settings-pill ${enabled ? "settings-pill--custom" : ""}">${enabled ? "On" : "Off"}</span>
                <div class="toggle settings-flag-toggle${enabled ? " toggle--on" : ""}" data-flag="${escapeHtml(name)}" data-enabled="${enabled}" role="switch" aria-checked="${enabled}" tabindex="0" ${canSetFlag ? "" : "aria-disabled=\"true\""}>
                    <div class="toggle-thumb"></div>
                </div>
            </div>`;
    };

    const settingsContext = {
        policy,
        rules,
        keywords,
        kidCaps,
        flags,
        filteredFlags,
        canUpdatePolicy,
        canSetFlag,
        renderSourceRule,
        renderKidCapability,
        renderFlag,
        customizedRules,
        customizedKidCaps,
        enabledFlagCount,
        guardedSources,
        disabledKidCaps,
        openKidCaps,
        privateSources,
        reviewItems,
        safetySignals,
    };

    body.innerHTML = `
        <div class="settings-shell">
            <div class="settings-safety-stage">
                <section class="settings-safety-hero${reviewItems.length ? " settings-safety-hero--review" : ""}">
                    <div>
                        <p class="settings-side-kicker">Family safety overview</p>
                        <h3>${escapeHtml(safetyTitle)}</h3>
                        <p>${escapeHtml(safetyCopy)}</p>
                    </div>
                    <div class="settings-safety-metrics">
                        <span><strong>${guardedSources}</strong> protected sources</span>
                        <span><strong>${disabledKidCaps}</strong> kid locks</span>
                        <span><strong>${keywords.length}</strong> sensitive terms</span>
                    </div>
                </section>
                <aside class="settings-safety-panel">
                    <div class="settings-policy-card settings-policy-card--m8">
                        <p class="settings-section-title">Parent control</p>
                        <h3>${policy ? `Policy v${escapeHtml(policy.version || 1)}` : "Default policy"}</h3>
                        <span class="settings-band settings-band--private">Parent only</span>
                    </div>
                    <div class="settings-signal-grid">
                        ${safetySignals.map((signal) => `
                            <button class="settings-signal-card${state.settingsViewMode === signal.key ? " settings-signal-card--active" : ""}" type="button" data-settings-mode="${escapeHtml(signal.key)}">
                                <span>${escapeHtml(signal.label)}</span>
                                <strong>${signal.value}</strong>
                                <small>${escapeHtml(signal.detail)}</small>
                            </button>
                        `).join("")}
                    </div>
                </aside>
            </div>
            <div class="settings-category-strip" role="tablist" aria-label="Settings category">
                ${SETTINGS_VIEW_MODES.map((mode) => `
                    <button class="settings-mode-btn${state.settingsViewMode === mode ? " settings-mode-btn--active" : ""}" type="button" role="tab" aria-selected="${state.settingsViewMode === mode ? "true" : "false"}" data-settings-mode="${mode}">
                        <span>${escapeHtml(_settingsModeLabel(mode))}</span>
                        <strong>${escapeHtml(_settingsModeCount(mode, settingsContext))}</strong>
                    </button>
                `).join("")}
            </div>
            <section class="settings-main settings-main--m8">
                <div class="settings-toolbar settings-toolbar--m8">
                    <div>
                        <p class="settings-side-kicker">${escapeHtml(_settingsModeLabel(state.settingsViewMode))}</p>
                        <h3>${escapeHtml(_settingsModeTitle(state.settingsViewMode))}</h3>
                        <p>${escapeHtml(_settingsModeSubtitle(state.settingsViewMode))}</p>
                    </div>
                    <div class="settings-toolbar-actions">
                        ${state.settingsViewMode === "features" && canSetFlag ? `<button class="view-small-btn view-small-btn--primary" data-app-action="family_settings:set_feature_flag">New flag</button>` : ""}
                    </div>
                </div>
                ${_renderSettingsSurface(state.settingsViewMode, settingsContext)}
            </section>
            <details class="settings-advanced-policy app-advanced-section"${state.settingsAdvancedOpen ? " open" : ""}>
                <summary><span>Advanced policy details</span><small>Raw IDs, visibility counts, and admin update</small></summary>
                <div class="app-advanced-section__body settings-advanced-policy__body">
                    ${_renderSettingsInspector(settingsContext)}
                    ${canUpdatePolicy ? `<div class="settings-admin-actions"><button class="view-small-btn" data-app-action="family_settings:update_visibility_policy">Update policy manually</button></div>` : ""}
                </div>
            </details>
        </div>`;

    body.querySelectorAll("[data-settings-mode]").forEach((btn) => {
        btn.addEventListener("click", () => {
            state.settingsViewMode = btn.dataset.settingsMode || "overview";
            _renderAdapterBody(viewId, "family_settings", manifest, writeActions, listData);
        });
    });
    const advancedPolicy = body.querySelector(".settings-advanced-policy");
    if (advancedPolicy) {
        advancedPolicy.addEventListener("toggle", () => {
            state.settingsAdvancedOpen = advancedPolicy.open;
        });
    }
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
    const flagSearch = body.querySelector("[data-settings-search]");
    if (flagSearch) {
        flagSearch.addEventListener("input", () => {
            state.settingsSearchQuery = flagSearch.value;
            const cursor = flagSearch.selectionStart ?? state.settingsSearchQuery.length;
            window.clearTimeout(state._settingsSearchTimer);
            state._settingsSearchTimer = window.setTimeout(() => {
                _renderAdapterBody(viewId, "family_settings", manifest, writeActions, listData);
                const nextInput = dom.viewBody[viewId]?.querySelector("[data-settings-search]");
                if (nextInput) {
                    nextInput.focus();
                    nextInput.setSelectionRange(cursor, cursor);
                }
            }, 120);
        });
    }
}

function _renderSettingsSurface(mode, ctx) {
    if (mode === "overview") return _renderSettingsOverview(ctx);
    if (mode === "kids") return _renderSettingsKids(ctx);
    if (mode === "sensitive") return _renderSettingsSensitive(ctx);
    if (mode === "features") return _renderSettingsFeatures(ctx);
    return _renderSettingsPrivacy(ctx);
}

function _renderSettingsOverview({ rules, kidCaps, keywords, flags, guardedSources, disabledKidCaps, openKidCaps, privateSources, reviewItems, enabledFlagCount }) {
    const limitedSources = SETTINGS_SOURCE_RULES.filter((source) => _settingsBandForSource(source, rules) !== "family");
    const lockedCaps = SETTINGS_KID_CAPABILITIES.filter((cap) => Object.prototype.hasOwnProperty.call(kidCaps, cap.key) ? !Boolean(kidCaps[cap.key]) : !cap.defaultValue);
    return `
        <div class="settings-overview-surface">
            <section class="settings-overview-card settings-overview-card--privacy">
                <header>
                    <div><p class="settings-section-title">Privacy</p><h4>${guardedSources ? "Visibility boundaries are active" : "Family-wide by default"}</h4></div>
                    <button class="view-small-btn" type="button" data-settings-mode="privacy">Privacy</button>
                </header>
                <div class="settings-posture-list">
                    ${limitedSources.length ? limitedSources.map((source) => {
                        const band = _settingsBandForSource(source, rules);
                        return `<div class="settings-posture-row" style="--settings-accent:${_settingsBandColor(band)}"><span></span><strong>${escapeHtml(source.label)}</strong><small>${escapeHtml(_settingsBandLabel(band))}</small></div>`;
                    }).join("") : `<p class="settings-callout">No source is limited beyond family visibility.</p>`}
                </div>
            </section>
            <section class="settings-overview-card settings-overview-card--kids">
                <header>
                    <div><p class="settings-section-title">Kid permissions</p><h4>${disabledKidCaps} locked, ${openKidCaps} allowed</h4></div>
                    <button class="view-small-btn" type="button" data-settings-mode="kids">Kid permissions</button>
                </header>
                <div class="settings-mini-list">
                    ${lockedCaps.length ? lockedCaps.slice(0, 4).map((cap) => `<span>${escapeHtml(cap.label)}</span>`).join("") : `<p class="settings-callout">No kid permission locks are active.</p>`}
                </div>
            </section>
            <section class="settings-overview-card settings-overview-card--sensitive">
                <header>
                    <div><p class="settings-section-title">Sensitive terms</p><h4>${keywords.length ? `${keywords.length} adults-only terms` : "No terms configured"}</h4></div>
                    <button class="view-small-btn" type="button" data-settings-mode="sensitive">Sensitive terms</button>
                </header>
                ${keywords.length ? `<div class="settings-keyword-preview">${keywords.slice(0, 8).map((kw) => `<span>${escapeHtml(kw)}</span>`).join("")}${keywords.length > 8 ? `<span>${keywords.length - 8} more</span>` : ""}</div>` : `<p class="settings-callout">Sensitive language is not listed yet.</p>`}
            </section>
            <section class="settings-overview-card settings-overview-card--features">
                <header>
                    <div><p class="settings-section-title">Feature access</p><h4>${flags.length ? `${enabledFlagCount}/${flags.length} enabled` : "No feature flags"}</h4></div>
                    <button class="view-small-btn" type="button" data-settings-mode="features">Feature access</button>
                </header>
                <div class="settings-feature-meter" style="--feature-on:${flags.length ? Math.round((enabledFlagCount / flags.length) * 100) : 0}%"><span></span></div>
                <p class="settings-feature-note">${privateSources ? `${privateSources} private source${privateSources === 1 ? "" : "s"} stay parent-only.` : "No source is marked parent-only."}</p>
            </section>
            ${reviewItems.length ? `<section class="settings-review-list"><p class="settings-section-title">Needs review</p>${reviewItems.map((item) => `<span>${escapeHtml(item)}</span>`).join("")}</section>` : ""}
        </div>`;
}

function _renderSettingsPrivacy({ policy, renderSourceRule }) {
    return `
        <div class="settings-privacy-surface">
            ${policy == null ? `<p class="settings-callout">No policy document visible.</p>` : ""}
            <div class="settings-source-list">
                ${SETTINGS_SOURCE_RULES.map(renderSourceRule).join("")}
            </div>
        </div>`;
}

function _renderSettingsSensitive({ keywords, canUpdatePolicy }) {
    return `
        <div class="settings-sensitive-surface">
            <section class="settings-section settings-section--keywords">
                <div class="settings-section-head">
                    <div>
                        <p class="settings-section-title">Sensitive Information</p>
                        <h3>Adults-only terms</h3>
                    </div>
                </div>
                <div class="settings-keywords">
                    ${keywords.length === 0
                        ? `<p class="settings-callout">No sensitive terms configured.</p>`
                        : `<div class="settings-keyword-list">${keywords.map((kw) => `
                            <span class="settings-keyword-chip">${escapeHtml(kw)}${canUpdatePolicy ? `<button type="button" data-keyword-remove="${escapeHtml(kw)}" aria-label="Remove ${escapeHtml(kw)}">&times;</button>` : ""}</span>`).join("")}</div>`}
                    ${canUpdatePolicy ? `
                        <div class="settings-keyword-add">
                            <input type="text" class="settings-keyword-input" data-keyword-input placeholder="doctor, salary, therapy" aria-label="Add sensitive terms">
                            <button type="button" class="view-small-btn" data-keyword-add>Add</button>
                        </div>` : ""}
                </div>
            </section>
        </div>`;
}

function _renderSettingsKids({ renderKidCapability }) {
    return `
        <div class="settings-kids-surface">
            <section class="settings-section settings-section--capabilities">
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
        </div>`;
}

function _renderSettingsFeatures({ flags, filteredFlags, renderFlag }) {
    return `
        <div class="settings-features-surface">
            <div class="settings-feature-tools">
                <label class="settings-search-wrap">
                    <span>Search</span>
                    <input class="settings-search" type="search" data-settings-search value="${escapeHtml(state.settingsSearchQuery || "")}" placeholder="Flag, scope, description">
                </label>
            </div>
            <div class="settings-flag-list">
                ${flags.length === 0
                    ? `<p class="settings-callout">No feature flags configured.</p>`
                    : filteredFlags.length === 0
                        ? `<p class="settings-callout">No flags match this search.</p>`
                        : filteredFlags.map(renderFlag).join("")}
            </div>
        </div>`;
}

function _renderSettingsInspector({ policy, rules, keywords, kidCaps, flags, customizedRules, customizedKidCaps, enabledFlagCount, guardedSources }) {
    const bandCounts = _settingsBandCounts(rules);
    return `
        <section class="settings-detail">
            <p class="settings-side-kicker">Policy snapshot</p>
            <h3>${policy ? "Active policy" : "Default policy"}</h3>
            <div class="settings-detail-stats">
                <span><strong>${guardedSources}</strong> guarded</span>
                <span><strong>${customizedRules}</strong> custom rules</span>
                <span><strong>${keywords.length}</strong> terms</span>
                <span><strong>${enabledFlagCount}</strong> flags on</span>
            </div>
            <div class="settings-band-stack">
                ${SETTINGS_VISIBILITY_BANDS.map((band) => `
                    <div class="settings-band-row" style="--settings-accent:${_settingsBandColor(band.value)}">
                        <span class="settings-source-swatch"></span>
                        <span>${escapeHtml(band.label)}</span>
                        <strong>${bandCounts[band.value] || 0}</strong>
                    </div>
                `).join("")}
            </div>
            <div class="settings-detail-meta">
                <span><strong>Policy ID</strong>${escapeHtml(policy?.id || "seeded on first read")}</span>
                <span><strong>Visibility</strong>${escapeHtml(policy?.visibility || "private")}</span>
                <span><strong>Kid caps changed</strong>${customizedKidCaps}/${SETTINGS_KID_CAPABILITIES.length}</span>
                <span><strong>Flags total</strong>${flags.length}</span>
            </div>
        </section>`;
}

function _settingsModeLabel(mode) {
    if (mode === "overview") return "Overview";
    if (mode === "kids") return "Kid permissions";
    if (mode === "sensitive") return "Sensitive terms";
    if (mode === "features") return "Feature access";
    return "Privacy";
}

function _settingsModeTitle(mode) {
    if (mode === "overview") return "Safety posture";
    if (mode === "kids") return "Child capability gates";
    if (mode === "sensitive") return "Adults-only terms";
    if (mode === "features") return "Feature availability";
    return "Source visibility";
}

function _settingsModeSubtitle(mode) {
    if (mode === "overview") return "The parent view before policy mechanics.";
    if (mode === "kids") return "What children can do without parent intervention.";
    if (mode === "sensitive") return "Terms that should stay in adult-facing contexts.";
    if (mode === "features") return "Feature switches by family space or member.";
    return "Who can see each source of family information.";
}

function _settingsModeCount(mode, counts) {
    if (mode === "overview") return counts.reviewItems.length ? `${counts.reviewItems.length}` : "OK";
    if (mode === "kids") return `${counts.disabledKidCaps}`;
    if (mode === "sensitive") return `${counts.keywords.length}`;
    if (mode === "features") return `${counts.enabledFlagCount}/${counts.flags.length}`;
    return `${counts.guardedSources}/${SETTINGS_SOURCE_RULES.length}`;
}

function _settingsFilteredFlags(flags, query) {
    const normalizedQuery = String(query || "").trim().toLowerCase();
    if (!normalizedQuery) return flags;
    return flags.filter((flag) => [flag.flag_name, flag.name, flag.id, flag.description, flag.scope, flag.target_member_id]
        .join(" ").toLowerCase().includes(normalizedQuery));
}

function _settingsBandForSource(source, rules) {
    return rules[source.key] || source.defaultBand || "family";
}

function _settingsBandLabel(band) {
    return SETTINGS_VISIBILITY_BANDS.find((item) => item.value === band)?.label || _humanizeLabel(band);
}

function _settingsBandColor(band) {
    return SETTINGS_BAND_COLORS[band] || SETTINGS_BAND_COLORS.family;
}

function _settingsBandCounts(rules) {
    return SETTINGS_SOURCE_RULES.reduce((counts, source) => {
        const band = _settingsBandForSource(source, rules);
        counts[band] = (counts[band] || 0) + 1;
        return counts;
    }, {});
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
            eventAction ? _callListAction(adapterId, eventAction, _calListRangeParams()) : null,
            feedAction ? _callListAction(adapterId, feedAction) : null,
        ]);
        const range = _calListRangeParams();
        calState.loadedStart = range.start;
        calState.loadedEnd = range.end;
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

async function _callListAction(adapterId, action, params = null) {
    let url = `/k1/tools/${adapterId}/${action.name}`;
    const query = new URLSearchParams();
    if (params && typeof params === "object") {
        Object.entries(params).forEach(([key, value]) => {
            if (value !== undefined && value !== null && value !== "") query.set(key, String(value));
        });
    } else if (adapterId === "calendar" && action.name === "list_events") {
        const range = _calListRangeParams();
        query.set("start", range.start);
        query.set("end", range.end);
        query.set("start_date", range.start_date);
        query.set("end_date", range.end_date);
    }
    const queryString = query.toString();
    if (queryString) {
        url += `?${queryString}`;
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
