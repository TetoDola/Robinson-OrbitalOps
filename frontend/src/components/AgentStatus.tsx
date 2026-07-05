import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";

import { useWorldStore } from "../store/worldStore";
import type {
  AgentFinding,
  AgentRuntimeItem,
  AgentStatusItem,
  Command,
  Incident,
  MissionPatchAction,
  NodeState,
  ThermalVisualInput,
  WorldState,
} from "../types/backend";

type Tone = "nominal" | "warn" | "critical";

interface SignalRow {
  label: string;
  value: string;
  limit?: string;
  tone?: Tone;
}

const fallbackAgents: AgentStatusItem[] = [
  {
    agent: "workload_agent",
    display_name: "Workload Agent",
    status: "monitoring",
    phase: "monitor",
    severity: "INFO",
    message: "Scheduler and GPU utilization are aligned.",
  },
  {
    agent: "thermal_physical_agent",
    display_name: "Thermal / Physical Agent",
    status: "monitoring",
    phase: "monitor",
    severity: "INFO",
    message: "Node temperatures are in nominal range.",
  },
  {
    agent: "power_orbit_agent",
    display_name: "Power / Orbit Agent",
    status: "monitoring",
    phase: "monitor",
    severity: "INFO",
    message: "Orbit and battery envelope are stable.",
  },
  {
    agent: "radiation_integrity_agent",
    display_name: "Radiation / Integrity Agent",
    status: "monitoring",
    phase: "monitor",
    severity: "INFO",
    message: "ECC and NaN checks are within expected envelope.",
  },
  {
    agent: "checkpoint_downlink_agent",
    display_name: "Checkpoint / Downlink Agent",
    status: "monitoring",
    phase: "monitor",
    severity: "INFO",
    message: "Checkpoint size and downlink capacity are healthy.",
  },
];

const detectorScope: Record<string, string> = {
  workload_agent: "Scheduler truth, GPU utilization, rank lag, worker progress, orphan process evidence.",
  thermal_physical_agent: "Rack temperature, node hotspot, IR inspection result, cooling state, contact vibration.",
  power_orbit_agent: "Battery state, solar input, orbit phase, eclipse countdown, compute and cooling load.",
  radiation_integrity_agent: "ECC trend, Xid events, checkpoint trust, NaN loss, rank divergence evidence.",
  checkpoint_downlink_agent: "Checkpoint size, transfer priority, contact window, downlink capacity, ground recovery artifacts.",
  vibration_health_agent: "Structure-borne contact sensor trend, frequency shift, thermal correlation, cooling-loop risk.",
  commander_agent: "Open findings, affected assets, safety validator output, patch status, approval boundary.",
};

function workStateClass(agent: AgentStatusItem, missionPatchActive: boolean): string {
  const value = `${agent.status} ${agent.phase}`.toLowerCase();
  if (missionPatchActive && agent.agent === "commander_agent") return "status-orange";
  if (value.includes("monitor") || value.includes("healthy")) return "status-green";
  if (value.includes("analy") || value.includes("detect") || value.includes("running")) return "status-cyan";
  if (value.includes("propos") || value.includes("planning")) return "status-orange";
  if (value.includes("blocked") || value.includes("failed")) return "status-red";
  return "status-cyan";
}

function workStateLabel(agent: AgentStatusItem, missionPatchActive: boolean): string {
  if (missionPatchActive && agent.agent === "commander_agent") return "patch ready";
  const value = agent.status || agent.phase;
  if (value === "healthy" || value === "scheduled") return "monitoring";
  return humanize(value);
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

function formatConfidence(finding: AgentFinding | undefined): string {
  if (!finding) return "pending";
  return `${Math.round(finding.confidence * 100)}%`;
}

function formatDate(value: string | undefined): string {
  if (!value) return "not recorded";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "not recorded";
  return parsed.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function secondsUntil(value: string | undefined, nowMs: number): number | null {
  if (!value) return null;
  const target = new Date(value).getTime();
  if (Number.isNaN(target)) return null;
  return Math.max(0, Math.round((target - nowMs) / 1000));
}

function formatSeconds(value: number | null | undefined): string {
  if (value === null || value === undefined) return "--";
  if (value <= 0) return "due";
  const minutes = Math.floor(value / 60);
  const seconds = value % 60;
  return minutes > 0 ? `${minutes}m ${seconds.toString().padStart(2, "0")}s` : `${seconds}s`;
}

function formatInterval(seconds: number | undefined): string {
  if (!seconds) return "--";
  if (seconds % 60 === 0) return `${seconds / 60} min`;
  return `${seconds}s`;
}

function actionLabel(action: string | MissionPatchAction): string {
  if (typeof action === "string") return humanize(action);
  return humanize(String(action.type ?? "action"));
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

function buildSignalRows(agentName: string, worldState: WorldState | null, openFindings: number, commandCount: number): SignalRow[] {
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
        { label: "ecc last 5 min", value: String(worldState?.radiation.ecc_errors_last_5min ?? "--"), limit: ">900", tone: (worldState?.radiation.ecc_errors_last_5min ?? 0) > 900 ? "critical" : "nominal" },
        { label: "xid event", value: yesNo(worldState?.radiation.xid_event), limit: "any true", tone: worldState?.radiation.xid_event ? "critical" : "nominal" },
        { label: "loss state", value: worldState?.training.loss_state ?? "--", tone: worldState?.training.loss_state?.includes("nan") ? "critical" : "nominal" },
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
        { label: "active patch", value: worldState?.active_mission_patch ? "present" : "none" },
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

function assetsFromSignals(signalRows: SignalRow[]): string {
  return signalRows.map((row) => `${row.label}: ${row.value}`).join(" | ");
}

interface AgentDetailModalProps {
  agent: AgentStatusItem;
  latestFinding?: AgentFinding;
  history: AgentFinding[];
  relatedIncident?: Incident;
  relatedCommands: Command[];
  patchActions: MissionPatchAction[];
  linkedPatchId?: string | null;
  worldState: WorldState | null;
  runtime?: AgentRuntimeItem;
  openFindingCount: number;
  commandCount: number;
  nowMs: number;
  onClose: () => void;
}

function AgentDetailModal({
  agent,
  latestFinding,
  history,
  relatedIncident,
  relatedCommands,
  patchActions,
  linkedPatchId,
  worldState,
  runtime,
  openFindingCount,
  commandCount,
  nowMs,
  onClose,
}: AgentDetailModalProps) {
  const actions = latestFinding?.recommended_actions?.length
    ? latestFinding.recommended_actions
    : patchActions.map((action) => String(action.type));
  const evidence = latestFinding?.evidence?.length ? latestFinding.evidence : [agent.message];
  const assets = latestFinding?.affected_assets?.length ? latestFinding.affected_assets : [];
  const signalRows = buildSignalRows(agent.agent, worldState, openFindingCount, relatedCommands.length || commandCount);
  const nextRunSeconds = secondsUntil(runtime?.next_run_at, nowMs);
  const patchActive = Boolean(linkedPatchId || worldState?.active_mission_patch);
  const thermalInput: ThermalVisualInput | null =
    agent.agent === "thermal_physical_agent" ? (worldState?.thermal.latest_visual_input ?? null) : null;

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
          <section className="agent-modal-section agent-current">
            <div className="section-header compact">
              <div>
                <div className="eyebrow">detector state</div>
                <strong>{workStateLabel(agent, patchActive)}</strong>
              </div>
              <b className={workStateClass(agent, patchActive)}>{workStateLabel(agent, patchActive)}</b>
            </div>
            <p>{agent.message}</p>
            <div className="agent-detail-metrics">
              <div>
                <span className="label">phase</span>
                <strong>{humanize(agent.phase)}</strong>
              </div>
              <div>
                <span className="label">confidence</span>
                <strong>{formatConfidence(latestFinding)}</strong>
              </div>
              <div>
                <span className="label">sample age</span>
                <strong>{formatDate(agent.updated_at)}</strong>
              </div>
              <div>
                <span className="label">run state</span>
                <strong>{runtime?.run_state ?? "scheduled"}</strong>
              </div>
              <div>
                <span className="label">next run</span>
                <strong>{formatSeconds(nextRunSeconds)}</strong>
              </div>
              <div>
                <span className="label">interval</span>
                <strong>{formatInterval(runtime?.interval_seconds)}</strong>
              </div>
            </div>
          </section>

          <section className="agent-modal-section">
            <div className="eyebrow">live inputs</div>
            <div className="agent-signal-table">
              {signalRows.map((row) => (
                <div className="agent-signal-row" key={row.label}>
                  <span>{row.label}</span>
                  <strong className={toneClass(row.tone)}>{row.value}</strong>
                  <small>{row.limit ?? "baseline"}</small>
                </div>
              ))}
            </div>
          </section>

          <section className="agent-modal-section span-2">
            <div className="section-header compact">
              <div>
                <div className="eyebrow">current finding</div>
                <strong>{latestFinding?.finding ?? "No open finding reported"}</strong>
              </div>
              <b className={toneClass(latestFinding ? "warn" : "nominal")}>
                {latestFinding?.status ?? humanize(agent.status)}
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

          {thermalInput ? (
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
                <strong>{relatedCommands.length}</strong>
              </div>
            </div>
          </section>

          <section className="agent-modal-section span-2">
            <div className="section-header compact">
              <div>
                <div className="eyebrow">recent reports</div>
                <strong>{history.length ? `${history.length} report${history.length === 1 ? "" : "s"}` : "status only"}</strong>
              </div>
              <b className="status-yellow">{assetsFromSignals(signalRows)}</b>
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
                  <b className={workStateClass(agent, patchActive)}>{workStateLabel(agent, patchActive)}</b>
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
  const commands = useWorldStore((state) => state.commands);
  const worldState = useWorldStore((state) => state.worldState);
  const visibleAgents = agents.length > 0 ? agents : fallbackAgents;
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);
  const [nowMs, setNowMs] = useState(Date.now());

  useEffect(() => {
    const interval = window.setInterval(() => setNowMs(Date.now()), 1000);
    return () => window.clearInterval(interval);
  }, []);

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
  const patchActions = missionPatch?.actions ?? [];
  const openFindingCount = agentFindings.filter((finding) => finding.status === "open").length;
  const missionPatchActive = Boolean(missionPatch);

  return (
    <section className="rail-section" aria-label="Independent agent status">
      <div className="eyebrow">detectors</div>
      <div className="agent-status-list">
        {visibleAgents.map((agent) => {
          const runtime = agentRuntime.find((item) => item.agent === agent.agent);
          const nextRun = formatSeconds(secondsUntil(runtime?.next_run_at, nowMs));
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
                <small>next run {nextRun}</small>
              </span>
              <b className={workStateClass(agent, missionPatchActive)}>{workStateLabel(agent, missionPatchActive)}</b>
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
              patchActions={patchActions}
              relatedCommands={relatedCommands}
              relatedIncident={relatedIncident}
              worldState={worldState}
              runtime={agentRuntime.find((item) => item.agent === selectedAgent.agent)}
              openFindingCount={openFindingCount}
              commandCount={commands.length}
              nowMs={nowMs}
              onClose={() => setSelectedAgentId(null)}
            />,
            document.body,
          )
        : null}
    </section>
  );
}
