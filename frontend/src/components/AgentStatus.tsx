import { useWorldStore } from "../store/worldStore";
import type { AgentStatusItem } from "../types/backend";

export const fallbackAgents: AgentStatusItem[] = [
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

export default function AgentStatus() {
  const agents = useWorldStore((state) => state.agents);
  const visibleAgents = agents.length > 0 ? agents : fallbackAgents;

  return (
    <section className="rail-section" aria-label="Independent agent status">
      <div className="eyebrow">agent status</div>
      <div className="agent-status-list">
        {visibleAgents.map((agent) => (
          <div className="agent-card" key={agent.agent}>
            <span>
              <strong>{agent.display_name}</strong>
              {agent.message}
            </span>
            <b className={severityClass(agent.severity)}>{agent.severity}</b>
          </div>
        ))}
      </div>
    </section>
  );
}
