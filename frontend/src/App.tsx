import { useEffect } from "react";

import {
  getActiveMissionPatch,
  getAgentFindings,
  getAgentsRuntime,
  getAgentsStatus,
  getCommands,
  getIncidents,
  getWorldState,
} from "./api/client";
import { connectLiveSocket } from "./api/liveSocket";
import MissionPatchPanel from "./components/MissionPatchPanel";
import SceneViewport from "./components/SceneViewport";
import TelemetryPanel from "./components/TelemetryPanel";
import { useWorldStore } from "./store/worldStore";

export default function App() {
  useEffect(() => {
    const store = useWorldStore.getState();

    void Promise.allSettled([
      getWorldState(),
      getAgentsStatus(),
      getAgentsRuntime(),
      getAgentFindings(),
      getCommands(),
      getIncidents(),
      getActiveMissionPatch(),
    ]).then(([worldResult, agentsResult, runtimeResult, findingsResult, commandsResult, incidentsResult, patchResult]) => {
      if (worldResult.status === "fulfilled") {
        store.setWorldState(
          worldResult.value.state,
          worldResult.value.version,
          worldResult.value.scenario_run_id,
        );
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
      if (commandsResult.status === "fulfilled") {
        store.setCommands(commandsResult.value.commands);
      }
      if (incidentsResult.status === "fulfilled") {
        store.setIncidents(incidentsResult.value.incidents);
      }
      if (patchResult.status === "fulfilled") {
        store.setMissionPatch(patchResult.value.mission_patch);
      }
    });

    return connectLiveSocket();
  }, []);

  return (
    <div className="app-shell">
      <TelemetryPanel />
      <SceneViewport />
      <MissionPatchPanel />
    </div>
  );
}
