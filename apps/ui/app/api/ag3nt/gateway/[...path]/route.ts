import { NextRequest } from 'next/server'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

interface RouteParams {
  params: Promise<{ path: string[] }>
}

function getGatewayBaseUrl(): string {
  const raw =
    process.env.AG3NT_GATEWAY_URL ||
    process.env.NEXT_PUBLIC_AG3NT_GATEWAY_URL ||
    'http://127.0.0.1:18789'
  return raw.replace(/\/+$/, '')
}

async function proxy(request: NextRequest, segments: string[]) {
  const base = getGatewayBaseUrl()
  const target = new URL(`${base}/api/${segments.join('/')}`)

  // Preserve query string
  request.nextUrl.searchParams.forEach((value, key) => {
    target.searchParams.set(key, value)
  })

  const headers = new Headers(request.headers)
  // Avoid forwarding hop-by-hop headers.
  headers.delete('host')
  headers.delete('connection')
  headers.delete('content-length')

  const init: RequestInit = {
    method: request.method,
    headers,
    cache: 'no-store',
    signal: AbortSignal.timeout(30_000),
  }

  if (request.method !== 'GET' && request.method !== 'HEAD') {
    const body = await request.arrayBuffer()
    if (body.byteLength > 0) init.body = body
  }

  const res = await fetch(target.toString(), init)
  return new Response(res.body, {
    status: res.status,
    headers: res.headers,
  })
}

export async function GET(request: NextRequest, { params }: RouteParams) {
  const { path } = await params
  return proxy(request, path)
}

export async function POST(request: NextRequest, { params }: RouteParams) {
  const { path } = await params
  return proxy(request, path)
}

export async function PUT(request: NextRequest, { params }: RouteParams) {
  const { path } = await params
  return proxy(request, path)
}

export async function PATCH(request: NextRequest, { params }: RouteParams) {
  const { path } = await params
  return proxy(request, path)
}

export async function DELETE(request: NextRequest, { params }: RouteParams) {
  const { path } = await params
  return proxy(request, path)
}

