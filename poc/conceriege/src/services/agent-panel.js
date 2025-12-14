/**
 * Agent Activity Panel Service
 *
 * Displays:
 * - Real-time agent status updates
 * - Specialist hierarchy (tree view)
 * - Progress indicators and spinners
 * - Agent lifecycle events
 */

/**
 * Initialize agent activity panel
 */
export function initializeAgentPanel() {
    const panel = document.getElementById('agentActivityPanel');
    if (!panel) return;

    // Start with empty state
    renderAgentPanel();
}

/**
 * Render agent activity panel UI
 */
export function renderAgentPanel() {
    const panel = document.getElementById('agentActivityPanel');
    if (!panel) return;

    if (!window.agentStates) {
        window.agentStates = {};
    }

    const agents = Object.values(window.agentStates || {});

    if (agents.length === 0) {
        panel.innerHTML = `
            <div class="agent-panel-empty">
                <p>No active agents</p>
            </div>
        `;
        return;
    }

    panel.innerHTML = '<div class="agent-panel-header">🏃 Active Agents</div>';

    // Render each agent
    for (const agent of agents) {
        const agentEl = createAgentElement(agent);
        panel.appendChild(agentEl);
    }
}

/**
 * Create agent display element
 */
function createAgentElement(agent) {
    const container = document.createElement('div');
    container.className = `agent-card ${agent.status}`;
    container.dataset.agentId = agent.id;

    const icon = getAgentIcon(agent.type);
    const progress = agent.progress || 0;

    const timeRemaining = agent.eta ? formatETA(agent.eta) : 'calculating...';

    container.innerHTML = `
        <div class="agent-header">
            <div class="agent-info">
                <span class="agent-icon">${icon}</span>
                <div class="agent-details">
                    <div class="agent-name">${agent.type}</div>
                    <div class="agent-status">${agent.status}</div>
                </div>
            </div>
            <button class="agent-expand-btn" data-agent-id="${agent.id}">▼</button>
        </div>

        <div class="agent-body" style="display: none;">
            <div class="agent-task">${agent.task || 'Processing...'}</div>

            <div class="progress-container">
                <div class="progress-bar">
                    <div class="progress-fill" style="width: ${progress}%"></div>
                </div>
                <div class="progress-text">${Math.round(progress)}%</div>
            </div>

            <div class="agent-timing">
                ⏱️ ${timeRemaining}
            </div>

            ${agent.children && agent.children.length > 0 ? `
                <div class="agent-specialists">
                    <div class="specialists-label">👥 Specialists:</div>
                    <div class="specialists-list">
                        ${agent.children.map(child => `
                            <div class="specialist-item">
                                <span class="specialist-icon">${getAgentIcon(child.type)}</span>
                                <span class="specialist-name">${child.type}</span>
                                <span class="specialist-status">${child.status}</span>
                            </div>
                        `).join('')}
                    </div>
                </div>
            ` : ''}
        </div>
    `;

    // Handle expand/collapse
    const expandBtn = container.querySelector('.agent-expand-btn');
    const body = container.querySelector('.agent-body');

    expandBtn.addEventListener('click', () => {
        const isOpen = body.style.display !== 'none';
        body.style.display = isOpen ? 'none' : 'block';
        expandBtn.textContent = isOpen ? '▶' : '▼';
    });

    return container;
}

/**
 * Handle agent event from WebSocket
 */
export function handleAgentEvent(data) {
    if (!window.agentStates) {
        window.agentStates = {};
    }

    switch (data.type) {
        case 'agent.started':
            handleAgentStarted(data);
            break;
        case 'agent.progress':
            handleAgentProgress(data);
            break;
        case 'agent.completed':
            handleAgentCompleted(data);
            break;
        case 'specialist.spawned':
            handleSpecialistSpawned(data);
            break;
    }

    renderAgentPanel();
}

/**
 * Handle agent started event
 */
function handleAgentStarted(data) {
    window.agentStates[data.agent_id] = {
        id: data.agent_id,
        type: data.agent_type,
        task: data.task,
        status: 'Running',
        progress: 0,
        parent: data.parent_agent,
        children: [],
        startTime: Date.now(),
        eta: null
    };
}

/**
 * Handle agent progress update
 */
function handleAgentProgress(data) {
    if (window.agentStates[data.agent_id]) {
        window.agentStates[data.agent_id].progress = Math.min(data.progress * 100, 99);
        window.agentStates[data.agent_id].status = data.status;

        // Estimate ETA based on progress and time elapsed
        const agent = window.agentStates[data.agent_id];
        if (agent.progress > 0) {
            const elapsed = (Date.now() - agent.startTime) / 1000;
            const rate = agent.progress / elapsed;
            const remaining = (100 - agent.progress) / rate;
            agent.eta = remaining;
        }
    }
}

/**
 * Handle agent completed event
 */
function handleAgentCompleted(data) {
    if (window.agentStates[data.agent_id]) {
        window.agentStates[data.agent_id].status = 'Completed';
        window.agentStates[data.agent_id].progress = 100;

        // Auto-remove after 2 seconds
        setTimeout(() => {
            delete window.agentStates[data.agent_id];
            renderAgentPanel();
        }, 2000);
    }
}

/**
 * Handle specialist spawned event
 */
function handleSpecialistSpawned(data) {
    if (window.agentStates[data.parent_id]) {
        const parent = window.agentStates[data.parent_id];

        parent.children = parent.children || [];
        parent.children.push({
            id: data.specialist_id,
            type: data.capability,
            status: 'Spawned',
            progress: 0
        });
    }
}

/**
 * Get emoji icon for agent type
 */
function getAgentIcon(agentType) {
    const icons = {
        'nutritionist': '🥗',
        'research': '🔍',
        'psychiatrist': '🧠',
        'fitness': '💪',
        'sleep': '😴',
        'stress': '🧘',
        'memory': '📚',
        'analysis': '📊',
        'data_retrieval': '💾',
        'family': '👨‍👩‍👧‍👦',
        'concierge': '🎩',
        'default': '🤖'
    };

    return icons[agentType?.toLowerCase()] || icons['default'];
}

/**
 * Format ETA (in seconds) to readable string
 */
function formatETA(seconds) {
    if (!seconds || seconds < 0) return 'calculating...';

    const mins = Math.floor(seconds / 60);
    const secs = Math.round(seconds % 60);

    if (mins === 0) {
        return `${secs}s remaining`;
    } else if (mins < 60) {
        return `${mins}m ${secs}s remaining`;
    } else {
        const hours = Math.floor(mins / 60);
        return `${hours}h ${mins % 60}m remaining`;
    }
}

/**
 * Toggle agent panel visibility
 */
export function toggleAgentPanel() {
    const panel = document.getElementById('agentActivityPanel');
    if (!panel) return;

    const isVisible = panel.style.display !== 'none';
    panel.style.display = isVisible ? 'none' : 'block';

    // Store preference
    localStorage.setItem('agentPanelVisible', !isVisible);
}

/**
 * Get agent panel visibility preference
 */
export function getAgentPanelPreference() {
    const stored = localStorage.getItem('agentPanelVisible');
    return stored !== 'false'; // Default to visible
}

/**
 * Clear all agents from panel
 */
export function clearAgentPanel() {
    window.agentStates = {};
    renderAgentPanel();
}
