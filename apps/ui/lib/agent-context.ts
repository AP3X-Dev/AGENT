import type { AssembledContext, TabContextSummary } from "@/types/tab-context";

function clip(text: string, max: number) {
  if (text.length <= max) return text;
  return text.slice(0, max) + "\n\n[truncated]";
}

function formatSummary(summary: TabContextSummary) {
  const head = `${summary.moduleType || "tab"}: ${summary.title}`;
  const parts = [summary.summary.description];

  if (summary.summary.keyPoints && summary.summary.keyPoints.length > 0) {
    parts.push(
      "Key points:\n" +
        summary.summary.keyPoints.map((k) => `- ${k}`).join("\n"),
    );
  }

  return `## ${head}\n${parts.filter(Boolean).join("\n\n")}`;
}

/**
 * Convert assembled tab context into a compact prompt block.
 *
 * Policy:
 * - Always include active tab summary (not full JSON)
 * - Include pinned tabs (as background summaries)
 * - Keep it small; the agent can request more via tools later
 */
export function buildAgentContext(
  assembled: AssembledContext,
  maxChars = 6000,
) {
  const active = assembled.activeTab;
  const activeModule = active?.tab.moduleType || "tab";
  const activeTitle = active?.tab.title || "Active";

  const activeSummary = active
    ? `## active: ${activeModule}: ${activeTitle}\n${active.summary?.description || ""}`
    : "";

  const background = assembled.backgroundTabs.map(formatSummary).join("\n\n");

  const block = ["# UI Context", activeSummary, background]
    .filter(Boolean)
    .join("\n\n");
  return clip(block, maxChars);
}
