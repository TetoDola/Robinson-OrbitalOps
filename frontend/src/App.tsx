import { useEffect } from "react";

import {
  getActiveMissionPatch,
  getAgentsStatus,
  getCommands,
  getIncidents,
  getWorldState,
} from "./api/client";
import { connectLiveSocket } from "./api/liveSocket";
import CommandBar from "./components/CommandBar";
import IncidentStrip from "./components/IncidentStrip";
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
      getCommands(),
      getIncidents(),
      getActiveMissionPatch(),
    ]).then(([worldResult, agentsResult, commandsResult, incidentsResult, patchResult]) => {
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
      <SceneViewport />
      <CommandBar />
      <TelemetryPanel />
      <MissionPatchPanel />
      <IncidentStrip />
    </div>
  );
}
