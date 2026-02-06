import { NextRequest } from "next/server";
import { getDeepAgentsDaemonClient } from "@/lib/deepagents/daemon-client";
import type { FileAttachment } from "@/types/types";

const debugLog: (...args: unknown[]) => void =
  process.env.NODE_ENV === "development"
    ? (...args: unknown[]) => { console.log(...args); }
    : () => {};

interface StreamRequest {
  threadId?: string;
  assistantId?: string;
  message: string;
  autoApprove?: boolean;
  model?: string;
  attachments?: FileAttachment[];
  uiContext?: string;
}

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
  let body: StreamRequest;
  try {
    body = await request.json();
  } catch (e) {
    console.error("[API] Failed to parse request body:", e);
    return new Response(
      JSON.stringify({ error: "Invalid JSON in request body" }),
      {
        status: 400,
        headers: { "Content-Type": "application/json" },
      },
    );
  }

  const {
    message,
    threadId,
    assistantId,
    autoApprove,
    model,
    attachments,
    uiContext,
  } = body;

  // Allow empty message if there are attachments
  if (!message && (!attachments || attachments.length === 0)) {
    return new Response(
      JSON.stringify({ error: "Message or attachments required" }),
      {
        status: 400,
        headers: { "Content-Type": "application/json" },
      },
    );
  }

  const encoder = new TextEncoder();
  const client = getDeepAgentsDaemonClient();
  let streamId: string | null = null;

  const stream = new ReadableStream({
    start(controller) {
      debugLog(
        "[API] Starting stream for message:",
        message,
        "| model:",
        model || "(default)",
        "| attachments:",
        attachments?.length || 0,
      );
      let isClosed = false;

      const sendEvent = (event: string, data: any) => {
        if (isClosed) {
          debugLog("[API] Skipping event (stream closed):", event);
          return;
        }
        try {
          debugLog("[API] Sending event:", event, data);
          controller.enqueue(
            encoder.encode(
              `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`,
            ),
          );
        } catch (e) {
          debugLog(
            "[API] Failed to send event (stream likely closed):",
            event,
          );
          isClosed = true;
        }
      };

      const closeController = () => {
        if (!isClosed) {
          isClosed = true;
          try {
            controller.close();
          } catch {
            /* already closed */
          }
        }
      };

      // Convert attachments to daemon format
      const daemonAttachments = attachments?.map((a) => ({
        id: a.id,
        name: a.name,
        type: a.type,
        size: a.size,
        content: a.content,
        data_url: a.dataUrl,
      }));

      streamId = client.requestStream(
        "chat_stream",
        {
          thread_id: threadId,
          assistant_id: assistantId || "agent",
          message: message || "",
          auto_approve: autoApprove ?? false,
          model: model || undefined,
          attachments: daemonAttachments,
          ui_context: uiContext || undefined,
        },
        (event) => {
          debugLog("[API] Received event from daemon:", event.type);
          // Map event types to SSE events
          switch (event.type) {
            case "status":
              sendEvent("status", {
                status: event.status,
                message: event.message,
              });
              break;
            case "thread_id":
              sendEvent("thread_id", { threadId: event.thread_id });
              break;
            case "text_delta":
              sendEvent("text_delta", { text: event.text });
              break;
            case "reasoning_delta":
              sendEvent("reasoning_delta", { text: event.text });
              break;
            case "tool_call":
              sendEvent("tool_call", {
                toolName: event.tool_name,
                toolCallId: event.tool_call_id,
                args: event.args,
              });
              break;
            case "tool_result":
              sendEvent("tool_result", {
                toolName: event.tool_name,
                toolCallId: event.tool_call_id,
                status: event.status,
                output: event.output,
                args: event.args,
                path: event.path,
                diff: event.diff,
                readOutput: event.read_output,
                error: event.error,
              });
              break;
            case "approval_required":
              sendEvent("approval_required", {
                approvals: event.approvals,
                autoApprove: event.auto_approve,
              });
              break;
            case "done":
              sendEvent("done", {
                approvalRequired: event.approval_required,
                autoApprove: event.auto_approve,
              });
              break;
            default:
              // Forward unknown events as-is
              sendEvent(event.type, event);
          }
        },
        () => {
          // Stream complete
          debugLog("[API] Stream complete from daemon");
          closeController();
        },
        (error) => {
          console.error("[API] Stream error from daemon:", error.message);
          sendEvent("error", { message: error.message });
          closeController();
        },
      );
    },
    cancel() {
      // Client disconnected - cancel the daemon stream
      debugLog("[API] Stream cancelled by client");
      if (streamId) {
        client.cancelStream(streamId);
      }
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
    },
  });
}
