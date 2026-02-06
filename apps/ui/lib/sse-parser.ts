/**
 * Shared SSE (Server-Sent Events) stream parser.
 *
 * Extracts `event:` / `data:` pairs from a ReadableStream and delivers
 * them via a callback, eliminating duplicate buffer/parse logic across
 * the codebase.
 */

export interface SSEEvent {
  event: string;
  data: unknown;
}

/**
 * Parse an SSE stream from a ReadableStreamDefaultReader.
 *
 * @param reader  - The stream reader (from `response.body.getReader()`)
 * @param onEvent - Called for every successfully parsed event
 */
export async function parseSSEStream(
  reader: ReadableStreamDefaultReader<Uint8Array>,
  onEvent: (evt: SSEEvent) => void,
): Promise<void> {
  const decoder = new TextDecoder();
  let buffer = "";
  let currentEvent = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      if (line.startsWith("event: ")) {
        currentEvent = line.slice(7);
      } else if (line.startsWith("data: ") && currentEvent) {
        try {
          const data: unknown = JSON.parse(line.slice(6));
          onEvent({ event: currentEvent, data });
        } catch {
          // Skip malformed JSON lines
        }
        currentEvent = "";
      }
    }
  }
}
