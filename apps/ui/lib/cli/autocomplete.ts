/**
 * Autocomplete Service
 * Client-side service for file path and command autocompletion
 */

import type { AutocompleteItem, AutocompleteResponse } from '@/types/cli'
import { COMMON_COMMANDS } from './shell'

const API_BASE = '/api/cli/autocomplete'

// Regex patterns for detecting autocomplete contexts
// TODO: Fix named capturing groups - requires ES2018+ but TypeScript is not recognizing it
export const AT_MENTION_PATTERN = /@([^\s@]|(?<=\\)\s)*$/
export const BASH_COMMAND_PATTERN = /^!(\S*)$/

/**
 * Fetch file path completions from the API
 */
export async function getFileCompletions(
  query: string,
  limit: number = 10
): Promise<AutocompleteResponse> {
  try {
    const params = new URLSearchParams({
      query,
      type: 'file',
      limit: limit.toString(),
    })

    const response = await fetch(`${API_BASE}?${params}`)
    const data = await response.json()
    return data
  } catch (error) {
    return { items: [], hasMore: false }
  }
}

/**
 * Get command completions (client-side, from common commands)
 */
export function getCommandCompletions(query: string): AutocompleteItem[] {
  const lowerQuery = query.toLowerCase()
  
  return COMMON_COMMANDS
    .filter(cmd => cmd.command.toLowerCase().startsWith(lowerQuery))
    .map(cmd => ({
      value: cmd.command,
      displayText: cmd.command,
      type: 'command' as const,
      description: cmd.description,
      icon: '💻',
    }))
}

/**
 * Detect if we're in an @ mention context and extract the path fragment
 */
export function detectAtMention(text: string, cursorPosition: number): string | null {
  const textUpToCursor = text.substring(0, cursorPosition)
  const match = AT_MENTION_PATTERN.exec(textUpToCursor)
  
  if (match?.groups?.path !== undefined) {
    return match.groups.path
  }
  
  return null
}

/**
 * Detect if we're in a bash command context
 */
export function detectBashCommand(text: string): string | null {
  const trimmed = text.trim()
  
  if (trimmed.startsWith('!')) {
    const command = trimmed.substring(1)
    // Only provide completions for the first word (the command itself)
    if (!command.includes(' ')) {
      return command
    }
  }
  
  return null
}

/**
 * Parse all @ file mentions from text
 */
export function parseFileMentions(text: string): Array<{
  raw: string
  path: string
  startIndex: number
  endIndex: number
}> {
  const pattern = /@((?:[^\s@]|(?<=\\)\s)+)/g
  const mentions: Array<{
    raw: string
    path: string
    startIndex: number
    endIndex: number
  }> = []
  
  let match
  while ((match = pattern.exec(text)) !== null) {
    const raw = match[0]
    const path = match[1].replace(/\\ /g, ' ') // Unescape spaces
    
    mentions.push({
      raw,
      path,
      startIndex: match.index,
      endIndex: match.index + raw.length,
    })
  }
  
  return mentions
}

/**
 * Apply completion to text
 * Returns the new text with the completion applied
 */
export function applyCompletion(
  text: string,
  cursorPosition: number,
  completion: AutocompleteItem,
  type: 'file' | 'command'
): { text: string; newCursorPosition: number } {
  if (type === 'file') {
    const textUpToCursor = text.substring(0, cursorPosition)
    const match = AT_MENTION_PATTERN.exec(textUpToCursor)
    
    if (match) {
      const beforeMention = textUpToCursor.substring(0, match.index + 1) // Include @
      const afterCursor = text.substring(cursorPosition)
      const newText = beforeMention + completion.value + afterCursor
      const newCursorPosition = beforeMention.length + completion.value.length
      
      return { text: newText, newCursorPosition }
    }
  } else if (type === 'command') {
    // Replace the command after !
    const afterExclamation = text.substring(1)
    const spaceIndex = afterExclamation.indexOf(' ')
    
    if (spaceIndex === -1) {
      // No arguments yet, just replace the command
      return {
        text: '!' + completion.value,
        newCursorPosition: 1 + completion.value.length,
      }
    } else {
      // Keep arguments
      return {
        text: '!' + completion.value + afterExclamation.substring(spaceIndex),
        newCursorPosition: 1 + completion.value.length,
      }
    }
  }
  
  return { text, newCursorPosition: cursorPosition }
}

