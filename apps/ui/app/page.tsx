"use client"

import { IconSidebar } from "@/components/layout/icon-sidebar"
import { ResizableLayout } from "@/components/layout/resizable-layout"
import { ChatSidebar } from "@/components/features/chat/chat-sidebar"
import { PreviewPanel } from "@/components/preview-panel"

export default function V0ClonePage() {
  return (
    <div data-testid="main-layout" className="flex h-screen w-full bg-primary-background font-sans text-text-primary">
      <IconSidebar className="w-14 shrink-0" />
      <div className="flex-1 overflow-hidden px-2 py-2">
        <ResizableLayout
          sidebarContent={<ChatSidebar />}
          mainContent={<PreviewPanel className="rounded-lg overflow-hidden" />}
        />
      </div>
    </div>
  )
}
