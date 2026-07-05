import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { approveMissionPatch, rejectMissionPatch } from "../api/client";
import { runHardwareToolCalls } from "../services/localTools";
import { useWorldStore, type AgentLogItem } from "../store/worldStore";
import type {
  AgentFinding,
  AgentRuntimeItem,
  AgentStatusItem,
  Command,
  Incident,
  MissionPatch,
  MissionPatchAction,
  NodeState,
  ProcessedRadiationRisk,
  ThermalVisualInput,
  WorldState,
} from "../types/backend";
import { CoolingTrendPanel } from "./SimulationControls";

type Tone = "nominal" | "warn" | "critical";

interface SignalRow {
  label: string;
  value: string;
  limit?: string;
  tone?: Tone;
}

interface PatchEvidenceItem {
  agent?: string;
  finding?: string;
  severity?: string;
  confidence?: number;
  affected_assets?: string[];
  evidence?: string[];
  risk?: string | null;
  recommended_actions?: string[];
}

type FlowStatus = "pending" | "running" | "complete" | "blocked";

interface AgentFlowNode {
  key: string;
  label: string;
  sub?: string;
  status: FlowStatus;
  lines: string[];
  image?: string | null;
}

// Shown only when the backend is unreachable. Must read as degraded, never
// as healthy monitoring, so an outage cannot masquerade as a green fleet.
const fallbackAgents: AgentStatusItem[] = [
  "workload_agent",
  "thermal_physical_agent",
  "power_orbit_agent",
  "radiation_integrity_agent",
  "checkpoint_downlink_agent",
  "vibration_health_agent",
].map((agent) => ({
  agent,
  display_name: agent
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" "),
  status: "offline",
  phase: "offline",
  severity: "RED",
  message: "Live agent status unavailable — backend not reachable.",
}));

const detectorScope: Record<string, string> = {
  workload_agent: "Scheduler truth, GPU utilization, rank lag, worker progress, orphan process evidence.",
  thermal_physical_agent: "Rack temperature, node hotspot, IR inspection result, cooling state, contact vibration.",
  power_orbit_agent: "Battery state, solar input, orbit phase, eclipse countdown, compute and cooling load.",
  radiation_integrity_agent: "ECC trend, Xid events, checkpoint trust, NaN loss, rank divergence evidence.",
  checkpoint_downlink_agent: "Checkpoint size, transfer priority, contact window, downlink capacity, ground recovery artifacts.",
  vibration_health_agent: "Structure-borne contact sensor trend, frequency shift, thermal correlation, cooling-loop risk.",
  commander_agent: "Open findings, affected assets, safety validator output, patch status, approval boundary.",
};

function workStateClass(agent: AgentStatusItem, missionPatchStatus?: string | null): string {
  const value = `${agent.status} ${agent.phase}`.toLowerCase();
  if (value.includes("offline")) return "status-red";
  if (agent.agent === "commander_agent" && missionPatchStatus === "verified") return "status-green";
  if (agent.agent === "commander_agent" && missionPatchStatus === "rejected") return "status-red";
  if (agent.agent === "commander_agent" && isActivePatchStatus(missionPatchStatus)) return "status-orange";
  if (value.includes("monitor") || value.includes("healthy")) return "status-green";
  if (value.includes("analy") || value.includes("detect") || value.includes("running")) return "status-cyan";
  if (value.includes("included") || value.includes("handoff")) return "status-orange";
  if (value.includes("propos") || value.includes("planning") || value.includes("approval")) return "status-orange";
  if (value.includes("blocked") || value.includes("failed")) return "status-red";
  return "status-cyan";
}

function workStateLabel(agent: AgentStatusItem, missionPatchStatus?: string | null): string {
  if (agent.agent === "commander_agent" && missionPatchStatus === "pending_approval") return "awaiting approval";
  if (agent.agent === "commander_agent" && missionPatchStatus === "approved") return "approved";
  if (agent.agent === "commander_agent" && missionPatchStatus === "executing") return "executing";
  if (agent.agent === "commander_agent" && missionPatchStatus === "verified") return "verified";
  if (agent.agent === "commander_agent" && missionPatchStatus === "rejected") return "rejected";
  const value = agent.status || agent.phase;
  if (value === "healthy" || value === "scheduled") return "monitoring";
  return humanize(value);
}

function isActivePatchStatus(status: string | null | undefined): boolean {
  return ["pending_approval", "approved", "executing"].includes(status ?? "");
}

// A status row can lag the patch decision (heartbeats re-emit the last row
// until the next poll). Never display "awaiting approval" unless a patch is
// actually pending — reconcile every agent against the live patch state.
function reconcileAgent(agent: AgentStatusItem, missionPatch: MissionPatch | null): AgentStatusItem {
  if (agent.agent !== "commander_agent" && ["awaiting_approval", "included_in_patch"].includes(agent.status)) {
    if (missionPatch?.status !== "pending_approval" || patchEvidenceForAgent(agent, missionPatch).length === 0) {
      return {
        ...agent,
        status: "monitoring",
        phase: "monitor",
        severity: "INFO",
        message:
          missionPatch?.status === "pending_approval"
            ? "Monitoring assigned domain; current Mission Patch is scoped to another detector."
            : "Monitoring assigned domain; no Mission Patch is currently pending.",
        linked_mission_patch_id: null,
      };
    }
    return {
      ...agent,
      status: "included_in_patch",
      phase: "handoff",
      message: "Finding included in pending Mission Patch.",
      linked_mission_patch_id: missionPatch.id,
    };
  }
  if (agent.status !== "awaiting_approval" || missionPatch?.status === "pending_approval") return agent;
  const message =
    missionPatch?.status === "rejected"
      ? "Operator rejected the related mission patch; monitoring baseline."
      : missionPatch?.status === "approved" || missionPatch?.status === "executing"
        ? "Approval received; related controls are executing."
        : missionPatch?.status === "verified"
          ? "Related controls verified; monitoring baseline."
          : "Monitoring assigned domain; no approval is currently pending.";
  return { ...agent, status: "monitoring", phase: "monitor", severity: "INFO", message };
}

function toneClass(tone: Tone | undefined): string {
  if (tone === "critical") return "status-red";
  if (tone === "warn") return "status-orange";
  return "status-green";
}

function humanize(value: string): string {
  return value.replace(/[_-]+/g, " ");
}

function shortId(value: string | null | undefined): string {
  if (!value) return "none";
  return value.length > 12 ? `${value.slice(0, 8)}...${value.slice(-4)}` : value;
}

function formatDate(value: string | undefined): string {
  if (!value) return "not recorded";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "not recorded";
  return parsed.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function formatLatency(milliseconds: number | null | undefined): string {
  if (typeof milliseconds !== "number" || Number.isNaN(milliseconds)) return "unknown time";
  return `${(milliseconds / 1000).toFixed(1)}s`;
}

function audioSizeLabel(dataUrl: string | null | undefined): string {
  if (!dataUrl || !dataUrl.includes(",")) return "audio";
  const base64Length = dataUrl.split(",", 2)[1]?.length ?? 0;
  const bytes = Math.max(0, Math.floor((base64Length * 3) / 4));
  return bytes > 1024 ? `${(bytes / 1024).toFixed(1)} KB` : `${bytes} B`;
}

function drawAudioFallback(canvas: HTMLCanvasElement, seedText: string) {
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  const { width, height } = canvas;
  const style = getComputedStyle(canvas);
  const line = style.getPropertyValue("--line") || "rgba(255,255,255,0.16)";
  const green = style.getPropertyValue("--green") || "rgb(85,220,150)";
  const orange = style.getPropertyValue("--orange") || "rgb(235,145,70)";
  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = "rgba(0, 0, 0, 0.16)";
  ctx.fillRect(0, 0, width, height);
  ctx.strokeStyle = line;
  ctx.lineWidth = 1;
  for (let y = 12; y < height; y += 16) {
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(width, y);
    ctx.stroke();
  }

  let seed = 0;
  for (let i = 0; i < seedText.length; i += 1) {
    seed = (seed * 31 + seedText.charCodeAt(i)) >>> 0;
  }
  const bars = Math.floor(width / 4);
  const mid = height * 0.52;
  for (let i = 0; i < bars; i += 1) {
    seed = (1664525 * seed + 1013904223) >>> 0;
    const t = i / Math.max(1, bars - 1);
    const rumble = Math.sin(t * Math.PI * 12) * 0.28 + Math.sin(t * Math.PI * 31) * 0.14;
    const random = (seed / 0xffffffff - 0.5) * 0.38;
    const alarm = Math.max(0, Math.sin((t - 0.28) * Math.PI * 14)) * 0.3;
    const amp = Math.max(0.12, Math.min(0.95, 0.38 + rumble + random + alarm));
    const x = i * 4 + 1;
    const h = amp * height * 0.42;
    ctx.strokeStyle = i % 9 === 0 ? orange : green;
    ctx.beginPath();
    ctx.moveTo(x, mid - h);
    ctx.lineTo(x, mid + h);
    ctx.stroke();
  }
}

async function drawDecodedAudio(canvas: HTMLCanvasElement, audioDataUrl: string): Promise<boolean> {
  const AudioContextClass =
    window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!AudioContextClass) return false;
  const response = await fetch(audioDataUrl);
  const bytes = await response.arrayBuffer();
  const audioContext = new AudioContextClass();
  try {
    const buffer = await audioContext.decodeAudioData(bytes.slice(0));
    const data = buffer.getChannelData(0);
    const ctx = canvas.getContext("2d");
    if (!ctx) return false;
    const { width, height } = canvas;
    const style = getComputedStyle(canvas);
    const line = style.getPropertyValue("--line") || "rgba(255,255,255,0.16)";
    const green = style.getPropertyValue("--green") || "rgb(85,220,150)";
    const orange = style.getPropertyValue("--orange") || "rgb(235,145,70)";
    ctx.clearRect(0, 0, width, height);
    ctx.fillStyle = "rgba(0, 0, 0, 0.16)";
    ctx.fillRect(0, 0, width, height);
    ctx.strokeStyle = line;
    ctx.lineWidth = 1;
    for (let y = 12; y < height; y += 16) {
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(width, y);
      ctx.stroke();
    }
    const mid = height * 0.52;
    const columns = Math.floor(width / 3);
    const samplesPerColumn = Math.max(1, Math.floor(data.length / columns));
    for (let x = 0; x < columns; x += 1) {
      let min = 1;
      let max = -1;
      for (let i = 0; i < samplesPerColumn; i += 1) {
        const sample = data[x * samplesPerColumn + i] ?? 0;
        min = Math.min(min, sample);
        max = Math.max(max, sample);
      }
      ctx.strokeStyle = x % 11 === 0 ? orange : green;
      ctx.beginPath();
      ctx.moveTo(x * 3 + 1, mid + min * height * 0.45);
      ctx.lineTo(x * 3 + 1, mid + max * height * 0.45);
      ctx.stroke();
    }
    return true;
  } finally {
    void audioContext.close();
  }
}

function AudioEvidenceCard({ input, compact = false }: { input: ThermalVisualInput; compact?: boolean }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const audioUrl = input.audio_data_url;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !audioUrl) return;
    let cancelled = false;
    drawAudioFallback(canvas, input.audio_notes ?? audioUrl);
    void drawDecodedAudio(canvas, audioUrl)
      .then((decoded) => {
        if (!decoded && !cancelled) {
          drawAudioFallback(canvas, input.audio_notes ?? audioUrl);
        }
      })
      .catch(() => {
        if (!cancelled) {
          drawAudioFallback(canvas, input.audio_notes ?? audioUrl);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [audioUrl, input.audio_notes]);

  if (!audioUrl) return null;

  return (
    <div className={compact ? "audio-evidence-card is-compact" : "audio-evidence-card"}>
      <div className="audio-evidence-head">
        <span className="label">fan audio evidence</span>
        <strong>{input.audio_duration_s?.toFixed(1) ?? "--"}s</strong>
      </div>
      <canvas
        aria-label="Fan audio waveform"
        className="audio-waveform"
        height={compact ? 58 : 84}
        ref={canvasRef}
        width={compact ? 260 : 360}
      />
      <div className="audio-evidence-meta">
        <span>{input.audio_mime_type ?? "audio/mpeg"}</span>
        <span>{audioSizeLabel(audioUrl)}</span>
      </div>
      {input.audio_notes ? <p>{input.audio_notes}</p> : null}
      <audio controls src={audioUrl} title={input.audio_notes ?? "Fan audio sent to the model"} />
    </div>
  );
}

function stepStatusClass(status: FlowStatus): string {
  if (status === "blocked") return "status-red";
  if (status === "complete") return "status-green";
  if (status === "running") return "status-orange";
  return "status-cyan";
}

function isAgentActive(agent: AgentStatusItem): boolean {
  const value = `${agent.status} ${agent.phase}`.toLowerCase();
  return ["analy", "detect", "dispatch", "explain", "model", "propos", "running"].some((needle) =>
    value.includes(needle),
  );
}

function modelReplyText(
  latestFinding: AgentFinding | undefined,
  activityLog: AgentLogItem[],
  thermalInput: ThermalVisualInput | null,
): string | null {
  if (thermalInput?.model_result?.model || typeof thermalInput?.model_result?.latency_ms === "number") {
    const model = thermalInput.model_result?.model ?? "Nemotron";
    const latency = thermalInput.model_result?.latency_ms;
    return typeof latency === "number" ? `${model} replied in ${formatLatency(latency)}.` : `${model} replied.`;
  }
  const logReply = activityLog.find((item) => item.detail.toLowerCase().includes("replied in"));
  if (logReply) return logReply.detail;
  return latestFinding?.evidence.find((item) => item.toLowerCase().includes("replied in")) ?? null;
}

function modelRequestText(activityLog: AgentLogItem[]): string | null {
  return activityLog.find((item) => item.detail.toLowerCase().includes("sending") && item.detail.toLowerCase().includes("to"))
    ?.detail ?? null;
}

function clip(value: string, max = 110): string {
  return value.length > max ? `${value.slice(0, max - 3).trimEnd()}...` : value;
}

function buildAgentFlowNodes({
  agent,
  latestFinding,
  missionPatch,
  runtime,
  signalRows,
  activityLog,
  thermalInput,
  patchCommands,
  modelName,
  patchRelevant,
  openFindingCount,
}: {
  agent: AgentStatusItem;
  latestFinding?: AgentFinding;
  missionPatch: MissionPatch | null;
  runtime?: AgentRuntimeItem;
  signalRows: SignalRow[];
  activityLog: AgentLogItem[];
  thermalInput: ThermalVisualInput | null;
  patchCommands: Command[];
  modelName: string | null;
  patchRelevant: boolean;
  openFindingCount: number;
}): AgentFlowNode[] {
  const active = isAgentActive(agent);
  const hasFinding = Boolean(latestFinding);
  const hasOpenFinding = latestFinding?.status === "open";
  const reply = modelReplyText(latestFinding, activityLog, thermalInput);
  const request = modelRequestText(activityLog);
  const hasPatch = Boolean(missionPatch && patchRelevant);
  const patchStatus = missionPatch?.status ?? null;
  // The Commander never produces its own findings; its flow is driven by the
  // open domain findings it groups and the patch it assembles.
  const isCommander = agent.agent === "commander_agent";
  const commanderHasWork = openFindingCount > 0 || hasPatch;

  const trigger: AgentFlowNode = {
    key: "trigger",
    label: "trigger",
    sub: humanize(runtime?.last_triggered_by ?? "runtime change"),
    status: isCommander ? (commanderHasWork ? "complete" : "pending") : hasFinding || active ? "complete" : "pending",
    lines: [
      isCommander
        ? `${openFindingCount} open domain finding${openFindingCount === 1 ? "" : "s"} to group.`
        : clip(latestFinding?.finding ?? runtime?.trigger_condition ?? agent.message),
    ],
  };

  const gather: AgentFlowNode = {
    key: "gather",
    label: "gather data",
    sub: `${runtime?.watched_fields?.length ?? signalRows.length} watched signals`,
    status:
      active && !hasFinding ? "running" : hasFinding || (isCommander && commanderHasWork) ? "complete" : "pending",
    lines: signalRows.slice(0, 4).map((row) => `${row.label}: ${row.value}`),
  };

  const model: AgentFlowNode = {
    key: "model",
    label: "model call",
    sub: isCommander
      ? "summary polish"
      : (thermalInput?.model_result?.model ?? (reply || request ? (modelName ?? "crusoe model") : "deterministic rules")),
    status: isCommander
      ? hasPatch
        ? "complete"
        : "pending"
      : reply
        ? "complete"
        : request
          ? "running"
          : hasFinding
            ? "complete"
            : "pending",
    lines: [
      isCommander
        ? hasPatch
          ? "Patch summary composed from grouped agent findings."
          : "Waiting for domain findings to group."
        : clip(
            reply ??
              request ??
              (hasFinding ? "Deterministic evidence used; no model advisory requested." : "Waiting for a trigger."),
          ),
    ],
    image: thermalInput?.image_data_url ?? null,
  };

  const finding: AgentFlowNode = {
    key: "finding",
    label: isCommander ? "findings intake" : "finding",
    sub: latestFinding ? `${latestFinding.severity} | ${Math.round(latestFinding.confidence * 100)}% confidence` : undefined,
    status: isCommander ? (commanderHasWork ? "complete" : "pending") : hasFinding ? "complete" : "pending",
    lines: [
      isCommander
        ? `${openFindingCount} open domain finding${openFindingCount === 1 ? "" : "s"} under review.`
        : clip(latestFinding?.finding ?? "No open finding from this detector."),
    ],
  };

  const commander: AgentFlowNode = {
    key: "commander",
    label: "mission patch",
    sub: hasPatch ? `patch ${shortId(missionPatch?.id)}` : undefined,
    status: hasPatch ? "complete" : (isCommander ? openFindingCount > 0 : hasOpenFinding) ? "running" : "pending",
    lines: [
      hasPatch
        ? clip(missionPatch?.summary ?? "Findings grouped into a mission patch.")
        : (isCommander ? openFindingCount > 0 : hasOpenFinding)
          ? "Grouping open findings into a mission patch."
          : isCommander
            ? clip(agent.message)
            : "No active Mission Patch for this detector.",
    ],
  };

  const approval: AgentFlowNode = {
    key: "approval",
    label: "human approval",
    sub: hasPatch ? humanize(patchStatus ?? "pending") : undefined,
    status: !hasPatch
      ? "pending"
      : patchStatus === "pending_approval"
        ? "running"
        : patchStatus === "rejected"
          ? "blocked"
          : "complete",
    lines: [
      hasPatch
        ? `${missionPatch?.actions?.length ?? 0} command${(missionPatch?.actions?.length ?? 0) === 1 ? "" : "s"} in scope.`
        : "No mission patch waiting.",
    ],
  };

  const succeeded = patchCommands.filter((command) => command.status === "succeeded").length;
  const execution: AgentFlowNode = {
    key: "execution",
    label: "execution",
    sub: patchStatus === "verified" ? "verified" : undefined,
    status: !hasPatch
      ? "pending"
      : patchStatus === "rejected"
        ? "blocked"
        : patchStatus === "verified" || (patchCommands.length > 0 && succeeded === patchCommands.length)
          ? "complete"
          : patchCommands.length > 0
            ? "running"
            : "pending",
    lines: [
      !hasPatch
        ? "Waiting for an approved patch."
        : patchStatus === "rejected"
          ? "Not executed — patch rejected."
          : patchCommands.length > 0
            ? `${succeeded}/${patchCommands.length} commands succeeded.`
            : "Commands queue after approval.",
    ],
  };

  return [trigger, gather, model, finding, commander, approval, execution];
}

function actionLabel(action: string | MissionPatchAction): string {
  if (typeof action === "string") return humanize(action);
  return humanize(String(action.type ?? "action"));
}

function actionTarget(action: MissionPatchAction): string {
  const target =
    action.node_id ??
    action.job_id ??
    action.checkpoint_id ??
    action.target_asset_id ??
    action.asset_id ??
    action.asset_ids;
  if (Array.isArray(target)) return target.join(", ");
  return typeof target === "string" ? target : "mission scope";
}

function commandDescriptor(action: MissionPatchAction): string {
  const target = actionTarget(action);
  if (target === "mission scope" && action.type === "transfer_priority") return "mission queue prioritization";
  return target;
}

function relatedPatchActions(
  agent: AgentStatusItem,
  history: AgentFinding[],
  patchActions: MissionPatchAction[],
  missionPatch: MissionPatch | null,
): MissionPatchAction[] {
  if (agent.agent === "commander_agent") return patchActions;
  const representedInPatch = patchEvidenceForAgent(agent, missionPatch).length > 0 || agent.linked_mission_patch_id === missionPatch?.id;
  const recommendedActions = new Set(
    history.flatMap((finding) => finding.recommended_actions).concat(representedInPatch ? fallbackActionsForAgent(agent.agent) : []),
  );
  if (!recommendedActions.size) return [];
  return patchActions.filter((action) => recommendedActions.has(String(action.type)));
}

function fallbackActionsForAgent(agentName: string): string[] {
  const map: Record<string, string[]> = {
    workload_agent: ["snapshot_evidence", "run_health_check", "pause_job", "rollback_training"],
    thermal_physical_agent: ["mark_node_suspect", "set_gpu_power_limit", "snapshot_evidence", "run_health_check"],
    power_orbit_agent: ["set_gpu_power_limit", "increase_checkpoint_frequency", "transfer_priority"],
    radiation_integrity_agent: ["mark_checkpoint_suspect", "rollback_training", "cordon_node", "run_health_check"],
    checkpoint_downlink_agent: ["transfer_priority", "snapshot_evidence"],
    vibration_health_agent: ["snapshot_evidence", "run_health_check", "mark_node_suspect"],
  };
  return map[agentName] ?? [];
}

function patchEvidenceItems(missionPatch: MissionPatch | null): PatchEvidenceItem[] {
  if (!missionPatch?.evidence) return [];
  const values = Array.isArray(missionPatch.evidence) ? missionPatch.evidence : [missionPatch.evidence];
  return values
    .filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object")
    .map((item) => ({
      agent: typeof item.agent === "string" ? item.agent : undefined,
      finding: typeof item.finding === "string" ? item.finding : undefined,
      severity: typeof item.severity === "string" ? item.severity : undefined,
      confidence: typeof item.confidence === "number" ? item.confidence : undefined,
      affected_assets: Array.isArray(item.affected_assets)
        ? item.affected_assets.filter((value): value is string => typeof value === "string")
        : undefined,
      evidence: Array.isArray(item.evidence)
        ? item.evidence.filter((value): value is string => typeof value === "string")
        : undefined,
      risk: typeof item.risk === "string" ? item.risk : undefined,
      recommended_actions: Array.isArray(item.recommended_actions)
        ? item.recommended_actions.filter((value): value is string => typeof value === "string")
        : undefined,
    }));
}

function patchEvidenceForAgent(agent: AgentStatusItem, missionPatch: MissionPatch | null): PatchEvidenceItem[] {
  const items = patchEvidenceItems(missionPatch);
  if (agent.agent === "commander_agent") return items;
  return items.filter((item) => item.agent === agent.agent);
}

function uniqueStrings(values: Array<string | undefined | null>): string[] {
  return [...new Set(values.filter((value): value is string => Boolean(value && value.trim())).map((value) => value.trim()))];
}

function commandMatchesAgent(command: Command, finding: AgentFinding | undefined): boolean {
  if (!finding) return false;
  return finding.recommended_actions.includes(command.action_type);
}

function findNode(worldState: WorldState | null, id: string): NodeState | undefined {
  return worldState?.nodes?.find((node) => node.id === id);
}

function pct(value: number | undefined, fallback = "--"): string {
  return typeof value === "number" ? `${Math.round(value)}%` : fallback;
}

function temp(value: number | undefined): string {
  return typeof value === "number" ? `${Math.round(value)} C` : "--";
}

function yesNo(value: boolean | undefined): string {
  return value ? "yes" : "no";
}

function radiationTone(radiationRisk: ProcessedRadiationRisk | null, fallbackRisk: string | undefined): Tone {
  const level = String(radiationRisk?.radiationLevel ?? fallbackRisk ?? "").toUpperCase();
  if (level === "CRITICAL" || level === "HIGH") return "critical";
  if (level === "MEDIUM" || level === "ELEVATED") return "warn";
  return "nominal";
}

function radiationRiskValue(radiationRisk: ProcessedRadiationRisk | null, fallbackRisk: string | undefined): string {
  if (!radiationRisk) return fallbackRisk ?? "--";
  return `${radiationRisk.radiationLevel} ${Math.round(radiationRisk.radiationRiskScore)}`;
}

function buildSignalRows(
  agentName: string,
  worldState: WorldState | null,
  radiationRisk: ProcessedRadiationRisk | null,
  openFindings: number,
  commandCount: number,
  missionPatchStatus: string | null = null,
): SignalRow[] {
  const nodeA = findNode(worldState, "node-a");
  const nodeB = findNode(worldState, "node-b");
  const nodeC = findNode(worldState, "node-c");

  switch (agentName) {
    case "workload_agent":
      return [
        { label: "node-a gpu", value: pct(nodeA?.gpu_util), limit: ">85% with lag", tone: (nodeA?.gpu_util ?? 0) > 85 ? "warn" : "nominal" },
        { label: "rank lag", value: `${Math.round((nodeA?.rank_lag ?? 0) * 100)}%`, limit: ">5%", tone: (nodeA?.rank_lag ?? 0) > 0.05 ? "warn" : "nominal" },
        { label: "job step", value: String(worldState?.training.current_step ?? "--") },
        { label: "job state", value: worldState?.training.status ?? "--" },
      ];
    case "thermal_physical_agent":
      return [
        { label: "highest rack temp", value: temp(worldState?.thermal.highest_temp_c), limit: ">88 C", tone: (worldState?.thermal.highest_temp_c ?? 0) >= 88 ? "critical" : "nominal" },
        { label: "hotspot node", value: worldState?.thermal.hotspot_node ?? "--" },
        { label: "node-c temp", value: temp(nodeC?.temp_c), limit: ">88 C", tone: (nodeC?.temp_c ?? 0) >= 88 ? "critical" : "nominal" },
        { label: "cooling state", value: worldState?.thermal.cooling_status ?? "--", tone: worldState?.thermal.cooling_status === "degraded" ? "warn" : "nominal" },
      ];
    case "power_orbit_agent":
      return [
        { label: "battery", value: pct(worldState?.power.battery_percent), limit: "<45% near eclipse", tone: (worldState?.power.battery_percent ?? 100) < 45 ? "warn" : "nominal" },
        { label: "solar input", value: `${worldState?.power.solar_kw ?? "--"} kW`, limit: "0 in eclipse", tone: (worldState?.power.solar_kw ?? 1) <= 0 ? "warn" : "nominal" },
        { label: "eclipse timer", value: `${worldState?.satellite.time_to_eclipse_min ?? "--"} min`, limit: "<15 min", tone: (worldState?.satellite.time_to_eclipse_min ?? 99) < 15 ? "warn" : "nominal" },
        { label: "power mode", value: worldState?.power.mode ?? "--" },
      ];
    case "radiation_integrity_agent":
      return [
        { label: "model risk", value: radiationRiskValue(radiationRisk, worldState?.radiation.risk), limit: ">=HIGH", tone: radiationTone(radiationRisk, worldState?.radiation.risk) },
        { label: "main driver", value: radiationRisk?.mainCause ?? worldState?.radiation.region ?? "--" },
        { label: "ecc last 5 min", value: String(worldState?.radiation.ecc_errors_last_5min ?? "--"), limit: ">900", tone: (worldState?.radiation.ecc_errors_last_5min ?? 0) > 900 ? "critical" : "nominal" },
        { label: "xid event", value: yesNo(worldState?.radiation.xid_event), limit: "any true", tone: worldState?.radiation.xid_event ? "critical" : "nominal" },
        { label: "checkpoint", value: worldState?.training.latest_checkpoint_status ?? "--", tone: worldState?.training.latest_checkpoint_status === "suspect" ? "critical" : "nominal" },
      ];
    case "checkpoint_downlink_agent":
      return [
        { label: "window open", value: yesNo(worldState?.downlink.window_open), tone: worldState?.downlink.window_open ? "nominal" : "warn" },
        { label: "capacity", value: `${worldState?.downlink.capacity_gb ?? "--"} GB`, limit: "180 GB full ckpt", tone: (worldState?.downlink.capacity_gb ?? 0) < 180 ? "warn" : "nominal" },
        { label: "time left", value: `${worldState?.downlink.time_remaining_min ?? "--"} min` },
        { label: "used", value: `${worldState?.downlink.used_gb ?? "--"} GB` },
      ];
    case "vibration_health_agent":
      return [
        { label: "vibration score", value: String(nodeC?.vibration_score ?? "--"), limit: ">0.75", tone: (nodeC?.vibration_score ?? 0) > 0.75 ? "warn" : "nominal" },
        { label: "node-c temp", value: temp(nodeC?.temp_c), limit: ">88 C", tone: (nodeC?.temp_c ?? 0) >= 88 ? "critical" : "nominal" },
        { label: "cooling state", value: worldState?.thermal.cooling_status ?? "--" },
        { label: "hotspot", value: worldState?.thermal.hotspot_node ?? "--" },
      ];
    case "commander_agent":
      return [
        { label: "open findings", value: String(openFindings), limit: ">0", tone: openFindings > 0 ? "warn" : "nominal" },
        {
          label: "active patch",
          value: missionPatchStatus ? humanize(missionPatchStatus) : "none",
          limit: "pending needs decision",
          tone: missionPatchStatus === "pending_approval" ? "warn" : "nominal",
        },
        { label: "commands tracked", value: String(commandCount) },
        { label: "approval boundary", value: "human required" },
      ];
    default:
      return [
        { label: "node-b gpu", value: pct(nodeB?.gpu_util) },
        { label: "node-c temp", value: temp(nodeC?.temp_c) },
        { label: "findings", value: String(openFindings) },
        { label: "commands", value: String(commandCount) },
      ];
  }
}

function approvalProblemTitle(
  agent: AgentStatusItem,
  latestFinding: AgentFinding | undefined,
  evidenceItems: PatchEvidenceItem[],
  missionPatch: MissionPatch | null,
  thermalInput: ThermalVisualInput | null,
): string {
  if (latestFinding?.finding) return latestFinding.finding;
  if (evidenceItems[0]?.finding) return evidenceItems[0].finding;
  if (thermalInput?.model_result?.summary) return thermalInput.model_result.summary;
  if (agent.agent === "commander_agent" && missionPatch?.summary) return missionPatch.summary;
  return "No approval-required issue is linked to this agent.";
}

function approvalRiskText(
  latestFinding: AgentFinding | undefined,
  evidenceItems: PatchEvidenceItem[],
  missionPatch: MissionPatch | null,
  thermalInput: ThermalVisualInput | null,
): string {
  return (
    latestFinding?.risk ||
    evidenceItems.find((item) => item.risk)?.risk ||
    thermalInput?.model_result?.risk ||
    missionPatch?.summary ||
    "No elevated operational risk is currently attached to this approval."
  );
}

function approvalEvidenceList(
  latestFinding: AgentFinding | undefined,
  evidenceItems: PatchEvidenceItem[],
  thermalInput: ThermalVisualInput | null,
): string[] {
  const patchEvidence = evidenceItems.flatMap((item) => item.evidence ?? []);
  const modelEvidence = thermalInput?.model_result?.evidence ?? [];
  return uniqueStrings([...(latestFinding?.evidence ?? []), ...patchEvidence, ...modelEvidence]).slice(0, 6);
}

function approvalAssetList(
  latestFinding: AgentFinding | undefined,
  evidenceItems: PatchEvidenceItem[],
  thermalInput: ThermalVisualInput | null,
): string[] {
  return uniqueStrings([
    ...(latestFinding?.affected_assets ?? []),
    ...evidenceItems.flatMap((item) => item.affected_assets ?? []),
    ...(thermalInput?.model_result?.affected_assets ?? []),
    thermalInput?.asset_id,
  ]);
}

type FlowActor = "runtime" | "agent" | "model" | "commander" | "operator" | "executor";

function transcriptActor(item: AgentLogItem): FlowActor {
  const detail = item.detail.toLowerCase();
  const label = item.label.toLowerCase();
  if (detail.includes("replied in") || detail.includes("model advisory")) return "model";
  if (label.includes("operator input") || detail.includes("human rejected") || detail.includes("human approval")) return "operator";
  if (label.includes("command") || label.includes("verification")) return "executor";
  if (label.includes("patch") || label.includes("approval state") || item.agent === "commander_agent") return "commander";
  if (detail.includes("heartbeat") || label.includes("reset")) return "runtime";
  return "agent";
}

function isModelRequestEntry(item: AgentLogItem): boolean {
  const detail = item.detail.toLowerCase();
  return detail.includes("sending") && detail.includes(" to ");
}

function LiveFlowTranscript({
  log,
  signalRows,
  thermalInput,
  audioInput,
}: {
  log: AgentLogItem[];
  signalRows: SignalRow[];
  thermalInput: ThermalVisualInput | null;
  audioInput: ThermalVisualInput | null;
}) {
  const scrollRef = useRef<HTMLOListElement | null>(null);
  // agentLogs store newest-first; a transcript reads oldest -> newest.
  const entries = useMemo(() => [...log].reverse(), [log]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [entries.length]);

  return (
    <ol className="flow-transcript" ref={scrollRef}>
      {entries.length === 0 ? (
        <li className="chat-row actor-runtime">
          <header>
            <b>runtime</b>
            <time>--</time>
          </header>
          <p>No workflow events recorded for this agent in this session yet.</p>
        </li>
      ) : null}
      {entries.map((item) => {
        const actor = transcriptActor(item);
        const showPayload = isModelRequestEntry(item);
        return (
          <li className={`chat-row actor-${actor} is-${item.status}`} key={item.id}>
            <header>
              <b>{actor}</b>
              <span>{item.label}</span>
              <time>{formatDate(item.time)}</time>
            </header>
            <p>{item.detail}</p>
            {showPayload ? (
              <div className="chat-payload">
                <span className="label">data sent with this request</span>
                <div className="agent-chip-list">
                  {signalRows.map((row) => (
                    <span key={row.label}>{`${row.label}: ${row.value}`}</span>
                  ))}
                </div>
                {thermalInput ? (
                  <>
                    <img alt={`Frame sent to the model for ${thermalInput.asset_id}`} src={thermalInput.image_data_url} />
                  </>
                ) : null}
                {audioInput ? <AudioEvidenceCard input={audioInput} compact /> : null}
              </div>
            ) : null}
          </li>
        );
      })}
    </ol>
  );
}

interface AgentDetailModalProps {
  agent: AgentStatusItem;
  latestFinding?: AgentFinding;
  history: AgentFinding[];
  relatedIncident?: Incident;
  relatedCommands: Command[];
  activityLog: AgentLogItem[];
  patchActions: MissionPatchAction[];
  missionPatch: MissionPatch | null;
  approvalActions: MissionPatchAction[];
  approvalBusy: boolean;
  approvalError: string | null;
  linkedPatchId?: string | null;
  patchCommands: Command[];
  modelName: string | null;
  worldState: WorldState | null;
  radiationRisk: ProcessedRadiationRisk | null;
  runtime?: AgentRuntimeItem;
  openFindingCount: number;
  commandCount: number;
  onApprovePatch: () => Promise<void>;
  onClose: () => void;
  onRejectPatch: () => Promise<void>;
}

function AgentDetailModal({
  agent,
  latestFinding,
  history,
  relatedIncident,
  relatedCommands,
  activityLog,
  patchActions,
  missionPatch,
  approvalActions,
  approvalBusy,
  approvalError,
  linkedPatchId,
  patchCommands,
  modelName,
  worldState,
  radiationRisk,
  runtime,
  openFindingCount,
  commandCount,
  onApprovePatch,
  onClose,
  onRejectPatch,
}: AgentDetailModalProps) {
  const actions = latestFinding?.recommended_actions?.length
    ? latestFinding.recommended_actions
    : patchActions.map((action) => String(action.type));
  const evidence = latestFinding?.evidence?.length
    ? latestFinding.evidence
    : ["No evidence packet from this detector."];
  const assets = latestFinding?.affected_assets?.length ? latestFinding.affected_assets : [];
  const signalRows = buildSignalRows(
    agent.agent,
    worldState,
    radiationRisk,
    openFindingCount,
    patchCommands.length || relatedCommands.length || commandCount,
    missionPatch?.status ?? null,
  );
  const latestThermalInput = worldState?.thermal.latest_visual_input ?? null;
  const thermalInput: ThermalVisualInput | null =
    agent.agent === "thermal_physical_agent" ? latestThermalInput : null;
  const audioInput: ThermalVisualInput | null =
    thermalInput?.audio_data_url
      ? thermalInput
      : agent.agent === "vibration_health_agent" && latestThermalInput?.audio_data_url
        ? latestThermalInput
        : null;
  const patchStatus = missionPatch?.status ?? null;
  const evidenceItems = patchEvidenceForAgent(agent, missionPatch);
  const approvalTitle = approvalProblemTitle(agent, latestFinding, evidenceItems, missionPatch, thermalInput);
  const approvalRisk = approvalRiskText(latestFinding, evidenceItems, missionPatch, thermalInput);
  const approvalEvidence = approvalEvidenceList(latestFinding, evidenceItems, thermalInput);
  const approvalAssets = approvalAssetList(latestFinding, evidenceItems, thermalInput);
  const patchRelevantToAgent =
    agent.agent === "commander_agent" ||
    evidenceItems.length > 0 ||
    approvalActions.length > 0 ||
    agent.linked_mission_patch_id === missionPatch?.id;
  const commandSet =
    patchRelevantToAgent && approvalActions.length > 0 ? approvalActions : patchActions;
  const approvalCommandCount = commandSet.length;
  const patchCommandCount = patchActions.length;
  const canDecidePatch = missionPatch?.status === "pending_approval" && patchCommandCount > 0;
  const commandContext = approvalActions.length === 0 ? "Mission Patch command set" : "Commands matching this agent context";
  const flowNodes = buildAgentFlowNodes({
    agent,
    latestFinding,
    missionPatch,
    runtime,
    signalRows,
    activityLog,
    thermalInput,
    patchCommands,
    modelName,
    patchRelevant: patchRelevantToAgent,
    openFindingCount,
  });

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        onClose();
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  return (
    <div className="agent-modal-backdrop" role="presentation" onMouseDown={onClose}>
      <section
        className="agent-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="agent-modal-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header className="agent-modal-header">
          <div>
            <div className="eyebrow">detector inspector</div>
            <h2 id="agent-modal-title">{agent.display_name}</h2>
            <p>{detectorScope[agent.agent] ?? "Telemetry detector for the selected operational domain."}</p>
          </div>
          <button className="close-btn" type="button" aria-label="Close agent details" onClick={onClose}>
            x
          </button>
        </header>

        <div className="agent-modal-grid">
          <section className="agent-modal-section span-2">
            <div className="section-header compact">
              <div>
                <div className="eyebrow">live agent flow</div>
                <strong>{flowNodes.find((node) => node.status === "running")?.label ?? "latest execution"}</strong>
              </div>
              <b className="status-cyan">{flowNodes.length} stages</b>
            </div>
            <div className="agent-flow-graph">
              {flowNodes.map((node, index) => (
                <Fragment key={node.key}>
                  {index > 0 ? <span aria-hidden="true" className={`flow-connector is-${node.status}`} /> : null}
                  <article className={`flow-node is-${node.status}`}>
                    <header>
                      <strong>{node.label}</strong>
                      <b className={stepStatusClass(node.status)}>{humanize(node.status)}</b>
                    </header>
                    {node.sub ? <small title={node.sub}>{node.sub}</small> : null}
                    {node.image ? <img alt={`Input frame sent to ${node.sub ?? "the model"}`} src={node.image} /> : null}
                    <ul>
                      {node.lines.map((line) => (
                        <li key={line}>{line}</li>
                      ))}
                    </ul>
                  </article>
                </Fragment>
              ))}
            </div>
          </section>

          <section className="agent-modal-section span-2">
            <div className="section-header compact">
              <div>
                <div className="eyebrow">live flow log</div>
                <strong>{activityLog.length ? `${activityLog.length} event${activityLog.length === 1 ? "" : "s"}` : "no events yet"}</strong>
              </div>
              <b className="status-cyan">chronological</b>
            </div>
            <LiveFlowTranscript log={activityLog} signalRows={signalRows} thermalInput={thermalInput} audioInput={audioInput} />
          </section>

          {missionPatch && patchRelevantToAgent && patchCommandCount > 0 ? (
            <section className="agent-modal-section span-2 agent-approval-section">
              <div className="section-header compact">
                <div>
                  <div className="eyebrow">approval review</div>
                  <strong>{approvalTitle}</strong>
                </div>
                <b className={canDecidePatch ? "status-orange" : "status-cyan"}>
                  {canDecidePatch ? "needs approval" : humanize(missionPatch.status)}
                </b>
              </div>
              <div className="approval-review-grid">
                <div className="approval-problem">
                  <span className="label">unsafe issue</span>
                  <p className="approval-issue">{approvalTitle}</p>
                  <span className="label">risk if ignored</span>
                  <p>{approvalRisk}</p>
                  <div className="approval-chip-row">
                    {(approvalAssets.length ? approvalAssets : ["mission scope"]).map((asset) => (
                      <span key={asset}>{asset}</span>
                    ))}
                  </div>
                  <div className="approval-evidence">
                    <span className="label">evidence</span>
                    <ul>
                      {(approvalEvidence.length ? approvalEvidence : ["No evidence packet attached to this agent."]).map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                    </ul>
                  </div>
                </div>
                <div className="approval-visual">
                  <span className="label">
                    {thermalInput ? "visual evidence" : audioInput ? "audio evidence" : "evidence source"}
                  </span>
                  {thermalInput ? (
                    <>
                      <img alt={`Thermal approval evidence for ${thermalInput.asset_id}`} src={thermalInput.image_data_url} />
                      <small>
                        {thermalInput.model_result?.model ?? "deterministic telemetry"} | {humanize(thermalInput.analysis_status)}
                      </small>
                      {audioInput ? <AudioEvidenceCard input={audioInput} /> : null}
                      {thermalInput.model_result?.summary ? <p>{thermalInput.model_result.summary}</p> : null}
                    </>
                  ) : audioInput ? (
                    <AudioEvidenceCard input={audioInput} />
                  ) : (
                    <div className="approval-no-visual">
                      This approval is based on telemetry, agent findings, and Commander validation.
                    </div>
                  )}
                </div>
              </div>
              <div className="approval-command-header">
                <span className="label">commands awaiting approval</span>
                <strong>
                  {approvalCommandCount} command{approvalCommandCount === 1 ? "" : "s"}
                </strong>
              </div>
              {approvalActions.length === 0 ? (
                <small className="agent-approval-subnote">
                  {commandContext}: this panel always reflects the full validated Mission Patch scope.
                </small>
              ) : null}
              <ol className="agent-command-approval-list">
                {commandSet.map((action) => (
                  <li key={`${action.type}-${commandDescriptor(action)}`}>
                    <span>
                      <strong>{actionLabel(action)}</strong>
                      <small>{commandDescriptor(action)}</small>
                    </span>
                  </li>
                ))}
              </ol>
              <div className="agent-approval-note">
                Approval is only needed because this detector raised an unsafe condition. Approving here executes the entire validated Mission Patch ({patchCommandCount} commands total), not just this one command group.
              </div>
              {approvalError ? <p className="approval-error">{approvalError}</p> : null}
              <div className="agent-approval-buttons">
                <button disabled={!canDecidePatch || approvalBusy} onClick={() => void onApprovePatch()} type="button">
                  Approve
                </button>
                <button disabled={!canDecidePatch || approvalBusy} onClick={() => void onRejectPatch()} type="button">
                  Reject
                </button>
              </div>
            </section>
          ) : null}

          {agent.agent === "thermal_physical_agent" ? <CoolingTrendPanel className="agent-cooling-trend" /> : null}

          <section className="agent-modal-section span-2">
            <div className="section-header compact">
              <div>
                <div className="eyebrow">{latestFinding?.status === "open" ? "current finding" : "latest report"}</div>
                <strong>{latestFinding?.finding ?? "No open finding reported"}</strong>
              </div>
              <b className={toneClass(latestFinding ? "warn" : "nominal")}>
                {latestFinding?.status ?? "none"}
              </b>
            </div>
            <p>{latestFinding?.risk ?? "No domain risk is currently above this detector's trigger threshold."}</p>
            <div className="agent-evidence-grid">
              <div>
                <span className="label">evidence</span>
                <ul>
                  {evidence.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </div>
              <div>
                <span className="label">affected assets</span>
                <div className="agent-chip-list">
                  {(assets.length ? assets : ["none"]).map((asset) => (
                    <span key={asset}>{asset}</span>
                  ))}
                </div>
              </div>
            </div>
          </section>

          <section className="agent-modal-section">
            <div className="eyebrow">proposed controls</div>
            <ul className="agent-action-list">
              {(actions.length ? actions : ["continue_monitoring"]).map((action) => (
                <li key={action}>{actionLabel(action)}</li>
              ))}
            </ul>
          </section>

          {thermalInput && approvalActions.length === 0 ? (
            <section className="agent-modal-section thermal-frame-section">
              <div className="section-header compact">
                <div>
                  <div className="eyebrow">latest thermal input</div>
                  <strong>{thermalInput.asset_id}</strong>
                </div>
                <b className={thermalInput.analysis_status === "completed" ? "status-yellow" : "status-orange"}>
                  {humanize(thermalInput.analysis_status)}
                </b>
              </div>
              <img alt={`Thermal input for ${thermalInput.asset_id}`} src={thermalInput.image_data_url} />
              {thermalInput.audio_data_url ? (
                <div className="thermal-frame-audio">
                  <AudioEvidenceCard input={thermalInput} />
                </div>
              ) : null}
              <div className="thermal-frame-meta">
                <span>{formatDate(thermalInput.received_at)}</span>
                <span>{thermalInput.model_result?.model ?? "deterministic fallback"}</span>
              </div>
              {thermalInput.model_result?.summary ? <p>{thermalInput.model_result.summary}</p> : null}
            </section>
          ) : null}

          <section className="agent-modal-section">
            <div className="eyebrow">operator context</div>
            <div className="linked-ops">
              <div>
                <span>incident</span>
                <strong>{relatedIncident ? shortId(relatedIncident.id) : "none"}</strong>
              </div>
              <div>
                <span>mission patch</span>
                <strong>{shortId(agent.linked_mission_patch_id ?? linkedPatchId)}</strong>
              </div>
              <div>
                <span>commands</span>
                <strong>{patchRelevantToAgent && patchCommands.length ? patchCommands.length : relatedCommands.length}</strong>
              </div>
            </div>
          </section>

          <section className="agent-modal-section span-2">
            <div className="section-header compact">
              <div>
                <div className="eyebrow">recent reports</div>
                <strong>{history.length ? `${history.length} report${history.length === 1 ? "" : "s"}` : "status only"}</strong>
              </div>
              <b className="status-cyan">{formatDate(agent.updated_at)}</b>
            </div>
            <ol className="agent-history">
              {(history.length ? history : latestFinding ? [latestFinding] : []).slice(0, 4).map((finding) => (
                <li key={finding.id}>
                  <time>{formatDate(finding.created_at)}</time>
                  <span>{finding.finding}</span>
                  <b className={toneClass(finding.status === "open" ? "warn" : "nominal")}>{finding.status}</b>
                </li>
              ))}
              {!history.length && !latestFinding ? (
                <li>
                  <time>{formatDate(agent.updated_at)}</time>
                  <span>{agent.message}</span>
                  <b className={workStateClass(agent, patchStatus)}>{workStateLabel(agent, patchStatus)}</b>
                </li>
              ) : null}
            </ol>
          </section>
        </div>
      </section>
    </div>
  );
}

export default function AgentStatus() {
  const agents = useWorldStore((state) => state.agents);
  const agentRuntime = useWorldStore((state) => state.agentRuntime);
  const agentFindings = useWorldStore((state) => state.agentFindings);
  const incidents = useWorldStore((state) => state.incidents);
  const missionPatch = useWorldStore((state) => state.missionPatch);
  const setMissionPatch = useWorldStore((state) => state.setMissionPatch);
  const setPatchMode = useWorldStore((state) => state.setPatchMode);
  const commands = useWorldStore((state) => state.commands);
  const worldState = useWorldStore((state) => state.worldState);
  const radiationRisk = useWorldStore((state) => state.radiationRisk);
  const agentLogs = useWorldStore((state) => state.agentLogs);
  const aiStatus = useWorldStore((state) => state.aiStatus);
  const missionPatchForReconcile = useWorldStore((state) => state.missionPatch);
  const visibleAgents = (agents.length > 0 ? agents : fallbackAgents)
    .map((agent) => reconcileAgent(agent, missionPatchForReconcile))
    .filter((agent) => agent.agent !== "commander_agent");
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);
  const [approvalBusy, setApprovalBusy] = useState(false);
  const [approvalError, setApprovalError] = useState<string | null>(null);

  const selectedAgent = useMemo(
    () => visibleAgents.find((agent) => agent.agent === selectedAgentId),
    [selectedAgentId, visibleAgents],
  );
  const selectedHistory = useMemo(
    () => (selectedAgent ? agentFindings.filter((finding) => finding.agent_name === selectedAgent.agent) : []),
    [agentFindings, selectedAgent],
  );
  const latestFinding = selectedHistory[0];
  const relatedIncident = latestFinding
    ? incidents.find((incident) => incident.finding_ids.includes(latestFinding.id))
    : undefined;
  const relatedCommands = commands.filter((command) => commandMatchesAgent(command, latestFinding));
  const patchCommands = missionPatch ? commands.filter((command) => command.mission_patch_id === missionPatch.id) : [];
  const patchActions = missionPatch?.actions ?? [];
  const approvalActions = selectedAgent ? relatedPatchActions(selectedAgent, selectedHistory, patchActions, missionPatch) : [];
  const openFindingCount = agentFindings.filter((finding) => finding.status === "open").length;
  const missionPatchStatus = missionPatch?.status ?? null;

  async function approveFromAgent() {
    if (!missionPatch || approvalBusy) return;
    setApprovalBusy(true);
    setApprovalError(null);
    setPatchMode("execute");
    try {
      const decision = await approveMissionPatch(missionPatch.id);
      setMissionPatch(decision.patch);
      if (decision.localToolCalls.length > 0) {
        void runHardwareToolCalls(decision.localToolCalls);
      }
    } catch {
      setPatchMode("pending");
      setApprovalError("Approve failed — the backend rejected the request or is unreachable. The patch is still pending.");
    } finally {
      setApprovalBusy(false);
    }
  }

  async function rejectFromAgent() {
    if (!missionPatch || approvalBusy) return;
    setApprovalBusy(true);
    setApprovalError(null);
    setPatchMode("reject");
    try {
      const decision = await rejectMissionPatch(missionPatch.id);
      setMissionPatch(decision.patch);
      if (decision.localToolCalls.length > 0) {
        void runHardwareToolCalls(decision.localToolCalls);
      }
    } catch {
      setPatchMode("pending");
      setApprovalError("Reject failed — the backend rejected the request or is unreachable. The patch is still pending.");
    } finally {
      setApprovalBusy(false);
    }
  }

  return (
    <section className="rail-section" aria-label="Independent agent status">
      <div className="eyebrow">agent system</div>
      <div className="agent-status-list">
        {visibleAgents.map((agent) => {
          const runtime = agentRuntime.find((item) => item.agent === agent.agent);
          const latestReport = agentFindings.find((finding) => finding.agent_name === agent.agent);
          const hasReport = Boolean(latestReport);
          const includedInPatch = patchEvidenceForAgent(agent, missionPatch).length > 0;
          const flowLine = isAgentActive(agent)
            ? "dispatch -> gathering data"
            : includedInPatch && isActivePatchStatus(missionPatchStatus)
              ? "finding included in Mission Patch"
              : hasReport
              ? latestReport?.status === "open"
                ? "report handed to Mission Patch"
                : "last report resolved"
              : runtime?.run_state === "awaiting_approval"
                ? "Mission Patch waiting for approval"
                : "watching triggers";
          return (
            <button
              className={`agent-card${agent.agent === selectedAgentId ? " is-selected" : ""}`}
              key={agent.agent}
              type="button"
              aria-pressed={agent.agent === selectedAgentId}
              onClick={() => setSelectedAgentId(agent.agent)}
            >
              <span>
                <strong>{agent.display_name}</strong>
                {agent.message}
                <small>{flowLine}</small>
              </span>
              <b className={workStateClass(agent, missionPatchStatus)}>{workStateLabel(agent, missionPatchStatus)}</b>
            </button>
          );
        })}
      </div>

      {selectedAgent && typeof document !== "undefined"
        ? createPortal(
            <AgentDetailModal
              agent={selectedAgent}
              history={selectedHistory}
              latestFinding={latestFinding}
              linkedPatchId={missionPatch?.id ?? null}
              missionPatch={missionPatch}
              approvalActions={approvalActions}
              approvalBusy={approvalBusy}
              approvalError={approvalError}
              patchCommands={patchCommands}
              modelName={aiStatus?.text_model ?? null}
              patchActions={patchActions}
              relatedCommands={relatedCommands}
              relatedIncident={relatedIncident}
              activityLog={agentLogs[selectedAgent.agent] ?? []}
              worldState={worldState}
              radiationRisk={radiationRisk}
              runtime={agentRuntime.find((item) => item.agent === selectedAgent.agent)}
              openFindingCount={openFindingCount}
              commandCount={commands.length}
              onApprovePatch={approveFromAgent}
              onClose={() => setSelectedAgentId(null)}
              onRejectPatch={rejectFromAgent}
            />,
            document.body,
          )
        : null}
    </section>
  );
}
