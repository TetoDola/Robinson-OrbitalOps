import type { AgentStatusItem } from "../types/backend";
import { FLEET, FLEET_QUEUE, HEALTH_LABEL, type FleetAsset } from "../fleet/fleetData";
import { fallbackAgents } from "../components/AgentStatus";
import { resolveMentionInText, stripMentions, mentionLabels } from "./chatMentions";
import type { TelemetrySnapshot } from "../store/worldStore";

export type ChatRole = "user" | "agent" | "system";

export type EvidenceId = "node-c-ir" | "ckpt-lineage" | "downlink-window";

export type ChatBlock =
  | { kind: "text"; value: string }
  | { kind: "evidence"; id: EvidenceId; label: string };

export interface ChatMessage {
  id: string;
  role: ChatRole;
  author?: string;
  /** Plain text for user messages. */
  text?: string;
  /** Rich blocks for agent messages (text + clickable evidence). */
  blocks?: ChatBlock[];
  /** Inline mission patch card. */
  patchId?: string;
  /** Stagger delay before showing this message in the deliberation thread. */
  delayMs?: number;
}

export type PatchDecision = "pending" | "approved" | "rejected";

function t(value: string): ChatBlock {
  return { kind: "text", value };
}

function ev(id: EvidenceId, label: string): ChatBlock {
  return { kind: "evidence", id, label };
}

function assetContext(asset: FleetAsset): string {
  const eclipse = asset.eclipseMin != null ? `${asset.eclipseMin} min` : "none imminent";
  return `${asset.id} · ${HEALTH_LABEL[asset.health]} · ${asset.gpu} GPU · battery ${asset.battery}% · eclipse ${eclipse}. ${asset.note}.`;
}

function agentLine(agent: AgentStatusItem, asset: FleetAsset): string {
  const base = agent.message;
  if (asset.health === "nominal") {
    return `${asset.id} is nominal from my lane — ${base.replace(/AKJA-\d+/g, asset.id)}`;
  }
  if (asset.id === "AKJA-03") return base;
  return `On ${asset.id}: ${base}`;
}

function blocksFromText(text: string): ChatBlock[] {
  return [t(text)];
}

/** AKJA-03 supervised loop — agents converge sequentially, patch at the end. */
function buildAkja03Deliberation(telemetry: TelemetrySnapshot): ChatMessage[] {
  return [
    {
      id: "u-open",
      role: "user",
      text: `Agent briefing for AKJA-03 — what are you seeing across the datacenter?`,
      delayMs: 0,
    },
    {
      id: "a-thermal",
      role: "agent",
      author: "Thermal Agent",
      delayMs: 500,
      blocks: [
        t("Reporting first — "),
        ev("node-c-ir", "Node C"),
        t(" hotspot confirmed by IR-01 at 96.4°C while idle. Rack telemetry agrees; no workload assigned."),
      ],
    },
    {
      id: "a-integrity",
      role: "agent",
      author: "Integrity Agent",
      delayMs: 1200,
      blocks: [
        t("Cross-checking checkpoints — "),
        ev("ckpt-lineage", "ckpt-184900"),
        t(" is suspect after ECC spike on Node B GPU 3 and NaN loss. Rollback target: ckpt-184500."),
      ],
    },
    {
      id: "a-power",
      role: "agent",
      author: "Power / Orbit Agent",
      delayMs: 1000,
      blocks: [
        t("Eclipse in 6.1 min, battery reserve at 31%. Any patch must complete before umbra or we shed compute."),
      ],
    },
    {
      id: "a-downlink",
      role: "agent",
      author: "Downlink Agent",
      delayMs: 900,
      blocks: [
        t("Ground window constraint — "),
        ev("downlink-window", "18/180 GB"),
        t(" fits in the next pass. Full checkpoint cannot ship; delta + manifest only."),
      ],
    },
    {
      id: "a-commander",
      role: "agent",
      author: "Commander",
      delayMs: 1100,
      blocks: [
        t(
          `Five agents converged on AKJA-03. Ground link ${telemetry.groundLink}, orbit ${telemetry.orbitPhase}, patch confidence ${telemetry.patchConfidence}. Mission Patch assembled — human approval required.`,
        ),
      ],
      patchId: "patch-042",
    },
  ];
}

function buildNominalBriefing(assetId: string, asset: FleetAsset): ChatMessage[] {
  return [
    {
      id: "u-open",
      role: "user",
      text: `Agent briefing for ${assetId} — what are you seeing across the datacenter?`,
      delayMs: 0,
    },
    {
      id: "a-commander",
      role: "agent",
      author: "Commander",
      delayMs: 400,
      blocks: [t(`Monitoring ${assetContext(asset)} No mission patch queued — standing by for cross-asset migration if fleet capacity allows.`)],
    },
  ];
}

function buildGenericDeliberation(
  assetId: string,
  asset: FleetAsset,
  roster: AgentStatusItem[],
): ChatMessage[] {
  const relevant = roster.filter((a) => a.severity.includes("RED") || a.severity.includes("ORANGE")).slice(0, 2);
  const agents = relevant.length > 0 ? relevant : roster.slice(0, 2);

  const messages: ChatMessage[] = [
    {
      id: "u-open",
      role: "user",
      text: `Agent briefing for ${assetId} — what are you seeing across the datacenter?`,
      delayMs: 0,
    },
  ];

  agents.forEach((agent, i) => {
    messages.push({
      id: `a-${agent.agent}-${i}`,
      role: "agent",
      author: agent.display_name,
      delayMs: 700 + i * 900,
      blocks: blocksFromText(agentLine(agent, asset)),
    });
  });

  const queuedPatch = FLEET_QUEUE.find((p) => p.asset === assetId);
  messages.push({
    id: "a-commander",
    role: "agent",
    author: "Commander",
    delayMs: 900,
    blocks: [
      t(
        queuedPatch
          ? `${agents.length} agents reported on ${assetId}. ${queuedPatch.detail}`
          : `Agents remain in ${roster.map((a) => a.phase).join(", ")} phases on ${assetId}.`,
      ),
    ],
    patchId: queuedPatch?.id,
  });

  return messages;
}

/** Opening briefing — staggered multi-agent deliberation thread. */
export function buildAgentBriefing(
  assetId: string,
  agents: AgentStatusItem[],
  telemetry: TelemetrySnapshot,
): ChatMessage[] {
  if (assetId === "AKJA-03") {
    return buildAkja03Deliberation(telemetry);
  }

  const asset = FLEET.find((a) => a.id === assetId) ?? FLEET[0];
  const roster = agents.length > 0 ? agents : fallbackAgents;

  if (asset.health === "nominal") {
    return buildNominalBriefing(assetId, asset);
  }

  return buildGenericDeliberation(assetId, asset, roster);
}

export const SUGGESTION_CHIPS = [
  "Which agent is most critical?",
  "Explain the eclipse window",
  "What would you propose?",
  "Open full ops console",
] as const;

export function systemMessage(text: string): ChatMessage {
  return { id: `sys-${Date.now()}`, role: "system", text };
}

export function mockAgentReply(
  query: string,
  assetId: string,
  agents: AgentStatusItem[],
): ChatMessage {
  const roster = agents.length > 0 ? agents : fallbackAgents;
  const mentioned = resolveMentionInText(query, roster);
  const labels = mentionLabels(roster);
  const q = query.toLowerCase();

  if (mentioned && mentioned !== "commander") {
    const asset = FLEET.find((a) => a.id === assetId) ?? FLEET[0];
    const topic = stripMentions(query, labels).replace(/\?$/, "").trim();
    const report = agentLine(mentioned, asset);
    const blocks: ChatBlock[] = [t(report)];
    if (mentioned.agent.includes("thermal") && assetId === "AKJA-03") {
      blocks.unshift(t("Focused response — "), ev("node-c-ir", "Node C"), t(": "));
    }
    if (mentioned.agent.includes("integrity") && assetId === "AKJA-03") {
      blocks.unshift(t("Focused response — "), ev("ckpt-lineage", "ckpt-184900"), t(": "));
    }
    if (topic.length > 2) {
      blocks.push(t(` (re: ${topic})`));
    }
    return {
      id: `a-${Date.now()}`,
      role: "agent",
      author: mentioned.display_name,
      blocks,
    };
  }

  if (mentioned === "commander" || q.includes("propose") || q.includes("patch")) {
    const queuedPatch = FLEET_QUEUE.find((p) => p.asset === assetId);
    if (queuedPatch) {
      return {
        id: `a-${Date.now()}`,
        role: "agent",
        author: "Commander",
        blocks: [t(`${queuedPatch.detail} Human approval required before execution.`)],
        patchId: queuedPatch.id,
      };
    }
    return {
      id: `a-${Date.now()}`,
      role: "agent",
      author: "Commander",
      blocks: [t(`No active patch for ${assetId}. I can draft a capacity or migration proposal if you authorize fleet-level action.`)],
    };
  }

  if (q.includes("console") || q.includes("ops")) {
    return {
      id: `a-${Date.now()}`,
      role: "agent",
      author: "Commander",
      blocks: [t(`Opening the full ops-loop console for ${assetId} — you'll get the 3D node view, vitals strip, and patch approval drawer.`)],
    };
  }

  if (q.includes("critical") || q.includes("severe")) {
    const worst = [...roster].sort((a, b) => {
      const rank = (s: string) => (s.includes("RED") ? 0 : s.includes("ORANGE") ? 1 : 2);
      return rank(a.severity) - rank(b.severity);
    })[0]!;
    return {
      id: `a-${Date.now()}`,
      role: "agent",
      author: worst.display_name,
      blocks: [t(`Highest severity on ${assetId}: ${worst.message} (${worst.severity}). Phase: ${worst.phase}.`)],
    };
  }

  if (q.includes("eclipse")) {
    const power = roster.find((a) => a.agent.includes("power")) ?? roster[0]!;
    return {
      id: `a-${Date.now()}`,
      role: "agent",
      author: power.display_name,
      blocks: [
        t(
          power.message.includes("Eclipse")
            ? power.message
            : `Eclipse recovery planning for ${assetId} — battery reserve and compute shed must be coordinated before umbra.`,
        ),
      ],
    };
  }

  return {
    id: `a-${Date.now()}`,
    role: "agent",
    author: "Commander",
    blocks: [
      t(`On ${assetId}: agents remain in ${roster.map((a) => a.phase).join(", ")} phases. Ask about eclipse, critical severity, or open the ops console for live control.`),
    ],
  };
}

export function patchForAsset(assetId: string) {
  return FLEET_QUEUE.find((p) => p.asset === assetId) ?? null;
}
