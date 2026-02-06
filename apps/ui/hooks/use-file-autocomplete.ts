/**
 * useFileAutocomplete Hook
 * Provides file path autocomplete functionality for @ mentions
 */

import { useState, useCallback, useEffect, useRef } from 'react'
import type { AutocompleteItem } from '@/types/cli'
import {
  getFileCompletions,
  getCommandCompletions,
  detectAtMention,
  detectBashCommand,
  applyCompletion,
} from '@/lib/cli/autocomplete'

interface UseFileAutocompleteOptions {
  debounceMs?: number
  maxItems?: number
}

interface UseFileAutocompleteReturn {
  items: AutocompleteItem[]
  isLoading: boolean
  isOpen: boolean
  selectedIndex: number
  activeType: 'file' | 'command' | null
  updateQuery: (text: string, cursorPosition: number) => void
  selectNext: () => void
  selectPrevious: () => void
  selectItem: (index?: number) => { text: string; newCursorPosition: number } | null
  close: () => void
  currentText: string
  cursorPosition: number
}

export function useFileAutocomplete(
  options: UseFileAutocompleteOptions = {}
): UseFileAutocompleteReturn {
  const { debounceMs = 150, maxItems = 10 } = options

  const [items, setItems] = useState<AutocompleteItem[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [isOpen, setIsOpen] = useState(false)
  const [selectedIndex, setSelectedIndex] = useState(0)
  const [activeType, setActiveType] = useState<'file' | 'command' | null>(null)
  const [currentText, setCurrentText] = useState('')
  const [cursorPosition, setCursorPosition] = useState(0)

  const debounceRef = useRef<NodeJS.Timeout | null>(null)

  const updateQuery = useCallback(
    (text: string, position: number) => {
      setCurrentText(text)
      setCursorPosition(position)

      // Clear previous debounce
      if (debounceRef.current) {
        clearTimeout(debounceRef.current)
      }

      // Check for @ file mention
      const filePath = detectAtMention(text, position)
      if (filePath !== null) {
        setActiveType('file')
        setIsLoading(true)
        setIsOpen(true)

        debounceRef.current = setTimeout(async () => {
          try {
            const response = await getFileCompletions(filePath, maxItems)
            setItems(response.items)
            setSelectedIndex(0)
          } catch (error) {
            setItems([])
          } finally {
            setIsLoading(false)
          }
        }, debounceMs)
        return
      }

      // Check for ! bash command
      const bashCommand = detectBashCommand(text)
      if (bashCommand !== null) {
        setActiveType('command')
        const commandItems = getCommandCompletions(bashCommand)
        setItems(commandItems.slice(0, maxItems))
        setSelectedIndex(0)
        setIsOpen(commandItems.length > 0)
        setIsLoading(false)
        return
      }

      // No autocomplete context
      setIsOpen(false)
      setActiveType(null)
      setItems([])
    },
    [debounceMs, maxItems]
  )

  const selectNext = useCallback(() => {
    setSelectedIndex((prev) => (prev + 1) % items.length)
  }, [items.length])

  const selectPrevious = useCallback(() => {
    setSelectedIndex((prev) => (prev - 1 + items.length) % items.length)
  }, [items.length])

  const selectItem = useCallback(
    (index?: number): { text: string; newCursorPosition: number } | null => {
      const itemIndex = index ?? selectedIndex
      const item = items[itemIndex]

      if (!item || !activeType) {
        return null
      }

      const result = applyCompletion(currentText, cursorPosition, item, activeType)
      setIsOpen(false)
      setItems([])
      return result
    },
    [items, selectedIndex, activeType, currentText, cursorPosition]
  )

  const close = useCallback(() => {
    setIsOpen(false)
    setItems([])
    setActiveType(null)
  }, [])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (debounceRef.current) {
        clearTimeout(debounceRef.current)
      }
    }
  }, [])

  return {
    items,
    isLoading,
    isOpen,
    selectedIndex,
    activeType,
    updateQuery,
    selectNext,
    selectPrevious,
    selectItem,
    close,
    currentText,
    cursorPosition,
  }
}

