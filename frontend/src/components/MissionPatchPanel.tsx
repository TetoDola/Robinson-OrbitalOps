import { approveMissionPatch } from "../api/client";
import { useWorldStore, type PatchMode } from "../store/worldStore";
import type { MissionPatchAction, NodeState } from "../types/backend";
import AgentStatus from "./AgentStatus";

const rackPatterns = [
  ["active", "compute", "compute", "active", "compute", "hot", "active", "compute"],
  ["compute", "compute", "active", "active", "compute", "compute", "active", "active"],
  ["active", "active", "compute", "compute", "hot", "compute", "active", "compute"],
  ["compute", "active", "active", "compute", "compute", "active", "compute", "active"],
  ["active", "compute", "compute", "compute", "active", "compute", "active", "warn"],
  ["compute", "compute", "active", "hot", "compute", "active", "compute", "active"],
];

const fallbackActions = [
  "Mark ckpt-184900 as suspect and preserve evidence.",
  "Roll back critical training to ckpt-184500.",
  "Cordon Node B GPU 3 from critical training.",
  "Mark Node C unavailable until thermal verification passes.",
  "Reduce Node A GPU power limit to 70% before eclipse.",
  "Send manifest, hashes, logs, and delta checkpoint first.",
  "Run canary eval and distributed health check before resume.",
];

function humanize(value: string): string {
  return value.replace(/[_-]+/g, " ");
}

function actionLabel(action: MissionPatchAction): string {
  const target = action.node_id ?? action.job_id ?? action.checkpoint_id ?? action.target_asset_id;
  const prefix = humanize(action.type);
  return target ? `${prefix} on ${humanize(target)}` : prefix;
}

function nodeLabel(node: NodeState): string {
  const temp = typeof node.temp_c === "number" ? `, ${node.temp_c.toFixed(1)} C` : "";
  const ecc = typeof node.ecc_errors === "number" ? `, ECC ${node.ecc_errors}` : "";
  return `${humanize(node.status)}${temp}${ecc}`;
}

function nodeSeverityClass(node: NodeState): string {
  const status = node.status.toLowerCase();
  if (status.includes("risk") || status.includes("suspect") || status.includes("thermal")) {
    return "node-state status-red";
  }
  if (status.includes("hot") || status.includes("degraded")) {
    return "node-state status-orange";
  }
  return "node-state";
}

function patchStateLabel(mode: PatchMode, backendStatus?: string): string {
  if (mode === "execute") {
    return "APPROVED";
  }
  if (mode === "verified") {
    return "VERIFIED";
  }
  if (mode === "replan") {
    return "REPLAN REQUESTED";
  }
  if (mode === "modify") {
    return "MODIFYING";
  }
  if (mode === "reject") {
    return "REJECTED";
  }
  return backendStatus ? humanize(backendStatus).toUpperCase() : "AWAITING APPROVAL";
}

function patchStateClass(mode: PatchMode): string {
  if (mode === "reject") {
    return "status-red";
  }
  if (mode === "replan" || mode === "modify") {
    return "status-yellow";
  }
  if (mode === "execute") {
    return "status-orange";
  }
  return "status-red";
}

function RackDiagram() {
  return (
    <div className="rack-shell" aria-hidden="true">
      {rackPatterns.map((slots, rackIndex) => (
        <div className="rack" key={`rack-${rackIndex}`}>
          <div className="rack-title">R{rackIndex + 1}</div>
          {slots.map((slotType, slotIndex) => (
            <div className={`slot ${slotType}`} key={`${rackIndex}-${slotIndex}`} />
          ))}
        </div>
      ))}
    </div>
  );
}

export default function MissionPatchPanel() {
  const telemetry = useWorldStore((state) => state.telemetry);
  const inspectionOpen = useWorldStore((state) => state.inspectionOpen);
  const setInspectionOpen = useWorldStore((state) => state.setInspectionOpen);
  const missionPatch = useWorldStore((state) => state.missionPatch);
  const setMissionPatch = useWorldStore((state) => state.setMissionPatch);
  const patchMode = useWorldStore((state) => state.patchMode);
  const setPatchMode = useWorldStore((state) => state.setPatchMode);
  const worldState = useWorldStore((state) => state.worldState);

  const actions = missionPatch?.actions?.length
    ? missionPatch.actions.map(actionLabel)
    : fallbackActions;
  const nodes = worldState?.nodes ?? [];
  const title = missionPatch
    ? `${missionPatch.id}: protect training integrity`
    : "patch-042: protect training integrity";

  async function approvePatch() {
    setPatchMode("execute");
    if (!missionPatch) {
      return;
    }

    try {
      const updatedPatch = await approveMissionPatch(missionPatch.id);
      setMissionPatch(updatedPatch);
    } catch {
      setPatchMode("pending");
    }
  }

  return (
    <aside
      className={inspectionOpen ? "asset-panel is-open" : "asset-panel"}
      aria-label="Selected satellite datacenter"
    >
      <div className="asset-header">
        <div>
          <div className="eyebrow">selected incident</div>
          <h2 className="panel-title">patch approval console</h2>
        </div>
        <button
          className="close-btn"
          aria-label="Close satellite inspection"
          onClick={() => setInspectionOpen(false)}
          type="button"
        >
          &times;
        </button>
      </div>

      <div className="asset-summary">
        <div className="summary-cell">
          <div className="label">severity</div>
          <strong className="status-red">{missionPatch?.severity ?? "RED"}</strong>
        </div>
        <div className="summary-cell">
          <div className="label">confidence</div>
          <strong>{telemetry.patchConfidence}</strong>
        </div>
        <div className="summary-cell">
          <div className="label">status</div>
          <strong className={patchStateClass(patchMode)}>
            {patchStateLabel(patchMode, missionPatch?.status)}
          </strong>
        </div>
      </div>

      <section className="rack-section" aria-label="Server rack cutaway">
        <div className="panel-header">
          <div>
            <div className="eyebrow">asset state</div>
            <h3 className="panel-title">AI compute racks</h3>
          </div>
          <div className={`label status-${telemetry.rackHealthTone}`}>{telemetry.rackHealth}</div>
        </div>
        <RackDiagram />
        <div className="rack-legend" aria-label="Rack color legend">
          <span className="legend-key">
            <span className="legend-dot" />
            healthy
          </span>
          <span className="legend-key">
            <span className="legend-dot yellow" />
            warning
          </span>
          <span className="legend-key">
            <span className="legend-dot orange" />
            degraded
          </span>
          <span className="legend-key">
            <span className="legend-dot red" />
            unsafe
          </span>
          <span className="legend-key">
            <span className="legend-dot blue" />
            critical workload
          </span>
          <span className="legend-key">
            <span className="legend-dot gray" />
            unavailable
          </span>
        </div>
      </section>

      <section className="rack-section" aria-label="Node operating state">
        <div className="eyebrow">node state</div>
        <ul className="node-list">
          {nodes.length > 0 ? (
            nodes.map((node) => (
              <li className="node-row" key={node.id}>
                <span>
                  <strong>{humanize(node.id)}</strong>
                  {nodeLabel(node)}
                </span>
                <b className={nodeSeverityClass(node)}>{humanize(node.status)}</b>
              </li>
            ))
          ) : (
            <>
              <li className="node-row">
                <span>
                  <strong>Node A</strong>
                  Critical training, reduced-power safe mode
                </span>
                <b className="node-state status-orange">degraded</b>
              </li>
              <li className="node-row">
                <span>
                  <strong>Node B</strong>
                  Free GPUs, ECC rising on GPU 3
                </span>
                <b className="node-state status-red">unsafe</b>
              </li>
              <li className="node-row">
                <span>
                  <strong>Node C</strong>
                  IR hotspot confirmed while idle
                </span>
                <b className="node-state status-red">unsafe</b>
              </li>
              <li className="node-row">
                <span>
                  <strong>Node D</strong>
                  Standby pool available for canary eval
                </span>
                <b className="node-state">healthy</b>
              </li>
            </>
          )}
        </ul>
      </section>

      <AgentStatus />

      <section className="patch-panel" aria-label="Mission Patch">
        <div className="eyebrow">Commander Agent mission patch</div>
        <h3 className="panel-title">{title}</h3>
        <div className="patch-meta">
          <div>
            <span className="label">mode</span>
            <strong>Human approval</strong>
          </div>
          <div>
            <span className="label">risk</span>
            <strong className="status-red">{missionPatch?.severity ?? "critical"}</strong>
          </div>
          <div>
            <span className="label">window</span>
            <strong>{telemetry.eclipse}</strong>
          </div>
        </div>
        <p className="patch-summary">
          {missionPatch?.summary ??
            "ECC escalation, Node C thermal anomaly, power drop, and limited downlink make the latest checkpoint unsafe for automatic continuation."}
        </p>
        <ol className="patch-action-list">
          {actions.map((action) => (
            <li key={action}>{action}</li>
          ))}
        </ol>
        <div className="patch-buttons">
          <button className="patch-btn primary" onClick={() => void approvePatch()} type="button">
            Approve Patch
          </button>
          <button className="patch-btn" onClick={() => setPatchMode("replan")} type="button">
            Ask Commander to Replan
          </button>
          <button className="patch-btn" onClick={() => setPatchMode("modify")} type="button">
            Modify Patch
          </button>
          <button className="patch-btn danger" onClick={() => setPatchMode("reject")} type="button">
            Reject
          </button>
        </div>
      </section>
    </aside>
  );
}
