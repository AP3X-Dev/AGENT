/**
 * CLI Integration Types
 * Types for file operations, shell commands, and autocomplete functionality
 */

// ============================================================================
// File Operations Types
// ============================================================================

export interface FileInfo {
  name: string
  path: string
  isDirectory: boolean
  size?: number
  lastModified?: Date
}

export interface FileReadRequest {
  path: string
  startLine?: number
  endLine?: number
}

export interface FileReadResponse {
  success: boolean
  content?: string
  error?: string
  lineCount?: number
  path: string
}

export interface FileWriteRequest {
  path: string
  content: string
  createDirectories?: boolean
}

export interface FileWriteResponse {
  success: boolean
  error?: string
  path: string
  bytesWritten?: number
}

export interface FileEditRequest {
  path: string
  oldString: string
  newString: string
  replaceAll?: boolean
}

export interface FileEditResponse {
  success: boolean
  error?: string
  path: string
  occurrencesReplaced?: number
  diff?: string
}

// ============================================================================
// Shell Execution Types
// ============================================================================

export interface ShellExecuteRequest {
  command: string
  cwd?: string
  timeout?: number
}

export interface ShellExecuteResponse {
  success: boolean
  output: string
  exitCode: number
  error?: string
  executionTime?: number
}

// ============================================================================
// Autocomplete Types
// ============================================================================

export interface AutocompleteItem {
  value: string
  displayText: string
  type: "file" | "directory" | "command"
  description?: string
  icon?: string
}

export interface AutocompleteRequest {
  query: string
  type: "file" | "command" | "all"
  cwd?: string
  limit?: number
}

export interface AutocompleteResponse {
  items: AutocompleteItem[]
  hasMore: boolean
}

// ============================================================================
// Chat Input Types
// ============================================================================

export type InputMode = "chat" | "file-mention" | "bash-command"

export interface ParsedInput {
  mode: InputMode
  rawText: string
  command?: string // For bash commands (without ! prefix)
  fileMentions: FileMention[]
  cleanText: string // Text with file mentions resolved
}

export interface FileMention {
  raw: string // Original @path text
  path: string // Resolved file path
  startIndex: number
  endIndex: number
  exists?: boolean
  content?: string
}

// ============================================================================
// Command History Types
// ============================================================================

export interface CommandHistoryEntry {
  id: string
  input: string
  timestamp: Date
  type: InputMode
}

export interface CommandHistoryState {
  entries: CommandHistoryEntry[]
  currentIndex: number
  maxEntries: number
}

// ============================================================================
// CLI Message Types (for chat display)
// ============================================================================

export interface CLIMessageContent {
  type: "file-content" | "command-output" | "file-diff" | "error"
  title?: string
  content: string
  language?: string
  exitCode?: number
  path?: string
}

export interface FilePreviewData {
  path: string
  content: string
  language: string
  startLine?: number
  endLine?: number
  totalLines: number
}

