/**
 * Session-scoped directive system.
 *
 * Manages directives that customize agent behavior per session.
 * Directives are stored as part of EnhancedSession and injected
 * into the system prompt.
 */
import { randomUUID } from 'crypto';
import type { SessionStore, Directive, EnhancedSession } from '../session/SessionStore.js';

// ─────────────────────────────────────────────────────────────────
// DirectiveManager
// ─────────────────────────────────────────────────────────────────

export class DirectiveManager {
  private sessionStore: SessionStore;

  constructor(sessionStore: SessionStore) {
    this.sessionStore = sessionStore;
  }

  /**
   * Add a directive to a session.
   */
  add(sessionId: string, directive: Omit<Directive, 'id' | 'createdAt'>): Directive {
    const session = this.sessionStore.load(sessionId);
    if (!session) {
      throw new Error(`Session not found: ${sessionId}`);
    }

    const newDirective: Directive = {
      id: randomUUID(),
      type: directive.type,
      content: directive.content,
      priority: directive.priority,
      active: directive.active,
      createdAt: new Date().toISOString(),
    };

    session.directives.push(newDirective);
    this.sessionStore.updateField(sessionId, 'directives', session.directives);

    return newDirective;
  }

  /**
   * Remove a directive from a session.
   */
  remove(sessionId: string, directiveId: string): boolean {
    const session = this.sessionStore.load(sessionId);
    if (!session) return false;

    const index = session.directives.findIndex((d) => d.id === directiveId);
    if (index === -1) return false;

    session.directives.splice(index, 1);
    this.sessionStore.updateField(sessionId, 'directives', session.directives);

    return true;
  }

  /**
   * List all directives for a session.
   */
  list(sessionId: string): Directive[] {
    const session = this.sessionStore.load(sessionId);
    if (!session) return [];

    return session.directives;
  }

  /**
   * Toggle a directive's active status.
   */
  toggle(sessionId: string, directiveId: string, active: boolean): boolean {
    const session = this.sessionStore.load(sessionId);
    if (!session) return false;

    const directive = session.directives.find((d) => d.id === directiveId);
    if (!directive) return false;

    directive.active = active;
    this.sessionStore.updateField(sessionId, 'directives', session.directives);

    return true;
  }

  /**
   * Build a prompt prefix from active directives.
   * Directives are sorted by priority (lower number = higher priority)
   * and concatenated into a single string.
   */
  buildPromptPrefix(sessionId: string): string {
    const session = this.sessionStore.load(sessionId);
    if (!session) return '';

    const activeDirectives = session.directives
      .filter((d) => d.active)
      .sort((a, b) => a.priority - b.priority);

    if (activeDirectives.length === 0) return '';

    const parts = activeDirectives.map(
      (d) => `[${d.type.toUpperCase()} DIRECTIVE] ${d.content}`,
    );

    return parts.join('\n\n') + '\n\n';
  }
}
