# 🗺️ Web UI Implementation Roadmap
## Milestone → Epic → Issue Breakdown

**Project:** Concierge V2 Web UI - World-Class Transformation
**Duration:** 3 weeks (90 hours)
**Start Date:** November 8, 2025
**Target Completion:** November 29, 2025

---

## 📊 Milestone Overview

| Milestone | Duration | Issues | Story Points | Priority |
|-----------|----------|--------|--------------|----------|
| **M1: Professional Foundation** | Week 1 (30h) | 28 issues | 60 pts | 🔴 Critical |
| **M2: Smart Features** | Week 2 (30h) | 24 issues | 55 pts | 🟡 High |
| **M3: Production Polish** | Week 3 (30h) | 18 issues | 45 pts | 🟢 Medium |
| **Total** | 3 weeks (90h) | 70 issues | 160 pts | - |

---

## 🎯 Milestone 1: Professional Foundation (Week 1)

**Goal:** Transform from functional to professional
**Duration:** 30 hours
**Completion Criteria:** Markdown rendering, dark mode, persistence, agent visualization

---

### Epic 1.1: Markdown Rendering System

**Story:** As a user, I want to see beautifully formatted responses with code blocks, lists, and links so that information is easier to read and understand.

**Acceptance Criteria:**
- [ ] Bold, italic, strikethrough text rendered correctly
- [ ] Code blocks with syntax highlighting (10+ languages)
- [ ] Inline code with distinct styling
- [ ] Ordered and unordered lists rendered
- [ ] Links clickable with preview on hover
- [ ] Tables rendered with proper borders
- [ ] Blockquotes styled distinctly

**Total Points:** 13 pts (4 hours)

---

#### Issue #1: Set up markdown parsing library
**Labels:** `setup`, `dependencies`, `M1-Epic1.1`
**Story Points:** 1 pt (15 min)
**Assignee:** Developer

**Description:**
Install and configure `marked` library for markdown parsing.

**Tasks:**
- [ ] Run `npm install marked`
- [ ] Add import statement in service file
- [ ] Configure marked options (breaks, gfm, sanitize)
- [ ] Test basic markdown parsing (console.log test)

**Acceptance Criteria:**
- [ ] marked@11.0.0 or higher installed
- [ ] No npm vulnerabilities
- [ ] Basic markdown string parses correctly

**Code Location:** `src/services/markdown.js`

---

#### Issue #2: Set up syntax highlighting library
**Labels:** `setup`, `dependencies`, `M1-Epic1.1`
**Story Points:** 1 pt (15 min)

**Description:**
Install and configure Prism.js for code syntax highlighting.

**Tasks:**
- [ ] Run `npm install prismjs`
- [ ] Import Prism core
- [ ] Import theme CSS (prism-tomorrow.css)
- [ ] Import language modules (js, python, typescript, bash, json)
- [ ] Test syntax highlighting (console test)

**Acceptance Criteria:**
- [ ] prismjs@1.29.0 or higher installed
- [ ] Dark theme CSS loaded
- [ ] At least 5 languages work

**Code Location:** `src/services/markdown.js`

---

#### Issue #3: Create markdown rendering service
**Labels:** `feature`, `core`, `M1-Epic1.1`
**Story Points:** 2 pts (30 min)

**Description:**
Create service module to parse markdown and highlight code.

**Tasks:**
- [ ] Create `src/services/markdown.js`
- [ ] Write `renderMarkdown(text)` function
- [ ] Configure marked with highlight callback
- [ ] Add Prism language detection
- [ ] Handle edge cases (empty string, null, undefined)
- [ ] Add error handling (try-catch)
- [ ] Write JSDoc comments

**Acceptance Criteria:**
- [ ] Function accepts string, returns HTML
- [ ] Code blocks highlighted correctly
- [ ] No XSS vulnerabilities (sanitization)
- [ ] Handles edge cases gracefully

**Code Location:** `src/services/markdown.js`

**Example:**
```javascript
import { marked } from 'marked';
import Prism from 'prismjs';

export function renderMarkdown(text) {
  if (!text) return '';

  try {
    return marked.parse(text);
  } catch (error) {
    console.error('Markdown parsing error:', error);
    return text; // Fallback to plain text
  }
}
```

---

#### Issue #4: Integrate markdown rendering into message display
**Labels:** `feature`, `integration`, `M1-Epic1.1`
**Story Points:** 2 pts (30 min)

**Description:**
Replace plain text rendering with markdown in message bubbles.

**Tasks:**
- [ ] Import `renderMarkdown` in main app
- [ ] Update `addMessage()` function to use `innerHTML`
- [ ] Change from `textContent` to `innerHTML`
- [ ] Test with sample messages
- [ ] Verify no layout breaks

**Acceptance Criteria:**
- [ ] Bold text renders as `<strong>`
- [ ] Code blocks have proper `<pre><code>` structure
- [ ] Lists render with `<ul>`/`<ol>`
- [ ] No text escaping issues

**Code Location:** `web_ui.py` or `src/main.js`

**Before:**
```javascript
bubble.textContent = data.message;
```

**After:**
```javascript
bubble.innerHTML = renderMarkdown(data.message);
```

---

#### Issue #5: Style code blocks with dark theme
**Labels:** `styling`, `css`, `M1-Epic1.1`
**Story Points:** 2 pts (30 min)

**Description:**
Add CSS for code block styling with dark background.

**Tasks:**
- [ ] Add `<pre>` styles (padding, border-radius, background)
- [ ] Add `<code>` font (monospace)
- [ ] Import Prism Tomorrow theme CSS
- [ ] Add line number styles (optional)
- [ ] Test on multiple code blocks
- [ ] Ensure scrollbar for long code

**Acceptance Criteria:**
- [ ] Dark background (#2d2d2d)
- [ ] Monospace font (Fira Code or Courier)
- [ ] Horizontal scroll for overflow
- [ ] Matches design system colors

**Code Location:** `src/styles/markdown.css` or `<style>` block

```css
pre {
  background: #2d2d2d;
  border-radius: 8px;
  padding: 16px;
  overflow-x: auto;
  margin: 12px 0;
}

code {
  font-family: 'Fira Code', 'Courier New', monospace;
  font-size: 14px;
  line-height: 1.5;
  color: #e5e5e5;
}

:not(pre) > code {
  background: rgba(0, 0, 0, 0.1);
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 0.9em;
}
```

---

#### Issue #6: Style inline code elements
**Labels:** `styling`, `css`, `M1-Epic1.1`
**Story Points:** 1 pt (15 min)

**Description:**
Add distinct styling for inline `code` elements.

**Tasks:**
- [ ] Add background color for inline code
- [ ] Add padding (2px 6px)
- [ ] Add border-radius (4px)
- [ ] Slightly reduce font size (0.9em)
- [ ] Test in light and dark themes

**Acceptance Criteria:**
- [ ] Inline code distinguishable from plain text
- [ ] Background contrasts with message bubble
- [ ] Font size proportional

**Code Location:** `src/styles/markdown.css`

---

#### Issue #7: Add support for markdown lists
**Labels:** `feature`, `markdown`, `M1-Epic1.1`
**Story Points:** 1 pt (15 min)

**Description:**
Ensure ordered and unordered lists render correctly.

**Tasks:**
- [ ] Add `<ul>` styles (margin, padding)
- [ ] Add `<ol>` styles (numbering)
- [ ] Add `<li>` styles (spacing)
- [ ] Test nested lists (2-3 levels)
- [ ] Test mixed list types

**Acceptance Criteria:**
- [ ] Lists have proper indentation
- [ ] Bullets visible
- [ ] Nested lists work
- [ ] Spacing between list items

**Code Location:** `src/styles/markdown.css`

```css
.message-bubble ul,
.message-bubble ol {
  margin: 8px 0;
  padding-left: 24px;
}

.message-bubble li {
  margin: 4px 0;
}
```

---

#### Issue #8: Add support for markdown links
**Labels:** `feature`, `markdown`, `M1-Epic1.1`
**Story Points:** 2 pts (30 min)

**Description:**
Style links and add external link indicators.

**Tasks:**
- [ ] Add link color (primary brand color)
- [ ] Add hover effect (underline)
- [ ] Add external link icon (optional)
- [ ] Add `target="_blank"` for external links
- [ ] Add `rel="noopener noreferrer"` for security
- [ ] Test link clicking

**Acceptance Criteria:**
- [ ] Links clickable
- [ ] Hover state visible
- [ ] External links open in new tab
- [ ] No security warnings

**Code Location:** `src/styles/markdown.css`

```css
.message-bubble a {
  color: var(--primary-600);
  text-decoration: none;
  border-bottom: 1px solid transparent;
  transition: border-color 0.2s;
}

.message-bubble a:hover {
  border-bottom-color: var(--primary-600);
}
```

---

#### Issue #9: Test markdown rendering with edge cases
**Labels:** `testing`, `qa`, `M1-Epic1.1`
**Story Points:** 1 pt (15 min)

**Description:**
Test markdown with edge cases to ensure robustness.

**Tasks:**
- [ ] Test empty message
- [ ] Test null/undefined
- [ ] Test very long code blocks (100+ lines)
- [ ] Test nested markdown (bold in lists)
- [ ] Test invalid markdown syntax
- [ ] Test XSS attempts (`<script>alert()</script>`)
- [ ] Document any issues found

**Acceptance Criteria:**
- [ ] No crashes on edge cases
- [ ] No XSS vulnerabilities
- [ ] Graceful degradation

**Test Cases:**
```javascript
const edgeCases = [
  "",
  null,
  undefined,
  "**bold** *italic* `code`",
  "```javascript\n" + "x".repeat(5000) + "\n```",
  "<script>alert('XSS')</script>",
  "- Item 1\n  - **Nested bold**\n    - `code`"
];
```

---

### Epic 1.2: Dark Mode System

**Story:** As a user, I want to toggle between light and dark themes so that I can use the app comfortably at any time of day.

**Acceptance Criteria:**
- [ ] Toggle button in header
- [ ] Theme persists across sessions (localStorage)
- [ ] Smooth transition animation (0.3s)
- [ ] All colors adapt to theme
- [ ] No flashing on page load
- [ ] System preference detection (prefers-color-scheme)

**Total Points:** 8 pts (3 hours)

---

#### Issue #10: Define CSS custom properties for theming
**Labels:** `setup`, `css`, `M1-Epic1.2`
**Story Points:** 1 pt (15 min)

**Description:**
Create CSS variables for all theme-dependent colors.

**Tasks:**
- [ ] Create `src/styles/themes.css`
- [ ] Define `:root` variables for light theme
- [ ] Define `[data-theme="dark"]` variables
- [ ] Include background, text, surface, border colors
- [ ] Test variable fallbacks

**Acceptance Criteria:**
- [ ] At least 10 color variables defined
- [ ] Light and dark variants for each
- [ ] Variables follow naming convention (--color-purpose)

**Code Location:** `src/styles/themes.css`

```css
:root {
  /* Light theme (default) */
  --bg-primary: #ffffff;
  --bg-secondary: #f5f5f5;
  --text-primary: #1a1a1a;
  --text-secondary: #6b7280;
  --surface: #ffffff;
  --border: #e5e7eb;
  --primary-600: #667eea;
  --primary-700: #764ba2;
}

[data-theme="dark"] {
  /* Dark theme */
  --bg-primary: #1a1a1a;
  --bg-secondary: #2d2d2d;
  --text-primary: #e5e5e5;
  --text-secondary: #9ca3af;
  --surface: #2d2d2d;
  --border: #374151;
  --primary-600: #7c94f5;
  --primary-700: #8b5fbf;
}
```

---

#### Issue #11: Replace hardcoded colors with CSS variables
**Labels:** `refactor`, `css`, `M1-Epic1.2`
**Story Points:** 2 pts (30 min)

**Description:**
Update all hardcoded color values to use CSS variables.

**Tasks:**
- [ ] Find all hardcoded colors in stylesheet
- [ ] Replace with appropriate CSS variables
- [ ] Test in both light and dark themes
- [ ] Verify no color regressions
- [ ] Update gradient backgrounds

**Acceptance Criteria:**
- [ ] Zero hardcoded color values (except variables)
- [ ] All colors transition with theme
- [ ] No visual regressions

**Code Location:** All CSS files

**Before:**
```css
body {
  background: #f5f5f5;
  color: #1a1a1a;
}
```

**After:**
```css
body {
  background: var(--bg-secondary);
  color: var(--text-primary);
}
```

---

#### Issue #12: Create theme toggle button component
**Labels:** `feature`, `ui`, `M1-Epic1.2`
**Story Points:** 2 pts (30 min)

**Description:**
Add toggle button in header to switch themes.

**Tasks:**
- [ ] Add button to header HTML
- [ ] Add sun/moon icons (☀️/🌙 or SVG)
- [ ] Add click event listener
- [ ] Toggle `data-theme` attribute on `<html>`
- [ ] Add transition class to body
- [ ] Style button (hover, active states)

**Acceptance Criteria:**
- [ ] Button visible in header
- [ ] Icons change based on theme
- [ ] Clicking toggles theme
- [ ] Smooth transition

**Code Location:** `web_ui.py` HTML template

```html
<button id="theme-toggle" aria-label="Toggle dark mode">
  <span class="icon-light">☀️</span>
  <span class="icon-dark">🌙</span>
</button>
```

```javascript
const themeToggle = document.getElementById('theme-toggle');
themeToggle.addEventListener('click', () => {
  const html = document.documentElement;
  const currentTheme = html.getAttribute('data-theme');
  const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
  html.setAttribute('data-theme', newTheme);
  localStorage.setItem('theme', newTheme);
});
```

---

#### Issue #13: Persist theme preference in localStorage
**Labels:** `feature`, `storage`, `M1-Epic1.2`
**Story Points:** 1 pt (15 min)

**Description:**
Save theme preference and restore on page load.

**Tasks:**
- [ ] Save theme to localStorage on toggle
- [ ] Read theme from localStorage on page load
- [ ] Set `data-theme` attribute before page render
- [ ] Handle missing localStorage (default to light)
- [ ] Test in private browsing mode

**Acceptance Criteria:**
- [ ] Theme persists after refresh
- [ ] No flash of wrong theme
- [ ] Handles missing localStorage gracefully

**Code Location:** `src/main.js` or inline script

```javascript
// Run immediately (before body loads)
(function() {
  const savedTheme = localStorage.getItem('theme') || 'light';
  document.documentElement.setAttribute('data-theme', savedTheme);
})();
```

---

#### Issue #14: Detect system theme preference
**Labels:** `feature`, `enhancement`, `M1-Epic1.2`
**Story Points:** 1 pt (15 min)

**Description:**
Use system preference if user hasn't set theme.

**Tasks:**
- [ ] Check `window.matchMedia('(prefers-color-scheme: dark)')`
- [ ] Use system preference if localStorage empty
- [ ] Listen for system preference changes
- [ ] Update theme when system changes (optional)

**Acceptance Criteria:**
- [ ] System dark mode → app dark mode (if no preference)
- [ ] User preference overrides system
- [ ] No errors if API unavailable

**Code Location:** `src/main.js`

```javascript
function getInitialTheme() {
  const saved = localStorage.getItem('theme');
  if (saved) return saved;

  const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
  return prefersDark ? 'dark' : 'light';
}
```

---

#### Issue #15: Add smooth theme transition animation
**Labels:** `polish`, `css`, `M1-Epic1.2`
**Story Points:** 1 pt (15 min)

**Description:**
Add CSS transitions for smooth theme switching.

**Tasks:**
- [ ] Add transition to background-color
- [ ] Add transition to color
- [ ] Add transition to border-color
- [ ] Set duration to 0.3s
- [ ] Test transition smoothness
- [ ] Disable transitions on initial load

**Acceptance Criteria:**
- [ ] Colors fade smoothly (300ms)
- [ ] No layout shift during transition
- [ ] No transition on page load

**Code Location:** `src/styles/themes.css`

```css
body {
  transition: background-color 0.3s ease, color 0.3s ease;
}

.message-bubble {
  transition: background-color 0.3s ease, border-color 0.3s ease;
}

/* Disable transitions on page load */
body.no-transition * {
  transition: none !important;
}
```

```javascript
// Remove no-transition class after load
window.addEventListener('load', () => {
  setTimeout(() => {
    document.body.classList.remove('no-transition');
  }, 100);
});
```

---

### Epic 1.3: Message Copy Functionality

**Story:** As a user, I want to copy individual messages to my clipboard so that I can share responses or save them elsewhere.

**Acceptance Criteria:**
- [ ] Copy button appears on message hover
- [ ] Clicking copies message text to clipboard
- [ ] Toast notification confirms copy
- [ ] Works on mobile (tap to show button)
- [ ] Preserves markdown formatting (plain text)

**Total Points:** 5 pts (1.5 hours)

---

#### Issue #16: Create copy button component
**Labels:** `feature`, `ui`, `M1-Epic1.3`
**Story Points:** 1 pt (15 min)

**Description:**
Add copy button to message bubbles.

**Tasks:**
- [ ] Add copy button HTML to message template
- [ ] Position absolute (top-right of bubble)
- [ ] Add clipboard icon (📋 or SVG)
- [ ] Initially hidden (opacity: 0)
- [ ] Show on message hover
- [ ] Add aria-label for accessibility

**Acceptance Criteria:**
- [ ] Button positioned correctly
- [ ] Appears on hover
- [ ] Icon visible and sized properly

**Code Location:** Message rendering function

```javascript
const copyBtn = document.createElement('button');
copyBtn.className = 'copy-btn';
copyBtn.innerHTML = '📋';
copyBtn.setAttribute('aria-label', 'Copy message');
copyBtn.onclick = () => copyMessage(data.message);
bubble.appendChild(copyBtn);
```

```css
.copy-btn {
  position: absolute;
  top: 8px;
  right: 8px;
  background: rgba(255, 255, 255, 0.2);
  border: none;
  padding: 4px 8px;
  border-radius: 4px;
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.2s;
}

.message:hover .copy-btn {
  opacity: 1;
}
```

---

#### Issue #17: Implement clipboard copy functionality
**Labels:** `feature`, `core`, `M1-Epic1.3`
**Story Points:** 2 pts (30 min)

**Description:**
Use Clipboard API to copy text.

**Tasks:**
- [ ] Create `copyToClipboard(text)` function
- [ ] Use `navigator.clipboard.writeText()`
- [ ] Add fallback for unsupported browsers
- [ ] Handle permission errors
- [ ] Add try-catch error handling
- [ ] Test on multiple browsers

**Acceptance Criteria:**
- [ ] Copies text successfully
- [ ] Handles errors gracefully
- [ ] Works on Chrome, Firefox, Safari, Edge
- [ ] Fallback for old browsers

**Code Location:** `src/utils/clipboard.js`

```javascript
export async function copyToClipboard(text) {
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    } else {
      // Fallback for older browsers
      const textarea = document.createElement('textarea');
      textarea.value = text;
      textarea.style.position = 'fixed';
      textarea.style.opacity = '0';
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
      return true;
    }
  } catch (error) {
    console.error('Copy failed:', error);
    return false;
  }
}
```

---

#### Issue #18: Create toast notification component
**Labels:** `feature`, `ui`, `M1-Epic1.3`
**Story Points:** 2 pts (30 min)

**Description:**
Show temporary notification when copy succeeds.

**Tasks:**
- [ ] Create `showToast(message, type)` function
- [ ] Create toast HTML element
- [ ] Position fixed (bottom-right)
- [ ] Add slide-in animation
- [ ] Auto-dismiss after 3 seconds
- [ ] Support success/error types
- [ ] Style with colors

**Acceptance Criteria:**
- [ ] Toast appears on copy
- [ ] Disappears after 3s
- [ ] Multiple toasts stack vertically
- [ ] Animation smooth

**Code Location:** `src/utils/toast.js`

```javascript
export function showToast(message, type = 'success') {
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.textContent = message;
  document.body.appendChild(toast);

  // Trigger animation
  setTimeout(() => toast.classList.add('show'), 10);

  // Auto-dismiss
  setTimeout(() => {
    toast.classList.remove('show');
    setTimeout(() => toast.remove(), 300);
  }, 3000);
}
```

```css
.toast {
  position: fixed;
  bottom: 24px;
  right: 24px;
  padding: 12px 20px;
  border-radius: 8px;
  color: white;
  font-size: 14px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.2);
  transform: translateX(400px);
  transition: transform 0.3s ease;
  z-index: 9999;
}

.toast.show {
  transform: translateX(0);
}

.toast-success {
  background: #10b981;
}

.toast-error {
  background: #ef4444;
}
```

---

### Epic 1.4: Message Persistence with IndexedDB

**Story:** As a user, I want my conversations to be saved so that I can resume them after closing the browser.

**Acceptance Criteria:**
- [ ] Messages saved to IndexedDB automatically
- [ ] Conversations restored on page load
- [ ] Support for 50MB+ storage
- [ ] Conversation list with timestamps
- [ ] Delete individual conversations
- [ ] Clear all conversations option

**Total Points:** 13 pts (6 hours)

---

#### Issue #19: Set up Dexie.js IndexedDB wrapper
**Labels:** `setup`, `dependencies`, `M1-Epic1.4`
**Story Points:** 1 pt (15 min)

**Description:**
Install and configure Dexie for IndexedDB access.

**Tasks:**
- [ ] Run `npm install dexie`
- [ ] Create `src/services/storage.js`
- [ ] Initialize Dexie database
- [ ] Define schema with tables
- [ ] Test database creation

**Acceptance Criteria:**
- [ ] Dexie installed
- [ ] Database initializes without errors
- [ ] Tables created successfully

**Code Location:** `src/services/storage.js`

```javascript
import Dexie from 'dexie';

const db = new Dexie('ConciergeDB');

db.version(1).stores({
  messages: '++id, conversationId, timestamp, role, content',
  conversations: '++id, startedAt, lastMessageAt, title'
});

export default db;
```

---

#### Issue #20: Create message save function
**Labels:** `feature`, `storage`, `M1-Epic1.4`
**Story Points:** 2 pts (30 min)

**Description:**
Implement function to save messages to IndexedDB.

**Tasks:**
- [ ] Create `saveMessage(conversationId, role, content)` function
- [ ] Add timestamp to message
- [ ] Handle errors (quota exceeded, etc.)
- [ ] Return saved message ID
- [ ] Test with multiple messages

**Acceptance Criteria:**
- [ ] Messages saved successfully
- [ ] Returns message ID
- [ ] Handles errors gracefully

**Code Location:** `src/services/storage.js`

```javascript
export async function saveMessage(conversationId, role, content) {
  try {
    const id = await db.messages.add({
      conversationId,
      role, // 'user' or 'assistant'
      content,
      timestamp: Date.now()
    });

    // Update conversation lastMessageAt
    await db.conversations.update(conversationId, {
      lastMessageAt: Date.now()
    });

    return id;
  } catch (error) {
    console.error('Failed to save message:', error);
    throw error;
  }
}
```

---

#### Issue #21: Create conversation load function
**Labels:** `feature`, `storage`, `M1-Epic1.4`
**Story Points:** 2 pts (30 min)

**Description:**
Load messages from a conversation.

**Tasks:**
- [ ] Create `loadConversation(conversationId)` function
- [ ] Query messages by conversationId
- [ ] Sort by timestamp
- [ ] Return array of messages
- [ ] Handle missing conversation

**Acceptance Criteria:**
- [ ] Returns messages in order
- [ ] Empty array if conversation not found
- [ ] No errors on missing data

**Code Location:** `src/services/storage.js`

```javascript
export async function loadConversation(conversationId) {
  try {
    const messages = await db.messages
      .where('conversationId')
      .equals(conversationId)
      .sortBy('timestamp');

    return messages;
  } catch (error) {
    console.error('Failed to load conversation:', error);
    return [];
  }
}
```

---

#### Issue #22: Create new conversation function
**Labels:** `feature`, `storage`, `M1-Epic1.4`
**Story Points:** 1 pt (15 min)

**Description:**
Initialize a new conversation record.

**Tasks:**
- [ ] Create `createConversation(title)` function
- [ ] Generate conversation ID
- [ ] Save to conversations table
- [ ] Return conversation object
- [ ] Auto-generate title if empty

**Acceptance Criteria:**
- [ ] Conversation created with unique ID
- [ ] Returns conversation object
- [ ] Title optional (defaults to timestamp)

**Code Location:** `src/services/storage.js`

```javascript
export async function createConversation(title = null) {
  const id = await db.conversations.add({
    title: title || `Conversation ${new Date().toLocaleDateString()}`,
    startedAt: Date.now(),
    lastMessageAt: Date.now()
  });

  return { id, title };
}
```

---

#### Issue #23: List all conversations
**Labels:** `feature`, `storage`, `M1-Epic1.4`
**Story Points:** 1 pt (15 min)

**Description:**
Get list of all saved conversations.

**Tasks:**
- [ ] Create `listConversations()` function
- [ ] Sort by lastMessageAt (newest first)
- [ ] Include message count per conversation
- [ ] Return array of conversations

**Acceptance Criteria:**
- [ ] Returns all conversations
- [ ] Sorted newest first
- [ ] Includes metadata

**Code Location:** `src/services/storage.js`

```javascript
export async function listConversations() {
  const conversations = await db.conversations
    .orderBy('lastMessageAt')
    .reverse()
    .toArray();

  // Add message count
  for (const conv of conversations) {
    conv.messageCount = await db.messages
      .where('conversationId')
      .equals(conv.id)
      .count();
  }

  return conversations;
}
```

---

#### Issue #24: Delete conversation function
**Labels:** `feature`, `storage`, `M1-Epic1.4`
**Story Points:** 1 pt (15 min)

**Description:**
Delete conversation and all its messages.

**Tasks:**
- [ ] Create `deleteConversation(conversationId)` function
- [ ] Delete conversation record
- [ ] Delete all associated messages
- [ ] Use transaction for atomicity
- [ ] Confirm before delete

**Acceptance Criteria:**
- [ ] Conversation and messages deleted
- [ ] Atomic operation (all or nothing)
- [ ] Returns success boolean

**Code Location:** `src/services/storage.js`

```javascript
export async function deleteConversation(conversationId) {
  try {
    await db.transaction('rw', [db.conversations, db.messages], async () => {
      await db.conversations.delete(conversationId);
      await db.messages.where('conversationId').equals(conversationId).delete();
    });
    return true;
  } catch (error) {
    console.error('Failed to delete conversation:', error);
    return false;
  }
}
```

---

#### Issue #25: Integrate storage with message sending
**Labels:** `integration`, `M1-Epic1.4`
**Story Points:** 2 pts (30 min)

**Description:**
Auto-save messages when sent/received.

**Tasks:**
- [ ] Call `saveMessage()` when user sends message
- [ ] Call `saveMessage()` when agent responds
- [ ] Create conversation on first message if needed
- [ ] Handle save errors without blocking UI
- [ ] Show error toast if save fails

**Acceptance Criteria:**
- [ ] All messages auto-saved
- [ ] UI not blocked by saving
- [ ] Errors handled gracefully

**Code Location:** `src/main.js` or `web_ui.py`

```javascript
async function sendMessage() {
  const message = messageInput.value.trim();
  if (!message) return;

  // Save user message
  await saveMessage(currentConversationId, 'user', message);

  // Send to server
  ws.send(JSON.stringify({ message }));

  messageInput.value = '';
}

ws.onmessage = async (event) => {
  const data = JSON.parse(event.data);

  // Save assistant message
  await saveMessage(currentConversationId, 'assistant', data.message);

  // Display message
  addMessage(data);
};
```

---

#### Issue #26: Restore conversation on page load
**Labels:** `feature`, `integration`, `M1-Epic1.4`
**Story Points:** 2 pts (30 min)

**Description:**
Load and display last conversation on app start.

**Tasks:**
- [ ] Get last conversation ID from localStorage
- [ ] Load messages from IndexedDB
- [ ] Render messages in UI
- [ ] Scroll to bottom
- [ ] Handle first-time users (no conversations)

**Acceptance Criteria:**
- [ ] Last conversation restored
- [ ] Messages appear in order
- [ ] Scrolled to bottom
- [ ] Works for new users

**Code Location:** `src/main.js`

```javascript
async function initializeApp() {
  // Get or create conversation
  let conversationId = localStorage.getItem('currentConversationId');

  if (!conversationId) {
    const conv = await createConversation();
    conversationId = conv.id;
    localStorage.setItem('currentConversationId', conversationId);
  }

  // Load messages
  const messages = await loadConversation(conversationId);

  // Render messages
  messages.forEach(msg => {
    addMessage({
      type: msg.role === 'user' ? 'user_message' : 'agent_message',
      message: msg.content,
      timestamp: new Date(msg.timestamp).toISOString()
    });
  });

  // Scroll to bottom
  messagesDiv.scrollTop = messagesDiv.scrollHeight;
}
```

---

#### Issue #27: Check storage quota and handle limits
**Labels:** `feature`, `storage`, `M1-Epic1.4`
**Story Points:** 1 pt (15 min)

**Description:**
Monitor storage usage and warn user when approaching limit.

**Tasks:**
- [ ] Check available storage quota
- [ ] Calculate current usage
- [ ] Show warning at 80% capacity
- [ ] Offer to delete old conversations
- [ ] Log storage stats to console

**Acceptance Criteria:**
- [ ] Quota checked on load
- [ ] Warning shown at 80%
- [ ] User can free up space

**Code Location:** `src/services/storage.js`

```javascript
export async function checkStorageQuota() {
  if ('storage' in navigator && 'estimate' in navigator.storage) {
    const { usage, quota } = await navigator.storage.estimate();
    const percentUsed = (usage / quota) * 100;

    console.log(`Storage: ${(usage / 1024 / 1024).toFixed(2)}MB / ${(quota / 1024 / 1024).toFixed(2)}MB (${percentUsed.toFixed(1)}%)`);

    if (percentUsed > 80) {
      showToast('Storage almost full. Consider deleting old conversations.', 'warning');
    }

    return { usage, quota, percentUsed };
  }

  return null;
}
```

---

### Epic 1.5: Full-Text Conversation Search

**Story:** As a user, I want to search through all my conversations so that I can quickly find past advice and information.

**Acceptance Criteria:**
- [ ] Search box in sidebar
- [ ] Searches across all conversations
- [ ] Highlights matching text
- [ ] Shows conversation preview
- [ ] Click result to jump to conversation
- [ ] Real-time search (debounced)

**Total Points:** 8 pts (4 hours)

---

#### Issue #28: Create search input UI
**Labels:** `feature`, `ui`, `M1-Epic1.5`
**Story Points:** 1 pt (15 min)

**Description:**
Add search box to conversation sidebar.

**Tasks:**
- [ ] Add search input HTML
- [ ] Add search icon (🔍)
- [ ] Style input (border, padding, focus)
- [ ] Add placeholder text
- [ ] Position at top of sidebar

**Acceptance Criteria:**
- [ ] Search input visible
- [ ] Styled consistently
- [ ] Focus state works

**Code Location:** HTML template

```html
<div class="search-box">
  <span class="search-icon">🔍</span>
  <input
    type="search"
    id="conversation-search"
    placeholder="Search conversations..."
    aria-label="Search conversations"
  />
</div>
```

```css
.search-box {
  position: relative;
  margin: 16px;
}

.search-box input {
  width: 100%;
  padding: 8px 12px 8px 36px;
  border: 1px solid var(--border);
  border-radius: 8px;
  font-size: 14px;
}

.search-icon {
  position: absolute;
  left: 12px;
  top: 50%;
  transform: translateY(-50%);
}
```

---

**[Continue with remaining 42 issues...]**

---

## 🎯 Milestone 2: Smart Features (Week 2)

### Epic 2.1: Conversation Sidebar & History
### Epic 2.2: Agent Activity Visualization Panel
### Epic 2.3: Voice Input System
### Epic 2.4: File Attachment Support
### Epic 2.5: Conversation Export (PDF/Markdown)
### Epic 2.6: Message Reactions

**[24 issues total - detailed breakdown...]**

---

## 🎯 Milestone 3: Production Polish (Week 3)

### Epic 3.1: Keyboard Shortcuts System
### Epic 3.2: Accessibility (WCAG 2.1 AA)
### Epic 3.3: Mobile Optimization
### Epic 3.4: Connection Resilience
### Epic 3.5: Performance Optimization
### Epic 3.6: Analytics Dashboard

**[18 issues total - detailed breakdown...]**

---

## 📊 Issue Template

```markdown
### Issue #X: [Clear, actionable title]
**Labels:** `type`, `epic`, `milestone`
**Story Points:** X pts (Xh Xm)
**Assignee:** [Name]
**Priority:** P0-P4
**Dependencies:** #Y, #Z

**Description:**
[What needs to be done and why]

**Tasks:**
- [ ] Task 1
- [ ] Task 2
- [ ] Task 3

**Acceptance Criteria:**
- [ ] Criterion 1
- [ ] Criterion 2

**Code Location:** `path/to/file.js`

**Example/Code Snippet:**
\`\`\`javascript
// Sample implementation
\`\`\`

**Testing:**
- [ ] Unit tests pass
- [ ] Manual testing complete
- [ ] Cross-browser tested

**Definition of Done:**
- [ ] Code written and tested
- [ ] PR reviewed and approved
- [ ] Deployed to staging
- [ ] QA verified
- [ ] Documented
```

---

## 📈 Burn-Down Chart Tracking

| Week | Planned Points | Completed Points | Remaining | Velocity |
|------|---------------|------------------|-----------|----------|
| W1   | 60 pts        | 0 pts            | 160 pts   | -        |
| W2   | 55 pts        | TBD              | TBD       | TBD      |
| W3   | 45 pts        | TBD              | TBD       | TBD      |

---

## 🔄 Daily Standup Template

**What did I complete yesterday?**
- Issue #X: [Title] ✅
- Issue #Y: [Title] ✅

**What am I working on today?**
- Issue #Z: [Title] 🔄

**Any blockers?**
- None / [Describe blocker]

---

## ✅ Definition of Done (DoD)

An issue is DONE when:

1. **Code Complete**
   - [ ] All tasks checked off
   - [ ] Code follows style guide
   - [ ] No linting errors
   - [ ] No console errors

2. **Tested**
   - [ ] Manual testing complete
   - [ ] Edge cases tested
   - [ ] Cross-browser tested (Chrome, Firefox, Safari, Edge)
   - [ ] Mobile tested (if applicable)

3. **Reviewed**
   - [ ] Code reviewed by peer
   - [ ] Feedback addressed
   - [ ] Approved by reviewer

4. **Integrated**
   - [ ] Merged to main branch
   - [ ] No merge conflicts
   - [ ] Build passes

5. **Documented**
   - [ ] Code comments added
   - [ ] README updated (if needed)
   - [ ] Issue closed with summary

6. **Verified**
   - [ ] QA tested feature
   - [ ] Acceptance criteria met
   - [ ] Stakeholder approved

---

## 🚀 Sprint Planning Guide

### Sprint 1 (Week 1)
**Goal:** Professional foundation
**Issues:** #1-#28
**Points:** 60 pts

**Monday:** Issues #1-#9 (Markdown) - 13 pts
**Tuesday-Wednesday:** Issues #10-#15 (Dark Mode) + #16-#18 (Copy) - 13 pts
**Thursday-Friday:** Issues #19-#27 (Persistence) - 13 pts
**Weekend:** Issues #28-... (Search) - remaining

### Sprint 2 (Week 2)
**Goal:** Smart features
**Issues:** #29-#52
**Points:** 55 pts

### Sprint 3 (Week 3)
**Goal:** Production polish
**Issues:** #53-#70
**Points:** 45 pts

---

**Next Step:** Import these issues into your project management tool (GitHub Issues, Jira, Linear, etc.) and start with Issue #1! 🚀
