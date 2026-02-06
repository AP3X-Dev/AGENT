"use client"

import type React from "react"

import { ThemeProvider } from "next-themes"
import { AppProvider } from "./app-provider"
import { ChatProvider } from "./chat-provider"
import { TabsProvider } from "./tabs-provider"
import { AgentProvider } from "./agent-provider"
import { TasksProvider } from "./tasks-provider"
import { BrowserSessionProvider } from "./browser-session-provider"

// Re-export hooks for convenience
export { useApp } from "./app-provider"
export { useTasks, TasksProvider, type Task } from "./tasks-provider"
export { useChat } from "./chat-provider"
export { useTabs } from "./tabs-provider"
export {
  useAgent,
  useAgentSubscription,
  useModuleContexts,
  useModuleContext,
} from "./agent-provider"

// Re-export tab context hooks
export {
  useTabContext,
  useActiveTabContext,
  useTabSearch,
  useBackgroundTabs,
  useAssembledContext,
  useTabStateEvents,
  useTabContextManager,
} from "@/hooks/use-tab-context"

// Re-export browser session hook
export { useBrowserSession } from "./browser-session-provider"

// Combined Providers wrapper
export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <ThemeProvider attribute="class" defaultTheme="dark" enableSystem disableTransitionOnChange>
      <AppProvider>
        <BrowserSessionProvider>
          <ChatProvider>
            <TabsProvider>
              <AgentProvider config={{ debug: process.env.NODE_ENV === 'development' }}>
                <TasksProvider>
                  {children}
                </TasksProvider>
              </AgentProvider>
            </TabsProvider>
          </ChatProvider>
        </BrowserSessionProvider>
      </AppProvider>
    </ThemeProvider>
  )
}
