/**
 * Search Service for Conversation Search
 *
 * Provides full-text search across all saved conversations with:
 * - Debounced search input (300ms)
 * - Result highlighting
 * - Click-to-load conversation
 * - Performance optimized for 100+ messages
 *
 * Usage:
 *   import { searchService } from './search.js';
 *   searchService.init(storage, onResultClick);
 *   await searchService.search('query');
 */

class SearchService {
    constructor() {
        this.storage = null;
        this.onResultClick = null;
        this.searchTimeout = null;
        this.debounceDelay = 300; // ms
        this.lastQuery = '';
        this.isSearching = false;
    }

    /**
     * Initialize search service
     * @param {Object} storage - Storage service instance
     * @param {Function} onResultClick - Callback when result is clicked (conversationId, messageId)
     */
    init(storage, onResultClick) {
        this.storage = storage;
        this.onResultClick = onResultClick;
    }

    /**
     * Debounced search function
     * @param {string} query - Search query
     * @param {Function} callback - Callback with results
     */
    debouncedSearch(query, callback) {
        // Clear existing timeout
        if (this.searchTimeout) {
            clearTimeout(this.searchTimeout);
        }

        // Set new timeout
        this.searchTimeout = setTimeout(async () => {
            const results = await this.search(query);
            callback(results);
        }, this.debounceDelay);
    }

    /**
     * Execute search
     * @param {string} query - Search query
     * @returns {Promise<Array>} Search results with highlights
     */
    async search(query) {
        if (!query || query.trim() === '') {
            return [];
        }

        this.lastQuery = query;
        this.isSearching = true;

        const startTime = performance.now();

        try {
            // Get raw results from storage
            const rawResults = await this.storage.searchMessages(query, 50);

            // Add highlights and format results
            const results = rawResults.map(msg => ({
                id: msg.id,
                conversationId: msg.conversationId,
                conversationTitle: msg.conversationTitle,
                type: msg.type,
                message: msg.message,
                timestamp: msg.timestamp,
                // Add highlighted snippet
                snippet: this.createHighlightedSnippet(msg.message, query)
            }));

            const endTime = performance.now();
            const duration = (endTime - startTime).toFixed(2);

            console.log(`Search completed in ${duration}ms: ${results.length} results for "${query}"`);

            return results;
        } catch (error) {
            console.error('Search failed:', error);
            return [];
        } finally {
            this.isSearching = false;
        }
    }

    /**
     * Create highlighted snippet around search query
     * @param {string} text - Full message text
     * @param {string} query - Search query
     * @param {number} contextLength - Characters to show before/after match
     * @returns {string} HTML snippet with highlighted query
     */
    createHighlightedSnippet(text, query, contextLength = 80) {
        const lowerText = text.toLowerCase();
        const lowerQuery = query.toLowerCase();

        // Find first occurrence
        const index = lowerText.indexOf(lowerQuery);

        if (index === -1) {
            // No match found (shouldn't happen), return start of text
            return this.escapeHtml(text.substring(0, contextLength * 2)) + '...';
        }

        // Calculate snippet boundaries
        const start = Math.max(0, index - contextLength);
        const end = Math.min(text.length, index + query.length + contextLength);

        // Extract snippet
        let snippet = text.substring(start, end);

        // Add ellipsis if truncated
        if (start > 0) snippet = '...' + snippet;
        if (end < text.length) snippet = snippet + '...';

        // Highlight all occurrences of query in snippet
        const escapedSnippet = this.escapeHtml(snippet);
        const regex = new RegExp(`(${this.escapeRegex(query)})`, 'gi');
        const highlighted = escapedSnippet.replace(regex, '<mark>$1</mark>');

        return highlighted;
    }

    /**
     * Escape HTML to prevent XSS
     * @param {string} text - Text to escape
     * @returns {string} Escaped text
     */
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    /**
     * Escape regex special characters
     * @param {string} text - Text to escape
     * @returns {string} Escaped text
     */
    escapeRegex(text) {
        return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    }

    /**
     * Format timestamp for display
     * @param {string} timestamp - ISO timestamp
     * @returns {string} Formatted timestamp
     */
    formatTimestamp(timestamp) {
        const date = new Date(timestamp);
        const now = new Date();
        const diffMs = now - date;
        const diffMins = Math.floor(diffMs / 60000);
        const diffHours = Math.floor(diffMs / 3600000);
        const diffDays = Math.floor(diffMs / 86400000);

        if (diffMins < 1) return 'Just now';
        if (diffMins < 60) return `${diffMins}m ago`;
        if (diffHours < 24) return `${diffHours}h ago`;
        if (diffDays < 7) return `${diffDays}d ago`;

        // Format as date
        return date.toLocaleDateString('en-US', {
            month: 'short',
            day: 'numeric',
            year: date.getFullYear() !== now.getFullYear() ? 'numeric' : undefined
        });
    }

    /**
     * Handle result click
     * @param {number} conversationId - Conversation ID
     * @param {number} messageId - Message ID
     */
    handleResultClick(conversationId, messageId) {
        if (this.onResultClick) {
            this.onResultClick(conversationId, messageId);
        }
    }

    /**
     * Clear search
     */
    clear() {
        this.lastQuery = '';
        if (this.searchTimeout) {
            clearTimeout(this.searchTimeout);
            this.searchTimeout = null;
        }
    }

    /**
     * Get performance stats
     * @returns {Object} Performance statistics
     */
    getStats() {
        return {
            lastQuery: this.lastQuery,
            isSearching: this.isSearching,
            debounceDelay: this.debounceDelay
        };
    }
}

// Export singleton instance
export const searchService = new SearchService();

// Make available globally for debugging
if (typeof window !== 'undefined') {
    window.searchService = searchService;
}
