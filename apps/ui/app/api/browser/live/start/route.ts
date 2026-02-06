import { NextRequest, NextResponse } from "next/server"
import { isStandaloneUi } from "@/lib/standalone"

export const runtime = "nodejs"

type LiveStartRequest = {
  url?: string
}

/**
 * POST /api/browser/live/start
 *
 * Standalone UI stub:
 * - Original upstream: `POST http://{AGENT_SCRAPER_HOST}:{AGENT_SCRAPER_PORT}/v1/live/start`
 * - Request JSON: `{ url: string }`
 * - Response JSON: `{ ok: true, sessionId: string, wsPath: string, streamPort?: number }`
 * - Auth/headers: typically `Content-Type: application/json` (auth varies by deployment)
 */
export async function POST(request: NextRequest) {
  const body = (await request.json().catch(() => ({}))) as LiveStartRequest
  const url = typeof body.url === "string" && body.url.trim() ? body.url.trim() : "https://www.google.com"

  if (isStandaloneUi()) {
    return NextResponse.json(
      { ok: false, error: "Browser live sessions are unavailable in standalone UI mode" },
      { status: 400 }
    )
  }

  const host = process.env.NEXT_PUBLIC_AGENT_SCRAPER_HOST || "localhost"
  const port = process.env.NEXT_PUBLIC_AGENT_SCRAPER_PORT || "3000"
  const upstream = `http://${host}:${port}/v1/live/start`

  try {
    const res = await fetch(upstream, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    })

    const data = await res.json().catch(() => ({ ok: false, error: res.statusText }))
    return NextResponse.json(data, { status: res.status })
  } catch (e) {
    return NextResponse.json({ ok: false, error: `Failed to reach upstream: ${upstream}` }, { status: 502 })
  }
}
