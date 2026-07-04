export type Severity = "INFO" | "WARN" | "WARNING" | "YELLOW" | "ORANGE" | "RED" | "CRITICAL" | string;

export interface SatelliteState {
  id: string;
  lat: number;
  lon: number;
  alt_km: number;
  velocity_km_s: number;
  orbit_phase: string;
  time_to_eclipse_min: number;
  ground_link: string;
}

export interface PowerState {
  battery_percent: number;
  solar_kw: number;
  compute_budget_kw: number;
  cooling_power_kw: number;
  comms_power_kw: number;
  mode: string;
}

export interface ThermalState {
  highest_temp_c: number;
  hotspot_node: string;
  cooling_status: string;
}

export interface RadiationState {
  risk: string;
  region: string;
  ecc_errors_last_5min: number;
  xid_event: boolean;
}

export interface DownlinkState {
  window_open: boolean;
  capacity_gb: number;
  used_gb: number;
  time_remaining_min: number;
}

export interface TrainingState {
  job_id: string;
  status: string;
  current_step: number;
  last_trusted_checkpoint: string;
  latest_checkpoint: string;
  latest_checkpoint_status: string;
  loss_state: string;
}

export interface NodeState {
  id: string;
  status: string;
  gpu_util?: number;
  temp_c?: number;
  power_w?: number;
  rank_lag?: number;
  ecc_errors?: number;
  xid_event?: boolean;
  vibration_score?: number;
}

export interface WorldState {
  scenario: string;
  scenario_name: string;
  tick: number;
  satellite: SatelliteState;
  power: PowerState;
  thermal: ThermalState;
  radiation: RadiationState;
  downlink: DownlinkState;
  training: TrainingState;
  nodes: NodeState[];
  agents: string[];
  active_mission_patch: string | MissionPatch | null;
}

export interface WorldStateResponse {
  version: number;
  scenario_run_id: string | null;
  updated_by: string;
  updated_at: string;
  state: WorldState;
}

export interface AgentStatusItem {
  agent: string;
  display_name: string;
  status: string;
  phase: string;
  severity: Severity;
  message: string;
  updated_at?: string;
  linked_mission_patch_id?: string | null;
}

export interface AgentsStatusResponse {
  agents: AgentStatusItem[];
}

export interface Incident {
  id: string;
  incident_key: string;
  title: string;
  severity: Severity;
  status: string;
  finding_ids: string[];
  summary: string;
}

export interface IncidentsResponse {
  incidents: Incident[];
}

export interface MissionPatchAction {
  type: string;
  node_id?: string;
  job_id?: string;
  checkpoint_id?: string;
  target_asset_id?: string;
  [key: string]: unknown;
}

export interface MissionPatch {
  id: string;
  incident_id: string;
  severity: Severity;
  status: string;
  summary: string;
  evidence: Record<string, unknown>;
  actions: MissionPatchAction[];
  rollback_plan: Record<string, unknown>;
  approval_required: boolean;
}

export interface ActiveMissionPatchResponse {
  mission_patch: MissionPatch | null;
}

export interface Command {
  id: string;
  mission_patch_id: string;
  action_type: string;
  target_asset_id: string | null;
  status: string;
  input: Record<string, unknown>;
  result: Record<string, unknown>;
}

export interface CommandsResponse {
  commands: Command[];
}

export interface LiveEventBase<TType extends string, TPayload> {
  type: TType;
  timestamp: string;
  payload: TPayload;
}

export type HeartbeatEvent = LiveEventBase<"heartbeat", { status: string }>;

export type WorldStateUpdatedEvent = LiveEventBase<
  "world_state.updated",
  {
    version: number;
    scenario_run_id: string | null;
    state: WorldState;
  }
>;

export type AgentStatusUpdatedEvent = LiveEventBase<
  "agent.status.updated",
  Omit<AgentStatusItem, "updated_at"> & { linked_mission_patch_id?: string | null }
>;

export type MissionPatchApprovedEvent = LiveEventBase<
  "mission_patch.approved",
  {
    id: string;
    status: string;
  }
>;

export type CommandBatchCreatedEvent = LiveEventBase<
  "command.batch_created",
  {
    mission_patch_id: string;
    command_count: number;
  }
>;

export type BackendLiveEvent =
  | HeartbeatEvent
  | WorldStateUpdatedEvent
  | AgentStatusUpdatedEvent
  | MissionPatchApprovedEvent
  | CommandBatchCreatedEvent
  | LiveEventBase<string, unknown>;
