import type { AgentStatusItem } from "../types/backend";

import { fallbackAgents } from "../components/AgentStatus";

export interface MentionCandidate {
  id: string;
  label: string;
  severity?: string;
}

const COMMANDER: MentionCandidate = { id: "commander", label: "Commander" };

export function mentionRoster(agents: AgentStatusItem[]): MentionCandidate[] {
  const roster = agents.length > 0 ? agents : fallbackAgents;
  return [
    COMMANDER,
    ...roster.map((agent) => ({
      id: agent.agent,
      label: agent.display_name,
      severity: agent.severity,
    })),
  ];
}

export function getActiveMentionQuery(
  text: string,
  cursor: number,
): { start: number; query: string } | null {
  const before = text.slice(0, cursor);
  const at = before.lastIndexOf("@");
  if (at === -1) {
    return null;
  }
  if (at > 0 && !/\s/.test(before[at - 1]!)) {
    return null;
  }
  const query = before.slice(at + 1);
  if (query.includes("\n")) {
    return null;
  }
  return { start: at, query };
}

export function filterMentionCandidates(
  candidates: MentionCandidate[],
  query: string,
): MentionCandidate[] {
  const q = query.trim().toLowerCase();
  if (!q) {
    return candidates;
  }
  return candidates.filter((candidate) => candidate.label.toLowerCase().includes(q));
}

export function insertMention(
  text: string,
  start: number,
  cursor: number,
  label: string,
): { next: string; nextCursor: number } {
  const before = text.slice(0, start);
  const after = text.slice(cursor);
  const mention = `@${label} `;
  const next = `${before}${mention}${after}`;
  return { next, nextCursor: before.length + mention.length };
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

export function resolveMentionInText(
  text: string,
  agents: AgentStatusItem[],
): AgentStatusItem | "commander" | null {
  const roster = agents.length > 0 ? agents : fallbackAgents;
  const labels = [...roster.map((a) => a.display_name)].sort((a, b) => b.length - a.length);

  for (const label of labels) {
    const pattern = new RegExp(`@${escapeRegExp(label)}(?=\\s|$|[.,!?])`, "i");
    if (pattern.test(text)) {
      return roster.find((a) => a.display_name.toLowerCase() === label.toLowerCase()) ?? null;
    }
  }

  if (/\b@commander\b/i.test(text)) {
    return "commander";
  }

  return null;
}

export function mentionLabels(agents: AgentStatusItem[]): string[] {
  return [...mentionRoster(agents).map((c) => c.label)];
}

export type MessagePart = { type: "text" | "mention"; value: string };

export function splitMessageParts(text: string, labels: string[]): MessagePart[] {
  if (!labels.length) {
    return [{ type: "text", value: text }];
  }

  const sorted = [...labels].sort((a, b) => b.length - a.length);
  const pattern = new RegExp(
    `@(?:${sorted.map((label) => escapeRegExp(label)).join("|")})`,
    "gi",
  );
  const parts: MessagePart[] = [];
  let last = 0;
  let match: RegExpExecArray | null;

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > last) {
      parts.push({ type: "text", value: text.slice(last, match.index) });
    }
    parts.push({ type: "mention", value: match[0] });
    last = match.index + match[0].length;
  }

  if (last < text.length) {
    parts.push({ type: "text", value: text.slice(last) });
  }

  return parts.length > 0 ? parts : [{ type: "text", value: text }];
}

export function stripMentions(text: string, labels: string[]): string {
  let next = text;
  for (const label of labels) {
    next = next.replace(new RegExp(`@${escapeRegExp(label)}`, "gi"), "");
  }
  return next.replace(/\s{2,}/g, " ").trim();
}
