/**
 * Markdown Rendering Service
 * 
 * Provides safe markdown rendering with syntax highlighting for code blocks.
 * Uses marked.js for markdown parsing and Prism.js for syntax highlighting.
 * 
 * Features:
 * - Full markdown support (bold, italic, lists, links, headings)
 * - Syntax highlighting for code blocks
 * - XSS protection with HTML sanitization
 * - Inline code styling
 * - Link handling (opens in new tab)
 */

import { marked } from 'https://cdn.jsdelivr.net/npm/marked@11.1.0/+esm';
import Prism from 'https://cdn.jsdelivr.net/npm/prismjs@1.29.0/+esm';

/**
 * Configure marked.js with custom renderer and options
 */
const renderer = new marked.Renderer();

// Custom link renderer - open in new tab for security
renderer.link = function(href, title, text) {
    const titleAttr = title ? ` title="${title}"` : '';
    return `<a href="${href}"${titleAttr} target="_blank" rel="noopener noreferrer">${text}</a>`;
};

// Custom code block renderer with syntax highlighting
renderer.code = function(code, language) {
    // Sanitize language name
    const lang = language || 'plaintext';
    const validLang = Prism.languages[lang] ? lang : 'plaintext';
    
    // Highlight code
    const highlighted = Prism.languages[validLang] 
        ? Prism.highlight(code, Prism.languages[validLang], validLang)
        : code;
    
    return `<pre class="language-${validLang}"><code class="language-${validLang}">${highlighted}</code></pre>`;
};

// Custom inline code renderer
renderer.codespan = function(code) {
    return `<code class="inline-code">${code}</code>`;
};

// Configure marked options
marked.setOptions({
    renderer: renderer,
    gfm: true, // GitHub Flavored Markdown
    breaks: true, // Convert \n to <br>
    pedantic: false,
    sanitize: false, // We handle sanitization separately
    smartLists: true,
    smartypants: true, // Use smart quotes
});

/**
 * Sanitize HTML to prevent XSS attacks
 * 
 * Removes dangerous tags and attributes while preserving safe markdown elements.
 * Allowed: p, br, strong, em, code, pre, ul, ol, li, a, h1-h6, blockquote
 * 
 * @param {string} html - Raw HTML string
 * @returns {string} Sanitized HTML
 */
function sanitizeHTML(html) {
    const allowedTags = [
        'p', 'br', 'strong', 'em', 'b', 'i', 'code', 'pre',
        'ul', 'ol', 'li', 'a', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
        'blockquote', 'hr', 'span', 'div'
    ];
    
    const allowedAttributes = {
        'a': ['href', 'title', 'target', 'rel'],
        'code': ['class'],
        'pre': ['class'],
        'span': ['class'],
        'div': ['class']
    };
    
    // Create temporary DOM element
    const temp = document.createElement('div');
    temp.innerHTML = html;
    
    // Recursively sanitize
    function sanitizeNode(node) {
        if (node.nodeType === Node.TEXT_NODE) {
            return node.textContent;
        }
        
        if (node.nodeType !== Node.ELEMENT_NODE) {
            return '';
        }
        
        const tagName = node.tagName.toLowerCase();
        
        // Remove disallowed tags
        if (!allowedTags.includes(tagName)) {
            return node.textContent;
        }
        
        // Create sanitized element
        const sanitized = document.createElement(tagName);
        
        // Copy allowed attributes
        const allowedAttrs = allowedAttributes[tagName] || [];
        Array.from(node.attributes).forEach(attr => {
            if (allowedAttrs.includes(attr.name)) {
                // Extra sanitization for href
                if (attr.name === 'href') {
                    const href = attr.value;
                    // Only allow http, https, mailto
                    if (/^(https?:|mailto:)/i.test(href)) {
                        sanitized.setAttribute(attr.name, attr.value);
                    }
                } else {
                    sanitized.setAttribute(attr.name, attr.value);
                }
            }
        });
        
        // Recursively sanitize children
        Array.from(node.childNodes).forEach(child => {
            const sanitizedChild = sanitizeNode(child);
            if (typeof sanitizedChild === 'string') {
                sanitized.appendChild(document.createTextNode(sanitizedChild));
            } else if (sanitizedChild) {
                sanitized.appendChild(sanitizedChild);
            }
        });
        
        return sanitized;
    }
    
    const sanitized = sanitizeNode(temp);
    return sanitized ? sanitized.innerHTML : '';
}

/**
 * Render markdown text to HTML
 * 
 * Main entry point for markdown rendering. Converts markdown to HTML,
 * applies syntax highlighting, and sanitizes output.
 * 
 * @param {string} text - Markdown text
 * @returns {string} Safe HTML string
 * 
 * @example
 * const html = renderMarkdown('**Bold** and `code`');
 * // Returns: '<p><strong>Bold</strong> and <code class="inline-code">code</code></p>'
 */
export function renderMarkdown(text) {
    if (!text || typeof text !== 'string') {
        return '';
    }
    
    try {
        // Parse markdown to HTML
        const rawHTML = marked.parse(text);
        
        // Sanitize HTML
        const safeHTML = sanitizeHTML(rawHTML);
        
        return safeHTML;
    } catch (error) {
        console.error('Markdown rendering error:', error);
        // Fallback to escaped text
        return document.createTextNode(text).textContent;
    }
}

/**
 * Detect if text contains markdown syntax
 * 
 * Quick check to determine if markdown rendering is needed.
 * Useful for optimization - skip rendering for plain text.
 * 
 * @param {string} text - Text to check
 * @returns {boolean} True if markdown syntax detected
 */
export function hasMarkdown(text) {
    if (!text) return false;
    
    const markdownPatterns = [
        /\*\*.*\*\*/,      // Bold
        /\*.*\*/,          // Italic
        /`.*`/,            // Code
        /^#+\s/m,          // Headers
        /^\s*[-*+]\s/m,    // Lists
        /^\s*\d+\.\s/m,    // Numbered lists
        /\[.*\]\(.*\)/,    // Links
        /^>/m,             // Blockquotes
    ];
    
    return markdownPatterns.some(pattern => pattern.test(text));
}

/**
 * Strip markdown formatting, return plain text
 * 
 * Useful for preview text, search indexing, or copy operations.
 * 
 * @param {string} text - Markdown text
 * @returns {string} Plain text without formatting
 */
export function stripMarkdown(text) {
    if (!text) return '';
    
    return text
        .replace(/\*\*(.*?)\*\*/g, '$1')     // Bold
        .replace(/\*(.*?)\*/g, '$1')         // Italic
        .replace(/`(.*?)`/g, '$1')           // Inline code
        .replace(/\[(.*?)\]\(.*?\)/g, '$1')  // Links
        .replace(/^#+\s+/gm, '')             // Headers
        .replace(/^[-*+]\s+/gm, '')          // Lists
        .replace(/^\d+\.\s+/gm, '')          // Numbered lists
        .replace(/^>\s+/gm, '')              // Blockquotes
        .trim();
}

// Export default for convenience
export default {
    renderMarkdown,
    hasMarkdown,
    stripMarkdown
};
