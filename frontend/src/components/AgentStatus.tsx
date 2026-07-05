import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";

import { useWorldStore } from "../store/worldStore";
import type { AgentFinding, AgentStatusItem, Command, Incident, MissionPatchAction } from "../types/backend";

const fallbackAgents: AgentStatusItem[] = [
  {
    agent: "workload_agent",
    display_name: "Workload Agent",
    status: "investigating",
    phase: "explain",
    severity: "ORANGE",
    message: "Rank 17 all-reduce timeout, orphan worker suspected",
  },
  {
    agent: "thermal_physical_agent",
    display_name: "Thermal Agent",
    status: "investigating",
    phase: "explain",
    severity: "RED",
    message: "Node C hotspot confirmed by IR and rack telemetry",
  },
  {
    agent: "power_orbit_agent",
    display_name: "Power / Orbit Agent",
    status: "planning",
    phase: "propose",
    severity: "ORANGE",
    message: "Eclipse recovery plan required, battery reserve below target",
  },
  {
    agent: "radiation_integrity_agent",
    display_name: "Integrity Agent",
    status: "planning",
    phase: "propose",
    severity: "RED",
    message: "ckpt-184900 suspect after ECC spike and NaN loss",
  },
  {
    agent: "checkpoint_downlink_agent",
    display_name: "Downlink Agent",
    status: "planning",
    phase: "propose",
    severity: "YELLOW",
    message: "22 GB window cannot carry 180 GB full checkpoint",
  },
];

const agentWorkflow: Record<string, string[]> = {
  workload_agent: ["Monitor scheduler and GPU truth", "Detect rank stalls", "Explain workload mismatch", "Propose safe worker recovery"],
  thermal_physical_agent: ["Monitor rack heat and IR frame", "Detect hotspot", "Explain physical risk", "Propose derate or isolation"],
  power_orbit_agent: ["Monitor orbit and power budget", "Detect eclipse pressure", "Explain battery margin", "Propose power-safe actions"],
  radiation_integrity_agent: ["Monitor ECC and training integrity", "Detect corruption evidence", "Explain checkpoint trust", "Propose rollback guardrails"],
  checkpoint_downlink_agent: ["Monitor checkpoint size and contact window", "Detect transfer mismatch", "Explain recovery priority", "Propose manifest and delta order"],
  vibration_health_agent: ["Monitor structure-borne vibration", "Detect mechanical anomaly", "Correlate with thermal risk", "Propose inspection-safe actions"],
  commander_agent: ["Read open findings", "Resolve agent conflicts", "Generate mission patch", "Wait for human approval"],
};

const agentReports: Record<string, string> = {
  workload_agent: "Compares scheduler state with GPU load, rank progress, worker health, and orphan process signals.",
  thermal_physical_agent: "Correlates node temperature, rack health, IR hotspot evidence, coolant loop state, and vibration contact sensors.",
  power_orbit_agent: "Calculates eclipse timing, battery reserve, solar input, compute power, cooling power, and downlink demand.",
  radiation_integrity_agent: "Checks ECC spikes, Xid events, NaN loss, checkpoint trust, and rank divergence. It detects corruption evidence, not exact bit flips.",
  checkpoint_downlink_agent: "Ranks checkpoint artifacts against the active ground contact window so recovery metadata moves before bulky payloads.",
  vibration_health_agent: "Uses contact-sensor vibration trends to flag mechanical cooling-loop risk without treating space as an audio medium.",
  commander_agent: "Fuses independent findings into one safety-checked mission patch and stops at approval until an operator decides.",
};

const phaseOrder = ["monitor", "detect", "explain", "propose", "approve", "execute", "verify"];

function severityClass(severity: string): string {
  const value = severity.toLowerCase();
  if (value.includes("red") || value.includes("critical")) {
    return "severity red";
  }
  if (value.includes("orange") || value.includes("warn")) {
    return "severity orange";
  }
  if (value.includes("yellow")) {
    return "severity yellow";
  }
  return "severity";
}

function statusToneClass(severity: string): string {
  const value = severity.toLowerCase();
  if (value.includes("red") || value.includes("critical")) return "status-red";
  if (value.includes("orange") || value.includes("warn")) return "status-orange";
  if (value.includes("yellow")) return "status-yellow";
  return "";
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

function actionLabel(action: string | MissionPatchAction): string {
  if (typeof action === "string") return humanize(action);
  return humanize(String(action.type ?? "action"));
}

function commandMatchesAgent(command: Command, finding: AgentFinding | undefined): boolean {
  if (!finding) return false;
  return finding.recommended_actions.includes(command.action_type);
}

interface AgentDetailModalProps {
  agent: AgentStatusItem;
  latestFinding?: AgentFinding;
  history: AgentFinding[];
  relatedIncident?: Incident;
  relatedCommands: Command[];
  patchActions: MissionPatchAction[];
  linkedPatchId?: string | null;
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
  onClose,
}: AgentDetailModalProps) {
  const workflow = agentWorkflow[agent.agent] ?? ["Monitor assigned domain", "Detect unsafe state", "Explain evidence", "Propose action"];
  const activePhaseIndex = Math.max(0, phaseOrder.indexOf(agent.phase.toLowerCase()));
  const actions = latestFinding?.recommended_actions?.length
    ? latestFinding.recommended_actions
    : patchActions.map((action) => String(action.type));
  const evidence = latestFinding?.evidence?.length ? latestFinding.evidence : [agent.message];
  const assets = latestFinding?.affected_assets?.length ? latestFinding.affected_assets : [];

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
            <div className="eyebrow">agent command file</div>
            <h2 id="agent-modal-title">{agent.display_name}</h2>
            <p>{agentReports[agent.agent] ?? "Independent agent monitoring assigned OrbitOps domain."}</p>
          </div>
          <button className="close-btn" type="button" aria-label="Close agent details" onClick={onClose}>
            x
          </button>
        </header>

        <div className="agent-modal-grid">
          <section className="agent-modal-section agent-current">
            <div className="section-header compact">
              <div>
                <div className="eyebrow">current activity</div>
                <strong>{humanize(agent.status)}</strong>
              </div>
              <b className={severityClass(agent.severity)}>{agent.severity}</b>
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
                <span className="label">updated</span>
                <strong>{formatDate(agent.updated_at)}</strong>
              </div>
            </div>
          </section>

          <section className="agent-modal-section">
            <div className="eyebrow">workflow</div>
            <ol className="agent-workflow">
              {workflow.map((step, index) => (
                <li
                  className={index <= Math.min(activePhaseIndex, workflow.length - 1) ? "is-complete" : ""}
                  key={`${agent.agent}-${step}`}
                >
                  <span>{String(index + 1).padStart(2, "0")}</span>
                  {step}
                </li>
              ))}
            </ol>
          </section>

          <section className="agent-modal-section span-2">
            <div className="section-header compact">
              <div>
                <div className="eyebrow">latest report</div>
                <strong>{latestFinding?.finding ?? "No open finding reported"}</strong>
              </div>
              <b className={statusToneClass(latestFinding?.severity ?? agent.severity)}>
                {latestFinding?.status ?? humanize(agent.status)}
              </b>
            </div>
            <p>{latestFinding?.risk ?? "Agent is monitoring its domain and has not published a detailed finding yet."}</p>
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
            <div className="eyebrow">recommendations</div>
            <ul className="agent-action-list">
              {(actions.length ? actions : ["continue_monitoring"]).map((action) => (
                <li key={action}>{actionLabel(action)}</li>
              ))}
            </ul>
          </section>

          <section className="agent-modal-section">
            <div className="eyebrow">linked operations</div>
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
            <div className="eyebrow">history</div>
            <ol className="agent-history">
              {(history.length ? history : latestFinding ? [latestFinding] : []).slice(0, 4).map((finding) => (
                <li key={finding.id}>
                  <time>{formatDate(finding.created_at)}</time>
                  <span>{finding.finding}</span>
                  <b className={severityClass(finding.severity)}>{finding.severity}</b>
                </li>
              ))}
              {!history.length && !latestFinding ? (
                <li>
                  <time>{formatDate(agent.updated_at)}</time>
                  <span>{agent.message}</span>
                  <b className={severityClass(agent.severity)}>{agent.severity}</b>
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
  const agentFindings = useWorldStore((state) => state.agentFindings);
  const incidents = useWorldStore((state) => state.incidents);
  const missionPatch = useWorldStore((state) => state.missionPatch);
  const commands = useWorldStore((state) => state.commands);
  const visibleAgents = agents.length > 0 ? agents : fallbackAgents;
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);

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

  return (
    <section className="rail-section" aria-label="Independent agent status">
      <div className="eyebrow">agent status</div>
      <div className="agent-status-list">
        {visibleAgents.map((agent) => (
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
            </span>
            <b className={severityClass(agent.severity)}>{agent.severity}</b>
          </button>
        ))}
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
              onClose={() => setSelectedAgentId(null)}
            />,
            document.body,
          )
        : null}
    </section>
  );
}
