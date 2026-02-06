import { NextRequest, NextResponse } from 'next/server'
import { getDeepAgentsDaemonClient } from '@/lib/deepagents/daemon-client'

export const runtime = 'nodejs'

interface ApproveRequest {
  threadId: string
  assistantId?: string
  interruptId: string
  decision: 'approve' | 'reject' | 'auto_approve_all'
}

export async function POST(request: NextRequest) {
  try {
    const body: ApproveRequest = await request.json()

    if (!body.threadId || !body.interruptId || !body.decision) {
      return NextResponse.json({ error: 'threadId, interruptId, decision are required' }, { status: 400 })
    }

    const client = getDeepAgentsDaemonClient()
    const result = await client.request('resume', {
      thread_id: body.threadId,
      assistant_id: body.assistantId || 'agent',
      interrupt_id: body.interruptId,
      decision: body.decision,
    })

    return NextResponse.json(result)
  } catch (error: any) {
    console.error('Approve API error:', error)
    return NextResponse.json({ error: error.message || 'Internal server error' }, { status: 500 })
  }
}
