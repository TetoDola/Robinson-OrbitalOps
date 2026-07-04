import { useWorldStore } from "../store/worldStore";
import type { Incident } from "../types/backend";

const fallbackIncidents: Incident[] = [
  {
    id: "power-orbit",
    incident_key: "power-orbit",
    title: "Power / Orbit Agent",
    severity: "ORANGE",
    status: "active",
    finding_ids: [],
    summary: "Eclipse in 11 min, battery reserve low",
  },
  {
    id: "integrity",
    incident_key: "integrity",
    title: "Integrity Agent",
    severity: "RED",
    status: "active",
    finding_ids: [],
    summary: "ECC spike on Node B GPU 3 before ckpt-184900",
  },
  {
    id: "workload",
    incident_key: "workload",
    title: "Workload Agent",
    severity: "ORANGE",
    status: "active",
    finding_ids: [],
    summary: "Rank 17 all-reduce timeout",
  },
  {
    id: "thermal",
    incident_key: "thermal",
    title: "Thermal Agent",
    severity: "RED",
    status: "active",
    finding_ids: [],
    summary: "IR hotspot on Node C while idle",
  },
  {
    id: "downlink",
    incident_key: "downlink",
    title: "Downlink Agent",
    severity: "YELLOW",
    status: "active",
    finding_ids: [],
    summary: "Full checkpoint exceeds contact window",
  },
  {
    id: "commander",
    incident_key: "commander",
    title: "Commander Agent",
    severity: "RED",
    status: "approval",
    finding_ids: [],
    summary: "Mission Patch patch-042 ready",
  },
];

function severityClass(severity: string, status: string): string {
  const value = `${severity} ${status}`.toLowerCase();
  if (value.includes("approval") || value.includes("red") || value.includes("critical")) {
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

function patchStatus(mode: string): { nodeStatus: string; statusText: string; commanderSeverity: string } {
  if (mode === "execute") {
    return {
      nodeStatus: "executor running",
      statusText: "cordoning unsafe GPUs, reducing power, and preparing trusted rollback",
      commanderSeverity: "executing",
    };
  }
  if (mode === "verified") {
    return {
      nodeStatus: "recovery verified",
      statusText: "training resumed from ckpt-184500, unsafe nodes remain cordoned",
      commanderSeverity: "verified",
    };
  }
  if (mode === "replan") {
    return {
      nodeStatus: "commander replanning",
      statusText: "Commander Agent is generating a lower-risk patch variant",
      commanderSeverity: "replan",
    };
  }
  if (mode === "modify") {
    return {
      nodeStatus: "patch under edit",
      statusText: "operator is adjusting recommended recovery actions",
      commanderSeverity: "review",
    };
  }
  if (mode === "reject") {
    return {
      nodeStatus: "patch rejected",
      statusText: "risk remains unresolved, agents continue monitoring",
      commanderSeverity: "blocked",
    };
  }
  return {
    nodeStatus: "mission patch ready",
    statusText: "Commander Agent requires human approval",
    commanderSeverity: "approval",
  };
}

export default function IncidentStrip() {
  const telemetry = useWorldStore((state) => state.telemetry);
  const incidents = useWorldStore((state) => state.incidents);
  const patchMode = useWorldStore((state) => state.patchMode);
  const visibleIncidents = incidents.length > 0 ? incidents : fallbackIncidents;
  const status = patchStatus(patchMode);

  return (
    <footer className="status-strip" aria-label="Active incidents">
      <div className="incident-header">
        <div className="eyebrow">active incidents</div>
        <div>
          <span className="incident-count">{visibleIncidents.length}</span>{" "}
          <strong>{status.nodeStatus}</strong>
        </div>
        <span>{status.statusText}</span>
      </div>
      <div className="incident-list">
        {visibleIncidents.map((incident, index) => {
          const isCommander = incident.title.toLowerCase().includes("commander");
          const label = isCommander ? status.commanderSeverity : incident.severity;
          const summary = incident.summary.replace("11 min", telemetry.eclipse);
          return (
            <div className="incident-row" key={incident.id}>
              <span className="incident-time">T+00:{String(index + 1).padStart(2, "0")}</span>
              <span>
                <strong>{incident.title}</strong>
                {summary}
              </span>
              <b className={severityClass(String(label), incident.status)}>{label}</b>
            </div>
          );
        })}
      </div>
    </footer>
  );
}
