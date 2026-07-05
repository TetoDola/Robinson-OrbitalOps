import { useState } from "react";

import { useAppStore } from "../store/appStore";
import {
  FLEET,
  FLEET_AGG,
  FLEET_QUEUE,
  HEALTH_LABEL,
  HEALTH_TOKEN,
  type FleetAsset,
} from "../fleet/fleetData";
import Constellation from "./Constellation";

const bySeverity = (a: FleetAsset, b: FleetAsset) => {
  const rank = { critical: 0, caution: 1, nominal: 2 };
  return rank[a.health] - rank[b.health];
};

export default function FleetView() {
  const openAsset = useAppStore((s) => s.openAsset);
  const [selected, setSelected] = useState("AKJA-03");
  const roster = [...FLEET].sort(bySeverity);
  const asset = FLEET.find((a) => a.id === selected) ?? FLEET[0];

  return (
    <div className="fleet">
      <div className="agg">
        <div className="kpi"><div className="k">Datacenters</div><div className="v">{FLEET_AGG.total} <small>online</small></div></div>
        <div className="kpi"><div className="k">Needs attention</div><div className="v crit">{FLEET_AGG.critical} <small>crit</small> · <span className="warn-c">{FLEET_AGG.caution} warn</span></div></div>
        <div className="kpi"><div className="k">Eclipsing &lt; 15m</div><div className="v warn">{FLEET_AGG.eclipsing}</div></div>
        <div className="kpi"><div className="k">GPUs online</div><div className="v">{FLEET_AGG.gpuOnline}<small>/{FLEET_AGG.gpuTotal}</small></div></div>
        <div className="kpi"><div className="k">Decisions pending</div><div className="v crit">{FLEET_AGG.decisions}</div></div>
      </div>

      <div className="fleet-body">
        <aside className="panel fui" aria-label="Fleet roster">
          <div className="fui-eyebrow"><span>Fleet roster</span><span>severity ▾</span></div>
          <div className="roster">
            {roster.map((a) => (
              <button
                key={a.id}
                className={`rrow${a.id === selected ? " is-sel" : ""}`}
                onClick={() => setSelected(a.id)}
                onDoubleClick={() => openAsset(a.id)}
                type="button"
              >
                <span className="sd" style={{ color: HEALTH_TOKEN[a.health] }} />
                <span className="rn"><strong>{a.id}</strong><span>{a.note}</span></span>
                <span className="rg">{a.gpu}<br />GPU</span>
              </button>
            ))}
          </div>
        </aside>

        <section className="const fui" aria-label="Constellation">
          <span className="brk tl" /><span className="brk br" />
          <div className="fui-eyebrow float"><span>Constellation · live</span><span>LEO · 51.6°</span></div>
          <Constellation selected={selected} onSelect={setSelected} />
          <div className="const-legend">
            <b className="lg-ok">nominal</b><b className="lg-warn">caution</b><b className="lg-crit">critical</b>
          </div>
          <div className="const-hint">click a datacenter · double-click to open console</div>
        </section>

        <div className="fleet-right">
          <aside className="panel fui" aria-label="Decisions awaiting you">
            <div className="fui-eyebrow"><span>Needs you · fleet queue</span><span>{FLEET_QUEUE.length}</span></div>
            {FLEET_QUEUE.map((d) =>
              d.kind === "migration" ? (
                <div key={d.id} className="qitem mig" onClick={() => setSelected(d.asset)}>
                  <div className="qh"><b>{d.label}</b><span className="qtag mig">Cross-asset</span></div>
                  <div className="mig-route">
                    <span className="a crit-c">{d.asset}</span>
                    <span className="arw">→</span>
                    <span className="a ok-c">{d.target}</span>
                  </div>
                  <p>{d.detail}</p>
                </div>
              ) : (
                <div key={d.id} className={`qitem${d.severity === "critical" ? " crit" : ""}`} onClick={() => openAsset(d.asset)}>
                  <div className="qh"><b>{d.label}</b><span className={`qtag ${d.severity === "critical" ? "crit" : "warn"}`}>{HEALTH_LABEL[d.severity]}</span></div>
                  <p>{d.detail}</p>
                </div>
              ),
            )}
          </aside>

          <aside className="panel fui peek" aria-label="Selected datacenter">
            <span className="brk tl" /><span className="brk br" />
            <div className="fui-eyebrow"><span>Selected asset</span><span style={{ color: HEALTH_TOKEN[asset.health] }}>{HEALTH_LABEL[asset.health]}</span></div>
            <h3 className="peek-id">{asset.id}</h3>
            <div className="peek-sub">{asset.note}</div>
            <div className="pgrid">
              <div><div className="k">GPUs</div><div className="v">{asset.gpu}</div></div>
              <div><div className="k">Battery</div><div className="v" style={{ color: HEALTH_TOKEN[asset.health] }}>{asset.battery}%</div></div>
              <div><div className="k">Eclipse in</div><div className="v">{asset.eclipseMin != null ? `${asset.eclipseMin}m` : "—"}</div></div>
              <div><div className="k">Health</div><div className="v" style={{ color: HEALTH_TOKEN[asset.health] }}>{HEALTH_LABEL[asset.health]}</div></div>
            </div>
            <button className="open-btn" onClick={() => openAsset(asset.id)} type="button">
              Open Ops-Loop console →
            </button>
          </aside>
        </div>
      </div>
    </div>
  );
}
