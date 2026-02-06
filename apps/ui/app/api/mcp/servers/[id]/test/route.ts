import { NextRequest, NextResponse } from 'next/server'
import type { McpServerTestResponse } from '@/types/mcp'
import { getDeepAgentsDaemonClient } from '@/lib/deepagents/daemon-client'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

interface RouteParams {
  params: Promise<{ id: string }>
}

/**
 * POST /api/mcp/servers/:id/test
 * Tests connectivity to an MCP server by asking the AG3NT daemon to connect and enumerate tools.
 */
export async function POST(_request: NextRequest, { params }: RouteParams) {
  const { id } = await params
  try {
    const client = getDeepAgentsDaemonClient()
    const result = await client.request<McpServerTestResponse>('mcp_test_server', { server_id: id })
    return NextResponse.json(result)
  } catch (error: any) {
    console.error('Error testing MCP server:', error)
    return NextResponse.json(
      {
        status: 'error',
        error: error.message || 'Failed to test connection',
        tool_count: 0,
        tools: [],
      } as McpServerTestResponse,
      { status: 500 }
    )
  }
}

