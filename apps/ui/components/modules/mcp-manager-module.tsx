"use client"

import { useState, useEffect, useCallback } from "react"
import { 
  Search, 
  Plus, 
  Settings, 
  RefreshCw, 
  Power, 
  Trash2, 
  TestTube,
  Download,
  ExternalLink,
  CheckCircle2,
  XCircle,
  Loader2,
  Globe,
  Brain,
  BookOpen,
  Database,
  FolderOpen,
  Github,
  Plug,
} from "lucide-react"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Switch } from "@/components/ui/switch"
import { cn } from "@/lib/utils"
import { ModuleContainer, EmptyModuleState, LoadingModuleState } from "./module-container"
import type { ModuleConfig, ModuleInstanceProps } from "@/types/modules"
import type { 
  McpServerConfig, 
  McpCatalogEntry, 
  McpConnectionStatus,
  McpServerCategory,
} from "@/types/mcp"

/**
 * MCP Manager Module Configuration
 */
export const mcpManagerModuleConfig: ModuleConfig = {
  metadata: {
    id: 'mcp-manager',
    displayName: 'MCP Manager',
    description: 'Manage MCP (Model Context Protocol) server connections',
    icon: 'Plug',
    category: 'utility',
    version: '1.0.0',
  },
  hasHeader: true,
  initialState: {
    isLoading: true,
    error: null,
    data: { servers: [], catalog: [], view: 'installed' },
  },
}

// Icon mapping for categories
const CATEGORY_ICONS: Record<McpServerCategory | string, React.ReactNode> = {
  browser: <Globe className="h-4 w-4" />,
  ai: <Brain className="h-4 w-4" />,
  developer: <BookOpen className="h-4 w-4" />,
  database: <Database className="h-4 w-4" />,
  filesystem: <FolderOpen className="h-4 w-4" />,
  search: <Search className="h-4 w-4" />,
  utility: <Settings className="h-4 w-4" />,
  other: <Plug className="h-4 w-4" />,
}

// Status configuration type
type StatusConfig = { color: string; icon: typeof CheckCircle2; label: string }

// Status configurations
const STATUS_CONFIGS: Record<McpConnectionStatus, StatusConfig> = {
  connected: { color: 'bg-success/20 text-success border-success/30', icon: CheckCircle2, label: 'Connected' },
  disconnected: { color: 'bg-muted/20 text-muted-foreground border-muted/30', icon: XCircle, label: 'Disconnected' },
  connecting: { color: 'bg-warning/20 text-warning border-warning/30', icon: Loader2, label: 'Connecting' },
  error: { color: 'bg-destructive/20 text-destructive border-destructive/30', icon: XCircle, label: 'Error' },
  unknown: { color: 'bg-muted/20 text-muted-foreground border-muted/30', icon: Plug, label: 'Unknown' },
}

// Status indicator component
function StatusBadge({ status }: { status: McpConnectionStatus }) {
  const config = STATUS_CONFIGS[status] || STATUS_CONFIGS.unknown
  const Icon = config.icon
  return (
    <Badge variant="outline" className={cn("gap-1 text-xs", config.color)}>
      <Icon className={cn("h-3 w-3", status === 'connecting' && "animate-spin")} />
      {config.label}
    </Badge>
  )
}

// Server card component
function McpServerCard({
  server,
  onToggle,
  onTest,
  onDelete,
  isTestLoading,
}: {
  server: McpServerConfig
  onToggle: (id: string, enabled: boolean) => void
  onTest: (id: string) => void
  onDelete: (id: string) => void
  isTestLoading: boolean
}) {
  const icon = CATEGORY_ICONS[server.category] || CATEGORY_ICONS.other
  
  return (
    <div className={cn(
      "flex items-center gap-4 p-4 rounded-lg border transition-colors",
      server.enabled 
        ? "bg-surface-elevated border-interactive-border" 
        : "bg-muted/20 border-muted/30 opacity-75"
    )}>
      <div className={cn(
        "flex h-10 w-10 items-center justify-center rounded-lg",
        server.enabled ? "bg-primary/10 text-primary" : "bg-muted text-muted-foreground"
      )}>
        {icon}
      </div>
      
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <h3 className="font-medium text-text-primary truncate">{server.name}</h3>
          <StatusBadge status={server.status} />
        </div>
        <p className="text-sm text-text-muted truncate">{server.description}</p>
        {server.toolCount > 0 && (
          <p className="text-xs text-text-muted mt-1">{server.toolCount} tools available</p>
        )}
      </div>

      <div className="flex items-center gap-2">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => onTest(server.id)}
          disabled={!server.enabled || isTestLoading}
          title="Test connection"
        >
          {isTestLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <TestTube className="h-4 w-4" />}
        </Button>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => onDelete(server.id)}
          className="text-destructive hover:text-destructive"
          title="Remove server"
        >
          <Trash2 className="h-4 w-4" />
        </Button>
        <Switch
          checked={server.enabled}
          onCheckedChange={(checked) => onToggle(server.id, checked)}
        />
      </div>
    </div>
  )
}

// Catalog entry card for discovery view
function CatalogEntryCard({
  entry,
  isInstalled,
  onInstall,
  isInstalling,
}: {
  entry: McpCatalogEntry
  isInstalled: boolean
  onInstall: (id: string) => void
  isInstalling: boolean
}) {
  const icon = CATEGORY_ICONS[entry.category] || CATEGORY_ICONS.other

  return (
    <div className="flex items-center gap-4 p-4 rounded-lg border bg-surface-elevated border-interactive-border">
      <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10 text-primary">
        {icon}
      </div>

      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <h3 className="font-medium text-text-primary truncate">{entry.name}</h3>
          <Badge variant="outline" className="text-xs capitalize">{entry.source}</Badge>
        </div>
        <p className="text-sm text-text-muted truncate">{entry.description}</p>
      </div>

      <div className="flex items-center gap-2">
        {entry.documentation_url && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => window.open(entry.documentation_url!, '_blank')}
            title="View documentation"
          >
            <ExternalLink className="h-4 w-4" />
          </Button>
        )}
        <Button
          variant={isInstalled ? "outline" : "default"}
          size="sm"
          onClick={() => onInstall(entry.id)}
          disabled={isInstalled || isInstalling}
        >
          {isInstalling ? (
            <Loader2 className="h-4 w-4 animate-spin mr-1" />
          ) : isInstalled ? (
            <CheckCircle2 className="h-4 w-4 mr-1" />
          ) : (
            <Download className="h-4 w-4 mr-1" />
          )}
          {isInstalled ? 'Installed' : 'Install'}
        </Button>
      </div>
    </div>
  )
}

// Main MCP Manager Module Component
export function McpManagerModule({ instanceId, initialData, onStateChange, className }: ModuleInstanceProps) {
  const [servers, setServers] = useState<McpServerConfig[]>([])
  const [catalog, setCatalog] = useState<McpCatalogEntry[]>([])
  const [searchQuery, setSearchQuery] = useState('')
  const [view, setView] = useState<'installed' | 'discover'>('installed')
  const [isLoading, setIsLoading] = useState(true)
  const [testingServer, setTestingServer] = useState<string | null>(null)
  const [installingEntry, setInstallingEntry] = useState<string | null>(null)

  // Fetch servers on mount
  const fetchServers = useCallback(async () => {
    try {
      const res = await fetch('/api/mcp/servers?status=true')
      const data = await res.json()
      setServers(data.servers || [])
    } catch (error) {
      console.error('Failed to fetch MCP servers:', error)
    }
  }, [])

  // Fetch catalog on mount
  const fetchCatalog = useCallback(async () => {
    try {
      const res = await fetch('/api/mcp/catalog')
      const data = await res.json()
      setCatalog(data.catalog || [])
    } catch (error) {
      console.error('Failed to fetch MCP catalog:', error)
    }
  }, [])

  useEffect(() => {
    Promise.all([fetchServers(), fetchCatalog()]).finally(() => setIsLoading(false))
  }, [fetchServers, fetchCatalog])

  // Toggle server enabled state
  const handleToggle = useCallback(async (id: string, enabled: boolean) => {
    setServers(prev => prev.map(s => s.id === id ? { ...s, enabled } : s))
    try {
      await fetch(`/api/mcp/servers/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled }),
      })
    } catch (error) {
      console.error('Failed to toggle server:', error)
      setServers(prev => prev.map(s => s.id === id ? { ...s, enabled: !enabled } : s))
    }
  }, [])

  // Test server connection
  const handleTest = useCallback(async (id: string) => {
    setTestingServer(id)
    try {
      const res = await fetch(`/api/mcp/servers/${id}/test`, { method: 'POST' })
      const result = await res.json()
      setServers(prev => prev.map(s => s.id === id ? {
        ...s,
        status: result.status,
        error: result.error,
        toolCount: result.tool_count,
        tools: result.tools,
      } : s))
    } catch (error) {
      console.error('Failed to test server:', error)
    } finally {
      setTestingServer(null)
    }
  }, [])

  // Delete server
  const handleDelete = useCallback(async (id: string) => {
    if (!confirm('Remove this MCP server?')) return
    try {
      await fetch(`/api/mcp/servers/${id}`, { method: 'DELETE' })
      setServers(prev => prev.filter(s => s.id !== id))
    } catch (error) {
      console.error('Failed to delete server:', error)
    }
  }, [])

  // Install from catalog
  const handleInstall = useCallback(async (catalogId: string) => {
    setInstallingEntry(catalogId)
    try {
      const res = await fetch('/api/mcp/catalog', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ catalog_id: catalogId }),
      })
      if (res.ok) {
        await fetchServers()
        setView('installed')
      }
    } catch (error) {
      console.error('Failed to install from catalog:', error)
    } finally {
      setInstallingEntry(null)
    }
  }, [fetchServers])

  // Filter items by search
  const filteredServers = servers.filter(s =>
    s.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    s.description.toLowerCase().includes(searchQuery.toLowerCase())
  )

  const filteredCatalog = catalog.filter(e =>
    e.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    e.description.toLowerCase().includes(searchQuery.toLowerCase())
  )

  const installedIds = new Set(servers.map(s => s.id))

  if (isLoading) {
    return <LoadingModuleState message="Loading MCP servers..." />
  }

  return (
    <ModuleContainer className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center gap-3 p-4 border-b border-interactive-border">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-text-muted" />
          <Input
            placeholder="Search MCP servers..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-9"
          />
        </div>
        <div className="flex gap-1 p-1 rounded-lg bg-muted/30">
          <Button
            variant={view === 'installed' ? 'default' : 'ghost'}
            size="sm"
            onClick={() => setView('installed')}
          >
            Installed ({servers.length})
          </Button>
          <Button
            variant={view === 'discover' ? 'default' : 'ghost'}
            size="sm"
            onClick={() => setView('discover')}
          >
            Discover
          </Button>
        </div>
        <Button variant="ghost" size="sm" onClick={() => { fetchServers(); fetchCatalog() }}>
          <RefreshCw className="h-4 w-4" />
        </Button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {view === 'installed' ? (
          filteredServers.length === 0 ? (
            <EmptyModuleState
              icon={Plug}
              title="No MCP Servers"
              description="Install MCP servers from the Discover tab to extend agent capabilities"
              action={<Button onClick={() => setView('discover')}><Plus className="h-4 w-4 mr-1" />Discover Servers</Button>}
            />
          ) : (
            filteredServers.map(server => (
              <McpServerCard
                key={server.id}
                server={server}
                onToggle={handleToggle}
                onTest={handleTest}
                onDelete={handleDelete}
                isTestLoading={testingServer === server.id}
              />
            ))
          )
        ) : (
          filteredCatalog.length === 0 ? (
            <EmptyModuleState
              icon={Search}
              title="No Results"
              description="No MCP servers match your search"
            />
          ) : (
            filteredCatalog.map(entry => (
              <CatalogEntryCard
                key={entry.id}
                entry={entry}
                isInstalled={installedIds.has(entry.id)}
                onInstall={handleInstall}
                isInstalling={installingEntry === entry.id}
              />
            ))
          )
        )}
      </div>
    </ModuleContainer>
  )
}

export default McpManagerModule
