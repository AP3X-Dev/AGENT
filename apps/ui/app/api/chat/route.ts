import { NextRequest, NextResponse } from 'next/server'
import { getDeepAgentsDaemonClient } from '@/lib/deepagents/daemon-client'

export const runtime = 'nodejs'

interface ChatMessage {
  role: 'user' | 'assistant' | 'system'
  content: string
}

interface ChatRequest {
  messages: ChatMessage[]
  threadId?: string
  assistantId?: string
  autoApprove?: boolean
}

export async function POST(request: NextRequest) {
  try {
    const body: ChatRequest = await request.json()
    const { messages, threadId, assistantId, autoApprove } = body

    if (!messages || messages.length === 0) {
      return NextResponse.json(
        { error: 'Messages are required' },
        { status: 400 }
      )
    }

    // Use the last user message as the prompt; the agent maintains its own
    // conversation state via LangGraph checkpointer keyed by thread_id.
    const lastUser = [...messages].reverse().find(m => m.role === 'user')
    if (!lastUser) {
      return NextResponse.json({ error: 'No user message found' }, { status: 400 })
    }

    const client = getDeepAgentsDaemonClient()
    const result = await client.request('chat', {
      thread_id: threadId,
      assistant_id: assistantId || 'agent',
      message: lastUser.content,
      auto_approve: autoApprove ?? false,
    })

    return NextResponse.json(result)
  } catch (error: any) {
    console.error('Chat API error:', error)
    return NextResponse.json(
      { error: error.message || 'Internal server error' },
      { status: 500 }
    )
  }
}

