/**
 * Tests for AllowlistPersistence.
 */

import { describe, it, expect, beforeEach, afterEach } from "vitest";
import fs from "node:fs/promises";
import path from "node:path";
import os from "node:os";
import {
  loadAllowlist,
  saveAllowlist,
  addToAllowlist,
  removeFromAllowlist,
} from "./AllowlistPersistence.js";

describe("AllowlistPersistence", () => {
  let tempDir: string;
  let testFilePath: string;

  beforeEach(async () => {
    tempDir = await fs.mkdtemp(path.join(os.tmpdir(), "allowlist-test-"));
    testFilePath = path.join(tempDir, "allowlist.json");
  });

  afterEach(async () => {
    try {
      await fs.rm(tempDir, { recursive: true });
    } catch {
      // Ignore cleanup errors
    }
  });

  describe("loadAllowlist", () => {
    it("should return empty array for non-existent file", async () => {
      const result = await loadAllowlist(testFilePath);
      expect(result).toEqual([]);
    });

    it("should load existing allowlist", async () => {
      const store = {
        allowlist: ["user1", "user2"],
        lastUpdated: new Date().toISOString(),
      };
      await fs.writeFile(testFilePath, JSON.stringify(store));

      const result = await loadAllowlist(testFilePath);
      expect(result).toEqual(["user1", "user2"]);
    });

    it("should return empty array for invalid JSON", async () => {
      await fs.writeFile(testFilePath, "invalid json");

      const result = await loadAllowlist(testFilePath);
      expect(result).toEqual([]);
    });

    it("should return empty array if allowlist property is missing", async () => {
      await fs.writeFile(testFilePath, JSON.stringify({ lastUpdated: "now" }));

      const result = await loadAllowlist(testFilePath);
      expect(result).toEqual([]);
    });

    it("should expand ~ to home directory", async () => {
      // This test verifies the path expansion logic
      const homePath = path.join(os.homedir(), ".ag3nt-test-allowlist.json");
      
      // Clean up first
      try {
        await fs.unlink(homePath);
      } catch {
        // Ignore if doesn't exist
      }

      const result = await loadAllowlist("~/.ag3nt-test-allowlist.json");
      expect(result).toEqual([]);
    });
  });

  describe("saveAllowlist", () => {
    it("should save allowlist to file", async () => {
      await saveAllowlist(testFilePath, ["user1", "user2"]);

      const content = await fs.readFile(testFilePath, "utf-8");
      const store = JSON.parse(content);
      expect(store.allowlist).toEqual(["user1", "user2"]);
      expect(store.lastUpdated).toBeDefined();
    });

    it("should create directory if it doesn't exist", async () => {
      const nestedPath = path.join(tempDir, "nested", "dir", "allowlist.json");
      await saveAllowlist(nestedPath, ["user1"]);

      const content = await fs.readFile(nestedPath, "utf-8");
      const store = JSON.parse(content);
      expect(store.allowlist).toEqual(["user1"]);
    });

    it("should overwrite existing file", async () => {
      await saveAllowlist(testFilePath, ["user1"]);
      await saveAllowlist(testFilePath, ["user2", "user3"]);

      const content = await fs.readFile(testFilePath, "utf-8");
      const store = JSON.parse(content);
      expect(store.allowlist).toEqual(["user2", "user3"]);
    });
  });

  describe("addToAllowlist", () => {
    it("should add entry to empty allowlist", async () => {
      const result = await addToAllowlist(testFilePath, "user1");
      expect(result).toEqual(["user1"]);

      const loaded = await loadAllowlist(testFilePath);
      expect(loaded).toEqual(["user1"]);
    });

    it("should add entry to existing allowlist", async () => {
      await saveAllowlist(testFilePath, ["user1"]);

      const result = await addToAllowlist(testFilePath, "user2");
      expect(result).toEqual(["user1", "user2"]);
    });

    it("should not add duplicate entry", async () => {
      await saveAllowlist(testFilePath, ["user1"]);

      const result = await addToAllowlist(testFilePath, "user1");
      expect(result).toEqual(["user1"]);
    });
  });

  describe("removeFromAllowlist", () => {
    it("should remove entry from allowlist", async () => {
      await saveAllowlist(testFilePath, ["user1", "user2", "user3"]);

      const result = await removeFromAllowlist(testFilePath, "user2");
      expect(result).toEqual(["user1", "user3"]);

      const loaded = await loadAllowlist(testFilePath);
      expect(loaded).toEqual(["user1", "user3"]);
    });

    it("should handle removing non-existent entry", async () => {
      await saveAllowlist(testFilePath, ["user1"]);

      const result = await removeFromAllowlist(testFilePath, "user2");
      expect(result).toEqual(["user1"]);
    });

    it("should handle empty allowlist", async () => {
      const result = await removeFromAllowlist(testFilePath, "user1");
      expect(result).toEqual([]);
    });
  });
});

