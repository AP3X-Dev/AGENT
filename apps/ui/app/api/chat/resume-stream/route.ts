import { NextRequest } from 'next/server'
import { getDeepAgentsDaemonClient } from '@/lib/deepagents/daemon-client'

interface ResumeStreamRequest {
  threadId: string
  assistantId?: string
  interruptId: string
  decision: string
}

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export async function POST(request: NextRequest) {
  const body: ResumeStreamRequest = await request.json()
  const { threadId, assistantId, interruptId, decision } = body

  if (!threadId || !interruptId || !decision) {
    return new Response(
      JSON.stringify({ error: 'threadId, interruptId, and decision are required' }),
      { status: 400, headers: { 'Content-Type': 'application/json' } }
    )
  }

  const encoder = new TextEncoder()
  const client = getDeepAgentsDaemonClient()
  let streamId: string | null = null

  const stream = new ReadableStream({
    start(controller) {
      let isClosed = false

      const sendEvent = (event: string, data: any) => {
        if (isClosed) return
        try {
          controller.enqueue(encoder.encode(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`))
        } catch {
          isClosed = true
        }
      }

      streamId = client.requestStream(
        'resume_stream',
        {
          thread_id: threadId,
          assistant_id: assistantId || 'agent',
          interrupt_id: interruptId,
          decision,
        },
        (event) => {
          switch (event.type) {
            case 'status':
              sendEvent('status', { status: event.status, message: event.message })
              break
            case 'thread_id':
              sendEvent('thread_id', { threadId: event.thread_id })
              break
            case 'text_delta':
              sendEvent('text_delta', { text: event.text })
              break
            case 'reasoning_delta':
              sendEvent('reasoning_delta', { text: event.text })
              break
            case 'tool_call':
              sendEvent('tool_call', {
                toolName: event.tool_name,
                toolCallId: event.tool_call_id,
                args: event.args,
              })
              break
            case 'tool_result':
              sendEvent('tool_result', {
                toolName: event.tool_name,
                toolCallId: event.tool_call_id,
                status: event.status,
                output: event.output,
                args: event.args,
                path: event.path,
                diff: event.diff,
                readOutput: event.read_output,
                error: event.error,
              })
              break
            case 'nested_tool_call':
              sendEvent('nested_tool_call', {
                parentToolCallId: event.parent_tool_call_id,
                toolName: event.tool_name,
                toolCallId: event.tool_call_id,
                args: event.args,
              })
              break
            case 'nested_tool_result':
              sendEvent('nested_tool_result', {
                parentToolCallId: event.parent_tool_call_id,
                toolName: event.tool_name,
                toolCallId: event.tool_call_id,
                status: event.status,
                output: event.output,
                error: event.error,
              })
              break
            case 'approval_required':
              sendEvent('approval_required', {
                approvals: event.approvals,
                autoApprove: event.auto_approve,
              })
              break
            case 'done':
              sendEvent('done', {
                approvalRequired: event.approval_required,
                autoApprove: event.auto_approve,
              })
              break
            default:
              sendEvent(event.type, event)
          }
        },
        () => {
          isClosed = true
          try {
            controller.close()
          } catch {
            /* ignore */
          }
        },
        (error) => {
          sendEvent('error', { message: error.message })
          isClosed = true
          try {
            controller.close()
          } catch {
            /* ignore */
          }
        }
      )
    },
    cancel() {
      // Client disconnected - cancel the daemon stream
      console.log("[API] Resume stream cancelled by client")
      if (streamId) {
        client.cancelStream(streamId)
      }
    },
  })

  return new Response(stream, {
    headers: {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
      Connection: 'keep-alive',
    },
  })
}
