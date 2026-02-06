"use client";

import {
  createContext,
  useContext,
  useState,
  useCallback,
  useEffect,
  useRef,
  type ReactNode,
} from "react";
import type { Tab, TabsState } from "@/types/types";
import { getTabContextManager } from "@/lib/tab-context-manager";
import { closeBrowserSession } from "./browser-session-provider";

interface TabsContextType extends TabsState {
  addTab: (tab?: Partial<Tab>) => string;
  removeTab: (id: string) => void;
  setActiveTab: (id: string) => void;
  updateTab: (id: string, updates: Partial<Tab>) => void;
  getActiveTab: () => Tab | undefined;
}

const TabsContext = createContext<TabsContextType | undefined>(undefined);

// Generate unique tab ID
const generateTabId = () =>
  `tab-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;

// Generate unique module instance ID
const generateModuleInstanceId = () =>
  `module-${Date.now().toString(36)}-${Math.random().toString(36).substring(2, 9)}`;

// Default first tab
const createDefaultTab = (): Tab => ({
  id: generateTabId(),
  title: "New Tab",
  url: null,
  isLoading: false,
  error: null,
  moduleType: "browser",
  moduleInstanceId: generateModuleInstanceId(),
  closable: true,
});

export function TabsProvider({ children }: { children: ReactNode }) {
  // Create initial tab with stable ID
  const initialTabRef = useRef<Tab | null>(null);
  if (!initialTabRef.current) {
    initialTabRef.current = createDefaultTab();
  }
  const initialTab = initialTabRef.current;

  const [tabs, setTabs] = useState<Tab[]>([initialTab]);
  const [activeTabId, setActiveTabIdState] = useState<string | null>(
    initialTab.id,
  );

  // Get tab context manager
  const contextManager = getTabContextManager();

  // Register initial tab with context manager
  useEffect(() => {
    contextManager.registerTab(initialTab);
    contextManager.setActiveTab(initialTab.id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Sync tab changes with context manager
  const syncTabToContextManager = useCallback(
    (tab: Tab) => {
      contextManager.updateTab(tab);
    },
    [contextManager],
  );

  const addTab = useCallback(
    (tabData?: Partial<Tab>): string => {
      const newTab: Tab = {
        id: generateTabId(),
        title: tabData?.title || "New Tab",
        url: tabData?.url || null,
        isLoading: tabData?.isLoading || false,
        error: tabData?.error || null,
        moduleType: tabData?.moduleType || "browser",
        moduleInstanceId:
          tabData?.moduleInstanceId || generateModuleInstanceId(),
        moduleData: tabData?.moduleData,
        icon: tabData?.icon,
        closable: tabData?.closable ?? true,
        pinned: tabData?.pinned ?? false,
      };

      // Register with context manager
      contextManager.registerTab(newTab);

      setTabs((prev) => [...prev, newTab]);
      setActiveTabIdState(newTab.id);
      contextManager.setActiveTab(newTab.id);

      return newTab.id;
    },
    [contextManager],
  );

  const removeTab = useCallback(
    (id: string) => {
      // Find the tab to get its session info before removing
      const tabToRemove = tabs.find((tab) => tab.id === id);

      // If it's an agent-browser tab with a session, close the session on the server
      if (
        tabToRemove?.moduleType === "agent-browser" &&
        tabToRemove.moduleData?.sessionId
      ) {
        const sessionId = tabToRemove.moduleData.sessionId as string;
        console.log(
          "[TabsProvider] Closing browser session for removed tab:",
          sessionId,
        );
        // Close asynchronously - don't block tab removal
        closeBrowserSession(sessionId).catch((err) => {
          console.error("[TabsProvider] Failed to close browser session:", err);
        });
      }

      // Unregister from context manager
      contextManager.unregisterTab(id);

      setTabs((prev) => {
        const newTabs = prev.filter((tab) => tab.id !== id);

        // If no tabs left, create a new default tab
        if (newTabs.length === 0) {
          const defaultTab = createDefaultTab();
          contextManager.registerTab(defaultTab);
          contextManager.setActiveTab(defaultTab.id);
          setActiveTabIdState(defaultTab.id);
          return [defaultTab];
        }

        return newTabs;
      });

      // If removing active tab, switch to another
      setActiveTabIdState((currentActiveId) => {
        if (currentActiveId === id) {
          // Find next tab to activate
          const currentIndex = tabs.findIndex((tab) => tab.id === id);
          const remainingTabs = tabs.filter((tab) => tab.id !== id);

          if (remainingTabs.length === 0) {
            return null;
          }

          // Prefer the tab to the left, otherwise the tab to the right
          const newIndex = Math.min(currentIndex, remainingTabs.length - 1);
          const nextTabId = remainingTabs[Math.max(0, newIndex)]?.id || null;

          if (nextTabId) {
            contextManager.setActiveTab(nextTabId);
          }

          return nextTabId;
        }
        return currentActiveId;
      });
    },
    [tabs, contextManager],
  );

  const setActiveTab = useCallback(
    (id: string) => {
      setActiveTabIdState(id);
      contextManager.setActiveTab(id);
    },
    [contextManager],
  );

  const updateTab = useCallback(
    (id: string, updates: Partial<Tab>) => {
      setTabs((prev) => {
        const updated = prev.map((tab) => {
          if (tab.id === id) {
            const updatedTab = { ...tab, ...updates };
            // Sync with context manager
            syncTabToContextManager(updatedTab);
            return updatedTab;
          }
          return tab;
        });
        return updated;
      });
    },
    [syncTabToContextManager],
  );

  const getActiveTab = useCallback((): Tab | undefined => {
    return tabs.find((tab) => tab.id === activeTabId);
  }, [tabs, activeTabId]);

  return (
    <TabsContext.Provider
      value={{
        tabs,
        activeTabId,
        addTab,
        removeTab,
        setActiveTab,
        updateTab,
        getActiveTab,
      }}
    >
      {children}
    </TabsContext.Provider>
  );
}

export function useTabs() {
  const context = useContext(TabsContext);
  if (context === undefined) {
    throw new Error("useTabs must be used within a TabsProvider");
  }
  return context;
}
