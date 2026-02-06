import { NextRequest, NextResponse } from 'next/server'
import type { McpCatalogEntry, McpCatalogResponse } from '@/types/mcp'
import { loadAg3ntMcpConfig, saveAg3ntMcpConfig, toMcpServerConfig } from '@/lib/mcp/config'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

function getCatalog(): McpCatalogEntry[] {
  return [
    {
      id: 'playwright',
      name: 'Playwright',
      description: 'Browser automation for web testing and scraping with Playwright',
      category: 'browser',
      icon: 'Globe',
      transport: 'stdio',
      default_command: 'npx',
      default_args: ['-y', '@anthropic/mcp-playwright'],
      install_command: 'npx -y @anthropic/mcp-playwright',
      documentation_url: 'https://github.com/anthropics/mcp-playwright',
      source: 'official',
    },
    {
      id: 'sequential-thinking',
      name: 'Sequential Thinking',
      description: 'Think through complex problems step-by-step with structured reasoning',
      category: 'ai',
      icon: 'Brain',
      transport: 'stdio',
      default_command: 'npx',
      default_args: ['-y', '@modelcontextprotocol/server-sequential-thinking'],
      install_command: 'npx -y @modelcontextprotocol/server-sequential-thinking',
      documentation_url: 'https://github.com/modelcontextprotocol/servers',
      source: 'official',
    },
    {
      id: 'context7',
      name: 'Context 7',
      description: 'Package documentation lookup and code context retrieval',
      category: 'developer',
      icon: 'BookOpen',
      transport: 'stdio',
      default_command: 'npx',
      default_args: ['-y', '@upstash/context7-mcp@latest'],
      install_command: 'npx -y @upstash/context7-mcp@latest',
      documentation_url: 'https://github.com/upstash/context7',
      source: 'verified',
    },
    {
      id: 'filesystem',
      name: 'Filesystem',
      description: 'Read and write files, list directories, and manage the filesystem',
      category: 'filesystem',
      icon: 'FolderOpen',
      transport: 'stdio',
      default_command: 'npx',
      default_args: ['-y', '@modelcontextprotocol/server-filesystem', '.'],
      install_command: 'npx -y @modelcontextprotocol/server-filesystem .',
      documentation_url: 'https://github.com/modelcontextprotocol/servers',
      source: 'official',
    },
    {
      id: 'github',
      name: 'GitHub',
      description: 'Interact with GitHub repositories, issues, pull requests, and more',
      category: 'developer',
      icon: 'Github',
      transport: 'stdio',
      default_command: 'npx',
      default_args: ['-y', '@modelcontextprotocol/server-github'],
      install_command: 'npx -y @modelcontextprotocol/server-github',
      documentation_url: 'https://github.com/modelcontextprotocol/servers',
      source: 'official',
    },
    {
      id: 'brave-search',
      name: 'Brave Search',
      description: 'Web search using Brave Search API for current information',
      category: 'search',
      icon: 'Search',
      transport: 'stdio',
      default_command: 'npx',
      default_args: ['-y', '@modelcontextprotocol/server-brave-search'],
      install_command: 'npx -y @modelcontextprotocol/server-brave-search',
      documentation_url: 'https://github.com/modelcontextprotocol/servers',
      source: 'official',
    },
  ]
}

/**
 * GET /api/mcp/catalog
 * Local MCP catalog for discovery/installation helpers.
 */
export async function GET(request: NextRequest) {
  const q = request.nextUrl.searchParams.get('q')?.toLowerCase()
  const catalog = getCatalog().filter((entry) => {
    if (!q) return true
    return (
      entry.id.toLowerCase().includes(q) ||
      entry.name.toLowerCase().includes(q) ||
      entry.description.toLowerCase().includes(q)
    )
  })

  const data: McpCatalogResponse = { catalog }
  return NextResponse.json(data)
}

/**
 * POST /api/mcp/catalog
 * Install a server from the local catalog by writing to ~/.ag3nt/mcp_servers.json.
 */
export async function POST(request: NextRequest) {
  try {
    const body = await request.json().catch(() => ({}))
    const catalogId = String(body.catalog_id || '').trim()
    if (!catalogId) {
      return NextResponse.json({ error: 'catalog_id is required' }, { status: 400 })
    }

    const entry = getCatalog().find((c) => c.id === catalogId)
    if (!entry) {
      return NextResponse.json({ error: 'Catalog entry not found' }, { status: 404 })
    }

    const config = await loadAg3ntMcpConfig()
    config.mcpServers[entry.id] = {
      enabled: true,
      name: entry.name,
      description: entry.description,
      category: entry.category,
      icon: entry.icon,
      installedAt: new Date().toISOString(),
      ...(entry.transport === 'stdio'
        ? {
            command: entry.default_command || 'npx',
            args: entry.default_args || [],
          }
        : {
            url: entry.default_url || undefined,
          }),
    }

    await saveAg3ntMcpConfig(config)

    return NextResponse.json(
      {
        ok: true,
        installed: true,
        server: toMcpServerConfig(entry.id, config.mcpServers[entry.id]),
      },
      { status: 201 }
    )
  } catch (error: any) {
    console.error('Error installing MCP server:', error)
    return NextResponse.json({ error: error.message || 'Failed to install MCP server' }, { status: 500 })
  }
}

