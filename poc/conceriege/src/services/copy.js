/**
 * Clipboard Copy Utilities
 *
 * Provides clipboard copy functionality with fallback support.
 * Handles both modern Clipboard API and legacy execCommand.
 *
 * Usage:
 *   import { copyToClipboard } from './copy.js';
 *   await copyToClipboard('text to copy');
 */

/**
 * Copy text to clipboard
 * Uses modern Clipboard API with fallback to execCommand
 *
 * @param {string} text - Text to copy
 * @returns {Promise<boolean>} True if successful
 */
export async function copyToClipboard(text) {
    if (!text) {
        console.warn('No text provided to copy');
        return false;
    }

    // Try modern Clipboard API first
    if (navigator.clipboard && navigator.clipboard.writeText) {
        try {
            await navigator.clipboard.writeText(text);
            return true;
        } catch (error) {
            console.warn('Clipboard API failed, trying fallback:', error);
            // Fall through to fallback
        }
    }

    // Fallback to execCommand (works in older browsers)
    return copyToClipboardFallback(text);
}

/**
 * Fallback copy method using execCommand
 *
 * @param {string} text - Text to copy
 * @returns {boolean} True if successful
 */
function copyToClipboardFallback(text) {
    // Create temporary textarea
    const textarea = document.createElement('textarea');
    textarea.value = text;

    // Make it invisible
    textarea.style.position = 'fixed';
    textarea.style.top = '0';
    textarea.style.left = '0';
    textarea.style.width = '2em';
    textarea.style.height = '2em';
    textarea.style.padding = '0';
    textarea.style.border = 'none';
    textarea.style.outline = 'none';
    textarea.style.boxShadow = 'none';
    textarea.style.background = 'transparent';
    textarea.style.opacity = '0';

    // Add to DOM
    document.body.appendChild(textarea);

    // Select text
    textarea.focus();
    textarea.select();

    // Try to copy
    let successful = false;
    try {
        successful = document.execCommand('copy');
    } catch (error) {
        console.error('execCommand copy failed:', error);
    }

    // Clean up
    document.body.removeChild(textarea);

    return successful;
}

/**
 * Check if clipboard API is available
 *
 * @returns {boolean} True if available
 */
export function isClipboardAvailable() {
    return !!(navigator.clipboard && navigator.clipboard.writeText);
}

/**
 * Copy HTML content (preserving formatting)
 * Only works with modern Clipboard API
 *
 * @param {string} html - HTML content to copy
 * @param {string} plainText - Plain text fallback
 * @returns {Promise<boolean>} True if successful
 */
export async function copyHTMLToClipboard(html, plainText) {
    if (!navigator.clipboard || !navigator.clipboard.write) {
        console.warn('HTML clipboard not supported, falling back to plain text');
        return copyToClipboard(plainText);
    }

    try {
        const htmlBlob = new Blob([html], { type: 'text/html' });
        const textBlob = new Blob([plainText], { type: 'text/plain' });

        const clipboardItem = new ClipboardItem({
            'text/html': htmlBlob,
            'text/plain': textBlob
        });

        await navigator.clipboard.write([clipboardItem]);
        return true;
    } catch (error) {
        console.error('HTML clipboard copy failed:', error);
        // Fallback to plain text
        return copyToClipboard(plainText);
    }
}

/**
 * Extract plain text from HTML element (for copying)
 *
 * @param {HTMLElement} element - Element to extract text from
 * @returns {string} Plain text content
 */
export function extractTextFromElement(element) {
    // Clone element to avoid modifying original
    const clone = element.cloneNode(true);

    // Remove copy buttons and other UI elements
    clone.querySelectorAll('.copy-button, .timestamp').forEach(el => el.remove());

    // Get text content
    return clone.textContent || clone.innerText || '';
}

/**
 * Copy message bubble content
 * Extracts text from bubble and copies to clipboard
 *
 * @param {HTMLElement} messageElement - Message element
 * @returns {Promise<boolean>} True if successful
 */
export async function copyMessageContent(messageElement) {
    const bubble = messageElement.querySelector('.message-bubble');
    if (!bubble) {
        console.warn('No message bubble found');
        return false;
    }

    const text = extractTextFromElement(bubble);
    return copyToClipboard(text);
}
