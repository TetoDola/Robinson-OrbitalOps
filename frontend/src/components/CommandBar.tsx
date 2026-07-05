import { useEffect, useState } from "react";

import { fallbackAgents } from "./AgentStatus";
import { FLEET_AGG } from "../fleet/fleetData";
import { useAppStore } from "../store/appStore";
import { useWorldStore } from "../store/worldStore";

/** Worst severity → a single mission-health verdict (label + color, never color alone). */
function missionHealth(severities: string[]): { cls: string; label: string } {
  const values = severities.map((value) => value.toLowerCase());
  if (values.some((v) => v.includes("red") || v.includes("critical"))) {
    return { cls: "is-critical", label: "Critical" };
  }
  if (values.some((v) => v.includes("orange") || v.includes("warn") || v.includes("yellow"))) {
    return { cls: "is-caution", label: "Caution" };
  }
  return { cls: "", label: "Nominal" };
}

export default function CommandBar() {
  const telemetry = useWorldStore((state) => state.telemetry);
  const connectionStatus = useWorldStore((state) => state.connectionStatus);
  const agents = useWorldStore((state) => state.agents);
  const view = useAppStore((state) => state.view);
  const selectedAssetId = useAppStore((state) => state.selectedAssetId);
  const goFleet = useAppStore((state) => state.goFleet);

  const [clock, setClock] = useState("--:--:-- UTC");
  useEffect(() => {
    const tick = () => setClock(`${new Date().toISOString().slice(11, 19)} UTC`);
    tick();
    const id = window.setInterval(tick, 1000);
    return () => window.clearInterval(id);
  }, []);

  const roster = agents.length > 0 ? agents : fallbackAgents;
  const health =
    view === "fleet"
      ? { cls: "is-critical", label: "Critical" }
      : missionHealth(roster.map((agent) => String(agent.severity)));
  const connLabel =
    connectionStatus === "live" ? "live" : connectionStatus === "connecting" ? "linking" : "local";

  return (
    <header className="command-bar">
      <div className="cb-brand">
        <div className="brand-mark">OPS</div>
        <div className="cb-id">
          <strong>OrbitOps</strong>
          <span>orbital datacenter command</span>
        </div>
      </div>

      {view === "fleet" ? (
        <span className="cb-crumb"><b>Fleet</b> · all assets</span>
      ) : (
        <button className="cb-crumb cb-back" onClick={goFleet} type="button">
          ‹ Fleet <span className="sep">/</span> <b>{selectedAssetId}</b>
        </button>
      )}

      <div className="cb-status" aria-label="Mission status">
        <span className={`cb-chip cb-health ${health.cls}`} aria-label={`Health ${health.label}`}>
          <span className="state-dot" aria-hidden="true" />
          {health.label}
        </span>
        {view === "fleet" ? (
          <>
            <span className="cb-chip"><span className="label">assets</span> <b>{FLEET_AGG.total}</b></span>
            <span className="cb-chip"><span className="label">critical</span> <b>{FLEET_AGG.critical}</b></span>
            <span className="cb-chip"><span className="label">gpus</span> <b>{FLEET_AGG.gpuOnline}/{FLEET_AGG.gpuTotal}</b></span>
          </>
        ) : (
          <>
            <span className="cb-chip"><span className="label">orbit</span> <b>{telemetry.orbitPhase}</b></span>
            <span className="cb-chip"><span className="label">link</span> <b>{telemetry.groundLink}</b></span>
            <span className="cb-chip"><span className="label">eclipse</span> <b>{telemetry.eclipse}</b></span>
          </>
        )}
      </div>

      <div className="cb-right">
        <div className="clock">{clock}</div>
        <span className={`connection-pill ${connectionStatus}`}>
          <span className="state-dot" aria-hidden="true" />
          {connLabel}
        </span>
      </div>
    </header>
  );
}
