import { NextRequest } from 'next/server'
import { getDeepAgentsDaemonClient } from '@/lib/deepagents/daemon-client'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export async function POST(request: NextRequest) {
  try {
    const client = getDeepAgentsDaemonClient()
    
    // First clear caches
    const result = await client.clearCaches()
    
    // Then kill the daemon to ensure a fresh start
    client.killDaemon()
    
    return Response.json({
      success: true,
      ...result,
      message: 'Caches cleared and daemon restarted'
    })
  } catch (error: any) {
    console.error('[clear-caches] Error:', error)
    return Response.json(
      { success: false, error: error.message },
      { status: 500 }
    )
  }
}

