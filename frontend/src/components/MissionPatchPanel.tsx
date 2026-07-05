import {
  useEffect,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type MouseEvent as ReactMouseEvent,
} from "react";

import { useWorldStore } from "../store/worldStore";
import type { NodeState } from "../types/backend";
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

  const nodes = worldState?.nodes ?? [];
  const maxNodeTemp = nodes.reduce((max, node) => Math.max(max, node.temp_c ?? 0), 0);
  const hasIssue = Boolean(missionPatch || incidents.length > 0 || maxNodeTemp >= 80);
  const assetStateLabel = resetIdle ? "monitoring" : missionPatch ? "review required" : "attention";

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

      <section className={inspectionOpen ? "rail-section asset-detail is-selected" : "rail-section asset-detail"}>
        <div className="section-header compact">
          <div>
            <div className="eyebrow">Selected asset</div>
            <h3 className="panel-title">Neon Noir</h3>
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
            sourceImageUrl={
              latestThermalInput && latestThermalInput.asset_id === irView.node.id
                ? latestThermalInput.image_data_url
                : null
            }
            onClose={() => setIrView(null)}
          />
        ) : null}
      </section>
    </aside>
  );
}
