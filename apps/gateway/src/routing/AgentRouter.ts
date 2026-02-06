/**
 * Intelligent agent routing layer.
 *
 * Selects the best agent/worker for a message based on routing
 * strategies: explicit assignment, directive-based, content-based,
 * priority-based, and default fallback.
 */
import type { ChannelMessage } from '../channels/types.js';
import type { EnhancedSession } from '../session/SessionStore.js';
import { WORKER_URL as DEFAULT_WORKER_URL } from '../config/constants.js';

// ─────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────

export interface RoutingDecision {
  agentName: string;
  workerUrl: string;
  reason: string;
  priority: number;
}

export interface RoutingConfig {
  strategy: 'auto' | 'explicit' | 'round-robin';
  defaultAgent: string;
  contentPatterns: ContentPattern[];
}

export interface ContentPattern {
  pattern: string;
  agentName: string;
}

export interface AgentInfo {
  name: string;
  description: string;
  priority: number;
  available: boolean;
}

// ─────────────────────────────────────────────────────────────────
// SubagentRegistryClient
// ─────────────────────────────────────────────────────────────────

export class SubagentRegistryClient {
  private workerUrl: string;
  private cachedAgents: AgentInfo[] = [];
  private lastFetch = 0;
  private cacheTTL = 30_000; // 30 seconds

  constructor(workerUrl?: string) {
    this.workerUrl = workerUrl || DEFAULT_WORKER_URL;
  }

  async getAvailableAgents(): Promise<AgentInfo[]> {
    const now = Date.now();
    if (now - this.lastFetch < this.cacheTTL && this.cachedAgents.length > 0) {
      return this.cachedAgents;
    }

    try {
      const response = await fetch(`${this.workerUrl}/subagents`, {
        method: 'GET',
        headers: { 'Content-Type': 'application/json' },
        signal: AbortSignal.timeout(5000),
      });

      if (!response.ok) return this.cachedAgents;

      const data = (await response.json()) as { subagents?: Array<{ config: any }> };
      const subagents = data.subagents || [];

      this.cachedAgents = subagents.map((s: any) => ({
        name: s.config?.name || s.name || 'unknown',
        description: s.config?.description || s.description || '',
        priority: s.config?.priority ?? 5,
        available: true,
      }));
      this.lastFetch = now;

      return this.cachedAgents;
    } catch {
      // Return cached or empty on failure
      return this.cachedAgents;
    }
  }
}

// ─────────────────────────────────────────────────────────────────
// AgentRouter
// ─────────────────────────────────────────────────────────────────

export class AgentRouter {
  private config: RoutingConfig;
  private registry: SubagentRegistryClient;
  private workerUrl: string;

  constructor(config: RoutingConfig, registry: SubagentRegistryClient, workerUrl?: string) {
    this.config = config;
    this.registry = registry;
    this.workerUrl = workerUrl || DEFAULT_WORKER_URL;
  }

  async route(message: ChannelMessage, session: EnhancedSession): Promise<RoutingDecision> {
    // Strategy 1: Explicit assignment
    if (session.assignedAgent) {
      return {
        agentName: session.assignedAgent,
        workerUrl: this.workerUrl,
        reason: `Explicitly assigned to agent: ${session.assignedAgent}`,
        priority: session.priority,
      };
    }

    // Strategy 2: Directive-based
    const directiveAgent = this.findAgentFromDirectives(session);
    if (directiveAgent) {
      return {
        agentName: directiveAgent,
        workerUrl: this.workerUrl,
        reason: `Agent specified by directive: ${directiveAgent}`,
        priority: session.priority,
      };
    }

    // Strategy 3: Content-based pattern matching
    if (this.config.strategy === 'auto' && this.config.contentPatterns.length > 0) {
      const matched = this.matchContentPattern(message.text);
      if (matched) {
        return {
          agentName: matched,
          workerUrl: this.workerUrl,
          reason: `Content pattern matched for agent: ${matched}`,
          priority: session.priority,
        };
      }
    }

    // Strategy 4: Priority-based (fetch available agents, pick best for priority)
    if (this.config.strategy === 'auto') {
      const agents = await this.registry.getAvailableAgents();
      if (agents.length > 0 && session.priority <= 3) {
        // High-priority sessions get the highest-priority agent
        const best = agents.reduce((a, b) => (a.priority < b.priority ? a : b));
        if (best.priority <= 3) {
          return {
            agentName: best.name,
            workerUrl: this.workerUrl,
            reason: `High-priority session routed to best agent: ${best.name}`,
            priority: session.priority,
          };
        }
      }
    }

    // Strategy 5: Default fallback
    const defaultAgent = this.config.defaultAgent || 'main';
    return {
      agentName: defaultAgent,
      workerUrl: this.workerUrl,
      reason: 'Default routing',
      priority: session.priority,
    };
  }

  async getAvailableAgents(): Promise<AgentInfo[]> {
    return this.registry.getAvailableAgents();
  }

  private findAgentFromDirectives(session: EnhancedSession): string | null {
    for (const directive of session.directives) {
      if (!directive.active) continue;
      // Look for directives that specify an agent with "agent:" prefix
      const agentMatch = directive.content.match(/^agent:\s*(\S+)/i);
      if (agentMatch) {
        return agentMatch[1];
      }
    }
    return null;
  }

  private matchContentPattern(text: string): string | null {
    const lower = text.toLowerCase();
    for (const { pattern, agentName } of this.config.contentPatterns) {
      try {
        if (new RegExp(pattern, 'i').test(lower)) {
          return agentName;
        }
      } catch {
        // Invalid regex, try plain string match
        if (lower.includes(pattern.toLowerCase())) {
          return agentName;
        }
      }
    }
    return null;
  }
}
