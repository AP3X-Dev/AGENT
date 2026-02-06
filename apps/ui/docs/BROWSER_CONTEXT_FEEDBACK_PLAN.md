# Browser-to-Agent Context Feedback System

## Overview
Create a bidirectional feedback loop where browser events, state changes, and page content are captured and sent back to the agent so it can make informed decisions.

---

## Task List

### Phase 1: Browser State Channel (Foundation)
Create a structured data channel from browser to agent.

- [ ] **1.1 Define BrowserContext data model in browser_ws_server.py**
  - Create `@dataclass BrowserContext` with fields: session_id, url, title, loading, can_go_back, can_go_forward, timestamp, navigation_success, navigation_error, final_url, last_error

- [ ] **1.2 Add 'browser_context' message type to WebSocket protocol**
  - Server sends `{type: 'browser_context', data: {...}}` messages to client with structured browser state

- [ ] **1.3 Send context updates on key events**
  - In browser_ws_server.py, send context updates when: navigation completes, page load finishes, title changes, errors occur

- [ ] **1.4 Create browser-context-bridge.ts**
  - New file with `BrowserContextUpdate` interface, `emitBrowserContextUpdate()` and `subscribeToBrowserContext()` functions

- [ ] **1.5 Handle context messages in agent-browser-module.tsx**
  - Parse 'browser_context' messages from WebSocket and emit to browser-context-bridge

### Phase 2: Agent State Integration
Pipe browser context into agent's state/messages.

- [ ] **2.1 Enhance browser tool responses with rich context**
  - Update `_impl_browser_navigate` and other tools to return: navigated_to, title, content_summary, visible_links, forms_found, errors

- [ ] **2.2 Add browser_state field to AgentState**
  - Extend agent state schema with: session_id, current_url, page_title, page_summary, visible_elements, console_errors, network_pending

- [ ] **2.3 Use Command pattern for state updates**
  - Browser tools return `Command(update={'browser_state': {...}})` to inject browser state into agent context

### Phase 3: Real-Time Event Streaming
Stream browser events to agent in real-time.

- [ ] **3.1 Add event capture to browser_ws_server.py**
  - Capture `page.on('console')`, `page.on('pageerror')`, `page.on('dialog')` events
  - Send via WebSocket as 'browser_event' messages

- [ ] **3.2 Define browser event types**
  - Create event schemas for: console, navigation, dialog, download, pageerror
  - Include: type, data, timestamp fields

- [ ] **3.3 Create BrowserEventBuffer class**
  - Event buffer (max 50 events) with methods: add(), getRecent(), getByType(), getErrors(), toContextString()

### Phase 4: Content Extraction Pipeline
Extract and structure page content for agent consumption.

- [ ] **4.1 Add accessibility snapshot streaming**
  - Create `get_accessibility_snapshot(page)` using `page.accessibility.snapshot()`

- [ ] **4.2 Add structured content extraction**
  - Create `extract_page_content(page)` returning: text, links, forms, headings, images, meta

- [ ] **4.3 Enhance browser_snapshot tool**
  - Update `_impl_browser_snapshot` to return: snapshot elements, content (title, main_text, links, forms, headings), url

### Phase 5: Agent Context Integration Layer
Make browser context automatically available to agent.

- [ ] **5.1 Add browser context tracking to WebBrowsingMiddleware**
  - Track `_browser_context` state, update after tool calls

- [ ] **5.2 Inject browser context into system prompt**
  - In `wrap_model_call`, append formatted browser context when browser session is active

---

## Priority

| Phase | Effort | Value | Priority |
|-------|--------|-------|----------|
| Phase 1 | Medium | High | **P0** |
| Phase 2 | Medium | High | **P0** |
| Phase 3 | Medium | Medium | P1 |
| Phase 4 | High | High | P1 |
| Phase 5 | Low | High | P2 |

---

## Files to Modify/Create

| File | Changes |
|------|---------|
| `browser_ws_server.py` | Add context messages, event capture, content extraction |
| `agent-browser-module.tsx` | Handle context messages, emit to bridge |
| `browser-context-bridge.ts` | **NEW** - Context event system for agent |
| `browser-session-events.ts` | Extend with new event types |
| `web_browsing.py` | Add context tracking, system prompt injection |
| Agent state schema | Add `browser_state` field |

---

## Token Budget for Browser Context

| Content Type | Typical Size | Strategy |
|--------------|--------------|----------|
| URL + Title | ~100 tokens | Always include |
| Error list | ~200 tokens | Last 5 errors |
| Accessibility tree | 500-2000 tokens | Truncate to visible area |
| Page text | 1000-5000 tokens | Summarize or extract main |
| Links list | 200-500 tokens | Top 10-20 links |
| Forms | 100-300 tokens | All forms |

**Total budget:** ~3000-5000 tokens for browser context

