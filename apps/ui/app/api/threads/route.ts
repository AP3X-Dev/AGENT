import { NextRequest, NextResponse } from 'next/server'
import { getDeepAgentsDaemonClient } from '@/lib/deepagents/daemon-client'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * GET /api/threads
 * List all threads with optional filtering
 */
export async function GET(request: NextRequest) {
  try {
    const searchParams = request.nextUrl.searchParams
    const agentName = searchParams.get('agent') || undefined
    const limit = parseInt(searchParams.get('limit') || '50', 10)

    const client = getDeepAgentsDaemonClient()
    const result = await client.listThreads(agentName, limit)

    return NextResponse.json(result)
  } catch (error: any) {
    console.error('[threads] List error:', error)
    return NextResponse.json(
      { error: error.message || 'Failed to list threads' },
      { status: 500 }
    )
  }
}

/**
 * DELETE /api/threads?id=thread_id
 * Delete a specific thread
 */
export async function DELETE(request: NextRequest) {
  try {
    const searchParams = request.nextUrl.searchParams
    const threadId = searchParams.get('id')

    if (!threadId) {
      return NextResponse.json(
        { error: 'Thread ID is required' },
        { status: 400 }
      )
    }

    const client = getDeepAgentsDaemonClient()
    const result = await client.deleteThread(threadId)

    return NextResponse.json(result)
  } catch (error: any) {
    console.error('[threads] Delete error:', error)
    return NextResponse.json(
      { error: error.message || 'Failed to delete thread' },
      { status: 500 }
    )
  }
}

