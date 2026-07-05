import { useWorldStore } from "../store/worldStore";

const STAGES = ["Monitor", "Detect", "Explain", "Propose", "Approve", "Execute", "Verify"];

export default function OpsSpine() {
  const patchMode = useWorldStore((s) => s.patchMode);
  const missionPatch = useWorldStore((s) => s.missionPatch);
  const demoResetAt = useWorldStore((s) => s.demoResetAt);
  const telemetry = useWorldStore((s) => s.telemetry);
  const resetIdle = Boolean(demoResetAt && !missionPatch);

  let cur = 4; // demo default: patch-042 awaiting approval
  if (resetIdle || patchMode === "reject") cur = 0;
  else if (patchMode === "execute") cur = 5;
  else if (patchMode === "verify" || patchMode === "verified") cur = 6;
  else if (patchMode === "replan" || patchMode === "modify") cur = 3;

  const critical = !resetIdle && cur >= 3 && cur <= 4;
  const subs = [
    "all systems nominal · loop armed",
    "anomaly on Node C · ECC spike",
    "5 agents converged · root cause",
    "patch-042 assembled by commander",
    `human decision required · window ${telemetry.eclipse}`,
    "executing commands · streaming results",
    patchMode === "verified" ? "integrity restored ✓" : "verifying integrity",
  ];

  return (
    <div className={`ops-spine${critical ? " is-critical" : ""}`} aria-label="Ops loop">
      <div className="ops-track">
        <div className="ops-fill" style={{ width: `${(cur / (STAGES.length - 1)) * 100}%` }} />
      </div>
      <div className="ops-nodes">
        {STAGES.map((stage, i) => (
          <div key={stage} className={`ops-node${i < cur ? " done" : i === cur ? " active" : ""}`}>
            <span className="ops-bul">{i < cur ? "✓" : i + 1}</span>
            <span className="ops-cap">{stage}</span>
          </div>
        ))}
      </div>
      <div className="ops-sub">{subs[cur]}</div>
    </div>
  );
}
