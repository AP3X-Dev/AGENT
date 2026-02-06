# Tool Call Display Component

## Overview

The tool call display has been redesigned to show a **collapsed state by default**, keeping the chat interface clean and scannable while providing detailed information on-demand.

## Features

### Collapsed State (Default)
Each tool call displays as a compact horizontal bar containing:

1. **Expand/collapse toggle** - Chevron icon (right when collapsed, down when expanded)
2. **Tool icon** - Visual indicator for the tool type (terminal, file, search, etc.)
3. **Tool name** - The name of the tool being called (e.g., "read_file", "shell", "web_search")
4. **Key arguments** - Truncated display of the most relevant argument:
   - File operations: filename
   - Shell commands: first 40 chars of command
   - Web search: search query
   - HTTP requests: URL
5. **Status indicator** - Icon showing pending/success/error with appropriate colors

### Expanded State
When clicked, the tool call expands to show:

- **Full arguments** - Complete JSON representation of all tool arguments
- **Output** - Complete tool output (scrollable if long)
- **Error details** - If the tool failed, full error message
- **Copy button** - Copy the output or arguments to clipboard

## Status Colors

- **Pending** (Yellow): Tool is currently executing
  - Icon: Clock
  - Border: `border-yellow-500/30`
  - Background: `bg-yellow-500/10`

- **Success** (Green): Tool completed successfully
  - Icon: CheckCircle
  - Border: `border-green-500/30`
  - Background: `bg-green-500/10`

- **Error** (Red): Tool failed
  - Icon: XCircle
  - Border: `border-red-500/30`
  - Background: `bg-red-500/10`

## Tool Icons

Different tools have specific icons for quick recognition:

- **Shell/Execute/Bash**: Terminal icon
- **Read/Write/Edit File**: FileText icon
- **Web Search**: Search icon
- **HTTP Request**: Globe icon
- **Other tools**: Wrench icon (default)

## Usage

The component is automatically used for all tool calls in the chat interface. Tool results from the DeepAgents daemon are automatically formatted and displayed using this component.

### Component Props

```typescript
interface ToolCallDisplayProps {
  toolName: string              // Name of the tool
  args?: Record<string, any>    // Tool arguments
  output?: string               // Tool output
  status?: "pending" | "success" | "error"  // Execution status
  error?: string                // Error message if failed
  className?: string            // Additional CSS classes
}
```

## Integration

The component is integrated into the chat message flow:

1. **chat-provider.tsx** - Processes tool events from the daemon and creates `tool-call` type CLI content
2. **chat-message.tsx** - Renders `ToolCallDisplay` for `tool-call` type content
3. **tool-call-display.tsx** - The actual component implementation

## Special Cases

### Shell Commands
Shell commands use the existing `CommandOutput` component which has similar collapsed/expanded behavior but is specialized for command execution with exit codes.

### File Operations
- **read_file**: Shows file content in `FilePreview` component
- **write_file/edit_file**: Shows as tool call with diff if available
- Other file operations use the standard tool call display

### Web Search & HTTP
These tools use the standard `ToolCallDisplay` with their specific icons and argument extraction.

## Benefits

✅ **Clean interface** - Collapsed by default reduces visual clutter
✅ **Scannable** - Easy to see what tools were called at a glance
✅ **On-demand details** - Full information available when needed
✅ **Consistent UX** - All tool calls follow the same pattern
✅ **Status awareness** - Clear visual indication of success/failure
✅ **Copy functionality** - Easy to copy outputs for debugging

