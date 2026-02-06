import fs from 'fs'
import { mkdir, readFile, writeFile } from 'fs/promises'
import os from 'os'
import path from 'path'
import type { McpServerCategory, McpServerConfig, McpTransport } from '@/types/mcp'

type McpServersFile = {
  mcpServers: Record<
    string,
    {
      // Standard Claude Desktop / MCP fields
      command?: string
      args?: string[]
      env?: Record<string, string>

      // Optional HTTP JSON-RPC form (not currently used by AG3NT runtime)
      url?: string
      headers?: Record<string, string>

      // UI convenience fields
      enabled?: boolean
      name?: string
      description?: string
      category?: McpServerCategory
      icon?: string
      installedAt?: string
    }
  >
}

export function getAg3ntMcpConfigPath(): string {
  return path.join(os.homedir(), '.ag3nt', 'mcp_servers.json')
}

export async function loadAg3ntMcpConfig(): Promise<McpServersFile> {
  const configPath = getAg3ntMcpConfigPath()
  if (!fs.existsSync(configPath)) return { mcpServers: {} }
  try {
    const raw = await readFile(configPath, 'utf-8')
    const parsed = JSON.parse(raw)
    if (parsed && typeof parsed === 'object' && parsed.mcpServers && typeof parsed.mcpServers === 'object') {
      return { mcpServers: parsed.mcpServers as McpServersFile['mcpServers'] }
    }
  } catch {
    // ignore
  }
  return { mcpServers: {} }
}

export async function saveAg3ntMcpConfig(config: McpServersFile): Promise<void> {
  const configPath = getAg3ntMcpConfigPath()
  await mkdir(path.dirname(configPath), { recursive: true })
  await writeFile(configPath, JSON.stringify(config, null, 2) + '\n', 'utf-8')
}

function inferCategory(id: string): McpServerCategory {
  const key = id.toLowerCase()
  if (key.includes('playwright') || key.includes('browser')) return 'browser'
  if (key.includes('filesystem') || key.includes('file')) return 'filesystem'
  if (key.includes('search') || key.includes('brave')) return 'search'
  if (key.includes('github')) return 'developer'
  if (key.includes('sequential') || key.includes('thinking')) return 'ai'
  return 'other'
}

function inferIcon(category: McpServerCategory): string {
  switch (category) {
    case 'browser':
      return 'Globe'
    case 'filesystem':
      return 'FolderOpen'
    case 'search':
      return 'Search'
    case 'developer':
      return 'Github'
    case 'ai':
      return 'Brain'
    default:
      return 'Plug'
  }
}

export function toMcpServerConfig(id: string, entry: McpServersFile['mcpServers'][string]): McpServerConfig {
  const enabled = entry.enabled !== false
  const category = entry.category || inferCategory(id)
  const icon = entry.icon || inferIcon(category)

  const transport: McpTransport = entry.url ? 'http_jsonrpc' : 'stdio'

  return {
    id,
    name: entry.name || id,
    description: entry.description || '',
    category,
    icon,
    transport,
    // Transport fields
    ...(entry.url ? { url: entry.url, headers: entry.headers } : {}),
    ...(entry.command ? { command: entry.command } : {}),
    ...(Array.isArray(entry.args) ? { args: entry.args } : {}),
    ...(entry.env ? { env: entry.env } : {}),
    // UI fields
    enabled,
    // Runtime fields (populated by /test or future status probes)
    status: 'unknown',
    error: null,
    toolCount: 0,
    tools: [],
    lastConnected: null,
    installedAt: entry.installedAt || null,
  }
}

