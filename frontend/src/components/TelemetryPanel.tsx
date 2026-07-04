import { useWorldStore } from "../store/worldStore";

const speeds = [1, 60, 600];

function agentMessage(agentName: string, fallback: string): string {
  const agent = useWorldStore
    .getState()
    .agents.find((item) => item.agent === agentName || item.display_name.toLowerCase().includes(agentName));
  return agent?.message ?? fallback;
}

export default function TelemetryPanel() {
  const telemetry = useWorldStore((state) => state.telemetry);
  const simSpeed = useWorldStore((state) => state.simSpeed);
  const followNode = useWorldStore((state) => state.followNode);
  const setSimSpeed = useWorldStore((state) => state.setSimSpeed);
  const setFollowNode = useWorldStore((state) => state.setFollowNode);
  const agents = useWorldStore((state) => state.agents);

  const commander =
    agents.find((item) => item.agent === "commander_agent")?.message ??
    "fusing five agent findings into patch-042";
  const power =
    agents.find((item) => item.agent === "power_orbit_agent")?.message ??
    `eclipse recovery plan required in ${telemetry.eclipse}`;
  const integrity =
    agents.find((item) => item.agent === "radiation_integrity_agent")?.message ??
    agentMessage("integrity", `checkpoint trust degraded, downlink via ${telemetry.groundLink}`);

  return (
    <aside className="control-panel" aria-label="Orbital telemetry">
      <div className="panel-header">
        <div>
          <div className="eyebrow">OrbitOps / AKJA-01</div>
          <h2 className="panel-title">Mission risk monitor</h2>
        </div>
        <div className="clock">{telemetry.clock}</div>
      </div>

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

      <ul className="agent-feed" aria-label="Commander feed">
        <li>
          <b>COMMANDER</b>
          <span>{commander}</span>
        </li>
        <li>
          <b>POWER</b>
          <span>{power}</span>
        </li>
        <li>
          <b>INTEGRITY</b>
          <span>{integrity}</span>
        </li>
      </ul>
    </aside>
  );
}
