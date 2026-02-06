import { NextRequest, NextResponse } from 'next/server'
import { getDeepAgentsDaemonClient } from '@/lib/deepagents/daemon-client'
import type { Tool, ToolsListResponse } from '@/types/tools'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * GET /api/tools
 * Lists tools from the running AG3NT DeepAgents daemon.
 */
export async function GET(request: NextRequest) {
  try {
    const searchParams = request.nextUrl.searchParams
    const searchQuery = searchParams.get('search')?.toLowerCase()
    const categoryFilter = searchParams.get('category')
    const sourceFilter = searchParams.get('source')
    const statusFilter = searchParams.get('status')
    const limit = parseInt(searchParams.get('limit') || '50', 10)
    const offset = parseInt(searchParams.get('offset') || '0', 10)

    const model = searchParams.get('model') || undefined

    const client = getDeepAgentsDaemonClient()
    const result = await client.request<{
      tools?: Tool[]
      mcp_servers?: any[]
      mcpServers?: any[]
    }>('list_tools', { model })

    let tools = Array.isArray(result?.tools) ? [...result.tools] : []

    // Apply filters
    if (searchQuery) {
      tools = tools.filter((tool) => {
        const searchText = [
          tool.name,
          tool.description,
          ...(tool.metadata?.tags || []),
          ...(tool.parameters || []).map((p) => p.name),
        ]
          .join(' ')
          .toLowerCase()
        return searchText.includes(searchQuery)
      })
    }

    if (categoryFilter && categoryFilter !== 'all') {
      tools = tools.filter((tool) => tool.metadata?.category === categoryFilter)
    }

    if (sourceFilter && sourceFilter !== 'all') {
      tools = tools.filter((tool) => tool.source === sourceFilter)
    }

    if (statusFilter && statusFilter !== 'all') {
      tools = tools.filter((tool) => tool.status === statusFilter)
    }

    // Sort by name
    tools.sort((a, b) => a.name.localeCompare(b.name))

    const total = tools.length
    const paginatedTools = tools.slice(offset, offset + limit)

    const response: ToolsListResponse = {
      tools: paginatedTools,
      total,
      limit,
      offset,
      hasMore: offset + limit < total,
      mcpServers: Array.isArray(result?.mcpServers)
        ? result.mcpServers
        : Array.isArray(result?.mcp_servers)
          ? result.mcp_servers
          : [],
    }

    return NextResponse.json(response)
  } catch (error: any) {
    console.error('Error listing tools:', error)
    return NextResponse.json({ error: error.message || 'Failed to list tools' }, { status: 500 })
  }
}

