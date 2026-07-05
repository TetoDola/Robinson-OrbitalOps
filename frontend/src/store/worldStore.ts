import { create } from "zustand";
import { subscribeWithSelector } from "zustand/middleware";

import type {
  AgentFinding,
  AgentRuntimeItem,
  AgentStatusItem,
  AiStatusResponse,
  BackendLiveEvent,
  Command,
  Incident,
  MissionPatch,
  ProcessedRadiationRisk,
  WorldState,
} from "../types/backend";

export type ConnectionStatus = "idle" | "connecting" | "live" | "offline" | "error";
export type PatchMode = "pending" | "execute" | "verify" | "verified" | "replan" | "modify" | "reject";

export interface TelemetrySnapshot {
  clock: string;
  speed: string;
  altitude: string;
  location: string;
  groundTrack: string;
  computeLoad: string;
  latency: string;
  battery: string;
  solar: string;
  eclipse: string;
  radiation: string;
  radiationExplanation?: string;
  radiationRecommendedAction?: string;
  eccTrend: string;
  trustedCheckpoint: string;
  latestCheckpoint: string;
  downlink: string;
  rackHealth: string;
  rackHealthTone: "yellow" | "orange";
  groundLink: string;
  orbitPhase: string;
  patchConfidence: string;
}

export const initialTelemetry: TelemetrySnapshot = {
  clock: "--",
  speed: "--",
  altitude: "--",
  location: "--",
  groundTrack: "ground track resolving",
  computeLoad: "--",
  latency: "--",
  battery: "38%",
  solar: "1.2 kW",
  eclipse: "11 min",
  radiation: "Elevated",
  eccTrend: "Rising",
  trustedCheckpoint: "ckpt-184500",
  latestCheckpoint: "ckpt-184900 suspect",
  downlink: "22 GB / 180 GB",
  rackHealth: "nominal",
  rackHealthTone: "yellow",
  groundLink: "Zurich-03",
  orbitPhase: "approaching eclipse",
  patchConfidence: "87%",
};

export interface WorkflowEventItem {
  id: string;
  time: string;
  label: string;
  detail: string;
  status: "running" | "complete" | "blocked" | "info";
}

export interface AgentLogItem {
  id: string;
  agent: string;
  time: string;
  label: string;
  detail: string;
  status: WorkflowEventItem["status"];
  eventType: string;
  commandId?: string;
  missionPatchId?: string;
}

interface WorldStore {
  worldState: WorldState | null;
  worldVersion: number | null;
  scenarioRunId: string | null;
  telemetry: TelemetrySnapshot;
  radiationRisk: ProcessedRadiationRisk | null;
  agents: AgentStatusItem[];
  agentRuntime: AgentRuntimeItem[];
  aiStatus: AiStatusResponse | null;
  workflowEvents: WorkflowEventItem[];
  agentLogs: Record<string, AgentLogItem[]>;
  agentFindings: AgentFinding[];
  incidents: Incident[];
  missionPatch: MissionPatch | null;
  commands: Command[];
  simSpeed: number;
  followNode: boolean;
  inspectionOpen: boolean;
  patchMode: PatchMode;
  connectionStatus: ConnectionStatus;
  lastEvent: BackendLiveEvent | null;
  lastEventAt: string | null;
  demoResetAt: string | null;
  setWorldState: (state: WorldState, version?: number | null, scenarioRunId?: string | null) => void;
  setTelemetry: (telemetry: TelemetrySnapshot) => void;
  setRadiationRisk: (radiationRisk: ProcessedRadiationRisk | null) => void;
  setAgents: (agents: AgentStatusItem[]) => void;
  upsertAgent: (agent: AgentStatusItem) => void;
  setAgentRuntime: (agents: AgentRuntimeItem[]) => void;
  upsertAgentRuntime: (agent: AgentRuntimeItem) => void;
  setAiStatus: (aiStatus: AiStatusResponse | null) => void;
  pushWorkflowEvent: (event: WorkflowEventItem) => void;
  pushAgentLog: (event: AgentLogItem) => void;
  setAgentFindings: (findings: AgentFinding[]) => void;
  upsertAgentFinding: (finding: AgentFinding) => void;
  setIncidents: (incidents: Incident[]) => void;
  setMissionPatch: (missionPatch: MissionPatch | null) => void;
  patchMissionPatch: (id: string, patch: Partial<MissionPatch>) => void;
  setCommands: (commands: Command[]) => void;
  setSimSpeed: (simSpeed: number) => void;
  setFollowNode: (followNode: boolean) => void;
  setInspectionOpen: (inspectionOpen: boolean) => void;
  setPatchMode: (patchMode: PatchMode) => void;
  setConnectionStatus: (connectionStatus: ConnectionStatus) => void;
  ingestLiveEvent: (event: BackendLiveEvent) => void;
}

export const useWorldStore = create<WorldStore>()(
  subscribeWithSelector((set) => ({
    worldState: null,
    worldVersion: null,
    scenarioRunId: null,
    telemetry: initialTelemetry,
    radiationRisk: null,
    agents: [],
    agentRuntime: [],
    aiStatus: null,
    workflowEvents: [],
    agentLogs: {},
    agentFindings: [],
    incidents: [],
    missionPatch: null,
    commands: [],
    simSpeed: 60,
    followNode: false,
    inspectionOpen: false,
    patchMode: "pending",
    connectionStatus: "idle",
    lastEvent: null,
    lastEventAt: null,
    demoResetAt: null,
    setWorldState: (worldState, worldVersion = null, scenarioRunId = null) =>
      set({ worldState, worldVersion, scenarioRunId }),
    setTelemetry: (telemetry) => set({ telemetry }),
    setRadiationRisk: (radiationRisk) => set({ radiationRisk }),
    setAgents: (agents) => set({ agents }),
    upsertAgent: (agent) =>
      set((state) => {
        const agents = state.agents.filter((item) => item.agent !== agent.agent);
        return { agents: [...agents, agent].sort((a, b) => a.agent.localeCompare(b.agent)) };
      }),
    setAgentRuntime: (agentRuntime) =>
      set({ agentRuntime: [...agentRuntime].sort((a, b) => a.agent.localeCompare(b.agent)) }),
    upsertAgentRuntime: (agent) =>
      set((state) => {
        const agentRuntime = state.agentRuntime.filter((item) => item.agent !== agent.agent);
        return { agentRuntime: [...agentRuntime, agent].sort((a, b) => a.agent.localeCompare(b.agent)) };
      }),
    setAiStatus: (aiStatus) => set({ aiStatus }),
    pushWorkflowEvent: (event) =>
      set((state) => ({ workflowEvents: [event, ...state.workflowEvents].slice(0, 12) })),
    pushAgentLog: (event) =>
      set((state) => ({ agentLogs: appendAgentLogItem(state.agentLogs, event) })),
    setAgentFindings: (agentFindings) =>
      set({
        agentFindings: [...agentFindings].sort(
          (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
        ),
      }),
    upsertAgentFinding: (finding) =>
      set((state) => {
        const agentFindings = state.agentFindings.filter((item) => item.id !== finding.id);
        return {
          agentFindings: [...agentFindings, finding].sort(
            (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
          ),
        };
      }),
    setIncidents: (incidents) => set({ incidents }),
    setMissionPatch: (missionPatch) => set({ missionPatch }),
    patchMissionPatch: (id, patch) =>
      set((state) => {
        if (!state.missionPatch || state.missionPatch.id !== id) {
          return state;
        }
        return { missionPatch: { ...state.missionPatch, ...patch } };
      }),
    setCommands: (commands) => set({ commands }),
    setSimSpeed: (simSpeed) => set({ simSpeed }),
    setFollowNode: (followNode) => set({ followNode }),
    setInspectionOpen: (inspectionOpen) => set({ inspectionOpen }),
    setPatchMode: (patchMode) => set({ patchMode }),
    setConnectionStatus: (connectionStatus) => set({ connectionStatus }),
    ingestLiveEvent: (event) =>
      set((state) => {
        const upsertCommand = (commandPatch: Partial<Command> & { id: string; mission_patch_id: string }): Command[] => {
          const existing = state.commands.find((command) => command.id === commandPatch.id);
          const command: Command = {
            id: commandPatch.id,
            mission_patch_id: commandPatch.mission_patch_id,
            action_type: commandPatch.action_type ?? existing?.action_type ?? "unknown",
            target_asset_id: commandPatch.target_asset_id ?? existing?.target_asset_id ?? null,
            status: commandPatch.status ?? existing?.status ?? "unknown",
            input: commandPatch.input ?? existing?.input ?? {},
            result: commandPatch.result ?? existing?.result ?? {},
          };
          return [...state.commands.filter((item) => item.id !== command.id), command];
        };

        if (event.type === "world_state.updated") {
          const payload = event.payload as Extract<BackendLiveEvent, { type: "world_state.updated" }>["payload"];
          return {
            worldState: payload.state,
            worldVersion: payload.version,
            scenarioRunId: payload.scenario_run_id,
            lastEvent: event,
            lastEventAt: event.timestamp,
          };
        }

        if (event.type === "agent.status.updated") {
          const agent = event.payload as AgentStatusItem;
          const agents = state.agents.filter((item) => item.agent !== agent.agent);
          const logStatus = agentEventStatus(agent);
          const shouldLog =
            agent.severity !== "INFO" ||
            !["monitor", "monitoring", "healthy"].includes(agent.phase) ||
            !["monitoring", "healthy"].includes(agent.status);
          return {
            agents: [...agents, { ...agent, updated_at: event.timestamp }].sort((a, b) =>
              a.agent.localeCompare(b.agent),
            ),
            workflowEvents: shouldLog
              ? workflowEntry(
                  state.workflowEvents,
                  event,
                  agent.display_name,
                  `${agent.phase}: ${agent.message}`,
                  logStatus,
                )
              : state.workflowEvents,
            agentLogs: shouldLog
              ? agentLogEntry(
                  state.agentLogs,
                  event,
                  [agent.agent],
                  "Status updated",
                  `${agent.phase}: ${agent.message}`,
                  logStatus,
                  { dedupeKey: `${event.type}:${agent.agent}:${event.timestamp}` },
                )
              : state.agentLogs,
            lastEvent: event,
            lastEventAt: event.timestamp,
          };
        }

        if (event.type === "agent.finding.created") {
          const payload = event.payload as Omit<AgentFinding, "created_at">;
          const finding = { ...payload, created_at: event.timestamp };
          const agentFindings = state.agentFindings.filter((item) => item.id !== finding.id);
          return {
            agentFindings: [...agentFindings, finding].sort(
              (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
            ),
            workflowEvents: workflowEntry(
              state.workflowEvents,
              event,
              "Finding created",
              `${finding.agent_name.replace(/_/g, " ")}: ${finding.finding}`,
              "complete",
            ),
            agentLogs: agentLogEntry(
              state.agentLogs,
              event,
              [finding.agent_name],
              "Finding created",
              finding.finding,
              "complete",
              { dedupeKey: `${event.type}:${finding.id}` },
            ),
            lastEvent: event,
            lastEventAt: event.timestamp,
          };
        }

        if (event.type === "mission_patch.created" || event.type === "mission_patch.updated") {
          const payload = event.payload as {
            id: string;
            status: string;
            severity: string;
            summary: string;
            actions: MissionPatch["actions"];
            approval_required: boolean;
            incident_id?: string | null;
            evidence?: Record<string, unknown> | Record<string, unknown>[];
            rollback_plan?: Record<string, unknown>;
          };
          const patchAgents = patchPayloadAgents(payload, state);
          const isUpdatedPatch = event.type === "mission_patch.updated";
          let agentLogs = agentLogEntry(
            state.agentLogs,
            event,
            ["commander_agent"],
            isUpdatedPatch ? "Mission patch refreshed" : "Mission patch generated",
            payload.summary,
            "running",
            { dedupeKey: `${event.type}:${payload.id}:commander`, missionPatchId: payload.id },
          );
          agentLogs = agentLogEntry(
            agentLogs,
            event,
            patchAgents,
            isUpdatedPatch ? "Patch evidence refreshed" : "Patch handoff",
            isUpdatedPatch
              ? "Commander refreshed the approval package with current agent evidence."
              : "Commander included this agent report in the approval package.",
            "running",
            { dedupeKey: `${event.type}:${payload.id}:handoff`, missionPatchId: payload.id },
          );
          return {
            missionPatch: {
              id: payload.id,
              incident_id: payload.incident_id ?? "",
              severity: payload.severity,
              status: payload.status,
              summary: payload.summary,
              evidence: payload.evidence ?? [],
              actions: payload.actions ?? [],
              rollback_plan: payload.rollback_plan ?? {},
              approval_required: payload.approval_required,
            },
            patchMode: "pending",
            workflowEvents: workflowEntry(
              state.workflowEvents,
              event,
              isUpdatedPatch ? "Mission patch refreshed" : "Mission patch",
              payload.summary,
              "running",
            ),
            agentLogs,
            lastEvent: event,
            lastEventAt: event.timestamp,
            demoResetAt: null,
          };
        }

        if (event.type === "simulator.reset") {
          return {
            incidents: [],
            agentFindings: [],
            missionPatch: null,
            commands: [],
            workflowEvents: workflowEntry([], event, "Reset baseline", "All agents monitoring", "complete"),
            agentLogs: resetAgentLogs(event, state.agents),
            patchMode: "pending",
            lastEvent: event,
            lastEventAt: event.timestamp,
            demoResetAt: event.timestamp,
          };
        }

        if (event.type === "mission_patch.approved" || event.type === "mission_patch.executing") {
          const payload = event.payload as { id: string; status: string };
          const relatedAgents = activePatchAgentNames(state);
          let agentLogs = agentLogEntry(
            state.agentLogs,
            event,
            ["commander_agent"],
            event.type === "mission_patch.executing" ? "Patch executing" : "Patch approved",
            payload.status,
            event.type === "mission_patch.executing" ? "running" : "complete",
            { dedupeKey: `${event.type}:${payload.id}:commander`, missionPatchId: payload.id },
          );
          agentLogs = agentLogEntry(
            agentLogs,
            event,
            relatedAgents,
            "Approval state",
            event.type === "mission_patch.executing"
              ? "Executor is running commands from this agent's recommendations."
              : "Human approval received for related controls.",
            event.type === "mission_patch.executing" ? "running" : "complete",
            { dedupeKey: `${event.type}:${payload.id}:agents`, missionPatchId: payload.id },
          );
          return {
            missionPatch:
              state.missionPatch?.id === payload.id
                ? { ...state.missionPatch, status: payload.status }
                : state.missionPatch,
            patchMode: event.type === "mission_patch.executing" ? "execute" : "execute",
            workflowEvents: workflowEntry(state.workflowEvents, event, "Mission patch approved", payload.status, "complete"),
            agentLogs,
            lastEvent: event,
            lastEventAt: event.timestamp,
            demoResetAt: null,
          };
        }

        if (event.type === "mission_patch.rejected") {
          const payload = event.payload as { id: string; status: string };
          const relatedAgents = activePatchAgentNames(state);
          let agentLogs = agentLogEntry(
            state.agentLogs,
            event,
            ["commander_agent"],
            "Patch rejected",
            payload.status,
            "blocked",
            { dedupeKey: `${event.type}:${payload.id}:commander`, missionPatchId: payload.id },
          );
          agentLogs = agentLogEntry(
            agentLogs,
            event,
            relatedAgents,
            "Approval state",
            "Human rejected the related patch.",
            "blocked",
            { dedupeKey: `${event.type}:${payload.id}:agents`, missionPatchId: payload.id },
          );
          return {
            missionPatch:
              state.missionPatch?.id === payload.id
                ? { ...state.missionPatch, status: payload.status }
                : state.missionPatch,
            patchMode: "reject",
            workflowEvents: workflowEntry(state.workflowEvents, event, "Mission patch rejected", payload.status, "blocked"),
            agentLogs,
            lastEvent: event,
            lastEventAt: event.timestamp,
          };
        }

        if (event.type === "command.batch_created") {
          const payload = event.payload as { mission_patch_id?: string; command_count?: number };
          const relatedAgents = activePatchAgentNames(state);
          let agentLogs = agentLogEntry(
            state.agentLogs,
            event,
            ["commander_agent"],
            "Commands queued",
            `${payload.command_count ?? "approved"} executor command${payload.command_count === 1 ? "" : "s"} queued.`,
            "running",
            { dedupeKey: `${event.type}:${payload.mission_patch_id ?? event.timestamp}:commander`, missionPatchId: payload.mission_patch_id },
          );
          agentLogs = agentLogEntry(
            agentLogs,
            event,
            relatedAgents,
            "Commands queued",
            "Executor queued controls related to this agent report.",
            "running",
            { dedupeKey: `${event.type}:${payload.mission_patch_id ?? event.timestamp}:agents`, missionPatchId: payload.mission_patch_id },
          );
          return {
            patchMode: "execute",
            workflowEvents: workflowEntry(state.workflowEvents, event, "Commands queued", "Executor received approved patch", "running"),
            agentLogs,
            lastEvent: event,
            lastEventAt: event.timestamp,
            demoResetAt: null,
          };
        }

        if (event.type === "command.started") {
          const payload = event.payload as {
            id: string;
            mission_patch_id: string;
            action_type: string;
            status: string;
          };
          const relatedAgents = agentsForCommand(payload.action_type, state);
          return {
            commands: upsertCommand(payload),
            patchMode: "execute",
            workflowEvents: workflowEntry(
              state.workflowEvents,
              event,
              "Command started",
              payload.action_type,
              "running",
              `${event.type}:${payload.id}`,
            ),
            agentLogs: agentLogEntry(
              state.agentLogs,
              event,
              relatedAgents,
              "Command started",
              payload.action_type,
              "running",
              {
                dedupeKey: `${event.type}:${payload.id}`,
                commandId: payload.id,
                missionPatchId: payload.mission_patch_id,
              },
            ),
            lastEvent: event,
            lastEventAt: event.timestamp,
          };
        }

        if (event.type === "command.succeeded") {
          const payload = event.payload as {
            id: string;
            mission_patch_id: string;
            action_type: string;
            status: string;
            result: Record<string, unknown>;
          };
          const relatedAgents = agentsForCommand(payload.action_type, state);
          return {
            commands: upsertCommand(payload),
            patchMode: "verify",
            workflowEvents: workflowEntry(
              state.workflowEvents,
              event,
              "Command succeeded",
              payload.action_type,
              "complete",
              `${event.type}:${payload.id}`,
            ),
            agentLogs: agentLogEntry(
              state.agentLogs,
              event,
              relatedAgents,
              "Command succeeded",
              payload.action_type,
              "complete",
              {
                dedupeKey: `${event.type}:${payload.id}`,
                commandId: payload.id,
                missionPatchId: payload.mission_patch_id,
              },
            ),
            lastEvent: event,
            lastEventAt: event.timestamp,
          };
        }

        if (event.type === "verification.completed") {
          const payload = event.payload as { mission_patch_id: string; status: string };
          const relatedAgents = activePatchAgentNames(state);
          let agentLogs = agentLogEntry(
            state.agentLogs,
            event,
            ["commander_agent"],
            "Verification completed",
            payload.status,
            "complete",
            { dedupeKey: `${event.type}:${payload.mission_patch_id}:commander`, missionPatchId: payload.mission_patch_id },
          );
          agentLogs = agentLogEntry(
            agentLogs,
            event,
            relatedAgents,
            "Verification completed",
            "Executor verified the controls related to this agent report.",
            "complete",
            { dedupeKey: `${event.type}:${payload.mission_patch_id}:agents`, missionPatchId: payload.mission_patch_id },
          );
          return {
            missionPatch:
              state.missionPatch?.id === payload.mission_patch_id
                ? { ...state.missionPatch, status: payload.status }
                : state.missionPatch,
            patchMode: "verified",
            workflowEvents: workflowEntry(state.workflowEvents, event, "Verification complete", payload.status, "complete"),
            agentLogs,
            lastEvent: event,
            lastEventAt: event.timestamp,
          };
        }

        if (event.type === "simulator.injected") {
          const payload = event.payload as { issue?: string };
          const issue = String(payload.issue ?? "manual input");
          const relatedAgents = agentsForInjectedIssue(issue);
          return {
            workflowEvents: workflowEntry(
              state.workflowEvents,
              event,
              "Simulation injected",
              issue.replace(/-/g, " "),
              "complete",
            ),
            agentLogs: agentLogEntry(
              state.agentLogs,
              event,
              relatedAgents,
              "Operator input",
              issue.replace(/-/g, " "),
              "complete",
              { dedupeKey: `${event.type}:${issue}:${event.timestamp}` },
            ),
            lastEvent: event,
            lastEventAt: event.timestamp,
          };
        }

        if (event.type === "thermal.image.analysis_completed") {
          const payload = event.payload as { analysis_status?: string; image_id?: string; asset_id?: string };
          const blocked = String(payload.analysis_status ?? "").includes("blocked");
          return {
            workflowEvents: workflowEntry(
              state.workflowEvents,
              event,
              "Thermal AI analysis",
              String(payload.analysis_status ?? "completed").replace(/_/g, " "),
              blocked ? "blocked" : "complete",
            ),
            agentLogs: agentLogEntry(
              state.agentLogs,
              event,
              ["thermal_physical_agent"],
              "Thermal AI analysis",
              `${String(payload.analysis_status ?? "completed").replace(/_/g, " ")} on ${payload.asset_id ?? "thermal frame"}`,
              blocked ? "blocked" : "complete",
              { dedupeKey: `${event.type}:${payload.image_id ?? event.timestamp}` },
            ),
            lastEvent: event,
            lastEventAt: event.timestamp,
          };
        }

        return { lastEvent: event, lastEventAt: event.timestamp };
      }),
  })),
);

function workflowEntry(
  existing: WorkflowEventItem[],
  event: BackendLiveEvent,
  label: string,
  detail: string,
  status: WorkflowEventItem["status"],
  dedupeKey?: string,
): WorkflowEventItem[] {
  const id = dedupeKey ?? `${event.type}-${event.timestamp}-${label}`;
  return [
    {
      id,
      time: event.timestamp,
      label,
      detail,
      status,
    },
    ...existing.filter((item) => item.id !== id),
  ].slice(0, 12);
}

function agentEventStatus(agent: AgentStatusItem): WorkflowEventItem["status"] {
  const value = `${agent.status} ${agent.phase}`.toLowerCase();
  if (value.includes("approval") || value.includes("blocked") || value.includes("failed")) return "blocked";
  if (value.includes("propos") || value.includes("analy") || value.includes("detect") || value.includes("running")) {
    return "running";
  }
  return "info";
}

const KNOWN_AGENTS = [
  "workload_agent",
  "thermal_physical_agent",
  "power_orbit_agent",
  "radiation_integrity_agent",
  "checkpoint_downlink_agent",
  "vibration_health_agent",
  "commander_agent",
];

const ISSUE_AGENT_MAP: Record<string, string[]> = {
  "workload-stall": ["workload_agent"],
  "thermal-frame": ["thermal_physical_agent"],
  "eclipse-risk": ["power_orbit_agent"],
  "radiation-spike": ["radiation_integrity_agent"],
  "downlink-constraint": ["checkpoint_downlink_agent"],
  "vibration-fault": ["vibration_health_agent"],
};

const ACTION_AGENT_FALLBACKS: Record<string, string[]> = {
  mark_checkpoint_suspect: ["radiation_integrity_agent"],
  rollback_training: ["radiation_integrity_agent", "workload_agent"],
  cordon_node: ["radiation_integrity_agent", "thermal_physical_agent"],
  mark_node_suspect: ["thermal_physical_agent", "vibration_health_agent"],
  set_gpu_power_limit: ["thermal_physical_agent", "power_orbit_agent"],
  increase_checkpoint_frequency: ["power_orbit_agent", "checkpoint_downlink_agent"],
  transfer_priority: ["checkpoint_downlink_agent"],
  snapshot_evidence: ["thermal_physical_agent", "vibration_health_agent", "radiation_integrity_agent"],
  run_health_check: ["workload_agent", "thermal_physical_agent", "vibration_health_agent"],
  pause_job: ["workload_agent"],
};

function appendAgentLogItem(existing: Record<string, AgentLogItem[]>, log: AgentLogItem): Record<string, AgentLogItem[]> {
  return {
    ...existing,
    [log.agent]: [log, ...(existing[log.agent] ?? []).filter((item) => item.id !== log.id)].slice(0, 48),
  };
}

function agentLogEntry(
  existing: Record<string, AgentLogItem[]>,
  event: BackendLiveEvent,
  agents: string[],
  label: string,
  detail: string,
  status: WorkflowEventItem["status"],
  options: {
    dedupeKey?: string;
    commandId?: string;
    missionPatchId?: string;
  } = {},
): Record<string, AgentLogItem[]> {
  return uniqueAgents(agents).reduce((logs, agent) => {
    const id = `${options.dedupeKey ?? `${event.type}:${event.timestamp}:${label}`}:${agent}`;
    return appendAgentLogItem(logs, {
      id,
      agent,
      time: event.timestamp,
      label,
      detail,
      status,
      eventType: event.type,
      commandId: options.commandId,
      missionPatchId: options.missionPatchId,
    });
  }, existing);
}

function resetAgentLogs(event: BackendLiveEvent, agents: AgentStatusItem[]): Record<string, AgentLogItem[]> {
  const agentNames = agents.length ? agents.map((agent) => agent.agent) : KNOWN_AGENTS;
  return agentLogEntry({}, event, agentNames, "Reset baseline", "Monitoring assigned domain.", "complete", {
    dedupeKey: `${event.type}:${event.timestamp}`,
  });
}

function agentsForInjectedIssue(issue: string): string[] {
  return ISSUE_AGENT_MAP[issue] ?? ["commander_agent"];
}

function agentsForCommand(actionType: string, state: WorldStore): string[] {
  const fromFindings = state.agentFindings
    .filter((finding) => finding.recommended_actions.includes(actionType))
    .map((finding) => finding.agent_name);
  return fromFindings.length ? uniqueAgents(fromFindings) : (ACTION_AGENT_FALLBACKS[actionType] ?? ["commander_agent"]);
}

function activePatchAgentNames(state: WorldStore): string[] {
  const fromPatch = state.missionPatch ? patchEvidenceAgentNames(state.missionPatch.evidence) : [];
  if (fromPatch.length) {
    return fromPatch;
  }
  return uniqueAgents(state.agentFindings.filter((finding) => finding.status === "open").map((finding) => finding.agent_name));
}

function patchPayloadAgents(
  payload: { evidence?: Record<string, unknown> | Record<string, unknown>[] },
  state: WorldStore,
): string[] {
  const fromEvidence = patchEvidenceAgentNames(payload.evidence ?? []);
  if (fromEvidence.length) {
    return fromEvidence;
  }
  return activePatchAgentNames(state);
}

function patchEvidenceAgentNames(evidence: Record<string, unknown> | Record<string, unknown>[]): string[] {
  const items = Array.isArray(evidence) ? evidence : [evidence];
  return uniqueAgents(
    items
      .map((item) => item?.agent)
      .filter((agent): agent is string => typeof agent === "string" && agent.length > 0),
  );
}

function uniqueAgents(agents: string[]): string[] {
  return [...new Set(agents.filter((agent) => typeof agent === "string" && agent.length > 0))];
}
