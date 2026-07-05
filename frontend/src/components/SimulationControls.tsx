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
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [busyIssue, setBusyIssue] = useState<string | null>(null);
  const [lastResult, setLastResult] = useState<string>("nominal baseline armed");

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
        <strong className={aiStatus?.enabled ? "status-green" : "status-orange"}>
          {aiStatus?.enabled ? "connected" : "offline"}
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
                <strong>{event.label}</strong>
                {event.detail}
              </span>
            </div>
          ))}
      </div>
    </section>
  );
}
