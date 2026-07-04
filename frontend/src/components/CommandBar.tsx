import { useWorldStore, type PatchMode } from "../store/worldStore";

const steps: Array<{ label: string; mode?: PatchMode }> = [
  { label: "Monitor" },
  { label: "Detect" },
  { label: "Explain" },
  { label: "Propose" },
  { label: "Approve", mode: "pending" },
  { label: "Execute", mode: "execute" },
  { label: "Verify", mode: "verify" },
];

function stepClass(mode: PatchMode, stepMode?: PatchMode): string {
  if (!stepMode) {
    return "loop-step is-done";
  }
  if (stepMode === mode || (stepMode === "verify" && mode === "verified")) {
    return mode === "verified" ? "loop-step is-done" : "loop-step is-active";
  }
  if (stepMode === "pending") {
    return mode === "pending" || mode === "replan" || mode === "modify" || mode === "reject"
      ? "loop-step is-active"
      : "loop-step is-done";
  }
  if (stepMode === "execute") {
    return mode === "verify" || mode === "verified" ? "loop-step is-done" : "loop-step";
  }
  return mode === "verified" ? "loop-step is-done" : "loop-step";
}

export default function CommandBar() {
  const telemetry = useWorldStore((state) => state.telemetry);
  const simSpeed = useWorldStore((state) => state.simSpeed);
  const connectionStatus = useWorldStore((state) => state.connectionStatus);
  const patchMode = useWorldStore((state) => state.patchMode);

  return (
    <>
      <header className="command-bar" aria-label="Mission command">
        <div className="brand">
          <div className="brand-mark">OPS</div>
          <div>
            <h1>OrbitOps command center</h1>
            <p>Supervised multi-agent operations for orbital GPU datacenters</p>
          </div>
        </div>
        <div className="mission-state">
          <span className="state-chip">
            <span className="state-dot" />
            {connectionStatus === "live" ? "live ops" : "supervised ops"}
          </span>
          <span className="hide-small">
            ground link <strong>{telemetry.groundLink}</strong>
          </span>
          <span className="hide-small">
            approval <strong>human required</strong>
          </span>
          <span className="hide-small">
            orbit <strong>{telemetry.orbitPhase}</strong>
          </span>
          <span>{simSpeed === 1 ? "1x realtime" : `${simSpeed}x simulation`}</span>
        </div>
      </header>

      <section className="ops-loop" aria-label="OrbitOps product loop">
        {steps.map((step) => (
          <div className={stepClass(patchMode, step.mode)} key={step.label}>
            {step.label}
          </div>
        ))}
      </section>
    </>
  );
}
