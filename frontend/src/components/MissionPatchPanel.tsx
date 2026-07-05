import { approveMissionPatch } from "../api/client";
import { useWorldStore, type PatchMode } from "../store/worldStore";
import type { MissionPatchAction } from "../types/backend";

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

function patchStateLabel(mode: PatchMode, backendStatus?: string): string {
  if (mode === "execute") return "APPROVED";
  if (mode === "verified") return "VERIFIED";
  if (mode === "replan") return "REPLAN REQUESTED";
  if (mode === "modify") return "MODIFYING";
  if (mode === "reject") return "REJECTED";
  return backendStatus ? humanize(backendStatus).toUpperCase() : "AWAITING APPROVAL";
}

function patchStateClass(mode: PatchMode): string {
  if (mode === "reject") return "status-red";
  if (mode === "replan" || mode === "modify") return "status-yellow";
  if (mode === "execute") return "status-orange";
  return "status-red";
}

function shortPatchId(id: string): string {
  return id.length > 12 ? `patch-${id.slice(0, 8)}` : id;
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
  const demoResetAt = useWorldStore((state) => state.demoResetAt);
  const resetIdle = Boolean(demoResetAt && !missionPatch);

  const actions = missionPatch?.actions?.length
    ? missionPatch.actions.map(actionLabel)
    : resetIdle
      ? []
      : fallbackActions;
  const title = missionPatch
    ? `${shortPatchId(missionPatch.id)}: protect training integrity`
    : resetIdle
      ? "no active mission patch"
      : "patch-042: protect training integrity";
  const severityLabel = missionPatch?.severity ?? (resetIdle ? "INFO" : "RED");
  const riskLabel = missionPatch?.severity ?? (resetIdle ? "nominal" : "critical");
  const approvalMode = resetIdle ? "Monitoring" : "Human approval";
  const statusLabel = resetIdle ? "MONITORING" : patchStateLabel(patchMode, missionPatch?.status);
  const statusClass = resetIdle ? "status-yellow" : patchStateClass(patchMode);

  async function approvePatch() {
    setPatchMode("execute");
    if (!missionPatch) return;

    try {
      const updatedPatch = await approveMissionPatch(missionPatch.id);
      setMissionPatch(updatedPatch);
    } catch {
      setPatchMode("pending");
    }
  }

  return (
    <aside className="right-rail" aria-label="Approvals">
      <section className="rail-section rail-heading">
        <div>
          <div className="eyebrow">Operations</div>
          <h2 className="panel-title">Approvals</h2>
        </div>
        {inspectionOpen ? (
          <button className="rail-action" onClick={() => setInspectionOpen(false)} type="button">
            Clear
          </button>
        ) : null}
      </section>

      <section className="patch-panel" aria-label="Mission patch approval">
        <div className="section-header compact">
          <div>
            <div className="eyebrow">Approvals</div>
            <h3 className="panel-title">{title}</h3>
          </div>
          <strong className={statusClass}>{statusLabel}</strong>
        </div>
        <div className="patch-meta">
          <div>
            <span className="label">mode</span>
            <strong>{approvalMode}</strong>
          </div>
          <div>
            <span className="label">risk</span>
            <strong className={resetIdle ? "status-yellow" : "status-red"}>{riskLabel}</strong>
          </div>
          <div>
            <span className="label">window</span>
            <strong>{telemetry.eclipse}</strong>
          </div>
        </div>
        <p className="patch-summary">
          {missionPatch?.summary ??
            (resetIdle
              ? "Agents are monitoring the reset baseline. No recovery patch is awaiting approval."
              : "ECC escalation, Node C thermal anomaly, power drop, and limited downlink make the latest checkpoint unsafe for automatic continuation.")}
        </p>
        <ol className="patch-action-list">
          {actions.slice(0, 5).map((action) => (
            <li key={action}>{action}</li>
          ))}
        </ol>
        {resetIdle ? (
          <div className="patch-buttons">
            <button className="patch-btn" disabled type="button">
              Monitoring Baseline
            </button>
          </div>
        ) : (
          <div className="patch-buttons">
            <button className="patch-btn primary" onClick={() => void approvePatch()} type="button">
              Approve
            </button>
            <button className="patch-btn" onClick={() => setPatchMode("replan")} type="button">
              Replan
            </button>
            <button className="patch-btn" onClick={() => setPatchMode("modify")} type="button">
              Modify
            </button>
            <button className="patch-btn danger" onClick={() => setPatchMode("reject")} type="button">
              Reject
            </button>
          </div>
        )}
      </section>

      <section className={inspectionOpen ? "rail-section asset-detail is-selected" : "rail-section asset-detail"}>
        <div className="section-header compact">
          <div>
            <div className="eyebrow">Selected asset</div>
            <h3 className="panel-title">AKJA-01 datacenter</h3>
          </div>
          <span className="selection-state">{inspectionOpen ? "selected" : "idle"}</span>
        </div>
        <div className="asset-summary">
          <div className="summary-cell">
            <div className="label">severity</div>
            <strong className={resetIdle ? "status-yellow" : "status-red"}>{severityLabel}</strong>
          </div>
          <div className="summary-cell">
            <div className="label">confidence</div>
            <strong>{telemetry.patchConfidence}</strong>
          </div>
          <div className="summary-cell">
            <div className="label">rack</div>
            <strong className={`status-${telemetry.rackHealthTone}`}>{telemetry.rackHealth}</strong>
          </div>
        </div>
        <RackDiagram />
      </section>
    </aside>
  );
}
