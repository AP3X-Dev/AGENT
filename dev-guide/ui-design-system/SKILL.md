---
name: ui-design-system
description: Guide to AG3NT UI patterns, Control Panel design, TUI conventions, and frontend development.
version: "1.0.0"
tags:
  - ui
  - design
  - frontend
  - tui
triggers:
  - "ui design"
  - "control panel"
  - "tui"
  - "frontend"
  - "design system"
required_permissions: []
license: MIT
compatibility: AG3NT 1.x
metadata:
  author: ag3nt-team
  category: development
---

# UI Design System Guide

Use this skill when working on AG3NT's user interfaces: Control Panel, TUI, or channel UIs.

## UI Components Overview

AG3NT has three main UI surfaces:

| Surface | Tech | Location | Purpose |
|---------|------|----------|---------|
| **Control Panel** | HTML/CSS/JS | `apps/gateway/src/ui/` | Web dashboard |
| **TUI** | Node.js/Ink | `apps/gateway/src/channels/cli/tui/` | Terminal interface |
| **Channel UIs** | Platform-native | Various | Telegram, Discord, etc. |

## Control Panel Design

### File Locations

```
apps/gateway/src/ui/
├── public/
│   ├── app.js          # Main application logic
│   ├── styles.css      # Global styles
│   └── index.html      # Served at /panel
└── views/
    └── control-panel.html  # Template
```

### Design Principles

1. **Dark Theme First**: All components designed for dark backgrounds
2. **Minimal Dependencies**: No frameworks, vanilla JS only
3. **Real-Time Updates**: WebSocket for live data streaming
4. **Responsive Tabs**: Tab-based navigation for features

### Color Palette

```css
/* Background hierarchy */
--bg-primary: #0d1117;      /* Main background */
--bg-secondary: #161b22;    /* Cards, panels */
--bg-tertiary: #21262d;     /* Hover states */

/* Text hierarchy */
--text-primary: #c9d1d9;    /* Main text */
--text-secondary: #8b949e;  /* Muted text */
--text-muted: #6e7681;      /* Very muted */

/* Accent colors */
--accent-blue: #58a6ff;     /* Links, primary actions */
--accent-green: #3fb950;    /* Success, online */
--accent-red: #f85149;      /* Error, danger */
--accent-yellow: #d29922;   /* Warning */
```

### Component Patterns

**Status Indicators**:
```html
<span class="status-dot online"></span>  <!-- Green dot -->
<span class="status-dot offline"></span> <!-- Red dot -->
```

**Tab Navigation**:
```javascript
// Tab switching pattern
document.querySelectorAll('.tab').forEach(tab => {
  tab.addEventListener('click', () => switchTab(tab.dataset.tab));
});
```

**Log Display**:
```html
<div class="log-entry">
  <span class="log-time">12:34:56</span>
  <span class="log-level info">info</span>
  <span class="log-source">Router</span>
  <span class="log-message">Message content</span>
</div>
```

### WebSocket Integration

```javascript
// Connect to debug WebSocket
const ws = new WebSocket(`ws://${location.host}/ws?debug=true`);

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  if (data.type === 'log') {
    addLogEntry(data);
  }
};
```

## TUI Design

### File Locations

```
apps/gateway/src/channels/cli/tui/
├── TuiApp.tsx           # Main React/Ink component
├── components/          # Reusable components
└── hooks/               # Custom hooks
```

### Ink Framework

The TUI uses [Ink](https://github.com/vadimdemedes/ink) - React for CLIs:

```tsx
import React from 'react';
import {Box, Text} from 'ink';

const StatusBar = ({status}) => (
  <Box>
    <Text color={status === 'online' ? 'green' : 'red'}>●</Text>
    <Text> {status}</Text>
  </Box>
);
```

### TUI Conventions

1. **Box Layout**: Use `<Box>` for layouts, never raw strings
2. **Color Semantics**: Green=success, Red=error, Yellow=warning, Blue=info
3. **Borders**: Use for section separation, sparingly
4. **Input**: Single input box at bottom, like chat apps

## Log Level Styling

Consistent across all UIs:

| Level | Color | Use Case |
|-------|-------|----------|
| `debug` | Gray | Verbose debugging |
| `info` | Blue | Normal operations |
| `warn` | Yellow | Potential issues |
| `error` | Red | Failures |

## Emoji Conventions

Used in debug logs for quick scanning:

| Emoji | Meaning |
|-------|---------|
| 📨 | Incoming message |
| 📤 | Outgoing response |
| 🤖 | Agent action |
| ⏸️ | Awaiting approval |
| ✅ | Approved/Success |
| ❌ | Rejected/Error |
| 🔒 | Security/Auth |

## Further Reading

- Control Panel code: `/apps/gateway/src/ui/public/app.js`
- TUI components: `/apps/gateway/src/channels/cli/tui/`
- Log buffer: `/apps/gateway/src/logs/LogBuffer.ts`

