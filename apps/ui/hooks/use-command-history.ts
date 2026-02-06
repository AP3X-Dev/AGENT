/**
 * useCommandHistory Hook
 * Provides command/chat history with up/down arrow navigation
 */

import { useState, useCallback, useRef, useEffect } from 'react'
import type { CommandHistoryEntry, InputMode } from '@/types/cli'

const STORAGE_KEY = 'ap3x-command-history'
const MAX_ENTRIES = 100

interface UseCommandHistoryOptions {
  maxEntries?: number
  persistToStorage?: boolean
}

interface UseCommandHistoryReturn {
  entries: CommandHistoryEntry[]
  currentIndex: number
  currentInput: string
  addEntry: (input: string, type: InputMode) => void
  navigateUp: (currentValue: string) => string | null
  navigateDown: () => string | null
  reset: () => void
  clearHistory: () => void
}

export function useCommandHistory(
  options: UseCommandHistoryOptions = {}
): UseCommandHistoryReturn {
  const { maxEntries = MAX_ENTRIES, persistToStorage = true } = options

  const [entries, setEntries] = useState<CommandHistoryEntry[]>([])
  const [currentIndex, setCurrentIndex] = useState(-1)
  const [currentInput, setCurrentInput] = useState('')

  // Store the original input before navigation started
  const originalInputRef = useRef<string>('')

  // Load from localStorage on mount
  useEffect(() => {
    if (persistToStorage && typeof window !== 'undefined') {
      try {
        const stored = localStorage.getItem(STORAGE_KEY)
        if (stored) {
          const parsed = JSON.parse(stored)
          setEntries(parsed.map((e: any) => ({
            ...e,
            timestamp: new Date(e.timestamp),
          })))
        }
      } catch (error) {
        console.error('Failed to load command history:', error)
      }
    }
  }, [persistToStorage])

  // Save to localStorage when entries change
  useEffect(() => {
    if (persistToStorage && typeof window !== 'undefined' && entries.length > 0) {
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(entries))
      } catch (error) {
        console.error('Failed to save command history:', error)
      }
    }
  }, [entries, persistToStorage])

  const addEntry = useCallback(
    (input: string, type: InputMode) => {
      const trimmed = input.trim()
      if (!trimmed) return

      // Don't add duplicates of the last entry
      setEntries((prev) => {
        if (prev.length > 0 && prev[prev.length - 1].input === trimmed) {
          return prev
        }

        const newEntry: CommandHistoryEntry = {
          id: Date.now().toString(),
          input: trimmed,
          timestamp: new Date(),
          type,
        }

        const newEntries = [...prev, newEntry]

        // Trim to max entries
        if (newEntries.length > maxEntries) {
          return newEntries.slice(-maxEntries)
        }

        return newEntries
      })

      // Reset navigation state
      setCurrentIndex(-1)
      setCurrentInput('')
      originalInputRef.current = ''
    },
    [maxEntries]
  )

  const navigateUp = useCallback(
    (currentValue: string): string | null => {
      if (entries.length === 0) return null

      // Store original input when starting navigation
      if (currentIndex === -1) {
        originalInputRef.current = currentValue
      }

      const newIndex = currentIndex === -1 ? entries.length - 1 : Math.max(0, currentIndex - 1)
      setCurrentIndex(newIndex)
      setCurrentInput(entries[newIndex].input)

      return entries[newIndex].input
    },
    [entries, currentIndex]
  )

  const navigateDown = useCallback((): string | null => {
    if (entries.length === 0 || currentIndex === -1) return null

    const newIndex = currentIndex + 1

    if (newIndex >= entries.length) {
      // Return to original input
      setCurrentIndex(-1)
      setCurrentInput(originalInputRef.current)
      return originalInputRef.current
    }

    setCurrentIndex(newIndex)
    setCurrentInput(entries[newIndex].input)
    return entries[newIndex].input
  }, [entries, currentIndex])

  const reset = useCallback(() => {
    setCurrentIndex(-1)
    setCurrentInput('')
    originalInputRef.current = ''
  }, [])

  const clearHistory = useCallback(() => {
    setEntries([])
    setCurrentIndex(-1)
    setCurrentInput('')
    originalInputRef.current = ''

    if (persistToStorage && typeof window !== 'undefined') {
      localStorage.removeItem(STORAGE_KEY)
    }
  }, [persistToStorage])

  return {
    entries,
    currentIndex,
    currentInput,
    addEntry,
    navigateUp,
    navigateDown,
    reset,
    clearHistory,
  }
}

