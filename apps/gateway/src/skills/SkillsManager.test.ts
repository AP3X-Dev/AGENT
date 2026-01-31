import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import * as fs from "node:fs";
import * as path from "node:path";
import * as os from "node:os";
import { SkillsManager, type SkillMetadata, type SkillSource } from "./SkillsManager.js";

// Mock fs module
vi.mock("node:fs");
vi.mock("node:os");

describe("SkillsManager", () => {
  // Use path.resolve to get platform-specific paths
  const mockBundledPath = path.resolve("/app/skills");
  const mockGlobalPath = path.join(path.resolve("/home/user"), ".ag3nt", "skills");
  const mockWorkspacePath = path.resolve("/project/.ag3nt/skills");

  const mockSkillMd = `---
name: test-skill
description: A test skill for unit testing
version: "1.0.0"
category: testing
tags:
  - test
  - unit
triggers:
  - "run test"
  - "execute test"
entrypoints:
  main:
    script: scripts/main.py
    description: Main entry point
required_permissions: []
license: MIT
metadata:
  author: test-author
  category: testing
---

# Test Skill

This is a test skill.
`;

  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(os.homedir).mockReturnValue(path.resolve("/home/user"));
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe("Constructor", () => {
    it("should accept legacy string path", () => {
      vi.mocked(fs.existsSync).mockReturnValue(false);
      const manager = new SkillsManager(mockBundledPath);
      expect(manager).toBeDefined();
    });

    it("should accept config object", () => {
      vi.mocked(fs.existsSync).mockReturnValue(false);
      const manager = new SkillsManager({
        bundledPath: mockBundledPath,
        globalPath: mockGlobalPath,
        workspacePath: mockWorkspacePath,
      });
      expect(manager).toBeDefined();
    });

    it("should use default global path when not provided", () => {
      vi.mocked(fs.existsSync).mockReturnValue(false);
      const manager = new SkillsManager({ bundledPath: mockBundledPath });
      expect(manager).toBeDefined();
    });
  });

  describe("getAllSkills", () => {
    it("should return empty array when no skills directories exist", async () => {
      vi.mocked(fs.existsSync).mockReturnValue(false);
      const manager = new SkillsManager(mockBundledPath);
      const skills = await manager.getAllSkills();
      expect(skills).toEqual([]);
    });

    it("should load skills from bundled path", async () => {
      vi.mocked(fs.existsSync).mockImplementation((p: fs.PathLike) => {
        const pathStr = path.normalize(p.toString());
        if (pathStr === mockBundledPath) return true;
        if (pathStr.includes("test-skill") && pathStr.includes("SKILL.md")) return true;
        return false;
      });

      vi.mocked(fs.readdirSync).mockImplementation((p: fs.PathLike) => {
        if (path.normalize(p.toString()) === mockBundledPath) {
          return [{ name: "test-skill", isDirectory: () => true }] as unknown as fs.Dirent[];
        }
        return [];
      });

      vi.mocked(fs.readFileSync).mockReturnValue(mockSkillMd);

      const manager = new SkillsManager(mockBundledPath);
      const skills = await manager.getAllSkills();

      expect(skills).toHaveLength(1);
      expect(skills[0].id).toBe("test-skill");
      expect(skills[0].name).toBe("test-skill");
      expect(skills[0].source).toBe("bundled");
      expect(skills[0].category).toBe("testing");
    });

    it("should override bundled skills with workspace skills", async () => {
      const bundledSkillMd = mockSkillMd.replace("name: test-skill", "name: bundled-version");
      const workspaceSkillMd = mockSkillMd.replace("name: test-skill", "name: workspace-version");

      vi.mocked(fs.existsSync).mockImplementation((p: fs.PathLike) => {
        const pathStr = path.normalize(p.toString());
        if (pathStr === mockBundledPath || pathStr === mockWorkspacePath) return true;
        if (pathStr.includes("test-skill") && pathStr.includes("SKILL.md")) return true;
        return false;
      });

      vi.mocked(fs.readdirSync).mockImplementation((p: fs.PathLike) => {
        const pathStr = path.normalize(p.toString());
        if (pathStr === mockBundledPath || pathStr === mockWorkspacePath) {
          return [{ name: "test-skill", isDirectory: () => true }] as unknown as fs.Dirent[];
        }
        return [];
      });

      vi.mocked(fs.readFileSync).mockImplementation((p: fs.PathOrFileDescriptor) => {
        const pathStr = path.normalize(p.toString());
        // Check for workspace path (contains "project")
        if (pathStr.includes("project")) return workspaceSkillMd;
        return bundledSkillMd;
      });

      // Pass explicit path that doesn't exist for global
      const manager = new SkillsManager({
        bundledPath: mockBundledPath,
        globalPath: "/nonexistent/global/skills",
        workspacePath: mockWorkspacePath,
      });
      const skills = await manager.getAllSkills();

      expect(skills).toHaveLength(1);
      expect(skills[0].name).toBe("workspace-version");
      expect(skills[0].source).toBe("workspace");
    });

    it("should skip non-directory entries", async () => {
      vi.mocked(fs.existsSync).mockImplementation((p: fs.PathLike) => {
        if (path.normalize(p.toString()) === mockBundledPath) return true;
        return false;
      });

      vi.mocked(fs.readdirSync).mockReturnValue([
        { name: "file.txt", isDirectory: () => false },
        { name: ".gitignore", isDirectory: () => false },
      ] as unknown as fs.Dirent[]);

      const manager = new SkillsManager(mockBundledPath);
      const skills = await manager.getAllSkills();

      expect(skills).toEqual([]);
    });

    it("should skip directories without SKILL.md", async () => {
      vi.mocked(fs.existsSync).mockImplementation((p: fs.PathLike) => {
        if (path.normalize(p.toString()) === mockBundledPath) return true;
        return false;
      });

      vi.mocked(fs.readdirSync).mockReturnValue([
        { name: "incomplete-skill", isDirectory: () => true },
      ] as unknown as fs.Dirent[]);

      const manager = new SkillsManager(mockBundledPath);
      const skills = await manager.getAllSkills();

      expect(skills).toEqual([]);
    });
  });

  describe("getSkill", () => {
    it("should return skill from bundled path", async () => {
      vi.mocked(fs.existsSync).mockImplementation((p: fs.PathLike) => {
        const pathStr = p.toString();
        // Only match bundled path (contains "app/skills")
        if (pathStr.includes("app") && pathStr.includes("test-skill") && pathStr.includes("SKILL.md")) return true;
        return false;
      });
      vi.mocked(fs.readFileSync).mockReturnValue(mockSkillMd);

      // Use config with explicit non-existent global path
      const manager = new SkillsManager({
        bundledPath: mockBundledPath,
        globalPath: "/nonexistent/global/skills",
      });
      const skill = await manager.getSkill("test-skill");

      expect(skill).toBeDefined();
      expect(skill?.id).toBe("test-skill");
      expect(skill?.source).toBe("bundled");
    });

    it("should prefer workspace skill over bundled", async () => {
      vi.mocked(fs.existsSync).mockImplementation((p: fs.PathLike) => {
        const pathStr = path.normalize(p.toString());
        // Workspace path check first
        if (pathStr.includes("project") && pathStr.includes("test-skill") && pathStr.includes("SKILL.md")) return true;
        return false;
      });
      vi.mocked(fs.readFileSync).mockReturnValue(mockSkillMd);

      const manager = new SkillsManager({
        bundledPath: mockBundledPath,
        workspacePath: mockWorkspacePath,
      });
      const skill = await manager.getSkill("test-skill");

      expect(skill?.source).toBe("workspace");
    });

    it("should return null for non-existent skill", async () => {
      vi.mocked(fs.existsSync).mockReturnValue(false);

      const manager = new SkillsManager(mockBundledPath);
      const skill = await manager.getSkill("non-existent");

      expect(skill).toBeNull();
    });
  });

  describe("getSkillContent", () => {
    it("should return skill content from highest priority path", async () => {
      vi.mocked(fs.existsSync).mockImplementation((p: fs.PathLike) => {
        const pathStr = path.normalize(p.toString());
        // Match workspace path for test-skill
        if (pathStr.includes("project") && pathStr.includes("test-skill") && pathStr.includes("SKILL.md")) return true;
        return false;
      });
      vi.mocked(fs.readFileSync).mockReturnValue(mockSkillMd);

      const manager = new SkillsManager({
        bundledPath: mockBundledPath,
        workspacePath: mockWorkspacePath,
      });
      const content = await manager.getSkillContent("test-skill");

      expect(content).toBe(mockSkillMd);
    });

    it("should return null for non-existent skill", async () => {
      vi.mocked(fs.existsSync).mockReturnValue(false);

      const manager = new SkillsManager(mockBundledPath);
      const content = await manager.getSkillContent("non-existent");

      expect(content).toBeNull();
    });
  });

  describe("getCategories", () => {
    it("should return unique categories sorted", async () => {
      const skillMd1 = mockSkillMd.replace("category: testing", "category: utilities");
      const skillMd2 = mockSkillMd;

      vi.mocked(fs.existsSync).mockImplementation((p: fs.PathLike) => {
        const pathStr = path.normalize(p.toString());
        if (pathStr === mockBundledPath) return true;
        if (pathStr.includes("SKILL.md")) return true;
        return false;
      });

      vi.mocked(fs.readdirSync).mockReturnValue([
        { name: "skill-1", isDirectory: () => true },
        { name: "skill-2", isDirectory: () => true },
      ] as unknown as fs.Dirent[]);

      let callCount = 0;
      vi.mocked(fs.readFileSync).mockImplementation(() => {
        return callCount++ % 2 === 0 ? skillMd1 : skillMd2;
      });

      const manager = new SkillsManager(mockBundledPath);
      const categories = await manager.getCategories();

      expect(categories).toContain("utilities");
      expect(categories).toContain("testing");
      expect(categories).toEqual([...categories].sort());
    });
  });

  describe("toggleSkill", () => {
    it("should disable skill", async () => {
      vi.mocked(fs.existsSync).mockReturnValue(true);
      vi.mocked(fs.readdirSync).mockReturnValue([
        { name: "test-skill", isDirectory: () => true },
      ] as unknown as fs.Dirent[]);
      vi.mocked(fs.readFileSync).mockReturnValue(mockSkillMd);

      const manager = new SkillsManager(mockBundledPath);
      manager.toggleSkill("test-skill", false);

      expect(manager.isEnabled("test-skill")).toBe(false);
    });

    it("should enable skill", async () => {
      vi.mocked(fs.existsSync).mockReturnValue(true);

      const manager = new SkillsManager(mockBundledPath);
      manager.toggleSkill("test-skill", false);
      manager.toggleSkill("test-skill", true);

      expect(manager.isEnabled("test-skill")).toBe(true);
    });
  });

  describe("parseSkillMd", () => {
    it("should extract all metadata fields", async () => {
      vi.mocked(fs.existsSync).mockImplementation((p: fs.PathLike) => {
        const pathStr = path.normalize(p.toString());
        if (pathStr === mockBundledPath) return true;
        if (pathStr.includes("SKILL.md")) return true;
        return false;
      });

      vi.mocked(fs.readdirSync).mockReturnValue([
        { name: "test-skill", isDirectory: () => true },
      ] as unknown as fs.Dirent[]);

      vi.mocked(fs.readFileSync).mockReturnValue(mockSkillMd);

      const manager = new SkillsManager(mockBundledPath);
      const skills = await manager.getAllSkills();

      expect(skills).toHaveLength(1);
      const skill = skills[0];

      expect(skill.name).toBe("test-skill");
      expect(skill.version).toBe("1.0.0");
      expect(skill.description).toBe("A test skill for unit testing");
      expect(skill.category).toBe("testing");
      expect(skill.tags).toContain("test");
      expect(skill.tags).toContain("unit");
      expect(skill.triggers).toContain("run test");
      expect(skill.license).toBe("MIT");
      expect(skill.author).toBe("test-author");
      expect(skill.source).toBe("bundled");
    });

    it("should handle missing frontmatter", async () => {
      vi.mocked(fs.existsSync).mockImplementation((p: fs.PathLike) => {
        const pathStr = path.normalize(p.toString());
        if (pathStr === mockBundledPath) return true;
        if (pathStr.includes("SKILL.md")) return true;
        return false;
      });

      vi.mocked(fs.readdirSync).mockReturnValue([
        { name: "minimal-skill", isDirectory: () => true },
      ] as unknown as fs.Dirent[]);

      vi.mocked(fs.readFileSync).mockReturnValue("# Just a markdown file\nNo frontmatter here.");

      const manager = new SkillsManager(mockBundledPath);
      const skills = await manager.getAllSkills();

      expect(skills).toHaveLength(1);
      const skill = skills[0];

      expect(skill.id).toBe("minimal-skill");
      expect(skill.name).toBe("minimal-skill");
      expect(skill.version).toBe("1.0.0");
      expect(skill.category).toBe("general");
      expect(skill.triggers).toEqual([]);
      expect(skill.tags).toEqual([]);
    });
  });
});

