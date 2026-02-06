# Sprint Plan: AG3NT Coding Capability Parity with OpenCode

## Executive Summary

After thorough analysis of both codebases, AG3NT has strong foundations (browser automation, multi-channel, semantic memory, subagent orchestration, scheduler) that OpenCode lacks. However, OpenCode has significantly more sophisticated **coding-specific** tooling. This plan closes those gaps across 5 sprints.

---

## Gap Analysis

### What AG3NT Already Has (no work needed)
| Capability | AG3NT | OpenCode |
|---|---|---|
| File read/write/edit | Yes (DeepAgents backend) | Yes |
| Glob file search | Yes (glob_tool) | Yes (ripgrep --files) |
| Grep content search | Yes (grep_tool, regex) | Yes (ripgrep) |
| Semantic code search | Yes (FAISS embeddings) | Partial (Exa API, external) |
| Shell execution | Yes (shell middleware + exec_tool) | Yes (bash tool) |
| Background processes | Yes (exec_tool background + process_tool) | No |
| Git operations | Yes (7 tools) | No dedicated tools |
| Apply patch (multi-file) | Yes (apply_patch_tool) | Yes |
| Notebook editing | Yes (notebook_tool) | No |
| Todo/planning | Yes (write_todos, read_todos, update_todo) | Yes |
| Browser automation | Yes (full Playwright suite) | No |
| Security/sandboxing | Yes (ShellSecurityValidator + PathSandbox) | Yes (permission system) |
| HITL approval | Yes (interrupt_on + exec_approval) | Yes |
| Tool policy profiles | Yes (tool_policy.yaml) | Yes (permission config) |
| Context compaction | Yes (summarization middleware) | Yes |
| Subagent delegation | Yes (subagent registry) | Yes (task tool) |
| Memory/knowledge base | Yes (FAISS memory_search) | No |
| Multi-channel (Telegram, Discord, Slack) | Yes | No |
| Scheduler/cron | Yes | No |
| Deep reasoning | Yes | No |

### Critical Gaps (AG3NT is missing)

| # | Feature | OpenCode Implementation | Impact |
|---|---------|------------------------|--------|
| G1 | **Fuzzy edit matching** | 9 cascading strategies (exact -> Levenshtein -> whitespace-normalized -> indentation-flexible -> context-aware) | High - prevents edit failures when LLM output has minor whitespace/formatting differences |
| G2 | **LSP diagnostics after edits** | Auto-starts 32+ language servers, feeds compile errors back to agent after every edit/write | Critical - agent sees type errors immediately instead of discovering them later |
| G3 | **LSP tool (go-to-def, references, hover)** | Experimental tool with 9 operations (goToDefinition, findReferences, hover, documentSymbol, workspaceSymbol, goToImplementation, callHierarchy) | High - enables precise code navigation instead of grep-based guessing |
| G4 | **File staleness detection** | Tracks read timestamps per session, blocks edits to files modified externally since last read, per-file write locks | High - prevents silent data loss from stale edits |
| G5 | **Git snapshot undo/redo** | Separate git repo tracks workspace state, can restore to any snapshot, diff from snapshots, auto-cleanup | High - safety net for destructive changes |
| G6 | **Session revert** | Revert file changes to any point in conversation history, with unrevert | Medium - user can undo agent mistakes at message granularity |
| G7 | **Multi-edit tool** | Apply N sequential edits to one file in a single tool call | Medium - reduces round-trips for multi-point edits |
| G8 | **Batch/parallel tool execution** | Execute up to 25 tool calls concurrently | Medium - dramatically faster for independent operations |
| G9 | **Smart output truncation** | Saves full output to disk, returns truncated + file path + suggestions (use grep/read with offset) | Medium - prevents context waste on large outputs |
| G10 | **File watching** | @parcel/watcher for real-time FS monitoring, publishes events on create/update/delete | Low-Medium - enables reactive behavior |
| G11 | **Question tool** | Agent can ask user multiple-choice questions mid-execution | Medium - better HITL beyond binary approve/deny |
| G12 | **Tree-sitter bash parsing** | Parses bash commands to extract command names and file paths for granular permission checks | Low - AG3NT already has regex-based validation |
| G13 | **External directory protection** | Explicit permission prompt when tools access files outside project root | Low - AG3NT PathSandbox covers this partially |
| G14 | **WebFetch HTML-to-markdown** | TurndownService converts fetched HTML to clean markdown | Low - improves web content readability |

---

## Sprint Breakdown

### Sprint 1: Edit Reliability (Fuzzy Matching + File Staleness)
**Goal:** Make file editing as reliable as OpenCode's - the single biggest impact on coding success rate.

#### S1.1 — Fuzzy edit matching engine
**File:** `vendor/deepagents/libs/deepagents/deepagents/backends/state.py` (and `sandbox.py`)
**New file:** `apps/agent/ag3nt_agent/fuzzy_edit.py`

Implement cascading replacement strategies (modeled on OpenCode's `edit.ts` lines 156-637):

1. **ExactReplacer** — Current behavior, exact string match (already exists)
2. **LineTrimmedReplacer** — Strip leading/trailing whitespace per line before matching
3. **WhitespaceNormalizedReplacer** — Collapse all whitespace to single spaces
4. **IndentationFlexibleReplacer** — Remove common leading indentation, match content only, re-apply target indentation
5. **BlockAnchorReplacer** — Match first+last lines exactly, use Levenshtein similarity (>0.8) for middle lines
6. **ContextAwareReplacer** — Use first+last lines as anchors, accept 50% middle-line similarity

Integration points:
- Replace `perform_string_replacement()` in `vendor/deepagents/libs/deepagents/deepagents/backends/state.py` with the new cascading engine
- Update sandbox backend's edit method similarly
- Add a `match_strategy` field to edit results so the agent knows which strategy matched
- Log warnings when falling back to fuzzy strategies

**Tests:** `apps/agent/tests/unit/test_fuzzy_edit.py`
- Exact match works as before
- Whitespace differences in LLM output still match
- Indentation differences still match
- First/last line anchoring with minor middle differences
- No false positives on ambiguous content

#### S1.2 — File staleness detection
**New file:** `apps/agent/ag3nt_agent/file_tracker.py`

Track file read/write timestamps per session:
- `FileTracker` singleton with `{session_id: {file_path: {last_read: timestamp, last_written: timestamp}}}`
- `record_read(session_id, file_path)` — called after every read_file
- `record_write(session_id, file_path)` — called after every write_file/edit_file
- `assert_fresh(session_id, file_path)` — before edit/write, check that file mtime matches last_read. Raise error with helpful message: "File was modified externally since you last read it. Read it again before editing."
- Per-file asyncio locks to prevent concurrent edits to the same file

Integration:
- Hook into the DeepAgents filesystem middleware (`vendor/deepagents/libs/deepagents/deepagents/middleware/filesystem.py`) — wrap read_file to call `record_read`, wrap edit_file/write_file to call `assert_fresh` + `record_write`
- Pass session_id through the tool runtime context

**Tests:** `apps/agent/tests/unit/test_file_tracker.py`

---

### Sprint 2: LSP Integration (Diagnostics + Tool)
**Goal:** Give the agent compile-error feedback after every edit and code navigation capabilities.

#### S2.1 — LSP client infrastructure
**New file:** `apps/agent/ag3nt_agent/lsp/client.py`

Implement a JSON-RPC LSP client over stdio:
- `LspClient` class wrapping subprocess communication with an LSP server
- Methods: `initialize()`, `shutdown()`, `didOpen()`, `didChange()`, `didSave()`, `textDocument/publishDiagnostics` handler
- Async message loop reading `Content-Length` framed JSON-RPC messages
- Support for `textDocument/definition`, `textDocument/references`, `textDocument/hover`, `textDocument/documentSymbol`, `workspace/symbol`

#### S2.2 — LSP server registry
**New file:** `apps/agent/ag3nt_agent/lsp/servers.py`

Server definitions for top priority languages (start with ~8, expand later):
1. TypeScript/JavaScript — `typescript-language-server` (npx)
2. Python — `pyright` (npx or pip)
3. Go — `gopls` (go install)
4. Rust — `rust-analyzer` (binary)
5. Java — `jdtls` (download)
6. C/C++ — `clangd` (download)
7. Ruby — `rubocop` (gem)
8. PHP — `intelephense` (npx)

Each entry: `{language_ids, file_extensions, command, args, install_command, auto_download: bool}`

Auto-download: Check if binary exists, if not, run install command or download from GitHub releases.

#### S2.3 — LSP manager (lifecycle)
**New file:** `apps/agent/ag3nt_agent/lsp/manager.py`

`LspManager` singleton:
- `start_for_file(file_path)` — Detect language from extension, start appropriate LSP server if not running
- `get_diagnostics(file_path, timeout=5s)` — Wait for diagnostics after a file change, return errors/warnings
- `stop_all()` — Shutdown all running servers on agent shutdown
- Lazy startup: Only start a server when the agent first touches a file of that language
- Server pooling: One server instance per language per workspace

#### S2.4 — Post-edit diagnostics hook
**Integration in:** `vendor/deepagents/libs/deepagents/deepagents/middleware/filesystem.py`

After every successful `edit_file` or `write_file`:
1. Notify LSP server of file change (`didChange`/`didSave`)
2. Wait up to 3 seconds for `publishDiagnostics`
3. If errors found, append to the tool result: `"\n\nLSP Diagnostics:\n- error: line 42: Type 'string' is not assignable to type 'number'"`
4. If no errors, append: `"\n\nNo LSP errors detected."`
5. If LSP not available for this language, silently skip

#### S2.5 — LSP navigation tool
**New file:** `apps/agent/ag3nt_agent/lsp/tool.py`

```python
@tool
def lsp_tool(
    action: Literal["definition", "references", "hover", "symbols", "workspace_symbols", "diagnostics"],
    file_path: str,
    line: int | None = None,
    character: int | None = None,
    query: str | None = None,  # for workspace_symbols
) -> dict:
```

Register in tool_registry.py. Mark as experimental initially.

**Tests:** `apps/agent/tests/unit/test_lsp_client.py`, `apps/agent/tests/unit/test_lsp_manager.py`

---

### Sprint 3: Undo/Revert System
**Goal:** Safety net — the agent (and user) can undo any changes.

#### S3.1 — Git snapshot manager
**New file:** `apps/agent/ag3nt_agent/snapshot.py`

Uses a shadow git repository at `~/.ag3nt/snapshots/<project-hash>/`:
- `Snapshot.track(workspace_path)` — `git add -A && git write-tree` to capture current state, return tree hash
- `Snapshot.restore(tree_hash)` — `git read-tree` + `git checkout-index -f -a` to restore workspace
- `Snapshot.diff(tree_hash)` — Show changes since snapshot
- `Snapshot.list_recent(n=20)` — List recent snapshots with timestamps
- Auto-cleanup: `git gc` periodically, prune snapshots older than 7 days

Integration:
- Take a snapshot before every `edit_file`, `write_file`, `apply_patch`, and destructive `exec_command`
- Store snapshot hashes in session metadata keyed by message/tool_call ID

#### S3.2 — Session revert
**New file:** `apps/agent/ag3nt_agent/revert.py`

`SessionRevert`:
- `revert_to_message(session_id, message_id)` — Find the snapshot taken just before that message, restore it
- `revert_last_action(session_id)` — Undo the most recent file-modifying action
- `unrevert(session_id)` — Re-apply the reverted changes (restore the snapshot from before the revert)

#### S3.3 — Revert tools
Add to planning_tools or as new tools:
- `undo_last()` — Revert the last file-modifying tool call
- `undo_to(message_id)` — Revert to a specific point

**Tests:** `apps/agent/tests/unit/test_snapshot.py`, `apps/agent/tests/unit/test_revert.py`

---

### Sprint 4: Parallel Execution + Smart Truncation + Multi-Edit
**Goal:** Speed and efficiency improvements.

#### S4.1 — Multi-edit tool
**New file:** `apps/agent/ag3nt_agent/multi_edit_tool.py`

```python
@tool
def multi_edit(
    file_path: str,
    edits: list[dict],  # [{old_string, new_string}]
) -> dict:
```

Applies edits sequentially to the same file content (each edit sees the result of the previous one). Uses the fuzzy edit engine from S1.1. Returns per-edit results.

Register in tool_registry.py.

#### S4.2 — Batch tool execution
**New file:** `apps/agent/ag3nt_agent/batch_tool.py`

```python
@tool
def batch(
    tool_calls: list[dict],  # [{tool_name, arguments}]
) -> dict:
```

- Execute up to 25 tool calls concurrently using `asyncio.gather`
- Cannot call itself recursively
- Cannot call risky tools (edit, write, exec_command, apply_patch) — read-only tools only
- Returns results keyed by index
- Individual errors don't fail the batch

Register in tool_registry.py. Mark as experimental.

#### S4.3 — Smart output truncation
**Modify:** `apps/agent/ag3nt_agent/exec_tool.py`, `apps/agent/ag3nt_agent/grep_tool.py`

When output exceeds threshold (50KB / 2000 lines):
1. Save full output to `~/.ag3nt/tool_output/<session_id>/<tool_call_id>.txt`
2. Return truncated output + message: `"Output truncated (X lines). Full output saved to <path>. Use grep_tool or read_file with offset to examine specific sections."`
3. Auto-cleanup: Delete output files older than 24 hours on startup

#### S4.4 — Question tool
**New file:** `apps/agent/ag3nt_agent/question_tool.py`

```python
@tool
def ask_user(
    question: str,
    options: list[str] | None = None,
    allow_custom: bool = True,
) -> str:
```

Uses the existing HITL/interrupt mechanism to present a question to the user via the CLI or UI. If `options` provided, show as numbered choices. Returns the user's response text.

Integrate with the gateway's HITL approval WebSocket channel.

**Tests:** `apps/agent/tests/unit/test_multi_edit.py`, `apps/agent/tests/unit/test_batch_tool.py`

---

### Sprint 5: File Watching + Polish
**Goal:** Reactive awareness and production hardening.

#### S5.1 — File watcher
**New file:** `apps/agent/ag3nt_agent/file_watcher.py`

Use `watchdog` (Python) for cross-platform file system monitoring:
- Watch the workspace directory for changes
- Publish events: `file_created`, `file_modified`, `file_deleted`
- Integrate with file_tracker (S1.2): invalidate staleness cache on external modifications
- Integrate with LSP manager (S2.3): notify LSP servers of external file changes
- Respect `.gitignore` patterns
- Debounce rapid changes (100ms window)

#### S5.2 — External directory protection
**Modify:** `apps/agent/ag3nt_agent/tool_policy.py` and filesystem middleware

When any file tool (read, write, edit, glob, grep) accesses a path outside the configured workspace root:
- Trigger an explicit HITL approval prompt: "Agent wants to access <path> which is outside the project directory. Allow?"
- Cache approvals per directory for the session duration
- Never auto-approve writes outside workspace

#### S5.3 — WebFetch HTML-to-markdown
**Modify:** `apps/agent/ag3nt_agent/deepagents_runtime.py` (fetch_url function)

Add `html2text` or `markdownify` dependency:
- Detect HTML responses by Content-Type header
- Convert to clean markdown before returning to agent
- Strip scripts, styles, navigation, and ads
- Preserve code blocks, tables, and links

#### S5.4 — Agent prompt updates
**Modify:** `apps/agent/ag3nt_agent/deepagents_runtime.py` (system prompt)

Update the agent's system prompt to document:
- New tools: multi_edit, batch, ask_user, lsp_tool, undo_last
- File staleness behavior: "You must read a file before editing it"
- LSP diagnostics: "After edits, you will see compile errors if any"
- Snapshot safety: "Your changes can be undone — take risks confidently"
- Fuzzy matching: "Edit tool is forgiving of minor whitespace differences"

**Tests:** Integration tests for file watcher, E2E test for external directory prompt

---

## Priority Order

If time is limited, implement in this order (highest impact first):

1. **S1.1 Fuzzy edit matching** — Single biggest reliability improvement. Every failed edit wastes an agent turn.
2. **S1.2 File staleness detection** — Prevents silent data corruption.
3. **S2.4 Post-edit LSP diagnostics** — Agent catches type errors immediately instead of 5 tool calls later.
4. **S3.1 Git snapshot undo** — Safety net enables the agent to be more aggressive.
5. **S4.1 Multi-edit tool** — Reduces round-trips.
6. **S2.5 LSP navigation tool** — Precise code navigation.
7. **S4.3 Smart output truncation** — Prevents context blowout.
8. **S4.4 Question tool** — Better human-agent collaboration.
9. **S4.2 Batch tool** — Speed improvement.
10. **S3.2 Session revert** — User-facing undo.
11. **S5.1 File watching** — Reactive awareness.
12. **S5.2-S5.4** — Polish items.

---

## Dependencies

```
S1.1 (fuzzy edit) ── standalone, no deps
S1.2 (file tracker) ── standalone, no deps
S2.1-S2.3 (LSP infra) ── standalone, no deps
S2.4 (post-edit diagnostics) ── depends on S2.1-S2.3
S2.5 (LSP tool) ── depends on S2.1-S2.3
S3.1 (snapshots) ── standalone, no deps
S3.2 (session revert) ── depends on S3.1
S4.1 (multi-edit) ── benefits from S1.1 (fuzzy matching)
S4.2 (batch) ── standalone, no deps
S4.3 (truncation) ── standalone, no deps
S4.4 (question tool) ── standalone, no deps
S5.1 (file watcher) ── benefits from S1.2 (file tracker)
```

Sprints 1 and 2 can run in parallel. Sprint 3 can start after Sprint 1. Sprint 4 items are all independent.

---

## New Dependencies to Add

### Python (apps/agent/requirements.txt)
```
watchdog>=4.0          # S5.1 file watching
html2text>=2024.2     # S5.3 HTML-to-markdown
python-Levenshtein>=0.25  # S1.1 fuzzy edit (or use rapidfuzz)
```

### System (auto-download)
```
typescript-language-server  # S2.2 LSP (npx)
pyright                     # S2.2 LSP (npx)
gopls                       # S2.2 LSP (go install)
```

---

## Verification Criteria

Each sprint should pass:
1. All existing tests still pass (`pytest tests/ -m unit`)
2. New unit tests pass with >80% coverage on new code
3. `pytest -m integration` passes for integration-level features (LSP, snapshot)
4. The agent successfully completes a multi-file refactoring task using the new capabilities
5. Coverage stays above 55% threshold
