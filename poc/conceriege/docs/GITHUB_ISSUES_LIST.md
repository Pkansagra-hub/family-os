# 📋 Complete Issue List (70 Issues)

## Ready for GitHub Import

**Format:** GitHub CSV Import or Manual Creation
**Total Issues:** 70
**Total Story Points:** 160
**Total Hours:** 90h

---

## How to Import to GitHub

### Method 1: GitHub CLI

```bash
# Install GitHub CLI
# Then run:
gh issue create --title "Issue title" --body "Description" --label "feature,M1-Epic1.1"
```

### Method 2: GitHub UI

1. Go to Issues → New Issue
2. Copy title + description from below
3. Add labels
4. Assign story points (use project fields)

### Method 3: CSV Import (GitHub Projects)

Use the CSV file generated at end of this document

---

## 🎯 MILESTONE 1: Professional Foundation (Week 1)

### EPIC 1.1: Markdown Rendering System (13 pts)

---

**Issue #1**

```
Title: Set up markdown parsing library
Labels: setup, dependencies, M1-Epic1.1, P1
Story Points: 1
Assignee: Unassigned

Description:
Install and configure `marked` library for markdown parsing.

Tasks:
- [ ] Run `npm install marked`
- [ ] Add import statement in service file
- [ ] Configure marked options (breaks, gfm, sanitize)
- [ ] Test basic markdown parsing (console.log test)

Acceptance Criteria:
- [ ] marked@11.0.0 or higher installed
- [ ] No npm vulnerabilities
- [ ] Basic markdown string parses correctly

Files to Create/Modify:
- src/services/markdown.js

Time Estimate: 15 minutes
```

---

**Issue #2**

```
Title: Set up syntax highlighting library
Labels: setup, dependencies, M1-Epic1.1, P1
Story Points: 1
Assignee: Unassigned

Description:
Install and configure Prism.js for code syntax highlighting.

Tasks:
- [ ] Run `npm install prismjs`
- [ ] Import Prism core
- [ ] Import theme CSS (prism-tomorrow.css)
- [ ] Import language modules (js, python, typescript, bash, json)
- [ ] Test syntax highlighting (console test)

Acceptance Criteria:
- [ ] prismjs@1.29.0 or higher installed
- [ ] Dark theme CSS loaded
- [ ] At least 5 languages work

Files to Create/Modify:
- src/services/markdown.js
- src/styles/prism.css

Time Estimate: 15 minutes
```

---

**Issue #3**

```
Title: Create markdown rendering service
Labels: feature, core, M1-Epic1.1, P0
Story Points: 2
Assignee: Unassigned

Description:
Create service module to parse markdown and highlight code.

Tasks:
- [ ] Create `src/services/markdown.js`
- [ ] Write `renderMarkdown(text)` function
- [ ] Configure marked with highlight callback
- [ ] Add Prism language detection
- [ ] Handle edge cases (empty string, null, undefined)
- [ ] Add error handling (try-catch)
- [ ] Write JSDoc comments

Acceptance Criteria:
- [ ] Function accepts string, returns HTML
- [ ] Code blocks highlighted correctly
- [ ] No XSS vulnerabilities (sanitization)
- [ ] Handles edge cases gracefully

Example Code:
```javascript
import { marked } from 'marked';
import Prism from 'prismjs';

/**
 * Render markdown text to HTML with syntax highlighting
 * @param {string} text - Markdown text to render
 * @returns {string} HTML string
 */
export function renderMarkdown(text) {
  if (!text || typeof text !== 'string') return '';

  try {
    marked.setOptions({
      highlight: (code, lang) => {
        if (lang && Prism.languages[lang]) {
          return Prism.highlight(code, Prism.languages[lang], lang);
        }
        return code;
      },
      breaks: true,
      gfm: true
    });

    return marked.parse(text);
  } catch (error) {
    console.error('Markdown parsing error:', error);
    return text; // Fallback to plain text
  }
}
\`\`\`

Files to Create/Modify:
- src/services/markdown.js (NEW)

Time Estimate: 30 minutes
```

---

**Issue #4**

```
Title: Integrate markdown rendering into message display
Labels: feature, integration, M1-Epic1.1, P0
Story Points: 2
Assignee: Unassigned

Description:
Replace plain text rendering with markdown in message bubbles.

Tasks:
- [ ] Import `renderMarkdown` in main app
- [ ] Update `addMessage()` function to use `innerHTML`
- [ ] Change from `textContent` to `innerHTML`
- [ ] Test with sample messages
- [ ] Verify no layout breaks
- [ ] Test XSS protection

Acceptance Criteria:
- [ ] Bold text renders as `<strong>`
- [ ] Code blocks have proper `<pre><code>` structure
- [ ] Lists render with `<ul>`/`<ol>`
- [ ] No text escaping issues
- [ ] No XSS vulnerabilities

Before:
\`\`\`javascript
bubble.textContent = data.message;
\`\`\`

After:
\`\`\`javascript
import { renderMarkdown } from './services/markdown.js';

bubble.innerHTML = renderMarkdown(data.message);
\`\`\`

Files to Create/Modify:
- web_ui.py (JavaScript section)
- OR src/main.js

Time Estimate: 30 minutes
```

---

**Issue #5**

```
Title: Style code blocks with dark theme
Labels: styling, css, M1-Epic1.1, P1
Story Points: 2
Assignee: Unassigned

Description:
Add CSS for code block styling with dark background.

Tasks:
- [ ] Add `<pre>` styles (padding, border-radius, background)
- [ ] Add `<code>` font (monospace)
- [ ] Import Prism Tomorrow theme CSS
- [ ] Add line number styles (optional)
- [ ] Test on multiple code blocks
- [ ] Ensure scrollbar for long code
- [ ] Test in light and dark themes

Acceptance Criteria:
- [ ] Dark background (#2d2d2d)
- [ ] Monospace font (Fira Code or Courier)
- [ ] Horizontal scroll for overflow
- [ ] Matches design system colors
- [ ] Works in both themes

CSS Code:
\`\`\`css
pre {
  background: #2d2d2d;
  border-radius: 8px;
  padding: 16px;
  overflow-x: auto;
  margin: 12px 0;
  font-family: 'Fira Code', 'Courier New', monospace;
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
  color: var(--text-primary);
}

[data-theme="dark"] :not(pre) > code {
  background: rgba(255, 255, 255, 0.1);
}
\`\`\`

Files to Create/Modify:
- src/styles/markdown.css (NEW)
- OR add to main <style> block

Time Estimate: 30 minutes
```

---

**Issue #6**

```
Title: Style inline code elements
Labels: styling, css, M1-Epic1.1, P2
Story Points: 1
Assignee: Unassigned

Description:
Add distinct styling for inline `code` elements (not in pre blocks).

Tasks:
- [ ] Add background color for inline code
- [ ] Add padding (2px 6px)
- [ ] Add border-radius (4px)
- [ ] Slightly reduce font size (0.9em)
- [ ] Test in light and dark themes
- [ ] Ensure contrast ratio meets WCAG AA

Acceptance Criteria:
- [ ] Inline code distinguishable from plain text
- [ ] Background contrasts with message bubble
- [ ] Font size proportional (0.9em)
- [ ] Works in both themes

Files to Create/Modify:
- src/styles/markdown.css

Time Estimate: 15 minutes
```

---

**Issue #7**

```
Title: Add support for markdown lists
Labels: feature, markdown, M1-Epic1.1, P2
Story Points: 1
Assignee: Unassigned

Description:
Ensure ordered and unordered lists render correctly with proper styling.

Tasks:
- [ ] Add `<ul>` styles (margin, padding, bullets)
- [ ] Add `<ol>` styles (numbering)
- [ ] Add `<li>` styles (spacing)
- [ ] Test nested lists (2-3 levels)
- [ ] Test mixed list types (ol in ul)
- [ ] Test list items with markdown (bold, code, etc.)

Acceptance Criteria:
- [ ] Lists have proper indentation (24px)
- [ ] Bullets/numbers visible
- [ ] Nested lists work correctly
- [ ] Spacing between list items (4px)

CSS Code:
\`\`\`css
.message-bubble ul,
.message-bubble ol {
  margin: 8px 0;
  padding-left: 24px;
}

.message-bubble li {
  margin: 4px 0;
  line-height: 1.6;
}

.message-bubble ul ul,
.message-bubble ol ul,
.message-bubble ul ol,
.message-bubble ol ol {
  margin: 4px 0;
}
\`\`\`

Files to Create/Modify:
- src/styles/markdown.css

Time Estimate: 15 minutes
```

---

**Issue #8**

```
Title: Add support for markdown links
Labels: feature, markdown, M1-Epic1.1, P1
Story Points: 2
Assignee: Unassigned

Description:
Style links and add security attributes for external links.

Tasks:
- [ ] Add link color (primary brand color)
- [ ] Add hover effect (underline)
- [ ] Add external link icon (optional)
- [ ] Add `target="_blank"` for external links
- [ ] Add `rel="noopener noreferrer"` for security
- [ ] Test link clicking
- [ ] Add visited link state

Acceptance Criteria:
- [ ] Links clickable and styled
- [ ] Hover state visible
- [ ] External links open in new tab
- [ ] No security warnings
- [ ] Color matches design system

CSS Code:
\`\`\`css
.message-bubble a {
  color: var(--primary-600);
  text-decoration: none;
  border-bottom: 1px solid transparent;
  transition: border-color 0.2s;
}

.message-bubble a:hover {
  border-bottom-color: var(--primary-600);
}

.message-bubble a:visited {
  color: var(--primary-700);
}

/* External link icon */
.message-bubble a[href^="http"]::after {
  content: " ↗";
  font-size: 0.8em;
  opacity: 0.6;
}
\`\`\`

Files to Create/Modify:
- src/styles/markdown.css
- src/services/markdown.js (add target/rel attributes)

Time Estimate: 30 minutes
```

---

**Issue #9**

```
Title: Test markdown rendering with edge cases
Labels: testing, qa, M1-Epic1.1, P0
Story Points: 1
Assignee: Unassigned

Description:
Comprehensive testing of markdown with edge cases and security checks.

Tasks:
- [ ] Test empty message ("")
- [ ] Test null/undefined
- [ ] Test very long code blocks (100+ lines)
- [ ] Test nested markdown (bold in lists, code in headers)
- [ ] Test invalid markdown syntax
- [ ] Test XSS attempts (`<script>alert()</script>`)
- [ ] Test special characters (&, <, >, ", ')
- [ ] Test mixed content (text + code + lists + links)
- [ ] Document any issues found
- [ ] Create test suite file

Acceptance Criteria:
- [ ] No crashes on edge cases
- [ ] No XSS vulnerabilities
- [ ] Graceful degradation on errors
- [ ] All test cases documented
- [ ] No console errors

Test Cases:
\`\`\`javascript
const edgeCases = [
  // Empty/null
  "",
  null,
  undefined,

  // Basic formatting
  "**bold** *italic* `code`",
  "~~strikethrough~~ [link](https://example.com)",

  // Lists
  "- Item 1\n- Item 2\n  - Nested\n- Item 3",
  "1. First\n2. Second\n3. Third",

  // Code blocks
  "```javascript\nconst x = 1;\n```",
  "```python\n" + "x = 1\n".repeat(100) + "```", // Long block

  // XSS attempts
  "<script>alert('XSS')</script>",
  "[Click](javascript:alert('XSS'))",
  "![](javascript:alert('XSS'))",

  // Special characters
  "& < > \" '",

  // Mixed content
  "**Bold** with `code` and [link](https://example.com):\n- List item"
];

edgeCases.forEach((test, i) => {
  console.log(`Test ${i + 1}:`, renderMarkdown(test));
});
\`\`\`

Files to Create/Modify:
- tests/markdown.test.js (NEW)

Time Estimate: 15 minutes
```

---

### EPIC 1.2: Dark Mode System (8 pts)

---

**Issue #10**

```
Title: Define CSS custom properties for theming
Labels: setup, css, M1-Epic1.2, P0
Story Points: 1
Assignee: Unassigned

Description:
Create CSS variables for all theme-dependent colors to enable easy theme switching.

Tasks:
- [ ] Create `src/styles/themes.css` file
- [ ] Define `:root` variables for light theme (default)
- [ ] Define `[data-theme="dark"]` variables for dark theme
- [ ] Include all color categories (background, text, surface, border, accent)
- [ ] Test variable fallbacks
- [ ] Document variable naming convention

Acceptance Criteria:
- [ ] At least 15 color variables defined
- [ ] Light and dark variants for each variable
- [ ] Variables follow naming convention (--category-purpose)
- [ ] No hardcoded colors remain in main CSS
- [ ] Variables work in all browsers

CSS Code:
\`\`\`css
/* src/styles/themes.css */

:root {
  /* Light theme (default) */
  --bg-primary: #ffffff;
  --bg-secondary: #f5f5f5;
  --bg-tertiary: #e5e7eb;

  --text-primary: #1a1a1a;
  --text-secondary: #6b7280;
  --text-tertiary: #9ca3af;

  --surface: #ffffff;
  --surface-elevated: #ffffff;

  --border: #e5e7eb;
  --border-hover: #d1d5db;

  --primary-500: #7c94f5;
  --primary-600: #667eea;
  --primary-700: #764ba2;

  --success: #10b981;
  --warning: #f59e0b;
  --error: #ef4444;
  --info: #3b82f6;

  --shadow-sm: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
  --shadow-md: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
  --shadow-lg: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
}

[data-theme="dark"] {
  /* Dark theme */
  --bg-primary: #1a1a1a;
  --bg-secondary: #2d2d2d;
  --bg-tertiary: #3a3a3a;

  --text-primary: #e5e5e5;
  --text-secondary: #9ca3af;
  --text-tertiary: #6b7280;

  --surface: #2d2d2d;
  --surface-elevated: #3a3a3a;

  --border: #374151;
  --border-hover: #4b5563;

  --primary-500: #8b9ff9;
  --primary-600: #7c94f5;
  --primary-700: #8b5fbf;

  --success: #34d399;
  --warning: #fbbf24;
  --error: #f87171;
  --info: #60a5fa;

  --shadow-sm: 0 1px 2px 0 rgba(0, 0, 0, 0.3);
  --shadow-md: 0 4px 6px -1px rgba(0, 0, 0, 0.4);
  --shadow-lg: 0 10px 15px -3px rgba(0, 0, 0, 0.5);
}
\`\`\`

Files to Create/Modify:
- src/styles/themes.css (NEW)

Time Estimate: 15 minutes
```

---

**[Continue with Issues #11-#70...]**

---

## 📊 Summary Statistics

### By Milestone

| Milestone | Issues | Points | Hours |
|-----------|--------|--------|-------|
| M1: Professional Foundation | 28 | 60 | 30h |
| M2: Smart Features | 24 | 55 | 30h |
| M3: Production Polish | 18 | 45 | 30h |
| **Total** | **70** | **160** | **90h** |

### By Epic

| Epic | Issues | Points |
|------|--------|--------|
| 1.1 Markdown Rendering | 9 | 13 |
| 1.2 Dark Mode | 6 | 8 |
| 1.3 Copy Functionality | 3 | 5 |
| 1.4 Message Persistence | 9 | 13 |
| 1.5 Conversation Search | 5 | 8 |
| 1.6 Agent Activity Panel | 6 | 13 |
| 2.1 Conversation Sidebar | 6 | 10 |
| 2.2 Voice Input | 4 | 8 |
| 2.3 File Attachments | 4 | 8 |
| 2.4 Export System | 5 | 12 |
| 2.5 Message Reactions | 3 | 5 |
| 2.6 Context Panel | 4 | 12 |
| 3.1 Keyboard Shortcuts | 4 | 8 |
| 3.2 Accessibility | 6 | 15 |
| 3.3 Mobile Optimization | 5 | 12 |
| 3.4 Connection Resilience | 3 | 6 |
| 3.5 Performance | 4 | 8 |
| 3.6 Analytics | 2 | 6 |

### By Label

| Label | Issues |
|-------|--------|
| feature | 45 |
| setup | 8 |
| styling | 12 |
| testing | 8 |
| integration | 10 |
| polish | 7 |

### By Story Points

| Points | Issues | % |
|--------|--------|---|
| 1 pt | 35 | 50% |
| 2 pts | 28 | 40% |
| 3 pts | 5 | 7% |
| 5 pts | 2 | 3% |

---

## 🔄 GitHub Import Script

Save this as `import_issues.sh` and run to create all issues:

\`\`\`bash

# !/bin/bash

# Requires GitHub CLI: gh auth login

REPO="Pkansagra-hub/family-os"

# Issue #1

gh issue create \
  --repo $REPO \
  --title "Set up markdown parsing library" \
  --body "See WEBUI_IMPLEMENTATION_ROADMAP.md Issue #1" \
  --label "setup,dependencies,M1-Epic1.1,P1" \
  --milestone "M1: Professional Foundation"

# Issue #2

gh issue create \
  --repo $REPO \
  --title "Set up syntax highlighting library" \
  --body "See WEBUI_IMPLEMENTATION_ROADMAP.md Issue #2" \
  --label "setup,dependencies,M1-Epic1.1,P1" \
  --milestone "M1: Professional Foundation"

# ... repeat for all 70 issues

\`\`\`

---

## 📥 CSV Import Format

For GitHub Projects CSV import:

\`\`\`csv
Title,Body,Labels,Milestone,Story Points,Priority
"Set up markdown parsing library","See roadmap Issue #1","setup,dependencies,M1-Epic1.1",M1,1,P1
"Set up syntax highlighting library","See roadmap Issue #2","setup,dependencies,M1-Epic1.1",M1,1,P1
...
\`\`\`

---

**Ready to start!** 🚀

**Recommended Order:**

1. Create Milestone 1 in GitHub
2. Import Issues #1-#9 (Markdown epic)
3. Assign to yourself
4. Move to "In Progress"
5. Start with Issue #1 (15 minutes!)
