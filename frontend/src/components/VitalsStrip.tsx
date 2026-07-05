import RadialGauge from "./RadialGauge";
import Sparkline from "./Sparkline";
import { useWorldStore } from "../store/worldStore";

const speeds = [1, 60, 600];

export default function VitalsStrip() {
  const telemetry = useWorldStore((s) => s.telemetry);
  const metrics = useWorldStore((s) => s.metrics);
  const history = useWorldStore((s) => s.metricsHistory);
  const simSpeed = useWorldStore((s) => s.simSpeed);
  const followNode = useWorldStore((s) => s.followNode);
  const setSimSpeed = useWorldStore((s) => s.setSimSpeed);
  const setFollowNode = useWorldStore((s) => s.setFollowNode);

  const battery = metrics?.battery;
  const batteryTone = battery == null ? "" : battery < 20 ? "is-hot" : battery < 40 ? "is-warn" : "";
  const btone =
    batteryTone === "is-hot" ? "var(--red)" : batteryTone === "is-warn" ? "var(--amber)" : "var(--green)";

  return (
    <div className="vitals-strip" aria-label="Vitals">
      <div className="vs-gauge">
        <RadialGauge value={battery ?? 0} tone={btone} label={telemetry.battery} sub="batt" size={46} />
      </div>
      <div className="vs-chip">
        <span className="label">solar</span>
        <b>{telemetry.solar}</b>
        <Sparkline data={history.solar} color="var(--yellow)" width={46} height={16} />
      </div>
      <div className="vs-chip is-warn">
        <span className="label">eclipse</span>
        <b>{telemetry.eclipse}</b>
        <Sparkline data={history.eclipseMin} color="var(--amber)" width={46} height={16} />
      </div>
      <div className="vs-chip is-hot">
        <span className="label">ecc / 5m</span>
        <b>{telemetry.eccTrend}</b>
        <Sparkline data={history.eccErrors} color="var(--red)" width={46} height={16} />
      </div>
      <div className="vs-chip is-hot">
        <span className="label">downlink</span>
        <b>{telemetry.downlink}</b>
      </div>
      <div className="vs-chip">
        <span className="label">load</span>
        <b>{telemetry.computeLoad}</b>
      </div>
      <div className="vs-chip">
        <span className="label">latency</span>
        <b>{telemetry.latency}</b>
      </div>

      <div className="vs-spacer" />

      <div className="vs-controls">
        <span className="label">time</span>
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
          follow
        </button>
      </div>
    </div>
  );
}
