import fs from "node:fs/promises";
import path from "node:path";
import os from "node:os";
import YAML from "yaml";
import { ConfigSchema, type Config } from "./schema.js";

function expandHome(p: string): string {
  if (p.startsWith("~/")) return path.join(os.homedir(), p.slice(2));
  return p;
}

async function readYamlIfExists(filePath: string): Promise<Record<string, unknown>> {
  try {
    const text = await fs.readFile(filePath, "utf8");
    return YAML.parse(text) ?? {};
  } catch {
    return {};
  }
}

export async function loadConfig(): Promise<Config> {
  const defaultPath = path.resolve(process.cwd(), "../../config/default-config.yaml");
  const userPath = expandHome("~/.ag3nt/config.yaml");

  const base = await readYamlIfExists(defaultPath);
  const user = await readYamlIfExists(userPath);

  const merged = { ...base, ...user };
  const parsed = ConfigSchema.safeParse(merged);
  if (!parsed.success) {
    const message = parsed.error.issues.map((i) => `${i.path.join(".")}: ${i.message}`).join("\n");
    throw new Error(`Invalid config\n${message}`);
  }
  return parsed.data;
}
