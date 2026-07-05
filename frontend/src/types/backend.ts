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
  latest_visual_input?: ThermalVisualInput | null;
}

export interface ThermalVisualInput {
  id: string;
  asset_id: string;
  source: string;
  notes?: string | null;
  received_at: string;
  image_data_url: string;
  analysis_status: string;
  model_result?: ThermalModelResult | null;
}

export interface ThermalModelResult {
  summary?: string;
  confidence?: number | null;
  affected_assets?: string[];
  evidence?: string[];
  risk?: string;
  recommended_actions?: string[];
  questions?: string[];
  needs_human_review?: boolean;
  model?: string;
  provider?: string;
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

export interface AgentRuntimeItem {
  agent: string;
  display_name: string;
  trigger_mode: string;
  interval_seconds: number;
  run_state: string;
  last_run_at: string;
  next_run_at: string;
  seconds_until_next_run: number;
  missed_runs: number;
  last_result: string;
}

export interface AgentsRuntimeResponse {
  agents: AgentRuntimeItem[];
}

export interface AiStatusResponse {
  provider: string;
  enabled: boolean;
  configured: boolean;
  status: string;
  text_model: string;
  multimodal_model: string;
}

export interface AgentFinding {
  id: string;
  agent_name: string;
  severity: Severity;
  confidence: number;
  affected_assets: string[];
  finding: string;
  evidence: string[];
  risk: string | null;
  recommended_actions: string[];
  status: string;
  created_at: string;
}

export interface AgentFindingsResponse {
  findings: AgentFinding[];
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
  evidence: Record<string, unknown> | Record<string, unknown>[];
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

export interface SimulatorInjectRequest {
  image_data_url?: string | null;
  asset_id?: string;
  source?: string;
  notes?: string | null;
}

export interface SimulatorInjectResponse {
  issue: string;
  status: string;
  world_state_version: number;
  finding_ids: string[];
  image_id?: string | null;
  mission_patch_id?: string | null;
  analysis_status?: string | null;
  model_result?: ThermalModelResult | null;
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

export type AgentFindingCreatedEvent = LiveEventBase<
  "agent.finding.created",
  Omit<AgentFinding, "created_at"> & { agent_name: string }
>;

export type MissionPatchCreatedEvent = LiveEventBase<
  "mission_patch.created",
  {
    id: string;
    status: string;
    severity: Severity;
    summary: string;
    actions: MissionPatchAction[];
    approval_required: boolean;
    incident_id?: string | null;
    evidence?: Record<string, unknown> | Record<string, unknown>[];
    rollback_plan?: Record<string, unknown>;
  }
>;

export type MissionPatchApprovedEvent = LiveEventBase<
  "mission_patch.approved",
  {
    id: string;
    status: string;
  }
>;

export type MissionPatchExecutingEvent = LiveEventBase<
  "mission_patch.executing",
  {
    id: string;
    status: string;
  }
>;

export type MissionPatchRejectedEvent = LiveEventBase<
  "mission_patch.rejected",
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

export type SimulatorResetEvent = LiveEventBase<
  "simulator.reset",
  {
    scenario: string;
    scenario_run_id: string;
    status: string;
  }
>;

export type CommandStartedEvent = LiveEventBase<
  "command.started",
  {
    id: string;
    mission_patch_id: string;
    action_type: string;
    status: string;
  }
>;

export type CommandSucceededEvent = LiveEventBase<
  "command.succeeded",
  {
    id: string;
    mission_patch_id: string;
    action_type: string;
    status: string;
    result: Record<string, unknown>;
  }
>;

export type VerificationCompletedEvent = LiveEventBase<
  "verification.completed",
  {
    mission_patch_id: string;
    status: string;
  }
>;

export type BackendLiveEvent =
  | HeartbeatEvent
  | WorldStateUpdatedEvent
  | AgentStatusUpdatedEvent
  | AgentFindingCreatedEvent
  | MissionPatchCreatedEvent
  | MissionPatchApprovedEvent
  | MissionPatchExecutingEvent
  | MissionPatchRejectedEvent
  | CommandBatchCreatedEvent
  | SimulatorResetEvent
  | CommandStartedEvent
  | CommandSucceededEvent
  | VerificationCompletedEvent
  | LiveEventBase<string, unknown>;
