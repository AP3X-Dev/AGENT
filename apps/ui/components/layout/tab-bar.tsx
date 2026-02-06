"use client";

import { Plus, X, Pin } from "lucide-react";
import { cn } from "@/lib/utils";
import { useTabs } from "@/providers/tabs-provider";
import { Button } from "@/components/ui/button";

export function TabBar() {
  const { tabs, activeTabId, addTab, removeTab, setActiveTab, updateTab } =
    useTabs();

  return (
    <div className="flex h-10 items-center bg-surface border-b border-[#1a1a1a]">
      <div className="flex items-center overflow-x-auto scrollbar-hide">
        {tabs.map((tab) => (
          <div
            key={tab.id}
            className={cn(
              "group flex h-10 min-w-[120px] max-w-[200px] items-center gap-2 px-3 cursor-pointer transition-all duration-150",
              activeTabId === tab.id
                ? "bg-surface-elevated text-text-primary border-b-2 border-text-muted"
                : "bg-transparent text-text-muted hover:bg-surface-secondary hover:text-text-secondary",
            )}
            onClick={() => setActiveTab(tab.id)}
          >
            <span className="truncate text-sm flex-1">
              {tab.isLoading ? "Loading..." : tab.title}
            </span>
            <button
              onClick={(e) => {
                e.stopPropagation();
                updateTab(tab.id, { pinned: !tab.pinned });
              }}
              title={tab.pinned ? "Unpin" : "Pin"}
              className={cn(
                "flex h-5 w-5 items-center justify-center rounded-sm transition-all",
                tab.pinned
                  ? "opacity-100 text-text-secondary"
                  : "opacity-0 group-hover:opacity-100 text-text-muted hover:text-text-secondary",
                "hover:bg-surface-elevated",
              )}
            >
              <Pin className="h-3 w-3" />
            </button>
            <button
              onClick={(e) => {
                e.stopPropagation();
                removeTab(tab.id);
              }}
              className={cn(
                "flex h-5 w-5 items-center justify-center rounded-sm transition-all",
                "opacity-0 group-hover:opacity-100 hover:bg-surface-elevated",
                activeTabId === tab.id && "opacity-40 group-hover:opacity-100",
              )}
            >
              <X className="h-3 w-3" />
            </button>
          </div>
        ))}
      </div>
      <Button
        variant="ghost"
        size="icon"
        className="h-10 w-10 shrink-0 text-text-muted hover:text-text-secondary hover:bg-surface-secondary"
        onClick={() => addTab()}
      >
        <Plus className="h-4 w-4" />
      </Button>
    </div>
  );
}
