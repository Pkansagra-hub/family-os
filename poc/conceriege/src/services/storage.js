/**
 * Storage Service using IndexedDB (via Dexie.js)
 *
 * Provides persistent storage for conversations and messages.
 * Automatically saves messages and restores on page load.
 *
 * Features:
 * - Create/read/update/delete conversations
 * - Save messages with timestamps
 * - Full-text search across messages
 * - Storage quota management
 *
 * Usage:
 *   import { storage } from './storage.js';
 *   await storage.saveMessage(conversationId, message);
 */

import Dexie from 'https://cdn.jsdelivr.net/npm/dexie@3.2.4/+esm';

class StorageService {
    constructor() {
        this.db = null;
        this.currentConversationId = null;
        this.init();
    }

    /**
     * Initialize database
     */
    async init() {
        this.db = new Dexie('ConciergeDB');

        // Define schema
        this.db.version(1).stores({
            conversations: '++id, title, createdAt, updatedAt',
            messages: '++id, conversationId, type, message, timestamp, [conversationId+timestamp]'
        });

        try {
            await this.db.open();
            console.log('Database initialized successfully');

            // Check storage quota
            await this.checkStorageQuota();

            // Get or create current conversation
            this.currentConversationId = await this.getCurrentConversation();
        } catch (error) {
            console.error('Failed to initialize database:', error);
        }
    }

    /**
     * Check storage quota and warn if low
     */
    async checkStorageQuota() {
        if (!navigator.storage || !navigator.storage.estimate) {
            console.warn('Storage API not available');
            return;
        }

        try {
            const estimate = await navigator.storage.estimate();
            const usedMB = (estimate.usage / 1024 / 1024).toFixed(2);
            const quotaMB = (estimate.quota / 1024 / 1024).toFixed(2);
            const percentUsed = ((estimate.usage / estimate.quota) * 100).toFixed(1);

            console.log(`Storage: ${usedMB}MB / ${quotaMB}MB (${percentUsed}%)`);

            // Warn if over 80% usage
            if (estimate.usage / estimate.quota > 0.8) {
                console.warn('Storage quota is over 80%! Consider cleaning up old conversations.');
                return {
                    warning: true,
                    percentUsed,
                    usedMB,
                    quotaMB
                };
            }

            return {
                warning: false,
                percentUsed,
                usedMB,
                quotaMB
            };
        } catch (error) {
            console.error('Failed to check storage quota:', error);
            return null;
        }
    }

    /**
     * Get or create current conversation
     * @returns {Promise<number>} Conversation ID
     */
    async getCurrentConversation() {
        // Check localStorage for current conversation
        const savedId = localStorage.getItem('currentConversationId');

        if (savedId) {
            const exists = await this.db.conversations.get(parseInt(savedId));
            if (exists) {
                return parseInt(savedId);
            }
        }

        // Create new conversation
        return this.createConversation('New Conversation');
    }

    /**
     * Create a new conversation
     * @param {string} title - Conversation title
     * @returns {Promise<number>} Conversation ID
     */
    async createConversation(title = 'New Conversation') {
        const now = new Date().toISOString();

        try {
            const id = await this.db.conversations.add({
                title,
                createdAt: now,
                updatedAt: now
            });

            localStorage.setItem('currentConversationId', id);
            this.currentConversationId = id;

            console.log(`Created conversation ${id}: ${title}`);
            return id;
        } catch (error) {
            console.error('Failed to create conversation:', error);
            throw error;
        }
    }

    /**
     * Get all conversations
     * @returns {Promise<Array>} Array of conversations
     */
    async listConversations() {
        try {
            return await this.db.conversations
                .orderBy('updatedAt')
                .reverse()
                .toArray();
        } catch (error) {
            console.error('Failed to list conversations:', error);
            return [];
        }
    }

    /**
     * Get conversation by ID
     * @param {number} id - Conversation ID
     * @returns {Promise<Object>} Conversation object
     */
    async getConversation(id) {
        try {
            return await this.db.conversations.get(id);
        } catch (error) {
            console.error('Failed to get conversation:', error);
            return null;
        }
    }

    /**
     * Update conversation
     * @param {number} id - Conversation ID
     * @param {Object} updates - Fields to update
     * @returns {Promise<void>}
     */
    async updateConversation(id, updates) {
        try {
            await this.db.conversations.update(id, {
                ...updates,
                updatedAt: new Date().toISOString()
            });
            console.log(`Updated conversation ${id}`);
        } catch (error) {
            console.error('Failed to update conversation:', error);
            throw error;
        }
    }

    /**
     * Delete conversation and all its messages
     * @param {number} id - Conversation ID
     * @returns {Promise<void>}
     */
    async deleteConversation(id) {
        try {
            // Delete all messages
            await this.db.messages.where('conversationId').equals(id).delete();

            // Delete conversation
            await this.db.conversations.delete(id);

            console.log(`Deleted conversation ${id}`);

            // If it was the current conversation, create a new one
            if (this.currentConversationId === id) {
                this.currentConversationId = await this.createConversation('New Conversation');
            }
        } catch (error) {
            console.error('Failed to delete conversation:', error);
            throw error;
        }
    }

    /**
     * Save a message
     * @param {number} conversationId - Conversation ID
     * @param {Object} messageData - Message data (type, message, timestamp)
     * @returns {Promise<number>} Message ID
     */
    async saveMessage(conversationId, messageData) {
        try {
            const id = await this.db.messages.add({
                conversationId,
                type: messageData.type,
                message: messageData.message,
                timestamp: messageData.timestamp || new Date().toISOString()
            });

            // Update conversation updatedAt
            await this.updateConversation(conversationId, {});

            return id;
        } catch (error) {
            console.error('Failed to save message:', error);
            throw error;
        }
    }

    /**
     * Load all messages for a conversation
     * @param {number} conversationId - Conversation ID
     * @returns {Promise<Array>} Array of messages
     */
    async loadMessages(conversationId) {
        try {
            return await this.db.messages
                .where('conversationId')
                .equals(conversationId)
                .sortBy('timestamp');
        } catch (error) {
            console.error('Failed to load messages:', error);
            return [];
        }
    }

    /**
     * Search messages across all conversations
     * @param {string} query - Search query
     * @param {number} limit - Max results
     * @returns {Promise<Array>} Array of matching messages
     */
    async searchMessages(query, limit = 50) {
        if (!query || query.trim() === '') {
            return [];
        }

        try {
            const lowerQuery = query.toLowerCase();

            // Get all messages and filter (Dexie doesn't support full-text search out of box)
            const messages = await this.db.messages
                .filter(msg => msg.message.toLowerCase().includes(lowerQuery))
                .limit(limit)
                .toArray();

            // Get conversation info for each message
            const results = await Promise.all(
                messages.map(async (msg) => {
                    const conversation = await this.getConversation(msg.conversationId);
                    return {
                        ...msg,
                        conversationTitle: conversation?.title || 'Unknown'
                    };
                })
            );

            return results;
        } catch (error) {
            console.error('Failed to search messages:', error);
            return [];
        }
    }

    /**
     * Get message count for a conversation
     * @param {number} conversationId - Conversation ID
     * @returns {Promise<number>} Message count
     */
    async getMessageCount(conversationId) {
        try {
            return await this.db.messages
                .where('conversationId')
                .equals(conversationId)
                .count();
        } catch (error) {
            console.error('Failed to get message count:', error);
            return 0;
        }
    }

    /**
     * Switch to a different conversation
     * @param {number} conversationId - Conversation ID
     * @returns {Promise<Array>} Messages in the conversation
     */
    async switchConversation(conversationId) {
        this.currentConversationId = conversationId;
        localStorage.setItem('currentConversationId', conversationId);
        return this.loadMessages(conversationId);
    }

    /**
     * Clear all data (for testing/debugging)
     * @returns {Promise<void>}
     */
    async clearAll() {
        try {
            await this.db.messages.clear();
            await this.db.conversations.clear();
            localStorage.removeItem('currentConversationId');
            console.log('All data cleared');

            // Create new conversation
            this.currentConversationId = await this.createConversation('New Conversation');
        } catch (error) {
            console.error('Failed to clear data:', error);
            throw error;
        }
    }
}

// Export singleton instance
export const storage = new StorageService();

// Export helper functions for sidebar
export async function getAllConversations() {
    return storage.listConversations();
}

export async function createNewConversation() {
    const now = new Date();
    const dateStr = now.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    const title = `Conversation - ${dateStr}`;
    const id = await storage.createConversation(title);
    return await storage.getConversation(id);
}

export async function deleteConversation(id) {
    return storage.deleteConversation(id);
}

export async function getCurrentConversationId() {
    return storage.currentConversationId || (await storage.getCurrentConversation());
}

export async function setCurrentConversationId(id) {
    return storage.switchConversation(id);
}

// Make available globally for debugging
if (typeof window !== 'undefined') {
    window.storage = storage;
    window.db = storage.db;
}
