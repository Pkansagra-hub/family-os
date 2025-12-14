/**
 * Sidebar Service - Conversation Management
 *
 * Handles:
 * - Display of conversation history
 * - Creating new conversations
 * - Switching between conversations
 * - Editing conversation titles
 * - Deleting conversations
 */

import { createNewConversation, deleteConversation, getAllConversations, getCurrentConversationId, setCurrentConversationId } from './storage.js';

/**
 * Initialize sidebar with event listeners
 */
export function initializeSidebar() {
    const toggleBtn = document.getElementById('sidebarToggle');
    const sidebar = document.getElementById('sidebar');
    const newChatBtn = document.getElementById('newChatBtn');

    if (toggleBtn && sidebar) {
        toggleBtn.addEventListener('click', () => toggleSidebar(sidebar));
    }

    if (newChatBtn) {
        newChatBtn.addEventListener('click', handleNewConversation);
    }

    // Initial render
    renderConversationList();

    // Listen for storage changes
    window.addEventListener('storage', renderConversationList);
}

/**
 * Toggle sidebar visibility
 */
export function toggleSidebar(sidebar) {
    const isOpen = sidebar.classList.contains('open');
    if (isOpen) {
        sidebar.classList.remove('open');
        sidebar.classList.add('closed');
    } else {
        sidebar.classList.remove('closed');
        sidebar.classList.add('open');
    }
}

/**
 * Render all conversations in sidebar
 */
export async function renderConversationList() {
    const conversationsList = document.getElementById('conversationsList');
    if (!conversationsList) return;

    const conversations = await getAllConversations();
    const currentId = await getCurrentConversationId();

    // Group by date
    const grouped = groupConversationsByDate(conversations);

    conversationsList.innerHTML = '';

    for (const [dateGroup, convos] of Object.entries(grouped)) {
        // Add date header
        const header = document.createElement('div');
        header.className = 'conversation-date-header';
        header.textContent = dateGroup;
        conversationsList.appendChild(header);

        // Add conversations for this date
        for (const convo of convos) {
            const item = createConversationItem(convo, currentId === convo.id);
            conversationsList.appendChild(item);
        }
    }
}

/**
 * Group conversations by date (Today, Yesterday, This Week, Older)
 */
function groupConversationsByDate(conversations) {
    const now = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);
    const weekAgo = new Date(today);
    weekAgo.setDate(weekAgo.getDate() - 7);

    const groups = {
        'Today': [],
        'Yesterday': [],
        'This Week': [],
        'Older': []
    };

    for (const convo of conversations) {
        const convoDate = new Date(convo.createdAt);
        const convoDayStart = new Date(convoDate.getFullYear(), convoDate.getMonth(), convoDate.getDate());

        if (convoDayStart.getTime() === today.getTime()) {
            groups['Today'].push(convo);
        } else if (convoDayStart.getTime() === yesterday.getTime()) {
            groups['Yesterday'].push(convo);
        } else if (convoDayStart.getTime() > weekAgo.getTime()) {
            groups['This Week'].push(convo);
        } else {
            groups['Older'].push(convo);
        }
    }

    // Remove empty groups and sort by date
    const result = {};
    for (const [key, value] of Object.entries(groups)) {
        if (value.length > 0) {
            result[key] = value.sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt));
        }
    }

    return result;
}

/**
 * Create conversation list item element
 */
function createConversationItem(convo, isActive) {
    const item = document.createElement('div');
    item.className = `conversation-item ${isActive ? 'active' : ''}`;
    item.dataset.conversationId = convo.id;

    // Main content (clickable to switch)
    const content = document.createElement('div');
    content.className = 'conversation-item-content';
    content.innerHTML = `
        <div class="conversation-title">${escapeHtml(convo.title)}</div>
        <div class="conversation-timestamp">${formatTimestamp(convo.updatedAt)}</div>
    `;

    content.addEventListener('click', () => switchConversation(convo.id));
    item.appendChild(content);

    // Actions (edit, delete)
    const actions = document.createElement('div');
    actions.className = 'conversation-actions';

    // Edit button (double-click title to edit)
    const titleEl = content.querySelector('.conversation-title');
    titleEl.style.cursor = 'pointer';
    titleEl.addEventListener('dblclick', (e) => {
        e.stopPropagation();
        editConversationTitle(convo.id, titleEl);
    });

    // Delete button
    const deleteBtn = document.createElement('button');
    deleteBtn.className = 'conversation-delete-btn';
    deleteBtn.innerHTML = '🗑️';
    deleteBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        showDeleteConfirmation(convo.id, convo.title);
    });

    actions.appendChild(deleteBtn);
    item.appendChild(actions);

    return item;
}

/**
 * Switch to a different conversation
 */
export async function switchConversation(conversationId) {
    await setCurrentConversationId(conversationId);

    // Update UI
    const items = document.querySelectorAll('.conversation-item');
    items.forEach(item => {
        item.classList.remove('active');
        if (item.dataset.conversationId === conversationId) {
            item.classList.add('active');
        }
    });

    // Clear messages and reload
    const messagesEl = document.getElementById('messagesContainer');
    if (messagesEl) {
        messagesEl.innerHTML = '<div class="status-message">Loading conversation...</div>';
    }

    // Dispatch event for main.js to handle
    window.dispatchEvent(new CustomEvent('conversationChanged', { detail: { conversationId } }));
}

/**
 * Handle new conversation creation
 */
export async function handleNewConversation() {
    const newConvo = await createNewConversation();
    await setCurrentConversationId(newConvo.id);

    // Clear messages
    const messagesEl = document.getElementById('messagesContainer');
    if (messagesEl) {
        messagesEl.innerHTML = '';
    }

    // Focus input
    const input = document.getElementById('messageInput');
    if (input) {
        input.focus();
    }

    // Re-render sidebar
    await renderConversationList();

    // Dispatch event
    window.dispatchEvent(new CustomEvent('conversationChanged', { detail: { conversationId: newConvo.id } }));
}

/**
 * Edit conversation title (inline editing)
 */
export async function editConversationTitle(conversationId, titleEl) {
    const currentTitle = titleEl.textContent;
    const input = document.createElement('input');
    input.type = 'text';
    input.value = currentTitle;
    input.className = 'conversation-title-edit';

    titleEl.replaceWith(input);
    input.focus();
    input.select();

    const finishEdit = async (newTitle) => {
        if (newTitle.trim() && newTitle !== currentTitle) {
            // Update in storage
            const convos = await getAllConversations();
            const convo = convos.find(c => c.id === conversationId);
            if (convo) {
                convo.title = newTitle.trim();
                convo.updatedAt = new Date().toISOString();
                await new Promise(resolve => {
                    const tx = window.db.transaction('conversations', 'readwrite');
                    tx.objectStore('conversations').put(convo);
                    tx.oncomplete = resolve;
                });
            }
        }

        const newTitleEl = document.createElement('div');
        newTitleEl.className = 'conversation-title';
        newTitleEl.textContent = currentTitle;
        newTitleEl.style.cursor = 'pointer';
        newTitleEl.addEventListener('dblclick', (e) => {
            e.stopPropagation();
            editConversationTitle(conversationId, newTitleEl);
        });

        input.replaceWith(newTitleEl);
        await renderConversationList();
    };

    input.addEventListener('blur', () => finishEdit(input.value));
    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            finishEdit(input.value);
        } else if (e.key === 'Escape') {
            finishEdit(currentTitle);
        }
    });
}

/**
 * Show delete confirmation modal
 */
export function showDeleteConfirmation(conversationId, title) {
    const modal = document.createElement('div');
    modal.className = 'modal-overlay';

    const content = document.createElement('div');
    content.className = 'modal-content delete-confirmation';
    content.innerHTML = `
        <h3>Delete Conversation?</h3>
        <p>Are you sure you want to delete "<strong>${escapeHtml(title)}</strong>"?</p>
        <p class="warning">This action cannot be undone.</p>
        <div class="modal-buttons">
            <button class="btn-cancel">Cancel</button>
            <button class="btn-delete">Delete</button>
        </div>
    `;

    modal.appendChild(content);
    document.body.appendChild(modal);

    const cancelBtn = content.querySelector('.btn-cancel');
    const deleteBtn = content.querySelector('.btn-delete');

    cancelBtn.addEventListener('click', () => modal.remove());
    deleteBtn.addEventListener('click', async () => {
        await deleteConversation(conversationId);
        modal.remove();

        // If we deleted current conversation, switch to most recent
        const convos = await getAllConversations();
        if (convos.length > 0) {
            await switchConversation(convos[0].id);
        } else {
            await handleNewConversation();
        }

        await renderConversationList();
    });

    modal.addEventListener('click', (e) => {
        if (e.target === modal) {
            modal.remove();
        }
    });
}

/**
 * Format timestamp for display
 */
function formatTimestamp(isoString) {
    const date = new Date(isoString);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return 'just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;

    return date.toLocaleDateString();
}

/**
 * Escape HTML to prevent XSS
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
