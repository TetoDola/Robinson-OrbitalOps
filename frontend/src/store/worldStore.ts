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

interface WorldStore {
  worldState: WorldState | null;
  worldVersion: number | null;
  scenarioRunId: string | null;
  telemetry: TelemetrySnapshot;
  agents: AgentStatusItem[];
  agentRuntime: AgentRuntimeItem[];
  aiStatus: AiStatusResponse | null;
  workflowEvents: WorkflowEventItem[];
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
  setAgents: (agents: AgentStatusItem[]) => void;
  upsertAgent: (agent: AgentStatusItem) => void;
  setAgentRuntime: (agents: AgentRuntimeItem[]) => void;
  upsertAgentRuntime: (agent: AgentRuntimeItem) => void;
  setAiStatus: (aiStatus: AiStatusResponse | null) => void;
  pushWorkflowEvent: (event: WorkflowEventItem) => void;
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
    agents: [],
    agentRuntime: [],
    aiStatus: null,
    workflowEvents: [],
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
                  agent.status === "proposing" || agent.status === "analyzing" ? "running" : "info",
                )
              : state.workflowEvents,
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
            lastEvent: event,
            lastEventAt: event.timestamp,
          };
        }

        if (event.type === "mission_patch.created") {
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
            workflowEvents: workflowEntry(state.workflowEvents, event, "Mission patch", payload.summary, "running"),
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
            patchMode: "pending",
            lastEvent: event,
            lastEventAt: event.timestamp,
            demoResetAt: event.timestamp,
          };
        }

        if (event.type === "mission_patch.approved" || event.type === "mission_patch.executing") {
          const payload = event.payload as { id: string; status: string };
          return {
            missionPatch:
              state.missionPatch?.id === payload.id
                ? { ...state.missionPatch, status: payload.status }
                : state.missionPatch,
            patchMode: event.type === "mission_patch.executing" ? "execute" : "execute",
            workflowEvents: workflowEntry(state.workflowEvents, event, "Mission patch approved", payload.status, "complete"),
            lastEvent: event,
            lastEventAt: event.timestamp,
            demoResetAt: null,
          };
        }

        if (event.type === "mission_patch.rejected") {
          const payload = event.payload as { id: string; status: string };
          return {
            missionPatch:
              state.missionPatch?.id === payload.id
                ? { ...state.missionPatch, status: payload.status }
                : state.missionPatch,
            patchMode: "reject",
            workflowEvents: workflowEntry(state.workflowEvents, event, "Mission patch rejected", payload.status, "blocked"),
            lastEvent: event,
            lastEventAt: event.timestamp,
          };
        }

        if (event.type === "command.batch_created") {
          return {
            patchMode: "execute",
            workflowEvents: workflowEntry(state.workflowEvents, event, "Commands queued", "Executor received approved patch", "running"),
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
          return {
            commands: upsertCommand(payload),
            patchMode: "execute",
            workflowEvents: workflowEntry(state.workflowEvents, event, "Command started", payload.action_type, "running"),
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
          return {
            commands: upsertCommand(payload),
            patchMode: "verify",
            workflowEvents: workflowEntry(state.workflowEvents, event, "Command succeeded", payload.action_type, "complete"),
            lastEvent: event,
            lastEventAt: event.timestamp,
          };
        }

        if (event.type === "verification.completed") {
          const payload = event.payload as { mission_patch_id: string; status: string };
          return {
            missionPatch:
              state.missionPatch?.id === payload.mission_patch_id
                ? { ...state.missionPatch, status: payload.status }
                : state.missionPatch,
            patchMode: "verified",
            workflowEvents: workflowEntry(state.workflowEvents, event, "Verification complete", payload.status, "complete"),
            lastEvent: event,
            lastEventAt: event.timestamp,
          };
        }

        if (event.type === "simulator.injected") {
          const payload = event.payload as { issue?: string };
          return {
            workflowEvents: workflowEntry(
              state.workflowEvents,
              event,
              "Simulation injected",
              String(payload.issue ?? "manual input").replace(/-/g, " "),
              "complete",
            ),
            lastEvent: event,
            lastEventAt: event.timestamp,
          };
        }

        if (event.type === "thermal.image.analysis_completed") {
          const payload = event.payload as { analysis_status?: string };
          const blocked = String(payload.analysis_status ?? "").includes("blocked");
          return {
            workflowEvents: workflowEntry(
              state.workflowEvents,
              event,
              "Thermal AI analysis",
              String(payload.analysis_status ?? "completed").replace(/_/g, " "),
              blocked ? "blocked" : "complete",
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
): WorkflowEventItem[] {
  return [
    {
      id: `${event.type}-${event.timestamp}-${label}`,
      time: event.timestamp,
      label,
      detail,
      status,
    },
    ...existing,
  ].slice(0, 12);
}
