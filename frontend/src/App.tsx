import { useEffect } from "react";

import {
  getActiveMissionPatch,
  getAgentsStatus,
  getCommands,
  getIncidents,
  getWorldState,
} from "./api/client";
import { connectLiveSocket } from "./api/liveSocket";
import AssetConsole from "./components/AssetConsole";
import CommandBar from "./components/CommandBar";
import FleetView from "./components/FleetView";
import { useAppStore } from "./store/appStore";
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

  const view = useAppStore((state) => state.view);

  return (
    <div className="app-shell">
      <CommandBar />
      <div className="view">{view === "fleet" ? <FleetView /> : <AssetConsole />}</div>
    </div>
  );
}
