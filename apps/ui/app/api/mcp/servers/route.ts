import { NextRequest, NextResponse } from 'next/server'
import type { McpServerResponse, McpServersListResponse } from '@/types/mcp'
import { loadAg3ntMcpConfig, saveAg3ntMcpConfig, toMcpServerConfig } from '@/lib/mcp/config'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * GET /api/mcp/servers
 * List configured MCP servers from AG3NT config (~/.ag3nt/mcp_servers.json).
 */
export async function GET(_request: NextRequest) {
  try {
    const config = await loadAg3ntMcpConfig()
    const servers = Object.entries(config.mcpServers)
      .map(([id, entry]) => toMcpServerConfig(id, entry))
      .sort((a, b) => a.name.localeCompare(b.name))

    const data: McpServersListResponse = { servers }
    return NextResponse.json(data)
  } catch (error: any) {
    console.error('Error listing MCP servers:', error)
    return NextResponse.json({ error: error.message || 'Failed to list MCP servers' }, { status: 500 })
  }
}

/**
 * POST /api/mcp/servers
 * Add a new MCP server entry.
 */
export async function POST(request: NextRequest) {
  try {
    const body = await request.json().catch(() => ({}))
    const id = String(body.id || '').trim()
    if (!id) {
      return NextResponse.json({ error: 'id is required' }, { status: 400 })
    }

    const config = await loadAg3ntMcpConfig()
    config.mcpServers[id] = {
      command: typeof body.command === 'string' ? body.command : undefined,
      args: Array.isArray(body.args) ? body.args.map(String) : undefined,
      env: body.env && typeof body.env === 'object' ? body.env : undefined,
      url: typeof body.url === 'string' ? body.url : undefined,
      headers: body.headers && typeof body.headers === 'object' ? body.headers : undefined,
      enabled: body.enabled !== false,
      name: typeof body.name === 'string' ? body.name : undefined,
      description: typeof body.description === 'string' ? body.description : undefined,
      category: typeof body.category === 'string' ? body.category : undefined,
      icon: typeof body.icon === 'string' ? body.icon : undefined,
      installedAt: new Date().toISOString(),
    }

    await saveAg3ntMcpConfig(config)

    const server = toMcpServerConfig(id, config.mcpServers[id])
    const data: McpServerResponse = { server }
    return NextResponse.json(data, { status: 201 })
  } catch (error: any) {
    console.error('Error adding MCP server:', error)
    return NextResponse.json({ error: error.message || 'Failed to add MCP server' }, { status: 500 })
  }
}

