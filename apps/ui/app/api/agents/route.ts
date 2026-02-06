import { NextRequest, NextResponse } from 'next/server'
import { getDeepAgentsDaemonClient } from '@/lib/deepagents/daemon-client'
import type { Agent, AgentsListResponse, AgentCategory, AgentMode, AgentStatus } from '@/types/agents'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

function normalizeBaseUrl(url: string): string {
  return url.replace(/\/+$/, '')
}

function inferCategory(name: string): AgentCategory {
  const n = name.toLowerCase()
  if (n.includes('coder') || n.includes('code') || n.includes('dev')) return 'coding'
  if (n.includes('research')) return 'research'
  if (n.includes('data') || n.includes('analyst')) return 'data'
  if (n.includes('creative') || n.includes('writer')) return 'creative'
  if (n.includes('auto') || n.includes('ops')) return 'automation'
  if (n.includes('debug') || n.includes('analysis')) return 'analysis'
  return 'general'
}

async function fetchAgentsFromGateway(): Promise<Agent[] | null> {
  const gatewayBase = normalizeBaseUrl(
    process.env.AG3NT_GATEWAY_URL ||
      process.env.NEXT_PUBLIC_AG3NT_GATEWAY_URL ||
      'http://127.0.0.1:18789'
  )

  const modelConfig = await fetch(`${gatewayBase}/api/model/config`, {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' },
    cache: 'no-store',
  })
    .then((r) => (r.ok ? r.json() : null))
    .catch(() => null)

  const provider = modelConfig?.provider || 'auto'
  const model = modelConfig?.model || 'default'

  const subagentsRes = await fetch(`${gatewayBase}/api/subagents`, {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' },
    cache: 'no-store',
  })

  if (!subagentsRes.ok) return null
  const subagentsData = await subagentsRes.json().catch(() => null)
  const subagents = (subagentsData?.subagents || subagentsData?.data?.subagents) as any[] | undefined
  if (!Array.isArray(subagents)) return null

  const mainAgent: Agent = {
    name: 'ag3nt',
    description: 'AG3NT main agent (managed by Gateway + DeepAgents)',
    mode: 'main',
    status: 'active',
    systemPrompt: '',
    model: { provider, model, temperature: 0.0 },
    permissions: {},
    enabledTools: [],
    disabledTools: [],
    middleware: [],
    metadata: { category: 'general', tags: ['main', 'gateway'] },
  }

  const detailPromises = subagents.map(async (sa) => {
    const name = String(sa?.name || '').trim()
    if (!name) return null

    const detail = await fetch(`${gatewayBase}/api/subagents/${encodeURIComponent(name)}`, {
      method: 'GET',
      headers: { 'Content-Type': 'application/json' },
      cache: 'no-store',
    })
      .then((r) => (r.ok ? r.json() : null))
      .catch(() => null)

    const description = String(detail?.description || sa?.description || '').trim()
    const tools = Array.isArray(detail?.tools) ? detail.tools : Array.isArray(sa?.tools) ? sa.tools : []
    const source = String(detail?.source || sa?.source || 'unknown')

    const agent: Agent = {
      name,
      description,
      mode: 'subagent',
      status: 'active',
      systemPrompt: String(detail?.system_prompt || ''),
      model: {
        provider,
        model: String(detail?.model_override || model),
        temperature: 0.0,
      },
      permissions: {},
      enabledTools: tools.map((t: any) => String(t)),
      disabledTools: [],
      middleware: [],
      metadata: {
        category: inferCategory(name),
        tags: ['subagent', `source:${source}`],
      },
    }

    return agent
  })

  const subagentAgents = (await Promise.all(detailPromises)).filter((a): a is Agent => Boolean(a))

  return [mainAgent, ...subagentAgents]
}

/**
 * GET /api/agents
 * Lists all available agents with filtering and pagination.
 *
 * Primary source: AG3NT Gateway subagent registry (http://127.0.0.1:18789).
 * Fallback: AG3NT DeepAgents daemon JSON-RPC (list_agents).
 */
export async function GET(request: NextRequest) {
  try {
    const searchParams = request.nextUrl.searchParams
    const searchQuery = searchParams.get('search')?.toLowerCase()
    const modeFilter = searchParams.get('mode')
    const categoryFilter = searchParams.get('category')
    const statusFilter = searchParams.get('status')
    const limit = parseInt(searchParams.get('limit') || '50', 10)
    const offset = parseInt(searchParams.get('offset') || '0', 10)

    let agents: Agent[] | null = null

    // Try Gateway first (matches AG3NT dashboard/control panel).
    try {
      agents = await fetchAgentsFromGateway()
    } catch {
      agents = null
    }

    // Fallback to daemon (stdio JSON-RPC).
    if (!agents) {
      const client = getDeepAgentsDaemonClient()
      const result = await client.request<{ agents?: Agent[] }>('list_agents', {})
      agents = Array.isArray(result?.agents) ? result.agents : []
    }

    // Apply filters
    if (searchQuery) {
      agents = agents.filter((agent) => {
        const searchText = [
          agent.name,
          agent.description,
          agent.mode,
          ...(agent.metadata?.tags || []),
          ...(agent.enabledTools || []),
        ]
          .join(' ')
          .toLowerCase()
        return searchText.includes(searchQuery)
      })
    }

    if (modeFilter && modeFilter !== 'all') {
      agents = agents.filter((agent) => agent.mode === (modeFilter as AgentMode))
    }

    if (categoryFilter && categoryFilter !== 'all') {
      agents = agents.filter((agent) => agent.metadata?.category === (categoryFilter as AgentCategory))
    }

    if (statusFilter && statusFilter !== 'all') {
      agents = agents.filter((agent) => agent.status === (statusFilter as AgentStatus))
    }

    // Sort by name
    agents.sort((a, b) => a.name.localeCompare(b.name))

    const total = agents.length
    const paginatedAgents = agents.slice(offset, offset + limit)

    const response: AgentsListResponse = {
      agents: paginatedAgents,
      total,
      limit,
      offset,
      hasMore: offset + limit < total,
    }

    return NextResponse.json(response)
  } catch (error: any) {
    console.error('Error listing agents:', error)
    return NextResponse.json({ error: error.message || 'Failed to list agents' }, { status: 500 })
  }
}

