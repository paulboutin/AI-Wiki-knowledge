/**
 * OpenCode Knowledge Base Plugin
 *
 * Hooks AI-Wiki-knowledge into OpenCode sessions:
 * - session.start: Injects knowledge base context
 * - session.stopping: Captures transcript for memory extraction
 * - tool.execute.after: Fallback for session end detection
 *
 * Auto-discovered from .opencode/plugins/ directory.
 * No config file needed.
 */

import type { Plugin } from "@opencode-ai/plugin";
import { spawn } from "child_process";
import { join, dirname } from "path";
import { fileURLToPath } from "url";
import fs from "fs";
import os from "os";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, "..", "..");
const HOOKS_DIR = join(ROOT, "hooks", "opencode");
const SCRIPTS_DIR = join(ROOT, "scripts");
const LAST_FLUSH_FILE = join(SCRIPTS_DIR, "last-flush.json");

// Timeout constants (ms)
const SESSION_START_TIMEOUT = 10_000;
const SESSION_STOP_TIMEOUT = 30_000;

// Transcript storage locations
function getTranscriptDir(): string {
  const home = os.homedir();
  return join(home, ".local", "share", "opencode");
}

/**
 * Spawn a Python hook script with timeout protection.
 * Returns stdout as string, or null on failure/timeout.
 */
function spawnPython(
  script: string,
  args: string[] = [],
  timeout: number
): Promise<string | null> {
  return new Promise((resolve) => {
    const child = spawn("uv", ["run", "python", script, ...args], {
      cwd: ROOT,
      timeout,
      env: { ...process.env },
    });

    let stdout = "";
    let stderr = "";

    child.stdout?.on("data", (data) => {
      stdout += data.toString();
    });

    child.stderr?.on("data", (data) => {
      stderr += data.toString();
    });

    child.on("error", (err) => {
      console.error(`[knowledge-base] Failed to spawn ${script}:`, err.message);
      resolve(null);
    });

    child.on("exit", (code) => {
      if (code === 0) {
        resolve(stdout.trim());
      } else {
        console.error(
          `[knowledge-base] ${script} exited with code ${code}:`,
          stderr.trim()
        );
        resolve(null);
      }
    });

    child.on("timeout", () => {
      child.kill();
      console.error(`[knowledge-base] ${script} timed out after ${timeout}ms`);
      resolve(null);
    });
  });
}

/**
 * Spawn a detached background process (survives after plugin exits).
 */
function spawnDetached(script: string, args: string[] = []): void {
  const child = spawn("uv", ["run", "python", script, ...args], {
    cwd: ROOT,
    detached: true,
    stdio: "ignore",
    env: { ...process.env, CLAUDE_INVOKED_BY: "memory_flush" },
  });

  child.unref();
}

/**
 * Check if a session has already been flushed (deduplication).
 */
function isSessionFlushed(sessionId: string): boolean {
  try {
    if (!fs.existsSync(LAST_FLUSH_FILE)) return false;
    const data = JSON.parse(fs.readFileSync(LAST_FLUSH_FILE, "utf-8"));
    return !!data[sessionId];
  } catch {
    return false;
  }
}

/**
 * Find the transcript file for a given session ID.
 */
function findTranscript(sessionId: string): string | null {
  const transcriptDir = getTranscriptDir();

  // Direct pattern: {sessionID}.jsonl
  const direct = join(transcriptDir, `${sessionId}.jsonl`);
  if (fs.existsSync(direct)) return direct;

  // Project-specific: <project-slug>/storage/{sessionID}.jsonl
  try {
    const entries = fs.readdirSync(transcriptDir, { withFileTypes: true });
    for (const entry of entries) {
      if (entry.isDirectory()) {
        const storage = join(transcriptDir, entry.name, "storage", `${sessionId}.jsonl`);
        if (fs.existsSync(storage)) return storage;
      }
    }
  } catch {
    // Ignore readdir errors
  }

  // Global: global/storage/{sessionID}.jsonl
  const globalStorage = join(transcriptDir, "global", "storage", `${sessionId}.jsonl`);
  if (fs.existsSync(globalStorage)) return globalStorage;

  return null;
}

export const knowledgeBase: Plugin = async ({ $ }) => {
  return {
    session: {
      start: {
        before: async (input) => {
          // Inject knowledge base context at session start
          const script = join(HOOKS_DIR, "session-start.py");

          try {
            const result = await spawnPython(script, [], SESSION_START_TIMEOUT);

            if (!result) {
              return input;
            }

            try {
              const parsed = JSON.parse(result);
              const context = parsed.additionalContext || parsed.hookSpecificOutput?.additionalContext;

              if (context) {
                console.log("[knowledge-base] Injected knowledge base context");
                return {
                  ...input,
                  additionalInstructions: `
# Knowledge Base Context

${context}

Use this context to inform your responses. This is your accumulated knowledge from previous sessions.
`.trim(),
                };
              }
            } catch (parseError) {
              console.error("[knowledge-base] Failed to parse session-start output:", parseError);
            }
          } catch (err) {
            console.error("[knowledge-base] session.start hook failed:", err);
          }

          return input;
        },
      },
      stopping: {
        before: async (input) => {
          // Capture transcript for memory extraction
          const sessionId = input.sessionId || input.session_id;

          if (!sessionId) {
            console.error("[knowledge-base] No session ID in stopping hook");
            return input;
          }

          const transcriptPath = findTranscript(sessionId);

          if (!transcriptPath) {
            console.log("[knowledge-base] No transcript found for session:", sessionId);
            return input;
          }

          console.log("[knowledge-base] Starting memory extraction for session:", sessionId);

          // Spawn stop.py as detached background process
          const script = join(HOOKS_DIR, "stop.py");
          spawnDetached(script, [sessionId]);

          return input;
        },
      },
    },
    tool: {
      execute: {
        after: async (input, output) => {
          // Fallback: detect session end patterns when session.stopping isn't available
          const sessionId = input.sessionId || input.session_id;

          if (!sessionId) {
            return output;
          }

          // Skip if already flushed
          if (isSessionFlushed(sessionId)) {
            return output;
          }

          // Detect session-ending patterns
          const toolName = input.tool?.toLowerCase() || "";
          const isSessionEnd =
            toolName === "exit" ||
            toolName === "quit" ||
            toolName === "end_session" ||
            toolName === "close";

          if (!isSessionEnd) {
            return output;
          }

          const transcriptPath = findTranscript(sessionId);

          if (!transcriptPath) {
            return output;
          }

          console.log("[knowledge-base] Fallback: capturing session end via tool.execute.after");

          const script = join(HOOKS_DIR, "stop.py");
          spawnDetached(script, [sessionId]);

          return output;
        },
      },
    },
  };
};
