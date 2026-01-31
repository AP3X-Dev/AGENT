/**
 * Skills Manager for AG3NT Gateway.
 *
 * Provides skill discovery, metadata extraction, and toggling functionality
 * for the control panel UI.
 *
 * Supports multi-path discovery:
 * - Bundled: ./skills/ - shipped with AG3NT
 * - Global: ~/.ag3nt/skills/ - user's personal skills
 * - Workspace: ./.ag3nt/skills/ - project-specific skills
 */

import * as fs from "node:fs";
import * as path from "node:path";
import * as os from "node:os";

/**
 * Source location of a skill.
 */
export type SkillSource = "bundled" | "global" | "workspace";

export interface SkillMetadata {
  id: string;
  name: string;
  version: string;
  description: string;
  category: string;
  triggers: string[];
  tags: string[];
  entrypoints: Array<{ name: string; description: string }>;
  requiredPermissions: string[];
  enabled: boolean;
  path: string;
  source: SkillSource;
  author?: string;
  license?: string;
}

interface SkillFrontmatter {
  name?: string;
  version?: string;
  description?: string;
  category?: string;
  triggers?: string[];
  tags?: string[];
  entrypoints?: Record<string, { script?: string; description?: string }> | Array<{ name: string; description: string }>;
  required_permissions?: string[];
  license?: string;
  metadata?: {
    author?: string;
    category?: string;
  };
}

export interface SkillsManagerConfig {
  /** Path to bundled skills (default: ./skills/) */
  bundledPath?: string;
  /** Path to global skills (default: ~/.ag3nt/skills/) */
  globalPath?: string;
  /** Path to workspace skills (default: ./.ag3nt/skills/) */
  workspacePath?: string;
}

export class SkillsManager {
  private bundledPath: string | null;
  private globalPath: string | null;
  private workspacePath: string | null;
  private disabledSkills: Set<string> = new Set();

  constructor(bundledPathOrConfig: string | SkillsManagerConfig) {
    if (typeof bundledPathOrConfig === "string") {
      // Legacy single-path constructor
      this.bundledPath = path.resolve(bundledPathOrConfig);
      this.globalPath = path.join(os.homedir(), ".ag3nt", "skills");
      this.workspacePath = null;
    } else {
      // New config-based constructor
      const config = bundledPathOrConfig;
      this.bundledPath = config.bundledPath ? path.resolve(config.bundledPath) : null;
      this.globalPath = config.globalPath ? path.resolve(config.globalPath) : path.join(os.homedir(), ".ag3nt", "skills");
      this.workspacePath = config.workspacePath ? path.resolve(config.workspacePath) : null;
    }
  }

  /**
   * Legacy getter for backward compatibility.
   */
  private get skillsPath(): string {
    return this.bundledPath || "";
  }

  /**
   * Get all available skills with their metadata.
   * Skills are discovered from all configured paths (bundled, global, workspace).
   * Later sources can override earlier ones (workspace > global > bundled).
   */
  async getAllSkills(): Promise<SkillMetadata[]> {
    const skillsMap = new Map<string, SkillMetadata>();

    // Load from bundled path first (lowest priority)
    if (this.bundledPath) {
      await this.loadSkillsFromPath(this.bundledPath, "bundled", skillsMap);
    }

    // Load from global path (medium priority)
    if (this.globalPath) {
      await this.loadSkillsFromPath(this.globalPath, "global", skillsMap);
    }

    // Load from workspace path last (highest priority)
    if (this.workspacePath) {
      await this.loadSkillsFromPath(this.workspacePath, "workspace", skillsMap);
    }

    return Array.from(skillsMap.values());
  }

  /**
   * Load skills from a specific path into the skills map.
   */
  private async loadSkillsFromPath(
    skillsPath: string,
    source: SkillSource,
    skillsMap: Map<string, SkillMetadata>
  ): Promise<void> {
    if (!fs.existsSync(skillsPath)) {
      return;
    }

    const entries = fs.readdirSync(skillsPath, { withFileTypes: true });

    for (const entry of entries) {
      if (!entry.isDirectory()) continue;

      const skillDir = path.join(skillsPath, entry.name);
      const skillMdPath = path.join(skillDir, "SKILL.md");

      if (!fs.existsSync(skillMdPath)) continue;

      try {
        const content = fs.readFileSync(skillMdPath, "utf-8");
        const metadata = this.parseSkillMd(entry.name, skillDir, content, source);
        skillsMap.set(metadata.id, metadata);
      } catch (err) {
        console.error(`[SkillsManager] Error parsing ${skillMdPath}:`, err);
      }
    }
  }

  /**
   * Get a specific skill by ID.
   * Searches all paths in priority order (workspace > global > bundled).
   */
  async getSkill(skillId: string): Promise<SkillMetadata | null> {
    // Check workspace first (highest priority)
    if (this.workspacePath) {
      const skill = await this.getSkillFromPath(skillId, this.workspacePath, "workspace");
      if (skill) return skill;
    }

    // Check global second
    if (this.globalPath) {
      const skill = await this.getSkillFromPath(skillId, this.globalPath, "global");
      if (skill) return skill;
    }

    // Check bundled last (lowest priority)
    if (this.bundledPath) {
      const skill = await this.getSkillFromPath(skillId, this.bundledPath, "bundled");
      if (skill) return skill;
    }

    return null;
  }

  /**
   * Get a skill from a specific path.
   */
  private async getSkillFromPath(
    skillId: string,
    skillsPath: string,
    source: SkillSource
  ): Promise<SkillMetadata | null> {
    const skillDir = path.join(skillsPath, skillId);
    const skillMdPath = path.join(skillDir, "SKILL.md");

    if (!fs.existsSync(skillMdPath)) {
      return null;
    }

    try {
      const content = fs.readFileSync(skillMdPath, "utf-8");
      return this.parseSkillMd(skillId, skillDir, content, source);
    } catch {
      return null;
    }
  }

  /**
   * Get all unique categories from available skills.
   */
  async getCategories(): Promise<string[]> {
    const skills = await this.getAllSkills();
    const categories = new Set<string>();

    for (const skill of skills) {
      if (skill.category) {
        categories.add(skill.category);
      }
    }

    return Array.from(categories).sort();
  }

  /**
   * Get the raw SKILL.md content.
   * Searches all paths in priority order (workspace > global > bundled).
   */
  async getSkillContent(skillId: string): Promise<string | null> {
    // Check workspace first (highest priority)
    if (this.workspacePath) {
      const content = this.getSkillContentFromPath(skillId, this.workspacePath);
      if (content) return content;
    }

    // Check global second
    if (this.globalPath) {
      const content = this.getSkillContentFromPath(skillId, this.globalPath);
      if (content) return content;
    }

    // Check bundled last (lowest priority)
    if (this.bundledPath) {
      const content = this.getSkillContentFromPath(skillId, this.bundledPath);
      if (content) return content;
    }

    return null;
  }

  /**
   * Get skill content from a specific path.
   */
  private getSkillContentFromPath(skillId: string, skillsPath: string): string | null {
    const skillMdPath = path.join(skillsPath, skillId, "SKILL.md");

    if (!fs.existsSync(skillMdPath)) {
      return null;
    }

    return fs.readFileSync(skillMdPath, "utf-8");
  }

  /**
   * Toggle a skill on/off.
   */
  toggleSkill(skillId: string, enabled: boolean): boolean {
    if (enabled) {
      this.disabledSkills.delete(skillId);
    } else {
      this.disabledSkills.add(skillId);
    }
    return true;
  }

  /**
   * Check if a skill is enabled.
   */
  isEnabled(skillId: string): boolean {
    return !this.disabledSkills.has(skillId);
  }

  /**
   * Parse SKILL.md file to extract metadata.
   */
  private parseSkillMd(
    id: string,
    skillDir: string,
    content: string,
    source: SkillSource
  ): SkillMetadata {
    const frontmatter = this.extractFrontmatter(content);

    // Convert entrypoints from Record to Array if needed
    let entrypoints: Array<{ name: string; description: string }> = [];
    if (frontmatter.entrypoints) {
      if (Array.isArray(frontmatter.entrypoints)) {
        entrypoints = frontmatter.entrypoints;
      } else {
        // Convert Record<string, { script?: string; description?: string }> to Array
        entrypoints = Object.entries(frontmatter.entrypoints).map(([name, entry]) => ({
          name,
          description: entry.description || "",
        }));
      }
    }

    // Get category from frontmatter or metadata.category
    const category = frontmatter.category || frontmatter.metadata?.category || "general";

    // Get author from metadata.author
    const author = frontmatter.metadata?.author;

    return {
      id,
      name: frontmatter.name || id,
      version: frontmatter.version || "1.0.0",
      description: frontmatter.description || "",
      category,
      triggers: frontmatter.triggers || [],
      tags: frontmatter.tags || [],
      entrypoints,
      requiredPermissions: frontmatter.required_permissions || [],
      enabled: this.isEnabled(id),
      path: skillDir,
      source,
      author,
      license: frontmatter.license,
    };
  }

  /**
   * Extract YAML frontmatter from SKILL.md.
   * Supports nested metadata section for author, category, etc.
   */
  private extractFrontmatter(content: string): SkillFrontmatter {
    const frontmatterMatch = content.match(/^---\n([\s\S]*?)\n---/);

    if (!frontmatterMatch) {
      return {};
    }

    const yaml = frontmatterMatch[1];
    const result: SkillFrontmatter = {};

    // Simple YAML parsing for common fields
    const lines = yaml.split("\n");
    let currentKey = "";
    let inList = false;
    let listItems: string[] = [];
    let inMetadata = false;

    for (const line of lines) {
      // Check for nested metadata section
      if (line.match(/^metadata:\s*$/)) {
        // Save previous list if any
        if (inList && currentKey) {
          this.setFrontmatterValue(result, currentKey, listItems, null);
        }
        inMetadata = true;
        inList = false;
        result.metadata = {};
        continue;
      }

      // Handle metadata nested keys (indented with 2 spaces)
      if (inMetadata) {
        const nestedMatch = line.match(/^\s{2}(\w+):\s*(.*)/);
        if (nestedMatch) {
          const nestedKey = nestedMatch[1];
          const nestedValue = nestedMatch[2].trim().replace(/^["']|["']$/g, "");
          if (result.metadata) {
            if (nestedKey === "author") {
              result.metadata.author = nestedValue;
            } else if (nestedKey === "category") {
              result.metadata.category = nestedValue;
            }
          }
          continue;
        }
        // If we hit a non-indented line, exit metadata section
        if (!line.match(/^\s/) && line.trim()) {
          inMetadata = false;
        }
      }

      const keyMatch = line.match(/^(\w+):\s*(.*)/);

      if (keyMatch) {
        // Save previous list if any
        if (inList && currentKey) {
          this.setFrontmatterValue(result, currentKey, listItems, null);
        }

        currentKey = keyMatch[1];
        const value = keyMatch[2].trim();

        if (value === "" || value === "|") {
          inList = true;
          listItems = [];
        } else {
          inList = false;
          this.setFrontmatterValue(result, currentKey, value, null);
        }
      } else if (inList && line.match(/^\s+-\s+(.+)/)) {
        const itemMatch = line.match(/^\s+-\s+(.+)/);
        if (itemMatch) {
          listItems.push(itemMatch[1].trim().replace(/^["']|["']$/g, ""));
        }
      }
    }

    // Save last list if any
    if (inList && currentKey) {
      this.setFrontmatterValue(result, currentKey, listItems, null);
    }

    return result;
  }

  private setFrontmatterValue(
    result: SkillFrontmatter,
    key: string,
    value: string | string[],
    _context: string | null
  ): void {
    // Remove quotes from string values
    const cleanValue = typeof value === "string" ? value.replace(/^["']|["']$/g, "") : value;

    switch (key) {
      case "name":
        result.name = cleanValue as string;
        break;
      case "version":
        result.version = cleanValue as string;
        break;
      case "description":
        result.description = cleanValue as string;
        break;
      case "category":
        result.category = cleanValue as string;
        break;
      case "license":
        result.license = cleanValue as string;
        break;
      case "triggers":
        result.triggers = Array.isArray(cleanValue) ? cleanValue : [cleanValue];
        break;
      case "tags":
        result.tags = Array.isArray(cleanValue) ? cleanValue : [cleanValue];
        break;
      case "required_permissions":
        result.required_permissions = Array.isArray(cleanValue) ? cleanValue : [cleanValue];
        break;
    }
  }
}

