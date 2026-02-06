/**
 * Tab Context Manager
 *
 * Central manager for tab context operations enabling intelligent querying
 * and retrieval of information from specific tabs without loading all
 * contexts into the conversation window.
 */

import { getAgentBus } from "./agent-bus";
import type { Tab } from "@/types/types";
import type {
  ModuleContext,
  ModuleInstanceId,
} from "@/types/agent-communication";
import type {
  TabContext,
  TabPriority,
  TabSummary,
  TabSearchCriteria,
  TabSearchResult,
  TabStateEvent,
  TabStateEventType,
  TabContextSummary,
  ContextAssemblyOptions,
  AssembledContext,
  ITabContextManager,
} from "@/types/tab-context";

// ============================================================================
// Priority Order
// ============================================================================

const PRIORITY_ORDER: Record<TabPriority, number> = {
  critical: 0,
  high: 1,
  normal: 2,
  low: 3,
  background: 4,
};

// ============================================================================
// Tab Context Manager Implementation
// ============================================================================

class TabContextManager implements ITabContextManager {
  private tabContexts: Map<string, TabContext> = new Map();
  private stateChangeHandlers: Set<(event: TabStateEvent) => void> = new Set();
  private activeTabId: string | null = null;

  constructor() {
    // Subscribe to module context updates from AgentBus
    const bus = getAgentBus();
    bus.subscribe(
      {
        type: ["context-update", "ready", "destroyed"],
        source: { type: "module" },
      },
      (message) => {
        const moduleContext = message.payload as ModuleContext;
        this.updateModuleContext(moduleContext);
      },
    );
  }

  // --------------------------------------------------------------------------
  // Context Retrieval
  // --------------------------------------------------------------------------

  getTabContext(tabId: string): TabContext | undefined {
    return this.tabContexts.get(tabId);
  }

  getActiveTabContext(): TabContext | undefined {
    if (!this.activeTabId) return undefined;
    return this.tabContexts.get(this.activeTabId);
  }

  getAllTabContexts(): TabContext[] {
    return Array.from(this.tabContexts.values());
  }

  // --------------------------------------------------------------------------
  // Querying
  // --------------------------------------------------------------------------

  searchTabs(criteria: TabSearchCriteria): TabSearchResult {
    let results = this.getAllTabContexts();

    // Apply filters
    if (criteria.tabIds?.length) {
      results = results.filter((ctx) => criteria.tabIds!.includes(ctx.tab.id));
    }
    if (criteria.instanceIds?.length) {
      results = results.filter(
        (ctx) =>
          ctx.tab.moduleInstanceId &&
          criteria.instanceIds!.includes(ctx.tab.moduleInstanceId),
      );
    }
    if (criteria.moduleTypes?.length) {
      results = results.filter(
        (ctx) =>
          ctx.tab.moduleType &&
          criteria.moduleTypes!.includes(ctx.tab.moduleType),
      );
    }
    if (criteria.isActive !== undefined) {
      results = results.filter((ctx) => ctx.isActive === criteria.isActive);
    }
    if (criteria.isLoading !== undefined) {
      results = results.filter(
        (ctx) => ctx.tab.isLoading === criteria.isLoading,
      );
    }
    if (criteria.hasError !== undefined) {
      results = results.filter((ctx) =>
        criteria.hasError ? !!ctx.tab.error : !ctx.tab.error,
      );
    }
    if (criteria.urlPattern) {
      const pattern =
        typeof criteria.urlPattern === "string"
          ? new RegExp(criteria.urlPattern, "i")
          : criteria.urlPattern;
      results = results.filter(
        (ctx) => ctx.tab.url && pattern.test(ctx.tab.url),
      );
    }
    if (criteria.titlePattern) {
      const pattern =
        typeof criteria.titlePattern === "string"
          ? new RegExp(criteria.titlePattern, "i")
          : criteria.titlePattern;
      results = results.filter((ctx) => pattern.test(ctx.tab.title));
    }
    if (criteria.hasUnsavedChanges !== undefined) {
      results = results.filter(
        (ctx) => ctx.summary?.hasUnsavedChanges === criteria.hasUnsavedChanges,
      );
    }
    if (criteria.contentTypes?.length) {
      results = results.filter(
        (ctx) =>
          ctx.summary?.contentType &&
          criteria.contentTypes!.includes(ctx.summary.contentType),
      );
    }
    if (criteria.priorities?.length) {
      results = results.filter((ctx) =>
        criteria.priorities!.includes(ctx.priority),
      );
    }
    if (criteria.customFilter) {
      results = results.filter(criteria.customFilter);
    }

    const totalCount = results.length;

    // Sort
    if (criteria.sortBy) {
      results.sort((a, b) => {
        let comparison = 0;
        switch (criteria.sortBy) {
          case "lastAccessed":
            comparison = a.lastAccessedAt - b.lastAccessedAt;
            break;
          case "lastUpdated":
            comparison = a.lastUpdatedAt - b.lastUpdatedAt;
            break;
          case "priority":
            comparison =
              PRIORITY_ORDER[a.priority] - PRIORITY_ORDER[b.priority];
            break;
          case "title":
            comparison = a.tab.title.localeCompare(b.tab.title);
            break;
        }
        return criteria.sortDirection === "desc" ? -comparison : comparison;
      });
    }

    // Limit
    if (criteria.limit && results.length > criteria.limit) {
      results = results.slice(0, criteria.limit);
    }

    return {
      tabs: results,
      totalCount,
      criteria,
      searchedAt: Date.now(),
    };
  }

  findTabsByModuleType(moduleType: string): TabContext[] {
    return this.searchTabs({ moduleTypes: [moduleType] }).tabs;
  }

  findTabsByUrl(pattern: string | RegExp): TabContext[] {
    return this.searchTabs({ urlPattern: pattern }).tabs;
  }

  // --------------------------------------------------------------------------
  // Summaries
  // --------------------------------------------------------------------------

  getTabSummary(tabId: string): TabSummary | undefined {
    return this.tabContexts.get(tabId)?.summary;
  }

  async generateTabSummary(tabId: string): Promise<TabSummary> {
    const context = this.tabContexts.get(tabId);
    if (!context) {
      return this.createDefaultSummary("Tab not found");
    }

    // Generate summary from tab and module context
    const summary = this.createSummaryFromContext(context);

    // Cache the summary
    context.summary = summary;
    this.tabContexts.set(tabId, context);

    return summary;
  }

  summarizeBackgroundTabs(): TabContextSummary[] {
    return this.getAllTabContexts()
      .filter((ctx) => !ctx.isActive)
      .sort((a, b) => PRIORITY_ORDER[a.priority] - PRIORITY_ORDER[b.priority])
      .map((ctx) => ({
        tabId: ctx.tab.id,
        title: ctx.tab.title,
        moduleType: ctx.tab.moduleType,
        summary: ctx.summary || this.createSummaryFromContext(ctx),
        isActive: ctx.isActive,
        priority: ctx.priority,
      }));
  }

  private createDefaultSummary(title: string): TabSummary {
    return {
      title,
      description: "",
      contentType: "empty",
      generatedAt: Date.now(),
    };
  }

  private createSummaryFromContext(context: TabContext): TabSummary {
    const { tab, moduleContext } = context;

    // Determine content type
    let contentType: TabSummary["contentType"] = "empty";
    if (tab.url) {
      contentType = "webpage";
    }
    if (tab.moduleType === "crm" || tab.moduleType === "email") {
      contentType = "form";
    }
    if (tab.moduleType === "file-manager") {
      contentType = "document";
    }

    // Build description
    const parts: string[] = [];
    if (tab.url) {
      parts.push(`URL: ${tab.url}`);
    }
    if (tab.moduleType) {
      parts.push(`Module: ${tab.moduleType}`);
    }
    if (moduleContext?.focus) {
      parts.push(`Focus: ${JSON.stringify(moduleContext.focus)}`);
    }

    // Key points from module context
    const keyPoints: string[] = [];
    if (moduleContext) {
      if (moduleContext.state?.isLoading) keyPoints.push("Loading");
      if (moduleContext.state?.error)
        keyPoints.push(`Error: ${moduleContext.state.error}`);
    }
    if (tab.isLoading) keyPoints.push("Tab loading");
    if (tab.error) keyPoints.push(`Tab error: ${tab.error}`);

    return {
      title: tab.title,
      description: parts.join(". ") || "No additional information",
      keyPoints: keyPoints.length > 0 ? keyPoints : undefined,
      contentType,
      hasUnsavedChanges: false, // Would need module-specific logic
      contentSize: "small",
      generatedAt: Date.now(),
    };
  }

  // --------------------------------------------------------------------------
  // Context Assembly
  // --------------------------------------------------------------------------

  assembleContext(options: ContextAssemblyOptions = {}): AssembledContext {
    const {
      includeActiveTabFull = true,
      includeBackgroundSummaries = true,
      maxBackgroundTabs = 10,
      minPriority = "background",
      includeModuleContext = true,
    } = options;

    const activeTab = this.getActiveTabContext();
    const backgroundTabs: TabContextSummary[] = [];

    if (includeBackgroundSummaries) {
      const minPriorityValue = PRIORITY_ORDER[minPriority];
      const eligible = this.getAllTabContexts()
        .filter(
          (ctx) =>
            !ctx.isActive && PRIORITY_ORDER[ctx.priority] <= minPriorityValue,
        )
        .sort((a, b) => PRIORITY_ORDER[a.priority] - PRIORITY_ORDER[b.priority])
        .slice(0, maxBackgroundTabs);

      for (const ctx of eligible) {
        backgroundTabs.push({
          tabId: ctx.tab.id,
          title: ctx.tab.title,
          moduleType: ctx.tab.moduleType,
          summary: ctx.summary || this.createSummaryFromContext(ctx),
          isActive: false,
          priority: ctx.priority,
        });
      }
    }

    // Prepare active tab (optionally strip module context for lighter payload)
    let processedActiveTab = activeTab;
    if (activeTab && !includeModuleContext) {
      processedActiveTab = { ...activeTab, moduleContext: undefined };
    }

    return {
      activeTab: includeActiveTabFull ? processedActiveTab : undefined,
      backgroundTabs,
      totalTabs: this.tabContexts.size,
      options,
      assembledAt: Date.now(),
      estimatedTokens: this.estimateTokens(processedActiveTab, backgroundTabs),
    };
  }

  private estimateTokens(
    activeTab: TabContext | undefined,
    backgroundTabs: TabContextSummary[],
  ): number {
    // Rough estimation: ~4 chars per token
    let chars = 0;
    if (activeTab) {
      chars += JSON.stringify(activeTab).length;
    }
    chars += JSON.stringify(backgroundTabs).length;
    return Math.ceil(chars / 4);
  }

  // --------------------------------------------------------------------------
  // State Management
  // --------------------------------------------------------------------------

  updateTabContext(tabId: string, updates: Partial<TabContext>): void {
    const existing = this.tabContexts.get(tabId);
    if (existing) {
      const updated = { ...existing, ...updates, lastUpdatedAt: Date.now() };
      this.tabContexts.set(tabId, updated);
      this.emitStateChange("tab-context-changed", tabId, updated.tab);
    }
  }

  setTabPriority(tabId: string, priority: TabPriority): void {
    this.updateTabContext(tabId, { priority });
  }

  // --------------------------------------------------------------------------
  // Tab State Synchronization (called by TabsProvider)
  // --------------------------------------------------------------------------

  registerTab(tab: Tab): void {
    const isActive = tab.id === this.activeTabId;
    const priority = isActive ? "high" : tab.pinned ? "high" : "normal";

    const context: TabContext = {
      tab,
      isActive,
      lastAccessedAt: Date.now(),
      lastUpdatedAt: Date.now(),
      priority,
    };
    this.tabContexts.set(tab.id, context);
    this.emitStateChange("tab-opened", tab.id, tab);
  }

  unregisterTab(tabId: string): void {
    const context = this.tabContexts.get(tabId);
    if (context) {
      this.tabContexts.delete(tabId);
      this.emitStateChange("tab-closed", tabId, context.tab);
    }
  }

  updateTab(tab: Tab): void {
    const existing = this.tabContexts.get(tab.id);

    if (existing) {
      const priority = existing.isActive
        ? "high"
        : tab.pinned
          ? "high"
          : "normal";
      const updated: TabContext = {
        ...existing,
        tab,
        priority,
        lastUpdatedAt: Date.now(),
      };
      this.tabContexts.set(tab.id, updated);
      this.emitStateChange("tab-updated", tab.id, tab);
      return;
    }

    this.registerTab(tab);
  }

  setActiveTab(tabId: string | null): void {
    const previousId = this.activeTabId;
    this.activeTabId = tabId;

    // Deactivate previous
    if (previousId) {
      const prev = this.tabContexts.get(previousId);
      if (prev) {
        prev.isActive = false;
        prev.priority = prev.tab.pinned ? "high" : "normal";
        this.tabContexts.set(previousId, prev);
        this.emitStateChange("tab-deactivated", previousId, prev.tab);
      }
    }

    // Activate new
    if (tabId) {
      const current = this.tabContexts.get(tabId);
      if (current) {
        current.isActive = true;
        current.priority = "high";
        current.lastAccessedAt = Date.now();
        this.tabContexts.set(tabId, current);
        this.emitStateChange("tab-activated", tabId, current.tab);
      }
    }
  }

  private updateModuleContext(moduleContext: ModuleContext): void {
    // Find tab by module instance ID
    for (const [tabId, context] of this.tabContexts) {
      if (context.tab.moduleInstanceId === moduleContext.instanceId) {
        context.moduleContext = moduleContext;
        context.lastUpdatedAt = Date.now();
        this.tabContexts.set(tabId, context);
        break;
      }
    }
  }

  // --------------------------------------------------------------------------
  // Event Subscription
  // --------------------------------------------------------------------------

  onTabStateChange(handler: (event: TabStateEvent) => void): () => void {
    this.stateChangeHandlers.add(handler);
    return () => this.stateChangeHandlers.delete(handler);
  }

  private emitStateChange(
    type: TabStateEventType,
    tabId: string,
    tab?: Tab,
  ): void {
    const event: TabStateEvent = {
      type,
      tabId,
      tab,
      timestamp: Date.now(),
    };

    // Notify local handlers
    this.stateChangeHandlers.forEach((handler) => handler(event));

    // Broadcast to AgentBus
    const bus = getAgentBus();
    bus.send({
      type: "event",
      source: { type: "system", id: "tab-context-manager" },
      target: { type: "agent" },
      payload: event,
    });
  }
}

// ============================================================================
// Singleton Instance
// ============================================================================

let tabContextManagerInstance: TabContextManager | null = null;

export function getTabContextManager(): TabContextManager {
  if (!tabContextManagerInstance) {
    tabContextManagerInstance = new TabContextManager();
  }
  return tabContextManagerInstance;
}

export function resetTabContextManager(): void {
  tabContextManagerInstance = null;
}

export { TabContextManager };
export default getTabContextManager;
