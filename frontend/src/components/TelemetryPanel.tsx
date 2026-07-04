import { useWorldStore } from "../store/worldStore";

const speeds = [1, 60, 600];

export default function TelemetryPanel() {
  const telemetry = useWorldStore((state) => state.telemetry);
  const simSpeed = useWorldStore((state) => state.simSpeed);
  const followNode = useWorldStore((state) => state.followNode);
  const setSimSpeed = useWorldStore((state) => state.setSimSpeed);
  const setFollowNode = useWorldStore((state) => state.setFollowNode);
  const connectionStatus = useWorldStore((state) => state.connectionStatus);
  const worldVersion = useWorldStore((state) => state.worldVersion);
  const scenarioRunId = useWorldStore((state) => state.scenarioRunId);
  const demoResetAt = useWorldStore((state) => state.demoResetAt);

  return (
    <aside className="left-rail" aria-label="Overview">
      <div className="rail-brand">
        <div className="brand-mark">OPS</div>
        <div>
          <h1>OrbitOps</h1>
          <p>Orbital datacenter command</p>
        </div>
      </div>

      <nav className="rail-nav" aria-label="Primary">
        <button className="nav-item active" type="button">
          <span className="nav-icon" aria-hidden="true" />
          Overview
        </button>
      </nav>

      <section className="rail-section">
        <div className="section-header">
          <div>
            <div className="eyebrow">Mission</div>
            <h2 className="panel-title">AKJA-01</h2>
          </div>
          <span className={`connection-pill ${connectionStatus}`}>
            <span className="state-dot" />
            {connectionStatus === "live" ? "live" : "local"}
          </span>
        </div>
        <div className="clock">{telemetry.clock}</div>
        <div className="mission-meta">
          <span>orbit {telemetry.orbitPhase}</span>
          <span>link {telemetry.groundLink}</span>
          <span>{worldVersion ? `state v${worldVersion}` : scenarioRunId ?? "demo state"}</span>
        </div>
      </section>

      <section className="rail-section">
        <div className="eyebrow">Overview</div>
      <div className="metric-grid">
        <div className="metric">
          <div className="label">speed</div>
          <div className="metric-value">{telemetry.speed}</div>
          <div className="metric-note">orbital velocity</div>
        </div>
        <div className="metric">
          <div className="label">altitude</div>
          <div className="metric-value">{telemetry.altitude}</div>
          <div className="metric-note">service orbit</div>
        </div>
        <div className="metric wide">
          <div className="label">location</div>
          <div className="metric-value">{telemetry.location}</div>
          <div className="metric-note">{telemetry.groundTrack}</div>
        </div>
        <div className="metric">
          <div className="label">training load</div>
          <div className="metric-value">{telemetry.computeLoad}</div>
          <div className="metric-note">14-day run active</div>
        </div>
        <div className="metric">
          <div className="label">agent latency</div>
          <div className="metric-value">{telemetry.latency}</div>
          <div className="metric-note">command loop</div>
        </div>
      </div>
      </section>

      <section className="rail-section">
        <div className="eyebrow">Risk summary</div>
      <div className="risk-grid" aria-label="Mission critical values">
        <div className="risk-row is-warn">
          <span>Battery</span>
          <strong>{telemetry.battery}</strong>
        </div>
        <div className="risk-row is-info">
          <span>Solar input</span>
          <strong>{telemetry.solar}</strong>
        </div>
        <div className="risk-row is-warn">
          <span>Time to eclipse</span>
          <strong>{telemetry.eclipse}</strong>
        </div>
        <div className="risk-row is-info">
          <span>Radiation risk</span>
          <strong>{telemetry.radiation}</strong>
        </div>
        <div className="risk-row is-hot">
          <span>ECC trend</span>
          <strong>{telemetry.eccTrend}</strong>
        </div>
        <div className="risk-row">
          <span>Last trusted checkpoint</span>
          <strong>{telemetry.trustedCheckpoint}</strong>
        </div>
        <div className="risk-row is-hot">
          <span>Latest checkpoint</span>
          <strong>{telemetry.latestCheckpoint}</strong>
        </div>
        <div className="risk-row is-warn">
          <span>Downlink window</span>
          <strong>{telemetry.downlink}</strong>
        </div>
      </div>
      </section>

      <section className="rail-section">
        <div className="eyebrow">Scene controls</div>
      <div className="controls-row">
        <span className="label">time scale</span>
        <div className="speed-group" aria-label="Simulation speed">
          {speeds.map((speed) => (
            <button
              className={simSpeed === speed ? "active" : undefined}
              key={speed}
              onClick={() => setSimSpeed(speed)}
              type="button"
            >
              {speed}x
            </button>
          ))}
        </div>
        <button
          className={followNode ? "follow-btn active" : "follow-btn"}
          onClick={() => setFollowNode(!followNode)}
          type="button"
        >
          follow node
        </button>
      </div>
      </section>

      <div className="rail-footer">
        <span>{demoResetAt ? "baseline reset" : "human approval required"}</span>
      </div>
    </aside>
  );
}
