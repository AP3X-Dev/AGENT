"use client"

import { useEffect, useRef, useCallback, useMemo } from 'react'
import { getAgentBus } from '@/lib/agent-bus'
import type {
  ModuleContext,
  BaseModuleContext,
  ModuleInstanceId,
  ModuleEvent,
  CommandHandler,
  AgentBusSubscription,
} from '@/types/agent-communication'
import type { ModuleTypeId } from '@/types/modules'

// ============================================================================
// Types
// ============================================================================

interface UseAgentConnectionOptions {
  /** Module instance ID */
  instanceId: ModuleInstanceId
  /** Module type */
  moduleType: ModuleTypeId
  /** Initial context data (module-specific) */
  initialContext?: Partial<Omit<ModuleContext, keyof BaseModuleContext>>
  /** Whether to auto-register on mount */
  autoRegister?: boolean
  /** Callback when a command is received */
  onCommand?: (action: string, params: unknown) => Promise<unknown> | unknown
}

interface AgentConnectionResult {
  /** Whether the module is registered with the agent */
  isRegistered: boolean
  /** Register the module context */
  register: (context?: Partial<ModuleContext>) => void
  /** Unregister the module */
  unregister: () => void
  /** Update the module context */
  updateContext: (updates: Partial<ModuleContext>) => void
  /** Send an event to the agent */
  sendEvent: <T>(type: string, data: T, options?: { requiresAttention?: boolean }) => void
  /** Register a command handler */
  onCommand: <TParams = unknown, TResult = unknown>(
    commandName: string,
    handler: CommandHandler<TParams, TResult>
  ) => AgentBusSubscription
  /** Focus changed handler */
  reportFocusChange: (focus: { type: string; id?: string; data?: unknown }) => void
  /** Selection changed handler */
  reportSelectionChange: (selection: unknown[]) => void
  /** Data changed handler */
  reportDataChange: (field: string, oldValue: unknown, newValue: unknown) => void
}

// ============================================================================
// Hook Implementation
// ============================================================================

/**
 * useAgentConnection - Hook for modules to connect to the agent communication system
 * 
 * This hook provides a clean interface for modules to:
 * - Register their context with the agent
 * - Update their context as state changes
 * - Send events to the agent
 * - Handle commands from the agent
 * 
 * @example
 * ```tsx
 * function MyModule({ instanceId }: ModuleInstanceProps) {
 *   const { updateContext, sendEvent, onCommand } = useAgentConnection({
 *     instanceId,
 *     moduleType: 'my-module',
 *     initialContext: { customData: {} },
 *   })
 * 
 *   // Register command handler
 *   useEffect(() => {
 *     const sub = onCommand('doSomething', async (params) => {
 *       // Handle the command
 *       return { success: true }
 *     })
 *     return () => sub.unsubscribe()
 *   }, [onCommand])
 * 
 *   // Update context when state changes
 *   useEffect(() => {
 *     updateContext({ data: { currentItem } })
 *   }, [currentItem, updateContext])
 * 
 *   // Send event on user action
 *   const handleClick = () => {
 *     sendEvent('user-interaction', { type: 'click', target: 'button' })
 *   }
 * }
 * ```
 */
export function useAgentConnection({
  instanceId,
  moduleType,
  initialContext,
  autoRegister = true,
  onCommand: onCommandProp,
}: UseAgentConnectionOptions): AgentConnectionResult {
  const bus = useMemo(() => getAgentBus(), [])
  const isRegisteredRef = useRef(false)
  const commandSubscriptionsRef = useRef<AgentBusSubscription[]>([])

  // Register module context
  const register = useCallback(
    (context?: Partial<ModuleContext>) => {
      if (isRegisteredRef.current) return

      const fullContext: BaseModuleContext = {
        instanceId,
        moduleType,
        state: { isLoading: false, error: null },
        isReady: true,
        lastUpdated: Date.now(),
        ...initialContext,
        ...context,
      }

      bus.registerContext(instanceId, fullContext as ModuleContext)
      isRegisteredRef.current = true
    },
    [bus, instanceId, moduleType, initialContext]
  )

  // Unregister module
  const unregister = useCallback(() => {
    if (!isRegisteredRef.current) return

    // Clean up command subscriptions
    commandSubscriptionsRef.current.forEach((sub) => sub.unsubscribe())
    commandSubscriptionsRef.current = []

    bus.unregisterContext(instanceId)
    isRegisteredRef.current = false
  }, [bus, instanceId])

  // Update context
  const updateContext = useCallback(
    (updates: Partial<ModuleContext>) => {
      if (!isRegisteredRef.current) return
      bus.updateContext(instanceId, updates)
    },
    [bus, instanceId]
  )

  // Send event
  const sendEvent = useCallback(
    <T,>(type: string, data: T, options?: { requiresAttention?: boolean }) => {
      const event: ModuleEvent<T> = {
        type,
        data,
        requiresAttention: options?.requiresAttention,
      }
      bus.emitModuleEvent(instanceId, event)
    },
    [bus, instanceId]
  )

  // Register command handler
  const onCommand = useCallback(
    <TParams = unknown, TResult = unknown>(
      commandName: string,
      handler: CommandHandler<TParams, TResult>
    ): AgentBusSubscription => {
      const subscription = bus.subscribeToCommands(instanceId, commandName, handler)
      commandSubscriptionsRef.current.push(subscription)
      return {
        unsubscribe: () => {
          subscription.unsubscribe()
          commandSubscriptionsRef.current = commandSubscriptionsRef.current.filter(
            (s) => s !== subscription
          )
        },
      }
    },
    [bus, instanceId]
  )

  // Convenience method for focus changes
  const reportFocusChange = useCallback(
    (focus: { type: string; id?: string; data?: unknown }) => {
      updateContext({ focus })
      sendEvent('focus-changed', { currentFocus: focus })
    },
    [updateContext, sendEvent]
  )

  // Convenience method for selection changes
  const reportSelectionChange = useCallback(
    (selection: unknown[]) => {
      sendEvent('selection-changed', { selection })
    },
    [sendEvent]
  )

  // Convenience method for data changes
  const reportDataChange = useCallback(
    (field: string, oldValue: unknown, newValue: unknown) => {
      sendEvent('data-changed', { field, oldValue, newValue })
    },
    [sendEvent]
  )

  // Auto-register on mount
  useEffect(() => {
    if (autoRegister) {
      register()
    }
    return () => {
      unregister()
    }
  }, [autoRegister, register, unregister])

  // Handle generic command callback
  useEffect(() => {
    if (!onCommandProp) return

    // Subscribe to all commands and delegate to callback
    const subscription = bus.subscribe(
      {
        type: 'command',
        target: { type: 'module', id: instanceId },
      },
      async (message) => {
        const command = message.payload as { action: string; params: unknown }
        try {
          const result = await onCommandProp(command.action, command.params)
          if (message.correlationId) {
            bus.send({
              type: 'response',
              source: { type: 'module', id: instanceId },
              target: message.source,
              payload: { success: true, data: result },
              correlationId: message.correlationId,
            })
          }
        } catch (error) {
          if (message.correlationId) {
            bus.send({
              type: 'response',
              source: { type: 'module', id: instanceId },
              target: message.source,
              payload: {
                success: false,
                error: error instanceof Error ? error.message : 'Command failed',
              },
              correlationId: message.correlationId,
            })
          }
        }
      }
    )

    return () => subscription.unsubscribe()
  }, [bus, instanceId, onCommandProp])

  return {
    isRegistered: isRegisteredRef.current,
    register,
    unregister,
    updateContext,
    sendEvent,
    onCommand,
    reportFocusChange,
    reportSelectionChange,
    reportDataChange,
  }
}

export default useAgentConnection

