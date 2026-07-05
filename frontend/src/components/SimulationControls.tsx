import { useRef, useState } from "react";

import {
  getActiveMissionPatch,
  getAiStatus,
  getAgentFindings,
  getAgentsRuntime,
  getAgentsStatus,
  getIncidents,
  getWorldState,
  injectSimulatorIssue,
} from "../api/client";
import { FAN_AUDIO_DURATION_SECONDS, renderFanAudioMp3DataUrl } from "../services/fanAudio";
import { useWorldStore, type CoolingTrendSample } from "../store/worldStore";
import { IRCameraCanvas, renderIrFrameDataUrl, type IrNodeTarget } from "./IRCamPopup";

// The thermal-frame scenario drives node-c to 91 C on the backend; render the
// simulated IR capture at that incident temperature so the frame sent to the
// model matches the story, not the pre-injection nominal board.
const SIMULATED_INCIDENT_TEMP_C = 91;

const issueButtons = [
  { id: "thermal-frame", label: "Thermal frame", tone: "danger" },
  { id: "radiation-spike", label: "Radiation spike", tone: "danger" },
  { id: "eclipse-risk", label: "Eclipse risk", tone: "warn" },
  { id: "downlink-constraint", label: "5 TB data request", tone: "warn" },
  { id: "workload-stall", label: "Rank stall", tone: "warn" },
  { id: "vibration-fault", label: "Vibration fault", tone: "warn" },
];

function fileToDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error ?? new Error("Unable to read image"));
    reader.readAsDataURL(file);
  });
}

function humanize(value: string): string {
  return value.replace(/[_-]+/g, " ");
}

function formatClock(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "";
  return parsed.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function coolingChartTrace(samples: CoolingTrendSample[], targetTempC: number): { points: string; targetY: number } {
  const fallbackSample = { time: "", tempC: targetTempC, fanPct: 0 };
  const chartSamples =
    samples.length > 1
      ? samples
      : samples.length === 1
        ? [samples[0], { ...samples[0], time: "" }]
        : [fallbackSample, fallbackSample];
  const temps = [...chartSamples.map((sample) => sample.tempC), targetTempC];
  const minTemp = Math.min(...temps);
  const maxTemp = Math.max(...temps);
  const range = Math.max(1, maxTemp - minTemp);
  const width = 100;
  const height = 100;
  const targetY = height - ((targetTempC - minTemp) / range) * height;

  return {
    points: chartSamples
      .map((sample, index) => {
        const x = (index / (chartSamples.length - 1)) * width;
        const y = height - ((sample.tempC - minTemp) / range) * height;
        return `${x.toFixed(2)},${y.toFixed(2)}`;
      })
      .join(" "),
    targetY,
  };
}

export function CoolingTrendPanel({ className = "" }: { className?: string }) {
  const coolingTrend = useWorldStore((state) => state.coolingTrend);
  const latestSample = coolingTrend.samples[coolingTrend.samples.length - 1] ?? null;
  if (coolingTrend.status === "idle" && coolingTrend.samples.length === 0) {
    return null;
  }

  const trace = coolingChartTrace(coolingTrend.samples, coolingTrend.targetTempC);
  const currentTemp = latestSample?.tempC ?? coolingTrend.baselineTempC;
  const dropC = Math.max(0, coolingTrend.baselineTempC - currentTemp);
  const fanPct = latestSample?.fanPct ?? 100;
  const classes = ["cooling-trend", `is-${coolingTrend.status}`, className].filter(Boolean).join(" ");

  return (
    <div className={classes} aria-live="polite">
      <div className="cooling-trend-head">
        <span className="label">local cooling</span>
        <strong>{coolingTrend.message}</strong>
        <b>{currentTemp ? `${currentTemp.toFixed(1)} C` : "--"}</b>
      </div>
      <div className="cooling-chart-frame">
        <svg className="cooling-chart" viewBox="0 0 100 100" preserveAspectRatio="none" role="img" aria-label="Temperature trend">
          <line className="cooling-target" x1="0" x2="100" y1={trace.targetY} y2={trace.targetY} />
          <polyline points={trace.points} />
        </svg>
      </div>
      <div className="cooling-trend-meta">
        <span>{dropC > 0 ? `${dropC.toFixed(1)} C drop` : "trace starting"}</span>
        <span>fan {fanPct}%</span>
        <span>target {coolingTrend.targetTempC ? coolingTrend.targetTempC.toFixed(1) : "--"} C</span>
      </div>
    </div>
  );
}

async function refreshBackendSnapshot() {
  const store = useWorldStore.getState();
  const [worldResult, agentsResult, runtimeResult, aiResult, findingsResult, incidentsResult, patchResult] =
    await Promise.allSettled([
      getWorldState(),
      getAgentsStatus(),
      getAgentsRuntime(),
      getAiStatus(),
      getAgentFindings(),
      getIncidents(),
      getActiveMissionPatch(),
    ]);

  if (worldResult.status === "fulfilled") {
    store.setWorldState(worldResult.value.state, worldResult.value.version, worldResult.value.scenario_run_id);
  }
  if (agentsResult.status === "fulfilled") {
    store.setAgents(agentsResult.value.agents);
  }
  if (runtimeResult.status === "fulfilled") {
    store.setAgentRuntime(runtimeResult.value.agents);
  }
  if (aiResult.status === "fulfilled") {
    store.setAiStatus(aiResult.value);
  }
  if (findingsResult.status === "fulfilled") {
    store.setAgentFindings(findingsResult.value.findings);
  }
  if (incidentsResult.status === "fulfilled") {
    store.setIncidents(incidentsResult.value.incidents);
  }
  if (patchResult.status === "fulfilled") {
    store.setMissionPatch(patchResult.value.mission_patch);
  }
}

export default function SimulationControls() {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const aiStatus = useWorldStore((state) => state.aiStatus);
  const workflowEvents = useWorldStore((state) => state.workflowEvents);
  const worldState = useWorldStore((state) => state.worldState);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [busyIssue, setBusyIssue] = useState<string | null>(null);
  const [lastResult, setLastResult] = useState<string>("nominal baseline armed");
  const latestThermalInput = worldState?.thermal.latest_visual_input ?? null;
  const preferredNodeId =
    latestThermalInput?.asset_id ??
    (worldState?.thermal.hotspot_node && worldState.thermal.hotspot_node !== "none"
      ? worldState.thermal.hotspot_node
      : "node-c");
  const thermalNode = worldState?.nodes.find((node) => node.id === preferredNodeId);
  const irNode: IrNodeTarget = {
    id: preferredNodeId,
    status: thermalNode?.status ?? worldState?.thermal.cooling_status ?? "nominal",
    tempC: thermalNode?.temp_c ?? worldState?.thermal.highest_temp_c ?? 62,
  };

  async function injectIssue(issue: string) {
    setBusyIssue(issue);
    const store = useWorldStore.getState();
    store.pushWorkflowEvent({
      id: `operator-${issue}-${Date.now()}`,
      time: new Date().toISOString(),
      label: "Operator input",
      detail: issue.replace(/-/g, " "),
      status: "running",
    });
    try {
      const simulatedIrFrame =
        issue === "thermal-frame" && !selectedFile
          ? await renderIrFrameDataUrl({
              id: "node-c",
              status: "thermal_risk",
              tempC: Math.max(irNode.tempC, SIMULATED_INCIDENT_TEMP_C),
            })
          : null;
      const fanAudio =
        issue === "thermal-frame" || issue === "vibration-fault"
          ? {
              audio_data_url: renderFanAudioMp3DataUrl({ severity: 1 }),
              audio_mime_type: "audio/mpeg",
              audio_duration_s: FAN_AUDIO_DURATION_SECONDS,
              audio_notes: "Synthetic MP3: high-RPM fan surge with bearing whine and intermittent warning chirps.",
            }
          : {};
      const payload =
        issue === "thermal-frame" && selectedFile
          ? {
              image_data_url: await fileToDataUrl(selectedFile),
              asset_id: "node-c",
              source: "operator-upload",
              notes: selectedFile.name,
              ...fanAudio,
            }
          : issue === "thermal-frame" && simulatedIrFrame
            ? {
                image_data_url: simulatedIrFrame,
                asset_id: "node-c",
                source: "ir-cam-sim",
                notes: "Simulated IR capture: thermal overlay on B200 board plus fan audio.",
                ...fanAudio,
              }
            : {
                asset_id: issue === "vibration-fault" || issue === "thermal-frame" ? "node-c" : "orbital-dc-01",
                source: "operator-sim",
                ...(issue === "vibration-fault" ? fanAudio : {}),
              };
      const response = await injectSimulatorIssue(issue, payload);
      store.pushWorkflowEvent({
        id: `backend-${issue}-${Date.now()}`,
        time: new Date().toISOString(),
        label: "Backend accepted",
        detail: response.finding_ids.length ? `${response.finding_ids.length} finding(s)` : "no finding",
        status: "complete",
      });
      if (response.analysis_status) {
        const blocked = response.analysis_status.includes("blocked");
        store.pushWorkflowEvent({
          id: `ai-${issue}-${Date.now()}`,
          time: new Date().toISOString(),
          label: "Thermal AI analysis",
          detail: response.analysis_status.replace(/_/g, " "),
          status: blocked ? "blocked" : "complete",
        });
      }
      if (response.mission_patch_id) {
        store.pushWorkflowEvent({
          id: `patch-${issue}-${Date.now()}`,
          time: new Date().toISOString(),
          label: "Mission patch ready",
          detail: response.mission_patch_id.slice(0, 8),
          status: "running",
        });
      }
      await refreshBackendSnapshot();
      setLastResult(
        response.analysis_status
          ? `${issue.replace(/-/g, " ")}: ${response.analysis_status}`
          : `${issue.replace(/-/g, " ")} injected`,
      );
    } catch {
      setLastResult(`${issue.replace(/-/g, " ")} failed`);
    } finally {
      setBusyIssue(null);
    }
  }

  return (
    <section className="rail-section simulation-panel" aria-label="Operator simulation controls">
      <div className="section-header compact">
        <div>
          <div className="eyebrow">Simulate</div>
          <h3 className="panel-title">Detector input</h3>
        </div>
        <strong className={busyIssue ? "status-cyan" : "status-green"}>{busyIssue ? "sending" : "ready"}</strong>
      </div>

      <div className="ai-status-row">
        <span>AI</span>
        <strong className={aiStatus?.connected ? "status-green" : aiStatus?.enabled ? "status-orange" : "status-red"}>
          {aiStatus?.connected ? "connected" : aiStatus?.enabled ? "missing key" : "offline"}
        </strong>
        <small>{aiStatus?.multimodal_model ?? "Nemotron status pending"}</small>
      </div>

      <div className="sim-grid">
        {issueButtons.map((issue) => (
          <button
            className={`sim-btn ${issue.tone}`}
            disabled={busyIssue !== null}
            key={issue.id}
            onClick={() => void injectIssue(issue.id)}
            type="button"
          >
            {busyIssue === issue.id ? "Sending..." : issue.label}
          </button>
        ))}
      </div>

      <div className="thermal-upload">
        <input
          accept="image/*"
          hidden
          onChange={(event) => setSelectedFile(event.target.files?.[0] ?? null)}
          ref={fileInputRef}
          type="file"
        />
        <button className="sim-upload" disabled={busyIssue !== null} onClick={() => fileInputRef.current?.click()} type="button">
          Select thermal image
        </button>
        <span>{selectedFile ? selectedFile.name : "sample frame if empty"}</span>
      </div>

      <div className="sim-ir-camera" aria-label="Simulated IR camera">
        <div className="sim-ir-head">
          <span className="eyebrow">ir camera</span>
          <strong>{humanize(irNode.id)}</strong>
          <b className={latestThermalInput ? "status-yellow" : "status-cyan"}>
            {latestThermalInput ? humanize(latestThermalInput.analysis_status) : "standby"}
          </b>
        </div>
        <IRCameraCanvas node={irNode} sourceImageUrl={latestThermalInput?.image_data_url} />
        <div className="sim-ir-meta">
          <span>{latestThermalInput?.source ?? "simulated feed"}</span>
          <span>{irNode.tempC.toFixed(1)}&deg;C max</span>
        </div>
      </div>

      <p className="sim-result">{lastResult}</p>

      <div className="workflow-run" aria-label="Live workflow run">
        {(workflowEvents.length
          ? workflowEvents
          : [{ id: "idle", time: "", label: "Monitoring", detail: "Waiting for detector input", status: "info" as const }]
        )
          .slice(0, 7)
          .map((event) => (
            <div className={`workflow-row ${event.status}`} key={event.id}>
              <i aria-hidden="true" />
              <span>
                <strong>
                  {event.label}
                  {event.time ? <time>{formatClock(event.time)}</time> : null}
                </strong>
                {event.detail}
              </span>
            </div>
          ))}
      </div>
    </section>
  );
}
