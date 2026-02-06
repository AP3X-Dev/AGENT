"use client"

import { useState, useEffect, useCallback, useMemo } from 'react'
import { Wrench, Search, Grid3x3, List, ChevronRight, Terminal, Globe, Brain, FolderOpen, Server, Settings, Copy, Check, Filter, X } from 'lucide-react'
import { cn } from '@/lib/utils'
import { ModuleContainer, EmptyModuleState, LoadingModuleState, ErrorModuleState } from './module-container'
import { useAgentConnection } from '@/hooks/use-agent-connection'
import type { ModuleConfig, ModuleInstanceProps } from '@/types/modules'
import type { Tool, ToolCategory, ToolSource, ToolStatus, ToolsListResponse } from '@/types/tools'

export const toolsLibraryModuleConfig: ModuleConfig = {
  metadata: { id: 'tools-library', displayName: 'Tools Library', description: 'Browse, search, and manage available agent tools and MCP integrations', icon: 'Wrench', category: 'data', version: '1.0.0' },
  hasHeader: true,
  initialState: { isLoading: false, error: null, data: { tools: [], selectedTool: null, mcpServers: [] } },
  agentConfig: { enabled: true, supportedCommands: ['search', 'getTool', 'activateTool', 'listByCategory'], emittedEvents: ['tool-selected', 'tool-activated', 'search-performed'], contextDescription: 'Tools library for browsing and managing agent tools and MCP integrations' },
}

const getCategoryIcon = (category: ToolCategory) => {
  switch (category) { case 'filesystem': return FolderOpen; case 'web': return Globe; case 'ai': return Brain; case 'browser': return Globe; case 'shell': return Terminal; case 'utility': return Settings; case 'mcp': return Server; case 'data': return FolderOpen; case 'communication': return Globe; case 'general': return Wrench; default: return Wrench }
}
const getCategoryColor = (category: ToolCategory) => {
  switch (category) { case 'filesystem': return 'text-amber-500'; case 'web': return 'text-blue-500'; case 'ai': return 'text-purple-500'; case 'browser': return 'text-cyan-500'; case 'shell': return 'text-green-500'; case 'utility': return 'text-gray-500'; case 'mcp': return 'text-orange-500'; case 'data': return 'text-teal-500'; case 'communication': return 'text-pink-500'; case 'general': return 'text-slate-500'; default: return 'text-text-muted' }
}
const getStatusBadge = (status: ToolStatus) => {
  switch (status) { case 'active': return { label: 'Active', className: 'bg-[#1a2f1a] border border-[#2a4a2a] text-emerald-400' }; case 'deferred': return { label: 'Deferred', className: 'bg-[#2a2a1a] border border-[#3a3a2a] text-amber-400' }; case 'disabled': return { label: 'Disabled', className: 'bg-[#1E1E1E] border border-[#2a2a2a] text-text-muted' }; case 'error': return { label: 'Error', className: 'bg-[#2f1a1a] border border-[#4a2a2a] text-red-400' }; default: return { label: 'Unknown', className: 'bg-[#1E1E1E] border border-[#2a2a2a] text-text-muted' } }
}
const getSourceBadge = (source: ToolSource) => {
  switch (source) { case 'builtin': return { label: 'Built-in', className: 'bg-[#1a1a2a] border border-[#2a2a3a] text-blue-400' }; case 'mcp': return { label: 'MCP', className: 'bg-[#2a1f1a] border border-[#3a2f2a] text-orange-400' }; case 'plugin': return { label: 'Plugin', className: 'bg-[#2a1a2a] border border-[#3a2a3a] text-purple-400' }; case 'custom': return { label: 'Custom', className: 'bg-[#1a2a1a] border border-[#2a3a2a] text-emerald-400' }; default: return { label: 'Unknown', className: 'bg-[#1E1E1E] border border-[#2a2a2a] text-text-muted' } }
}

const CATEGORIES: { value: ToolCategory | 'all'; label: string }[] = [{ value: 'all', label: 'All Categories' }, { value: 'filesystem', label: 'Filesystem' }, { value: 'web', label: 'Web' }, { value: 'ai', label: 'AI' }, { value: 'browser', label: 'Browser' }, { value: 'shell', label: 'Shell' }, { value: 'utility', label: 'Utility' }, { value: 'mcp', label: 'MCP' }]
const SOURCES: { value: ToolSource | 'all'; label: string }[] = [{ value: 'all', label: 'All Sources' }, { value: 'builtin', label: 'Built-in' }, { value: 'mcp', label: 'MCP' }, { value: 'plugin', label: 'Plugin' }, { value: 'custom', label: 'Custom' }]
const CATEGORY_ORDER: ToolCategory[] = ['browser', 'filesystem', 'web', 'shell', 'ai', 'utility', 'data', 'communication', 'mcp', 'general']
const CATEGORY_LABELS: Record<ToolCategory, string> = { filesystem: 'Filesystem', web: 'Web & HTTP', ai: 'AI & Research', browser: 'Browser Automation', shell: 'Shell & Terminal', utility: 'Utilities', mcp: 'MCP Tools', data: 'Data & Storage', communication: 'Communication', general: 'General' }

interface ToolCardProps { tool: Tool; isSelected: boolean; viewMode: 'list' | 'grid'; onSelect: (tool: Tool) => void }

function ToolCard({ tool, isSelected, viewMode, onSelect }: ToolCardProps) {
  const CategoryIcon = getCategoryIcon(tool.metadata.category)
  const statusBadge = getStatusBadge(tool.status)
  const sourceBadge = getSourceBadge(tool.source)
  if (viewMode === 'grid') {
    return (<button onClick={() => onSelect(tool)} className={cn("flex flex-col p-4 rounded-lg border text-left transition-all hover:bg-surface-elevated hover:border-border-active", isSelected ? "bg-surface-elevated border-status-info ring-1 ring-status-info/30" : "bg-surface border-border")}>
      <div className="flex items-start justify-between mb-2"><div className={cn("p-2 rounded-md bg-surface-elevated", getCategoryColor(tool.metadata.category))}><CategoryIcon className="h-4 w-4" /></div><span className={cn("text-xs px-2 py-0.5 rounded-full", statusBadge.className)}>{statusBadge.label}</span></div>
      <h3 className="font-medium text-text-primary text-sm mb-1 truncate">{tool.name}</h3><p className="text-xs text-text-muted line-clamp-2 mb-2">{tool.description}</p>
      <div className="flex items-center gap-2 mt-auto"><span className={cn("text-xs px-1.5 py-0.5 rounded", sourceBadge.className)}>{sourceBadge.label}</span>{tool.mcpServer && <span className="text-xs text-text-muted">{tool.mcpServer}</span>}</div>
    </button>)
  }
  return (<button onClick={() => onSelect(tool)} className={cn("flex items-center gap-3 p-3 rounded-lg border text-left transition-all w-full hover:bg-surface-elevated hover:border-border-active", isSelected ? "bg-surface-elevated border-status-info ring-1 ring-status-info/30" : "bg-surface border-border")}>
    <div className={cn("p-2 rounded-md bg-surface-elevated shrink-0", getCategoryColor(tool.metadata.category))}><CategoryIcon className="h-4 w-4" /></div>
    <div className="flex-1 min-w-0"><div className="flex items-center gap-2"><h3 className="font-medium text-text-primary text-sm truncate">{tool.name}</h3><span className={cn("text-xs px-1.5 py-0.5 rounded shrink-0", sourceBadge.className)}>{sourceBadge.label}</span></div><p className="text-xs text-text-muted truncate">{tool.description}</p></div>
    <span className={cn("text-xs px-2 py-0.5 rounded-full shrink-0", statusBadge.className)}>{statusBadge.label}</span><ChevronRight className="h-4 w-4 text-text-muted shrink-0" />
  </button>)
}

interface ToolDetailPanelProps { tool: Tool; onClose: () => void }

function ToolDetailPanel({ tool, onClose }: ToolDetailPanelProps) {
  const [copiedParam, setCopiedParam] = useState<string | null>(null)
  const CategoryIcon = getCategoryIcon(tool.metadata.category)
  const statusBadge = getStatusBadge(tool.status)
  const sourceBadge = getSourceBadge(tool.source)
  const copyToClipboard = (text: string, paramName: string) => { navigator.clipboard.writeText(text); setCopiedParam(paramName); setTimeout(() => setCopiedParam(null), 2000) }
  return (
    <div className="flex flex-col h-full bg-surface border-l border-border">
      <div className="flex items-center justify-between p-4 border-b border-border">
        <div className="flex items-center gap-3"><div className={cn("p-2 rounded-md bg-surface-elevated", getCategoryColor(tool.metadata.category))}><CategoryIcon className="h-5 w-5" /></div><div><h2 className="font-semibold text-text-primary">{tool.name}</h2><div className="flex items-center gap-2 mt-1"><span className={cn("text-xs px-1.5 py-0.5 rounded", sourceBadge.className)}>{sourceBadge.label}</span><span className={cn("text-xs px-1.5 py-0.5 rounded", statusBadge.className)}>{statusBadge.label}</span></div></div></div>
        <button onClick={onClose} className="p-1.5 rounded-md hover:bg-surface-elevated text-text-muted hover:text-text-primary transition-colors"><X className="h-4 w-4" /></button>
      </div>
      <div className="flex-1 overflow-y-auto p-4 space-y-6">
        <div><h3 className="text-sm font-medium text-text-secondary mb-2">Description</h3><p className="text-sm text-text-muted">{tool.description}</p></div>
        {tool.mcpServer && <div><h3 className="text-sm font-medium text-text-secondary mb-2">MCP Server</h3><div className="flex items-center gap-2 p-2 rounded-md bg-surface-elevated"><Server className="h-4 w-4 text-orange-500" /><span className="text-sm text-text-primary">{tool.mcpServer}</span></div></div>}
        {tool.parameters.length > 0 && <div><h3 className="text-sm font-medium text-text-secondary mb-2">Parameters ({tool.parameters.length})</h3><div className="space-y-2">{tool.parameters.map((param) => (<div key={param.name} className="p-3 rounded-md bg-surface-elevated border border-border"><div className="flex items-center justify-between mb-1"><div className="flex items-center gap-2"><code className="text-sm font-mono text-status-info">{param.name}</code><span className="text-xs text-text-muted">({param.type})</span>{param.required && <span className="text-xs px-1.5 py-0.5 rounded bg-[#2f1a1a] border border-[#4a2a2a] text-red-400">required</span>}</div><button onClick={() => copyToClipboard(param.name, param.name)} className="p-1 rounded hover:bg-interactive-hover text-text-muted hover:text-text-primary transition-colors">{copiedParam === param.name ? <Check className="h-3 w-3 text-green-500" /> : <Copy className="h-3 w-3" />}</button></div><p className="text-xs text-text-muted">{param.description}</p>{param.default !== undefined && <p className="text-xs text-text-muted mt-1">Default: <code className="text-text-secondary">{JSON.stringify(param.default)}</code></p>}</div>))}</div></div>}
        <div><h3 className="text-sm font-medium text-text-secondary mb-2">Metadata</h3><div className="grid grid-cols-2 gap-2"><div className="p-2 rounded-md bg-surface-elevated"><span className="text-xs text-text-muted">Category</span><p className="text-sm text-text-primary capitalize">{tool.metadata.category}</p></div><div className="p-2 rounded-md bg-surface-elevated"><span className="text-xs text-text-muted">Cost</span><p className="text-sm text-text-primary capitalize">{tool.metadata.cost}</p></div><div className="p-2 rounded-md bg-surface-elevated"><span className="text-xs text-text-muted">Requires Approval</span><p className="text-sm text-text-primary">{tool.metadata.requiresApproval ? 'Yes' : 'No'}</p></div><div className="p-2 rounded-md bg-surface-elevated"><span className="text-xs text-text-muted">Cacheable</span><p className="text-sm text-text-primary">{tool.metadata.cacheable ? 'Yes' : 'No'}</p></div></div></div>
        {tool.metadata.tags.length > 0 && <div><h3 className="text-sm font-medium text-text-secondary mb-2">Tags</h3><div className="flex flex-wrap gap-1">{tool.metadata.tags.map((tag) => (<span key={tag} className="text-xs px-2 py-1 rounded-full bg-surface-elevated text-text-muted">{tag}</span>))}</div></div>}
      </div>
    </div>
  )
}

export function ToolsLibraryModule({ instanceId, tabId, initialData, onStateChange, onTabUpdate, agentEnabled, moduleType }: ModuleInstanceProps) {
  const [tools, setTools] = useState<Tool[]>([])
  const [selectedTool, setSelectedTool] = useState<Tool | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [categoryFilter, setCategoryFilter] = useState<ToolCategory | 'all'>('all')
  const [sourceFilter, setSourceFilter] = useState<ToolSource | 'all'>('all')
  const [viewMode, setViewMode] = useState<'list' | 'grid'>('list')
  const [showFilters, setShowFilters] = useState(false)

  const { updateContext, sendEvent, onCommand } = useAgentConnection({ instanceId, moduleType: 'tools-library' })

  const fetchTools = useCallback(async () => {
    setIsLoading(true); setError(null)
    try {
      const params = new URLSearchParams()
      if (searchQuery) params.set('search', searchQuery)
      if (categoryFilter !== 'all') params.set('category', categoryFilter)
      if (sourceFilter !== 'all') params.set('source', sourceFilter)
      const response = await fetch(`/api/tools?${params.toString()}`)
      if (!response.ok) throw new Error('Failed to fetch tools')
      const data: ToolsListResponse = await response.json()
      setTools(data.tools)
    } catch (err) { setError(err instanceof Error ? err.message : 'Failed to load tools') } finally { setIsLoading(false) }
  }, [searchQuery, categoryFilter, sourceFilter])

  useEffect(() => { fetchTools() }, [fetchTools])
  useEffect(() => { updateContext({ toolCount: tools.length, selectedTool: selectedTool?.name || null, filters: { search: searchQuery, category: categoryFilter, source: sourceFilter } }) }, [tools, selectedTool, searchQuery, categoryFilter, sourceFilter, updateContext])

  useEffect(() => {
    const sub1 = onCommand('search', async (params: { query?: string }) => {
      if (typeof params?.query === 'string') { setSearchQuery(params.query); sendEvent('search-performed', { query: params.query }) }
    })
    const sub2 = onCommand('getTool', async (params: { name?: string }) => {
      if (typeof params?.name === 'string') { const tool = tools.find(t => t.name === params.name); if (tool) { setSelectedTool(tool); sendEvent('tool-selected', { tool: tool.name }) } }
    })
    const sub3 = onCommand('listByCategory', async (params: { category?: string }) => {
      if (typeof params?.category === 'string') { setCategoryFilter(params.category as ToolCategory) }
    })
    return () => { sub1.unsubscribe(); sub2.unsubscribe(); sub3.unsubscribe() }
  }, [onCommand, sendEvent, tools])

  const filteredTools = useMemo(() => tools.filter(tool => { if (searchQuery && !tool.name.toLowerCase().includes(searchQuery.toLowerCase()) && !tool.description.toLowerCase().includes(searchQuery.toLowerCase())) return false; if (categoryFilter !== 'all' && tool.metadata.category !== categoryFilter) return false; if (sourceFilter !== 'all' && tool.source !== sourceFilter) return false; return true }), [tools, searchQuery, categoryFilter, sourceFilter])

  const builtinToolsByCategory = useMemo(() => {
    const builtinTools = filteredTools.filter(t => t.source === 'builtin')
    const grouped: Record<ToolCategory, Tool[]> = { filesystem: [], web: [], ai: [], browser: [], shell: [], utility: [], mcp: [], data: [], communication: [], general: [] }
    builtinTools.forEach(tool => { const cat = tool.metadata.category; if (grouped[cat]) grouped[cat].push(tool) })
    return CATEGORY_ORDER.map(cat => ({ category: cat, label: CATEGORY_LABELS[cat], tools: grouped[cat], icon: getCategoryIcon(cat), color: getCategoryColor(cat) })).filter(g => g.tools.length > 0)
  }, [filteredTools])

  const mcpToolsByServer = useMemo(() => {
    const mcpTools = filteredTools.filter(t => t.source === 'mcp')
    const grouped: Record<string, Tool[]> = {}
    mcpTools.forEach(tool => {
      const server = tool.mcpServer || 'Unknown'
      if (!grouped[server]) grouped[server] = []
      grouped[server].push(tool)
    })
    return Object.entries(grouped).map(([server, tools]) => ({ server, label: server.replace(/_/g, ' '), tools, icon: Server, color: 'text-orange-500' }))
  }, [filteredTools])

  const handleSelectTool = (tool: Tool) => { setSelectedTool(tool); sendEvent('tool-selected', { tool: tool.name }) }

  if (isLoading) return <LoadingModuleState message="Loading tools..." />
  if (error) return <ErrorModuleState error={error} onRetry={fetchTools} />

  return (
    <ModuleContainer className="flex flex-col h-full">
      <div className="flex items-center gap-2 p-3 border-b border-border">
        <div className="relative flex-1"><Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-text-muted" /><input type="text" placeholder="Search tools..." value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)} className="w-full pl-9 pr-3 py-2 text-sm bg-surface-elevated border border-border rounded-md focus:outline-none focus:ring-1 focus:ring-status-info text-text-primary placeholder:text-text-muted" /></div>
        <button onClick={() => setShowFilters(!showFilters)} className={cn("p-2 rounded-md border transition-colors", showFilters ? "bg-[#1a1a2a] border-[#3a3a4a] text-blue-400" : "bg-surface-elevated border-border text-text-muted hover:text-text-primary")}><Filter className="h-4 w-4" /></button>
        <div className="flex items-center border border-border rounded-md overflow-hidden"><button onClick={() => setViewMode('list')} className={cn("p-2 transition-colors", viewMode === 'list' ? "bg-[#1a1a2a] text-blue-400" : "bg-surface-elevated text-text-muted hover:text-text-primary")}><List className="h-4 w-4" /></button><button onClick={() => setViewMode('grid')} className={cn("p-2 transition-colors", viewMode === 'grid' ? "bg-[#1a1a2a] text-blue-400" : "bg-surface-elevated text-text-muted hover:text-text-primary")}><Grid3x3 className="h-4 w-4" /></button></div>
      </div>
      {showFilters && <div className="flex items-center gap-2 p-3 border-b border-border bg-surface-elevated"><select value={categoryFilter} onChange={(e) => setCategoryFilter(e.target.value as ToolCategory | 'all')} className="px-3 py-1.5 text-sm bg-surface border border-border rounded-md text-text-primary focus:outline-none focus:ring-1 focus:ring-status-info">{CATEGORIES.map(c => <option key={c.value} value={c.value}>{c.label}</option>)}</select><select value={sourceFilter} onChange={(e) => setSourceFilter(e.target.value as ToolSource | 'all')} className="px-3 py-1.5 text-sm bg-surface border border-border rounded-md text-text-primary focus:outline-none focus:ring-1 focus:ring-status-info">{SOURCES.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}</select><span className="text-xs text-text-muted ml-auto">{filteredTools.length} tools</span></div>}
      <div className="flex flex-1 overflow-hidden">
        <div className="flex-1 overflow-y-auto p-3 pb-8">
          {filteredTools.length === 0 ? <EmptyModuleState icon={Wrench} title="No tools found" description={searchQuery ? "Try adjusting your search or filters" : "No tools available"} /> : (
            <div className="space-y-6">
              {mcpToolsByServer.length > 0 && (
                <div className="space-y-4">
                  <h2 className="text-sm font-semibold text-text-primary uppercase tracking-wider flex items-center gap-2 pb-2 border-b border-border">
                    <Server className="h-4 w-4 text-orange-500" />MCP Tools ({mcpToolsByServer.reduce((sum, g) => sum + g.tools.length, 0)})
                  </h2>
                  {mcpToolsByServer.map(group => {
                    const GroupIcon = group.icon
                    return (
                      <div key={group.server}>
                        <h3 className={cn("text-xs font-medium uppercase tracking-wider mb-2 flex items-center gap-2", group.color)}>
                          <GroupIcon className="h-3 w-3" />{group.label} ({group.tools.length})
                        </h3>
                        <div className={viewMode === 'grid' ? "grid grid-cols-3 gap-2" : "space-y-2"}>
                          {group.tools.map(tool => <ToolCard key={tool.name} tool={tool} isSelected={selectedTool?.name === tool.name} viewMode={viewMode} onSelect={handleSelectTool} />)}
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
              {builtinToolsByCategory.length > 0 && (
                <div className="space-y-4">
                  <h2 className="text-sm font-semibold text-text-primary uppercase tracking-wider flex items-center gap-2 pb-2 border-b border-border">
                    <Wrench className="h-4 w-4 text-blue-500" />Built-in Tools ({builtinToolsByCategory.reduce((sum, g) => sum + g.tools.length, 0)})
                  </h2>
                  {builtinToolsByCategory.map(group => {
                    const GroupIcon = group.icon
                    return (
                      <div key={group.category}>
                        <h3 className={cn("text-xs font-medium uppercase tracking-wider mb-2 flex items-center gap-2", group.color)}>
                          <GroupIcon className="h-3 w-3" />{group.label} ({group.tools.length})
                        </h3>
                        <div className={viewMode === 'grid' ? "grid grid-cols-3 gap-2" : "space-y-2"}>
                          {group.tools.map(tool => <ToolCard key={tool.name} tool={tool} isSelected={selectedTool?.name === tool.name} viewMode={viewMode} onSelect={handleSelectTool} />)}
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          )}
        </div>
        {selectedTool && <div className="w-80 shrink-0"><ToolDetailPanel tool={selectedTool} onClose={() => setSelectedTool(null)} /></div>}
      </div>
    </ModuleContainer>
  )
}

export default ToolsLibraryModule

