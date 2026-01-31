#!/usr/bin/env npx ts-node
/**
 * AG3NT CLI - Simple command-line interface for chatting with the agent.
 *
 * Usage:
 *   pnpm cli                     # Start interactive chat
 *   pnpm cli "your message"      # Send single message and exit
 *
 * Environment:
 *   AG3NT_GATEWAY_URL  - Gateway URL (auto-detected or default: http://127.0.0.1:18789)
 *   AG3NT_SESSION_ID   - Session ID (default: auto-generated)
 */

import * as readline from "readline";
import * as fs from "fs";
import * as path from "path";
import * as os from "os";

const SESSION_ID = process.env.AG3NT_SESSION_ID || `cli-${Date.now()}`;

// Default ports to probe in order
const DEFAULT_PORTS = [18789, 18790, 18791, 18792, 18793];

/**
 * Discover the Gateway URL by:
 * 1. Checking AG3NT_GATEWAY_URL environment variable
 * 2. Reading from ~/.ag3nt/runtime.json (written by start.ps1)
 * 3. Probing default ports for a live Gateway
 */
async function discoverGatewayUrl(): Promise<string> {
  // 1. Environment variable takes precedence
  if (process.env.AG3NT_GATEWAY_URL) {
    return process.env.AG3NT_GATEWAY_URL;
  }

  // 2. Try to read from runtime.json
  const runtimePath = path.join(os.homedir(), ".ag3nt", "runtime.json");
  try {
    if (fs.existsSync(runtimePath)) {
      const content = fs.readFileSync(runtimePath, "utf-8");
      const runtime = JSON.parse(content);
      if (runtime.gatewayUrl) {
        // Verify the Gateway is actually responding
        try {
          const resp = await fetch(`${runtime.gatewayUrl}/api/health`, {
            signal: AbortSignal.timeout(2000),
          });
          if (resp.ok) {
            return runtime.gatewayUrl;
          }
        } catch {
          // Gateway from runtime.json is not responding, continue to probe
        }
      }
    }
  } catch {
    // Ignore errors reading runtime.json
  }

  // 3. Probe default ports
  for (const port of DEFAULT_PORTS) {
    const url = `http://127.0.0.1:${port}`;
    try {
      const resp = await fetch(`${url}/api/health`, {
        signal: AbortSignal.timeout(1000),
      });
      if (resp.ok) {
        return url;
      }
    } catch {
      // Port not responding, try next
    }
  }

  // Fallback to default
  return "http://127.0.0.1:18789";
}

let GATEWAY_URL = "http://127.0.0.1:18789"; // Will be updated by discoverGatewayUrl()

interface ChatResponse {
  ok: boolean;
  text?: string;
  error?: string;
  session_id?: string;
  events?: Array<Record<string, unknown>>;
}

async function sendMessage(text: string): Promise<ChatResponse> {
  const response = await fetch(`${GATEWAY_URL}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, session_id: SESSION_ID }),
  });

  return response.json() as Promise<ChatResponse>;
}

async function singleMessage(text: string): Promise<void> {
  try {
    const result = await sendMessage(text);
    if (result.ok) {
      console.log(result.text);
    } else {
      console.error("Error:", result.error);
      process.exit(1);
    }
  } catch (err) {
    console.error("Failed to connect:", err instanceof Error ? err.message : err);
    process.exit(1);
  }
}

async function interactiveChat(): Promise<void> {
  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout,
  });

  console.log("AG3NT CLI - Type your message and press Enter. Type 'exit' to quit.\n");
  console.log(`Session: ${SESSION_ID}`);
  console.log(`Gateway: ${GATEWAY_URL}\n`);

  const prompt = () => {
    rl.question("You: ", async (input) => {
      const text = input.trim();

      if (!text) {
        prompt();
        return;
      }

      if (text.toLowerCase() === "exit" || text.toLowerCase() === "quit") {
        console.log("Goodbye!");
        rl.close();
        return;
      }

      try {
        console.log("\nAG3NT: Thinking...");
        const result = await sendMessage(text);

        if (result.ok) {
          // Clear "Thinking..." and print response
          process.stdout.write("\x1b[1A\x1b[2K"); // Move up and clear line
          console.log(`AG3NT: ${result.text}\n`);
        } else {
          console.log(`Error: ${result.error}\n`);
        }
      } catch (err) {
        console.log(`Connection error: ${err instanceof Error ? err.message : err}\n`);
      }

      prompt();
    });
  };

  prompt();
}

async function main(): Promise<void> {
  // Auto-discover Gateway URL
  console.log("Discovering Gateway...");
  GATEWAY_URL = await discoverGatewayUrl();
  console.log(`Connected to: ${GATEWAY_URL}\n`);

  const args = process.argv.slice(2);

  if (args.length > 0) {
    // Single message mode
    await singleMessage(args.join(" "));
  } else {
    // Interactive mode
    await interactiveChat();
  }
}

main().catch(console.error);

