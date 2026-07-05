import { create } from "zustand";
import { subscribeWithSelector } from "zustand/middleware";

import type {
  AgentStatusItem,
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

/** Raw numeric telemetry, buffered into rolling history for sparklines / meters. */
export interface TelemetryMetrics {
  battery: number;
  solar: number;
  latency: number;
  computeLoad: number;
  eclipseMin: number;
  downlinkWindowGb: number;
  eccErrors: number;
  thermal: number;
}

export type MetricKey = keyof TelemetryMetrics;
export type MetricsHistory = Record<MetricKey, number[]>;

/** ~15 s of trend at the 250 ms telemetry cadence. */
const HISTORY_LEN = 60;

const emptyHistory = (): MetricsHistory => ({
  battery: [],
  solar: [],
  latency: [],
  computeLoad: [],
  eclipseMin: [],
  downlinkWindowGb: [],
  eccErrors: [],
  thermal: [],
});

interface WorldStore {
  worldState: WorldState | null;
  worldVersion: number | null;
  scenarioRunId: string | null;
  telemetry: TelemetrySnapshot;
  radiationRisk: ProcessedRadiationRisk | null;
  metrics: TelemetryMetrics | null;
  metricsHistory: MetricsHistory;
  agents: AgentStatusItem[];
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
  pushMetrics: (metrics: TelemetryMetrics) => void;
  setAgents: (agents: AgentStatusItem[]) => void;
  upsertAgent: (agent: AgentStatusItem) => void;
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
    metrics: null,
    metricsHistory: emptyHistory(),
    agents: [],
    incidents: [],
    missionPatch: null,
    commands: [],
    simSpeed: 1,
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
    pushMetrics: (metrics) =>
      set((state) => {
        const history = { ...state.metricsHistory };
        (Object.keys(metrics) as MetricKey[]).forEach((key) => {
          const next = state.metricsHistory[key].concat(metrics[key]);
          history[key] = next.length > HISTORY_LEN ? next.slice(next.length - HISTORY_LEN) : next;
        });
        return { metrics, metricsHistory: history };
      }),
    setAgents: (agents) => set({ agents }),
    upsertAgent: (agent) =>
      set((state) => {
        const agents = state.agents.filter((item) => item.agent !== agent.agent);
        return { agents: [...agents, agent].sort((a, b) => a.agent.localeCompare(b.agent)) };
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
          return {
            agents: [...agents, { ...agent, updated_at: event.timestamp }].sort((a, b) =>
              a.agent.localeCompare(b.agent),
            ),
            lastEvent: event,
            lastEventAt: event.timestamp,
          };
        }

        if (event.type === "simulator.reset") {
          return {
            incidents: [],
            missionPatch: null,
            commands: [],
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
            lastEvent: event,
            lastEventAt: event.timestamp,
          };
        }

        if (event.type === "command.batch_created") {
          return {
            patchMode: "execute",
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
            lastEvent: event,
            lastEventAt: event.timestamp,
          };
        }

        return { lastEvent: event, lastEventAt: event.timestamp };
      }),
  })),
);
