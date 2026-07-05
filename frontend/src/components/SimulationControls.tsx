import { useRef, useState } from "react";

import {
  getActiveMissionPatch,
  getAgentFindings,
  getAgentsRuntime,
  getAgentsStatus,
  getIncidents,
  getWorldState,
  injectSimulatorIssue,
} from "../api/client";
import { useWorldStore } from "../store/worldStore";

const issueButtons = [
  { id: "thermal-frame", label: "Thermal frame", tone: "danger" },
  { id: "radiation-spike", label: "Radiation spike", tone: "danger" },
  { id: "eclipse-risk", label: "Eclipse risk", tone: "warn" },
  { id: "downlink-constraint", label: "Downlink limit", tone: "warn" },
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

async function refreshBackendSnapshot() {
  const store = useWorldStore.getState();
  const [worldResult, agentsResult, runtimeResult, findingsResult, incidentsResult, patchResult] =
    await Promise.allSettled([
      getWorldState(),
      getAgentsStatus(),
      getAgentsRuntime(),
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
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [busyIssue, setBusyIssue] = useState<string | null>(null);
  const [lastResult, setLastResult] = useState<string>("nominal baseline armed");

  async function injectIssue(issue: string) {
    setBusyIssue(issue);
    try {
      const payload =
        issue === "thermal-frame" && selectedFile
          ? {
              image_data_url: await fileToDataUrl(selectedFile),
              asset_id: "node-c",
              source: "operator-upload",
              notes: selectedFile.name,
            }
          : {
              asset_id: issue === "vibration-fault" || issue === "thermal-frame" ? "node-c" : "orbital-dc-01",
              source: "operator-sim",
            };
      const response = await injectSimulatorIssue(issue, payload);
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
        <strong className={busyIssue ? "status-orange" : "status-yellow"}>{busyIssue ? "sending" : "ready"}</strong>
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

      <p className="sim-result">{lastResult}</p>
    </section>
  );
}
