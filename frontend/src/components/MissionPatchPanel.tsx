import {
  useEffect,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type MouseEvent as ReactMouseEvent,
} from "react";

import { approveMissionPatch, rejectMissionPatch } from "../api/client";
import { useWorldStore, type PatchMode } from "../store/worldStore";
import type { MissionPatchAction, NodeState } from "../types/backend";
import AgentStatus from "./AgentStatus";
import IRCamPopup, { type IrNodeTarget } from "./IRCamPopup";
import SimulationControls from "./SimulationControls";

const nominalRackPatterns = [
  ["active", "compute", "compute", "active", "compute", "compute", "active", "compute"],
  ["compute", "compute", "active", "active", "compute", "compute", "active", "active"],
  ["active", "active", "compute", "compute", "active", "compute", "active", "compute"],
  ["compute", "active", "active", "compute", "compute", "active", "compute", "active"],
  ["active", "compute", "compute", "compute", "active", "compute", "active", "compute"],
  ["compute", "compute", "active", "active", "compute", "active", "compute", "active"],
];

const incidentRackPatterns = [
  ["active", "compute", "compute", "active", "compute", "hot", "active", "compute"],
  ["compute", "compute", "active", "active", "compute", "compute", "active", "active"],
  ["active", "active", "compute", "compute", "hot", "compute", "active", "compute"],
  ["compute", "active", "active", "compute", "compute", "active", "compute", "active"],
  ["active", "compute", "compute", "compute", "active", "compute", "active", "warn"],
  ["compute", "compute", "active", "hot", "compute", "active", "compute", "active"],
];

const fallbackNodeRows = [
  { id: "Node A", desc: "Training worker nominal", status: "healthy", cls: "node-state", tempC: 61.2 },
  { id: "Node B", desc: "Integrity counters nominal", status: "healthy", cls: "node-state", tempC: 58.4 },
  { id: "Node C", desc: "Cooling loop nominal", status: "healthy", cls: "node-state", tempC: 60.1 },
  { id: "Node D", desc: "Standby pool available", status: "healthy", cls: "node-state", tempC: 52.1 },
];

function humanize(value: string): string {
  return value.replace(/[_-]+/g, " ");
}

function formatClock(value: string | undefined): string {
  if (!value) return "--:--";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "--:--";
  return parsed.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
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

function inferNodeTemp(status: string): number {
  const value = status.toLowerCase();
  if (value.includes("thermal") || value.includes("hot")) return 92.3;
  if (value.includes("unsafe") || value.includes("suspect") || value.includes("risk")) return 84.6;
  if (value.includes("degraded")) return 76.1;
  if (value.includes("cordon") || value.includes("unavail")) return 46.8;
  return 57.4;
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
  if (mode === "execute") return "APPROVED";
  if (mode === "verified") return "VERIFIED";
  if (mode === "replan") return "REPLAN REQUESTED";
  if (mode === "modify") return "MODIFYING";
  if (mode === "reject") return "REJECTED";
  if (backendStatus === "pending_approval") return "NEEDS APPROVAL";
  return backendStatus ? humanize(backendStatus).toUpperCase() : "AWAITING APPROVAL";
}

function patchStateClass(mode: PatchMode): string {
  if (mode === "reject") return "status-red";
  if (mode === "replan" || mode === "modify") return "status-yellow";
  if (mode === "execute") return "status-cyan";
  if (mode === "verified") return "status-green";
  return "status-orange";
}

function severityClass(value: string): string {
  const severity = value.toLowerCase();
  if (severity.includes("approval") || severity.includes("red") || severity.includes("critical")) {
    return "severity red";
  }
  if (severity.includes("orange") || severity.includes("warn")) {
    return "severity orange";
  }
  if (severity.includes("yellow")) {
    return "severity yellow";
  }
  if (severity.includes("info") || severity.includes("monitor") || severity.includes("healthy")) {
    return "severity info";
  }
  return "severity info";
}

function shortPatchId(id: string): string {
  return id.length > 12 ? `patch-${id.slice(0, 8)}` : id;
}

function RackDiagram({ hasIssue }: { hasIssue: boolean }) {
  const rackPatterns = hasIssue ? incidentRackPatterns : nominalRackPatterns;
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
  const [approvalError, setApprovalError] = useState<string | null>(null);
  const worldState = useWorldStore((state) => state.worldState);
  const incidents = useWorldStore((state) => state.incidents);
  const resetIdle = !missionPatch && incidents.length === 0;
  const latestThermalInput = worldState?.thermal.latest_visual_input ?? null;
  const [irView, setIrView] = useState<{ node: IrNodeTarget; anchor: { x: number; y: number } } | null>(null);

  useEffect(() => {
    if (!inspectionOpen) {
      setIrView(null);
    }
  }, [inspectionOpen]);

  function toggleIrView(target: IrNodeTarget, anchor: { x: number; y: number }) {
    setIrView((current) => (current?.node.id === target.id ? null : { node: target, anchor }));
  }

  function nodeRowProps(target: IrNodeTarget) {
    return {
      "aria-label": `Open IR thermal view of ${humanize(target.id)}`,
      className: irView?.node.id === target.id ? "node-row is-clickable is-inspected" : "node-row is-clickable",
      onClick: (event: ReactMouseEvent<HTMLLIElement>) =>
        toggleIrView(target, { x: event.clientX, y: event.clientY }),
      onKeyDown: (event: ReactKeyboardEvent<HTMLLIElement>) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          const rect = event.currentTarget.getBoundingClientRect();
          toggleIrView(target, { x: rect.left, y: rect.top + rect.height / 2 });
        }
      },
      role: "button",
      tabIndex: 0,
      title: "Open IR thermal view",
    };
  }

  const actions = missionPatch?.actions?.length ? missionPatch.actions.map(actionLabel) : [];
  const rollbackValue = missionPatch?.rollback_plan?.if_verification_fails;
  const rollbackSteps = Array.isArray(rollbackValue)
    ? rollbackValue.filter((step): step is string => typeof step === "string")
    : [];
  const nodes = worldState?.nodes ?? [];
  const visibleIncidents = incidents;
  const maxNodeTemp = nodes.reduce((max, node) => Math.max(max, node.temp_c ?? 0), 0);
  const hasIssue = Boolean(missionPatch || visibleIncidents.length > 0 || maxNodeTemp >= 80);
  const title = missionPatch
    ? `${shortPatchId(missionPatch.id)}: protect training integrity`
    : resetIdle
      ? "no active mission patch"
      : "incident under review";
  const assetStateLabel = resetIdle ? "monitoring" : missionPatch ? "review required" : "attention";
  const operatorLabel = resetIdle ? "standby" : missionPatch?.status === "pending_approval" ? "approve or replan" : humanize(missionPatch?.status ?? "review");
  const approvalMode = resetIdle ? "Monitoring" : "Human approval";
  const statusLabel = resetIdle ? "MONITORING" : patchStateLabel(patchMode, missionPatch?.status);
  const statusClass = resetIdle ? "status-green" : patchStateClass(patchMode);
  const canDecidePatch = missionPatch?.status === "pending_approval";

  async function approvePatch() {
    if (!missionPatch) return;
    setApprovalError(null);
    setPatchMode("execute");

    try {
      const updatedPatch = await approveMissionPatch(missionPatch.id);
      setMissionPatch(updatedPatch);
    } catch {
      setPatchMode("pending");
      setApprovalError("Approve failed — the backend rejected the request or is unreachable. The patch is still pending.");
    }
  }

  async function rejectPatch() {
    if (!missionPatch) return;
    setApprovalError(null);
    setPatchMode("reject");

    try {
      const updatedPatch = await rejectMissionPatch(missionPatch.id);
      setMissionPatch(updatedPatch);
    } catch {
      setPatchMode("pending");
      setApprovalError("Reject failed — the backend rejected the request or is unreachable. The patch is still pending.");
    }
  }

  return (
    <aside className="right-rail" aria-label="Agents and approvals">
      <section className="rail-section rail-heading">
        <div>
          <div className="eyebrow">Operations</div>
          <h2 className="panel-title">Agents</h2>
        </div>
        {inspectionOpen ? (
          <button className="rail-action" onClick={() => setInspectionOpen(false)} type="button">
            Clear
          </button>
        ) : null}
      </section>

      <AgentStatus />

      <SimulationControls />

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
            <span className="label">operator</span>
            <strong className={resetIdle ? "status-green" : "status-orange"}>{operatorLabel}</strong>
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
              : "An incident is open. Waiting for Commander to assemble a validated mission patch.")}
        </p>
        {missionPatch ? (
          <div className="patch-scope">
            <span className={severityClass(String(missionPatch.severity))}>{missionPatch.severity}</span>
            <span>
              {actions.length} command{actions.length === 1 ? "" : "s"} in scope — approving executes all of them
            </span>
          </div>
        ) : null}
        <ol className="patch-action-list">
          {actions.map((action) => (
            <li key={action}>{action}</li>
          ))}
        </ol>
        {rollbackSteps.length > 0 ? (
          <p className="patch-rollback">
            <span className="label">rollback if verification fails</span>
            {rollbackSteps.map(humanize).join(", ")}
          </p>
        ) : null}
        {approvalError ? <p className="approval-error">{approvalError}</p> : null}
        {resetIdle ? (
          <div className="patch-buttons">
            <button className="patch-btn" disabled type="button">
              Monitoring Baseline
            </button>
          </div>
        ) : (
          <div className="patch-buttons">
            <button className="patch-btn primary" disabled={!canDecidePatch} onClick={() => void approvePatch()} type="button">
              Approve
            </button>
            <button className="patch-btn danger" disabled={!canDecidePatch} onClick={() => void rejectPatch()} type="button">
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
            <div className="label">state</div>
            <strong className={resetIdle ? "status-green" : "status-orange"}>{assetStateLabel}</strong>
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
        <RackDiagram hasIssue={hasIssue} />
      </section>

      <section className="rail-section" aria-label="Node operating state">
        <div className="eyebrow">Node state</div>
        <ul className="node-list">
          {nodes.length > 0
            ? nodes.map((node) => {
                const target: IrNodeTarget = {
                  id: node.id,
                  status: node.status,
                  tempC: node.temp_c ?? inferNodeTemp(node.status),
                };
                return (
                  <li key={node.id} {...nodeRowProps(target)}>
                    <span>
                      <strong>{humanize(node.id)}</strong>
                      {nodeLabel(node)}
                    </span>
                    <b className={nodeSeverityClass(node)}>{humanize(node.status)}</b>
                    <span aria-hidden="true" className="ir-chip">IR</span>
                  </li>
                );
              })
            : fallbackNodeRows.map((row) => (
                <li key={row.id} {...nodeRowProps({ id: row.id, status: row.status, tempC: row.tempC })}>
                  <span>
                    <strong>{row.id}</strong>
                    {row.desc}
                  </span>
                  <b className={row.cls}>{row.status}</b>
                  <span aria-hidden="true" className="ir-chip">IR</span>
                </li>
              ))}
        </ul>
        {irView ? (
          <IRCamPopup
            anchor={irView.anchor}
            node={irView.node}
            sourceImageUrl={latestThermalInput?.asset_id === irView.node.id ? latestThermalInput.image_data_url : null}
            onClose={() => setIrView(null)}
          />
        ) : null}
      </section>

      <section className="rail-section incidents-panel" aria-label="Active incidents">
        <div className="section-header compact">
          <div>
            <div className="eyebrow">Active incidents</div>
            <h3 className="panel-title">{visibleIncidents.length} open</h3>
          </div>
        </div>
        <div className="incident-list">
          {visibleIncidents.map((incident) => (
            <div className="incident-row" key={incident.id}>
              <span className="incident-time">{formatClock(incident.created_at)}</span>
              <span>
                <strong>{incident.title}</strong>
                {incident.summary}
              </span>
              <b className={severityClass(String(incident.severity))}>{incident.status}</b>
            </div>
          ))}
        </div>
      </section>
    </aside>
  );
}
