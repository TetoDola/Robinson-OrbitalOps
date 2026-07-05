import MeterBar from "./MeterBar";
import RadialGauge from "./RadialGauge";
import Sparkline from "./Sparkline";
import { useWorldStore } from "../store/worldStore";

const speeds = [1, 60, 600];

/** GB the full checkpoint needs; the downlink window is measured against it. */
const CHECKPOINT_GB = 180;

export default function TelemetryPanel() {
  const telemetry = useWorldStore((state) => state.telemetry);
  const metrics = useWorldStore((state) => state.metrics);
  const history = useWorldStore((state) => state.metricsHistory);
  const simSpeed = useWorldStore((state) => state.simSpeed);
  const followNode = useWorldStore((state) => state.followNode);
  const setSimSpeed = useWorldStore((state) => state.setSimSpeed);
  const setFollowNode = useWorldStore((state) => state.setFollowNode);
  const demoResetAt = useWorldStore((state) => state.demoResetAt);

  const battery = metrics?.battery;
  const batteryTone = battery == null ? "" : battery < 20 ? "is-hot" : battery < 40 ? "is-warn" : "";
  const eclipseMin = metrics?.eclipseMin;
  const downlinkWindow = metrics?.downlinkWindowGb;

  return (
    <aside className="left-rail" aria-label="Telemetry">
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
          <Sparkline
            data={history.computeLoad}
            color="var(--cyan)"
            width={116}
            ariaLabel={`Training load trend, currently ${telemetry.computeLoad}`}
          />
          <div className="metric-note">14-day run active</div>
        </div>
        <div className="metric">
          <div className="label">agent latency</div>
          <div className="metric-value">{telemetry.latency}</div>
          <Sparkline
            data={history.latency}
            color="var(--muted)"
            width={116}
            ariaLabel={`Agent latency trend, currently ${telemetry.latency}`}
          />
          <div className="metric-note">command loop</div>
        </div>
      </div>
      </section>

      <section className="rail-section">
        <div className="eyebrow">Risk summary</div>
      <div className="trend-list" aria-label="Mission critical values">
        <div className="trend-row gauge-row">
          <RadialGauge
            value={battery ?? 0}
            tone={batteryTone === "is-hot" ? "var(--red)" : batteryTone === "is-warn" ? "var(--amber)" : "var(--green)"}
            label={telemetry.battery}
            sub="battery"
          />
          <div className="gauge-meta">
            <span className="label">reserve target 40%</span>
            <span>eclipse {telemetry.eclipse}</span>
          </div>
        </div>

        <div className="trend-row">
          <div className="trend-head">
            <span>Solar input</span>
            <strong>{telemetry.solar}</strong>
          </div>
          <Sparkline
            data={history.solar}
            color="var(--yellow)"
            width={232}
            height={22}
            ariaLabel={`Solar input trend, currently ${telemetry.solar}`}
          />
        </div>

        <div className="trend-row">
          <div className={`trend-head ${eclipseMin != null && eclipseMin < 10 ? "is-warn" : ""}`}>
            <span>Time to eclipse</span>
            <strong>{telemetry.eclipse}</strong>
          </div>
          <Sparkline
            data={history.eclipseMin}
            color="var(--amber)"
            width={232}
            height={22}
            ariaLabel={`Time to eclipse trend, currently ${telemetry.eclipse}`}
          />
        </div>

        <div className="trend-row">
          <div className="trend-head is-hot">
            <span>ECC errors / 5 min</span>
            <strong>{telemetry.eccTrend}</strong>
          </div>
          <Sparkline
            data={history.eccErrors}
            color="var(--red)"
            width={232}
            height={22}
            ariaLabel={`ECC error trend, ${telemetry.eccTrend}`}
          />
        </div>

        <div className="trend-row">
          <div className={`trend-head ${downlinkWindow != null && downlinkWindow < CHECKPOINT_GB ? "is-hot" : ""}`}>
            <span>Downlink window</span>
            <strong>{telemetry.downlink}</strong>
          </div>
          <MeterBar
            value={downlinkWindow ?? 0}
            max={CHECKPOINT_GB}
            target={CHECKPOINT_GB}
            zones={[
              { upTo: 60, tone: "var(--red)" },
              { upTo: CHECKPOINT_GB, tone: "var(--amber)" },
              { upTo: 1e9, tone: "var(--green)" },
            ]}
            ariaLabel={`Downlink window ${telemetry.downlink}, checkpoint needs ${CHECKPOINT_GB} gigabytes`}
          />
        </div>

        <div className="risk-row is-info">
          <span>Radiation risk</span>
          <strong>{telemetry.radiation}</strong>
        </div>
        <div className="risk-row">
          <span>Last trusted checkpoint</span>
          <strong>{telemetry.trustedCheckpoint}</strong>
        </div>
        <div className="risk-row is-hot">
          <span>Latest checkpoint</span>
          <strong>{telemetry.latestCheckpoint}</strong>
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
