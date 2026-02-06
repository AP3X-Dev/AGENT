import { NextRequest, NextResponse } from 'next/server'
import type { McpServerResponse } from '@/types/mcp'
import { loadAg3ntMcpConfig, saveAg3ntMcpConfig, toMcpServerConfig } from '@/lib/mcp/config'

interface RouteParams {
  params: Promise<{ id: string }>
}

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * GET /api/mcp/servers/:id
 * Get a specific MCP server config.
 */
export async function GET(_request: NextRequest, { params }: RouteParams) {
  const { id } = await params
  try {
    const config = await loadAg3ntMcpConfig()
    const entry = config.mcpServers[id]
    if (!entry) return NextResponse.json({ error: 'Server not found' }, { status: 404 })

    const data: McpServerResponse = { server: toMcpServerConfig(id, entry) }
    return NextResponse.json(data)
  } catch (error: any) {
    console.error('Error fetching MCP server:', error)
    return NextResponse.json({ error: error.message || 'Failed to fetch MCP server' }, { status: 500 })
  }
}

/**
 * PATCH /api/mcp/servers/:id
 * Update a server entry.
 */
export async function PATCH(request: NextRequest, { params }: RouteParams) {
  const { id } = await params
  try {
    const body = await request.json().catch(() => ({}))
    const config = await loadAg3ntMcpConfig()
    const existing = config.mcpServers[id]
    if (!existing) return NextResponse.json({ error: 'Server not found' }, { status: 404 })

    config.mcpServers[id] = {
      ...existing,
      ...(typeof body.enabled === 'boolean' ? { enabled: body.enabled } : {}),
      ...(typeof body.name === 'string' ? { name: body.name } : {}),
      ...(typeof body.description === 'string' ? { description: body.description } : {}),
      ...(typeof body.command === 'string' ? { command: body.command } : {}),
      ...(Array.isArray(body.args) ? { args: body.args.map(String) } : {}),
      ...(body.env && typeof body.env === 'object' ? { env: body.env } : {}),
      ...(typeof body.url === 'string' ? { url: body.url } : {}),
      ...(body.headers && typeof body.headers === 'object' ? { headers: body.headers } : {}),
      ...(typeof body.category === 'string' ? { category: body.category } : {}),
      ...(typeof body.icon === 'string' ? { icon: body.icon } : {}),
    }

    await saveAg3ntMcpConfig(config)

    const data: McpServerResponse = { server: toMcpServerConfig(id, config.mcpServers[id]) }
    return NextResponse.json(data)
  } catch (error: any) {
    console.error('Error updating MCP server:', error)
    return NextResponse.json({ error: error.message || 'Failed to update MCP server' }, { status: 500 })
  }
}

/**
 * DELETE /api/mcp/servers/:id
 * Remove a server entry.
 */
export async function DELETE(_request: NextRequest, { params }: RouteParams) {
  const { id } = await params
  try {
    const config = await loadAg3ntMcpConfig()
    if (!config.mcpServers[id]) return NextResponse.json({ error: 'Server not found' }, { status: 404 })
    delete config.mcpServers[id]
    await saveAg3ntMcpConfig(config)
    return NextResponse.json({ ok: true })
  } catch (error: any) {
    console.error('Error deleting MCP server:', error)
    return NextResponse.json({ error: error.message || 'Failed to delete MCP server' }, { status: 500 })
  }
}

